"""Tests for data freshness check module."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from data_ingestion.timeframe_config import Timeframe
from signal_generation.data_freshness_check import (
    DataFreshnessChecker,
    FreshnessResult,
)


class TestFreshnessResult:
    """Tests for FreshnessResult dataclass."""

    def test_freshness_result_creation(self):
        """Test creating a FreshnessResult."""
        result = FreshnessResult(
            is_fresh=True,
            data_age_seconds=30.0,
            max_allowed_age_seconds=120.0,
            timeframe="1h",
            errors=[],
            warnings=[],
        )

        assert result.is_fresh is True
        assert result.is_stale is False
        assert result.data_age_seconds == 30.0
        assert result.max_allowed_age_seconds == 120.0

    def test_freshness_result_stale(self):
        """Test stale result properties."""
        result = FreshnessResult(
            is_fresh=False,
            data_age_seconds=300.0,
            max_allowed_age_seconds=120.0,
            timeframe="1h",
            errors=["Data is stale"],
            warnings=[],
        )

        assert result.is_fresh is False
        assert result.is_stale is True

    def test_freshness_result_to_dict(self):
        """Test conversion to dictionary."""
        result = FreshnessResult(
            is_fresh=True,
            data_age_seconds=30.0,
            max_allowed_age_seconds=120.0,
            timeframe="1h",
            errors=[],
            warnings=["Minor delay"],
        )

        d = result.to_dict()
        assert d["is_fresh"] is True
        assert d["is_stale"] is False
        assert d["data_age_seconds"] == 30.0
        assert d["warnings"] == ["Minor delay"]


class TestDataFreshnessChecker:
    """Tests for DataFreshnessChecker."""

    def test_initialization(self):
        """Test checker initialization."""
        checker = DataFreshnessChecker(
            freshness_multiplier=2.0, enable_health_alerts=True
        )

        assert checker.freshness_multiplier == 2.0
        assert checker.enable_health_alerts is True

    def test_get_interval_seconds_known_timeframe(self):
        """Test getting interval for known timeframes."""
        checker = DataFreshnessChecker()

        assert checker._get_interval_seconds(Timeframe.MINUTE_1) == 60.0
        assert checker._get_interval_seconds(Timeframe.MINUTE_5) == 300.0
        assert checker._get_interval_seconds(Timeframe.HOUR_1) == 3600.0
        assert checker._get_interval_seconds(Timeframe.DAY_1) == 86400.0

    def test_check_freshness_empty_data(self):
        """Test freshness check with empty data."""
        checker = DataFreshnessChecker()

        result = checker.check_freshness([], Timeframe.HOUR_1)

        assert result.is_fresh is False
        assert result.is_stale is True
        assert "No data provided" in result.errors[0]

    def test_check_freshness_fresh_data(self):
        """Test freshness check with fresh data."""
        # Use mock validator to avoid MagicMock comparison issues
        mock_validator = MagicMock()
        mock_validator.validate.return_value = MagicMock(
            is_valid=True, is_fresh=True, errors=[], warnings=[]
        )

        checker = DataFreshnessChecker(data_validator=mock_validator)

        # Create fresh data (30 seconds old)
        now = datetime.now(UTC)
        mock_data = [
            MagicMock(
                timestamp=int(now.timestamp()),
                datetime_utc=now - timedelta(seconds=30),
            )
        ]

        result = checker.check_freshness(
            mock_data, Timeframe.HOUR_1, reference_time=now
        )

        assert result.is_fresh is True
        assert result.is_stale is False
        assert result.data_age_seconds == 30.0

    def test_check_freshness_stale_data(self):
        """Test freshness check with stale data."""
        # Use mock validator to avoid MagicMock comparison issues
        mock_validator = MagicMock()
        mock_validator.validate.return_value = MagicMock(
            is_valid=True, is_fresh=False, errors=[], warnings=[]
        )

        checker = DataFreshnessChecker(
            data_validator=mock_validator, enable_health_alerts=False
        )

        # Create stale data (3 hours old, threshold is 2 hours for 1h timeframe)
        now = datetime.now(UTC)
        mock_data = [
            MagicMock(
                timestamp=int((now - timedelta(hours=3)).timestamp()),
                datetime_utc=now - timedelta(hours=3),
            )
        ]

        result = checker.check_freshness(
            mock_data, Timeframe.HOUR_1, reference_time=now
        )

        assert result.is_fresh is False
        assert result.is_stale is True
        assert result.data_age_seconds == pytest.approx(10800.0, abs=1.0)

    def test_check_freshness_2x_threshold(self):
        """Test the 2x timeframe interval threshold."""
        # Use mock validator to avoid MagicMock comparison issues
        mock_validator = MagicMock()
        mock_validator.validate.return_value = MagicMock(
            is_valid=True, is_fresh=True, errors=[], warnings=[]
        )

        checker = DataFreshnessChecker(
            data_validator=mock_validator, freshness_multiplier=2.0
        )

        now = datetime.now(UTC)

        # For 1h timeframe: interval=3600s, threshold=7200s
        # Data at 7000s should be fresh
        fresh_data = [
            MagicMock(
                timestamp=int((now - timedelta(seconds=7000)).timestamp()),
                datetime_utc=now - timedelta(seconds=7000),
            )
        ]

        result = checker.check_freshness(
            fresh_data, Timeframe.HOUR_1, reference_time=now
        )
        assert result.is_fresh is True

        # Data at 7500s should be stale
        stale_data = [
            MagicMock(
                timestamp=int((now - timedelta(seconds=7500)).timestamp()),
                datetime_utc=now - timedelta(seconds=7500),
            )
        ]

        result = checker.check_freshness(
            stale_data, Timeframe.HOUR_1, reference_time=now
        )
        assert result.is_fresh is False

    def test_check_freshness_batch(self):
        """Test batch freshness check."""
        # Use mock validator to avoid MagicMock comparison issues
        mock_validator = MagicMock()
        mock_validator.validate.return_value = MagicMock(
            is_valid=True, is_fresh=True, errors=[], warnings=[]
        )

        checker = DataFreshnessChecker(data_validator=mock_validator)

        now = datetime.now(UTC)
        fresh_time = now - timedelta(seconds=30)

        data_map = {
            Timeframe.HOUR_1: [
                MagicMock(
                    timestamp=int(fresh_time.timestamp()), datetime_utc=fresh_time
                )
            ],
            Timeframe.HOUR_4: [
                MagicMock(
                    timestamp=int(fresh_time.timestamp()), datetime_utc=fresh_time
                )
            ],
        }

        results = checker.check_freshness_batch(data_map, reference_time=now)

        assert len(results) == 2
        assert Timeframe.HOUR_1 in results
        assert Timeframe.HOUR_4 in results
        assert all(r.is_fresh for r in results.values())

    def test_is_healthy_all_fresh(self):
        """Test health check with all fresh data."""
        checker = DataFreshnessChecker()

        results = {
            Timeframe.HOUR_1: FreshnessResult(
                is_fresh=True,
                data_age_seconds=30.0,
                max_allowed_age_seconds=7200.0,
                timeframe="1h",
                errors=[],
                warnings=[],
            ),
            Timeframe.HOUR_4: FreshnessResult(
                is_fresh=True,
                data_age_seconds=60.0,
                max_allowed_age_seconds=28800.0,
                timeframe="4h",
                errors=[],
                warnings=[],
            ),
        }

        assert checker.is_healthy(results) is True

    def test_is_healthy_some_stale(self):
        """Test health check with some stale data."""
        checker = DataFreshnessChecker()

        results = {
            Timeframe.HOUR_1: FreshnessResult(
                is_fresh=True,
                data_age_seconds=30.0,
                max_allowed_age_seconds=7200.0,
                timeframe="1h",
                errors=[],
                warnings=[],
            ),
            Timeframe.HOUR_4: FreshnessResult(
                is_fresh=False,
                data_age_seconds=50000.0,
                max_allowed_age_seconds=28800.0,
                timeframe="4h",
                errors=["Stale"],
                warnings=[],
            ),
        }

        assert checker.is_healthy(results) is False

    def test_health_alert_cooldown(self):
        """Test health alert cooldown prevents spam."""
        # Use mock validator to avoid MagicMock comparison issues
        mock_validator = MagicMock()
        mock_validator.validate.return_value = MagicMock(
            is_valid=True, is_fresh=True, errors=[], warnings=[]
        )

        checker = DataFreshnessChecker(
            data_validator=mock_validator, enable_health_alerts=True
        )
        checker._alert_cooldown_seconds = 1  # 1 second for testing

        now = datetime.now(UTC)
        stale_data = [
            MagicMock(
                timestamp=int((now - timedelta(hours=3)).timestamp()),
                datetime_utc=now - timedelta(hours=3),
            )
        ]

        # First call should trigger alert
        checker._last_alert_time = None
        checker.check_freshness(stale_data, Timeframe.HOUR_1, reference_time=now)
        assert checker._last_alert_time is not None

        # Second call immediately should not trigger (cooldown)
        last_alert = checker._last_alert_time
        checker.check_freshness(stale_data, Timeframe.HOUR_1, reference_time=now)
        assert checker._last_alert_time == last_alert

    def test_integration_with_data_validator(self):
        """Test integration with DataValidator."""
        mock_validator = MagicMock()
        mock_validator.validate.return_value = MagicMock(
            is_valid=True, is_fresh=True, errors=[], warnings=["Test warning"]
        )

        checker = DataFreshnessChecker(data_validator=mock_validator)

        now = datetime.now(UTC)
        mock_data = [MagicMock(timestamp=int(now.timestamp()), datetime_utc=now)]

        result = checker.check_freshness(
            mock_data, Timeframe.HOUR_1, reference_time=now
        )

        # Should include warning from validator
        assert "Test warning" in result.warnings
        mock_validator.validate.assert_called_once()


class TestDataFreshnessCheckerEdgeCases:
    """Edge case tests for DataFreshnessChecker."""

    def test_data_age_calculation_failure(self):
        """Test handling of data age calculation failure."""
        checker = DataFreshnessChecker()

        # Data with invalid timestamp
        mock_data = [MagicMock(timestamp=0, datetime_utc=None)]

        result = checker.check_freshness(mock_data, Timeframe.HOUR_1)

        assert result.is_fresh is False
        assert result.data_age_seconds is None

    def test_negative_data_age(self):
        """Test handling of negative data age (future data)."""
        # Use mock validator to avoid MagicMock comparison issues
        mock_validator = MagicMock()
        mock_validator.validate.return_value = MagicMock(
            is_valid=True, is_fresh=True, errors=[], warnings=[]
        )

        checker = DataFreshnessChecker(data_validator=mock_validator)

        now = datetime.now(UTC)
        future_time = now + timedelta(hours=1)

        mock_data = [
            MagicMock(timestamp=int(future_time.timestamp()), datetime_utc=future_time)
        ]

        result = checker.check_freshness(
            mock_data, Timeframe.HOUR_1, reference_time=now
        )

        # Negative age should be clamped to 0
        assert result.data_age_seconds == 0.0
        assert result.is_fresh is True
