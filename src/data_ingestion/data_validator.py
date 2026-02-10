"""Data validator for OHLCV freshness and quality checks.

Validates that fetched data meets freshness requirements and detects
quality issues like stale timestamps or invalid price data.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from data_ingestion.ohlcv_fetcher import OHLCVData
from data_ingestion.timeframe_config import Timeframe, get_freshness_threshold

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of data validation check.

    Attributes:
        is_valid: Whether data passed all validation checks
        is_fresh: Whether data is within freshness threshold
        errors: List of validation error messages
        warnings: List of validation warning messages
        data_age_seconds: Age of the most recent data point
    """

    is_valid: bool
    is_fresh: bool
    errors: list[str]
    warnings: list[str]
    data_age_seconds: float | None


class DataValidator:
    """Validator for OHLCV data freshness and quality."""

    def __init__(
        self,
        freshness_check_enabled: bool = True,
        max_price_change_percent: float = 50.0,
    ):
        """Initialize data validator.

        Args:
            freshness_check_enabled: Whether to enforce freshness checks
            max_price_change_percent: Maximum allowed price change between
                consecutive candles (as percentage, for anomaly detection)
        """
        self.freshness_check_enabled = freshness_check_enabled
        self.max_price_change_percent = max_price_change_percent

    def validate(
        self,
        data: list[OHLCVData],
        timeframe: Timeframe,
        reference_time: datetime | None = None,
    ) -> ValidationResult:
        """Validate OHLCV data for freshness and quality.

        Args:
            data: List of OHLCV data points
            timeframe: Timeframe the data represents
            reference_time: Time to check freshness against (defaults to now)

        Returns:
            ValidationResult with validation status and details
        """
        errors: list[str] = []
        warnings: list[str] = []

        # Check for empty data
        if not data:
            errors.append("No data provided")
            return ValidationResult(
                is_valid=False,
                is_fresh=False,
                errors=errors,
                warnings=warnings,
                data_age_seconds=None,
            )

        # Check for minimum data points
        if len(data) < 2:
            warnings.append("Less than 2 data points, cannot validate continuity")

        # Validate individual candles
        for i, candle in enumerate(data):
            candle_errors = self._validate_candle(candle)
            if candle_errors:
                errors.extend([f"Candle {i}: {e}" for e in candle_errors])

        # Check freshness of most recent data
        data_age = self._calculate_data_age(data, reference_time)
        freshness_threshold = get_freshness_threshold(timeframe)
        is_fresh = data_age is not None and data_age <= freshness_threshold

        if not is_fresh and self.freshness_check_enabled:
            if data_age is not None:
                errors.append(
                    f"Data is stale: age={data_age:.1f}s, "
                    f"threshold={freshness_threshold:.1f}s"
                )
            else:
                errors.append("Could not determine data age")
        elif not is_fresh:
            warnings.append(
                f"Data is stale: age={data_age:.1f}s, "
                f"threshold={freshness_threshold:.1f}s"
            )

        # Check for price anomalies
        price_warnings = self._check_price_anomalies(data)
        warnings.extend(price_warnings)

        # Check for market gaps (zero volume periods)
        gap_warnings = self._check_volume_gaps(data, timeframe)
        warnings.extend(gap_warnings)

        is_valid = len(errors) == 0

        return ValidationResult(
            is_valid=is_valid,
            is_fresh=is_fresh,
            errors=errors,
            warnings=warnings,
            data_age_seconds=data_age,
        )

    def _validate_candle(self, candle: OHLCVData) -> list[str]:
        """Validate a single OHLCV candle.

        Args:
            candle: OHLCV data point to validate

        Returns:
            List of validation error messages
        """
        errors: list[str] = []

        # Check for valid prices
        if candle.open_price <= 0:
            errors.append(f"Invalid open price: {candle.open_price}")
        if candle.high_price <= 0:
            errors.append(f"Invalid high price: {candle.high_price}")
        if candle.low_price <= 0:
            errors.append(f"Invalid low price: {candle.low_price}")
        if candle.close_price <= 0:
            errors.append(f"Invalid close price: {candle.close_price}")

        # Check OHLC relationships
        if candle.high_price < candle.low_price:
            errors.append(f"High ({candle.high_price}) < Low ({candle.low_price})")

        if candle.high_price < max(
            candle.open_price, candle.close_price
        ) or candle.low_price > min(candle.open_price, candle.close_price):
            errors.append("High/Low do not contain Open/Close range")

        # Check for valid volume
        if candle.volume < 0:
            errors.append(f"Invalid volume: {candle.volume}")

        # Check for valid timestamp
        if candle.timestamp <= 0:
            errors.append(f"Invalid timestamp: {candle.timestamp}")

        return errors

    def _calculate_data_age(
        self,
        data: list[OHLCVData],
        reference_time: datetime | None = None,
    ) -> float | None:
        """Calculate age of the most recent data point.

        Args:
            data: List of OHLCV data points
            reference_time: Time to check against (defaults to UTC now)

        Returns:
            Age in seconds, or None if cannot be determined
        """
        if not data:
            return None

        if reference_time is None:
            reference_time = datetime.now(UTC)

        try:
            most_recent = max(data, key=lambda x: x.timestamp)
            data_time = most_recent.datetime_utc
            age = (reference_time - data_time).total_seconds()
            return max(0.0, age)  # Ensure non-negative
        except Exception as e:
            logger.warning(f"Failed to calculate data age: {e}")
            return None

    def _check_price_anomalies(self, data: list[OHLCVData]) -> list[str]:
        """Check for unusual price movements between consecutive candles.

        Args:
            data: List of OHLCV data points

        Returns:
            List of warning messages
        """
        warnings: list[str] = []

        if len(data) < 2:
            return warnings

        for i in range(1, len(data)):
            prev_close = data[i - 1].close_price
            curr_close = data[i].close_price

            if prev_close <= 0:
                continue

            change_percent = abs(curr_close - prev_close) / prev_close * 100

            if change_percent > self.max_price_change_percent:
                warnings.append(
                    f"Large price change at index {i}: "
                    f"{change_percent:.1f}% "
                    f"(threshold: {self.max_price_change_percent}%)"
                )

        return warnings

    def _check_volume_gaps(
        self, data: list[OHLCVData], timeframe: Timeframe
    ) -> list[str]:
        """Check for periods of zero or very low volume.

        Args:
            data: List of OHLCV data points
            timeframe: Timeframe the data represents

        Returns:
            List of warning messages
        """
        warnings: list[str] = []

        zero_volume_count = sum(1 for d in data if d.volume == 0)

        if zero_volume_count > 0:
            percentage = (zero_volume_count / len(data)) * 100

            if percentage > 50:
                warnings.append(
                    f"High zero-volume ratio: {zero_volume_count}/{len(data)} "
                    f"({percentage:.1f}%) - possible market closure or low liquidity"
                )
            elif percentage > 10:
                warnings.append(
                    f"Elevated zero-volume ratio: {zero_volume_count}/{len(data)} "
                    f"({percentage:.1f}%)"
                )

        return warnings

    def validate_batch(
        self,
        data_map: dict[Timeframe, list[OHLCVData]],
        reference_time: datetime | None = None,
    ) -> dict[Timeframe, ValidationResult]:
        """Validate data for multiple timeframes.

        Args:
            data_map: Dictionary mapping timeframe to data list
            reference_time: Time to check freshness against

        Returns:
            Dictionary mapping timeframe to ValidationResult
        """
        results: dict[Timeframe, ValidationResult] = {}

        for timeframe, data in data_map.items():
            results[timeframe] = self.validate(data, timeframe, reference_time)

        return results
