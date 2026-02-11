"""Tests for candidate ranking engine."""

from datetime import datetime

import pytest

from backtesting.candidate.models import (
    BacktestMetrics,
    CandidateResult,
    CandidateStatus,
    RankingConfig,
    RankingCriteria,
    WalkForwardWindow,
)
from backtesting.candidate.ranking import CriteriaNormalizer, RankingEngine


class TestCriteriaNormalizer:
    """Tests for CriteriaNormalizer."""

    def test_normalize_higher_is_better(self) -> None:
        """Test normalization when higher is better."""
        normalizer = CriteriaNormalizer(
            criteria=RankingCriteria.SHARPE_RATIO,
            higher_is_better=True,
            min_value=0.0,
            max_value=3.0,
        )

        assert normalizer.normalize(0.0) == 0.0
        assert normalizer.normalize(1.5) == 50.0
        assert normalizer.normalize(3.0) == 100.0

    def test_normalize_lower_is_better(self) -> None:
        """Test normalization when lower is better."""
        normalizer = CriteriaNormalizer(
            criteria=RankingCriteria.MAX_DRAWDOWN,
            higher_is_better=False,
            min_value=0.0,
            max_value=50.0,
        )

        # Lower drawdown is better, so 0% = 100 score, 50% = 0 score
        assert normalizer.normalize(0.0) == 100.0
        assert normalizer.normalize(25.0) == 50.0
        assert normalizer.normalize(50.0) == 0.0

    def test_normalize_clamping(self) -> None:
        """Test that values are clamped to range."""
        normalizer = CriteriaNormalizer(
            criteria=RankingCriteria.SHARPE_RATIO,
            higher_is_better=True,
            min_value=0.0,
            max_value=3.0,
        )

        # Values outside range should be clamped
        assert normalizer.normalize(-1.0) == 0.0
        assert normalizer.normalize(5.0) == 100.0

    def test_normalize_with_transform(self) -> None:
        """Test normalization with transform function."""
        normalizer = CriteriaNormalizer(
            criteria=RankingCriteria.SHARPE_RATIO,
            higher_is_better=True,
            min_value=0.0,
            max_value=10.0,
            transform=lambda x: x * 2,  # Double the value
        )

        # Value 2.5 becomes 5.0 after transform, which is 50% of max
        assert normalizer.normalize(2.5) == 50.0


class TestRankingEngine:
    """Tests for RankingEngine."""

    def create_test_result(
        self,
        candidate_id: str,
        sharpe: float = 1.0,
        drawdown: float = 15.0,
        win_rate: float = 55.0,
        status: CandidateStatus = CandidateStatus.COMPLETED,
    ) -> CandidateResult:
        """Helper to create test candidate results."""
        window = WalkForwardWindow(
            train_start=datetime(2024, 1, 1),
            train_end=datetime(2024, 1, 31),
            test_start=datetime(2024, 1, 31),
            test_end=datetime(2024, 2, 7),
        )

        result = CandidateResult(
            candidate_id=candidate_id,
            strategy_id="strategy-001",
            version="1.0.0",
            status=status,
            window=window,
        )
        result.metrics = BacktestMetrics(
            sharpe_ratio=sharpe,
            max_drawdown_pct=drawdown,
            win_rate_pct=win_rate,
            profit_factor=1.5,
            total_return_pct=20.0,
        )
        return result

    def test_rank_candidates_basic(self) -> None:
        """Test basic candidate ranking."""
        engine = RankingEngine()

        candidates = [
            self.create_test_result("low", sharpe=0.5, drawdown=20.0),
            self.create_test_result("high", sharpe=2.0, drawdown=10.0),
            self.create_test_result("medium", sharpe=1.0, drawdown=15.0),
        ]

        ranked = engine.rank_candidates(candidates)

        # Should be sorted by composite score (high > medium > low)
        assert ranked[0].candidate_id == "high"
        assert ranked[1].candidate_id == "medium"
        assert ranked[2].candidate_id == "low"

        # Check ranks are assigned
        assert ranked[0].rank_position == 1
        assert ranked[1].rank_position == 2
        assert ranked[2].rank_position == 3

    def test_rank_candidates_skips_non_completed(self) -> None:
        """Test that non-completed candidates are skipped."""
        engine = RankingEngine()

        candidates = [
            self.create_test_result("completed", sharpe=1.0),
            self.create_test_result(
                "failed", sharpe=2.0, status=CandidateStatus.FAILED
            ),
            self.create_test_result(
                "pending", sharpe=2.0, status=CandidateStatus.PENDING
            ),
        ]

        ranked = engine.rank_candidates(candidates)

        assert len(ranked) == 1
        assert ranked[0].candidate_id == "completed"

    def test_get_top_candidates(self) -> None:
        """Test getting top N candidates."""
        engine = RankingEngine()

        candidates = [
            self.create_test_result("first", sharpe=2.0),
            self.create_test_result("second", sharpe=1.5),
            self.create_test_result("third", sharpe=1.0),
            self.create_test_result("fourth", sharpe=0.5),
        ]

        top = engine.get_top_candidates(candidates, n=3)

        assert len(top) == 3
        assert top[0].candidate_id == "first"
        assert top[1].candidate_id == "second"
        assert top[2].candidate_id == "third"

    def test_composite_score_calculation(self) -> None:
        """Test composite score calculation."""
        config = RankingConfig()
        engine = RankingEngine(config=config)

        candidate = self.create_test_result(
            "test", sharpe=1.5, drawdown=15.0, win_rate=60.0
        )
        engine._calculate_composite_score(candidate)

        # Check that scores were calculated
        assert candidate.composite_score > 0
        assert len(candidate.ranking_scores) > 0

        # Check that all configured criteria have scores
        criteria_with_scores = {s.criteria for s in candidate.ranking_scores}
        for criteria in config.criteria_weights:
            assert criteria in criteria_with_scores

    def test_get_ranking_breakdown(self) -> None:
        """Test getting ranking breakdown."""
        engine = RankingEngine()

        candidate = self.create_test_result("test", sharpe=1.5)
        engine._calculate_composite_score(candidate)
        candidate.rank_position = 1

        breakdown = engine.get_ranking_breakdown(candidate)

        assert breakdown["candidate_id"] == "test"
        assert "composite_score" in breakdown
        assert "criteria_breakdown" in breakdown
        assert len(breakdown["criteria_breakdown"]) > 0

    def test_get_ranking_summary(self) -> None:
        """Test getting ranking summary."""
        engine = RankingEngine()

        candidates = [
            self.create_test_result("a", sharpe=2.0),
            self.create_test_result("b", sharpe=1.0),
            self.create_test_result("c", sharpe=0.5),
        ]

        ranked = engine.rank_candidates(candidates)
        summary = engine.get_ranking_summary(ranked)

        assert summary["total_candidates"] == 3
        assert summary["completed"] == 3
        assert summary["failed"] == 0
        assert "average_score" in summary
        assert "top_score" in summary
        assert "top_3_candidates" in summary

    def test_custom_weights(self) -> None:
        """Test ranking with custom weights."""
        config = RankingConfig(
            criteria_weights={
                RankingCriteria.SHARPE_RATIO: 0.7,
                RankingCriteria.WIN_RATE: 0.3,
            }
        )
        engine = RankingEngine(config=config)

        candidates = [
            self.create_test_result("a", sharpe=1.0, win_rate=40.0),
            self.create_test_result("b", sharpe=0.8, win_rate=70.0),
        ]

        ranked = engine.rank_candidates(candidates)

        # With high Sharpe weight (0.7), candidate a should rank higher
        # even with lower win rate (40% vs 70%)
        # Candidate a: Sharpe 1.0 (normalized ~60%) * 0.7 = 42 + Win rate 40% (normalized ~40%) * 0.3 = 12 = ~54
        # Candidate b: Sharpe 0.8 (normalized ~56%) * 0.7 = 39.2 + Win rate 70% (normalized ~70%) * 0.3 = 21 = ~60.2
        # So candidate b should actually rank higher with these values
        assert ranked[0].candidate_id == "b"

    def test_default_normalizers(self) -> None:
        """Test that default normalizers are present."""
        engine = RankingEngine()

        assert RankingCriteria.SHARPE_RATIO in engine.normalizers
        assert RankingCriteria.MAX_DRAWDOWN in engine.normalizers
        assert RankingCriteria.WIN_RATE in engine.normalizers

    def test_custom_normalizers(self) -> None:
        """Test using custom normalizers."""
        custom_normalizers = {
            RankingCriteria.SHARPE_RATIO: CriteriaNormalizer(
                criteria=RankingCriteria.SHARPE_RATIO,
                higher_is_better=True,
                min_value=-1.0,
                max_value=5.0,
            )
        }

        engine = RankingEngine(normalizers=custom_normalizers)

        assert engine.normalizers[RankingCriteria.SHARPE_RATIO].max_value == 5.0
