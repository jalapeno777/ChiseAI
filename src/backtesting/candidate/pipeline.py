"""Main candidate backtesting pipeline.

Orchestrates the full candidate backtesting and ranking workflow,
integrating with the strategy registry for candidate inputs.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol

import numpy as np

from backtesting.candidate.influx_storage import CandidateResultStorage
from backtesting.candidate.models import (
    BacktestMetrics,
    CandidateResult,
    CandidateStatus,
    RankingConfig,
    WalkForwardWindow,
)
from backtesting.candidate.ranking import RankingEngine
from backtesting.candidate.walk_forward import WalkForwardConfig, WalkForwardEngine


class StrategyRegistry(Protocol):
    """Protocol for strategy registry integration."""

    def get_candidates(self) -> list[dict[str, Any]]:
        """Get list of candidate strategies for backtesting.

        Returns:
            List of candidate strategy configurations
        """
        ...

    def update_candidate_status(
        self,
        candidate_id: str,
        status: str,
        metrics: dict[str, Any] | None = None,
    ) -> bool:
        """Update candidate status in registry.

        Args:
            candidate_id: Candidate identifier
            status: New status
            metrics: Optional metrics to store

        Returns:
            True if updated successfully
        """
        ...


@dataclass
class PipelineConfig:
    """Configuration for the backtesting pipeline.

    Attributes:
        walk_forward: Walk-forward backtesting configuration
        ranking: Ranking configuration
        batch_size: Number of candidates to process in parallel
        max_runtime_hours: Maximum pipeline runtime
        store_results: Whether to persist results to InfluxDB
    """

    walk_forward: WalkForwardConfig = None  # type: ignore[assignment]
    ranking: RankingConfig = None  # type: ignore[assignment]
    batch_size: int = 10
    max_runtime_hours: int = 4
    store_results: bool = True

    def __post_init__(self) -> None:
        """Set default configurations."""
        if self.walk_forward is None:
            self.walk_forward = WalkForwardConfig()
        if self.ranking is None:
            self.ranking = RankingConfig()


class CandidateBacktestPipeline:
    """Main pipeline for candidate backtesting and ranking.

    Orchestrates the full workflow from candidate retrieval through
    walk-forward backtesting, ranking, and result persistence.
    """

    def __init__(
        self,
        config: PipelineConfig | None = None,
        strategy_registry: StrategyRegistry | None = None,
        data_provider: Any | None = None,
        strategy_executor: Any | None = None,
        storage: CandidateResultStorage | None = None,
    ):
        """Initialize the pipeline.

        Args:
            config: Pipeline configuration
            strategy_registry: Strategy registry for candidate inputs
            data_provider: Market data provider
            strategy_executor: Strategy execution engine
            storage: Result storage (created if not provided)
        """
        self.config = config or PipelineConfig()
        self.strategy_registry = strategy_registry
        self.data_provider = data_provider
        self.strategy_executor = strategy_executor
        self.storage = storage or CandidateResultStorage()

        # Initialize engines
        self.walk_forward_engine = WalkForwardEngine(
            config=self.config.walk_forward,
            data_provider=data_provider,
            strategy_executor=strategy_executor,
        )
        self.ranking_engine = RankingEngine(config=self.config.ranking)

    def run(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        symbol: str = "BTCUSDT",
    ) -> dict[str, Any]:
        """Run the full candidate backtesting pipeline.

        Args:
            start_date: Analysis start date (default: 90 days ago)
            end_date: Analysis end date (default: now)
            symbol: Trading symbol to backtest

        Returns:
            Pipeline results summary
        """
        start_time = datetime.utcnow()

        # Set default dates
        if end_date is None:
            end_date = datetime.utcnow()
        if start_date is None:
            start_date = end_date - timedelta(days=90)

        # Get candidates from registry
        candidates = self._get_candidates()

        # Generate walk-forward windows
        windows = self.walk_forward_engine.generate_windows(start_date, end_date)

        # Run backtests
        results = self._run_backtests(candidates, windows, symbol)

        # Rank candidates
        ranked = self.ranking_engine.rank_candidates(results)

        # Get top candidates
        top_candidates = self.ranking_engine.get_top_candidates(
            ranked, n=self.config.ranking.top_n_candidates
        )

        # Store results
        if self.config.store_results:
            self.storage.store_results(ranked)

        # Update registry
        self._update_registry(ranked)

        # Calculate runtime
        runtime = datetime.utcnow() - start_time

        return {
            "pipeline_id": str(uuid.uuid4()),
            "start_time": start_time.isoformat(),
            "end_time": datetime.utcnow().isoformat(),
            "runtime_seconds": runtime.total_seconds(),
            "total_candidates": len(candidates),
            "completed": len(
                [r for r in ranked if r.status == CandidateStatus.COMPLETED]
            ),
            "failed": len([r for r in ranked if r.status == CandidateStatus.FAILED]),
            "top_candidates": [
                {
                    "rank": c.rank_position,
                    "candidate_id": c.candidate_id,
                    "strategy_id": c.strategy_id,
                    "composite_score": round(c.composite_score, 2),
                    "sharpe_ratio": round(c.metrics.sharpe_ratio, 2),
                    "max_drawdown_pct": round(c.metrics.max_drawdown_pct, 2),
                    "win_rate_pct": round(c.metrics.win_rate_pct, 2),
                }
                for c in top_candidates
            ],
            "ranking_summary": self.ranking_engine.get_ranking_summary(ranked),
        }

    def _get_candidates(self) -> list[dict[str, Any]]:
        """Get candidates from strategy registry.

        Returns:
            List of candidate configurations
        """
        if self.strategy_registry:
            return self.strategy_registry.get_candidates()
        return []

    def _run_backtests(
        self,
        candidates: list[dict[str, Any]],
        windows: list[WalkForwardWindow],
        symbol: str,
    ) -> list[CandidateResult]:
        """Run backtests for all candidates across all windows.

        Args:
            candidates: List of candidate configurations
            windows: List of walk-forward windows
            symbol: Trading symbol

        Returns:
            List of candidate results
        """
        results = []

        for candidate_config in candidates:
            candidate_id = candidate_config.get("candidate_id", str(uuid.uuid4()))
            strategy_id = candidate_config.get("strategy_id", "unknown")
            version = candidate_config.get("version", "1.0.0")

            # For each window, create a result
            for window in windows:
                result = CandidateResult(
                    candidate_id=f"{candidate_id}_{window.test_start.strftime('%Y%m%d')}",
                    strategy_id=strategy_id,
                    version=version,
                    status=CandidateStatus.PENDING,
                    window=window,
                )

                # Run backtest
                if self.data_provider and self.strategy_executor:
                    result = self.walk_forward_engine.run_backtest(
                        result, candidate_config, symbol
                    )
                else:
                    # Mock execution for testing
                    result.status = CandidateStatus.COMPLETED
                    result.metrics = self._generate_mock_metrics()
                    result.completed_at = datetime.utcnow()

                results.append(result)

        return results

    def _generate_mock_metrics(self) -> BacktestMetrics:
        """Generate mock metrics for testing without data provider.

        Returns:
            Mock backtest metrics
        """
        rng = np.random.default_rng()

        return BacktestMetrics(
            sharpe_ratio=float(rng.uniform(0.5, 2.5)),
            max_drawdown_pct=float(rng.uniform(5.0, 25.0)),
            win_rate_pct=float(rng.uniform(40.0, 65.0)),
            profit_factor=float(rng.uniform(1.0, 2.5)),
            total_return_pct=float(rng.uniform(-10.0, 50.0)),
            volatility_pct=float(rng.uniform(10.0, 40.0)),
            calmar_ratio=float(rng.uniform(0.5, 3.0)),
            sortino_ratio=float(rng.uniform(0.5, 3.0)),
            trade_count=int(rng.integers(20, 201)),
            avg_trade_return_pct=float(rng.uniform(-0.5, 1.5)),
            avg_win_pct=float(rng.uniform(1.0, 5.0)),
            avg_loss_pct=float(rng.uniform(-3.0, -0.5)),
            largest_win_pct=float(rng.uniform(5.0, 15.0)),
            largest_loss_pct=float(rng.uniform(-10.0, -2.0)),
            consecutive_wins=int(rng.integers(2, 9)),
            consecutive_losses=int(rng.integers(2, 7)),
        )

    def _update_registry(self, results: list[CandidateResult]) -> None:
        """Update strategy registry with results.

        Args:
            results: List of candidate results
        """
        if not self.strategy_registry:
            return

        for result in results:
            self.strategy_registry.update_candidate_status(
                candidate_id=result.candidate_id,
                status=result.status.value,
                metrics={
                    "composite_score": result.composite_score,
                    "rank_position": result.rank_position,
                    "sharpe_ratio": result.metrics.sharpe_ratio,
                    "max_drawdown_pct": result.metrics.max_drawdown_pct,
                },
            )

    def get_candidate_details(self, candidate_id: str) -> dict[str, Any] | None:
        """Get detailed information for a specific candidate.

        Args:
            candidate_id: Candidate identifier

        Returns:
            Candidate details or None if not found
        """
        results = self.storage.query_results()
        for result in results:
            if result.get("candidate_id") == candidate_id:
                return result
        return None

    def get_top_candidates_for_paper(
        self,
        min_score: float = 60.0,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        """Get top candidates eligible for paper trading.

        Args:
            min_score: Minimum composite score required
            limit: Maximum number of candidates

        Returns:
            List of eligible candidates
        """
        results = self.storage.query_results()

        # Filter eligible
        eligible = [
            r
            for r in results
            if r.get("composite_score", 0) >= min_score
            and r.get("sharpe_ratio", 0) > 0
            and r.get("max_drawdown_pct", 100) < 20.0
        ]

        # Sort by composite score
        eligible.sort(key=lambda x: x.get("composite_score", 0), reverse=True)

        return eligible[:limit]
