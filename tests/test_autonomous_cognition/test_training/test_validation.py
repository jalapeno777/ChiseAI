"""Tests for validation module."""

import pytest
from src.autonomous_cognition.training.validation import (
    ValidationMetrics,
    ValidationSplit,
    ValidationSplitManager,
    create_validation_split_manager,
)
from src.ml.training.training_pipeline import TrainingConfig


class TestValidationMetrics:
    """Tests for ValidationMetrics dataclass."""

    def test_creation(self):
        """Test validation metrics creation."""
        metrics = ValidationMetrics(
            loss=0.5,
            metric=0.8,
            num_samples=100,
        )
        assert metrics.loss == 0.5
        assert metrics.metric == 0.8
        assert metrics.num_samples == 100

    def test_to_dict(self):
        """Test validation metrics to dict."""
        metrics = ValidationMetrics(
            loss=0.5,
            metric=0.8,
            num_samples=100,
        )
        d = metrics.to_dict()
        assert d["loss"] == 0.5
        assert d["metric"] == 0.8
        assert d["num_samples"] == 100


class TestValidationSplit:
    """Tests for ValidationSplit dataclass."""

    def test_creation(self):
        """Test validation split creation."""
        split = ValidationSplit(
            train_data=[1, 2, 3],
            val_data=[4, 5],
            test_data=[6, 7],
        )
        assert split.train_count == 3
        assert split.val_count == 2
        assert split.test_count == 2
        assert split.total_count == 7

    def test_default_config(self):
        """Test default configuration."""
        split = ValidationSplit()
        assert split.config.train_ratio == 0.70
        assert split.config.validation_ratio == 0.15
        assert split.config.test_ratio == 0.15


class TestValidationSplitManager:
    """Tests for ValidationSplitManager class."""

    def test_creation(self):
        """Test manager creation."""
        manager = ValidationSplitManager()
        assert manager.config.train_ratio == 0.70

    def test_create_split(self):
        """Test split creation."""
        manager = ValidationSplitManager(
            config=TrainingConfig(
                train_ratio=0.7,
                validation_ratio=0.15,
                test_ratio=0.15,
            )
        )

        samples = list(range(100))
        split = manager.create_split(samples)

        assert split.train_count == 70
        assert split.val_count == 15
        assert split.test_count == 15
        assert split.total_count == 100

    def test_create_split_empty(self):
        """Test split with empty data."""
        manager = ValidationSplitManager()
        split = manager.create_split([])
        assert split.total_count == 0

    def test_create_split_small(self):
        """Test split with small dataset."""
        manager = ValidationSplitManager()
        split = manager.create_split([1, 2, 3])
        assert split.train_count >= 0
        assert split.val_count >= 0
        assert split.test_count >= 0
        assert split.total_count == 3

    def test_create_split_with_seed(self):
        """Test split with specific seed."""
        manager = ValidationSplitManager(config=TrainingConfig(random_seed=42))
        samples = list(range(100))

        split1 = manager.create_split(samples, seed=123)
        split2 = manager.create_split(samples, seed=123)

        # Same seed should produce same split
        assert split1.train_data == split2.train_data

    def test_compute_metrics(self):
        """Test metrics computation."""
        manager = ValidationSplitManager()

        params = {"x": 1.0}

        def metric_fn(p, sample):
            return (p["x"] - sample) ** 2

        data = [0.0, 1.0, 2.0]
        metrics = manager.compute_metrics(params, data, metric_fn)

        # (1-0)^2 + (1-1)^2 + (1-2)^2 = 1 + 0 + 1 = 2, avg = 2/3
        assert metrics.num_samples == 3
        assert metrics.metric == pytest.approx(2.0 / 3.0)

    def test_compute_metrics_with_loss(self):
        """Test metrics computation with loss function."""
        manager = ValidationSplitManager()

        params = {"x": 1.0}

        def loss_fn(p, sample):
            return (p["x"] - sample) ** 2

        def metric_fn(p, sample):
            return abs(p["x"] - sample)

        data = [0.0, 1.0, 2.0]
        metrics = manager.compute_metrics(params, data, metric_fn, loss_fn=loss_fn)

        assert metrics.loss == pytest.approx(2.0 / 3.0)
        assert metrics.metric == pytest.approx(2.0 / 3.0)

    def test_compute_metrics_empty(self):
        """Test metrics computation with empty data."""
        manager = ValidationSplitManager()
        params = {"x": 1.0}

        def metric_fn(p, sample):
            return 0.0

        metrics = manager.compute_metrics(params, [], metric_fn)
        assert metrics.loss == 0.0
        assert metrics.num_samples == 0

    def test_compute_metrics_async(self):
        """Test async metrics computation."""
        import asyncio

        manager = ValidationSplitManager()
        params = {"x": 1.0}

        def metric_fn(p, sample):
            return (p["x"] - sample) ** 2

        data = [0.0, 1.0, 2.0]

        async def run():
            return await manager.compute_metrics_async(params, data, metric_fn)

        metrics = asyncio.get_event_loop().run_until_complete(run())

        assert metrics.num_samples == 3
        assert metrics.metric == pytest.approx(2.0 / 3.0)

    def test_evaluate_on_test(self):
        """Test test set evaluation."""
        manager = ValidationSplitManager()
        params = {"x": 1.0}

        def metric_fn(p, sample):
            return abs(p["x"] - sample)

        test_data = [0.0, 2.0]
        metrics = manager.evaluate_on_test(params, test_data, metric_fn)

        # |1-0| + |1-2| = 1 + 1 = 2, avg = 1
        assert metrics.metric == pytest.approx(1.0)

    def test_get_split_info(self):
        """Test split info."""
        manager = ValidationSplitManager(
            config=TrainingConfig(
                train_ratio=0.7,
                validation_ratio=0.15,
                test_ratio=0.15,
                random_seed=42,
            )
        )

        split = manager.create_split(list(range(100)))
        info = manager.get_split_info(split)

        assert info["total_samples"] == 100
        assert info["train"]["count"] == 70
        assert info["train"]["ratio"] == 0.7
        assert info["validation"]["count"] == 15
        assert info["test"]["count"] == 15


class TestCreateValidationSplitManager:
    """Tests for create_validation_split_manager factory."""

    def test_factory(self):
        """Test factory function."""
        manager = create_validation_split_manager(
            train_ratio=0.8,
            validation_ratio=0.1,
            test_ratio=0.1,
            random_seed=123,
        )

        assert manager.config.train_ratio == 0.8
        assert manager.config.validation_ratio == 0.1
        assert manager.config.test_ratio == 0.1
        assert manager.config.random_seed == 123
