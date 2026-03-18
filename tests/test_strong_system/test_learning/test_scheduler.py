"""Tests for scheduler module."""

import pytest
from src.strong_system.learning import (
    ConstantLR,
    CosineAnnealingLR,
    CyclicalLR,
    ExponentialLR,
    LRScheduler,
    MetaLearningScheduler,
    ReduceLROnPlateau,
    SchedulerConfig,
    SchedulerState,
    StepLR,
    WarmupScheduler,
    create_scheduler,
)


class TestSchedulerConfig:
    """Tests for SchedulerConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = SchedulerConfig()
        assert config.initial_lr == 0.001
        assert config.min_lr == 1e-7
        assert config.warmup_steps == 0

    def test_custom_config(self):
        """Test custom configuration."""
        config = SchedulerConfig(
            initial_lr=0.01,
            min_lr=1e-6,
            warmup_steps=100,
        )
        assert config.initial_lr == 0.01
        assert config.min_lr == 1e-6
        assert config.warmup_steps == 100


class TestSchedulerState:
    """Tests for SchedulerState."""

    def test_default_state(self):
        """Test default state values."""
        state = SchedulerState()
        assert state.current_lr == 0.001
        assert state.step_count == 0
        assert state.best_loss == float("inf")

    def test_state_to_dict(self):
        """Test converting state to dictionary."""
        state = SchedulerState(
            current_lr=0.01,
            step_count=100,
            best_loss=0.5,
        )
        d = state.to_dict()
        assert d["current_lr"] == 0.01
        assert d["step_count"] == 100
        assert d["best_loss"] == 0.5


class TestLRScheduler:
    """Tests for LRScheduler base class."""

    def test_initialization(self):
        """Test scheduler initialization."""
        scheduler = LRScheduler(initial_lr=0.01, min_lr=1e-6)
        assert scheduler.initial_lr == 0.01
        assert scheduler.current_lr == 0.01
        assert scheduler.min_lr == 1e-6

    def test_get_lr(self):
        """Test getting current learning rate."""
        scheduler = LRScheduler(initial_lr=0.01)
        assert scheduler.get_lr() == 0.01

    def test_reset(self):
        """Test resetting scheduler."""
        scheduler = LRScheduler(initial_lr=0.01)
        scheduler.step()
        scheduler.step()
        assert scheduler.step_count == 2

        scheduler.reset()
        assert scheduler.step_count == 0
        assert scheduler.current_lr == 0.01

    def test_warmup(self):
        """Test warmup functionality."""
        scheduler = LRScheduler(
            initial_lr=0.01,
            warmup_steps=10,
            warmup_init_lr=0.001,
        )

        # First step should be at warmup init
        lr = scheduler.step()
        assert lr > 0.001  # Should be between init and target
        assert lr < 0.01

        # After warmup, should be at initial_lr
        for _ in range(10):
            lr = scheduler.step()
        assert lr == pytest.approx(0.01, abs=1e-6)

    def test_min_lr_enforcement(self):
        """Test that minimum learning rate is enforced."""
        scheduler = LRScheduler(initial_lr=0.01, min_lr=0.005)
        # Manually set below min
        scheduler.current_lr = 0.001
        lr = scheduler.step()
        assert lr >= 0.005


class TestConstantLR:
    """Tests for ConstantLR scheduler."""

    def test_constant_lr(self):
        """Test that learning rate remains constant."""
        scheduler = ConstantLR(initial_lr=0.01)

        for _ in range(10):
            lr = scheduler.step()
            assert lr == 0.01

    def test_with_warmup(self):
        """Test constant LR with warmup."""
        scheduler = ConstantLR(
            initial_lr=0.01,
            warmup_steps=5,
            warmup_init_lr=0.001,
        )

        # During warmup
        lr = scheduler.step()
        assert lr > 0.001
        assert lr < 0.01

        # After warmup
        for _ in range(5):
            lr = scheduler.step()
        assert lr == 0.01


class TestStepLR:
    """Tests for StepLR scheduler."""

    def test_step_decay(self):
        """Test step decay functionality."""
        scheduler = StepLR(initial_lr=0.1, step_size=3, gamma=0.1)

        # First 3 steps at initial LR
        for _ in range(3):
            lr = scheduler.step()
        assert lr == pytest.approx(0.1, abs=1e-6)

        # After step_size steps, should decay
        lr = scheduler.step()
        assert lr == pytest.approx(0.01, abs=1e-6)  # 0.1 * 0.1

        # After another step_size steps
        for _ in range(3):
            lr = scheduler.step()
        assert lr == pytest.approx(0.001, abs=1e-6)  # 0.01 * 0.1

    def test_with_warmup(self):
        """Test step LR with warmup."""
        scheduler = StepLR(
            initial_lr=0.1,
            step_size=5,
            gamma=0.5,
            warmup_steps=3,
        )

        # During warmup
        for _ in range(3):
            lr = scheduler.step()

        # After warmup, should decay after step_size effective steps
        for _ in range(5):
            lr = scheduler.step()
        assert lr == pytest.approx(0.1, abs=1e-6)

        lr = scheduler.step()
        assert lr == pytest.approx(0.05, abs=1e-6)


class TestExponentialLR:
    """Tests for ExponentialLR scheduler."""

    def test_exponential_decay(self):
        """Test exponential decay."""
        scheduler = ExponentialLR(initial_lr=0.1, gamma=0.9)

        lr = scheduler.step()
        assert lr == pytest.approx(0.09, abs=1e-6)  # 0.1 * 0.9

        lr = scheduler.step()
        assert lr == pytest.approx(0.081, abs=1e-6)  # 0.09 * 0.9

    def test_decay_over_multiple_steps(self):
        """Test decay over many steps."""
        scheduler = ExponentialLR(initial_lr=0.1, gamma=0.95)

        for _ in range(10):
            lr = scheduler.step()

        expected = 0.1 * (0.95**10)
        assert lr == pytest.approx(expected, abs=1e-6)


class TestCosineAnnealingLR:
    """Tests for CosineAnnealingLR scheduler."""

    def test_cosine_decay(self):
        """Test cosine annealing decay."""
        scheduler = CosineAnnealingLR(initial_lr=0.1, T_max=10, eta_min=0.01)

        # At start, should be near initial_lr
        lr = scheduler.step()
        assert lr > 0.09  # Close to initial

        # At T_max, should be at eta_min
        for _ in range(9):
            lr = scheduler.step()
        assert lr == pytest.approx(0.01, abs=1e-6)

    def test_cosine_shape(self):
        """Test that LR follows cosine shape."""
        scheduler = CosineAnnealingLR(initial_lr=0.1, T_max=4, eta_min=0.0)

        lrs = [scheduler.step() for _ in range(5)]

        # Should decrease monotonically
        for i in range(len(lrs) - 1):
            assert lrs[i] >= lrs[i + 1]

        # Final should be near eta_min
        assert lrs[-1] < 0.02


class TestReduceLROnPlateau:
    """Tests for ReduceLROnPlateau scheduler."""

    def test_no_reduction_when_improving(self):
        """Test that LR doesn't reduce when loss is improving."""
        scheduler = ReduceLROnPlateau(initial_lr=0.1, patience=3)

        # Improving losses
        losses = [1.0, 0.9, 0.8, 0.7, 0.6]
        for loss in losses:
            lr = scheduler.step(loss)

        assert lr == 0.1  # Should not reduce

    def test_reduction_on_plateau(self):
        """Test LR reduction when loss plateaus."""
        scheduler = ReduceLROnPlateau(initial_lr=0.1, patience=2, factor=0.5)

        # Plateau losses
        losses = [1.0, 1.0, 1.0, 1.0]
        for loss in losses:
            lr = scheduler.step(loss)

        # After patience + 1 steps on plateau, should reduce
        assert lr < 0.1

    def test_cooldown(self):
        """Test cooldown after reduction."""
        scheduler = ReduceLROnPlateau(
            initial_lr=0.1, patience=1, factor=0.5, cooldown=2
        )

        # Trigger reduction
        scheduler.step(1.0)
        scheduler.step(1.0)
        scheduler.step(1.0)

        lr_after_reduction = scheduler.current_lr

        # During cooldown, LR should not change
        for _ in range(2):
            lr = scheduler.step(1.0)
            assert lr == lr_after_reduction

    def test_reset(self):
        """Test resetting plateau scheduler."""
        scheduler = ReduceLROnPlateau(initial_lr=0.1, patience=2)

        # Trigger plateau
        for _ in range(5):
            scheduler.step(1.0)

        assert scheduler.current_lr < 0.1

        scheduler.reset()
        assert scheduler.current_lr == 0.1
        assert scheduler.best_loss == float("inf")
        assert scheduler.num_bad_steps == 0


class TestCyclicalLR:
    """Tests for CyclicalLR scheduler."""

    def test_triangular_mode(self):
        """Test triangular cyclical mode."""
        scheduler = CyclicalLR(base_lr=0.01, max_lr=0.1, step_size=5, mode="triangular")

        # First half cycle: increasing
        lrs_increasing = [scheduler.step() for _ in range(5)]
        assert lrs_increasing[0] == 0.01
        assert lrs_increasing[-1] == pytest.approx(0.1, abs=1e-6)

        # Second half cycle: decreasing
        lrs_decreasing = [scheduler.step() for _ in range(5)]
        assert lrs_decreasing[-1] == pytest.approx(0.01, abs=1e-6)

    def test_triangular2_mode(self):
        """Test triangular2 cyclical mode."""
        scheduler = CyclicalLR(
            base_lr=0.01, max_lr=0.1, step_size=5, mode="triangular2"
        )

        # First cycle - track the maximum LR
        max_lr_cycle1 = 0.01
        for _ in range(10):
            lr1 = scheduler.step()
            max_lr_cycle1 = max(max_lr_cycle1, lr1)

        # Second cycle should have half the amplitude
        max_lr_cycle2 = 0.01
        for _ in range(10):
            lr2 = scheduler.step()
            max_lr_cycle2 = max(max_lr_cycle2, lr2)

        # The peak of cycle 2 should be less than the peak of cycle 1
        assert max_lr_cycle2 < max_lr_cycle1
        # Cycle 1 peak should be 0.1, cycle 2 peak should be ~0.055
        assert max_lr_cycle1 == pytest.approx(0.1, abs=1e-6)
        assert max_lr_cycle2 == pytest.approx(0.055, abs=1e-6)


class TestWarmupScheduler:
    """Tests for WarmupScheduler."""

    def test_warmup_then_base(self):
        """Test warmup followed by base scheduler."""
        base_scheduler = StepLR(initial_lr=0.1, step_size=5, gamma=0.5)
        scheduler = WarmupScheduler(
            base_scheduler=base_scheduler,
            warmup_steps=3,
            warmup_init_lr=0.01,
        )

        # During warmup
        lr = scheduler.step()
        assert lr > 0.01
        assert lr < 0.1

        # Finish warmup
        for _ in range(2):
            lr = scheduler.step()

        # Should now use base scheduler
        for _ in range(5):
            lr = scheduler.step()
        assert lr == pytest.approx(0.1, abs=1e-6)


class TestMetaLearningScheduler:
    """Tests for MetaLearningScheduler."""

    def test_initialization(self):
        """Test meta-learning scheduler initialization."""
        base_scheduler = ConstantLR(initial_lr=0.01)
        scheduler = MetaLearningScheduler(base_scheduler)

        assert scheduler.base_scheduler == base_scheduler
        assert scheduler.adaptation_rate == 0.1

    def test_step_delegation(self):
        """Test that step delegates to base scheduler."""
        base_scheduler = ConstantLR(initial_lr=0.01)
        scheduler = MetaLearningScheduler(base_scheduler)

        lr = scheduler.step()
        assert lr == 0.01

    def test_get_lr_delegation(self):
        """Test that get_lr delegates to base scheduler."""
        base_scheduler = ConstantLR(initial_lr=0.01)
        scheduler = MetaLearningScheduler(base_scheduler)

        assert scheduler.get_lr() == 0.01


class TestCreateScheduler:
    """Tests for create_scheduler factory function."""

    def test_create_constant_scheduler(self):
        """Test creating constant scheduler."""
        scheduler = create_scheduler("constant", initial_lr=0.01)
        assert isinstance(scheduler, ConstantLR)
        assert scheduler.initial_lr == 0.01

    def test_create_step_scheduler(self):
        """Test creating step scheduler."""
        scheduler = create_scheduler("step", initial_lr=0.01, step_size=10, gamma=0.5)
        assert isinstance(scheduler, StepLR)
        assert scheduler.step_size == 10
        assert scheduler.gamma == 0.5

    def test_create_exponential_scheduler(self):
        """Test creating exponential scheduler."""
        scheduler = create_scheduler("exponential", initial_lr=0.01, gamma=0.9)
        assert isinstance(scheduler, ExponentialLR)
        assert scheduler.gamma == 0.9

    def test_create_cosine_scheduler(self):
        """Test creating cosine scheduler."""
        scheduler = create_scheduler("cosine", initial_lr=0.01, T_max=100)
        assert isinstance(scheduler, CosineAnnealingLR)
        assert scheduler.T_max == 100

    def test_create_plateau_scheduler(self):
        """Test creating plateau scheduler."""
        scheduler = create_scheduler("plateau", initial_lr=0.01, patience=5)
        assert isinstance(scheduler, ReduceLROnPlateau)
        assert scheduler.patience == 5

    def test_create_cyclical_scheduler(self):
        """Test creating cyclical scheduler."""
        scheduler = create_scheduler("cyclical", initial_lr=0.01, max_lr=0.1)
        assert isinstance(scheduler, CyclicalLR)
        assert scheduler.max_lr == 0.1

    def test_create_unknown_scheduler(self):
        """Test creating unknown scheduler raises error."""
        with pytest.raises(ValueError, match="Unknown scheduler type"):
            create_scheduler("unknown")


class TestSchedulerIntegration:
    """Integration tests for schedulers."""

    def test_scheduler_state_persistence(self):
        """Test that scheduler state can be saved and restored."""
        scheduler = StepLR(initial_lr=0.1, step_size=5, gamma=0.5)

        # Run some steps
        for _ in range(10):
            scheduler.step()

        # Get state
        state = scheduler.get_state()

        # Create new scheduler and restore state
        new_scheduler = StepLR(initial_lr=0.1, step_size=5, gamma=0.5)
        new_scheduler.set_state(state)

        assert new_scheduler.step_count == scheduler.step_count
        assert new_scheduler.current_lr == scheduler.current_lr

    def test_training_simulation(self):
        """Simulate a training run with scheduler."""
        scheduler = ReduceLROnPlateau(initial_lr=0.1, patience=3, factor=0.5)

        # Simulate training with plateau
        lrs = []
        losses = [1.0, 0.9, 0.85, 0.82, 0.81, 0.81, 0.81, 0.81]

        for loss in losses:
            lr = scheduler.step(loss)
            lrs.append(lr)

        # LR should eventually reduce
        assert lrs[-1] < lrs[0]

    def test_all_schedulers_decrease_lr(self):
        """Test that all schedulers eventually decrease LR."""
        schedulers = [
            StepLR(initial_lr=0.1, step_size=5, gamma=0.5),
            ExponentialLR(initial_lr=0.1, gamma=0.9),
            CosineAnnealingLR(initial_lr=0.1, T_max=10),
        ]

        for scheduler in schedulers:
            initial_lr = scheduler.get_lr()

            # Run for many steps
            for _ in range(20):
                lr = scheduler.step()

            assert lr < initial_lr, f"{type(scheduler).__name__} did not decrease LR"
