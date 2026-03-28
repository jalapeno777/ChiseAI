"""Integration tests for GradientLearningOptimizer."""

import shutil
import tempfile

import pytest
from src.autonomous_cognition.gradient_learning import (
    ClipMode,
    GradientLearningOptimizer,
    ScheduleType,
    create_adam_optimizer,
    create_sgd_optimizer,
)


class TestGradientLearningOptimizer:
    """Integration tests for GradientLearningOptimizer."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Clean up temp files."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_basic_optimization_loop(self):
        """Test basic optimization with simple quadratic metric."""

        def calibration_error(params):
            # Minimize (x - 2)^2
            return (params["confidence_threshold"] - 2.0) ** 2

        params = {"confidence_threshold": 0.0}
        metric_fns = {"calibration_error": calibration_error}

        optimizer = GradientLearningOptimizer(
            params=params,
            metric_fns=metric_fns,
            optimizer_type="SGD",
            learning_rate=0.1,
            require_audit=False,  # Skip audit for testing
        )

        # Run optimization
        for _ in range(100):
            result = optimizer.step(rationale="Test optimization")

        # Should converge close to optimal value
        assert abs(optimizer.params["confidence_threshold"] - 2.0) < 0.1

    def test_constitution_audit_rejection(self):
        """Test that rejected audit prevents parameter update."""

        def always_reject(decision):
            return False

        params = {"threshold": 0.0}
        metric_fns = {"metric": lambda p: p["threshold"] ** 2}

        optimizer = GradientLearningOptimizer(
            params=params,
            metric_fns=metric_fns,
            constitution_audit_fn=always_reject,
            require_audit=True,
        )

        original_value = optimizer.params["threshold"]
        result = optimizer.step()

        # Update should be rejected
        assert result.rejected is True
        assert result.approved is False
        assert optimizer.params["threshold"] == original_value

    def test_constitution_audit_approval(self):
        """Test that approved audit allows parameter update."""

        def always_approve(decision):
            return True

        params = {"threshold": 0.0}
        metric_fns = {"metric": lambda p: p["threshold"] ** 2}

        optimizer = GradientLearningOptimizer(
            params=params,
            metric_fns=metric_fns,
            constitution_audit_fn=always_approve,
            require_audit=True,
        )

        result = optimizer.step()

        # Update should be approved
        assert result.approved is True
        assert result.rejected is False

    def test_checkpoint_save_and_load(self):
        """Test checkpointing functionality."""
        params = {"x": 0.0, "y": 0.0}
        metric_fns = {"mse": lambda p: p["x"] ** 2 + p["y"] ** 2}

        optimizer = GradientLearningOptimizer(
            params=params,
            metric_fns=metric_fns,
            checkpoint_dir=f"{self.temp_dir}/checkpoints",
            checkpoint_every=5,
            require_audit=False,
        )

        # Run a few steps
        for _ in range(10):
            optimizer.step()

        assert optimizer._step == 10

        # Save checkpoint manually
        checkpoint_id = optimizer.save_checkpoint()
        assert checkpoint_id.startswith("step_10_")

        # Modify state
        optimizer.params["x"] = 999.0

        # Load checkpoint
        optimizer.load_checkpoint(checkpoint_id)
        assert optimizer.params["x"] != 999.0
        assert optimizer._step == 10

    def test_rollback(self):
        """Test rollback to previous checkpoint."""
        params = {"x": 0.0}
        metric_fns = {"mse": lambda p: p["x"] ** 2}

        optimizer = GradientLearningOptimizer(
            params=params,
            metric_fns=metric_fns,
            checkpoint_dir=f"{self.temp_dir}/checkpoints",
            checkpoint_every=3,
            require_audit=False,
        )

        # Run steps to create checkpoints
        for _ in range(10):
            optimizer.step()

        original_x = optimizer.params["x"]

        # Rollback to step 6
        optimizer.rollback(target_step=6)
        assert optimizer._step == 6

    def test_gradient_clipping(self):
        """Test that large gradients are clipped."""
        params = {"x": 0.0}
        call_count = [0]

        def steep_metric(params):
            call_count[0] += 1
            # Very steep function - large gradients
            return params["x"] * 1000

        metric_fns = {"steep": steep_metric}

        optimizer = GradientLearningOptimizer(
            params=params,
            metric_fns=metric_fns,
            learning_rate=0.1,
            clip_mode=ClipMode.NORM,
            clip_max_norm=0.5,  # Strict norm limit
            require_audit=False,
        )

        result = optimizer.step()

        # Gradient should be clipped
        assert result.clipped_gradients["x"] != result.gradients["x"]
        # Norm should be at or below max
        import math

        clipped_norm = math.sqrt(sum(g**2 for g in result.clipped_gradients.values()))
        assert clipped_norm <= 0.5

    def test_learning_rate_scheduling(self):
        """Test that learning rate decays over time."""
        params = {"x": 0.0}
        metric_fns = {"mse": lambda p: p["x"] ** 2}

        optimizer = GradientLearningOptimizer(
            params=params,
            metric_fns=metric_fns,
            learning_rate=0.1,
            scheduler_type=ScheduleType.EXPONENTIAL,
            scheduler_config={"gamma": 0.9},
            require_audit=False,
        )

        initial_lr = optimizer.scheduler.get_lr()
        lrs = [optimizer.step().learning_rate for _ in range(10)]

        # Learning rate should decrease over time
        assert lrs[-1] < lrs[0]
        # After 10 steps (step 0-9), the last lr returned is for step 9
        assert lrs[-1] == pytest.approx(initial_lr * (0.9**9), rel=0.01)

    def test_factory_sgd_optimizer(self):
        """Test SGD factory function."""
        params = {"x": 1.0}
        metric_fns = {"mse": lambda p: p["x"] ** 2}

        optimizer = create_sgd_optimizer(
            params=params,
            metric_fns=metric_fns,
            learning_rate=0.01,
            constitution_audit_fn=lambda d: True,
        )

        assert optimizer.optimizer.learning_rate == 0.01
        result = optimizer.step()
        assert result.approved

    def test_factory_adam_optimizer(self):
        """Test Adam factory function."""
        params = {"x": 1.0}
        metric_fns = {"mse": lambda p: p["x"] ** 2}

        optimizer = create_adam_optimizer(
            params=params,
            metric_fns=metric_fns,
            learning_rate=0.001,
            constitution_audit_fn=lambda d: True,
        )

        assert optimizer.optimizer.learning_rate == 0.001
        result = optimizer.step()
        assert result.approved

    def test_multiple_metrics(self):
        """Test optimization with multiple metrics."""
        params = {"x": 0.0, "y": 0.0}

        def metric_a(params):
            return (params["x"] - 1.0) ** 2

        def metric_b(params):
            return (params["y"] + 1.0) ** 2

        metric_fns = {"metric_a": metric_a, "metric_b": metric_b}

        optimizer = GradientLearningOptimizer(
            params=params,
            metric_fns=metric_fns,
            learning_rate=0.1,
            require_audit=False,
        )

        for _ in range(100):
            optimizer.step()

        # Should converge towards x=1, y=-1
        assert abs(optimizer.params["x"] - 1.0) < 0.2
        assert abs(optimizer.params["y"] + 1.0) < 0.2

    def test_get_state(self):
        """Test getting full optimizer state."""
        params = {"x": 1.0}
        metric_fns = {"mse": lambda p: p["x"] ** 2}

        optimizer = GradientLearningOptimizer(
            params=params,
            metric_fns=metric_fns,
            require_audit=False,
        )

        optimizer.step()
        state = optimizer.get_state()

        assert "step" in state
        assert "params" in state
        assert "optimizer" in state
        assert "scheduler" in state
        assert "clipper" in state
