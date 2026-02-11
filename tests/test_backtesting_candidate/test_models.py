"""Tests for candidate backtesting models."""

from datetime import datetime

import pytest

from backtesting.candidate.models import (
    BacktestMetrics,
    CandidateResult,
    CandidateStatus,
    RankingConfig,
    RankingCriteria,
    RankingScore,
    WalkForwardWindow,
)


class TestWalkForwardWindow:
    """Tests for WalkForwardWindow."""

    def test_valid_window(self) -> None:
        """Test creating a valid walk-forward window."""
        train_start = datetime(2024, 1, 1)
        train_end = datetime(2024, 1, 31)
        test_start = datetime(2024, 1, 31)
        test_end = datetime(2024, 2, 7)

        window = WalkForwardWindow(
            train_start=train_start,
            train_end=train_end,
            test_start=test_start,
            test_end=test_end,
        )

        assert window.train_start == train_start
        assert window.train_end == train_end
        assert window.test_start == test_start
        assert window.test_end == test_end

    def test_invalid_train_window(self) -> None:
        """Test that invalid train window raises error."""
        with pytest.raises(ValueError, match="train_end must be after train_start"):
            WalkForwardWindow(
                train_start=datetime(2024, 1, 31),
                train_end=datetime(2024, 1, 1),
                test_start=datetime(2024, 1, 31),
                test_end=datetime(2024, 2, 7),
            )

    def test_invalid_test_window(self) -> None:
        """Test that invalid test window raises error."""
        with pytest.raises(ValueError, match="test_end must be after test_start"):
            WalkForwardWindow(
                train_start=datetime(2024, 1, 1),
                train_end=datetime(2024, 1, 31),
                test_start=datetime(2024, 2, 7),
                test_end=datetime(2024, 2, 1),
            )

    def test_overlapping_windows(self) -> None:
        """Test that overlapping train/test raises error."""
        with pytest.raises(ValueError, match="test_start must be >= train_end"):
            WalkForwardWindow(
                train_start=datetime(2024, 1, 1),
                train_end=datetime(2024, 1, 31),
                test_start=datetime(2024, 1, 15),  # Overlaps with train
                test_end=datetime(2024, 2, 7),
            )


class TestBacktestMetrics:
    """Tests for BacktestMetrics."""

    def test_default_metrics(self) -> None:
        """Test default metric values."""
        metrics = BacktestMetrics()

        assert metrics.sharpe_ratio == 0.0
        assert metrics.max_drawdown_pct == 0.0
        assert metrics.win_rate_pct == 0.0
        assert metrics.trade_count == 0

    def test_custom_metrics(self) -> None:
        """Test creating metrics with custom values."""
        metrics = BacktestMetrics(
            sharpe_ratio=1.5,
            max_drawdown_pct=15.0,
            win_rate_pct=55.0,
            trade_count=100,
        )

        assert metrics.sharpe_ratio == 1.5
        assert metrics.max_drawdown_pct == 15.0
        assert metrics.win_rate_pct == 55.0
        assert metrics.trade_count == 100

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        metrics = BacktestMetrics(sharpe_ratio=1.5, trade_count=50)
        data = metrics.to_dict()

        assert data["sharpe_ratio"] == 1.5
        assert data["trade_count"] == 50
        assert "max_drawdown_pct" in data

    def test_from_dict(self) -> None:
        """Test creation from dictionary."""
        data = {
            "sharpe_ratio": 1.5,
            "max_drawdown_pct": 10.0,
            "win_rate_pct": 60.0,
            "trade_count": 100,
        }
        metrics = BacktestMetrics.from_dict(data)

        assert metrics.sharpe_ratio == 1.5
        assert metrics.max_drawdown_pct == 10.0
        assert metrics.win_rate_pct == 60.0
        assert metrics.trade_count == 100


class TestRankingScore:
    """Tests for RankingScore."""

    def test_valid_score(self) -> None:
        """Test creating a valid ranking score."""
        score = RankingScore(
            criteria=RankingCriteria.SHARPE_RATIO,
            raw_value=1.5,
            normalized_score=75.0,
            weight=0.3,
            weighted_score=22.5,
        )

        assert score.criteria == RankingCriteria.SHARPE_RATIO
        assert score.raw_value == 1.5
        assert score.normalized_score == 75.0
        assert score.weight == 0.3
        assert score.weighted_score == 22.5

    def test_invalid_normalized_score(self) -> None:
        """Test that invalid normalized score raises error."""
        with pytest.raises(ValueError, match="normalized_score must be 0-100"):
            RankingScore(
                criteria=RankingCriteria.SHARPE_RATIO,
                raw_value=1.5,
                normalized_score=150.0,  # Invalid
                weight=0.3,
                weighted_score=45.0,
            )

    def test_invalid_weight(self) -> None:
        """Test that invalid weight raises error."""
        with pytest.raises(ValueError, match="weight must be 0-1"):
            RankingScore(
                criteria=RankingCriteria.SHARPE_RATIO,
                raw_value=1.5,
                normalized_score=75.0,
                weight=1.5,  # Invalid
                weighted_score=112.5,
            )


class TestRankingConfig:
    """Tests for RankingConfig."""

    def test_default_config(self) -> None:
        """Test default configuration."""
        config = RankingConfig()

        assert RankingCriteria.SHARPE_RATIO in config.criteria_weights
        assert config.criteria_weights[RankingCriteria.SHARPE_RATIO] == 0.30
        assert config.top_n_candidates == 3
        assert config.min_sharpe_ratio == 0.5

    def test_weights_sum_to_one(self) -> None:
        """Test that default weights sum to 1.0."""
        config = RankingConfig()
        total = sum(config.criteria_weights.values())
        assert 0.99 <= total <= 1.01

    def test_invalid_weights_sum(self) -> None:
        """Test that weights not summing to 1.0 raises error."""
        with pytest.raises(ValueError, match="Criteria weights must sum to 1.0"):
            RankingConfig(
                criteria_weights={
                    RankingCriteria.SHARPE_RATIO: 0.5,
                    RankingCriteria.WIN_RATE: 0.3,
                    # Sum = 0.8, not 1.0
                }
            )

    def test_get_weight(self) -> None:
        """Test getting weight for specific criterion."""
        config = RankingConfig()
        weight = config.get_weight(RankingCriteria.SHARPE_RATIO)
        assert weight == 0.30

    def test_get_weight_missing(self) -> None:
        """Test getting weight for missing criterion returns 0."""
        config = RankingConfig()
        # Create config with limited criteria
        config.criteria_weights = {RankingCriteria.SHARPE_RATIO: 1.0}
        weight = config.get_weight(RankingCriteria.WIN_RATE)
        assert weight == 0.0


class TestCandidateResult:
    """Tests for CandidateResult."""

    def test_basic_result(self) -> None:
        """Test creating a basic candidate result."""
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
            status=CandidateStatus.PENDING,
            window=window,
        )

        assert result.candidate_id == "test-001"
        assert result.strategy_id == "strategy-001"
        assert result.version == "1.0.0"
        assert result.status == CandidateStatus.PENDING
        assert result.composite_score == 0.0

    def test_is_eligible_for_paper(self) -> None:
        """Test paper trading eligibility check."""
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
            composite_score=75.0,
        )
        result.metrics = BacktestMetrics(
            sharpe_ratio=1.5,
            max_drawdown_pct=15.0,
        )

        assert result.is_eligible_for_paper() is True

    def test_not_eligible_low_score(self) -> None:
        """Test that low composite score makes ineligible."""
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
            composite_score=50.0,  # Below default threshold
        )
        result.metrics = BacktestMetrics(
            sharpe_ratio=1.5,
            max_drawdown_pct=15.0,
        )

        assert result.is_eligible_for_paper() is False

    def test_not_eligible_high_drawdown(self) -> None:
        """Test that high drawdown makes ineligible."""
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
            composite_score=75.0,
        )
        result.metrics = BacktestMetrics(
            sharpe_ratio=1.5,
            max_drawdown_pct=25.0,  # Above 20% threshold
        )

        assert result.is_eligible_for_paper() is False

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
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
            composite_score=75.0,
            rank_position=1,
        )

        data = result.to_dict()

        assert data["candidate_id"] == "test-001"
        assert data["composite_score"] == 75.0
        assert data["rank_position"] == 1
        assert data["status"] == "completed"
        assert "window" in data
        assert "metrics" in data
