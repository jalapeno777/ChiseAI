"""
Tests for Retrieval Quality Evaluator.

ST-GOV-007: Retrieval Quality Evaluator

Tests cover:
- RetrievalEvaluator class
- Relevance tracking
- Metrics calculation
- Human validation sampling
"""

import pytest
from datetime import datetime, UTC
from unittest.mock import MagicMock, patch

from src.governance.retrieval.evaluator import (
    RetrievalEvaluator,
    RetrievalResult,
    RetrievalMetrics,
    QueryEvaluation,
    RelevanceLabel,
)


class TestRetrievalResult:
    """Tests for RetrievalResult dataclass."""

    def test_creation(self):
        """Test creating a retrieval result."""
        result = RetrievalResult(
            doc_id="doc1",
            score=0.95,
            content="Test content",
        )
        assert result.doc_id == "doc1"
        assert result.score == 0.95
        assert result.content == "Test content"
        assert result.relevance == RelevanceLabel.UNKNOWN

    def test_to_dict(self):
        """Test serialization to dict."""
        result = RetrievalResult(
            doc_id="doc1",
            score=0.95,
            relevance=RelevanceLabel.RELEVANT,
        )
        d = result.to_dict()
        assert d["doc_id"] == "doc1"
        assert d["score"] == 0.95
        assert d["relevance"] == "relevant"

    def test_from_dict(self):
        """Test deserialization from dict."""
        d = {
            "doc_id": "doc1",
            "score": 0.95,
            "relevance": "relevant",
        }
        result = RetrievalResult.from_dict(d)
        assert result.doc_id == "doc1"
        assert result.score == 0.95
        assert result.relevance == RelevanceLabel.RELEVANT


class TestRetrievalMetrics:
    """Tests for RetrievalMetrics dataclass."""

    def test_default_values(self):
        """Test default metric values."""
        metrics = RetrievalMetrics()
        assert metrics.precision_at_5 == 0.0
        assert metrics.recall_at_10 == 0.0
        assert metrics.mrr == 0.0
        assert metrics.query_count == 0

    def test_meets_validation_gates_pass(self):
        """Test validation gates when passing."""
        metrics = RetrievalMetrics(
            precision_at_5=0.90,
            recall_at_10=0.85,
            mrr=0.80,
        )
        assert metrics.meets_validation_gates() is True

    def test_meets_validation_gates_fail_precision(self):
        """Test validation gates failing on precision."""
        metrics = RetrievalMetrics(
            precision_at_5=0.80,  # Below 85%
            recall_at_10=0.85,
            mrr=0.80,
        )
        assert metrics.meets_validation_gates() is False

    def test_meets_validation_gates_fail_recall(self):
        """Test validation gates failing on recall."""
        metrics = RetrievalMetrics(
            precision_at_5=0.90,
            recall_at_10=0.75,  # Below 80%
            mrr=0.80,
        )
        assert metrics.meets_validation_gates() is False

    def test_meets_validation_gates_fail_mrr(self):
        """Test validation gates failing on MRR."""
        metrics = RetrievalMetrics(
            precision_at_5=0.90,
            recall_at_10=0.85,
            mrr=0.70,  # Below 0.75
        )
        assert metrics.meets_validation_gates() is False

    def test_to_dict(self):
        """Test serialization."""
        metrics = RetrievalMetrics(
            precision_at_5=0.85,
            recall_at_10=0.80,
            mrr=0.75,
            query_count=100,
        )
        d = metrics.to_dict()
        assert d["precision_at_5"] == 0.85
        assert d["recall_at_10"] == 0.80
        assert d["mrr"] == 0.75
        assert d["query_count"] == 100


class TestRetrievalEvaluator:
    """Tests for RetrievalEvaluator class."""

    def test_init(self):
        """Test evaluator initialization."""
        evaluator = RetrievalEvaluator()
        assert evaluator._redis is None
        assert evaluator._vector_store is None
        assert evaluator._sample_rate == 0.1

    def test_init_with_sample_rate(self):
        """Test initialization with custom sample rate."""
        evaluator = RetrievalEvaluator(sample_rate=0.2)
        assert evaluator._sample_rate == 0.2

    def test_evaluate_query(self):
        """Test evaluating a query."""
        evaluator = RetrievalEvaluator()

        results = [
            RetrievalResult(doc_id="doc1", score=0.95),
            RetrievalResult(doc_id="doc2", score=0.90),
            RetrievalResult(doc_id="doc3", score=0.85),
        ]

        evaluation = evaluator.evaluate_query(
            query_id="q1",
            query_text="test query",
            retrieved_results=results,
            known_relevant={"doc1", "doc2"},
        )

        assert evaluation.query_id == "q1"
        assert evaluation.query_text == "test query"
        assert len(evaluation.results) == 3
        assert evaluation.relevant_docs == {"doc1", "doc2"}

    def test_track_relevance(self):
        """Test tracking relevance for a result."""
        evaluator = RetrievalEvaluator()

        results = [
            RetrievalResult(doc_id="doc1", score=0.95),
            RetrievalResult(doc_id="doc2", score=0.90),
        ]

        evaluator.evaluate_query(
            query_id="q1",
            query_text="test query",
            retrieved_results=results,
        )

        # Track relevance
        success = evaluator.track_relevance(
            query_id="q1",
            doc_id="doc1",
            relevance=RelevanceLabel.RELEVANT,
        )

        assert success is True
        evaluation = evaluator.get_evaluation("q1")
        assert evaluation.results[0].relevance == RelevanceLabel.RELEVANT

    def test_track_relevance_nonexistent_query(self):
        """Test tracking relevance for non-existent query."""
        evaluator = RetrievalEvaluator()
        success = evaluator.track_relevance(
            query_id="nonexistent",
            doc_id="doc1",
            relevance=RelevanceLabel.RELEVANT,
        )
        assert success is False

    def test_track_relevance_nonexistent_doc(self):
        """Test tracking relevance for non-existent doc."""
        evaluator = RetrievalEvaluator()

        evaluator.evaluate_query(
            query_id="q1",
            query_text="test query",
            retrieved_results=[RetrievalResult(doc_id="doc1", score=0.95)],
        )

        success = evaluator.track_relevance(
            query_id="q1",
            doc_id="nonexistent",
            relevance=RelevanceLabel.RELEVANT,
        )
        assert success is False

    def test_calculate_metrics(self):
        """Test calculating metrics."""
        evaluator = RetrievalEvaluator()

        # Create evaluations with known relevant docs
        for i in range(3):
            results = [
                RetrievalResult(doc_id=f"doc{i}a", score=0.95),
                RetrievalResult(doc_id=f"doc{i}b", score=0.90),
                RetrievalResult(doc_id=f"doc{i}c", score=0.85),
                RetrievalResult(doc_id=f"doc{i}d", score=0.80),
                RetrievalResult(doc_id=f"doc{i}e", score=0.75),
            ]

            evaluator.evaluate_query(
                query_id=f"q{i}",
                query_text=f"test query {i}",
                retrieved_results=results,
                known_relevant={f"doc{i}a", f"doc{i}b"},  # Top 2 are relevant
            )

        metrics = evaluator.calculate_metrics()

        # With top 2/5 relevant, precision@5 should be 0.4
        assert metrics.precision_at_5 == pytest.approx(0.4, rel=0.01)
        assert metrics.query_count == 3

    def test_calculate_metrics_empty(self):
        """Test calculating metrics with no queries."""
        evaluator = RetrievalEvaluator()
        metrics = evaluator.calculate_metrics()

        assert metrics.precision_at_5 == 0.0
        assert metrics.query_count == 0

    def test_get_human_validation_sample(self):
        """Test getting sample for human validation."""
        evaluator = RetrievalEvaluator(sample_rate=1.0)  # 100% sample rate

        # Create some evaluations
        for i in range(5):
            evaluator.evaluate_query(
                query_id=f"q{i}",
                query_text=f"test query {i}",
                retrieved_results=[RetrievalResult(doc_id=f"doc{i}", score=0.9)],
            )

        sample = evaluator.get_human_validation_sample(sample_size=3)
        assert len(sample) <= 3

    def test_record_human_validation(self):
        """Test recording human validation."""
        evaluator = RetrievalEvaluator()

        evaluator.evaluate_query(
            query_id="q1",
            query_text="test query",
            retrieved_results=[
                RetrievalResult(doc_id="doc1", score=0.95),
                RetrievalResult(doc_id="doc2", score=0.90),
            ],
        )

        success = evaluator.record_human_validation(
            query_id="q1",
            relevant_doc_ids={"doc1"},
            validator="human1",
        )

        assert success is True
        evaluation = evaluator.get_evaluation("q1")
        assert evaluation.human_validated is True
        assert evaluation.validator == "human1"
        assert evaluation.relevant_docs == {"doc1"}
        assert evaluation.results[0].relevance == RelevanceLabel.RELEVANT
        assert evaluation.results[1].relevance == RelevanceLabel.NOT_RELEVANT

    def test_get_all_evaluations(self):
        """Test getting all evaluations."""
        evaluator = RetrievalEvaluator()

        evaluator.evaluate_query(
            query_id="q1",
            query_text="test1",
            retrieved_results=[],
        )
        evaluator.evaluate_query(
            query_id="q2",
            query_text="test2",
            retrieved_results=[],
        )

        all_evals = evaluator.get_all_evaluations()
        assert len(all_evals) == 2

    def test_validate_passing(self):
        """Test validation with passing metrics."""
        evaluator = RetrievalEvaluator()

        # Create high-quality evaluations
        for i in range(5):
            results = [
                RetrievalResult(
                    doc_id=f"doc{i}a", score=0.95, relevance=RelevanceLabel.RELEVANT
                ),
                RetrievalResult(
                    doc_id=f"doc{i}b", score=0.90, relevance=RelevanceLabel.RELEVANT
                ),
                RetrievalResult(
                    doc_id=f"doc{i}c", score=0.85, relevance=RelevanceLabel.RELEVANT
                ),
                RetrievalResult(
                    doc_id=f"doc{i}d", score=0.80, relevance=RelevanceLabel.RELEVANT
                ),
                RetrievalResult(
                    doc_id=f"doc{i}e", score=0.75, relevance=RelevanceLabel.RELEVANT
                ),
            ]

            evaluator.evaluate_query(
                query_id=f"q{i}",
                query_text=f"test query {i}",
                retrieved_results=results,
                known_relevant={
                    f"doc{i}a",
                    f"doc{i}b",
                    f"doc{i}c",
                    f"doc{i}d",
                    f"doc{i}e",
                },
            )

        # All results are relevant, should pass validation gates
        assert evaluator.validate() is True


class TestRetrievalEvaluatorWithRedis:
    """Tests for RetrievalEvaluator with Redis."""

    def test_init_with_redis(self):
        """Test initialization with Redis client."""
        mock_redis = MagicMock()
        evaluator = RetrievalEvaluator(redis_client=mock_redis)
        assert evaluator._redis is not None

    def test_store_evaluation(self):
        """Test storing evaluation to Redis."""
        mock_redis = MagicMock()
        evaluator = RetrievalEvaluator(redis_client=mock_redis)

        evaluator.evaluate_query(
            query_id="q1",
            query_text="test query",
            retrieved_results=[RetrievalResult(doc_id="doc1", score=0.95)],
        )

        # Verify Redis set was called
        mock_redis.set.assert_called()

    def test_record_human_validation_with_redis(self):
        """Test recording human validation with Redis."""
        mock_redis = MagicMock()
        evaluator = RetrievalEvaluator(redis_client=mock_redis)

        evaluator.evaluate_query(
            query_id="q1",
            query_text="test query",
            retrieved_results=[RetrievalResult(doc_id="doc1", score=0.95)],
        )

        evaluator.record_human_validation(
            query_id="q1",
            relevant_doc_ids={"doc1"},
            validator="human1",
        )

        # Verify Redis lpush was called for validation storage
        mock_redis.lpush.assert_called()


class TestRetrievalMetricsEdgeCases:
    """Edge case tests for metrics calculation."""

    def test_mrr_calculation(self):
        """Test Mean Reciprocal Rank calculation."""
        evaluator = RetrievalEvaluator()

        # Query 1: First result is relevant (RR = 1.0)
        evaluator.evaluate_query(
            query_id="q1",
            query_text="test1",
            retrieved_results=[
                RetrievalResult(
                    doc_id="doc1", score=0.95, relevance=RelevanceLabel.RELEVANT
                ),
                RetrievalResult(
                    doc_id="doc2", score=0.90, relevance=RelevanceLabel.NOT_RELEVANT
                ),
            ],
            known_relevant={"doc1"},
        )

        # Query 2: Second result is relevant (RR = 0.5)
        evaluator.evaluate_query(
            query_id="q2",
            query_text="test2",
            retrieved_results=[
                RetrievalResult(
                    doc_id="doc3", score=0.95, relevance=RelevanceLabel.NOT_RELEVANT
                ),
                RetrievalResult(
                    doc_id="doc4", score=0.90, relevance=RelevanceLabel.RELEVANT
                ),
            ],
            known_relevant={"doc4"},
        )

        metrics = evaluator.calculate_metrics()
        # MRR = (1.0 + 0.5) / 2 = 0.75
        assert metrics.mrr == pytest.approx(0.75, rel=0.01)

    def test_no_relevant_docs_in_results(self):
        """Test when no relevant docs are retrieved."""
        evaluator = RetrievalEvaluator()

        evaluator.evaluate_query(
            query_id="q1",
            query_text="test1",
            retrieved_results=[
                RetrievalResult(doc_id="doc1", score=0.95),
                RetrievalResult(doc_id="doc2", score=0.90),
            ],
            known_relevant={"doc3", "doc4"},  # Not in results
        )

        metrics = evaluator.calculate_metrics()
        assert metrics.precision_at_5 == 0.0
        assert metrics.mrr == 0.0

    def test_all_results_relevant(self):
        """Test when all results are relevant."""
        evaluator = RetrievalEvaluator()

        results = [
            RetrievalResult(
                doc_id=f"doc{i}",
                score=0.95 - i * 0.05,
                relevance=RelevanceLabel.RELEVANT,
            )
            for i in range(5)
        ]

        evaluator.evaluate_query(
            query_id="q1",
            query_text="test1",
            retrieved_results=results,
            known_relevant={f"doc{i}" for i in range(5)},
        )

        metrics = evaluator.calculate_metrics()
        assert metrics.precision_at_5 == 1.0
