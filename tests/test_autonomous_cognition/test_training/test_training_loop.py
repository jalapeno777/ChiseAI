"""Tests for training_loop module."""

import pytest
from src.autonomous_cognition.training.training_loop import (
    EarlyStoppingMode,
    EpochMetrics,
    SyncTrainingLoop,
    TrainingLoop,
    TrainingLoopState,
)


class TestEpochMetrics:
    """Tests for EpochMetrics dataclass."""

    def test_creation(self):
        """Test epoch metrics creation."""
        metrics = EpochMetrics(
            epoch=1,
            train_loss=0.5,
            val_loss=0.4,
            train_metric=0.8,
            val_metric=0.75,
            learning_rate=0.01,
            duration_seconds=1.5,
        )
        assert metrics.epoch == 1
        assert metrics.train_loss == 0.5
        assert metrics.val_loss == 0.4

    def test_to_dict(self):
        """Test epoch metrics to dict."""
        metrics = EpochMetrics(epoch=1, train_loss=0.5, val_loss=0.4)
        d = metrics.to_dict()
        assert d["epoch"] == 1
        assert d["train_loss"] == 0.5
        assert d["val_loss"] == 0.4


class TestTrainingLoopState:
    """Tests for TrainingLoopState dataclass."""

    def test_creation(self):
        """Test state creation."""
        state = TrainingLoopState()
        assert state.current_epoch == 0
        assert state.best_epoch == 0
        assert state.best_val_loss == float("inf")
        assert state.is_training is False
        assert state.should_stop is False

    def test_to_dict(self):
        """Test state to dict."""
        state = TrainingLoopState(current_epoch=5, best_epoch=3)
        d = state.to_dict()
        assert d["current_epoch"] == 5
        assert d["best_epoch"] == 3


class TestTrainingLoop:
    """Tests for TrainingLoop class."""

    def test_creation(self):
        """Test training loop creation."""
        loop = TrainingLoop(max_epochs=100, early_stopping_patience=10)
        assert loop.max_epochs == 100
        assert loop.early_stopping_patience == 10

    def test_invalid_max_epochs(self):
        """Test invalid max epochs raises error."""
        with pytest.raises(ValueError, match="max_epochs must be positive"):
            TrainingLoop(max_epochs=0)

    def test_invalid_patience(self):
        """Test invalid patience raises error."""
        with pytest.raises(
            ValueError, match="early_stopping_patience must be positive"
        ):
            TrainingLoop(early_stopping_patience=0)

    def test_invalid_min_epochs(self):
        """Test invalid min_epochs raises error."""
        with pytest.raises(ValueError, match="min_epochs must be at least 1"):
            TrainingLoop(min_epochs=0)

    @pytest.mark.asyncio
    async def test_basic_training(self):
        """Test basic training run."""
        loop = TrainingLoop(max_epochs=5, early_stopping_patience=10, log_interval=5)

        loss_values = [1.0, 0.8, 0.6, 0.5, 0.4]

        async def train_step(params, batch):
            epoch = loop.state.current_epoch
            loss = loss_values[epoch - 1] if epoch <= len(loss_values) else 0.3
            return loss, {"metric": loss}

        async def val_step(params, val_data):
            epoch = loop.state.current_epoch
            loss = loss_values[epoch - 1] if epoch <= len(loss_values) else 0.3
            return loss, loss

        state = await loop.run(
            initial_params={"x": 0.0},
            train_step=train_step,
            val_step=val_step,
            train_data=None,
            val_data=None,
        )

        assert state.current_epoch == 5
        assert len(loop.history) == 5
        assert loop.history[0].epoch == 1
        assert loop.history[-1].epoch == 5

    @pytest.mark.asyncio
    async def test_early_stopping(self):
        """Test early stopping triggers."""
        loop = TrainingLoop(
            max_epochs=100,
            early_stopping_patience=3,
            early_stopping_mode=EarlyStoppingMode.PATIENCE,
            log_interval=1,
        )

        async def train_step(params, batch):
            return 1.0, {}

        async def val_step(params, val_data):
            # Validation loss increases (worse)
            return 1.0 + (loop.state.current_epoch * 0.1), 0.5

        state = await loop.run(
            initial_params={"x": 0.0},
            train_step=train_step,
            val_step=val_step,
            train_data=None,
            val_data=None,
        )

        # Should stop early due to no improvement
        assert state.current_epoch < 100
        assert state.should_stop is True

    @pytest.mark.asyncio
    async def test_early_stopping_min_epochs(self):
        """Test early stopping respects min_epochs."""
        loop = TrainingLoop(
            max_epochs=100,
            early_stopping_patience=3,
            min_epochs=10,
        )

        async def train_step(params, batch):
            return 1.0, {}

        async def val_step(params, val_data):
            return 1.0, 0.5

        state = await loop.run(
            initial_params={"x": 0.0},
            train_step=train_step,
            val_step=val_step,
            train_data=None,
            val_data=None,
        )

        # Should run at least min_epochs
        assert state.current_epoch >= 10

    @pytest.mark.asyncio
    async def test_metric_based_early_stopping(self):
        """Test metric-based early stopping."""
        loop = TrainingLoop(
            max_epochs=100,
            early_stopping_patience=1,
            early_stopping_mode=EarlyStoppingMode.METRIC,
            early_stopping_threshold=0.5,
            early_stopping_metric_direction="minimize",
        )

        async def train_step(params, batch):
            return 0.3, {}

        async def val_step(params, val_data):
            # Target metric drops below threshold quickly
            if loop.state.current_epoch >= 3:
                return 0.4, 0.4  # Below 0.5 threshold
            return 0.6, 0.6

        state = await loop.run(
            initial_params={"x": 0.0},
            train_step=train_step,
            val_step=val_step,
            train_data=None,
            val_data=None,
        )

        assert state.should_stop is True

    @pytest.mark.asyncio
    async def test_lr_scheduler_callback(self):
        """Test learning rate scheduler callback."""
        lrs = []

        def lr_scheduler(epoch):
            return 0.1 * (0.9**epoch)

        loop = TrainingLoop(
            max_epochs=5,
            lr_scheduler_fn=lr_scheduler,
            log_interval=1,
        )

        async def train_step(params, batch):
            lrs.append(loop.history[-1].learning_rate if loop.history else 0.1)
            return 0.5, {}

        async def val_step(params, val_data):
            return 0.5, 0.5

        await loop.run(
            initial_params={"x": 0.0},
            train_step=train_step,
            val_step=val_step,
            train_data=None,
            val_data=None,
        )

        # LR should decrease over epochs
        assert lrs[0] > lrs[-1]

    @pytest.mark.asyncio
    async def test_checkpoint_callback(self):
        """Test checkpoint callback is called."""
        checkpoints = []

        def checkpoint_callback(epoch, metrics):
            checkpoints.append((epoch, metrics.val_loss))

        loop = TrainingLoop(
            max_epochs=3,
            checkpoint_callback=checkpoint_callback,
        )

        async def train_step(params, batch):
            return 0.5, {}

        async def val_step(params, val_data):
            return 0.5, 0.5

        await loop.run(
            initial_params={"x": 0.0},
            train_step=train_step,
            val_step=val_step,
            train_data=None,
            val_data=None,
        )

        assert len(checkpoints) == 3
        assert checkpoints[0][0] == 1


class TestSyncTrainingLoop:
    """Tests for SyncTrainingLoop."""

    def test_sync_loop_creation(self):
        """Test sync training loop creation."""
        loop = SyncTrainingLoop(max_epochs=10)
        assert loop.state.current_epoch == 0

    def test_sync_loop_run(self):
        """Test sync training loop run."""

        loop = SyncTrainingLoop(max_epochs=5, log_interval=5)

        async def train_step(params, batch):
            return 0.5, {}

        async def val_step(params, val_data):
            return 0.5, 0.5

        state = loop.run(
            initial_params={"x": 0.0},
            train_step=train_step,
            val_step=val_step,
            train_data=None,
            val_data=None,
        )

        assert state.current_epoch == 5
        assert len(loop.history) == 5
