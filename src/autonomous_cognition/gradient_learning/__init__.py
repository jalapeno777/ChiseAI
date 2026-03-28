"""Gradient-based parameter optimization for autonomous cognition.

This module provides the main integration layer for gradient-based parameter
optimization with constitution audit integration.

All parameter updates MUST go through constitution_audit approval before being applied.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .checkpoint import Checkpoint, CheckpointManager
from .clipping import ClipMode, GradientClipper
from .gradient_computer import GradientComputer
from .optimizer import SGD, Adam, Optimizer
from .scheduler import (
    CosineScheduler,
    ExponentialScheduler,
    LearningRateScheduler,
    ScheduleType,
    StepScheduler,
    create_scheduler,
)

__all__ = [
    "Checkpoint",
    "CheckpointManager",
    "ClipMode",
    "CosineScheduler",
    "ExponentialScheduler",
    "GradientClipper",
    "GradientComputer",
    "GradientLearningOptimizer",
    "LearningRateScheduler",
    "Optimizer",
    "ParameterUpdateRejected",
    "SGD",
    "Adam",
    "ScheduleType",
    "StepScheduler",
    "create_adam_optimizer",
    "create_sgd_optimizer",
    "create_scheduler",
]

logger = logging.getLogger(__name__)


class ParameterUpdateRejected(Exception):
    """Raised when constitution audit rejects parameter updates."""

    pass


@dataclass
class OptimizationResult:
    """Result of an optimization step.

    Attributes:
        step: Optimization step number
        params: Updated parameters
        gradients: Computed gradients
        clipped_gradients: Gradients after clipping
        learning_rate: Learning rate used
        metrics: Optional metrics snapshot
        approved: Whether update was approved
        rejected: Whether update was rejected
    """

    step: int
    params: dict[str, float]
    gradients: dict[str, float]
    clipped_gradients: dict[str, float]
    learning_rate: float
    metrics: dict[str, float] | None = None
    approved: bool = True
    rejected: bool = False


class GradientLearningOptimizer:
    """Main gradient learning optimizer with constitution audit integration.

    This class orchestrates gradient computation, optimization, clipping,
    checkpointing, and constitution audit approval.

    Attributes:
        params: Current tunable parameters
        gradient_computer: Computes numerical gradients
        optimizer: Updates parameters based on gradients
        scheduler: Adjusts learning rate over time
        clipper: Clips gradients to prevent large swings
        checkpoint_manager: Manages parameter state snapshots
        constitution_audit_fn: Optional function to request constitution approval
    """

    def __init__(
        self,
        params: dict[str, float],
        metric_fns: dict[str, Callable[[dict[str, float]], float]],
        constitution_audit_fn: Callable[[dict[str, Any]], bool] | None = None,
        optimizer_type: str = "SGD",
        learning_rate: float = 0.01,
        scheduler_type: ScheduleType = ScheduleType.EXPONENTIAL,
        scheduler_config: dict[str, Any] | None = None,
        clip_mode: ClipMode = ClipMode.NORM,
        clip_max_norm: float = 1.0,
        checkpoint_dir: str = "checkpoints/gradient_learning",
        checkpoint_every: int = 10,
        require_audit: bool = True,
    ):
        """Initialize gradient learning optimizer.

        Args:
            params: Initial parameter values {name: value}
            metric_fns: Dictionary of {metric_name: function(params) -> float}
            constitution_audit_fn: Optional approval function.
                                  If provided, called before parameter updates.
                                  Should return True if approved, False otherwise.
            optimizer_type: Type of optimizer ('SGD' or 'Adam')
            learning_rate: Initial learning rate
            scheduler_type: Type of learning rate schedule
            scheduler_config: Additional scheduler configuration
            clip_mode: Gradient clipping mode
            clip_max_norm: Maximum gradient norm for clipping
            checkpoint_dir: Directory for checkpoints
            checkpoint_every: Save checkpoint every N steps
            require_audit: Whether to require constitution audit approval
        """
        self.params = params.copy()
        self.metric_fns = metric_fns
        self.constitution_audit_fn = constitution_audit_fn
        self.require_audit = require_audit

        # Initialize components
        self.gradient_computer = GradientComputer()
        self.optimizer = self._create_optimizer(optimizer_type, learning_rate)
        self.scheduler = create_scheduler(
            scheduler_type,
            learning_rate,
            **(scheduler_config or {}),
        )
        self.clipper = GradientClipper(mode=clip_mode, max_norm=clip_max_norm)
        self.checkpoint_manager = CheckpointManager(checkpoint_dir=checkpoint_dir)

        self.checkpoint_every = checkpoint_every
        self._step = 0

        logger.info(
            "GradientLearningOptimizer initialized with %d params, optimizer=%s, lr=%.4f",
            len(params),
            optimizer_type,
            learning_rate,
        )

    def _create_optimizer(self, optimizer_type: str, learning_rate: float) -> Optimizer:
        """Create optimizer instance."""
        if optimizer_type.upper() == "SGD":
            return SGD(learning_rate=learning_rate)
        elif optimizer_type.upper() == "ADAM":
            return Adam(learning_rate=learning_rate)
        else:
            raise ValueError(f"Unknown optimizer type: {optimizer_type}")

    def _request_constitution_audit(
        self, new_params: dict[str, float], rationale: str
    ) -> bool:
        """Request constitution audit approval for parameter update.

        Args:
            new_params: Proposed new parameter values
            rationale: Description of why the update is needed

        Returns:
            True if approved, False otherwise
        """
        if not self.constitution_audit_fn:
            logger.warning(
                "No constitution_audit_fn configured, auto-approving parameter update"
            )
            return True

        decision = {
            "action": "parameter_update",
            "description": rationale,
            "parameters": new_params,
            "risk_level": "medium",
            "evidence": {
                "current_params": self.params,
                "proposed_params": new_params,
                "step": self._step,
            },
        }

        try:
            approved = self.constitution_audit_fn(decision)
            if approved:
                logger.info(
                    "Constitution audit approved parameter update at step %d",
                    self._step,
                )
            else:
                logger.warning(
                    "Constitution audit rejected parameter update at step %d",
                    self._step,
                )
            return approved
        except Exception as e:
            logger.error("Constitution audit error: %s", e)
            if self.require_audit:
                raise ParameterUpdateRejected(f"Constitution audit error: {e}") from e
            return True

    def step(
        self,
        metrics: dict[str, float] | None = None,
        rationale: str = "Gradient descent optimization",
    ) -> OptimizationResult:
        """Perform one optimization step.

        Args:
            metrics: Optional metrics snapshot for checkpointing
            rationale: Description for constitution audit

        Returns:
            OptimizationResult with update details

        Raises:
            ParameterUpdateRejected: If constitution audit rejects the update
        """
        self._step += 1

        # Compute gradients
        gradients = self.gradient_computer.compute_gradients_for_metrics(
            self.metric_fns, self.params
        )

        # Aggregate gradients (average across metrics)
        aggregated_gradients: dict[str, float] = {}
        for param_name in self.params:
            param_grads = [
                result.gradients.get(param_name, 0.0)
                for result in gradients.values()
                if param_name in result.gradients
            ]
            if param_grads:
                aggregated_gradients[param_name] = sum(param_grads) / len(param_grads)
            else:
                aggregated_gradients[param_name] = 0.0

        # Clip gradients
        clip_result = self.clipper.clip(aggregated_gradients)

        # Get learning rate
        lr = self.scheduler.step()

        # Compute proposed parameter updates
        proposed_params = self.optimizer.step(
            self.params, clip_result.clipped_gradients
        )

        # Request constitution approval
        if self.require_audit or self.constitution_audit_fn:
            approved = self._request_constitution_audit(proposed_params, rationale)
            if not approved:
                return OptimizationResult(
                    step=self._step,
                    params=self.params,
                    gradients=aggregated_gradients,
                    clipped_gradients=clip_result.clipped_gradients,
                    learning_rate=lr,
                    metrics=metrics,
                    approved=False,
                    rejected=True,
                )

        # Apply approved updates
        self.params = proposed_params

        # Checkpoint if needed
        if self._step % self.checkpoint_every == 0:
            self.save_checkpoint(metrics)

        logger.debug(
            "Step %d: lr=%.6f, clipped_norm=%.4f, params=%s",
            self._step,
            lr,
            clip_result.clipped_norm,
            self.params,
        )

        return OptimizationResult(
            step=self._step,
            params=self.params,
            gradients=aggregated_gradients,
            clipped_gradients=clip_result.clipped_gradients,
            learning_rate=lr,
            metrics=metrics,
            approved=True,
            rejected=False,
        )

    def save_checkpoint(self, metrics: dict[str, float] | None = None) -> str:
        """Save current state to checkpoint.

        Args:
            metrics: Optional metrics snapshot

        Returns:
            Checkpoint ID
        """
        checkpoint_id = f"step_{self._step}_{uuid.uuid4().hex[:8]}"

        checkpoint = Checkpoint(
            checkpoint_id=checkpoint_id,
            step=self._step,
            params=self.params.copy(),
            optimizer_state=self.optimizer.get_state(),
            scheduler_state=self.scheduler.get_state(),
            clipper_state=self.clipper.get_state(),
            metrics=metrics,
        )

        self.checkpoint_manager.save(checkpoint, checkpoint_id)
        return checkpoint_id

    def load_checkpoint(self, checkpoint_id: str) -> None:
        """Load state from checkpoint.

        Args:
            checkpoint_id: Checkpoint to restore
        """
        checkpoint = self.checkpoint_manager.load(checkpoint_id)

        self._step = checkpoint.step
        self.params = checkpoint.params.copy()

        if checkpoint.optimizer_state:
            self.optimizer.load_state(checkpoint.optimizer_state)
        if checkpoint.scheduler_state:
            self.scheduler.load_state(checkpoint.scheduler_state)
        if checkpoint.clipper_state:
            loaded_clipper = GradientClipper.from_state(checkpoint.clipper_state)
            self.clipper = loaded_clipper

        logger.info("Loaded checkpoint %s at step %d", checkpoint_id, self._step)

    def rollback(self, target_step: int | None = None) -> dict[str, float]:
        """Rollback to previous checkpoint.

        Args:
            target_step: Step number to rollback to

        Returns:
            Rolled back parameters
        """
        checkpoint = self.checkpoint_manager.rollback(target_step=target_step)
        self.load_checkpoint(checkpoint.checkpoint_id)
        return self.params

    def get_state(self) -> dict[str, Any]:
        """Get full optimizer state."""
        return {
            "step": self._step,
            "params": self.params.copy(),
            "optimizer": self.optimizer.get_state(),
            "scheduler": self.scheduler.get_state(),
            "clipper": self.clipper.get_state(),
        }


# Factory functions for common configurations
def create_sgd_optimizer(
    params: dict[str, float],
    metric_fns: dict[str, Callable[[dict[str, float]], float]],
    learning_rate: float = 0.01,
    constitution_audit_fn: Callable[[dict[str, Any]], bool] | None = None,
) -> GradientLearningOptimizer:
    """Create SGD-based gradient optimizer.

    Args:
        params: Initial parameters
        metric_fns: Metric functions
        learning_rate: Learning rate
        constitution_audit_fn: Constitution audit function

    Returns:
        Configured GradientLearningOptimizer
    """
    return GradientLearningOptimizer(
        params=params,
        metric_fns=metric_fns,
        optimizer_type="SGD",
        learning_rate=learning_rate,
        constitution_audit_fn=constitution_audit_fn,
    )


def create_adam_optimizer(
    params: dict[str, float],
    metric_fns: dict[str, Callable[[dict[str, float]], float]],
    learning_rate: float = 0.001,
    constitution_audit_fn: Callable[[dict[str, Any]], bool] | None = None,
) -> GradientLearningOptimizer:
    """Create Adam-based gradient optimizer.

    Args:
        params: Initial parameters
        metric_fns: Metric functions
        learning_rate: Learning rate
        constitution_audit_fn: Constitution audit function

    Returns:
        Configured GradientLearningOptimizer
    """
    return GradientLearningOptimizer(
        params=params,
        metric_fns=metric_fns,
        optimizer_type="Adam",
        learning_rate=learning_rate,
        constitution_audit_fn=constitution_audit_fn,
    )
