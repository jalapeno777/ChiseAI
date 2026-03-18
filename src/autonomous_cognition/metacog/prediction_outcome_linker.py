"""Prediction-outcome linking for calibration and feedback loops."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PredictionOutcomePair:
    """Pair of prediction confidence and realized outcome."""

    confidence: float
    success: bool


class PredictionOutcomeLinker:
    """Links prediction confidence and realized outcomes."""

    def link(
        self, confidences: list[float], outcomes: list[bool]
    ) -> list[PredictionOutcomePair]:
        """Create aligned prediction-outcome pairs."""
        size = min(len(confidences), len(outcomes))
        return [
            PredictionOutcomePair(
                confidence=float(confidences[i]), success=bool(outcomes[i])
            )
            for i in range(size)
        ]
