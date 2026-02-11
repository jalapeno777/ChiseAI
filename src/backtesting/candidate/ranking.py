"""Candidate ranking engine with transparent scoring.

This module implements the ranking pipeline for candidate strategies,
applying uniform criteria and weights to produce composite scores.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Callable

from backtesting.candidate.models import (
    BacktestMetrics,
    CandidateResult,
    CandidateStatus,
    RankingConfig,
    RankingCriteria,
    RankingScore,
)


# Type alias for normalization functions
Normalizer = Callable[[float], float]


@dataclass
class CriteriaNormalizer:
    """Normalizer configuration for a ranking criterion.

    Attributes:
        criteria: The ranking criterion
        higher_is_better: Whether higher values are better
        min_value: Minimum expected value for normalization
        max_value: Maximum expected value for normalization
        transform: Optional transformation function
    """

    criteria: RankingCriteria
    higher_is_better: bool = True
    min_value: float = 0.0
    max_value: float = 100.0
    transform: Callable[[float], float] | None = None

    def normalize(self, value: float) -> float:
        """Normalize a raw value to 0-100 scale.

        Args:
            value: Raw metric value

        Returns:
            Normalized score (0-100)
        """
        # Apply transformation if provided
        if self.transform:
            value = self.transform(value)

        # Clamp to range
        clamped = max(self.min_value, min(self.max_value, value))

        # Normalize to 0-100
        range_size = self.max_value - self.min_value
        if range_size == 0:
            normalized = 50.0
        else:
            normalized = (clamped - self.min_value) / range_size * 100

        # Invert if lower is better
        if not self.higher_is_better:
            normalized = 100 - normalized

        return max(0.0, min(100.0, normalized))


class RankingEngine:
    """Engine for ranking candidate strategies.

    Applies uniform criteria and weights to calculate composite scores
    and rank candidates for paper trading selection.
    """

    # Default normalizers for each criterion
    DEFAULT_NORMALIZERS: dict[RankingCriteria, CriteriaNormalizer] = {
        RankingCriteria.SHARPE_RATIO: CriteriaNormalizer(
            criteria=RankingCriteria.SHARPE_RATIO,
            higher_is_better=True,
            min_value=-2.0,
            max_value=3.0,
        ),
        RankingCriteria.MAX_DRAWDOWN: CriteriaNormalizer(
            criteria=RankingCriteria.MAX_DRAWDOWN,
            higher_is_better=False,  # Lower drawdown is better
            min_value=0.0,
            max_value=50.0,
        ),
        RankingCriteria.WIN_RATE: CriteriaNormalizer(
            criteria=RankingCriteria.WIN_RATE,
            higher_is_better=True,
            min_value=0.0,
            max_value=100.0,
        ),
        RankingCriteria.PROFIT_FACTOR: CriteriaNormalizer(
            criteria=RankingCriteria.PROFIT_FACTOR,
            higher_is_better=True,
            min_value=0.0,
            max_value=5.0,
        ),
        RankingCriteria.TOTAL_RETURN: CriteriaNormalizer(
            criteria=RankingCriteria.TOTAL_RETURN,
            higher_is_better=True,
            min_value=-50.0,
            max_value=100.0,
        ),
        RankingCriteria.VOLATILITY: CriteriaNormalizer(
            criteria=RankingCriteria.VOLATILITY,
            higher_is_better=False,  # Lower volatility is better
            min_value=0.0,
            max_value=100.0,
        ),
        RankingCriteria.CALMAR_RATIO: CriteriaNormalizer(
            criteria=RankingCriteria.CALMAR_RATIO,
            higher_is_better=True,
            min_value=0.0,
            max_value=5.0,
        ),
        RankingCriteria.SORTINO_RATIO: CriteriaNormalizer(
            criteria=RankingCriteria.SORTINO_RATIO,
            higher_is_better=True,
            min_value=-2.0,
            max_value=5.0,
        ),
    }

    def __init__(
        self,
        config: RankingConfig | None = None,
        normalizers: dict[RankingCriteria, CriteriaNormalizer] | None = None,
    ):
        """Initialize ranking engine.

        Args:
            config: Ranking configuration with weights
            normalizers: Custom normalizers for criteria
        """
        self.config = config or RankingConfig()
        self.normalizers = normalizers or self.DEFAULT_NORMALIZERS.copy()

    def rank_candidates(
        self,
        candidates: list[CandidateResult],
    ) -> list[CandidateResult]:
        """Rank candidates by composite score.

                Calculates composite scores for all completed candidates,
        sorts by score (descending), and assigns rank positions.

                Args:
                    candidates: List of candidate results

                Returns:
                    Sorted list with rank positions assigned
        """
        # Calculate scores for eligible candidates
        scored_candidates = []
        for candidate in candidates:
            if candidate.status == CandidateStatus.COMPLETED:
                self._calculate_composite_score(candidate)
                scored_candidates.append(candidate)

        # Sort by composite score (descending)
        scored_candidates.sort(key=lambda c: c.composite_score, reverse=True)

        # Assign rank positions
        for i, candidate in enumerate(scored_candidates, start=1):
            candidate.rank_position = i

        return scored_candidates

    def get_top_candidates(
        self,
        candidates: list[CandidateResult],
        n: int | None = None,
    ) -> list[CandidateResult]:
        """Get top N candidates for paper trading.

        Args:
            candidates: List of candidate results
            n: Number of candidates to return (default: config.top_n_candidates)

        Returns:
            Top N candidates sorted by composite score
        """
        top_n = n or self.config.top_n_candidates
        ranked = self.rank_candidates(candidates)
        return ranked[:top_n]

    def _calculate_composite_score(self, candidate: CandidateResult) -> None:
        """Calculate composite score for a candidate.

        Args:
            candidate: Candidate result to score
        """
        scores = []
        total_weighted_score = 0.0

        for criteria, weight in self.config.criteria_weights.items():
            if weight <= 0:
                continue

            # Get raw value from metrics
            raw_value = self._get_metric_value(candidate.metrics, criteria)

            # Normalize
            normalizer = self.normalizers.get(criteria)
            if normalizer:
                normalized = normalizer.normalize(raw_value)
            else:
                normalized = self._default_normalize(raw_value)

            # Calculate weighted score
            weighted = normalized * weight
            total_weighted_score += weighted

            # Store ranking score
            scores.append(
                RankingScore(
                    criteria=criteria,
                    raw_value=raw_value,
                    normalized_score=normalized,
                    weight=weight,
                    weighted_score=weighted,
                )
            )

        candidate.ranking_scores = scores
        candidate.composite_score = total_weighted_score

    def _get_metric_value(
        self,
        metrics: BacktestMetrics,
        criteria: RankingCriteria,
    ) -> float:
        """Get metric value for a criterion.

        Args:
            metrics: Backtest metrics
            criteria: Ranking criterion

        Returns:
            Raw metric value
        """
        mapping = {
            RankingCriteria.SHARPE_RATIO: metrics.sharpe_ratio,
            RankingCriteria.MAX_DRAWDOWN: metrics.max_drawdown_pct,
            RankingCriteria.WIN_RATE: metrics.win_rate_pct,
            RankingCriteria.PROFIT_FACTOR: metrics.profit_factor,
            RankingCriteria.TOTAL_RETURN: metrics.total_return_pct,
            RankingCriteria.VOLATILITY: metrics.volatility_pct,
            RankingCriteria.CALMAR_RATIO: metrics.calmar_ratio,
            RankingCriteria.SORTINO_RATIO: metrics.sortino_ratio,
        }
        return mapping.get(criteria, 0.0)

    def _default_normalize(
        self, value: float, min_val: float = -10.0, max_val: float = 10.0
    ) -> float:
        """Default normalization for unknown criteria.

        Args:
            value: Raw value
            min_val: Minimum expected value
            max_val: Maximum expected value

        Returns:
            Normalized score (0-100)
        """
        clamped = max(min_val, min(max_val, value))
        range_size = max_val - min_val
        if range_size == 0:
            return 50.0
        return (clamped - min_val) / range_size * 100

    def get_ranking_breakdown(self, candidate: CandidateResult) -> dict:
        """Get detailed ranking breakdown for a candidate.

        Args:
            candidate: Candidate result

        Returns:
            Dictionary with ranking details
        """
        return {
            "candidate_id": candidate.candidate_id,
            "strategy_id": candidate.strategy_id,
            "composite_score": round(candidate.composite_score, 2),
            "rank_position": candidate.rank_position,
            "is_eligible_for_paper": candidate.is_eligible_for_paper(),
            "criteria_breakdown": [
                {
                    "criteria": score.criteria.value,
                    "raw_value": round(score.raw_value, 4),
                    "normalized_score": round(score.normalized_score, 2),
                    "weight": score.weight,
                    "weighted_score": round(score.weighted_score, 2),
                }
                for score in candidate.ranking_scores
            ],
        }

    def get_ranking_summary(self, candidates: list[CandidateResult]) -> dict:
        """Get summary statistics for a ranking run.

        Args:
            candidates: List of ranked candidates

        Returns:
            Dictionary with summary statistics
        """
        completed = [c for c in candidates if c.status == CandidateStatus.COMPLETED]
        scores = [c.composite_score for c in completed]

        if not scores:
            return {
                "total_candidates": len(candidates),
                "completed": 0,
                "failed": len(
                    [c for c in candidates if c.status == CandidateStatus.FAILED]
                ),
                "average_score": 0.0,
                "median_score": 0.0,
                "top_score": 0.0,
            }

        return {
            "total_candidates": len(candidates),
            "completed": len(completed),
            "failed": len(
                [c for c in candidates if c.status == CandidateStatus.FAILED]
            ),
            "disqualified": len(
                [c for c in candidates if c.status == CandidateStatus.DISQUALIFIED]
            ),
            "average_score": round(statistics.mean(scores), 2),
            "median_score": round(statistics.median(scores), 2),
            "top_score": round(max(scores), 2),
            "bottom_score": round(min(scores), 2),
            "top_3_candidates": [
                {
                    "rank": c.rank_position,
                    "candidate_id": c.candidate_id,
                    "strategy_id": c.strategy_id,
                    "composite_score": round(c.composite_score, 2),
                }
                for c in completed[:3]
            ],
        }
