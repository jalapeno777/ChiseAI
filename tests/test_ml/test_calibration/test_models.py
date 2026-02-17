"""Unit tests for calibration data models."""

from __future__ import annotations

import pytest
from datetime import UTC, datetime

import sys

sys.path.insert(0, "src")

from ml.calibration.models import (
    CalibrationConfig,
    CalibrationRecord,
    CollectionWindow,
    SignalType,
)


class TestSignalType:
    """Tests for SignalType enum."""

    def test_signal_type_values(self):
        """Test SignalType enum values."""
        assert SignalType.LONG.value == "LONG"
        assert SignalType.SHORT.value == "SHORT"
        assert SignalType.SCALP.value == "SCALP"

    def test_signal_type_from_string(self):
        """Test creating SignalType from string."""
        assert SignalType("LONG") == SignalType.LONG
        assert SignalType("SHORT") == SignalType.SHORT
        assert SignalType("SCALP") == SignalType.SCALP


class TestCollectionWindow:
    """Tests for CollectionWindow enum."""

    def test_collection_window_values(self):
        """Test CollectionWindow enum values."""
        assert CollectionWindow.ONE_HOUR.value == "1h"
        assert CollectionWindow.ONE_DAY.value == "24h"
        assert CollectionWindow.ONE_WEEK.value == "7d"
        assert CollectionWindow.ONE_MONTH.value == "30d"

    def test_to_hours(self):
        """Test conversion to hours."""
        assert CollectionWindow.ONE_HOUR.to_hours() == 1
        assert CollectionWindow.ONE_DAY.to_hours() == 24
        assert CollectionWindow.ONE_WEEK.to_hours() == 168
        assert CollectionWindow.ONE_MONTH.to_hours() == 720

    def test_to_seconds(self):
        """Test conversion to seconds."""
        assert CollectionWindow.ONE_HOUR.to_seconds() == 3600
        assert CollectionWindow.ONE_DAY.to_seconds() == 86400

    def test_from_string(self):
        """Test creating CollectionWindow from string."""
        assert CollectionWindow("1h") == CollectionWindow.ONE_HOUR
        assert CollectionWindow("24h") == CollectionWindow.ONE_DAY
        assert CollectionWindow("7d") == CollectionWindow.ONE_WEEK
        assert CollectionWindow("30d") == CollectionWindow.ONE_MONTH


class TestCalibrationRecord:
    """Tests for CalibrationRecord dataclass."""

    def test_valid_record_creation(self):
        """Test creating a valid CalibrationRecord."""
        timestamp = datetime.now(UTC)
        record = CalibrationRecord(
            timestamp=timestamp,
            signal_id="test-sig-001",
            predicted_prob=0.75,
            actual_outcome=1,
            signal_type=SignalType.LONG,
            confidence_bin=7,
        )

        assert record.timestamp == timestamp
        assert record.signal_id == "test-sig-001"
        assert record.predicted_prob == 0.75
        assert record.actual_outcome == 1
        assert record.signal_type == SignalType.LONG
        assert record.confidence_bin == 7
        assert record.strategy_id is None
        assert record.metadata == {}

    def test_record_with_optional_fields(self):
        """Test creating a record with optional fields."""
        timestamp = datetime.now(UTC)
        record = CalibrationRecord(
            timestamp=timestamp,
            signal_id="test-sig-002",
            predicted_prob=0.85,
            actual_outcome=0,
            signal_type=SignalType.SHORT,
            confidence_bin=8,
            strategy_id="grid_btc_1h",
            metadata={"source": "test", "version": "1.0"},
        )

        assert record.strategy_id == "grid_btc_1h"
        assert record.metadata == {"source": "test", "version": "1.0"}

    def test_invalid_predicted_prob_high(self):
        """Test validation fails for predicted_prob > 1.0."""
        with pytest.raises(
            ValueError, match="predicted_prob must be between 0.0 and 1.0"
        ):
            CalibrationRecord(
                timestamp=datetime.now(UTC),
                signal_id="test",
                predicted_prob=1.5,
                actual_outcome=1,
                signal_type=SignalType.LONG,
                confidence_bin=9,
            )

    def test_invalid_predicted_prob_low(self):
        """Test validation fails for predicted_prob < 0.0."""
        with pytest.raises(
            ValueError, match="predicted_prob must be between 0.0 and 1.0"
        ):
            CalibrationRecord(
                timestamp=datetime.now(UTC),
                signal_id="test",
                predicted_prob=-0.1,
                actual_outcome=1,
                signal_type=SignalType.LONG,
                confidence_bin=0,
            )

    def test_invalid_actual_outcome(self):
        """Test validation fails for non-binary actual_outcome."""
        with pytest.raises(ValueError, match="actual_outcome must be 0 or 1"):
            CalibrationRecord(
                timestamp=datetime.now(UTC),
                signal_id="test",
                predicted_prob=0.5,
                actual_outcome=2,
                signal_type=SignalType.LONG,
                confidence_bin=5,
            )

    def test_invalid_confidence_bin_high(self):
        """Test validation fails for confidence_bin > 9."""
        with pytest.raises(ValueError, match="confidence_bin must be between 0 and 9"):
            CalibrationRecord(
                timestamp=datetime.now(UTC),
                signal_id="test",
                predicted_prob=0.5,
                actual_outcome=1,
                signal_type=SignalType.LONG,
                confidence_bin=10,
            )

    def test_invalid_confidence_bin_low(self):
        """Test validation fails for confidence_bin < 0."""
        with pytest.raises(ValueError, match="confidence_bin must be between 0 and 9"):
            CalibrationRecord(
                timestamp=datetime.now(UTC),
                signal_id="test",
                predicted_prob=0.5,
                actual_outcome=1,
                signal_type=SignalType.LONG,
                confidence_bin=-1,
            )

    def test_calculate_confidence_bin(self):
        """Test confidence bin calculation."""
        # Test edge cases
        assert CalibrationRecord.calculate_confidence_bin(0.0) == 0
        assert CalibrationRecord.calculate_confidence_bin(0.09) == 0
        assert CalibrationRecord.calculate_confidence_bin(0.1) == 1
        assert CalibrationRecord.calculate_confidence_bin(0.5) == 5
        assert CalibrationRecord.calculate_confidence_bin(0.99) == 9
        assert CalibrationRecord.calculate_confidence_bin(1.0) == 9

    def test_calculate_confidence_bin_invalid(self):
        """Test confidence bin calculation with invalid input."""
        with pytest.raises(ValueError):
            CalibrationRecord.calculate_confidence_bin(1.5)

        with pytest.raises(ValueError):
            CalibrationRecord.calculate_confidence_bin(-0.1)

    def test_bin_range(self):
        """Test bin range calculation."""
        record = CalibrationRecord(
            timestamp=datetime.now(UTC),
            signal_id="test",
            predicted_prob=0.75,
            actual_outcome=1,
            signal_type=SignalType.LONG,
            confidence_bin=7,
        )

        assert record.bin_range == (0.7, 0.8)

    def test_to_dict(self):
        """Test conversion to dictionary."""
        timestamp = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        record = CalibrationRecord(
            timestamp=timestamp,
            signal_id="test-sig-001",
            predicted_prob=0.75,
            actual_outcome=1,
            signal_type=SignalType.LONG,
            confidence_bin=7,
            strategy_id="test-strategy",
            metadata={"key": "value"},
        )

        data = record.to_dict()

        assert data["timestamp"] == "2024-01-15T12:00:00+00:00"
        assert data["signal_id"] == "test-sig-001"
        assert data["predicted_prob"] == 0.75
        assert data["actual_outcome"] == 1
        assert data["signal_type"] == "LONG"
        assert data["confidence_bin"] == 7
        assert data["strategy_id"] == "test-strategy"
        assert data["metadata"] == {"key": "value"}

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "timestamp": "2024-01-15T12:00:00+00:00",
            "signal_id": "test-sig-001",
            "predicted_prob": 0.75,
            "actual_outcome": 1,
            "signal_type": "LONG",
            "confidence_bin": 7,
            "strategy_id": "test-strategy",
            "metadata": {"key": "value"},
        }

        record = CalibrationRecord.from_dict(data)

        assert record.signal_id == "test-sig-001"
        assert record.predicted_prob == 0.75
        assert record.actual_outcome == 1
        assert record.signal_type == SignalType.LONG
        assert record.confidence_bin == 7
        assert record.strategy_id == "test-strategy"
        assert record.metadata == {"key": "value"}

    def test_from_dict_without_timestamp(self):
        """Test creation from dictionary without timestamp."""
        data = {
            "signal_id": "test-sig-001",
            "predicted_prob": 0.75,
            "actual_outcome": 1,
            "signal_type": "LONG",
            "confidence_bin": 7,
        }

        record = CalibrationRecord.from_dict(data)

        assert record.signal_id == "test-sig-001"
        assert record.timestamp is not None

    def test_to_ece_format(self):
        """Test conversion to ECE format."""
        record = CalibrationRecord(
            timestamp=datetime.now(UTC),
            signal_id="test",
            predicted_prob=0.75,
            actual_outcome=1,
            signal_type=SignalType.LONG,
            confidence_bin=7,
        )

        ece_data = record.to_ece_format()

        assert ece_data["confidence"] == 0.75
        assert ece_data["outcome"] == 1


class TestCalibrationConfig:
    """Tests for CalibrationConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = CalibrationConfig()

        assert config.n_bins == 10
        assert config.retention_days == 90
        assert config.default_window == CollectionWindow.ONE_DAY
        assert config.redis_host == "host.docker.internal"
        assert config.redis_port == 6380
        assert config.redis_db == 0
        assert config.key_prefix == "calibration"
        assert config.enable_compression is False

    def test_custom_config(self):
        """Test custom configuration values."""
        config = CalibrationConfig(
            n_bins=20,
            retention_days=180,
            default_window=CollectionWindow.ONE_WEEK,
            redis_host="localhost",
            redis_port=6379,
            redis_db=1,
            key_prefix="custom",
            enable_compression=True,
        )

        assert config.n_bins == 20
        assert config.retention_days == 180
        assert config.default_window == CollectionWindow.ONE_WEEK
        assert config.redis_host == "localhost"
        assert config.redis_port == 6379
        assert config.redis_db == 1
        assert config.key_prefix == "custom"
        assert config.enable_compression is True

    def test_get_redis_key(self):
        """Test Redis key generation."""
        config = CalibrationConfig()

        key = config.get_redis_key(SignalType.LONG, "2024-01-15")
        assert key == "calibration:LONG:2024-01-15"

        key = config.get_redis_key(SignalType.SHORT, "2024-12-25")
        assert key == "calibration:SHORT:2024-12-25"

    def test_get_redis_pattern(self):
        """Test Redis pattern generation."""
        config = CalibrationConfig()

        # Pattern for specific signal type
        pattern = config.get_redis_pattern(SignalType.LONG)
        assert pattern == "calibration:LONG:*"

        # Pattern for all signal types
        pattern = config.get_redis_pattern(None)
        assert pattern == "calibration:*"

    def test_to_dict(self):
        """Test conversion to dictionary."""
        config = CalibrationConfig(
            n_bins=15,
            retention_days=60,
            default_window=CollectionWindow.ONE_HOUR,
        )

        data = config.to_dict()

        assert data["n_bins"] == 15
        assert data["retention_days"] == 60
        assert data["default_window"] == "1h"
        assert data["redis_host"] == "host.docker.internal"
        assert data["redis_port"] == 6380

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "n_bins": 20,
            "retention_days": 120,
            "default_window": "7d",
            "redis_host": "redis.example.com",
            "redis_port": 6380,
            "redis_db": 2,
            "key_prefix": "prod",
            "enable_compression": True,
        }

        config = CalibrationConfig.from_dict(data)

        assert config.n_bins == 20
        assert config.retention_days == 120
        assert config.default_window == CollectionWindow.ONE_WEEK
        assert config.redis_host == "redis.example.com"
        assert config.redis_db == 2
        assert config.key_prefix == "prod"
        assert config.enable_compression is True
