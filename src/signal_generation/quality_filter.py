"""Quality filter for signal threshold enforcement.

Implements the quality_score threshold filter for signals.
Signals with quality_score below threshold are filtered before trading.

Supports configurable threshold via constructor or environment variable.
Default threshold is 0.5 (50%).

For ST-PIPELINE-TRANSPARENCY S2: Quality Filter Metrics
Tracks per-signal-type pass/drop counts and emits metrics events.
"""

from __future__ import annotations

import json
import logging
import math
import os
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from signal_generation.models import Signal

logger = logging.getLogger(__name__)

# Redis key patterns for quality filter metrics
_QUALITY_METRICS_KEY_PREFIX = "chiseai:metrics:quality_filter"


@dataclass
class QualityFilterResult:
    """Result of quality filtering.

    Attributes:
        is_qualified: Whether signal meets quality threshold
        threshold: The quality threshold used (0.0-1.0)
        quality_score: The signal's quality score (from metadata)
        reason: Explanation of filter decision
        metadata_preserved: Whether signal metadata was preserved intact
    """

    is_qualified: bool
    threshold: float
    quality_score: float | None
    reason: str
    metadata_preserved: bool = True


@dataclass
class QualityFilterMetrics:
    """Metrics for quality filter tracking.

    Attributes:
        total_processed: Total signals processed
        signals_filtered: Signals filtered (below threshold)
        signals_passed: Signals passed (above threshold)
        signals_missing_quality: Signals missing quality_score in metadata
        filter_rate: Ratio of filtered to total (0.0-1.0)
        last_updated: Timestamp of last metric update
        by_signal_type: Breakdown of counts by signal_type
    """

    total_processed: int = 0
    signals_filtered: int = 0
    signals_passed: int = 0
    signals_missing_quality: int = 0
    last_updated: datetime = field(default_factory=lambda: datetime.now(UTC))
    by_signal_type: dict[str, dict[str, int]] = field(default_factory=dict)

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

    @property
    def missing_quality_rate(self) -> float:
        """Calculate missing quality score rate.

        Returns:
            Missing rate as ratio (0.0-1.0), 0.0 if no signals processed
        """
        if self.total_processed == 0:
            return 0.0
        return self.signals_missing_quality / self.total_processed

    def _ensure_signal_type(self, signal_type: str) -> None:
        """Ensure signal_type entry exists in by_signal_type dict.

        Args:
            signal_type: The signal type to ensure exists
        """
        if signal_type not in self.by_signal_type:
            self.by_signal_type[signal_type] = {
                "total": 0,
                "passed": 0,
                "filtered": 0,
                "missing_quality": 0,
            }

    def increment_by_type(
        self,
        signal_type: str,
        passed: bool = False,
        filtered: bool = False,
        missing_quality: bool = False,
    ) -> None:
        """Increment counts for a specific signal type.

        Args:
            signal_type: The signal type identifier
            passed: If True, increment passed count
            filtered: If True, increment filtered count
            missing_quality: If True, increment missing_quality count
        """
        self._ensure_signal_type(signal_type)
        self.by_signal_type[signal_type]["total"] += 1
        if passed:
            self.by_signal_type[signal_type]["passed"] += 1
        if filtered:
            self.by_signal_type[signal_type]["filtered"] += 1
        if missing_quality:
            self.by_signal_type[signal_type]["missing_quality"] += 1

    def to_dict(self) -> dict:
        """Convert metrics to dictionary for export.

        Returns:
            Dictionary with metric values
        """
        return {
            "total_processed": self.total_processed,
            "signals_filtered": self.signals_filtered,
            "signals_passed": self.signals_passed,
            "signals_missing_quality": self.signals_missing_quality,
            "filter_rate": self.filter_rate,
            "pass_rate": self.pass_rate,
            "missing_quality_rate": self.missing_quality_rate,
            "by_signal_type": self.by_signal_type,
            "last_updated": self.last_updated.isoformat(),
        }


class QualityFilter:
    """Filter signals based on quality_score threshold.

    Default threshold is 50% (0.5) for signal quality.
    Signals below threshold are filtered before trading.
    Missing quality_score is treated as 0.0 (filtered).

    Threshold can be configured via:
    1. Constructor parameter
    2. SIGNAL_QUALITY_THRESHOLD environment variable
    3. Default value (0.5)

    This filter preserves signal metadata integrity - it only reads
    the quality_score, never modifies the signal's metadata dict.

    For ST-PIPELINE-TRANSPARENCY S2: Emits metrics events to Redis
    with signal_id, signal_type, filter_result, confidence_score, timestamp.
    """

    DEFAULT_THRESHOLD = 0.5
    MIN_THRESHOLD = 0.0
    MAX_THRESHOLD = 1.0

    # Redis connection settings
    DEFAULT_REDIS_HOST = "host.docker.internal"
    DEFAULT_REDIS_PORT = 6380
    DEFAULT_REDIS_DB = 0

    def __init__(
        self,
        threshold: float | None = None,
        redis_host: str | None = None,
        redis_port: int | None = None,
        redis_db: int | None = None,
    ):
        """Initialize quality filter.

        Args:
            threshold: Optional custom threshold (0.0-1.0).
                If not provided, uses environment variable or default.
            redis_host: Redis host for metrics emission (defaults to host.docker.internal)
            redis_port: Redis port (defaults to 6380)
            redis_db: Redis DB number (defaults to 0)
        """
        self.threshold = self._resolve_threshold(threshold)
        self.metrics = QualityFilterMetrics()

        # Redis settings for metrics emission
        self._redis_host = redis_host or self.DEFAULT_REDIS_HOST
        self._redis_port = redis_port or self.DEFAULT_REDIS_PORT
        self._redis_db = redis_db if redis_db is not None else self.DEFAULT_REDIS_DB
        self._redis_client: Any = None
        self._redis_lock = threading.Lock()

        logger.info(f"QualityFilter initialized with threshold: {self.threshold:.0%}")

    def _resolve_threshold(self, override: float | None) -> float:
        """Resolve threshold from override, env var, or default.

        Args:
            override: Optional threshold override

        Returns:
            Resolved threshold value
        """
        if override is not None:
            return self._clamp_threshold(override)

        env_threshold = os.getenv("SIGNAL_QUALITY_THRESHOLD")
        if env_threshold:
            try:
                return self._clamp_threshold(float(env_threshold))
            except ValueError:
                logger.warning(
                    f"Invalid SIGNAL_QUALITY_THRESHOLD: {env_threshold}, "
                    f"using default {self.DEFAULT_THRESHOLD}"
                )

        return self.DEFAULT_THRESHOLD

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

    def _get_redis_client(self) -> Any | None:
        """Get or create Redis client for metrics emission.

        Returns:
            Redis client or None if connection fails
        """
        if self._redis_client is not None:
            return self._redis_client

        with self._redis_lock:
            if self._redis_client is not None:
                return self._redis_client

            try:
                import redis

                client = redis.Redis(
                    host=self._redis_host,
                    port=self._redis_port,
                    db=self._redis_db,
                    decode_responses=True,
                    socket_timeout=5.0,
                    socket_connect_timeout=5.0,
                )
                client.ping()
                self._redis_client = client
                logger.debug("QualityFilter: Redis metrics client connected")
                return client
            except Exception as e:
                logger.warning(f"QualityFilter: Redis connection failed: {e}")
                return None

    def _extract_signal_type(self, signal: Signal) -> str:
        """Extract signal_type from signal metadata or related fields.

        Args:
            signal: The signal to extract from

        Returns:
            Signal type string (defaults to "unknown")
        """
        # First check metadata for signal_type
        metadata = getattr(signal, "metadata", None)
        if metadata and isinstance(metadata, dict):
            signal_type = metadata.get("signal_type")
            if signal_type:
                return str(signal_type)

        # Check for signal_type attribute directly
        signal_type = getattr(signal, "signal_type", None)
        if signal_type:
            return str(signal_type)

        # Fall back to a default based on direction or other indicators
        # Check for ICT-specific types in metadata
        if metadata and isinstance(metadata, dict):
            for itype in ["cvd", "fvg", "order_block", "bos", "choch"]:
                if metadata.get(itype) or metadata.get(f"is_{itype}"):
                    return itype

        return "unknown"

    def _emit_filter_event(
        self,
        signal: Signal,
        signal_type: str,
        filter_result: QualityFilterResult,
    ) -> None:
        """Emit a filter metrics event to Redis.

        Args:
            signal: The signal that was filtered
            signal_type: The type of signal
            filter_result: The filter result
        """
        client = self._get_redis_client()
        if client is None:
            return

        try:
            event = {
                "event_type": "quality_filter",
                "signal_id": signal.signal_id,
                "signal_type": signal_type,
                "token": signal.token,
                "direction": signal.direction_str,
                "filter_result": "passed" if filter_result.is_qualified else "dropped",
                "confidence_score": filter_result.quality_score,
                "threshold": self.threshold,
                "quality_score": filter_result.quality_score,
                "reason": filter_result.reason,
                "actionable": filter_result.is_qualified,
                "timestamp": datetime.now(UTC).isoformat(),
            }

            # Use Redis hash for atomic metric updates
            key = f"{_QUALITY_METRICS_KEY_PREFIX}:events"
            client.xadd(key, {"data": json.dumps(event)})

            # Also update running counters by signal_type
            counter_key = f"{_QUALITY_METRICS_KEY_PREFIX}:counters:{signal_type}"
            counter_key_all = f"{_QUALITY_METRICS_KEY_PREFIX}:counters:all"

            pipe = client.pipeline()
            pipe.hincrby(counter_key, "total", 1)
            if filter_result.is_qualified:
                pipe.hincrby(counter_key, "passed", 1)
            else:
                pipe.hincrby(counter_key, "dropped", 1)

            pipe.hincrby(counter_key_all, "total", 1)
            if filter_result.is_qualified:
                pipe.hincrby(counter_key_all, "passed", 1)
            else:
                pipe.hincrby(counter_key_all, "dropped", 1)

            pipe.execute()

            logger.debug(
                f"QualityFilter: Emitted event for signal {signal.signal_id} "
                f"signal_type={signal_type} result={'passed' if filter_result.is_qualified else 'dropped'}"
            )

        except Exception as e:
            logger.warning(f"QualityFilter: Failed to emit metrics event: {e}")

    def _extract_quality_score(self, signal: Signal) -> float | None:
        """Extract quality_score from signal metadata.

        Args:
            signal: The signal to extract from

        Returns:
            Quality score from metadata or None if not present
        """
        metadata = getattr(signal, "metadata", None)
        if not metadata or not isinstance(metadata, dict):
            return None

        quality_score = metadata.get("quality_score")
        if quality_score is None:
            return None

        # Validate it's a number
        try:
            score = float(quality_score)
            if math.isnan(score) or math.isinf(score):
                logger.warning(
                    f"Invalid quality_score {quality_score!r} in signal metadata, "
                    f"treating as missing"
                )
                return None
            return score
        except (TypeError, ValueError):
            logger.warning(
                f"Non-numeric quality_score {quality_score!r} in signal metadata, "
                f"treating as missing"
            )
            return None

    def filter(self, signal: Signal) -> QualityFilterResult:
        """Filter a signal based on quality_score threshold.

        Args:
            signal: The signal to filter

        Returns:
            QualityFilterResult with decision and explanation

        Note:
            For ST-PIPELINE-TRANSPARENCY S2: This method now tracks
            per-signal-type metrics and emits events to Redis.
        """
        self.metrics.total_processed += 1

        # Extract signal_type for metrics tracking (S2)
        signal_type = self._extract_signal_type(signal)

        # Extract quality_score from metadata
        quality_score = self._extract_quality_score(signal)

        # Handle missing quality_score
        if quality_score is None:
            self.metrics.signals_missing_quality += 1
            self.metrics.last_updated = datetime.now(UTC)
            self.metrics.increment_by_type(
                signal_type, passed=False, filtered=False, missing_quality=True
            )
            result = QualityFilterResult(
                is_qualified=False,
                threshold=self.threshold,
                quality_score=None,
                reason="Signal missing quality_score in metadata - treated as unqualified",
                metadata_preserved=True,
            )
            self._emit_filter_event(signal, signal_type, result)
            return result

        # Apply threshold check
        if quality_score >= self.threshold:
            self.metrics.signals_passed += 1
            self.metrics.last_updated = datetime.now(UTC)
            self.metrics.increment_by_type(
                signal_type, passed=True, filtered=False, missing_quality=False
            )
            result = QualityFilterResult(
                is_qualified=True,
                threshold=self.threshold,
                quality_score=quality_score,
                reason=(
                    f"Signal quality_score {quality_score:.1%} meets threshold "
                    f"{self.threshold:.0%}"
                ),
                metadata_preserved=True,
            )
            self._emit_filter_event(signal, signal_type, result)
            return result
        else:
            self.metrics.signals_filtered += 1
            self.metrics.last_updated = datetime.now(UTC)
            self.metrics.increment_by_type(
                signal_type, passed=False, filtered=True, missing_quality=False
            )
            result = QualityFilterResult(
                is_qualified=False,
                threshold=self.threshold,
                quality_score=quality_score,
                reason=(
                    f"Signal quality_score {quality_score:.1%} below threshold "
                    f"{self.threshold:.0%}"
                ),
                metadata_preserved=True,
            )
            self._emit_filter_event(signal, signal_type, result)
            return result

    def should_trade(self, signal: Signal) -> bool:
        """Quick check if signal should be traded based on quality.

        Args:
            signal: The signal to check

        Returns:
            True if signal meets quality threshold
        """
        quality_score = self._extract_quality_score(signal)
        if quality_score is None:
            return False
        # Explicit inf check for consistency with filter() behavior
        if (
            not isinstance(quality_score, float)
            or math.isnan(quality_score)
            or math.isinf(quality_score)
        ):
            return False
        return bool(quality_score >= self.threshold)

    def log_unqualified(self, signal: Signal, quality_score: float | None) -> None:
        """Log an unqualified signal for audit purposes.

        Args:
            signal: The unqualified signal to log
            quality_score: The quality score (or None if missing)
        """
        score_str = f"{quality_score:.1%}" if quality_score is not None else "missing"
        logger.info(
            f"Unqualified signal: {signal.token} [{signal.direction_str}] "
            f"quality_score={score_str} (threshold={self.threshold:.0%})"
        )

    def get_threshold_percent(self) -> float:
        """Get threshold as percentage (0-100)."""
        return self.threshold * 100

    def get_metrics(self) -> QualityFilterMetrics:
        """Get current filter metrics.

        Returns:
            QualityFilterMetrics with current counts and rates
        """
        return self.metrics

    def get_metrics_dict(self) -> dict:
        """Get metrics as dictionary for dashboards.

        Returns:
            Dictionary with metric values
        """
        return self.metrics.to_dict()

    def reset_metrics(self) -> None:
        """Reset all metrics to initial state."""
        self.metrics = QualityFilterMetrics()
        logger.info("Quality filter metrics reset")
