"""Candidate backtesting models and data structures.

This module defines the data models for candidate strategy backtesting
including backtest results, ranking scores, and composite metrics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class CandidateStatus(Enum):
    """Status of a candidate strategy in the backtesting pipeline."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DISQUALIFIED = "disqualified"


class RankingCriteria(Enum):
    """Ranking criteria for candidate evaluation."""

    SHARPE_RATIO = "sharpe_ratio"
    MAX_DRAWDOWN = "max_drawdown"
    WIN_RATE = "win_rate"
    PROFIT_FACTOR = "profit_factor"
    TOTAL_RETURN = "total_return"
    VOLATILITY = "volatility"
    CALMAR_RATIO = "calmar_ratio"
    SORTINO_RATIO = "sortino_ratio"


@dataclass(frozen=True)
class WalkForwardWindow:
    """A single walk-forward window configuration.

    Attributes:
        train_start: Start of training period
        train_end: End of training period
        test_start: Start of test period
        test_end: End of test period
    """

    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime

    def __post_init__(self) -> None:
        """Validate window configuration."""
        if self.train_end <= self.train_start:
            raise ValueError("train_end must be after train_start")
        if self.test_end <= self.test_start:
            raise ValueError("test_end must be after test_start")
        if self.test_start < self.train_end:
            raise ValueError("test_start must be >= train_end (no overlap)")


@dataclass
class BacktestMetrics:
    """Comprehensive backtest metrics for a candidate strategy.

    Attributes:
        sharpe_ratio: Risk-adjusted return metric
        max_drawdown_pct: Maximum peak-to-trough decline (%)
        win_rate_pct: Percentage of winning trades
        profit_factor: Gross profit / gross loss
        total_return_pct: Total strategy return (%)
        volatility_pct: Standard deviation of returns (%)
        calmar_ratio: Annual return / max drawdown
        sortino_ratio: Return / downside deviation
        trade_count: Total number of trades
        avg_trade_return_pct: Average return per trade (%)
        avg_win_pct: Average winning trade return (%)
        avg_loss_pct: Average losing trade return (%)
        largest_win_pct: Largest single winning trade (%)
        largest_loss_pct: Largest single losing trade (%)
        consecutive_wins: Maximum consecutive winning trades
        consecutive_losses: Maximum consecutive losing trades
    """

    # Core metrics
    sharpe_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    win_rate_pct: float = 0.0
    profit_factor: float = 0.0
    total_return_pct: float = 0.0
    volatility_pct: float = 0.0
    calmar_ratio: float = 0.0
    sortino_ratio: float = 0.0

    # Trade statistics
    trade_count: int = 0
    avg_trade_return_pct: float = 0.0
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0
    largest_win_pct: float = 0.0
    largest_loss_pct: float = 0.0
    consecutive_wins: int = 0
    consecutive_losses: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary for serialization."""
        return {
            "sharpe_ratio": self.sharpe_ratio,
            "max_drawdown_pct": self.max_drawdown_pct,
            "win_rate_pct": self.win_rate_pct,
            "profit_factor": self.profit_factor,
            "total_return_pct": self.total_return_pct,
            "volatility_pct": self.volatility_pct,
            "calmar_ratio": self.calmar_ratio,
            "sortino_ratio": self.sortino_ratio,
            "trade_count": self.trade_count,
            "avg_trade_return_pct": self.avg_trade_return_pct,
            "avg_win_pct": self.avg_win_pct,
            "avg_loss_pct": self.avg_loss_pct,
            "largest_win_pct": self.largest_win_pct,
            "largest_loss_pct": self.largest_loss_pct,
            "consecutive_wins": self.consecutive_wins,
            "consecutive_losses": self.consecutive_losses,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BacktestMetrics:
        """Create metrics from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class RankingScore:
    """Individual ranking criterion score with weight.

    Attributes:
        criteria: The ranking criterion
        raw_value: Raw metric value
        normalized_score: Normalized score (0-100)
        weight: Weight in composite calculation (0-1)
        weighted_score: normalized_score * weight
    """

    criteria: RankingCriteria
    raw_value: float
    normalized_score: float
    weight: float
    weighted_score: float

    def __post_init__(self) -> None:
        """Validate score values."""
        if not 0 <= self.normalized_score <= 100:
            raise ValueError(
                f"normalized_score must be 0-100, got {self.normalized_score}"
            )
        if not 0 <= self.weight <= 1:
            raise ValueError(f"weight must be 0-1, got {self.weight}")


@dataclass
class CandidateResult:
    """Complete backtest result for a candidate strategy.

    Attributes:
        candidate_id: Unique identifier for the candidate
        strategy_id: Reference to parent strategy
        version: Strategy version string
        status: Current status in pipeline
        window: Walk-forward window used
        metrics: Backtest metrics
        ranking_scores: Individual criterion scores
        composite_score: Final composite ranking score
        rank_position: Rank among all candidates (1-based)
        created_at: Result creation timestamp
        completed_at: Completion timestamp (if completed)
        error_message: Error details (if failed)
    """

    candidate_id: str
    strategy_id: str
    version: str
    status: CandidateStatus
    window: WalkForwardWindow
    metrics: BacktestMetrics = field(default_factory=BacktestMetrics)
    ranking_scores: list[RankingScore] = field(default_factory=list)
    composite_score: float = 0.0
    rank_position: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    error_message: str | None = None

    def is_eligible_for_paper(self, min_composite_score: float = 60.0) -> bool:
        """Check if candidate is eligible for paper trading.

        Args:
            min_composite_score: Minimum composite score required

        Returns:
            True if eligible for paper trading
        """
        return (
            self.status == CandidateStatus.COMPLETED
            and self.composite_score >= min_composite_score
            and self.metrics.sharpe_ratio > 0
            and self.metrics.max_drawdown_pct < 20.0
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary for serialization."""
        return {
            "candidate_id": self.candidate_id,
            "strategy_id": self.strategy_id,
            "version": self.version,
            "status": self.status.value,
            "window": {
                "train_start": self.window.train_start.isoformat(),
                "train_end": self.window.train_end.isoformat(),
                "test_start": self.window.test_start.isoformat(),
                "test_end": self.window.test_end.isoformat(),
            },
            "metrics": self.metrics.to_dict(),
            "ranking_scores": [
                {
                    "criteria": s.criteria.value,
                    "raw_value": s.raw_value,
                    "normalized_score": s.normalized_score,
                    "weight": s.weight,
                    "weighted_score": s.weighted_score,
                }
                for s in self.ranking_scores
            ],
            "composite_score": self.composite_score,
            "rank_position": self.rank_position,
            "created_at": self.created_at.isoformat(),
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "error_message": self.error_message,
        }


@dataclass
class RankingConfig:
    """Configuration for candidate ranking.

    Attributes:
        criteria_weights: Dict mapping criteria to weight (0-1)
        min_sharpe_ratio: Minimum Sharpe ratio for eligibility
        max_drawdown_threshold: Maximum drawdown % for eligibility
        min_win_rate: Minimum win rate % for eligibility
        top_n_candidates: Number of top candidates to select
    """

    criteria_weights: dict[RankingCriteria, float] = field(
        default_factory=lambda: {
            RankingCriteria.SHARPE_RATIO: 0.30,
            RankingCriteria.MAX_DRAWDOWN: 0.25,
            RankingCriteria.WIN_RATE: 0.20,
            RankingCriteria.PROFIT_FACTOR: 0.15,
            RankingCriteria.CALMAR_RATIO: 0.10,
        }
    )
    min_sharpe_ratio: float = 0.5
    max_drawdown_threshold: float = 20.0
    min_win_rate: float = 45.0
    top_n_candidates: int = 3

    def __post_init__(self) -> None:
        """Validate configuration."""
        total_weight = sum(self.criteria_weights.values())
        if not 0.99 <= total_weight <= 1.01:  # Allow small floating point errors
            raise ValueError(f"Criteria weights must sum to 1.0, got {total_weight}")
        for criteria, weight in self.criteria_weights.items():
            if not 0 <= weight <= 1:
                raise ValueError(
                    f"Weight for {criteria.value} must be 0-1, got {weight}"
                )

    def get_weight(self, criteria: RankingCriteria) -> float:
        """Get weight for a specific criterion."""
        return self.criteria_weights.get(criteria, 0.0)
