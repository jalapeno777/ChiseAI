"""Quality filter for signal threshold enforcement.

Implements the quality_score threshold filter for signals.
Signals with quality_score below threshold are filtered before trading.

Supports configurable threshold via constructor or environment variable.
Default threshold is 0.5 (50%).
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from signal_generation.models import Signal

logger = logging.getLogger(__name__)


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
    """

    total_processed: int = 0
    signals_filtered: int = 0
    signals_passed: int = 0
    signals_missing_quality: int = 0
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

    @property
    def missing_quality_rate(self) -> float:
        """Calculate missing quality score rate.

        Returns:
            Missing rate as ratio (0.0-1.0), 0.0 if no signals processed
        """
        if self.total_processed == 0:
            return 0.0
        return self.signals_missing_quality / self.total_processed

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
    """

    DEFAULT_THRESHOLD = 0.5
    MIN_THRESHOLD = 0.0
    MAX_THRESHOLD = 1.0

    def __init__(self, threshold: float | None = None):
        """Initialize quality filter.

        Args:
            threshold: Optional custom threshold (0.0-1.0).
                If not provided, uses environment variable or default.
        """
        self.threshold = self._resolve_threshold(threshold)
        self.metrics = QualityFilterMetrics()
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
        """
        self.metrics.total_processed += 1

        # Extract quality_score from metadata
        quality_score = self._extract_quality_score(signal)

        # Handle missing quality_score
        if quality_score is None:
            self.metrics.signals_missing_quality += 1
            self.metrics.last_updated = datetime.now(UTC)
            return QualityFilterResult(
                is_qualified=False,
                threshold=self.threshold,
                quality_score=None,
                reason="Signal missing quality_score in metadata - treated as unqualified",
                metadata_preserved=True,
            )

        # Guard against NaN/inf in quality_score (defense in depth)
        if not isinstance(quality_score, float) or math.isnan(quality_score):
            self.metrics.signals_filtered += 1
            self.metrics.last_updated = datetime.now(UTC)
            return QualityFilterResult(
                is_qualified=False,
                threshold=self.threshold,
                quality_score=None,
                reason="Invalid quality_score detected - marking as unqualified",
                metadata_preserved=True,
            )

        # Apply threshold check
        if quality_score >= self.threshold:
            self.metrics.signals_passed += 1
            self.metrics.last_updated = datetime.now(UTC)
            return QualityFilterResult(
                is_qualified=True,
                threshold=self.threshold,
                quality_score=quality_score,
                reason=(
                    f"Signal quality_score {quality_score:.1%} meets threshold "
                    f"{self.threshold:.0%}"
                ),
                metadata_preserved=True,
            )
        else:
            self.metrics.signals_filtered += 1
            self.metrics.last_updated = datetime.now(UTC)
            return QualityFilterResult(
                is_qualified=False,
                threshold=self.threshold,
                quality_score=quality_score,
                reason=(
                    f"Signal quality_score {quality_score:.1%} below threshold "
                    f"{self.threshold:.0%}"
                ),
                metadata_preserved=True,
            )

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
        if not isinstance(quality_score, float) or math.isnan(quality_score):
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
