"""Tests for data validator module."""

from datetime import UTC, datetime, timedelta

import pytest

from data_ingestion.data_validator import DataValidator, ValidationResult
from data_ingestion.ohlcv_fetcher import OHLCVData
from data_ingestion.timeframe_config import Timeframe


class TestValidationResult:
    """Test cases for ValidationResult dataclass."""

    def test_creation(self):
        """Test creating ValidationResult."""
        result = ValidationResult(
            is_valid=True,
            is_fresh=True,
            errors=[],
            warnings=[],
            data_age_seconds=30.0,
        )
        assert result.is_valid is True
        assert result.is_fresh is True
        assert result.errors == []
        assert result.warnings == []
        assert result.data_age_seconds == 30.0


class TestDataValidator:
    """Test cases for DataValidator class."""

    @pytest.fixture
    def validator(self):
        """Create a DataValidator instance."""
        return DataValidator()

    @pytest.fixture
    def valid_candles(self):
        """Create valid OHLCV candles."""
        now = int(datetime.now(UTC).timestamp() * 1000)
        return [
            OHLCVData(
                timestamp=now - 60000,
                open_price=100.0,
                high_price=110.0,
                low_price=95.0,
                close_price=105.0,
                volume=1000.0,
            ),
            OHLCVData(
                timestamp=now,
                open_price=105.0,
                high_price=115.0,
                low_price=100.0,
                close_price=110.0,
                volume=1500.0,
            ),
        ]

    def test_validate_empty_data(self, validator):
        """Test validation of empty data."""
        result = validator.validate([], Timeframe.MINUTE_1)

        assert result.is_valid is False
        assert result.is_fresh is False
        assert "No data provided" in result.errors

    def test_validate_valid_data(self, validator, valid_candles):
        """Test validation of valid data."""
        result = validator.validate(valid_candles, Timeframe.MINUTE_1)

        assert result.is_valid is True
        assert result.is_fresh is True
        assert len(result.errors) == 0

    def test_validate_stale_data(self, validator):
        """Test validation of stale data."""
        # Create data that's older than freshness threshold
        old_time = int((datetime.now(UTC) - timedelta(minutes=10)).timestamp() * 1000)
        stale_candles = [
            OHLCVData(
                timestamp=old_time,
                open_price=100.0,
                high_price=110.0,
                low_price=95.0,
                close_price=105.0,
                volume=1000.0,
            )
        ]

        result = validator.validate(stale_candles, Timeframe.MINUTE_1)

        assert result.is_valid is False
        assert result.is_fresh is False
        assert any("stale" in e.lower() for e in result.errors)

    def test_validate_freshness_disabled(self, validator):
        """Test that freshness check can be disabled."""
        validator.freshness_check_enabled = False

        old_time = int((datetime.now(UTC) - timedelta(minutes=10)).timestamp() * 1000)
        stale_candles = [
            OHLCVData(
                timestamp=old_time,
                open_price=100.0,
                high_price=110.0,
                low_price=95.0,
                close_price=105.0,
                volume=1000.0,
            )
        ]

        result = validator.validate(stale_candles, Timeframe.MINUTE_1)

        # Should be valid (no errors) but not fresh (warning)
        assert result.is_valid is True
        assert result.is_fresh is False
        assert any("stale" in w.lower() for w in result.warnings)

    def test_validate_invalid_prices(self, validator):
        """Test validation of data with invalid prices."""
        now = int(datetime.now(UTC).timestamp() * 1000)
        invalid_candles = [
            OHLCVData(
                timestamp=now,
                open_price=-100.0,  # Invalid: negative
                high_price=110.0,
                low_price=95.0,
                close_price=105.0,
                volume=1000.0,
            )
        ]

        result = validator.validate(invalid_candles, Timeframe.MINUTE_1)

        assert result.is_valid is False
        assert any("Invalid open price" in e for e in result.errors)

    def test_validate_high_low_relationship(self, validator):
        """Test validation of high/low price relationship."""
        now = int(datetime.now(UTC).timestamp() * 1000)
        invalid_candles = [
            OHLCVData(
                timestamp=now,
                open_price=100.0,
                high_price=90.0,  # Invalid: high < low
                low_price=95.0,
                close_price=105.0,
                volume=1000.0,
            )
        ]

        result = validator.validate(invalid_candles, Timeframe.MINUTE_1)

        assert result.is_valid is False
        assert any("High" in e and "Low" in e for e in result.errors)

    def test_validate_negative_volume(self, validator):
        """Test validation of negative volume."""
        now = int(datetime.now(UTC).timestamp() * 1000)
        invalid_candles = [
            OHLCVData(
                timestamp=now,
                open_price=100.0,
                high_price=110.0,
                low_price=95.0,
                close_price=105.0,
                volume=-1000.0,  # Invalid: negative
            )
        ]

        result = validator.validate(invalid_candles, Timeframe.MINUTE_1)

        assert result.is_valid is False
        assert any("Invalid volume" in e for e in result.errors)

    def test_validate_price_anomaly(self, validator):
        """Test detection of large price changes."""
        now = int(datetime.now(UTC).timestamp() * 1000)
        candles_with_anomaly = [
            OHLCVData(
                timestamp=now - 60000,
                open_price=100.0,
                high_price=110.0,
                low_price=95.0,
                close_price=100.0,
                volume=1000.0,
            ),
            OHLCVData(
                timestamp=now,
                open_price=100.0,
                high_price=200.0,  # 100% change
                low_price=95.0,
                close_price=200.0,  # 100% change from previous close
                volume=1000.0,
            ),
        ]

        result = validator.validate(candles_with_anomaly, Timeframe.MINUTE_1)

        assert any("Large price change" in w for w in result.warnings)

    def test_validate_zero_volume_warning(self, validator):
        """Test warning for zero volume periods."""
        now = int(datetime.now(UTC).timestamp() * 1000)
        zero_volume_candles = [
            OHLCVData(
                timestamp=now - 60000 * i,
                open_price=100.0,
                high_price=110.0,
                low_price=95.0,
                close_price=105.0,
                volume=0.0,
            )
            for i in range(10)
        ]

        result = validator.validate(zero_volume_candles, Timeframe.MINUTE_1)

        assert any("zero-volume" in w.lower() for w in result.warnings)

    def test_validate_single_candle_warning(self, validator):
        """Test warning for single candle data."""
        now = int(datetime.now(UTC).timestamp() * 1000)
        single_candle = [
            OHLCVData(
                timestamp=now,
                open_price=100.0,
                high_price=110.0,
                low_price=95.0,
                close_price=105.0,
                volume=1000.0,
            )
        ]

        result = validator.validate(single_candle, Timeframe.MINUTE_1)

        assert result.is_valid is True
        assert any("Less than 2 data points" in w for w in result.warnings)

    def test_validate_batch(self, validator, valid_candles):
        """Test batch validation across multiple timeframes."""
        data_map = {
            Timeframe.MINUTE_1: valid_candles,
            Timeframe.MINUTE_5: valid_candles,
        }

        results = validator.validate_batch(data_map)

        assert len(results) == 2
        assert Timeframe.MINUTE_1 in results
        assert Timeframe.MINUTE_5 in results
        assert all(r.is_valid for r in results.values())

    def test_calculate_data_age(self, validator, valid_candles):
        """Test data age calculation."""
        now = datetime.now(UTC)
        result = validator.validate(valid_candles, Timeframe.MINUTE_1, now)

        assert result.data_age_seconds is not None
        assert result.data_age_seconds >= 0

    def test_calculate_data_age_empty(self, validator):
        """Test data age calculation with empty data."""
        result = validator._calculate_data_age([])
        assert result is None

    def test_validate_ohlc_containment(self, validator):
        """Test that high/low contain open/close range."""
        now = int(datetime.now(UTC).timestamp() * 1000)
        invalid_candles = [
            OHLCVData(
                timestamp=now,
                open_price=100.0,
                high_price=105.0,  # Less than open/close
                low_price=95.0,
                close_price=110.0,  # Greater than high
                volume=1000.0,
            )
        ]

        result = validator.validate(invalid_candles, Timeframe.MINUTE_1)

        assert result.is_valid is False
        assert any("High/Low" in e for e in result.errors)
