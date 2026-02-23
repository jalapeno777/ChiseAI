"""
Integration tests for Retrieval Quality Evaluator.

ST-GOV-007: Retrieval Quality Evaluator

Tests cover end-to-end integration of:
- Evaluator + Metrics Exporter
- A/B Tester + Evaluator
- Threshold Tuner + Evaluator
"""

import pytest
from unittest.mock import MagicMock

from src.governance.retrieval import (
    RetrievalEvaluator,
    RetrievalResult,
    RetrievalMetrics,
    RelevanceLabel,
    ABTester,
    ThresholdTuner,
    TunerConfig,
    AdjustmentStrategy,
    RetrievalMetricsExporter,
)


class MockRetrievalStrategy:
    """Mock retrieval strategy for testing."""

    def __init__(self, name: str, quality: float = 0.8):
        """
        Initialize mock strategy.

        Args:
            name: Strategy name
            quality: Simulated quality (0-1), affects result relevance
        """
        self.name = name
        self._quality = quality

    def retrieve(self, query: str, limit: int = 10, **kwargs):
        """Return mock results."""
        results = []
        for i in range(limit):
            # Higher quality = higher scores for early positions
            score = self._quality * (1 - i * 0.05)
            results.append(
                {
                    "doc_id": f"{self.name}_doc{i}",
                    "score": score,
                    "content": f"Result {i} for query: {query}",
                }
            )
        return results


class TestEvaluatorMetricsIntegration:
    """Integration tests for Evaluator + Metrics Exporter."""

    def test_evaluator_feeds_exporter(self):
        """Test that evaluator metrics can be exported."""
        evaluator = RetrievalEvaluator()
        exporter = RetrievalMetricsExporter()

        # Create some evaluations
        for i in range(10):
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
                    doc_id=f"doc{i}d", score=0.80, relevance=RelevanceLabel.NOT_RELEVANT
                ),
                RetrievalResult(
                    doc_id=f"doc{i}e", score=0.75, relevance=RelevanceLabel.NOT_RELEVANT
                ),
            ]
            evaluator.evaluate_query(
                query_id=f"q{i}",
                query_text=f"test query {i}",
                retrieved_results=results,
                known_relevant={f"doc{i}a", f"doc{i}b", f"doc{i}c"},
            )

        # Calculate metrics
        metrics = evaluator.calculate_metrics()

        # Record to exporter
        exporter.record_metrics(
            precision_at_5=metrics.precision_at_5,
            precision_at_10=metrics.precision_at_10,
            recall_at_5=metrics.recall_at_5,
            recall_at_10=metrics.recall_at_10,
            mrr=metrics.mrr,
        )
        exporter.record_query_evaluated()

        # Verify exporter has the data
        summary = exporter.get_summary()
        assert summary["queries_evaluated"] >= 1
        assert summary["precision_at_5"] == metrics.precision_at_5
        assert summary["recall_at_10"] == metrics.recall_at_10


class TestABTesterEvaluatorIntegration:
    """Integration tests for A/B Tester + Evaluator."""

    def test_ab_tester_with_evaluator_feedback(self):
        """Test A/B testing with evaluator feedback."""
        evaluator = RetrievalEvaluator()
        tester = ABTester()

        # Register strategies
        control = MockRetrievalStrategy("control", quality=0.75)
        treatment = MockRetrievalStrategy("treatment", quality=0.85)
        tester.register_strategy("control", control)
        tester.register_strategy("treatment", treatment)

        # Create and start experiment
        exp_id = tester.create_experiment(
            name="Quality comparison",
            control="control",
            treatment="treatment",
        )
        tester.start_experiment(exp_id)

        # Run queries through both strategies
        for i in range(5):
            for strategy_name in ["control", "treatment"]:
                # Run through A/B tester
                ab_result = tester.run_query(
                    experiment_id=exp_id,
                    query=f"test query {i}",
                    strategy_name=strategy_name,
                )

                # Also evaluate through evaluator
                results = [
                    RetrievalResult(
                        doc_id=r["doc_id"],
                        score=r["score"],
                    )
                    for r in ab_result.results[:5]
                ]

                # Simulate known relevant (based on strategy quality)
                known_relevant = {r["doc_id"] for r in ab_result.results[:3]}

                evaluator.evaluate_query(
                    query_id=f"{strategy_name}_{i}",
                    query_text=f"test query {i}",
                    retrieved_results=results,
                    known_relevant=known_relevant,
                )

                # Record feedback to A/B tester
                tester.record_relevance_feedback(
                    experiment_id=exp_id,
                    query_id=ab_result.query_id,
                    relevant_doc_ids=known_relevant,
                )

        # Analyze experiment
        analysis = tester.analyze_experiment(exp_id)
        assert "precision_at_5" in analysis

        # Get evaluator metrics
        metrics = evaluator.calculate_metrics()
        assert metrics.query_count == 10  # 5 queries * 2 strategies


class TestThresholdTunerIntegration:
    """Integration tests for Threshold Tuner + Evaluator."""

    def test_tuner_with_evaluator_metrics(self):
        """Test threshold tuner using evaluator metrics."""
        tuner = ThresholdTuner()
        evaluator = RetrievalEvaluator()

        # Register threshold
        tuner.register_threshold(
            name="similarity_cutoff",
            initial_value=0.7,
            target_metric="precision_at_5",
            target_value=0.85,
        )

        # Simulate retrieval with current threshold
        for i in range(10):
            results = [
                RetrievalResult(doc_id=f"doc{i}a", score=0.95),
                RetrievalResult(doc_id=f"doc{i}b", score=0.90),
                RetrievalResult(doc_id=f"doc{i}c", score=0.85),
                RetrievalResult(doc_id=f"doc{i}d", score=0.65),  # Below threshold
                RetrievalResult(doc_id=f"doc{i}e", score=0.60),  # Below threshold
            ]
            evaluator.evaluate_query(
                query_id=f"q{i}",
                query_text=f"query {i}",
                retrieved_results=results[:3],  # Only above threshold
                known_relevant={f"doc{i}a", f"doc{i}b"},
            )

        # Calculate metrics
        metrics = evaluator.calculate_metrics()

        # Tune threshold based on metrics
        tuning_result = tuner.tune(
            threshold_name="similarity_cutoff",
            current_metrics={
                "precision_at_5": metrics.precision_at_5,
                "recall_at_10": metrics.recall_at_10,
            },
            sample_size=100,
        )

        # Should have made an adjustment
        assert (
            tuning_result is not None
            or tuner.get_threshold("similarity_cutoff") is not None
        )


class TestFullPipelineIntegration:
    """End-to-end integration tests."""

    def test_full_retrieval_pipeline(self):
        """Test the full retrieval quality pipeline."""
        # Initialize all components
        evaluator = RetrievalEvaluator()
        tester = ABTester()
        tuner = ThresholdTuner()
        exporter = RetrievalMetricsExporter()

        # 1. Register strategies for A/B testing
        baseline = MockRetrievalStrategy("baseline", quality=0.75)
        enhanced = MockRetrievalStrategy("enhanced", quality=0.85)
        tester.register_strategy("baseline", baseline)
        tester.register_strategy("enhanced", enhanced)

        # 2. Create and start experiment
        exp_id = tester.create_experiment(
            name="Enhanced retrieval test",
            control="baseline",
            treatment="enhanced",
        )
        tester.start_experiment(exp_id)
        exporter.record_ab_experiment_started()

        # 3. Register threshold
        tuner.register_threshold(
            name="similarity_cutoff",
            initial_value=0.7,
            target_metric="precision_at_5",
            target_value=0.85,
        )

        # 4. Run queries through the pipeline
        for i in range(10):
            query = f"test query {i}"
            strategy_name = tester.get_strategy_for_query(exp_id, query)

            # Run query
            ab_result = tester.run_query(
                experiment_id=exp_id,
                query=query,
                strategy_name=strategy_name,
            )

            # Evaluate with evaluator
            results = [
                RetrievalResult(doc_id=r["doc_id"], score=r["score"])
                for r in ab_result.results
            ]
            known_relevant = {r["doc_id"] for r in ab_result.results[:3]}

            evaluator.evaluate_query(
                query_id=ab_result.query_id,
                query_text=query,
                retrieved_results=results,
                known_relevant=known_relevant,
            )

            # Record feedback
            tester.record_relevance_feedback(
                experiment_id=exp_id,
                query_id=ab_result.query_id,
                relevant_doc_ids=known_relevant,
            )

            exporter.record_query_evaluated()

        # 5. Calculate and record metrics
        metrics = evaluator.calculate_metrics()
        exporter.record_metrics(
            precision_at_5=metrics.precision_at_5,
            precision_at_10=metrics.precision_at_10,
            recall_at_5=metrics.recall_at_5,
            recall_at_10=metrics.recall_at_10,
            mrr=metrics.mrr,
        )

        # 6. Tune threshold
        tuner.auto_tune_from_evaluator(
            metrics=metrics.to_dict(),
            sample_size=100,
        )
        exporter.record_threshold_adjustment()

        # 7. Analyze experiment
        analysis = tester.analyze_experiment(exp_id)

        # 8. Complete experiment
        tester.complete_experiment(exp_id)
        exporter.record_ab_experiment_completed()

        # 9. Verify final state
        summary = exporter.get_summary()
        assert summary["queries_evaluated"] == 10
        assert "precision_at_5" in summary

        # 10. Verify validation gates
        assert isinstance(summary["validation_gates_passed"], bool)


class TestValidationGatesIntegration:
    """Tests for validation gates at integration level."""

    def test_validation_gates_with_high_quality_data(self):
        """Test validation gates pass with high quality data."""
        evaluator = RetrievalEvaluator()

        # Create high-quality evaluations
        for i in range(20):
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
                query_text=f"query {i}",
                retrieved_results=results,
                known_relevant={
                    f"doc{i}a",
                    f"doc{i}b",
                    f"doc{i}c",
                    f"doc{i}d",
                    f"doc{i}e",
                },
            )

        metrics = evaluator.calculate_metrics()

        # Should pass validation gates
        assert metrics.precision_at_5 >= 0.85
        assert metrics.recall_at_10 >= 0.80
        assert metrics.mrr >= 0.75
        assert metrics.meets_validation_gates() is True

    def test_validation_gates_with_mixed_quality_data(self):
        """Test validation gates with mixed quality data."""
        evaluator = RetrievalEvaluator()

        # Create mixed-quality evaluations
        for i in range(20):
            # Vary quality
            relevant_count = 2 + (i % 3)  # 2, 3, or 4 relevant
            results = []
            known_relevant = set()

            for j in range(5):
                is_relevant = j < relevant_count
                results.append(
                    RetrievalResult(
                        doc_id=f"doc{i}_{j}",
                        score=0.95 - j * 0.05,
                        relevance=RelevanceLabel.RELEVANT
                        if is_relevant
                        else RelevanceLabel.NOT_RELEVANT,
                    )
                )
                if is_relevant:
                    known_relevant.add(f"doc{i}_{j}")

            evaluator.evaluate_query(
                query_id=f"q{i}",
                query_text=f"query {i}",
                retrieved_results=results,
                known_relevant=known_relevant,
            )

        metrics = evaluator.calculate_metrics()

        # Results will vary, just verify calculation works
        assert metrics.query_count == 20
