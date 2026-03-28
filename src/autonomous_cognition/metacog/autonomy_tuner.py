"""Autonomy level tuning based on calibration and incident trends.

.. deprecated::
    This module is a stub. Use :mod:`autonomous_cognition.autonomy_tuner`
    for the full production implementation.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass


def __getattr__(name: str):
    """Deprecation shim to redirect to the production module."""
    if name == "AutonomyTuner":
        warnings.warn(
            "autonomous_cognition.metacog.autonomy_tuner is deprecated. "
            "Use autonomous_cognition.autonomy_tuner instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        from autonomous_cognition.autonomy_tuner import AutonomyTuner as AT

        return AT
    if name == "AutonomyTuningDecision":
        warnings.warn(
            "autonomous_cognition.metacog.autonomy_tuner is deprecated. "
            "Use autonomous_cognition.autonomy_tuner instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        from autonomous_cognition.autonomy_tuner import (
            AutonomyTuningDecision as ATD,
        )

        return ATD
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


@dataclass
class AutonomyTuningDecision:
    """Decision record for autonomy level tuning."""

    previous_level: str
    new_level: str
    reason: str


class AutonomyTuner:
    """Tunes autonomy level with conservative safety-first logic."""

    _levels = ["supervised", "bounded", "assisted", "autonomous"]

    def tune(
        self,
        current_level: str,
        ece: float,
        incident_count: int,
    ) -> AutonomyTuningDecision:
        """Tune autonomy level from current metrics."""
        level = current_level if current_level in self._levels else "supervised"
        idx = self._levels.index(level)

        if incident_count > 0 or ece > 0.15:
            new_idx = max(0, idx - 1)
            reason = "regression_guardrail_triggered"
        elif ece < 0.08 and incident_count == 0:
            new_idx = min(len(self._levels) - 1, idx + 1)
            reason = "sustained_calibration_stability"
        else:
            new_idx = idx
            reason = "hold_level"

        return AutonomyTuningDecision(
            previous_level=level,
            new_level=self._levels[new_idx],
            reason=reason,
        )
