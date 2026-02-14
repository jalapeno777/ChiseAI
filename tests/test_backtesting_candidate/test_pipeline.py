"""Tests for candidate backtesting pipeline."""

from datetime import datetime
from unittest.mock import MagicMock, patch

from backtesting.candidate.models import (
    RankingConfig,
)
from backtesting.candidate.pipeline import (
    CandidateBacktestPipeline,
    PipelineConfig,
)
from backtesting.candidate.walk_forward import WalkForwardConfig


class TestPipelineConfig:
    """Tests for PipelineConfig."""

    def test_default_config(self) -> None:
        """Test default pipeline configuration."""
        config = PipelineConfig()

        assert config.batch_size == 10
        assert config.max_runtime_hours == 4
        assert config.store_results is True
        assert config.walk_forward is not None
        assert config.ranking is not None

    def test_custom_config(self) -> None:
        """Test custom pipeline configuration."""
        wf_config = WalkForwardConfig(train_days=60, test_days=14)
        ranking_config = RankingConfig(top_n_candidates=5)

        config = PipelineConfig(
            walk_forward=wf_config,
            ranking=ranking_config,
            batch_size=20,
            max_runtime_hours=8,
            store_results=False,
        )

        assert config.walk_forward.train_days == 60
        assert config.walk_forward.test_days == 14
        assert config.ranking.top_n_candidates == 5
        assert config.batch_size == 20
        assert config.max_runtime_hours == 8
        assert config.store_results is False


class TestCandidateBacktestPipeline:
    """Tests for CandidateBacktestPipeline."""

    def create_mock_registry(self, candidates=None):
        """Create a mock strategy registry."""
        registry = MagicMock()
        registry.get_candidates.return_value = candidates or [
            {
                "candidate_id": "cand-001",
                "strategy_id": "strat-001",
                "version": "1.0.0",
                "config": {"param1": 1.0},
            },
            {
                "candidate_id": "cand-002",
                "strategy_id": "strat-002",
                "version": "1.0.0",
                "config": {"param1": 2.0},
            },
        ]
        registry.update_candidate_status.return_value = True
        return registry

    def test_pipeline_initialization(self) -> None:
        """Test pipeline initialization."""
        config = PipelineConfig()
        pipeline = CandidateBacktestPipeline(config=config)

        assert pipeline.config == config
        assert pipeline.walk_forward_engine is not None
        assert pipeline.ranking_engine is not None
        assert pipeline.storage is not None

    def test_run_pipeline_basic(self) -> None:
        """Test basic pipeline execution."""
        registry = self.create_mock_registry()
        config = PipelineConfig(store_results=False, test_mode=True)

        pipeline = CandidateBacktestPipeline(
            config=config,
            strategy_registry=registry,
        )

        start = datetime(2024, 1, 1)
        end = datetime(2024, 4, 1)

        result = pipeline.run(start_date=start, end_date=end)

        assert "pipeline_id" in result
        assert "start_time" in result
        assert "end_time" in result
        assert "runtime_seconds" in result
        assert result["total_candidates"] == 2
        assert result["completed"] > 0
        assert "top_candidates" in result
        assert "ranking_summary" in result

    def test_run_pipeline_no_registry(self) -> None:
        """Test pipeline execution without registry."""
        config = PipelineConfig(store_results=False)
        pipeline = CandidateBacktestPipeline(config=config)

        result = pipeline.run()

        assert result["total_candidates"] == 0
        assert result["completed"] == 0

    def test_get_top_candidates_for_paper(self) -> None:
        """Test getting top candidates for paper trading."""
        config = PipelineConfig(store_results=False)
        pipeline = CandidateBacktestPipeline(config=config)

        # Mock storage query results
        mock_results = [
            {
                "candidate_id": "cand-001",
                "composite_score": 80.0,
                "sharpe_ratio": 1.5,
                "max_drawdown_pct": 15.0,
            },
            {
                "candidate_id": "cand-002",
                "composite_score": 70.0,
                "sharpe_ratio": 1.2,
                "max_drawdown_pct": 18.0,
            },
            {
                "candidate_id": "cand-003",
                "composite_score": 50.0,  # Below threshold
                "sharpe_ratio": 0.8,
                "max_drawdown_pct": 15.0,
            },
        ]

        with patch.object(pipeline.storage, "query_results", return_value=mock_results):
            top = pipeline.get_top_candidates_for_paper(min_score=60.0, limit=3)

        assert len(top) == 2
        assert top[0]["candidate_id"] == "cand-001"
        assert top[1]["candidate_id"] == "cand-002"

    def test_get_top_candidates_filters_drawdown(self) -> None:
        """Test that high drawdown candidates are filtered."""
        config = PipelineConfig(store_results=False)
        pipeline = CandidateBacktestPipeline(config=config)

        mock_results = [
            {
                "candidate_id": "cand-001",
                "composite_score": 80.0,
                "sharpe_ratio": 1.5,
                "max_drawdown_pct": 15.0,
            },
            {
                "candidate_id": "cand-002",
                "composite_score": 75.0,
                "sharpe_ratio": 1.3,
                "max_drawdown_pct": 25.0,  # Above 20% threshold
            },
        ]

        with patch.object(pipeline.storage, "query_results", return_value=mock_results):
            top = pipeline.get_top_candidates_for_paper(min_score=60.0)

        assert len(top) == 1
        assert top[0]["candidate_id"] == "cand-001"

    def test_get_candidate_details(self) -> None:
        """Test getting candidate details."""
        config = PipelineConfig(store_results=False)
        pipeline = CandidateBacktestPipeline(config=config)

        mock_results = [
            {"candidate_id": "cand-001", "sharpe_ratio": 1.5},
            {"candidate_id": "cand-002", "sharpe_ratio": 1.2},
        ]

        with patch.object(pipeline.storage, "query_results", return_value=mock_results):
            details = pipeline.get_candidate_details("cand-001")

        assert details is not None
        assert details["candidate_id"] == "cand-001"
        assert details["sharpe_ratio"] == 1.5

    def test_get_candidate_details_not_found(self) -> None:
        """Test getting details for non-existent candidate."""
        config = PipelineConfig(store_results=False)
        pipeline = CandidateBacktestPipeline(config=config)

        with patch.object(pipeline.storage, "query_results", return_value=[]):
            details = pipeline.get_candidate_details("non-existent")

        assert details is None

    def test_pipeline_runtime_within_limit(self) -> None:
        """Test that pipeline completes within configured time limit."""
        registry = self.create_mock_registry()
        config = PipelineConfig(
            max_runtime_hours=4,
            store_results=False,
        )

        pipeline = CandidateBacktestPipeline(
            config=config,
            strategy_registry=registry,
        )

        result = pipeline.run()

        # Runtime should be less than max (in seconds)
        max_seconds = config.max_runtime_hours * 3600
        assert result["runtime_seconds"] < max_seconds

    def test_update_registry_called(self) -> None:
        """Test that registry is updated with results."""
        registry = self.create_mock_registry()
        config = PipelineConfig(store_results=False, test_mode=True)

        pipeline = CandidateBacktestPipeline(
            config=config,
            strategy_registry=registry,
        )

        pipeline.run()

        # Registry update should be called for each result
        assert registry.update_candidate_status.called
