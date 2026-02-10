"""Data freshness checker for signal generation.

Validates data freshness before generating signals using the 2x
timeframe interval threshold. Raises health alerts if data is stale.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from data_ingestion.data_validator import DataValidator
    from data_ingestion.ohlcv_fetcher import OHLCVData
    from data_ingestion.timeframe_config import Timeframe

logger = logging.getLogger(__name__)


@dataclass
class FreshnessResult:
    """Result of data freshness check.

    Attributes:
        is_fresh: Whether data is fresh enough for signal generation
        data_age_seconds: Age of the most recent data point
        max_allowed_age_seconds: Maximum allowed age (2x interval)
        timeframe: Timeframe that was checked
        errors: List of freshness errors
        warnings: List of freshness warnings
    """

    is_fresh: bool
    data_age_seconds: float | None
    max_allowed_age_seconds: float
    timeframe: str
    errors: list[str]
    warnings: list[str]

    @property
    def is_stale(self) -> bool:
        """Check if data is stale (not fresh)."""
        return not self.is_fresh

    def to_dict(self) -> dict:
        """Convert to dictionary for logging/serialization."""
        return {
            "is_fresh": self.is_fresh,
            "is_stale": self.is_stale,
            "data_age_seconds": self.data_age_seconds,
            "max_allowed_age_seconds": self.max_allowed_age_seconds,
            "timeframe": self.timeframe,
            "errors": self.errors,
            "warnings": self.warnings,
        }


class DataFreshnessChecker:
    """Checker for data freshness before signal generation.

    Uses the 2x timeframe interval threshold from the validation registry:
    - Data is considered stale if older than 2x the timeframe interval
    - If data freshness checks fail, signals are not emitted as actionable
    - Health alerts are raised for stale data

    Integrates with DataValidator from ST-NS-001 for consistency.
    """

    DEFAULT_FRESHNESS_MULTIPLIER = 2.0

    def __init__(
        self,
        data_validator: DataValidator | None = None,
        freshness_multiplier: float = DEFAULT_FRESHNESS_MULTIPLIER,
        enable_health_alerts: bool = True,
    ):
        """Initialize freshness checker.

        Args:
            data_validator: Optional DataValidator instance for reuse
            freshness_multiplier: Multiplier for freshness threshold (default 2.0)
            enable_health_alerts: Whether to raise health alerts for stale data
        """
        self.data_validator = data_validator
        self.freshness_multiplier = freshness_multiplier
        self.enable_health_alerts = enable_health_alerts

        # Track health alert state to avoid spam
        self._last_alert_time: datetime | None = None
        self._alert_cooldown_seconds = 300  # 5 minutes between alerts

    def _get_validator(self) -> DataValidator:
        """Get or create DataValidator instance."""
        if self.data_validator is None:
            from data_ingestion.data_validator import DataValidator

            self.data_validator = DataValidator()
        return self.data_validator

    def _get_interval_seconds(self, timeframe: Timeframe) -> float:
        """Get interval seconds for a timeframe.

        Args:
            timeframe: Timeframe to get interval for

        Returns:
            Interval in seconds
        """
        from data_ingestion.timeframe_config import TIMEFRAME_CONFIG

        config = TIMEFRAME_CONFIG.get(timeframe)
        if config:
            return float(config.interval_seconds)

        # Fallback for unknown timeframes
        logger.warning(f"Unknown timeframe: {timeframe}, using default 1h interval")
        return 3600.0

    def check_freshness(
        self,
        data: list[OHLCVData],
        timeframe: Timeframe,
        reference_time: datetime | None = None,
    ) -> FreshnessResult:
        """Check data freshness for signal generation.

        Args:
            data: List of OHLCV data points
            timeframe: Timeframe the data represents
            reference_time: Time to check against (defaults to UTC now)

        Returns:
            FreshnessResult with freshness status and details
        """
        if reference_time is None:
            reference_time = datetime.now(UTC)

        # Calculate max allowed age (2x interval)
        interval_seconds = self._get_interval_seconds(timeframe)
        max_allowed_age = interval_seconds * self.freshness_multiplier

        errors: list[str] = []
        warnings: list[str] = []

        # Check for empty data
        if not data:
            errors.append("No data provided for freshness check")
            return FreshnessResult(
                is_fresh=False,
                data_age_seconds=None,
                max_allowed_age_seconds=max_allowed_age,
                timeframe=timeframe.value,
                errors=errors,
                warnings=warnings,
            )

        # Calculate data age
        try:
            most_recent = max(data, key=lambda x: x.timestamp)
            data_time = most_recent.datetime_utc
            data_age = (reference_time - data_time).total_seconds()
            data_age = max(0.0, data_age)  # Ensure non-negative
        except Exception as e:
            logger.warning(f"Failed to calculate data age: {e}")
            errors.append(f"Failed to calculate data age: {e}")
            return FreshnessResult(
                is_fresh=False,
                data_age_seconds=None,
                max_allowed_age_seconds=max_allowed_age,
                timeframe=timeframe.value,
                errors=errors,
                warnings=warnings,
            )

        # Check freshness
        is_fresh = data_age <= max_allowed_age

        if not is_fresh:
            error_msg = (
                f"Data is stale: age={data_age:.1f}s, "
                f"threshold={max_allowed_age:.1f}s (2x {timeframe.value} interval)"
            )
            errors.append(error_msg)

            # Raise health alert if enabled
            if self.enable_health_alerts:
                self._raise_health_alert(timeframe, data_age, max_allowed_age)

        # Also run full validation for additional checks
        validator = self._get_validator()
        validation_result = validator.validate(data, timeframe, reference_time)

        # Add validation warnings
        warnings.extend(validation_result.warnings)

        # If validation failed, mark as not fresh
        if not validation_result.is_valid:
            errors.extend(validation_result.errors)
            is_fresh = False

        return FreshnessResult(
            is_fresh=is_fresh,
            data_age_seconds=data_age,
            max_allowed_age_seconds=max_allowed_age,
            timeframe=timeframe.value,
            errors=errors,
            warnings=warnings,
        )

    def check_freshness_batch(
        self,
        data_map: dict[Timeframe, list[OHLCVData]],
        reference_time: datetime | None = None,
    ) -> dict[Timeframe, FreshnessResult]:
        """Check freshness for multiple timeframes.

        Args:
            data_map: Dictionary mapping timeframe to data list
            reference_time: Time to check against

        Returns:
            Dictionary mapping timeframe to FreshnessResult
        """
        results: dict[Timeframe, FreshnessResult] = {}

        for timeframe, data in data_map.items():
            results[timeframe] = self.check_freshness(data, timeframe, reference_time)

        return results

    def _raise_health_alert(
        self, timeframe: Timeframe, data_age: float, threshold: float
    ) -> None:
        """Raise a health alert for stale data.

        Args:
            timeframe: Timeframe with stale data
            data_age: Actual data age in seconds
            threshold: Maximum allowed age in seconds
        """
        now = datetime.now(UTC)

        # Check cooldown to avoid alert spam
        if self._last_alert_time is not None:
            elapsed = (now - self._last_alert_time).total_seconds()
            if elapsed < self._alert_cooldown_seconds:
                return  # Skip alert due to cooldown

        self._last_alert_time = now

        logger.error(
            f"HEALTH ALERT: Stale data detected for {timeframe.value}. "
            f"Age: {data_age:.1f}s, Threshold: {threshold:.1f}s"
        )

        # TODO: Integrate with actual health monitoring system
        # This could emit to:
        # - Discord webhook
        # - Metrics system (Prometheus/Grafana)
        # - Alert manager (PagerDuty, etc.)

    def is_healthy(self, results: dict[Timeframe, FreshnessResult]) -> bool:
        """Check if all timeframes have fresh data.

        Args:
            results: Freshness results for multiple timeframes

        Returns:
            True if all data is fresh
        """
        return all(result.is_fresh for result in results.values())
