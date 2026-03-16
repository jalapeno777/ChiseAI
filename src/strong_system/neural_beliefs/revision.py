"""Belief Revision Engine with gradient-based optimization.

Provides optimization algorithms for updating beliefs based on gradients,
including learning rate scheduling, momentum, and adaptive methods.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum, auto
from typing import TYPE_CHECKING, Any

import numpy as np
from src.strong_system.belief_embeddings import ValidationError

if TYPE_CHECKING:
    from .belief import NeuralBelief


class OptimizerType(Enum):
    """Type of optimization algorithm."""

    SGD = auto()
    MOMENTUM = auto()
    ADAM = auto()
    RMSPROP = auto()


@dataclass
class OptimizerConfig:
    """Configuration for belief revision optimizer.

    Attributes:
        optimizer_type: Type of optimization algorithm
        learning_rate: Initial learning rate
        momentum: Momentum coefficient (for MOMENTUM optimizer)
        beta1: First moment decay rate (for ADAM optimizer)
        beta2: Second moment decay rate (for ADAM optimizer)
        epsilon: Small constant for numerical stability
        weight_decay: L2 regularization coefficient
        max_grad_norm: Maximum gradient norm for clipping (None = no clipping)
    """

    optimizer_type: OptimizerType = OptimizerType.ADAM
    learning_rate: float = 0.001
    momentum: float = 0.9
    beta1: float = 0.9
    beta2: float = 0.999
    epsilon: float = 1e-8
    weight_decay: float = 0.0
    max_grad_norm: float | None = None

    def __post_init__(self) -> None:
        """Validate configuration."""
        if self.learning_rate <= 0:
            raise ValidationError(
                f"learning_rate must be positive, got {self.learning_rate}"
            )
        if not 0 <= self.momentum < 1:
            raise ValidationError(f"momentum must be in [0, 1), got {self.momentum}")
        if not 0 <= self.beta1 < 1:
            raise ValidationError(f"beta1 must be in [0, 1), got {self.beta1}")
        if not 0 <= self.beta2 < 1:
            raise ValidationError(f"beta2 must be in [0, 1), got {self.beta2}")


@dataclass
class RevisionMetrics:
    """Metrics from a belief revision step.

    Attributes:
        step_number: The revision step number
        timestamp: When the revision occurred
        num_beliefs: Number of beliefs revised
        avg_gradient_magnitude: Average gradient magnitude
        max_gradient_magnitude: Maximum gradient magnitude
        learning_rate: Learning rate used
        convergence_score: Convergence metric (0-1, higher = more converged)
    """

    step_number: int
    timestamp: datetime
    num_beliefs: int
    avg_gradient_magnitude: float
    max_gradient_magnitude: float
    learning_rate: float
    convergence_score: float

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "step_number": self.step_number,
            "timestamp": self.timestamp.isoformat(),
            "num_beliefs": self.num_beliefs,
            "avg_gradient_magnitude": self.avg_gradient_magnitude,
            "max_gradient_magnitude": self.max_gradient_magnitude,
            "learning_rate": self.learning_rate,
            "convergence_score": self.convergence_score,
        }


class LearningRateScheduler:
    """Learning rate scheduler for belief revision.

    Supports various scheduling strategies:
    - Constant: Fixed learning rate
    - Step decay: Reduce by factor every N steps
    - Exponential: Exponential decay
    - Cosine annealing: Cosine decay to minimum
    """

    def __init__(
        self,
        initial_lr: float,
        schedule_type: str = "constant",
        decay_factor: float = 0.1,
        decay_steps: int = 100,
        min_lr: float = 1e-7,
    ):
        """Initialize scheduler.

        Args:
            initial_lr: Initial learning rate
            schedule_type: One of "constant", "step", "exponential", "cosine"
            decay_factor: Factor for step/exponential decay
            decay_steps: Steps between decays (for step) or decay rate (for exponential)
            min_lr: Minimum learning rate
        """
        self.initial_lr = initial_lr
        self.current_lr = initial_lr
        self.schedule_type = schedule_type
        self.decay_factor = decay_factor
        self.decay_steps = decay_steps
        self.min_lr = min_lr
        self.step_count = 0

    def step(self) -> float:
        """Advance one step and return current learning rate."""
        self.step_count += 1

        if self.schedule_type == "constant":
            pass
        elif self.schedule_type == "step":
            if self.step_count % self.decay_steps == 0:
                self.current_lr = max(self.current_lr * self.decay_factor, self.min_lr)
        elif self.schedule_type == "exponential":
            self.current_lr = max(
                self.initial_lr
                * (self.decay_factor ** (self.step_count / self.decay_steps)),
                self.min_lr,
            )
        elif self.schedule_type == "cosine":
            import math

            progress = min(self.step_count / self.decay_steps, 1.0)
            cosine_decay = 0.5 * (1 + math.cos(math.pi * progress))
            self.current_lr = (
                self.min_lr + (self.initial_lr - self.min_lr) * cosine_decay
            )

        return self.current_lr

    def get_lr(self) -> float:
        """Get current learning rate without advancing."""
        return self.current_lr

    def reset(self) -> None:
        """Reset scheduler to initial state."""
        self.current_lr = self.initial_lr
        self.step_count = 0


class BeliefRevisionEngine:
    """Engine for gradient-based belief revision.

    Implements various optimization algorithms (SGD, Momentum, Adam, RMSprop)
    for updating beliefs based on computed gradients. Supports learning rate
    scheduling, gradient clipping, and convergence detection.

    Attributes:
        config: Optimizer configuration
        scheduler: Learning rate scheduler
        step_count: Current optimization step
        state: Optimizer state (momentums, velocities, etc.)
        history: History of revision metrics
    """

    def __init__(
        self,
        config: OptimizerConfig | None = None,
        scheduler: LearningRateScheduler | None = None,
    ):
        """Initialize the revision engine.

        Args:
            config: Optimizer configuration (uses defaults if None)
            scheduler: Learning rate scheduler (creates constant if None)
        """
        self.config = config or OptimizerConfig()
        self.scheduler = scheduler or LearningRateScheduler(
            initial_lr=self.config.learning_rate
        )
        self.step_count: int = 0
        self.state: dict[str, dict[str, Any]] = {}
        self.history: list[RevisionMetrics] = []
        self._convergence_window: list[float] = []
        self._window_size: int = 10

    def step(self, beliefs: list[NeuralBelief]) -> RevisionMetrics:
        """Perform one revision step on the given beliefs.

        Updates each belief based on its gradient using the configured
        optimization algorithm.

        Args:
            beliefs: List of NeuralBelief objects to revise

        Returns:
            RevisionMetrics for this step
        """
        self.step_count += 1
        lr = self.scheduler.step()

        gradient_magnitudes = []

        for belief in beliefs:
            if belief.gradient is None:
                continue

            # Get or initialize optimizer state for this belief
            state = self._get_state(belief.belief_id)

            # Compute update
            update = self._compute_update(belief, state, lr)

            # Apply weight decay if configured
            if self.config.weight_decay > 0:
                update = update + self.config.weight_decay * belief.vector

            # Track gradient magnitude
            grad_norm = np.linalg.norm(belief.gradient)
            gradient_magnitudes.append(grad_norm)

            # Apply update
            belief.apply_update(-update)  # Negative for gradient descent
            belief.zero_grad()

        # Compute metrics
        avg_grad = np.mean(gradient_magnitudes) if gradient_magnitudes else 0.0
        max_grad = np.max(gradient_magnitudes) if gradient_magnitudes else 0.0

        # Update convergence tracking
        convergence = self._update_convergence(avg_grad)

        metrics = RevisionMetrics(
            step_number=self.step_count,
            timestamp=datetime.now(UTC),
            num_beliefs=len(beliefs),
            avg_gradient_magnitude=float(avg_grad),
            max_gradient_magnitude=float(max_grad),
            learning_rate=lr,
            convergence_score=convergence,
        )

        self.history.append(metrics)
        return metrics

    def _get_state(self, belief_id: str) -> dict[str, Any]:
        """Get or initialize optimizer state for a belief."""
        if belief_id not in self.state:
            self.state[belief_id] = {
                "m": None,  # First moment (momentum)
                "v": None,  # Second moment (velocity)
                "step": 0,
            }
        return self.state[belief_id]

    def _compute_update(
        self,
        belief: NeuralBelief,
        state: dict[str, Any],
        lr: float,
    ) -> np.ndarray:
        """Compute parameter update based on optimizer type.

        Args:
            belief: The belief being updated
            state: Optimizer state for this belief
            lr: Current learning rate

        Returns:
            Update vector to apply
        """
        gradient = belief.gradient
        if gradient is None:
            return np.zeros(belief.dimension)

        # Apply gradient clipping if configured
        if self.config.max_grad_norm is not None:
            grad_norm = np.linalg.norm(gradient)
            if grad_norm > self.config.max_grad_norm:
                gradient = gradient * (self.config.max_grad_norm / grad_norm)

        opt_type = self.config.optimizer_type

        if opt_type == OptimizerType.SGD:
            return lr * gradient

        elif opt_type == OptimizerType.MOMENTUM:
            if state["m"] is None:
                state["m"] = np.zeros_like(gradient)

            # Update momentum: m = momentum * m + gradient
            state["m"] = self.config.momentum * state["m"] + gradient
            return lr * state["m"]

        elif opt_type == OptimizerType.RMSPROP:
            if state["v"] is None:
                state["v"] = np.zeros_like(gradient)

            # Update velocity: v = beta2 * v + (1 - beta2) * gradient^2
            state["v"] = self.config.beta2 * state["v"] + (1 - self.config.beta2) * (
                gradient**2
            )

            # Compute update: lr * gradient / (sqrt(v) + epsilon)
            return lr * gradient / (np.sqrt(state["v"]) + self.config.epsilon)

        elif opt_type == OptimizerType.ADAM:
            state["step"] += 1
            step = state["step"]

            if state["m"] is None:
                state["m"] = np.zeros_like(gradient)
            if state["v"] is None:
                state["v"] = np.zeros_like(gradient)

            # Update biased first moment: m = beta1 * m + (1 - beta1) * gradient
            state["m"] = (
                self.config.beta1 * state["m"] + (1 - self.config.beta1) * gradient
            )

            # Update biased second moment: v = beta2 * v + (1 - beta2) * gradient^2
            state["v"] = self.config.beta2 * state["v"] + (1 - self.config.beta2) * (
                gradient**2
            )

            # Bias correction
            m_hat = state["m"] / (1 - self.config.beta1**step)
            v_hat = state["v"] / (1 - self.config.beta2**step)

            # Compute update
            return lr * m_hat / (np.sqrt(v_hat) + self.config.epsilon)

        else:
            raise ValidationError(f"Unknown optimizer type: {opt_type}")

    def _update_convergence(self, avg_gradient: float) -> float:
        """Update convergence tracking and return convergence score.

        Args:
            avg_gradient: Average gradient magnitude

        Returns:
            Convergence score between 0 and 1
        """
        self._convergence_window.append(avg_gradient)

        if len(self._convergence_window) > self._window_size:
            self._convergence_window.pop(0)

        if len(self._convergence_window) < 2:
            return 0.0

        # Compute relative change in gradient magnitude
        recent_avg = np.mean(self._convergence_window[-5:])
        older_avg = (
            np.mean(self._convergence_window[:5])
            if len(self._convergence_window) >= 5
            else recent_avg
        )

        if older_avg < 1e-10:
            return 1.0

        relative_change = abs(recent_avg - older_avg) / older_avg

        # Small relative change indicates convergence
        convergence = max(0.0, 1.0 - relative_change)

        # Also consider absolute gradient magnitude
        if recent_avg < 1e-6:
            convergence = max(convergence, 0.9)

        return float(convergence)

    def has_converged(self, threshold: float = 0.95, min_steps: int = 10) -> bool:
        """Check if optimization has converged.

        Args:
            threshold: Convergence score threshold
            min_steps: Minimum steps before considering converged

        Returns:
            True if converged, False otherwise
        """
        if self.step_count < min_steps:
            return False

        if not self.history:
            return False

        recent_scores = [m.convergence_score for m in self.history[-5:]]
        return all(s >= threshold for s in recent_scores)

    def get_metrics_summary(self) -> dict[str, Any]:
        """Get summary of revision metrics."""
        if not self.history:
            return {
                "total_steps": 0,
                "avg_gradient": 0.0,
                "final_lr": self.config.learning_rate,
                "converged": False,
            }

        recent = self.history[-10:]
        return {
            "total_steps": self.step_count,
            "avg_gradient": np.mean([m.avg_gradient_magnitude for m in recent]),
            "max_gradient": max([m.max_gradient_magnitude for m in recent]),
            "final_lr": self.scheduler.get_lr(),
            "converged": self.has_converged(),
            "convergence_score": recent[-1].convergence_score if recent else 0.0,
        }

    def reset(self) -> None:
        """Reset the engine to initial state."""
        self.step_count = 0
        self.state.clear()
        self.history.clear()
        self._convergence_window.clear()
        self.scheduler.reset()

    def zero_grad(self, beliefs: list[NeuralBelief]) -> None:
        """Zero gradients for all beliefs."""
        for belief in beliefs:
            belief.zero_grad()
