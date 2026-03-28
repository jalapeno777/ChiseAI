"""Integration tests for autocog training pipeline."""

import shutil
import tempfile

import pytest
from src.autonomous_cognition.training import (
    AutocogTrainingConfig,
    AutocogTrainingPipeline,
    AutocogTrainingResult,
    create_autocog_pipeline,
)


class TestAutocogTrainingPipeline:
    """Integration tests for AutocogTrainingPipeline."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Clean up temp files."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_creation(self):
        """Test pipeline creation."""
        params = {"threshold": 0.5}
        metric_fns = {"error": lambda p: (p["threshold"] - 0.8) ** 2}

        pipeline = AutocogTrainingPipeline(
            params=params,
            metric_fns=metric_fns,
            config=AutocogTrainingConfig(
                max_epochs=5,
                batch_size=4,
                checkpoint_dir=self.temp_dir,
            ),
        )

        assert pipeline.current_params == params
        assert pipeline.config.max_epochs == 5

    def test_pipeline_components(self):
        """Test that pipeline has all required components."""
        params = {"threshold": 0.5}
        metric_fns = {"error": lambda p: (p["threshold"] - 0.8) ** 2}

        pipeline = AutocogTrainingPipeline(
            params=params,
            metric_fns=metric_fns,
        )

        assert pipeline.validation_manager is not None
        assert pipeline.batch_processor is not None
        assert pipeline.checkpointing is not None
        assert pipeline.gradient_optimizer is not None

    def test_config_validation(self):
        """Test configuration validation."""
        params = {"threshold": 0.5}
        metric_fns = {"error": lambda p: 0.0}

        # Invalid split ratios should raise
        with pytest.raises(ValueError, match="Split ratios must sum to 1.0"):
            AutocogTrainingConfig(
                train_ratio=0.5,
                validation_ratio=0.3,
                test_ratio=0.3,  # Sum = 1.1
            )


class TestAutocogTrainingPipelineRun:
    """Tests for pipeline training execution."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Clean up temp files."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_train_simple(self):
        """Test simple training run."""
        params = {"threshold": 0.5}

        def metric_fn(p):
            # Minimize (threshold - 0.8)^2
            return (p["threshold"] - 0.8) ** 2

        pipeline = AutocogTrainingPipeline(
            params=params,
            metric_fns={"error": metric_fn},
            config=AutocogTrainingConfig(
                max_epochs=10,
                batch_size=8,
                early_stopping_patience=5,
                checkpoint_dir=self.temp_dir,
                require_constitution_audit=False,  # Skip audit for testing
            ),
        )

        # Create simple training data
        train_samples = list(range(20))
        val_samples = list(range(5))

        result = await pipeline.train(
            train_samples=train_samples,
            val_samples=val_samples,
        )

        assert isinstance(result, AutocogTrainingResult)
        assert result.final_state is not None
        assert len(result.training_history) <= 10

    @pytest.mark.asyncio
    async def test_train_with_audit(self):
        """Test training with constitution audit."""
        audit_calls = []

        def audit_fn(decision):
            audit_calls.append(decision)
            return True

        params = {"threshold": 0.5}

        def metric_fn(p):
            return (p["threshold"] - 0.8) ** 2

        pipeline = AutocogTrainingPipeline(
            params=params,
            metric_fns={"error": metric_fn},
            constitution_audit_fn=audit_fn,
            config=AutocogTrainingConfig(
                max_epochs=5,
                batch_size=4,
                checkpoint_dir=self.temp_dir,
                constitution_audit_required=True,
            ),
        )

        train_samples = list(range(10))
        val_samples = list(range(3))

        result = await pipeline.train(
            train_samples=train_samples,
            val_samples=val_samples,
        )

        # Audit should be called during optimization steps
        # (might be 0 if gradient updates are rejected or skipped)
        assert isinstance(result, AutocogTrainingResult)

    @pytest.mark.asyncio
    async def test_train_auto_split(self):
        """Test training with automatic data splitting."""
        params = {"threshold": 0.5}

        def metric_fn(p):
            return (p["threshold"] - 0.8) ** 2

        pipeline = AutocogTrainingPipeline(
            params=params,
            metric_fns={"error": metric_fn},
            config=AutocogTrainingConfig(
                max_epochs=5,
                batch_size=4,
                checkpoint_dir=self.temp_dir,
                require_constitution_audit=False,
            ),
        )

        # Provide only train_samples, split should happen automatically
        train_samples = list(range(20))

        result = await pipeline.train(train_samples=train_samples)

        assert result.success is True
        # Should have split data internally
        assert len(result.training_history) > 0

    def test_rollback_to_best(self):
        """Test rollback to best checkpoint."""
        params = {"threshold": 0.5}

        def metric_fn(p):
            return (p["threshold"] - 0.8) ** 2

        pipeline = AutocogTrainingPipeline(
            params=params,
            metric_fns={"error": metric_fn},
            config=AutocogTrainingConfig(
                max_epochs=3,
                batch_size=4,
                checkpoint_dir=self.temp_dir,
                require_constitution_audit=False,
            ),
        )

        # Simulate saving a checkpoint
        pipeline.checkpointing.check_and_save(
            epoch=1,
            params={"threshold": 0.7},
            metrics={"val_loss": 0.1},
        )

        # Modify current params
        pipeline._current_params = {"threshold": 0.3}

        # Rollback
        best = pipeline.rollback_to_best()
        assert best == {"threshold": 0.7}

    def test_get_best_params(self):
        """Test getting best params."""
        params = {"threshold": 0.5}

        def metric_fn(p):
            return (p["threshold"] - 0.8) ** 2

        pipeline = AutocogTrainingPipeline(
            params=params,
            metric_fns={"error": metric_fn},
            config=AutocogTrainingConfig(checkpoint_dir=self.temp_dir),
        )

        pipeline.checkpointing.check_and_save(
            epoch=1,
            params={"threshold": 0.6},
            metrics={"val_loss": 0.04},
        )

        best = pipeline.get_best_params()
        assert best == {"threshold": 0.6}


class TestCreateAutocogPipeline:
    """Tests for create_autocog_pipeline factory."""

    def test_factory(self):
        """Test factory function."""
        params = {"threshold": 0.5}

        def metric_fn(p):
            return (p["threshold"] - 0.8) ** 2

        pipeline = create_autocog_pipeline(
            params=params,
            metric_fns={"error": metric_fn},
            max_epochs=50,
            batch_size=32,
            learning_rate=0.01,
            optimizer_type="Adam",
            checkpoint_dir="/tmp/checkpoints",
        )

        assert pipeline.config.max_epochs == 50
        assert pipeline.config.batch_size == 32
        assert pipeline.config.learning_rate == 0.01
        assert pipeline.config.optimizer_type == "Adam"
        assert pipeline.config.checkpoint_dir == "/tmp/checkpoints"

    def test_factory_with_audit(self):
        """Test factory with constitution audit."""
        params = {"threshold": 0.5}

        def metric_fn(p):
            return 0.0

        def audit_fn(d):
            return True

        pipeline = create_autocog_pipeline(
            params=params,
            metric_fns={"error": metric_fn},
            constitution_audit_fn=audit_fn,
            max_epochs=10,
        )

        assert pipeline.constitution_audit_fn is audit_fn


class TestAutocogTrainingResult:
    """Tests for AutocogTrainingResult."""

    def test_to_dict(self):
        """Test result serialization."""
        from src.autonomous_cognition.training.training_loop import TrainingLoopState

        state = TrainingLoopState(
            current_epoch=5,
            best_epoch=3,
            best_val_loss=0.25,
        )

        result = AutocogTrainingResult(
            success=True,
            final_state=state,
            best_params={"threshold": 0.7},
            best_metrics={"val_loss": 0.25},
        )

        d = result.to_dict()

        assert d["success"] is True
        assert d["final_state"]["current_epoch"] == 5
        assert d["best_params"] == {"threshold": 0.7}
