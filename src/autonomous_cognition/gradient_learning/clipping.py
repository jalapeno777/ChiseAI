"""Gradient clipping to prevent large parameter updates.

This module provides safety mechanisms to prevent destabilizing parameter swings
during gradient-based optimization.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ClipMode(str, Enum):
    """Gradient clipping modes."""

    NORM = "norm"  # Clip by gradient norm
    VALUE = "value"  # Clip by absolute value


@dataclass
class ClipResult:
    """Result of gradient clipping operation.

    Attributes:
        clipped_gradients: Gradients after clipping
        original_norm: Norm before clipping
        clipped_norm: Norm after clipping
        was_clipped: Whether any clipping occurred
        clip_fraction: Fraction of gradients that were clipped
    """

    clipped_gradients: dict[str, float]
    original_norm: float
    clipped_norm: float
    was_clipped: bool
    clip_fraction: float


class GradientClipper:
    """Clips gradients to prevent large parameter updates.

    Supports two clipping modes:
    - Norm clipping: Scales gradients so their L2 norm doesn't exceed max_norm
    - Value clipping: Clips individual gradient values to [-max_value, max_value]
    """

    def __init__(
        self,
        mode: ClipMode = ClipMode.NORM,
        max_norm: float | None = None,
        max_value: float | None = None,
    ):
        """Initialize gradient clipper.

        Args:
            mode: Clipping mode (NORM or VALUE)
            max_norm: Maximum L2 norm for gradients (used in NORM mode)
            max_value: Maximum absolute value (used in VALUE mode)

        Raises:
            ValueError: If mode is NORM and max_norm is not positive,
                       or if mode is VALUE and max_value is not positive
        """
        self.mode = mode

        if mode == ClipMode.NORM:
            if max_norm is None:
                max_norm = 1.0
            if max_norm <= 0:
                raise ValueError("max_norm must be positive for NORM mode")
            self.max_norm = max_norm
        elif mode == ClipMode.VALUE:
            if max_value is None:
                max_value = 1.0
            if max_value <= 0:
                raise ValueError("max_value must be positive for VALUE mode")
            self.max_value = max_value
        else:
            raise ValueError(f"Unknown clip mode: {mode}")

    def _compute_norm(self, gradients: dict[str, float]) -> float:
        """Compute L2 norm of gradients.

        Args:
            gradients: Dictionary of gradients

        Returns:
            L2 norm of gradients
        """
        if not gradients:
            return 0.0
        return math.sqrt(sum(g**2 for g in gradients.values()))

    def clip(self, gradients: dict[str, float]) -> ClipResult:
        """Clip gradients based on configured mode.

        Args:
            gradients: Dictionary of {param_name: gradient}

        Returns:
            ClipResult with clipped gradients and clipping statistics
        """
        if not gradients:
            return ClipResult(
                clipped_gradients={},
                original_norm=0.0,
                clipped_norm=0.0,
                was_clipped=False,
                clip_fraction=0.0,
            )

        original_norm = self._compute_norm(gradients)
        clipped_gradients = gradients.copy()
        total_count = len(gradients)

        if self.mode == ClipMode.NORM:
            # Norm clipping: scale gradients if norm exceeds max
            if original_norm > self.max_norm:
                scale = self.max_norm / original_norm
                clipped_gradients = {name: g * scale for name, g in gradients.items()}
                clipped_norm = self.max_norm
                was_clipped = True
                clip_fraction = 1.0  # All are scaled
                logger.debug(
                    "Norm clip: original_norm=%.4f, scale=%.4f", original_norm, scale
                )
            else:
                clipped_norm = original_norm
                was_clipped = False
                clip_fraction = 0.0

        elif self.mode == ClipMode.VALUE:
            # Value clipping: clip individual values
            clipped_count = 0
            for name in gradients:
                g = gradients[name]
                if abs(g) > self.max_value:
                    clipped_gradients[name] = math.copysign(self.max_value, g)
                    clipped_count += 1

            clipped_norm = self._compute_norm(clipped_gradients)
            was_clipped = clipped_count > 0
            clip_fraction = clipped_count / total_count if total_count > 0 else 0.0

            if was_clipped:
                logger.debug(
                    "Value clip: %d/%d gradients clipped to max_value=%.4f",
                    clipped_count,
                    total_count,
                    self.max_value,
                )

        return ClipResult(
            clipped_gradients=clipped_gradients,
            original_norm=original_norm,
            clipped_norm=clipped_norm,
            was_clipped=was_clipped,
            clip_fraction=clip_fraction,
        )

    def get_state(self) -> dict[str, Any]:
        """Get clipper state for checkpointing."""
        state: dict[str, Any] = {"mode": self.mode.value}
        if self.mode == ClipMode.NORM:
            state["max_norm"] = self.max_norm
        else:
            state["max_value"] = self.max_value
        return state

    @classmethod
    def from_state(cls, state: dict[str, Any]) -> GradientClipper:
        """Create clipper from saved state."""
        mode = ClipMode(state["mode"])
        if mode == ClipMode.NORM:
            return cls(mode=mode, max_norm=state["max_norm"])
        else:
            return cls(mode=mode, max_value=state["max_value"])
