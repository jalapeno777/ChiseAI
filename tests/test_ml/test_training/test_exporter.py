"""Tests for dataset exporter module."""

from __future__ import annotations

import tempfile
from datetime import datetime

import pytest

from ml.training.exporter import (
    DatasetExporter,
    DatasetInfo,
    DatasetStatistics,
    ExportFormat,
    ModelType,
    export_from_samples,
)
from ml.training.extractor import FeatureExtractor
from ml.training.pipeline import TrainingPipeline
from ml.training.schema import TrainingSample


@pytest.fixture
def pipeline():
    """Create test pipeline."""
    extractor = FeatureExtractor()
    return TrainingPipeline(extractor)


@pytest.fixture
def exporter(pipeline):
    """Create test exporter."""
    return DatasetExporter(pipeline)


@pytest.fixture
def sample_samples():
    """Create sample training data."""
    samples = []
    for i in range(100):
        sample = TrainingSample(
            sample_id=f"test-{i:04d}",
            timestamp=datetime.now(),
            token="BTC" if i % 2 == 0 else "ETH",
            timeframe="1h" if i % 3 == 0 else "4h",
            rsi=50 + (i % 40),
            macd=i * 0.1,
            macd_signal=i * 0.1 - 5,
            macd_histogram=5,
            bb_upper=50000 + i * 10,
            bb_lower=49000 + i * 10,
            bb_width=2.0,
            atr=1000,
            volume_sma=1.2,
            trend_state="bullish" if i % 2 == 0 else "bearish",
            confluence_score=60 + (i % 30),
            confidence=0.7,
            direction="long" if i % 2 == 0 else "short",
            entry_price=50000,
            price_change_24h=2.5,
            volatility=2.0,
            outcome=1 if i % 5 != 0 else 0,
            pnl_percent=2.5 if i % 5 != 0 else -1.5,
            holding_period_minutes=60 + i,
        )
        samples.append(sample)
    return samples


class TestDatasetExporter:
    """Tests for DatasetExporter class."""

    def test_export_parquet(self, exporter, sample_samples, tmp_path):
        """Test Parquet export."""
        output_path = tmp_path / "test.parquet"

        info = exporter.export_dataset(
            samples=sample_samples,
            output_path=str(output_path),
            format=ExportFormat.PARQUET,
            train_test_split=0.8,
        )

        assert output_path.exists()
        assert info.num_samples == 100
        assert info.format == ExportFormat.PARQUET
        assert info.train_samples == 80
        assert info.test_samples == 20
        assert info.statistics.win_rate > 0

    def test_export_csv(self, exporter, sample_samples, tmp_path):
        """Test CSV export."""
        output_path = tmp_path / "test.csv"

        info = exporter.export_dataset(
            samples=sample_samples,
            output_path=str(output_path),
            format=ExportFormat.CSV,
            train_test_split=0.8,
        )

        assert output_path.exists()
        assert info.num_samples == 100
        assert info.format == ExportFormat.CSV

    def test_export_json(self, exporter, sample_samples, tmp_path):
        """Test JSON export."""
        output_path = tmp_path / "test.json"

        info = exporter.export_dataset(
            samples=sample_samples,
            output_path=str(output_path),
            format=ExportFormat.JSON,
            train_test_split=0.0,
        )

        assert output_path.exists()
        assert info.num_samples == 100
        assert info.format == ExportFormat.JSON
        assert info.train_samples == 100
        assert info.test_samples == 0

    def test_export_hdf5(self, exporter, sample_samples, tmp_path):
        """Test HDF5 export."""
        # Check if h5py is available
        pytest.importorskip("h5py")

        output_path = tmp_path / "test.h5"

        info = exporter.export_dataset(
            samples=sample_samples,
            output_path=str(output_path),
            format=ExportFormat.HDF5,
            train_test_split=0.8,
        )

        assert output_path.exists()
        assert info.num_samples == 100
        assert info.format == ExportFormat.HDF5

    def test_statistics_calculation(self, exporter, sample_samples):
        """Test statistics calculation."""
        stats = exporter._calculate_statistics(sample_samples)

        assert stats.win_rate > 0
        assert stats.avg_pnl != 0
        assert "wins" in stats.outcome_distribution
        assert "losses" in stats.outcome_distribution
        assert "rsi" in stats.feature_means
        assert "macd" in stats.feature_means

    def test_max_drawdown_calculation(self, exporter):
        """Test max drawdown calculation."""
        # Simulate a losing streak followed by recovery
        pnl_values = [1.0, 2.0, -3.0, -2.0, -1.0, 1.0, 3.0, 5.0]
        max_dd = exporter._calculate_max_drawdown(pnl_values)

        # Should be negative (drawdown)
        assert max_dd < 0

    def test_split_data_no_shuffle(self, exporter, sample_samples):
        """Test data splitting without shuffle."""
        data = exporter._samples_to_dicts(sample_samples)
        train, test = exporter._split_data(data, 0.8, shuffle=False, random_seed=42)

        assert len(train) == 80
        assert len(test) == 20

    def test_split_data_with_shuffle(self, exporter, sample_samples):
        """Test data splitting with shuffle."""
        data = exporter._samples_to_dicts(sample_samples)

        # Different seeds should produce different splits
        train1, _ = exporter._split_data(data, 0.8, shuffle=True, random_seed=1)
        train2, _ = exporter._split_data(data, 0.8, shuffle=True, random_seed=2)

        # Same seed should produce same split
        train3, _ = exporter._split_data(data, 0.8, shuffle=True, random_seed=1)

        # Check that shuffles differ (with very high probability)
        assert train1 != train2
        # Check reproducibility
        assert train1 == train3

    def test_empty_samples_raises_error(self, exporter, tmp_path):
        """Test that empty samples raises error."""
        with pytest.raises(ValueError, match="No samples"):
            exporter.export_dataset(
                samples=[],
                output_path=str(tmp_path / "test.parquet"),
                format=ExportFormat.PARQUET,
            )

    def test_unlabeled_samples_raises_error(self, exporter, tmp_path):
        """Test that unlabeled samples raises error."""
        # Create unlabeled samples
        samples = [
            TrainingSample(
                sample_id=f"test-{i}",
                timestamp=datetime.now(),
                token="BTC",
                timeframe="1h",
                rsi=50,
            )
            for i in range(10)
        ]

        with pytest.raises(ValueError, match="No labeled"):
            exporter.export_dataset(
                samples=samples,
                output_path=str(tmp_path / "test.parquet"),
                format=ExportFormat.PARQUET,
            )

    def test_generate_statistics_from_parquet(self, exporter, sample_samples, tmp_path):
        """Test statistics generation from Parquet file."""
        output_path = tmp_path / "stats_test.parquet"

        exporter.export_dataset(
            samples=sample_samples,
            output_path=str(output_path),
            format=ExportFormat.PARQUET,
            train_test_split=0.0,
        )

        stats = exporter.generate_statistics(str(output_path))

        assert stats.win_rate > 0
        assert stats.avg_pnl != 0

    def test_generate_statistics_from_csv(self, exporter, sample_samples, tmp_path):
        """Test statistics generation from CSV file."""
        output_path = tmp_path / "stats_test.csv"

        exporter.export_dataset(
            samples=sample_samples,
            output_path=str(output_path),
            format=ExportFormat.CSV,
            train_test_split=0.0,
        )

        stats = exporter.generate_statistics(str(output_path))

        assert stats.win_rate > 0


class TestExportFromSamples:
    """Tests for convenience function."""

    def test_export_from_samples_parquet(self, sample_samples, tmp_path):
        """Test export_from_samples convenience function."""
        output_path = tmp_path / "convenience.parquet"

        info = export_from_samples(
            samples=sample_samples,
            output_path=str(output_path),
            format=ExportFormat.PARQUET,
            train_test_split=0.8,
        )

        assert info.num_samples == 100
        assert output_path.exists()


class TestDatasetInfo:
    """Tests for DatasetInfo dataclass."""

    def test_to_dict(self):
        """Test DatasetInfo serialization."""
        stats = DatasetStatistics(
            win_rate=0.6,
            avg_pnl=2.5,
            max_drawdown=-5.0,
            outcome_distribution={"wins": 60, "losses": 40},
        )

        info = DatasetInfo(
            path="/tmp/test.parquet",
            format=ExportFormat.PARQUET,
            num_samples=100,
            num_features=14,
            train_samples=80,
            test_samples=20,
            created_at=datetime(2026, 1, 1),
            feature_names=["rsi", "macd"],
            statistics=stats,
        )

        d = info.to_dict()

        assert d["path"] == "/tmp/test.parquet"
        assert d["format"] == "parquet"
        assert d["num_samples"] == 100
        assert d["statistics"]["win_rate"] == 0.6


class TestDatasetStatistics:
    """Tests for DatasetStatistics dataclass."""

    def test_to_dict(self):
        """Test DatasetStatistics serialization."""
        stats = DatasetStatistics(
            win_rate=0.75,
            avg_pnl=3.5,
            max_drawdown=-2.0,
            feature_means={"rsi": 50.0},
            feature_stds={"rsi": 15.0},
            outcome_distribution={"wins": 75, "losses": 25},
        )

        d = stats.to_dict()

        assert d["win_rate"] == 0.75
        assert d["avg_pnl"] == 3.5
        assert d["feature_means"]["rsi"] == 50.0
        assert d["outcome_distribution"]["wins"] == 75


class TestExportFormats:
    """Tests for export format handling."""

    @pytest.mark.parametrize(
        "format",
        [
            ExportFormat.CSV,
            ExportFormat.PARQUET,
            ExportFormat.JSON,
        ],
    )
    def test_all_formats(self, exporter, sample_samples, tmp_path, format):
        """Test all export formats."""
        output_path = tmp_path / f"test.{format.value}"

        info = exporter.export_dataset(
            samples=sample_samples,
            output_path=str(output_path),
            format=format,
            train_test_split=0.0,
        )

        assert output_path.exists()
        assert info.format == format


class TestCli:
    """Test CLI interface."""

    def test_cli_demo_command(self, tmp_path):
        """Test CLI demo command."""
        from ml.training.cli import main

        output_path = tmp_path / "cli_demo.parquet"

        # Mock sys.argv
        import sys

        original_argv = sys.argv
        sys.argv = [
            "cli",
            "demo",
            "--output",
            str(output_path),
            "--samples",
            "50",
        ]

        try:
            result = main()
            assert result == 0
            assert output_path.exists()
        finally:
            sys.argv = original_argv

    def test_cli_help(self):
        """Test CLI help output."""
        from ml.training.cli import create_parser

        parser = create_parser()
        # Test that parser can be created without error
        assert parser is not None


def test_hdf5_format_requires_h5py():
    """Test that HDF5 export requires h5py."""
    extractor = FeatureExtractor()
    pipeline = TrainingPipeline(extractor)
    exporter = DatasetExporter(pipeline)

    # Create minimal samples
    samples = [
        TrainingSample(
            sample_id=f"test-{i}",
            timestamp=datetime.now(),
            token="BTC",
            timeframe="1h",
            rsi=50,
            outcome=1,
            pnl_percent=2.0,
        )
        for i in range(5)
    ]

    with tempfile.NamedTemporaryFile(suffix=".h5", delete=False) as f:
        # This should work if h5py is available
        try:
            info = exporter.export_dataset(
                samples=samples,
                output_path=f.name,
                format=ExportFormat.HDF5,
                train_test_split=0.0,
            )
            assert info.num_samples == 5
        except ImportError:
            pytest.skip("h5py not installed")


def test_pytorch_export_requires_torch():
    """Test PyTorch export requires torch."""
    extractor = FeatureExtractor()
    pipeline = TrainingPipeline(extractor)
    exporter = DatasetExporter(pipeline)

    samples = [
        TrainingSample(
            sample_id=f"test-{i}",
            timestamp=datetime.now(),
            token="BTC",
            timeframe="1h",
            rsi=50,
            outcome=1,
            pnl_percent=2.0,
        )
        for i in range(5)
    ]

    with tempfile.NamedTemporaryFile(suffix=".pt", delete=False) as f:
        try:
            info = exporter.export_for_model(
                samples=samples,
                model_type=ModelType.PYTORCH,
                output_path=f.name,
                train_test_split=0.8,
            )
            assert info.num_samples == 5
        except ImportError:
            pytest.skip("PyTorch not installed")


def test_tensorflow_export_requires_tf():
    """Test TensorFlow export requires TensorFlow."""
    extractor = FeatureExtractor()
    pipeline = TrainingPipeline(extractor)
    exporter = DatasetExporter(pipeline)

    samples = [
        TrainingSample(
            sample_id=f"test-{i}",
            timestamp=datetime.now(),
            token="BTC",
            timeframe="1h",
            rsi=50,
            outcome=1,
            pnl_percent=2.0,
        )
        for i in range(5)
    ]

    with tempfile.NamedTemporaryFile(suffix=".tfrecord", delete=False) as f:
        try:
            info = exporter.export_for_model(
                samples=samples,
                model_type=ModelType.TENSORFLOW,
                output_path=f.name,
                train_test_split=0.8,
            )
            assert info.num_samples == 5
        except ImportError:
            pytest.skip("TensorFlow not installed")
