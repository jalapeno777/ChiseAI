"""Learning rate schedulers for gradient optimization.

This module provides various learning rate decay schedules.
"""

from __future__ import annotations

import logging
import math
from enum import Enum

logger = logging.getLogger(__name__)


class ScheduleType(str, Enum):
    """Supported learning rate schedule types."""

    EXPONENTIAL = "exponential"
    STEP = "step"
    COSINE = "cosine"
    CONSTANT = "constant"


class LearningRateScheduler:
    """Base class for learning rate schedulers."""

    def __init__(self, initial_lr: float):
        """Initialize scheduler.

        Args:
            initial_lr: Initial learning rate
        """
        self.initial_lr = initial_lr
        self._step = 0

    def step(self) -> float:
        """Get learning rate for current step and advance.

        Returns:
            Learning rate for current step
        """
        raise NotImplementedError("Subclasses must implement step()")

    def get_lr(self) -> float:
        """Get current learning rate without advancing step.

        Returns:
            Current learning rate
        """
        raise NotImplementedError("Subclasses must implement get_lr()")

    def reset(self) -> None:
        """Reset scheduler to initial state."""
        self._step = 0


class ExponentialScheduler(LearningRateScheduler):
    """Exponential decay learning rate scheduler.

    lr = initial_lr * gamma^step

    Attributes:
        gamma: Decay factor (0 < gamma < 1)
    """

    def __init__(self, initial_lr: float, gamma: float = 0.95):
        """Initialize exponential scheduler.

        Args:
            initial_lr: Initial learning rate
            gamma: Decay factor in (0, 1), default 0.95
        """
        super().__init__(initial_lr)
        if not 0 < gamma <= 1:
            raise ValueError("gamma must be in (0, 1]")
        self.gamma = gamma

    def step(self) -> float:
        """Get learning rate and advance step."""
        lr = self.get_lr()
        self._step += 1
        return lr

    def get_lr(self) -> float:
        """Get current learning rate."""
        return self.initial_lr * (self.gamma**self._step)

    def get_state(self) -> dict:
        """Get scheduler state."""
        return {"type": "ExponentialScheduler", "step": self._step, "gamma": self.gamma}

    def load_state(self, state: dict) -> None:
        """Load scheduler state."""
        self._step = state["step"]
        self.gamma = state["gamma"]


class StepScheduler(LearningRateScheduler):
    """Step decay learning rate scheduler.

    lr = initial_lr * gamma^(floor(step / step_size))

    Attributes:
        step_size: Number of steps between decay
        gamma: Decay factor
    """

    def __init__(self, initial_lr: float, step_size: int, gamma: float = 0.1):
        """Initialize step scheduler.

        Args:
            initial_lr: Initial learning rate
            step_size: Number of steps between decay
            gamma: Decay factor (default: 0.1)
        """
        super().__init__(initial_lr)
        if step_size <= 0:
            raise ValueError("step_size must be positive")
        if not 0 < gamma <= 1:
            raise ValueError("gamma must be in (0, 1]")
        self.step_size = step_size
        self.gamma = gamma

    def step(self) -> float:
        """Get learning rate and advance step."""
        lr = self.get_lr()
        self._step += 1
        return lr

    def get_lr(self) -> float:
        """Get current learning rate."""
        decay_factor = self.gamma ** (self._step // self.step_size)
        return self.initial_lr * decay_factor

    def get_state(self) -> dict:
        """Get scheduler state."""
        return {
            "type": "StepScheduler",
            "step": self._step,
            "step_size": self.step_size,
            "gamma": self.gamma,
        }

    def load_state(self, state: dict) -> None:
        """Load scheduler state."""
        self._step = state["step"]
        self.step_size = state["step_size"]
        self.gamma = state["gamma"]


class CosineScheduler(LearningRateScheduler):
    """Cosine annealing learning rate scheduler.

    lr = initial_lr * (1 + cos(pi * step / T_max)) / 2

    Where T_max is the total number of steps.

    Attributes:
        T_max: Maximum number of steps
        eta_min: Minimum learning rate (default: 0)
    """

    def __init__(self, initial_lr: float, T_max: int, eta_min: float = 0.0):
        """Initialize cosine scheduler.

        Args:
            initial_lr: Initial learning rate
            T_max: Maximum number of steps
            eta_min: Minimum learning rate (default: 0)
        """
        super().__init__(initial_lr)
        if T_max <= 0:
            raise ValueError("T_max must be positive")
        self.T_max = T_max
        self.eta_min = eta_min

    def step(self) -> float:
        """Get learning rate and advance step."""
        lr = self.get_lr()
        self._step += 1
        return lr

    def get_lr(self) -> float:
        """Get current learning rate."""
        if self._step >= self.T_max:
            # After T_max, stay at eta_min
            return self.eta_min
        return (
            self.eta_min
            + (self.initial_lr - self.eta_min)
            * (1 + math.cos(math.pi * self._step / self.T_max))
            / 2
        )

    def get_state(self) -> dict:
        """Get scheduler state."""
        return {
            "type": "CosineScheduler",
            "step": self._step,
            "T_max": self.T_max,
            "eta_min": self.eta_min,
        }

    def load_state(self, state: dict) -> None:
        """Load scheduler state."""
        self._step = state["step"]
        self.T_max = state["T_max"]
        self.eta_min = state["eta_min"]


class ConstantScheduler(LearningRateScheduler):
    """Constant learning rate scheduler (no decay)."""

    def step(self) -> float:
        """Get learning rate and advance step."""
        self._step += 1
        return self.initial_lr

    def get_lr(self) -> float:
        """Get current learning rate."""
        return self.initial_lr

    def get_state(self) -> dict:
        """Get scheduler state."""
        return {"type": "ConstantScheduler", "step": self._step}

    def load_state(self, state: dict) -> None:
        """Load scheduler state."""
        self._step = state["step"]


def create_scheduler(
    schedule_type: ScheduleType,
    initial_lr: float,
    **kwargs,
) -> LearningRateScheduler:
    """Factory function to create a learning rate scheduler.

    Args:
        schedule_type: Type of schedule to create
        initial_lr: Initial learning rate
        **kwargs: Additional arguments for specific scheduler types

    Returns:
        Configured LearningRateScheduler instance

    Raises:
        ValueError: If schedule_type is not supported or arguments are invalid
    """
    if schedule_type == ScheduleType.EXPONENTIAL:
        gamma = kwargs.get("gamma", 0.95)
        return ExponentialScheduler(initial_lr, gamma)
    elif schedule_type == ScheduleType.STEP:
        step_size = kwargs.get("step_size", 10)
        gamma = kwargs.get("gamma", 0.1)
        return StepScheduler(initial_lr, step_size, gamma)
    elif schedule_type == ScheduleType.COSINE:
        T_max = kwargs.get("T_max", 100)
        eta_min = kwargs.get("eta_min", 0.0)
        return CosineScheduler(initial_lr, T_max, eta_min)
    elif schedule_type == ScheduleType.CONSTANT:
        return ConstantScheduler(initial_lr)
    else:
        raise ValueError(f"Unknown schedule type: {schedule_type}")
