"""Unit tests for training data schema.

Tests TrainingSample, TrainingDataset, and related components.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

# Import training module
import sys

sys.path.insert(0, "/tmp/worktrees/ST-NS-020-dev/src")

from ml.training import (
    TrainingSample,
    TrainingDataset,
    FeatureValidator,
    FeatureSpec,
    FeatureType,
    TrendState,
    StorageFormatManager,
    DatasetMetadata,
    SchemaVersion,
    SchemaVersionManager,
    CURRENT_SCHEMA_VERSION,
)


class TestSchemaVersion:
    """Tests for SchemaVersion class."""

    def test_version_creation(self):
        """Test creating schema version."""
        version = SchemaVersion(1, 2, 3)
        assert version.major == 1
        assert version.minor == 2
        assert version.patch == 3
        assert str(version) == "1.2.3"

    def test_version_from_string(self):
        """Test parsing version from string."""
        version = SchemaVersion.from_string("2.1.0")
        assert version.major == 2
        assert version.minor == 1
        assert version.patch == 0

    def test_version_from_string_invalid(self):
        """Test parsing invalid version string."""
        with pytest.raises(ValueError):
            SchemaVersion.from_string("1.0")

        with pytest.raises(ValueError):
            SchemaVersion.from_string("invalid")

    def test_version_compatibility(self):
        """Test version compatibility check."""
        v1 = SchemaVersion(1, 0, 0)
        v2 = SchemaVersion(1, 1, 0)
        v3 = SchemaVersion(2, 0, 0)

        # Same major version = compatible
        assert v1.is_compatible_with(v2)
        assert v2.is_compatible_with(v1)

        # Different major version = incompatible
        assert not v1.is_compatible_with(v3)
        assert not v3.is_compatible_with(v1)

    def test_version_comparison(self):
        """Test version comparison."""
        v1 = SchemaVersion(1, 0, 0)
        v2 = SchemaVersion(1, 1, 0)
        v3 = SchemaVersion(2, 0, 0)
        v4 = SchemaVersion(1, 0, 1)

        assert v2.is_newer_than(v1)
        assert v3.is_newer_than(v2)
        assert v4.is_newer_than(v1)
        assert not v1.is_newer_than(v2)


class TestSchemaVersionManager:
    """Tests for SchemaVersionManager class."""

    def test_get_version(self):
        """Test getting current version."""
        manager = SchemaVersionManager()
        version = manager.get_version()
        assert isinstance(version, SchemaVersion)
        assert version == CURRENT_SCHEMA_VERSION

    def test_validate_version(self):
        """Test version validation."""
        manager = SchemaVersionManager()

        # Valid version
        assert manager.validate_version("1.0.0")

        # Invalid version
        assert not manager.validate_version("2.0.0")  # Different major
        assert not manager.validate_version("invalid")

    def test_check_compatibility(self):
        """Test compatibility check."""
        manager = SchemaVersionManager()

        # Compatible version
        compatible, msg = manager.check_compatibility("1.0.0")
        assert compatible

        # Incompatible version
        compatible, msg = manager.check_compatibility("2.0.0")
        assert not compatible
        assert "Incompatible" in msg


class TestTrainingSample:
    """Tests for TrainingSample class."""

    def test_sample_creation(self):
        """Test creating training sample."""
        sample = TrainingSample(
            token="BTC",
            timeframe="1h",
            rsi=65.5,
            macd=0.5,
            trend_state="bullish",
        )

        assert sample.token == "BTC"
        assert sample.timeframe == "1h"
        assert sample.rsi == 65.5
        assert sample.trend_state == "bullish"
        assert sample.sample_id is not None
        assert sample.schema_version == str(CURRENT_SCHEMA_VERSION)

    def test_sample_validation_rsi_range(self):
        """Test RSI range validation."""
        # Valid RSI
        sample = TrainingSample(token="BTC", timeframe="1h", rsi=50.0)
        assert sample.rsi == 50.0

        # Invalid RSI (too high)
        with pytest.raises(ValueError):
            TrainingSample(token="BTC", timeframe="1h", rsi=150.0)

        # Invalid RSI (too low)
        with pytest.raises(ValueError):
            TrainingSample(token="BTC", timeframe="1h", rsi=-10.0)

    def test_sample_validation_timeframe(self):
        """Test timeframe validation."""
        # Valid timeframes
        for tf in ["1m", "5m", "15m", "1h", "4h", "1d", "1w"]:
            sample = TrainingSample(token="BTC", timeframe=tf)
            assert sample.timeframe == tf

        # Invalid timeframe
        with pytest.raises(ValueError):
            TrainingSample(token="BTC", timeframe="invalid")

    def test_sample_validation_trend_state(self):
        """Test trend state validation."""
        # Valid states
        for state in ["bullish", "bearish", "neutral", "unknown"]:
            sample = TrainingSample(
                token="BTC",
                timeframe="1h",
                trend_state=state,
            )
            assert sample.trend_state == state

        # Invalid state
        with pytest.raises(ValueError):
            TrainingSample(
                token="BTC",
                timeframe="1h",
                trend_state="invalid",
            )

    def test_sample_validation_direction(self):
        """Test direction validation."""
        # Valid directions
        for direction in ["long", "short", "neutral"]:
            sample = TrainingSample(
                token="BTC",
                timeframe="1h",
                direction=direction,
            )
            assert sample.direction == direction

        # Invalid direction
        with pytest.raises(ValueError):
            TrainingSample(
                token="BTC",
                timeframe="1h",
                direction="invalid",
            )

    def test_sample_to_dict(self):
        """Test converting sample to dictionary."""
        sample = TrainingSample(
            token="BTC",
            timeframe="1h",
            rsi=65.5,
            outcome=1,
            pnl_percent=2.5,
        )

        data = sample.to_dict()
        assert data["token"] == "BTC"
        assert data["timeframe"] == "1h"
        assert data["rsi"] == 65.5
        assert data["outcome"] == 1
        assert data["pnl_percent"] == 2.5

    def test_sample_feature_dict(self):
        """Test getting feature dictionary."""
        sample = TrainingSample(
            token="BTC",
            timeframe="1h",
            rsi=65.5,
            outcome=1,
            pnl_percent=2.5,
        )

        features = sample.to_feature_dict()
        assert "token" in features
        assert "timeframe" in features
        assert "rsi" in features
        assert "outcome" not in features  # Labels excluded
        assert "pnl_percent" not in features

    def test_sample_label_dict(self):
        """Test getting label dictionary."""
        sample = TrainingSample(
            token="BTC",
            timeframe="1h",
            rsi=65.5,
            outcome=1,
            pnl_percent=2.5,
        )

        labels = sample.to_label_dict()
        assert "outcome" in labels
        assert "pnl_percent" in labels
        assert "token" not in labels  # Features excluded

    def test_sample_has_labels(self):
        """Test checking if sample has labels."""
        # With labels
        sample_with = TrainingSample(
            token="BTC",
            timeframe="1h",
            outcome=1,
        )
        assert sample_with.has_labels()

        # Without labels
        sample_without = TrainingSample(
            token="BTC",
            timeframe="1h",
        )
        assert not sample_without.has_labels()

    def test_sample_confidence_bucket(self):
        """Test confidence bucket calculation."""
        sample = TrainingSample(
            token="BTC",
            timeframe="1h",
            confidence=0.75,
        )
        assert sample.get_confidence_bucket() == 7

        # No confidence
        sample_no_conf = TrainingSample(token="BTC", timeframe="1h")
        assert sample_no_conf.get_confidence_bucket() == 0

        # Max confidence
        sample_max = TrainingSample(
            token="BTC",
            timeframe="1h",
            confidence=1.0,
        )
        assert sample_max.get_confidence_bucket() == 10


class TestTrainingDataset:
    """Tests for TrainingDataset class."""

    def test_dataset_creation(self):
        """Test creating empty dataset."""
        dataset = TrainingDataset()
        assert dataset.get_sample_count() == 0

    def test_dataset_add_sample(self):
        """Test adding sample to dataset."""
        dataset = TrainingDataset()
        sample = TrainingSample(token="BTC", timeframe="1h", rsi=65.5)

        assert dataset.add_sample(sample)
        assert dataset.get_sample_count() == 1

    def test_dataset_add_samples(self):
        """Test adding multiple samples."""
        dataset = TrainingDataset()
        samples = [
            TrainingSample(token="BTC", timeframe="1h"),
            TrainingSample(token="ETH", timeframe="1h"),
            TrainingSample(token="BTC", timeframe="4h"),
        ]

        added = dataset.add_samples(samples)
        assert added == 3
        assert dataset.get_sample_count() == 3

    def test_dataset_get_labeled_samples(self):
        """Test getting labeled samples."""
        dataset = TrainingDataset()

        # Add labeled sample
        labeled = TrainingSample(
            token="BTC",
            timeframe="1h",
            outcome=1,
            pnl_percent=2.5,
        )
        dataset.add_sample(labeled)

        # Add unlabeled sample
        unlabeled = TrainingSample(token="ETH", timeframe="1h")
        dataset.add_sample(unlabeled)

        labeled_samples = dataset.get_labeled_samples()
        assert len(labeled_samples) == 1
        assert labeled_samples[0].token == "BTC"

    def test_dataset_get_unlabeled_samples(self):
        """Test getting unlabeled samples."""
        dataset = TrainingDataset()

        # Add labeled sample
        labeled = TrainingSample(
            token="BTC",
            timeframe="1h",
            outcome=1,
        )
        dataset.add_sample(labeled)

        # Add unlabeled sample
        unlabeled = TrainingSample(token="ETH", timeframe="1h")
        dataset.add_sample(unlabeled)

        unlabeled_samples = dataset.get_unlabeled_samples()
        assert len(unlabeled_samples) == 1
        assert unlabeled_samples[0].token == "ETH"

    def test_dataset_validate_schema(self):
        """Test schema validation."""
        dataset = TrainingDataset()

        # Valid data
        valid_data = {
            "token": "BTC",
            "timeframe": "1h",
            "rsi": 65.5,
        }
        assert dataset.validate_schema(valid_data)

        # Invalid data (missing required field)
        invalid_data = {
            "token": "BTC",
            "rsi": 65.5,
        }
        assert not dataset.validate_schema(invalid_data)

    def test_dataset_get_statistics(self):
        """Test getting dataset statistics."""
        dataset = TrainingDataset()

        # Empty dataset
        stats = dataset.get_statistics()
        assert stats["sample_count"] == 0

        # Add samples
        dataset.add_sample(
            TrainingSample(
                token="BTC",
                timeframe="1h",
                outcome=1,
            )
        )
        dataset.add_sample(
            TrainingSample(
                token="ETH",
                timeframe="4h",
                outcome=0,
            )
        )

        stats = dataset.get_statistics()
        assert stats["sample_count"] == 2
        assert stats["labeled_count"] == 2
        assert "BTC" in stats["unique_tokens"]
        assert "ETH" in stats["unique_tokens"]
        assert "1h" in stats["unique_timeframes"]
        assert "4h" in stats["unique_timeframes"]

    def test_dataset_export_import_csv(self):
        """Test CSV export and import."""
        dataset = TrainingDataset()
        dataset.add_sample(
            TrainingSample(
                token="BTC",
                timeframe="1h",
                rsi=65.5,
                outcome=1,
            )
        )

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name

        try:
            # Export
            assert dataset.export_csv(path)

            # Import
            imported = TrainingDataset.from_csv(path)
            assert imported.get_sample_count() == 1
            assert imported.samples[0].token == "BTC"
        finally:
            Path(path).unlink(missing_ok=True)

    def test_dataset_export_import_json(self):
        """Test JSON export and import."""
        dataset = TrainingDataset()
        dataset.add_sample(
            TrainingSample(
                token="BTC",
                timeframe="1h",
                rsi=65.5,
                outcome=1,
            )
        )

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            # Export
            assert dataset.export_json(path)

            # Verify file exists and has content
            with open(path) as f:
                data = json.load(f)
            assert len(data) == 1
            assert data[0]["token"] == "BTC"
        finally:
            Path(path).unlink(missing_ok=True)


class TestFeatureValidator:
    """Tests for FeatureValidator class."""

    def test_validate_numeric_feature(self):
        """Test numeric feature validation."""
        validator = FeatureValidator()

        # Valid numeric
        is_valid, error = validator.validate_feature("rsi", 50.0)
        assert is_valid
        assert error == ""

        # Out of range
        is_valid, error = validator.validate_feature("rsi", 150.0)
        assert not is_valid
        assert "above maximum" in error

    def test_validate_categorical_feature(self):
        """Test categorical feature validation."""
        validator = FeatureValidator()

        # Valid categorical
        is_valid, error = validator.validate_feature("trend_state", "bullish")
        assert is_valid

        # Invalid value
        is_valid, error = validator.validate_feature("trend_state", "invalid")
        assert not is_valid

    def test_validate_unknown_feature(self):
        """Test unknown feature validation."""
        validator = FeatureValidator()

        is_valid, error = validator.validate_feature("unknown_feature", "value")
        assert not is_valid
        assert "Unknown feature" in error

    def test_validate_features(self):
        """Test multiple feature validation."""
        validator = FeatureValidator()

        features = {
            "rsi": 50.0,
            "trend_state": "bullish",
            "token": "BTC",
        }

        is_valid, errors = validator.validate_features(features)
        assert is_valid
        assert len(errors) == 0

        # Invalid features
        invalid_features = {
            "rsi": 150.0,  # Out of range
            "trend_state": "invalid",
        }

        is_valid, errors = validator.validate_features(invalid_features)
        assert not is_valid
        assert len(errors) == 2


class TestStorageFormatManager:
    """Tests for StorageFormatManager class."""

    def test_get_supported_formats(self):
        """Test getting supported formats."""
        manager = StorageFormatManager()
        formats = manager.get_supported_formats()

        assert "parquet" in formats
        assert "csv" in formats
        assert "json" in formats

    def test_export_import_csv(self):
        """Test CSV export and import."""
        manager = StorageFormatManager()

        data = [
            {"token": "BTC", "rsi": 65.5},
            {"token": "ETH", "rsi": 45.0},
        ]

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = Path(f.name)

        try:
            # Export
            assert manager.export(data, path, "csv")

            # Import
            imported = manager.import_data(path, "csv")
            assert len(imported) == 2
            assert imported[0]["token"] == "BTC"
        finally:
            path.unlink(missing_ok=True)

    def test_validate_csv(self):
        """Test CSV validation."""
        manager = StorageFormatManager()

        # Valid CSV
        data = [{"token": "BTC", "rsi": 65.5}]

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = Path(f.name)

        try:
            manager.export(data, path, "csv")
            is_valid, msg = manager.validate(path, "csv")
            assert is_valid
            assert "Valid CSV" in msg
        finally:
            path.unlink(missing_ok=True)

    def test_export_with_metadata(self):
        """Test export with metadata."""
        manager = StorageFormatManager()

        data = [
            {"token": "BTC", "timeframe": "1h", "outcome": 1},
            {"token": "ETH", "timeframe": "4h", "outcome": 0},
        ]

        with tempfile.NamedTemporaryFile(suffix="", delete=False) as f:
            base_path = Path(f.name)

        try:
            success, metadata = manager.export_with_metadata(data, base_path, "csv")
            assert success
            assert metadata.sample_count == 2
            assert "BTC" in metadata.tokens
            assert "ETH" in metadata.tokens

            # Check metadata file was created
            metadata_path = base_path.with_suffix(".metadata.json")
            assert metadata_path.exists()
        finally:
            base_path.with_suffix(".csv").unlink(missing_ok=True)
            base_path.with_suffix(".metadata.json").unlink(missing_ok=True)


class TestAcceptanceCriteria:
    """Tests verifying acceptance criteria."""

    def test_ac_1_schema_definition(self):
        """AC1: Define training data schema with all signal features."""
        sample = TrainingSample(
            token="BTC",
            timeframe="1h",
            rsi=65.5,
            macd=0.5,
            macd_signal=0.3,
            macd_histogram=0.2,
            bb_upper=50000.0,
            bb_lower=48000.0,
            bb_width=4.0,
            atr=500.0,
            volume_sma=1.2,
            trend_state="bullish",
            confluence_score=75.0,
            confidence=0.8,
            direction="long",
            entry_price=49000.0,
            price_change_24h=2.5,
            volatility=0.05,
            outcome=1,
            pnl_percent=3.5,
            holding_period_minutes=120,
            predicted_prob=0.85,
            confidence_bin=8,
        )

        # Verify all fields are set
        assert sample.token == "BTC"
        assert sample.rsi == 65.5
        assert sample.trend_state == "bullish"
        assert sample.outcome == 1
        assert sample.pnl_percent == 3.5

    def test_ac_2_pydantic_validation(self):
        """AC2: Implement Pydantic models for validation."""
        # Valid sample
        sample = TrainingSample(token="BTC", timeframe="1h", rsi=50.0)
        assert isinstance(sample, TrainingSample)

        # Invalid sample (out of range)
        with pytest.raises(ValueError):
            TrainingSample(token="BTC", timeframe="1h", rsi=150.0)

        # Invalid sample (wrong enum)
        with pytest.raises(ValueError):
            TrainingSample(token="BTC", timeframe="1h", trend_state="invalid")

    def test_ac_3_export_formats(self):
        """AC3: Support multiple export formats (Parquet, CSV, JSON)."""
        manager = StorageFormatManager()
        formats = manager.get_supported_formats()

        assert "parquet" in formats
        assert "csv" in formats
        assert "json" in formats

    def test_ac_4_schema_versioning(self):
        """AC4: Schema versioning for backward compatibility."""
        manager = SchemaVersionManager()

        # Current version
        version = manager.get_version()
        assert isinstance(version, SchemaVersion)

        # Compatibility check
        compatible, msg = manager.check_compatibility("1.0.0")
        assert compatible

        # Incompatibility check
        compatible, msg = manager.check_compatibility("2.0.0")
        assert not compatible


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
