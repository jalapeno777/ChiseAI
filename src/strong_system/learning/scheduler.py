"""Learning rate scheduling for belief-based learning.

Provides various learning rate schedulers including StepLR, ExponentialLR,
ReduceLROnPlateau, and warmup support. Integrates with meta_learning patterns
from the existing controller module.

Example:
    >>> from src.strong_system.learning import LRScheduler, StepLR
    >>> import numpy as np
    >>>
    >>> # Create scheduler
    >>> scheduler = StepLR(initial_lr=0.01, step_size=30, gamma=0.1)
    >>>
    >>> # Training loop
    >>> for epoch in range(100):
    ...     lr = scheduler.get_lr()
    ...     # ... training code ...
    ...     scheduler.step()
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from src.strong_system.meta_learning.controller import MetaLearningController


class SchedulerType(Enum):
    """Type of learning rate scheduler."""

    CONSTANT = auto()
    STEP = auto()
    EXPONENTIAL = auto()
    COSINE = auto()
    REDUCE_ON_PLATEAU = auto()
    CYCLICAL = auto()
    WARMUP = auto()


@dataclass
class SchedulerConfig:
    """Configuration for learning rate scheduler.

    Attributes:
        scheduler_type: Type of scheduler
        initial_lr: Initial learning rate
        min_lr: Minimum learning rate
        warmup_steps: Number of warmup steps
        warmup_init_lr: Initial learning rate for warmup
    """

    scheduler_type: SchedulerType = SchedulerType.CONSTANT
    initial_lr: float = 0.001
    min_lr: float = 1e-7
    warmup_steps: int = 0
    warmup_init_lr: float = 1e-5


@dataclass
class SchedulerState:
    """State of a learning rate scheduler.

    Attributes:
        current_lr: Current learning rate
        step_count: Number of steps taken
        epoch_count: Number of epochs completed
        best_loss: Best loss seen (for plateau detection)
        patience_counter: Counter for patience
    """

    current_lr: float = 0.001
    step_count: int = 0
    epoch_count: int = 0
    best_loss: float = float("inf")
    patience_counter: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert state to dictionary."""
        return {
            "current_lr": self.current_lr,
            "step_count": self.step_count,
            "epoch_count": self.epoch_count,
            "best_loss": self.best_loss,
            "patience_counter": self.patience_counter,
        }


class LRScheduler:
    """Base class for learning rate schedulers.

    Provides common functionality for all schedulers including:
    - Step counting
    - Learning rate bounds
    - State management
    - Warmup support

    Attributes:
        initial_lr: Initial learning rate
        current_lr: Current learning rate
        min_lr: Minimum learning rate
        step_count: Number of steps taken
        warmup_steps: Number of warmup steps
    """

    def __init__(
        self,
        initial_lr: float = 0.001,
        min_lr: float = 1e-7,
        warmup_steps: int = 0,
        warmup_init_lr: float = 1e-5,
    ):
        """Initialize the scheduler.

        Args:
            initial_lr: Initial learning rate
            min_lr: Minimum learning rate
            warmup_steps: Number of warmup steps
            warmup_init_lr: Initial learning rate for warmup
        """
        self.initial_lr = initial_lr
        self.current_lr = initial_lr
        self.min_lr = min_lr
        self.warmup_steps = warmup_steps
        self.warmup_init_lr = warmup_init_lr
        self.step_count = 0
        self._state = SchedulerState(
            current_lr=initial_lr,
        )

    def step(self, loss: float | None = None) -> float:
        """Advance one step and return the new learning rate.

        Args:
            loss: Optional loss value (used by some schedulers)

        Returns:
            Current learning rate
        """
        self.step_count += 1

        # Handle warmup
        if self.step_count <= self.warmup_steps:
            self.current_lr = self._compute_warmup_lr()
        else:
            self.current_lr = self._compute_lr(loss)

        # Enforce minimum
        self.current_lr = max(self.current_lr, self.min_lr)

        # Update state
        self._state.current_lr = self.current_lr
        self._state.step_count = self.step_count

        return self.current_lr

    def get_lr(self) -> float:
        """Get current learning rate without stepping."""
        return self.current_lr

    def get_state(self) -> SchedulerState:
        """Get current scheduler state."""
        return self._state

    def set_state(self, state: SchedulerState) -> None:
        """Set scheduler state."""
        self._state = state
        self.current_lr = state.current_lr
        self.step_count = state.step_count

    def reset(self) -> None:
        """Reset scheduler to initial state."""
        self.current_lr = self.initial_lr
        self.step_count = 0
        self._state = SchedulerState(current_lr=self.initial_lr)

    def _compute_lr(self, loss: float | None = None) -> float:
        """Compute learning rate (to be implemented by subclasses)."""
        # Base class returns constant learning rate
        return self.initial_lr

    def _compute_warmup_lr(self) -> float:
        """Compute warmup learning rate."""
        if self.warmup_steps == 0:
            return self.initial_lr

        progress = self.step_count / self.warmup_steps
        return self.warmup_init_lr + (self.initial_lr - self.warmup_init_lr) * progress


class ConstantLR(LRScheduler):
    """Constant learning rate scheduler.

    Maintains a constant learning rate throughout training.
    """

    def __init__(
        self,
        initial_lr: float = 0.001,
        min_lr: float = 1e-7,
        warmup_steps: int = 0,
        warmup_init_lr: float = 1e-5,
    ):
        """Initialize constant scheduler."""
        super().__init__(initial_lr, min_lr, warmup_steps, warmup_init_lr)

    def _compute_lr(self, loss: float | None = None) -> float:
        """Return constant learning rate."""
        return self.initial_lr


class StepLR(LRScheduler):
    """Step learning rate scheduler.

    Decays learning rate by gamma every step_size steps.

    Attributes:
        step_size: Number of steps between decays
        gamma: Decay factor
    """

    def __init__(
        self,
        initial_lr: float = 0.001,
        step_size: int = 30,
        gamma: float = 0.1,
        min_lr: float = 1e-7,
        warmup_steps: int = 0,
        warmup_init_lr: float = 1e-5,
    ):
        """Initialize step scheduler.

        Args:
            initial_lr: Initial learning rate
            step_size: Steps between decays
            gamma: Decay factor
            min_lr: Minimum learning rate
            warmup_steps: Warmup steps
            warmup_init_lr: Warmup initial learning rate
        """
        super().__init__(initial_lr, min_lr, warmup_steps, warmup_init_lr)
        self.step_size = step_size
        self.gamma = gamma

    def _compute_lr(self, loss: float | None = None) -> float:
        """Compute step-decayed learning rate."""
        # Adjust for warmup - effective step starts after warmup
        # step_count has already been incremented in step() before this is called
        # So we use effective_step = step_count - warmup_steps - 1 for 0-indexed
        if self.step_count <= self.warmup_steps:
            # Still in warmup, return initial_lr (warmup handles the ramp)
            return self.initial_lr

        # After warmup, compute decay based on steps taken after warmup
        # effective_step is 0-indexed
        effective_step = self.step_count - self.warmup_steps - 1
        # Decay happens after every step_size steps
        # Steps 0-2 (3 steps) at initial LR, step 3+ at decayed LR for step_size=3
        decay_count = effective_step // self.step_size
        return self.initial_lr * (self.gamma**decay_count)


class ExponentialLR(LRScheduler):
    """Exponential learning rate scheduler.

    Decays learning rate exponentially.

    Attributes:
        gamma: Exponential decay factor
    """

    def __init__(
        self,
        initial_lr: float = 0.001,
        gamma: float = 0.95,
        min_lr: float = 1e-7,
        warmup_steps: int = 0,
        warmup_init_lr: float = 1e-5,
    ):
        """Initialize exponential scheduler.

        Args:
            initial_lr: Initial learning rate
            gamma: Decay factor (per step)
            min_lr: Minimum learning rate
            warmup_steps: Warmup steps
            warmup_init_lr: Warmup initial learning rate
        """
        super().__init__(initial_lr, min_lr, warmup_steps, warmup_init_lr)
        self.gamma = gamma

    def _compute_lr(self, loss: float | None = None) -> float:
        """Compute exponentially decayed learning rate."""
        effective_step = max(0, self.step_count - self.warmup_steps)
        return self.initial_lr * (self.gamma**effective_step)


class CosineAnnealingLR(LRScheduler):
    """Cosine annealing learning rate scheduler.

    Decays learning rate following a cosine curve.

    Attributes:
        T_max: Maximum number of iterations
        eta_min: Minimum learning rate
    """

    def __init__(
        self,
        initial_lr: float = 0.001,
        T_max: int = 100,
        eta_min: float = 0.0,
        warmup_steps: int = 0,
        warmup_init_lr: float = 1e-5,
    ):
        """Initialize cosine annealing scheduler.

        Args:
            initial_lr: Initial learning rate
            T_max: Maximum iterations
            eta_min: Minimum learning rate
            warmup_steps: Warmup steps
            warmup_init_lr: Warmup initial learning rate
        """
        super().__init__(initial_lr, eta_min, warmup_steps, warmup_init_lr)
        self.T_max = T_max
        self.eta_min = eta_min

    def _compute_lr(self, loss: float | None = None) -> float:
        """Compute cosine annealed learning rate."""
        effective_step = max(0, self.step_count - self.warmup_steps)

        if effective_step >= self.T_max:
            return self.eta_min

        progress = effective_step / self.T_max
        cosine_decay = 0.5 * (1 + math.cos(math.pi * progress))

        return self.eta_min + (self.initial_lr - self.eta_min) * cosine_decay


class ReduceLROnPlateau(LRScheduler):
    """Reduce learning rate when loss plateaus.

    Reduces learning rate when metric stops improving.

    Attributes:
        factor: Factor by which to reduce learning rate
        patience: Number of steps with no improvement
        threshold: Threshold for measuring improvement
        cooldown: Number of steps to wait before resuming
    """

    def __init__(
        self,
        initial_lr: float = 0.001,
        factor: float = 0.1,
        patience: int = 10,
        threshold: float = 1e-4,
        cooldown: int = 0,
        min_lr: float = 1e-7,
        warmup_steps: int = 0,
        warmup_init_lr: float = 1e-5,
    ):
        """Initialize plateau scheduler.

        Args:
            initial_lr: Initial learning rate
            factor: Reduction factor
            patience: Steps to wait before reducing
            threshold: Improvement threshold
            cooldown: Cooldown steps
            min_lr: Minimum learning rate
            warmup_steps: Warmup steps
            warmup_init_lr: Warmup initial learning rate
        """
        super().__init__(initial_lr, min_lr, warmup_steps, warmup_init_lr)
        self.factor = factor
        self.patience = patience
        self.threshold = threshold
        self.cooldown = cooldown
        self.cooldown_counter = 0
        self.best_loss = float("inf")
        self.num_bad_steps = 0

    def _compute_lr(self, loss: float | None = None) -> float:
        """Compute learning rate based on plateau detection."""
        if loss is None:
            return self.current_lr

        # Check cooldown first - during cooldown, don't update anything
        if self.cooldown_counter > 0:
            self.cooldown_counter -= 1
            return self.current_lr

        # Update best loss
        if loss < self.best_loss - self.threshold:
            self.best_loss = loss
            self.num_bad_steps = 0
        else:
            self.num_bad_steps += 1

        # Reduce learning rate if patience exceeded (>= for faster reduction)
        if self.num_bad_steps >= self.patience:
            self.current_lr = max(self.current_lr * self.factor, self.min_lr)
            self.cooldown_counter = self.cooldown
            # Reset bad steps to negative patience so we need patience more bad steps
            # This prevents immediate re-reduction after cooldown
            self.num_bad_steps = -self.patience

        return self.current_lr

    def reset(self) -> None:
        """Reset the engine to initial state."""
        super().reset()
        self.cooldown_counter = 0
        self.best_loss = float("inf")
        self.num_bad_steps = 0


class CyclicalLR(LRScheduler):
    """Cyclical learning rate scheduler.

    Cycles learning rate between base and max values.

    Attributes:
        base_lr: Base learning rate
        max_lr: Maximum learning rate
        step_size: Steps per half cycle
        mode: Cycle mode (triangular, triangular2, exp_range)
    """

    def __init__(
        self,
        base_lr: float = 0.001,
        max_lr: float = 0.01,
        step_size: int = 2000,
        mode: str = "triangular",
        gamma: float = 1.0,
        warmup_steps: int = 0,
    ):
        """Initialize cyclical scheduler.

        Args:
            base_lr: Base learning rate
            max_lr: Maximum learning rate
            step_size: Steps per half cycle
            mode: Cycle mode (triangular, triangular2, exp_range)
            gamma: Decay factor for exp_range mode
            warmup_steps: Warmup steps
        """
        super().__init__(base_lr, base_lr, warmup_steps, base_lr)
        self.base_lr = base_lr
        self.max_lr = max_lr
        self.step_size = step_size
        self.mode = mode
        self.gamma = gamma

    def _compute_lr(self, loss: float | None = None) -> float:
        """Compute cyclical learning rate."""
        if self.step_count <= self.warmup_steps:
            return self.current_lr  # Warmup handles this

        # effective_step is 0-indexed (step_count was already incremented in step())
        # So step 1 -> effective_step 0, step 2 -> effective_step 1, etc.
        effective_step = self.step_count - self.warmup_steps - 1

        # Calculate position within cycle
        # step_size is steps per HALF cycle
        # So a full cycle is 2 * step_size steps
        cycle_length = 2 * self.step_size
        position_in_cycle = effective_step % cycle_length

        # Calculate x: 0 at start, 1 at peak, 0 at end of cycle
        # We use (step_size - 1) as the divisor to reach max at step_size-1
        # But actually, let's think about it differently:
        # For step_size=5, we want: step 0->0.0, step 4->1.0, step 5->1.0, step 9->0.0
        if position_in_cycle < self.step_size:
            # First half: increasing from base to max (0 to step_size-1)
            x = position_in_cycle / (self.step_size - 1) if self.step_size > 1 else 1.0
        else:
            # Second half: decreasing from max to base (step_size to 2*step_size-1)
            # position_in_cycle goes from step_size to 2*step_size-1
            # We want x=1.0 at position_in_cycle=step_size and x=0.0 at position_in_cycle=2*step_size-1
            x = (
                (2 * self.step_size - 1 - position_in_cycle) / (self.step_size - 1)
                if self.step_size > 1
                else 0.0
            )

        # Clamp x to [0, 1] to handle edge cases
        x = max(0.0, min(1.0, x))

        # Calculate cycle number for triangular2 decay (1-indexed)
        cycle_number = (effective_step // cycle_length) + 1

        if self.mode == "triangular":
            lr = self.base_lr + (self.max_lr - self.base_lr) * x
        elif self.mode == "triangular2":
            lr = self.base_lr + (self.max_lr - self.base_lr) * x / (
                2 ** (cycle_number - 1)
            )
        elif self.mode == "exp_range":
            lr = self.base_lr + (self.max_lr - self.base_lr) * x * (
                self.gamma**effective_step
            )
        else:
            lr = self.base_lr

        return lr


class WarmupScheduler(LRScheduler):
    """Warmup scheduler that wraps another scheduler.

    Provides warmup before handing off to the main scheduler.

    Attributes:
        base_scheduler: The main scheduler to wrap
        warmup_steps: Number of warmup steps
    """

    def __init__(
        self,
        base_scheduler: LRScheduler,
        warmup_steps: int = 1000,
        warmup_init_lr: float = 1e-5,
    ):
        """Initialize warmup scheduler.

        Args:
            base_scheduler: Main scheduler to wrap
            warmup_steps: Number of warmup steps
            warmup_init_lr: Initial warmup learning rate
        """
        super().__init__(
            initial_lr=base_scheduler.initial_lr,
            min_lr=base_scheduler.min_lr,
            warmup_steps=warmup_steps,
            warmup_init_lr=warmup_init_lr,
        )
        self.base_scheduler = base_scheduler
        self._warmup_done = False

    def step(self, loss: float | None = None) -> float:
        """Advance one step."""
        self.step_count += 1

        if self.step_count <= self.warmup_steps:
            self.current_lr = self._compute_warmup_lr()
        else:
            if not self._warmup_done:
                # Sync base scheduler state - base scheduler starts at step 0
                self.base_scheduler.step_count = 0
                self.base_scheduler.current_lr = self.base_scheduler.initial_lr
                self._warmup_done = True
            # Step the base scheduler and get its LR
            self.current_lr = self.base_scheduler.step(loss)

        self.current_lr = max(self.current_lr, self.min_lr)
        return self.current_lr

    def _compute_lr(self, loss: float | None = None) -> float:
        """Delegate to base scheduler."""
        return self.base_scheduler._compute_lr(loss)


class MetaLearningScheduler:
    """Scheduler that adapts based on meta-learning patterns.

    Integrates with MetaLearningController to adapt learning rates
    based on task performance across episodes.

    Attributes:
        base_scheduler: Base learning rate scheduler
        meta_controller: Optional meta-learning controller
        adaptation_rate: Rate of adaptation based on meta-learning
    """

    def __init__(
        self,
        base_scheduler: LRScheduler,
        meta_controller: MetaLearningController | None = None,
        adaptation_rate: float = 0.1,
    ):
        """Initialize meta-learning scheduler.

        Args:
            base_scheduler: Base scheduler
            meta_controller: Optional meta-learning controller
            adaptation_rate: Rate of adaptation
        """
        self.base_scheduler = base_scheduler
        self.meta_controller = meta_controller
        self.adaptation_rate = adaptation_rate
        self.episode_performance: list[float] = []

    def step(
        self, loss: float | None = None, episode_loss: float | None = None
    ) -> float:
        """Advance one step with meta-learning adaptation.

        Args:
            loss: Current loss
            episode_loss: Episode loss for meta-learning

        Returns:
            Current learning rate
        """
        # Track episode performance
        if episode_loss is not None:
            self.episode_performance.append(episode_loss)

        # Adapt based on meta-learning if available
        if self.meta_controller is not None and len(self.episode_performance) >= 2:
            self._adapt_from_meta_learning()

        # Step base scheduler
        return self.base_scheduler.step(loss)

    def get_lr(self) -> float:
        """Get current learning rate."""
        return self.base_scheduler.get_lr()

    def _adapt_from_meta_learning(self) -> None:
        """Adapt learning rate based on meta-learning patterns."""
        # Simple adaptation: if performance is improving, increase LR slightly
        # if worsening, decrease LR
        if len(self.episode_performance) < 2:
            return

        recent_perf = np.mean(self.episode_performance[-3:])
        older_perf = (
            np.mean(self.episode_performance[-6:-3])
            if len(self.episode_performance) >= 6
            else recent_perf
        )

        if recent_perf < older_perf:  # Improving
            adjustment = 1 + self.adaptation_rate
        else:  # Worsening
            adjustment = 1 - self.adaptation_rate

        self.base_scheduler.current_lr *= adjustment


def create_scheduler(
    scheduler_type: str,
    initial_lr: float = 0.001,
    **kwargs: Any,
) -> LRScheduler:
    """Factory function to create schedulers by type.

    Args:
        scheduler_type: Type of scheduler (constant, step, exponential, cosine, plateau)
        initial_lr: Initial learning rate
        **kwargs: Additional arguments for specific scheduler types

    Returns:
        Configured scheduler

    Example:
        >>> scheduler = create_scheduler("step", initial_lr=0.01, step_size=30, gamma=0.1)
        >>> scheduler = create_scheduler("cosine", initial_lr=0.01, T_max=100)
    """
    scheduler_type = scheduler_type.lower()

    if scheduler_type == "constant":
        return ConstantLR(initial_lr=initial_lr, **kwargs)
    elif scheduler_type == "step":
        return StepLR(initial_lr=initial_lr, **kwargs)
    elif scheduler_type == "exponential":
        return ExponentialLR(initial_lr=initial_lr, **kwargs)
    elif scheduler_type == "cosine":
        return CosineAnnealingLR(initial_lr=initial_lr, **kwargs)
    elif scheduler_type == "plateau":
        return ReduceLROnPlateau(initial_lr=initial_lr, **kwargs)
    elif scheduler_type == "cyclical":
        return CyclicalLR(base_lr=initial_lr, **kwargs)
    else:
        raise ValueError(f"Unknown scheduler type: {scheduler_type}")
