"""Portfolio policy experiment runner for autonomous candidate evaluation."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from autonomous_cognition.experiments.hypothesis_generator import Hypothesis


@dataclass
class ExperimentResult:
    """Result of running one hypothesis in policy lab."""

    hypothesis_id: str
    sharpe: float
    sortino: float
    drawdown: float
    ece: float
    passed: bool

    def to_metrics(self) -> dict[str, float]:
        """Map result to promotion metric bundle."""
        return {
            "sharpe": self.sharpe,
            "sortino": self.sortino,
            "drawdown": self.drawdown,
            "ece": self.ece,
        }


class PortfolioPolicyLab:
    """Runs deterministic pseudo-experiments for bounded autonomous evaluation."""

    def run(self, hypothesis: Hypothesis) -> ExperimentResult:
        """Run one hypothesis and produce comparable candidate metrics."""
        seed = int(
            hashlib.sha256(hypothesis.hypothesis_id.encode("utf-8")).hexdigest()[:8], 16
        )
        sharpe = 0.9 + (seed % 60) / 100
        sortino = sharpe + 0.1
        drawdown = 0.08 + ((seed // 10) % 18) / 100
        ece = 0.04 + ((seed // 100) % 10) / 100
        passed = sharpe >= 1.1 and drawdown <= 0.2 and ece <= 0.15
        return ExperimentResult(
            hypothesis_id=hypothesis.hypothesis_id,
            sharpe=round(sharpe, 3),
            sortino=round(sortino, 3),
            drawdown=round(drawdown, 3),
            ece=round(ece, 3),
            passed=passed,
        )
