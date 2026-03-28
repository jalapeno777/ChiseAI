"""Optimizer implementations for parameter updates.

This module provides SGD and Adam-like optimizers for parameter tuning.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class OptimizerState:
    """State of the optimizer for a single parameter.

    Attributes:
        param_name: Name of the parameter
        value: Current value
        gradient: Last computed gradient
        momentum: Momentum buffer (for SGD with momentum and Adam)
        velocity: Velocity buffer (for Adam)
        step: Number of optimization steps taken
    """

    param_name: str
    value: float
    gradient: float = 0.0
    momentum: float = 0.0
    velocity: float = 0.0
    step: int = 0


class Optimizer:
    """Base class for optimizers."""

    def __init__(self, learning_rate: float):
        """Initialize optimizer.

        Args:
            learning_rate: Learning rate for parameter updates
        """
        self.learning_rate = learning_rate
        if learning_rate <= 0:
            raise ValueError("Learning rate must be positive")

    def step(
        self, params: dict[str, float], gradients: dict[str, float]
    ) -> dict[str, float]:
        """Update parameters based on gradients.

        Args:
            params: Current parameter values
            gradients: Computed gradients

        Returns:
            Updated parameter values
        """
        raise NotImplementedError("Subclasses must implement step()")

    def get_state(self) -> dict[str, Any]:
        """Get optimizer state for checkpointing."""
        raise NotImplementedError("Subclasses must implement get_state()")

    def load_state(self, state: dict[str, Any]) -> None:
        """Load optimizer state from checkpoint."""
        raise NotImplementedError("Subclasses must implement load_state()")


class SGD(Optimizer):
    """Stochastic Gradient Descent optimizer.

    Supports momentum and weight decay.

    Attributes:
        momentum: Momentum coefficient (0 = no momentum)
        weight_decay: L2 regularization coefficient
    """

    def __init__(
        self,
        learning_rate: float,
        momentum: float = 0.0,
        weight_decay: float = 0.0,
    ):
        """Initialize SGD optimizer.

        Args:
            learning_rate: Learning rate
            momentum: Momentum coefficient (default: 0)
            weight_decay: L2 regularization coefficient (default: 0)
        """
        super().__init__(learning_rate)
        self.momentum = momentum
        self.weight_decay = weight_decay
        self._state: dict[str, OptimizerState] = {}

    def step(
        self, params: dict[str, float], gradients: dict[str, float]
    ) -> dict[str, float]:
        """Perform one optimization step.

        Update rule with momentum:
            v = momentum * v + gradient
            param = param - lr * v

        Args:
            params: Current parameters
            gradients: Computed gradients

        Returns:
            Updated parameters
        """
        updated_params = {}

        for param_name, param_value in params.items():
            if param_name not in self._state:
                self._state[param_name] = OptimizerState(
                    param_name=param_name, value=param_value
                )

            state = self._state[param_name]
            gradient = gradients.get(param_name, 0.0)

            # Apply momentum
            if self.momentum > 0:
                state.momentum = self.momentum * state.momentum + gradient
                gradient = state.momentum

            # Apply weight decay (L2 regularization)
            if self.weight_decay > 0:
                gradient = gradient + self.weight_decay * param_value

            # Update parameter
            new_value = param_value - self.learning_rate * gradient
            state.value = new_value
            state.gradient = gradient
            state.step += 1

            updated_params[param_name] = new_value

            logger.debug(
                "SGD update: %s = %.6f (gradient=%.6f, momentum=%.6f)",
                param_name,
                new_value,
                gradient,
                state.momentum,
            )

        return updated_params

    def get_state(self) -> dict[str, Any]:
        """Get optimizer state for checkpointing."""
        return {
            "type": "SGD",
            "learning_rate": self.learning_rate,
            "momentum": self.momentum,
            "weight_decay": self.weight_decay,
            "param_state": {
                name: {
                    "value": state.value,
                    "gradient": state.gradient,
                    "momentum": state.momentum,
                    "step": state.step,
                }
                for name, state in self._state.items()
            },
        }

    def load_state(self, state: dict[str, Any]) -> None:
        """Load optimizer state from checkpoint."""
        if state.get("type") != "SGD":
            raise ValueError(
                f"Cannot load {state.get('type')} state into SGD optimizer"
            )

        self.learning_rate = state["learning_rate"]
        self.momentum = state["momentum"]
        self.weight_decay = state["weight_decay"]

        self._state = {}
        for name, param_state in state.get("param_state", {}).items():
            self._state[name] = OptimizerState(
                param_name=name,
                value=param_state["value"],
                gradient=param_state["gradient"],
                momentum=param_state["momentum"],
                step=param_state["step"],
            )


class Adam(Optimizer):
    """Adam optimizer (Adaptive Moment Estimation).

    Implements the Adam algorithm from Kingma and Ba (2014).

    Attributes:
        beta1: Exponential decay rate for first moment (momentum)
        beta2: Exponential decay rate for second moment (velocity)
        epsilon: Small constant for numerical stability
    """

    def __init__(
        self,
        learning_rate: float,
        beta1: float = 0.9,
        beta2: float = 0.999,
        epsilon: float = 1e-8,
    ):
        """Initialize Adam optimizer.

        Args:
            learning_rate: Learning rate
            beta1: Decay rate for first moment (default: 0.9)
            beta2: Decay rate for second moment (default: 0.999)
            epsilon: Small constant for numerical stability (default: 1e-8)
        """
        super().__init__(learning_rate)
        self.beta1 = beta1
        self.beta2 = beta2
        self.epsilon = epsilon
        self._state: dict[str, OptimizerState] = {}
        self._global_step = 0

    def step(
        self, params: dict[str, float], gradients: dict[str, float]
    ) -> dict[str, float]:
        """Perform one optimization step.

        Args:
            params: Current parameters
            gradients: Computed gradients

        Returns:
            Updated parameters
        """
        self._global_step += 1
        updated_params = {}
        bias_correction1 = 1.0 - self.beta1**self._global_step
        bias_correction2 = 1.0 - self.beta2**self._global_step

        for param_name, param_value in params.items():
            if param_name not in self._state:
                self._state[param_name] = OptimizerState(
                    param_name=param_name, value=param_value
                )

            state = self._state[param_name]
            gradient = gradients.get(param_name, 0.0)

            # Update biased first moment estimate (momentum)
            state.momentum = self.beta1 * state.momentum + (1 - self.beta1) * gradient

            # Update biased second moment estimate (velocity)
            state.velocity = (
                self.beta2 * state.velocity + (1 - self.beta2) * gradient * gradient
            )

            # Compute bias-corrected first moment estimate
            momentum_hat = state.momentum / bias_correction1

            # Compute bias-corrected second moment estimate
            velocity_hat = state.velocity / bias_correction2

            # Compute parameter update
            denom = math.sqrt(velocity_hat) + self.epsilon
            update = self.learning_rate * momentum_hat / denom

            # Update parameter
            new_value = param_value - update
            state.value = new_value
            state.gradient = gradient
            state.step += 1

            updated_params[param_name] = new_value

            logger.debug(
                "Adam update: %s = %.6f (gradient=%.6f, m=%.6f, v=%.6f)",
                param_name,
                new_value,
                gradient,
                momentum_hat,
                velocity_hat,
            )

        return updated_params

    def get_state(self) -> dict[str, Any]:
        """Get optimizer state for checkpointing."""
        return {
            "type": "Adam",
            "learning_rate": self.learning_rate,
            "beta1": self.beta1,
            "beta2": self.beta2,
            "epsilon": self.epsilon,
            "global_step": self._global_step,
            "param_state": {
                name: {
                    "value": state.value,
                    "gradient": state.gradient,
                    "momentum": state.momentum,
                    "velocity": state.velocity,
                    "step": state.step,
                }
                for name, state in self._state.items()
            },
        }

    def load_state(self, state: dict[str, Any]) -> None:
        """Load optimizer state from checkpoint."""
        if state.get("type") != "Adam":
            raise ValueError(
                f"Cannot load {state.get('type')} state into Adam optimizer"
            )

        self.learning_rate = state["learning_rate"]
        self.beta1 = state["beta1"]
        self.beta2 = state["beta2"]
        self.epsilon = state["epsilon"]
        self._global_step = state["global_step"]

        self._state = {}
        for name, param_state in state.get("param_state", {}).items():
            self._state[name] = OptimizerState(
                param_name=name,
                value=param_state["value"],
                gradient=param_state["gradient"],
                momentum=param_state["momentum"],
                velocity=param_state["velocity"],
                step=param_state["step"],
            )
