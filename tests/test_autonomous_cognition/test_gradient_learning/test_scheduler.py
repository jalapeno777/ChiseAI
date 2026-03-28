"""Unit tests for LearningRateScheduler."""

import math
import pytest
from src.autonomous_cognition.gradient_learning.scheduler import (
    LearningRateScheduler,
    ExponentialScheduler,
    StepScheduler,
    CosineScheduler,
    ConstantScheduler,
    ScheduleType,
    create_scheduler,
)


class TestExponentialScheduler:
    """Tests for ExponentialScheduler."""

    def test_initial_lr(self):
        """Test initial learning rate."""
        scheduler = ExponentialScheduler(initial_lr=0.1, gamma=0.95)
        assert scheduler.get_lr() == 0.1

    def test_exponential_decay(self):
        """Test exponential decay over steps."""
        scheduler = ExponentialScheduler(initial_lr=1.0, gamma=0.5)
        # Step 0: 1.0 * 0.5^0 = 1.0
        assert scheduler.step() == pytest.approx(1.0)
        # Step 1: 1.0 * 0.5^1 = 0.5
        assert scheduler.step() == pytest.approx(0.5)
        # Step 2: 1.0 * 0.5^2 = 0.25
        assert scheduler.step() == pytest.approx(0.25)

    def test_invalid_gamma_raises(self):
        """Test that invalid gamma raises ValueError."""
        with pytest.raises(ValueError):
            ExponentialScheduler(initial_lr=0.1, gamma=1.5)
        with pytest.raises(ValueError):
            ExponentialScheduler(initial_lr=0.1, gamma=0.0)

    def test_state_persistence(self):
        """Test scheduler state save/load."""
        scheduler = ExponentialScheduler(initial_lr=0.1, gamma=0.9)
        scheduler.step()
        scheduler.step()

        state = scheduler.get_state()
        new_scheduler = ExponentialScheduler(initial_lr=0.1, gamma=0.9)
        new_scheduler.load_state(state)

        assert new_scheduler._step == scheduler._step


class TestStepScheduler:
    """Tests for StepScheduler."""

    def test_no_decay_before_step_size(self):
        """Test no decay before step_size."""
        scheduler = StepScheduler(initial_lr=1.0, step_size=10, gamma=0.5)
        for _ in range(9):
            assert scheduler.step() == pytest.approx(1.0)

    def test_decay_at_step_size(self):
        """Test decay at step_size boundary."""
        scheduler = StepScheduler(initial_lr=1.0, step_size=5, gamma=0.5)
        for _ in range(5):
            scheduler.step()
        # After step 5: gamma^1 = 0.5
        assert scheduler.step() == pytest.approx(0.5)

    def test_multiple_decays(self):
        """Test multiple decay events."""
        scheduler = StepScheduler(initial_lr=1.0, step_size=3, gamma=0.1)
        steps = [scheduler.step() for _ in range(10)]
        # Steps 0-2: 1.0, Step 3-5: 0.1, Step 6-8: 0.01, Step 9: 0.001
        assert steps[2] == pytest.approx(1.0)
        assert steps[5] == pytest.approx(0.1)
        assert steps[8] == pytest.approx(0.01)

    def test_invalid_step_size_raises(self):
        """Test that invalid step_size raises ValueError."""
        with pytest.raises(ValueError):
            StepScheduler(initial_lr=0.1, step_size=0)


class TestCosineScheduler:
    """Tests for CosineScheduler."""

    def test_cosine_annealing(self):
        """Test cosine annealing schedule."""
        scheduler = CosineScheduler(initial_lr=0.1, T_max=10, eta_min=0.0)
        # At step 0: lr = 0.1 * (1 + cos(0)) / 2 = 0.1
        assert scheduler.step() == pytest.approx(0.1)
        # At step 5: lr = 0.1 * (1 + cos(pi/2)) / 2 = 0.05
        for _ in range(4):
            scheduler.step()
        assert scheduler.step() == pytest.approx(0.05, abs=0.01)
        # At step 10: lr = eta_min = 0.0 (minimum)
        for _ in range(5):
            scheduler.step()
        assert scheduler.step() == pytest.approx(0.0, abs=0.01)

    def test_cosine_with_warmup(self):
        """Test cosine with eta_min > 0."""
        scheduler = CosineScheduler(initial_lr=0.1, T_max=10, eta_min=0.01)
        lr0 = scheduler.get_lr()
        assert lr0 >= 0.01

    def test_cosine_beyond_T_max(self):
        """Test cosine scheduler stays at eta_min after T_max."""
        scheduler = CosineScheduler(initial_lr=0.1, T_max=5, eta_min=0.0)
        for _ in range(10):
            scheduler.step()
        assert scheduler.get_lr() == pytest.approx(0.0)


class TestConstantScheduler:
    """Tests for ConstantScheduler."""

    def test_always_returns_initial_lr(self):
        """Test constant scheduler returns initial_lr."""
        scheduler = ConstantScheduler(initial_lr=0.05)
        for _ in range(100):
            assert scheduler.step() == pytest.approx(0.05)


class TestCreateScheduler:
    """Tests for create_scheduler factory function."""

    def test_create_exponential(self):
        """Test creating exponential scheduler."""
        scheduler = create_scheduler(ScheduleType.EXPONENTIAL, 0.1, gamma=0.9)
        assert isinstance(scheduler, ExponentialScheduler)
        assert scheduler.gamma == 0.9

    def test_create_step(self):
        """Test creating step scheduler."""
        scheduler = create_scheduler(ScheduleType.STEP, 0.1, step_size=5, gamma=0.5)
        assert isinstance(scheduler, StepScheduler)
        assert scheduler.step_size == 5
        assert scheduler.gamma == 0.5

    def test_create_cosine(self):
        """Test creating cosine scheduler."""
        scheduler = create_scheduler(ScheduleType.COSINE, 0.1, T_max=100)
        assert isinstance(scheduler, CosineScheduler)
        assert scheduler.T_max == 100

    def test_create_constant(self):
        """Test creating constant scheduler."""
        scheduler = create_scheduler(ScheduleType.CONSTANT, 0.1)
        assert isinstance(scheduler, ConstantScheduler)

    def test_unknown_type_raises(self):
        """Test that unknown schedule type raises ValueError."""
        with pytest.raises(ValueError):
            create_scheduler("unknown", 0.1)
