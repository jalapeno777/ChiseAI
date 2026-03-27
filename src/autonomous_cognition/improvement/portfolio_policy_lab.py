"""Portfolio policy lab for evaluating strategy alternatives.

This module provides the PortfolioPolicyLab class which runs deterministic
pseudo-experiments for bounded autonomous evaluation of hypotheses.
It produces comparable candidate metrics for champion-challenger evaluation.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from autonomous_cognition.improvement.hypothesis_generator import Hypothesis
from autonomous_cognition.improvement.scoring import composite_score


@dataclass
class ExperimentMetrics:
    """Performance metrics from a policy lab experiment.

    Attributes:
        sharpe: Sharpe ratio (risk-adjusted returns)
        sortino: Sortino ratio (downside risk-adjusted)
        drawdown: Maximum drawdown percentage
        ece: Expected Calibration Error
        win_rate: Percentage of profitable trades
        turnover: Portfolio turnover rate
    """

    sharpe: float
    sortino: float
    drawdown: float
    ece: float
    win_rate: float = 0.55
    turnover: float = 0.15


@dataclass
class ExperimentResult:
    """Result of running one hypothesis in policy lab.

    Attributes:
        hypothesis_id: ID of the hypothesis evaluated
        metrics: Performance metrics from the experiment
        passed: Whether the experiment passed minimum thresholds
        details: Additional experiment details
    """

    hypothesis_id: str
    metrics: ExperimentMetrics
    passed: bool
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "hypothesis_id": self.hypothesis_id,
            "metrics": {
                "sharpe": self.metrics.sharpe,
                "sortino": self.metrics.sortino,
                "drawdown": self.metrics.drawdown,
                "ece": self.metrics.ece,
                "win_rate": self.metrics.win_rate,
                "turnover": self.metrics.turnover,
            },
            "passed": self.passed,
            "details": self.details,
        }


@dataclass
class PortfolioPolicyLabConfig:
    """Configuration for portfolio policy lab.

    Attributes:
        min_sharpe: Minimum Sharpe ratio to pass
        max_drawdown: Maximum drawdown percentage to pass
        max_ece: Maximum ECE to pass
        seed: Optional seed for deterministic results
    """

    min_sharpe: float = 1.1
    max_drawdown: float = 0.20
    max_ece: float = 0.15


class PortfolioPolicyLab:
    """Runs deterministic pseudo-experiments for bounded autonomous evaluation.

    Evaluates hypotheses against portfolio policy criteria and produces
    comparable metrics for champion-challenger comparison.

    Example:
        >>> config = PortfolioPolicyLabConfig()
        >>> lab = PortfolioPolicyLab(config)
        >>> hypothesis = Hypothesis(...)
        >>> result = lab.run(hypothesis)
    """

    # Gate thresholds for experiment pass/fail
    GATE_SHARPE = 1.1
    GATE_SORTINO = 1.2
    GATE_DRAWDOWN = 0.20
    GATE_ECE = 0.15

    def __init__(self, config: PortfolioPolicyLabConfig | None = None):
        """Initialize the portfolio policy lab.

        Args:
            config: Optional configuration. Uses defaults if not provided.
        """
        self._config = config or PortfolioPolicyLabConfig()

    def run(self, hypothesis: Hypothesis) -> ExperimentResult:
        """Run one hypothesis and produce comparable candidate metrics.

        Uses deterministic pseudo-random generation based on hypothesis ID
        to ensure reproducible results.

        Args:
            hypothesis: The hypothesis to evaluate

        Returns:
            Experiment result with metrics and pass/fail status
        """
        seed = int(
            hashlib.sha256(hypothesis.hypothesis_id.encode("utf-8")).hexdigest()[:8], 16
        )

        # Generate deterministic metrics from seed
        sharpe = 0.9 + (seed % 60) / 100
        sortino = sharpe + 0.1 + ((seed // 10) % 20) / 100
        drawdown = 0.08 + ((seed // 10) % 18) / 100
        ece = 0.04 + ((seed // 100) % 10) / 100
        win_rate = 0.52 + ((seed // 1000) % 15) / 100
        turnover = 0.10 + ((seed // 10000) % 10) / 100

        metrics = ExperimentMetrics(
            sharpe=round(sharpe, 3),
            sortino=round(sortino, 3),
            drawdown=round(drawdown, 3),
            ece=round(ece, 3),
            win_rate=round(win_rate, 3),
            turnover=round(turnover, 3),
        )

        # Determine pass/fail based on config thresholds
        passed = (
            sharpe >= self._config.min_sharpe
            and sortino >= self._config.min_sharpe + 0.1  # sortino gate is relative
            and drawdown <= self._config.max_drawdown
            and ece <= self._config.max_ece
        )

        return ExperimentResult(
            hypothesis_id=hypothesis.hypothesis_id,
            metrics=metrics,
            passed=passed,
            details={
                "seed": seed,
                "gates_sharpe": self._config.min_sharpe,
                "gates_sortino": self._config.min_sharpe + 0.1,
                "gates_drawdown": self._config.max_drawdown,
                "gates_ece": self._config.max_ece,
            },
        )

    def run_batch(self, hypotheses: list[Hypothesis]) -> dict[str, ExperimentResult]:
        """Run multiple hypotheses and return results keyed by hypothesis ID.

        Args:
            hypotheses: List of hypotheses to evaluate

        Returns:
            Dictionary mapping hypothesis_id -> ExperimentResult
        """
        results = {}
        for hypothesis in hypotheses:
            results[hypothesis.hypothesis_id] = self.run(hypothesis)
        return results

    def compare(self, result_a: ExperimentResult, result_b: ExperimentResult) -> str:
        """Compare two experiment results.

        Args:
            result_a: First experiment result
            result_b: Second experiment result

        Returns:
            String describing which is better: 'a', 'b', or 'tie'
        """

        # Score based on weighted metrics
        score_a = composite_score(
            {
                "sharpe": result_a.metrics.sharpe,
                "sortino": result_a.metrics.sortino,
                "drawdown": result_a.metrics.drawdown,
                "ece": result_a.metrics.ece,
            }
        )
        score_b = composite_score(
            {
                "sharpe": result_b.metrics.sharpe,
                "sortino": result_b.metrics.sortino,
                "drawdown": result_b.metrics.drawdown,
                "ece": result_b.metrics.ece,
            }
        )

        if score_a > score_b:
            return "a"
        elif score_b > score_a:
            return "b"
        return "tie"
