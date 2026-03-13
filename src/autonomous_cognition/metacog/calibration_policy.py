"""Calibration policy updates for autonomous cognition."""

from __future__ import annotations

from autonomous_cognition.metacog.prediction_outcome_linker import (
    PredictionOutcomePair,
)


class CalibrationPolicy:
    """Computes calibration error and threshold suggestions."""

    def compute_ece(self, pairs: list[PredictionOutcomePair]) -> float:
        """Compute a simple expected calibration error approximation."""
        if not pairs:
            return 0.0
        err = 0.0
        for pair in pairs:
            observed = 1.0 if pair.success else 0.0
            err += abs(pair.confidence - observed)
        return err / len(pairs)

    def recommend_confidence_offset(self, ece: float) -> float:
        """Recommend confidence offset from current ECE."""
        if ece <= 0.05:
            return 0.0
        if ece <= 0.10:
            return -0.03
        if ece <= 0.20:
            return -0.07
        return -0.12

