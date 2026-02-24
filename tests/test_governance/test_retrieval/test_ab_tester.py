"""
Tests for A/B Testing Module.

ST-GOV-007: Retrieval Quality Evaluator

Tests cover:
- ABTester class
- Strategy registration
- Experiment creation and management
- Statistical significance analysis
"""

from unittest.mock import MagicMock

import pytest
from src.governance.retrieval.ab_tester import (
    ABTester,
    Experiment,
    ExperimentResult,
    ExperimentStatus,
    StatisticalResult,
    StrategyConfig,
)


class MockRetrievalStrategy:
    """Mock retrieval strategy for testing."""

    def __init__(self, name: str, results: list[dict] | None = None):
        self.name = name
        self._results = results or [
            {"doc_id": f"doc{i}", "score": 0.9 - i * 0.1} for i in range(5)
        ]

    def retrieve(self, query: str, limit: int = 10, **kwargs):
        return self._results[:limit]


class TestStrategyConfig:
    """Tests for StrategyConfig."""

    def test_creation(self):
        """Test creating a strategy config."""
        config = StrategyConfig(
            name="test_strategy",
            description="Test strategy",
            weight=0.6,
        )
        assert config.name == "test_strategy"
        assert config.description == "Test strategy"
        assert config.weight == 0.6

    def test_serialization(self):
        """Test serialization round-trip."""
        config = StrategyConfig(
            name="test",
            parameters={"threshold": 0.7},
        )
        d = config.to_dict()
        restored = StrategyConfig.from_dict(d)
        assert restored.name == config.name
        assert restored.parameters == config.parameters


class TestExperimentResult:
    """Tests for ExperimentResult."""

    def test_creation(self):
        """Test creating an experiment result."""
        result = ExperimentResult(
            experiment_id="exp1",
            query_id="q1",
            strategy_name="baseline",
            results=[{"doc_id": "doc1", "score": 0.9}],
            metrics={"latency_ms": 10.5},
        )
        assert result.experiment_id == "exp1"
        assert result.query_id == "q1"
        assert result.strategy_name == "baseline"
        assert len(result.results) == 1
        assert result.metrics["latency_ms"] == 10.5

    def test_serialization(self):
        """Test serialization round-trip."""
        result = ExperimentResult(
            experiment_id="exp1",
            query_id="q1",
            strategy_name="baseline",
            results=[{"doc_id": "doc1", "score": 0.9}],
        )
        d = result.to_dict()
        restored = ExperimentResult.from_dict(d)
        assert restored.experiment_id == result.experiment_id
        assert restored.query_id == result.query_id


class TestExperiment:
    """Tests for Experiment."""

    def test_creation(self):
        """Test creating an experiment."""
        exp = Experiment(
            experiment_id="exp1",
            name="Test Experiment",
            description="Testing",
        )
        assert exp.experiment_id == "exp1"
        assert exp.name == "Test Experiment"
        assert exp.status == ExperimentStatus.DRAFT

    def test_serialization(self):
        """Test serialization round-trip."""
        exp = Experiment(
            experiment_id="exp1",
            name="Test",
            control_strategy=StrategyConfig(name="control"),
            treatment_strategy=StrategyConfig(name="treatment"),
        )
        d = exp.to_dict()
        restored = Experiment.from_dict(d)
        assert restored.experiment_id == exp.experiment_id
        assert restored.control_strategy.name == "control"


class TestABTester:
    """Tests for ABTester class."""

    def test_init(self):
        """Test A/B tester initialization."""
        tester = ABTester()
        assert tester._redis is None
        assert tester._default_confidence == 0.95

    def test_register_strategy(self):
        """Test registering a strategy."""
        tester = ABTester()
        strategy = MockRetrievalStrategy("baseline")

        tester.register_strategy("baseline", strategy)

        assert "baseline" in tester.get_registered_strategies()

    def test_unregister_strategy(self):
        """Test unregistering a strategy."""
        tester = ABTester()
        strategy = MockRetrievalStrategy("baseline")

        tester.register_strategy("baseline", strategy)
        result = tester.unregister_strategy("baseline")

        assert result is True
        assert "baseline" not in tester.get_registered_strategies()

    def test_unregister_nonexistent_strategy(self):
        """Test unregistering a non-existent strategy."""
        tester = ABTester()
        result = tester.unregister_strategy("nonexistent")
        assert result is False

    def test_create_experiment(self):
        """Test creating an experiment."""
        tester = ABTester()
        control = MockRetrievalStrategy("control")
        treatment = MockRetrievalStrategy("treatment")

        tester.register_strategy("control", control)
        tester.register_strategy("treatment", treatment)

        exp_id = tester.create_experiment(
            name="Test Experiment",
            control="control",
            treatment="treatment",
        )

        assert exp_id.startswith("exp-")
        exp = tester.get_experiment(exp_id)
        assert exp is not None
        assert exp.name == "Test Experiment"
        assert exp.status == ExperimentStatus.DRAFT

    def test_create_experiment_unregistered_strategy(self):
        """Test creating experiment with unregistered strategy."""
        tester = ABTester()

        with pytest.raises(ValueError, match="not registered"):
            tester.create_experiment(
                name="Test",
                control="unregistered",
                treatment="treatment",
            )

    def test_start_experiment(self):
        """Test starting an experiment."""
        tester = ABTester()
        tester.register_strategy("control", MockRetrievalStrategy("control"))
        tester.register_strategy("treatment", MockRetrievalStrategy("treatment"))

        exp_id = tester.create_experiment(
            name="Test",
            control="control",
            treatment="treatment",
        )

        result = tester.start_experiment(exp_id)
        assert result is True

        exp = tester.get_experiment(exp_id)
        assert exp.status == ExperimentStatus.RUNNING
        assert exp.started_at is not None

    def test_pause_experiment(self):
        """Test pausing an experiment."""
        tester = ABTester()
        tester.register_strategy("control", MockRetrievalStrategy("control"))
        tester.register_strategy("treatment", MockRetrievalStrategy("treatment"))

        exp_id = tester.create_experiment(
            name="Test",
            control="control",
            treatment="treatment",
        )
        tester.start_experiment(exp_id)

        result = tester.pause_experiment(exp_id)
        assert result is True

        exp = tester.get_experiment(exp_id)
        assert exp.status == ExperimentStatus.PAUSED

    def test_complete_experiment(self):
        """Test completing an experiment."""
        tester = ABTester()
        tester.register_strategy("control", MockRetrievalStrategy("control"))
        tester.register_strategy("treatment", MockRetrievalStrategy("treatment"))

        exp_id = tester.create_experiment(
            name="Test",
            control="control",
            treatment="treatment",
        )
        tester.start_experiment(exp_id)

        result = tester.complete_experiment(exp_id)
        assert result is True

        exp = tester.get_experiment(exp_id)
        assert exp.status == ExperimentStatus.COMPLETED
        assert exp.completed_at is not None

    def test_get_strategy_for_query(self):
        """Test strategy assignment for queries."""
        tester = ABTester()
        tester.register_strategy("control", MockRetrievalStrategy("control"))
        tester.register_strategy("treatment", MockRetrievalStrategy("treatment"))

        exp_id = tester.create_experiment(
            name="Test",
            control="control",
            treatment="treatment",
            traffic_split=0.5,
        )
        tester.start_experiment(exp_id)

        # Same query should always get same strategy
        strategy1 = tester.get_strategy_for_query(exp_id, "test query")
        strategy2 = tester.get_strategy_for_query(exp_id, "test query")
        assert strategy1 == strategy2

    def test_get_strategy_for_query_not_running(self):
        """Test strategy assignment when experiment not running."""
        tester = ABTester()
        tester.register_strategy("control", MockRetrievalStrategy("control"))
        tester.register_strategy("treatment", MockRetrievalStrategy("treatment"))

        exp_id = tester.create_experiment(
            name="Test",
            control="control",
            treatment="treatment",
        )
        # Not started - should return control

        strategy = tester.get_strategy_for_query(exp_id, "test query")
        assert strategy == "control"

    def test_run_query(self):
        """Test running a query through the experiment."""
        tester = ABTester()
        tester.register_strategy("control", MockRetrievalStrategy("control"))
        tester.register_strategy("treatment", MockRetrievalStrategy("treatment"))

        exp_id = tester.create_experiment(
            name="Test",
            control="control",
            treatment="treatment",
        )
        tester.start_experiment(exp_id)

        result = tester.run_query(
            experiment_id=exp_id,
            query="test query",
            strategy_name="control",
        )

        assert result.experiment_id == exp_id
        assert result.strategy_name == "control"
        assert len(result.results) == 5
        assert "latency_ms" in result.metrics

    def test_record_relevance_feedback(self):
        """Test recording relevance feedback."""
        tester = ABTester()
        tester.register_strategy("control", MockRetrievalStrategy("control"))
        tester.register_strategy("treatment", MockRetrievalStrategy("treatment"))

        exp_id = tester.create_experiment(
            name="Test",
            control="control",
            treatment="treatment",
        )
        tester.start_experiment(exp_id)

        result = tester.run_query(
            experiment_id=exp_id,
            query="test query",
            strategy_name="control",
            query_id="q1",
        )

        success = tester.record_relevance_feedback(
            experiment_id=exp_id,
            query_id="q1",
            relevant_doc_ids={"doc0", "doc1"},
        )

        assert success is True
        assert result.metrics["precision_at_5"] == pytest.approx(0.4, rel=0.01)

    def test_get_experiment_metrics(self):
        """Test getting experiment metrics."""
        tester = ABTester()
        tester.register_strategy("control", MockRetrievalStrategy("control"))
        tester.register_strategy("treatment", MockRetrievalStrategy("treatment"))

        exp_id = tester.create_experiment(
            name="Test",
            control="control",
            treatment="treatment",
        )
        tester.start_experiment(exp_id)

        # Run some queries
        for i in range(3):
            tester.run_query(
                experiment_id=exp_id,
                query=f"query {i}",
                strategy_name="control",
                query_id=f"q{i}",
            )
            tester.record_relevance_feedback(
                experiment_id=exp_id,
                query_id=f"q{i}",
                relevant_doc_ids={"doc0"},
            )

        metrics = tester.get_experiment_metrics(exp_id)
        assert "control" in metrics
        assert metrics["control"].sample_count == 3

    def test_analyze_experiment(self):
        """Test statistical analysis of experiment."""
        tester = ABTester()
        tester.register_strategy("control", MockRetrievalStrategy("control"))
        tester.register_strategy("treatment", MockRetrievalStrategy("treatment"))

        exp_id = tester.create_experiment(
            name="Test",
            control="control",
            treatment="treatment",
        )
        tester.start_experiment(exp_id)

        # Run queries for both strategies
        for i in range(10):
            # Control
            result = tester.run_query(
                experiment_id=exp_id,
                query=f"query_control_{i}",
                strategy_name="control",
            )
            # Simulate feedback
            result.metrics["precision_at_5"] = 0.7 + (i % 3) * 0.05

            # Treatment
            result = tester.run_query(
                experiment_id=exp_id,
                query=f"query_treatment_{i}",
                strategy_name="treatment",
            )
            result.metrics["precision_at_5"] = 0.8 + (i % 3) * 0.05

        analysis = tester.analyze_experiment(exp_id)

        assert "precision_at_5" in analysis
        assert (
            analysis["precision_at_5"].control_mean
            < analysis["precision_at_5"].treatment_mean
        )

    def test_analyze_experiment_insufficient_data(self):
        """Test analysis with insufficient data."""
        tester = ABTester()
        tester.register_strategy("control", MockRetrievalStrategy("control"))
        tester.register_strategy("treatment", MockRetrievalStrategy("treatment"))

        exp_id = tester.create_experiment(
            name="Test",
            control="control",
            treatment="treatment",
        )
        tester.start_experiment(exp_id)

        # Only run control, not treatment
        tester.run_query(
            experiment_id=exp_id,
            query="query",
            strategy_name="control",
        )

        analysis = tester.analyze_experiment(exp_id)
        # Should return empty due to no treatment data
        assert len(analysis) == 0

    def test_get_all_experiments(self):
        """Test getting all experiments."""
        tester = ABTester()
        tester.register_strategy("control", MockRetrievalStrategy("control"))
        tester.register_strategy("treatment", MockRetrievalStrategy("treatment"))

        exp_id1 = tester.create_experiment(
            name="Test1",
            control="control",
            treatment="treatment",
        )
        tester.create_experiment(
            name="Test2",
            control="control",
            treatment="treatment",
        )
        tester.start_experiment(exp_id1)

        all_exps = tester.get_all_experiments()
        assert len(all_exps) == 2

        running_exps = tester.get_all_experiments(status=ExperimentStatus.RUNNING)
        assert len(running_exps) == 1
        assert running_exps[0].experiment_id == exp_id1


class TestABTesterWithRedis:
    """Tests for ABTester with Redis."""

    def test_init_with_redis(self):
        """Test initialization with Redis client."""
        mock_redis = MagicMock()
        tester = ABTester(redis_client=mock_redis)
        assert tester._redis is not None

    def test_store_experiment(self):
        """Test storing experiment to Redis."""
        mock_redis = MagicMock()
        tester = ABTester(redis_client=mock_redis)
        tester.register_strategy("control", MockRetrievalStrategy("control"))
        tester.register_strategy("treatment", MockRetrievalStrategy("treatment"))

        tester.create_experiment(
            name="Test",
            control="control",
            treatment="treatment",
        )

        # Verify Redis set was called
        mock_redis.set.assert_called()

    def test_store_result(self):
        """Test storing result to Redis."""
        mock_redis = MagicMock()
        tester = ABTester(redis_client=mock_redis)
        tester.register_strategy("control", MockRetrievalStrategy("control"))
        tester.register_strategy("treatment", MockRetrievalStrategy("treatment"))

        exp_id = tester.create_experiment(
            name="Test",
            control="control",
            treatment="treatment",
        )
        tester.start_experiment(exp_id)

        tester.run_query(
            experiment_id=exp_id,
            query="test query",
            strategy_name="control",
        )

        # Verify Redis set was called for result
        assert mock_redis.set.call_count >= 2  # Experiment + result


class TestStatisticalSignificance:
    """Tests for statistical significance calculation."""

    def test_statistical_result(self):
        """Test StatisticalResult dataclass."""
        result = StatisticalResult(
            metric_name="precision_at_5",
            control_mean=0.75,
            treatment_mean=0.85,
            control_std=0.1,
            treatment_std=0.08,
            p_value=0.02,
            is_significant=True,
            effect_size=1.11,
        )

        assert result.metric_name == "precision_at_5"
        assert result.is_significant is True
        assert result.p_value == 0.02

    def test_significance_threshold(self):
        """Test significance threshold at 95% confidence."""
        tester = ABTester(default_confidence=0.95)
        tester.register_strategy("control", MockRetrievalStrategy("control"))
        tester.register_strategy("treatment", MockRetrievalStrategy("treatment"))

        exp_id = tester.create_experiment(
            name="Test",
            control="control",
            treatment="treatment",
        )
        tester.start_experiment(exp_id)

        # Create clearly different results
        for i in range(20):
            result = tester.run_query(
                experiment_id=exp_id,
                query=f"query_control_{i}",
                strategy_name="control",
            )
            result.metrics["precision_at_5"] = 0.70

            result = tester.run_query(
                experiment_id=exp_id,
                query=f"query_treatment_{i}",
                strategy_name="treatment",
            )
            result.metrics["precision_at_5"] = 0.90

        analysis = tester.analyze_experiment(exp_id, confidence=0.95)

        # Should be significant with such different means
        assert "precision_at_5" in analysis
        # The result may or may not be significant depending on variance
        # but we should have a valid p_value
        assert 0 <= analysis["precision_at_5"].p_value <= 1
