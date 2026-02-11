"""Candidate backtesting candidate submodule.

This submodule contains the core candidate backtesting implementation.
"""

from backtesting.candidate.influx_storage import CandidateResultStorage
from backtesting.candidate.models import (
    BacktestMetrics,
    CandidateResult,
    CandidateStatus,
    RankingConfig,
    RankingCriteria,
    RankingScore,
    WalkForwardWindow,
)
from backtesting.candidate.pipeline import (
    CandidateBacktestPipeline,
    PipelineConfig,
)
from backtesting.candidate.ranking import CriteriaNormalizer, RankingEngine
from backtesting.candidate.walk_forward import (
    WalkForwardConfig,
    WalkForwardEngine,
)

__all__ = [
    # Models
    "BacktestMetrics",
    "CandidateResult",
    "CandidateStatus",
    "RankingConfig",
    "RankingCriteria",
    "RankingScore",
    "WalkForwardWindow",
    # Pipeline
    "CandidateBacktestPipeline",
    "PipelineConfig",
    # Ranking
    "CriteriaNormalizer",
    "RankingEngine",
    # Walk-forward
    "WalkForwardConfig",
    "WalkForwardEngine",
    # Storage
    "CandidateResultStorage",
]
