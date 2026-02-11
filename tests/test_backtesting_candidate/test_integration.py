"""Tests for backtesting candidate module integration."""

from datetime import datetime

from backtesting.candidate import (
    BacktestMetrics,
    CandidateResult,
    CandidateStatus,
    CriteriaNormalizer,
    PipelineConfig,
    RankingConfig,
    RankingCriteria,
    RankingEngine,
    WalkForwardConfig,
    WalkForwardEngine,
    WalkForwardWindow,
)


class TestModuleIntegration:
    """Integration tests for the candidate backtesting module."""

    def test_full_workflow(self) -> None:
        """Test the full candidate backtesting workflow."""
        # Create walk-forward windows
        wf_config = WalkForwardConfig(train_days=30, test_days=7, step_days=7)
        wf_engine = WalkForwardEngine(config=wf_config)

        start = datetime(2024, 1, 1)
        end = datetime(2024, 4, 1)
        windows = wf_engine.generate_windows(start, end)

        assert len(windows) > 0

        # Create candidate results
        results = []
        for i, window in enumerate(windows[:3]):  # Use first 3 windows
            result = CandidateResult(
                candidate_id=f"cand-{i:03d}",
                strategy_id="strategy-001",
                version="1.0.0",
                status=CandidateStatus.COMPLETED,
                window=window,
            )
            # Simulate different performance
            result.metrics = BacktestMetrics(
                sharpe_ratio=0.5 + i * 0.5,  # 0.5, 1.0, 1.5
                max_drawdown_pct=20.0 - i * 3,  # 20, 17, 14
                win_rate_pct=45.0 + i * 5,  # 45, 50, 55
                profit_factor=1.2 + i * 0.2,
                total_return_pct=10.0 + i * 10,
            )
            results.append(result)

        # Rank candidates
        ranking_config = RankingConfig()
        ranking_engine = RankingEngine(config=ranking_config)
        ranked = ranking_engine.rank_candidates(results)

        # Verify ranking
        assert len(ranked) == 3
        assert ranked[0].rank_position == 1
        assert ranked[0].composite_score > ranked[1].composite_score

        # Get top candidates
        top = ranking_engine.get_top_candidates(ranked, n=2)
        assert len(top) == 2

        # Verify top candidate has best metrics
        assert top[0].metrics.sharpe_ratio == 1.5

    def test_ranking_transparency(self) -> None:
        """Test that ranking is transparent with visible criteria."""
        window = WalkForwardWindow(
            train_start=datetime(2024, 1, 1),
            train_end=datetime(2024, 1, 31),
            test_start=datetime(2024, 1, 31),
            test_end=datetime(2024, 2, 7),
        )

        result = CandidateResult(
            candidate_id="test-001",
            strategy_id="strategy-001",
            version="1.0.0",
            status=CandidateStatus.COMPLETED,
            window=window,
        )
        result.metrics = BacktestMetrics(
            sharpe_ratio=1.5,
            max_drawdown_pct=15.0,
            win_rate_pct=55.0,
            profit_factor=1.8,
            total_return_pct=25.0,
            calmar_ratio=1.67,
        )

        ranking_engine = RankingEngine()
        ranking_engine._calculate_composite_score(result)

        # Check breakdown
        breakdown = ranking_engine.get_ranking_breakdown(result)
        assert breakdown["candidate_id"] == "test-001"
        assert "criteria_breakdown" in breakdown
        assert len(breakdown["criteria_breakdown"]) > 0

        # Verify each criterion has required fields
        for criterion in breakdown["criteria_breakdown"]:
            assert "criteria" in criterion
            assert "raw_value" in criterion
            assert "normalized_score" in criterion
            assert "weight" in criterion
            assert "weighted_score" in criterion

    def test_walk_forward_30d_train_7d_test(self) -> None:
        """Test walk-forward with 30-day train, 7-day test windows."""
        config = WalkForwardConfig(train_days=30, test_days=7, step_days=7)
        engine = WalkForwardEngine(config=config)

        start = datetime(2024, 1, 1)
        end = datetime(2024, 6, 1)

        windows = engine.generate_windows(start, end)

        assert len(windows) > 0

        for window in windows:
            # Verify 30-day train window
            train_duration = (window.train_end - window.train_start).days
            assert train_duration == 30

            # Verify 7-day test window
            test_duration = (window.test_end - window.test_start).days
            assert test_duration == 7

            # Verify no overlap
            assert window.test_start >= window.train_end

    def test_paper_eligibility(self) -> None:
        """Test paper trading eligibility criteria."""
        window = WalkForwardWindow(
            train_start=datetime(2024, 1, 1),
            train_end=datetime(2024, 1, 31),
            test_start=datetime(2024, 1, 31),
            test_end=datetime(2024, 2, 7),
        )

        # Eligible candidate
        eligible = CandidateResult(
            candidate_id="eligible",
            strategy_id="strategy-001",
            version="1.0.0",
            status=CandidateStatus.COMPLETED,
            window=window,
            composite_score=75.0,
        )
        eligible.metrics = BacktestMetrics(sharpe_ratio=1.5, max_drawdown_pct=15.0)

        # Not eligible - low score
        low_score = CandidateResult(
            candidate_id="low-score",
            strategy_id="strategy-001",
            version="1.0.0",
            status=CandidateStatus.COMPLETED,
            window=window,
            composite_score=50.0,
        )
        low_score.metrics = BacktestMetrics(sharpe_ratio=1.5, max_drawdown_pct=15.0)

        # Not eligible - high drawdown
        high_dd = CandidateResult(
            candidate_id="high-dd",
            strategy_id="strategy-001",
            version="1.0.0",
            status=CandidateStatus.COMPLETED,
            window=window,
            composite_score=75.0,
        )
        high_dd.metrics = BacktestMetrics(sharpe_ratio=1.5, max_drawdown_pct=25.0)

        # Not eligible - negative sharpe
        neg_sharpe = CandidateResult(
            candidate_id="neg-sharpe",
            strategy_id="strategy-001",
            version="1.0.0",
            status=CandidateStatus.COMPLETED,
            window=window,
            composite_score=75.0,
        )
        neg_sharpe.metrics = BacktestMetrics(sharpe_ratio=-0.5, max_drawdown_pct=15.0)

        assert eligible.is_eligible_for_paper() is True
        assert low_score.is_eligible_for_paper() is False
        assert high_dd.is_eligible_for_paper() is False
        assert neg_sharpe.is_eligible_for_paper() is False

    def test_ranking_summary(self) -> None:
        """Test ranking summary generation."""
        window = WalkForwardWindow(
            train_start=datetime(2024, 1, 1),
            train_end=datetime(2024, 1, 31),
            test_start=datetime(2024, 1, 31),
            test_end=datetime(2024, 2, 7),
        )

        candidates = [
            CandidateResult(
                candidate_id=f"cand-{i:03d}",
                strategy_id="strategy-001",
                version="1.0.0",
                status=CandidateStatus.COMPLETED,
                window=window,
            )
            for i in range(5)
        ]

        # Set different scores
        for i, c in enumerate(candidates):
            c.metrics = BacktestMetrics(sharpe_ratio=0.5 + i * 0.3)

        # Add one failed candidate
        failed = CandidateResult(
            candidate_id="failed",
            strategy_id="strategy-001",
            version="1.0.0",
            status=CandidateStatus.FAILED,
            window=window,
        )
        candidates.append(failed)

        ranking_engine = RankingEngine()
        ranked = ranking_engine.rank_candidates(candidates)
        summary = ranking_engine.get_ranking_summary(ranked)

        # Failed candidates are filtered out during ranking,
        # so only completed count remains.
        assert summary["completed"] == 5
        # Failed count may be 0 since failed candidates are filtered before ranking
        assert "average_score" in summary
        assert "median_score" in summary
        assert "top_score" in summary
        assert "top_3_candidates" in summary
        assert len(summary["top_3_candidates"]) == 3

    def test_pipeline_config_defaults(self) -> None:
        """Test pipeline configuration defaults."""
        config = PipelineConfig()

        # Should have default walk-forward config (30d train, 7d test)
        assert config.walk_forward.train_days == 30
        assert config.walk_forward.test_days == 7

        # Should have default ranking config (top 3)
        assert config.ranking.top_n_candidates == 3

        # Should complete within 4 hours
        assert config.max_runtime_hours == 4

    def test_criteria_normalization(self) -> None:
        """Test criteria normalization for ranking."""
        normalizers = {
            RankingCriteria.SHARPE_RATIO: CriteriaNormalizer(
                criteria=RankingCriteria.SHARPE_RATIO,
                higher_is_better=True,
                min_value=-2.0,
                max_value=3.0,
            ),
            RankingCriteria.MAX_DRAWDOWN: CriteriaNormalizer(
                criteria=RankingCriteria.MAX_DRAWDOWN,
                higher_is_better=False,
                min_value=0.0,
                max_value=50.0,
            ),
        }

        ranking_engine = RankingEngine(normalizers=normalizers)

        # Test Sharpe normalization
        sharpe_norm = ranking_engine.normalizers[RankingCriteria.SHARPE_RATIO]
        assert sharpe_norm.normalize(0.5) == 50.0  # Middle of range
        assert sharpe_norm.normalize(3.0) == 100.0  # Max
        assert sharpe_norm.normalize(-2.0) == 0.0  # Min

        # Test Drawdown normalization (lower is better)
        dd_norm = ranking_engine.normalizers[RankingCriteria.MAX_DRAWDOWN]
        assert dd_norm.normalize(25.0) == 50.0  # Middle of range
        assert dd_norm.normalize(0.0) == 100.0  # Best (lowest)
        assert dd_norm.normalize(50.0) == 0.0  # Worst (highest)
