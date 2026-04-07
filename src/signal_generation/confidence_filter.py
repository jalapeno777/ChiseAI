"""Confidence filter for signal threshold enforcement.

Implements the 75% actionable threshold filter for signals.
Signals below 75% are logged but not surfaced as actionable.

Supports optional LLM-enhanced confidence analysis when USE_LLM_ENHANCEMENT
environment variable is set to "true".
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from signal_generation.models import Signal

logger = logging.getLogger(__name__)

# LLM enhancer availability flag
LLM_ENHANCER_AVAILABLE = False
try:
    from signal_generation.llm_enhancer import LLMConfidenceEnhancer

    LLM_ENHANCER_AVAILABLE = True
except ImportError:
    logger.debug("LLMConfidenceEnhancer not available")


# InfluxDB availability flag - graceful degradation if not installed
INFLUXDB_AVAILABLE = False
try:
    import influxdb_client  # noqa: F401
    from influxdb_client.client.write.point import Point  # noqa: F401
    from influxdb_client.client.write_api import SYNCHRONOUS  # noqa: F401

    INFLUXDB_AVAILABLE = True
except ImportError:
    pass


@dataclass
class FilterResult:
    """Result of confidence filtering.

    Attributes:
        is_actionable: Whether signal meets actionable threshold
        threshold: The confidence threshold used (0.0-1.0)
        confidence: The signal's confidence score
        reason: Explanation of filter decision
        llm_enhanced: Whether confidence was LLM-enhanced
        llm_rationale: LLM rationale for enhancement (if applicable)
        base_confidence: Original confidence before LLM enhancement
    """

    is_actionable: bool
    threshold: float
    confidence: float
    reason: str
    llm_enhanced: bool = False
    llm_rationale: str | None = None
    base_confidence: float | None = None


@dataclass
class FilterMetrics:
    """Metrics for confidence filter tracking.

    Attributes:
        total_processed: Total signals processed
        signals_filtered: Signals filtered (below threshold)
        signals_passed: Signals passed (above threshold)
        filter_rate: Ratio of filtered to total (0.0-1.0)
        last_updated: Timestamp of last metric update
    """

    total_processed: int = 0
    signals_filtered: int = 0
    signals_passed: int = 0
    last_updated: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def filter_rate(self) -> float:
        """Calculate filter rate (filtered/total).

        Returns:
            Filter rate as ratio (0.0-1.0), 0.0 if no signals processed
        """
        if self.total_processed == 0:
            return 0.0
        return self.signals_filtered / self.total_processed

    @property
    def pass_rate(self) -> float:
        """Calculate pass rate (passed/total).

        Returns:
            Pass rate as ratio (0.0-1.0), 0.0 if no signals processed
        """
        if self.total_processed == 0:
            return 0.0
        return self.signals_passed / self.total_processed

    def to_dict(self) -> dict:
        """Convert metrics to dictionary for export.

        Returns:
            Dictionary with metric values
        """
        return {
            "total_processed": self.total_processed,
            "signals_filtered": self.signals_filtered,
            "signals_passed": self.signals_passed,
            "filter_rate": self.filter_rate,
            "pass_rate": self.pass_rate,
            "last_updated": self.last_updated.isoformat(),
        }

    def for_influxdb(self) -> dict:
        """Format metrics for InfluxDB export.

        Returns:
            Dictionary suitable for InfluxDB Point fields
        """
        return {
            "total_processed": self.total_processed,
            "signals_filtered": self.signals_filtered,
            "signals_passed": self.signals_passed,
            "filter_rate": self.filter_rate,
            "pass_rate": self.pass_rate,
        }


class ConfidenceFilter:
    """Filter signals based on confidence threshold.

    Default threshold is 75% (0.75) for actionable signals.
    Signals below threshold are logged but not surfaced.

    Threshold can be configured via:
    1. Constructor parameter
    2. SIGNAL_CONFIDENCE_THRESHOLD environment variable
    3. Default value (0.75)

    Supports optional LLM-enhanced confidence analysis when
    USE_LLM_ENHANCEMENT environment variable is "true".
    When enabled, blends base confidence with LLM analysis:
    final_confidence = (base_confidence * 0.7) + (llm_confidence * 0.3)

    Tracks metrics for Grafana export:
    - Total signals processed
    - Signals filtered (below threshold)
    - Signals passed (above threshold)
    - Filter rate (filtered/total)
    - LLM enhancement rate (if enabled)
    """

    DEFAULT_THRESHOLD = 0.75
    MIN_THRESHOLD = 0.50
    MAX_THRESHOLD = 0.95

    def __init__(
        self,
        threshold: float | None = None,
        use_llm_enhancement: bool | None = None,
    ):
        """Initialize confidence filter.

        Args:
            threshold: Optional custom threshold (0.0-1.0).
                If not provided, uses environment variable or default.
            use_llm_enhancement: Whether to use LLM enhancement.
                If not provided, uses USE_LLM_ENHANCEMENT env var.
        """
        self.threshold = self._resolve_threshold(threshold)
        self.metrics = FilterMetrics()
        self._influx_exporter: InfluxDBExporter | None = None

        # Initialize LLM enhancer if available and enabled
        self._llm_enhancer: Any = None
        self._use_llm = self._resolve_use_llm(use_llm_enhancement)
        self._llm_enhanced_count = 0

        if self._use_llm and LLM_ENHANCER_AVAILABLE:
            try:
                self._llm_enhancer = LLMConfidenceEnhancer()  # type: ignore
                if self._llm_enhancer.is_available():
                    provider = self._llm_enhancer.get_provider()
                    logger.info(
                        f"ConfidenceFilter initialized with threshold: "
                        f"{self.threshold:.0%} and LLM enhancement "
                        f"(provider: {provider})"
                    )
                else:
                    logger.warning(
                        "LLM enhancement enabled but no LLM provider available"
                    )
                    self._llm_enhancer = None
            except Exception as e:
                logger.warning(f"Failed to initialize LLM enhancer: {e}")
                self._llm_enhancer = None
        else:
            logger.info(
                f"ConfidenceFilter initialized with threshold: {self.threshold:.0%} "
                f"(LLM enhancement disabled)"
            )

    def _resolve_threshold(self, override: float | None) -> float:
        """Resolve threshold from override, env var, or default.

        Args:
            override: Optional threshold override

        Returns:
            Resolved threshold value
        """
        if override is not None:
            return self._clamp_threshold(override)

        env_threshold = os.getenv("SIGNAL_CONFIDENCE_THRESHOLD")
        if env_threshold:
            try:
                return self._clamp_threshold(float(env_threshold))
            except ValueError:
                logger.warning(
                    f"Invalid SIGNAL_CONFIDENCE_THRESHOLD: {env_threshold}, "
                    f"using default {self.DEFAULT_THRESHOLD}"
                )

        return self.DEFAULT_THRESHOLD

    def _resolve_use_llm(self, override: bool | None) -> bool:
        """Resolve whether to use LLM enhancement from override or env var.

        Args:
            override: Optional override value

        Returns:
            True if LLM enhancement should be used
        """
        if override is not None:
            return override

        env_value = os.getenv("USE_LLM_ENHANCEMENT", "false").lower()
        return env_value in ("true", "1", "yes", "on")

    def _clamp_threshold(self, threshold: float) -> float:
        """Clamp threshold to valid range.

        Args:
            threshold: Proposed threshold value

        Returns:
            Clamped threshold
        """
        clamped = max(self.MIN_THRESHOLD, min(self.MAX_THRESHOLD, threshold))
        if clamped != threshold:
            logger.warning(
                f"Threshold {threshold} clamped to valid range "
                f"[{self.MIN_THRESHOLD}, {self.MAX_THRESHOLD}]"
            )
        return clamped

    def filter(
        self,
        signal: Signal,
        indicators: dict[str, Any] | None = None,
    ) -> FilterResult:
        """Filter a signal based on confidence threshold.

        Optionally uses LLM enhancement if enabled. When LLM enhancement
        is active, the final confidence is blended:
        final = (base_confidence * 0.7) + (llm_confidence * 0.3)

        Args:
            signal: The signal to filter
            indicators: Optional technical indicators for LLM analysis

        Returns:
            FilterResult with decision and explanation
        """
        base_confidence = signal.confidence
        final_confidence = base_confidence
        llm_enhanced = False
        llm_rationale = None

        # Apply LLM enhancement if enabled and available
        if self._use_llm and self._llm_enhancer is not None:
            try:
                llm_result = self._llm_enhancer.enhance(signal, indicators)
                final_confidence = self._llm_enhancer.calculate_blended_confidence(
                    base_confidence, llm_result.enhanced_confidence
                )
                llm_enhanced = True
                llm_rationale = llm_result.rationale
                self._llm_enhanced_count += 1

                logger.debug(
                    f"LLM enhancement applied: {base_confidence:.1%} -> "
                    f"{final_confidence:.1%} "
                    f"(LLM: {llm_result.enhanced_confidence:.0f}%)"
                )
            except Exception as e:
                logger.warning(f"LLM enhancement failed, using base confidence: {e}")
                final_confidence = base_confidence

        self.metrics.total_processed += 1

        # Guard against NaN/inf in final_confidence (defense in depth)
        if (
            not isinstance(final_confidence, float)
            or math.isnan(final_confidence)
            or math.isinf(final_confidence)
        ):
            logger.warning(
                f"Invalid final_confidence {final_confidence!r} detected, "
                f"marking signal as non-actionable"
            )
            final_confidence = 0.0

        if final_confidence >= self.threshold:
            self.metrics.signals_passed += 1
            self.metrics.last_updated = datetime.now(UTC)
            return FilterResult(
                is_actionable=True,
                threshold=self.threshold,
                confidence=final_confidence,
                reason=(
                    f"Signal confidence {final_confidence:.1%} meets threshold "
                    f"{self.threshold:.0%}"
                    + (" (LLM-enhanced)" if llm_enhanced else "")
                ),
                llm_enhanced=llm_enhanced,
                llm_rationale=llm_rationale,
                base_confidence=base_confidence,
            )
        else:
            self.metrics.signals_filtered += 1
            self.metrics.last_updated = datetime.now(UTC)
            return FilterResult(
                is_actionable=False,
                threshold=self.threshold,
                confidence=final_confidence,
                reason="confidence_below_threshold",
                llm_enhanced=llm_enhanced,
                llm_rationale=llm_rationale,
                base_confidence=base_confidence,
            )

    def should_emit(self, signal: Signal) -> bool:
        """Quick check if signal should be emitted.

        Args:
            signal: The signal to check

        Returns:
            True if signal meets actionable threshold
        """
        # Guard against invalid confidence (defense in depth)
        if not isinstance(signal.confidence, float) or math.isnan(signal.confidence):
            return False
        return bool(signal.confidence >= self.threshold)

    def log_non_actionable(self, signal: Signal) -> None:
        """Log a non-actionable signal for audit purposes.

        Args:
            signal: The non-actionable signal to log
        """
        logger.info(
            f"Non-actionable signal: {signal.token} [{signal.direction_str}] "
            f"confidence={signal.confidence:.1%} (threshold={self.threshold:.0%})"
        )

    def get_threshold_percent(self) -> float:
        """Get threshold as percentage (0-100)."""
        return self.threshold * 100

    def get_metrics(self) -> FilterMetrics:
        """Get current filter metrics.

        Returns:
            FilterMetrics with current counts and rates
        """
        return self.metrics

    def get_metrics_dict(self) -> dict:
        """Get metrics as dictionary for dashboards.

        Returns:
            Dictionary with metric values
        """
        return self.metrics.to_dict()

    def set_influx_exporter(self, exporter: InfluxDBExporter) -> None:
        """Set InfluxDB exporter for metrics export.

        Args:
            exporter: InfluxDBExporter instance for metrics export
        """
        self._influx_exporter = exporter
        logger.info("InfluxDB exporter configured for confidence filter")

    def export_to_influxdb(self) -> bool:
        """Export current metrics to InfluxDB.

        Returns:
            True if export successful, False otherwise
        """
        if self._influx_exporter is None:
            logger.warning("No InfluxDB exporter configured")
            return False

        return self._influx_exporter.export_filter_metrics(self.metrics)

    def reset_metrics(self) -> None:
        """Reset all metrics to initial state."""
        self.metrics = FilterMetrics()
        logger.info("Confidence filter metrics reset")

    def get_filter_rate_trend(self) -> list[dict]:
        """Get filter rate trend for visualization.

        Returns:
            List of trend data points (currently returns current state)
        """
        # For now, return current state - can be extended to track history
        return [self.metrics.to_dict()]

    def is_llm_enhancement_enabled(self) -> bool:
        """Check if LLM enhancement is enabled.

        Returns:
            True if LLM enhancement is active
        """
        return self._use_llm and self._llm_enhancer is not None

    def get_llm_enhancement_stats(self) -> dict[str, Any]:
        """Get LLM enhancement statistics.

        Returns:
            Dictionary with LLM enhancement stats
        """
        if not self._llm_enhancer:
            return {
                "enabled": False,
                "provider": "none",
                "enhanced_count": 0,
                "cache_stats": {},
            }

        return {
            "enabled": True,
            "provider": self._llm_enhancer.get_provider(),
            "enhanced_count": self._llm_enhanced_count,
            "cache_stats": self._llm_enhancer.get_cache_stats(),
        }

    def get_llm_interaction_log(self) -> list[dict[str, Any]]:
        """Get LLM interaction log for audit.

        Returns:
            List of LLM interaction log entries
        """
        if self._llm_enhancer:
            return self._llm_enhancer.get_interaction_log()
        return []


class InfluxDBExporter:
    """Export confidence filter metrics to InfluxDB for Grafana visualization.

    Uses the same InfluxDB connection pattern as data_quality_monitoring.
    """

    def __init__(
        self,
        influx_url: str = "http://chiseai-influxdb:18087",
        influx_token: str = "",
        influx_org: str = "chiseai",
        influx_bucket: str = "chiseai",
    ):
        """Initialize InfluxDB exporter.

        Args:
            influx_url: InfluxDB URL (default uses chiseai network)
            influx_token: InfluxDB token
            influx_org: InfluxDB organization
            influx_bucket: Bucket for confidence filter metrics
        """
        self.influx_url = influx_url
        self.influx_token = influx_token
        self.influx_org = influx_org
        self.influx_bucket = influx_bucket
        self._client: Any = None
        self._write_api: Any = None

    def _get_client(self) -> Any:
        """Get or create InfluxDB client."""
        if not INFLUXDB_AVAILABLE:
            logger.warning("influxdb-client not installed")
            return None

        if self._client is None:
            try:
                from influxdb_client.client.influxdb_client import (
                    InfluxDBClient as Client,
                )
                from influxdb_client.client.write_api import SYNCHRONOUS as Sync

                self._client = Client(
                    url=self.influx_url,
                    token=self.influx_token,
                    org=self.influx_org,
                )
                self._write_api = self._client.write_api(write_options=Sync)
            except Exception as e:
                logger.error(f"Failed to create InfluxDB client: {e}")
                return None

        return self._client

    def export_filter_metrics(self, metrics: FilterMetrics) -> bool:
        """Export filter metrics to InfluxDB.

        Args:
            metrics: FilterMetrics to export

        Returns:
            True if export successful
        """
        if not INFLUXDB_AVAILABLE:
            logger.debug("InfluxDB not available, skipping export")
            return False

        client = self._get_client()
        if client is None:
            return False

        try:
            # Import Point here to avoid issues when not available
            from influxdb_client.client.write.point import Point

            point = (
                Point("confidence_filter")
                .field("total_processed", metrics.total_processed)
                .field("signals_filtered", metrics.signals_filtered)
                .field("signals_passed", metrics.signals_passed)
                .field("filter_rate", metrics.filter_rate)
                .field("pass_rate", metrics.pass_rate)
                .time(metrics.last_updated)
            )

            if self._write_api:
                self._write_api.write(
                    bucket=self.influx_bucket,
                    org=self.influx_org,
                    record=point,
                )

            logger.debug(
                f"Exported confidence filter metrics: "
                f"total={metrics.total_processed}, "
                f"filtered={metrics.signals_filtered}, "
                f"passed={metrics.signals_passed}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to export filter metrics: {e}")
            return False

    def export_single_filter_event(
        self,
        is_actionable: bool,
        confidence: float,
        threshold: float,
    ) -> bool:
        """Export a single filter event to InfluxDB.

        Args:
            is_actionable: Whether signal passed the filter
            confidence: Signal confidence score
            threshold: Filter threshold used

        Returns:
            True if export successful
        """
        if not INFLUXDB_AVAILABLE:
            return False

        client = self._get_client()
        if client is None:
            return False

        try:
            # Import Point here to avoid issues when not available
            from influxdb_client.client.write.point import Point

            now = datetime.now(UTC)
            point = (
                Point("confidence_filter_events")
                .tag("result", "actionable" if is_actionable else "filtered")
                .field("confidence", confidence)
                .field("threshold", threshold)
                .field("is_actionable", 1 if is_actionable else 0)
                .time(now)
            )

            if self._write_api:
                self._write_api.write(
                    bucket=self.influx_bucket,
                    org=self.influx_org,
                    record=point,
                )

            return True

        except Exception as e:
            logger.error(f"Failed to export filter event: {e}")
            return False
