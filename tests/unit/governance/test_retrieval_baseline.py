"""
Tests for Retrieval Baseline script.

ST-GOV-MINI-001: Retrieval Baseline Tests
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.governance.retrieval_baseline import (
    DEFAULT_TEST_QUERIES,
    CoverageMetrics,
    LatencyMetrics,
    RelevanceMetrics,
    RetrievalBaselineData,
    TopKAccuracy,
    calculate_coverage,
    calculate_percentile,
    calculate_std_dev,
    create_retrieval_baseline,
    measure_latency,
    measure_relevance,
    save_baseline,
)


class TestLatencyMetrics:
    """Tests for LatencyMetrics dataclass."""

    def test_latency_metrics_defaults(self):
        """Test LatencyMetrics default values."""
        metrics = LatencyMetrics()

        assert metrics.p50_ms == 0.0
        assert metrics.p95_ms == 0.0
        assert metrics.p99_ms == 0.0
        assert metrics.mean_ms == 0.0
        assert metrics.min_ms == 0.0
        assert metrics.max_ms == 0.0
        assert metrics.samples == 0

    def test_latency_metrics_with_values(self):
        """Test LatencyMetrics with values."""
        metrics = LatencyMetrics(
            p50_ms=25.0,
            p95_ms=50.0,
            p99_ms=100.0,
            mean_ms=30.0,
            min_ms=10.0,
            max_ms=150.0,
            samples=100,
        )

        assert metrics.p50_ms == 25.0
        assert metrics.p95_ms == 50.0
        assert metrics.p99_ms == 100.0
        assert metrics.mean_ms == 30.0
        assert metrics.min_ms == 10.0
        assert metrics.max_ms == 150.0
        assert metrics.samples == 100


class TestRelevanceMetrics:
    """Tests for RelevanceMetrics dataclass."""

    def test_relevance_metrics_defaults(self):
        """Test RelevanceMetrics default values."""
        metrics = RelevanceMetrics()

        assert metrics.mean_score == 0.0
        assert metrics.min_score == 0.0
        assert metrics.max_score == 0.0
        assert metrics.std_dev == 0.0


class TestTopKAccuracy:
    """Tests for TopKAccuracy dataclass."""

    def test_top_k_accuracy_defaults(self):
        """Test TopKAccuracy default values."""
        metrics = TopKAccuracy()

        assert metrics.k5_precision == 0.0
        assert metrics.k5_recall == 0.0
        assert metrics.k10_precision == 0.0
        assert metrics.k10_recall == 0.0
        assert metrics.mrr == 0.0


class TestCoverageMetrics:
    """Tests for CoverageMetrics dataclass."""

    def test_coverage_metrics_defaults(self):
        """Test CoverageMetrics default values."""
        metrics = CoverageMetrics()

        assert metrics.total_queries == 0
        assert metrics.queries_with_results == 0
        assert metrics.coverage_ratio == 0.0
        assert metrics.empty_results_count == 0


class TestRetrievalBaselineData:
    """Tests for RetrievalBaselineData dataclass."""

    def test_baseline_to_dict(self):
        """Test converting baseline to dictionary."""
        baseline = RetrievalBaselineData()
        baseline.metadata = {"capture_time": "2026-01-01T00:00:00Z"}
        baseline.latency = LatencyMetrics(p50_ms=25.0, p95_ms=50.0)
        baseline.relevance = RelevanceMetrics(mean_score=0.75)
        baseline.top_k = TopKAccuracy(k5_precision=0.8, mrr=0.7)
        baseline.coverage = CoverageMetrics(total_queries=10, coverage_ratio=0.9)

        data = baseline.to_dict()

        assert data["metadata"]["capture_time"] == "2026-01-01T00:00:00Z"
        assert data["latency"]["p50_ms"] == 25.0
        assert data["latency"]["p95_ms"] == 50.0
        assert data["relevance"]["mean_score"] == 0.75
        assert data["top_k_accuracy"]["k5_precision"] == 0.8
        assert data["top_k_accuracy"]["mrr"] == 0.7
        assert data["coverage"]["total_queries"] == 10
        assert data["coverage"]["coverage_ratio"] == 0.9

    def test_baseline_to_json(self):
        """Test converting baseline to JSON."""
        baseline = RetrievalBaselineData()
        baseline.metadata = {"capture_time": "2026-01-01T00:00:00Z"}

        json_str = baseline.to_json()

        # Should be valid JSON
        data = json.loads(json_str)
        assert data["metadata"]["capture_time"] == "2026-01-01T00:00:00Z"


class TestCalculatePercentile:
    """Tests for calculate_percentile function."""

    def test_calculate_percentile_empty(self):
        """Test percentile with empty list."""
        result = calculate_percentile([], 50)
        assert result == 0.0

    def test_calculate_percentile_single_value(self):
        """Test percentile with single value."""
        result = calculate_percentile([10.0], 50)
        assert result == 10.0

    def test_calculate_percentile_multiple_values(self):
        """Test percentile with multiple values."""
        values = [10.0, 20.0, 30.0, 40.0, 50.0]

        p50 = calculate_percentile(values, 50)
        assert p50 == 30.0

        p90 = calculate_percentile(values, 90)
        assert p90 == 50.0


class TestCalculateStdDev:
    """Tests for calculate_std_dev function."""

    def test_calculate_std_dev_empty(self):
        """Test std dev with empty list."""
        result = calculate_std_dev([], 0.0)
        assert result == 0.0

    def test_calculate_std_dev_single_value(self):
        """Test std dev with single value."""
        result = calculate_std_dev([10.0], 10.0)
        assert result == 0.0

    def test_calculate_std_dev_multiple_values(self):
        """Test std dev with multiple values."""
        values = [10.0, 20.0, 30.0]
        mean = sum(values) / len(values)
        result = calculate_std_dev(values, mean)

        # std dev of [10, 20, 30] with mean 20
        # variance = ((10-20)^2 + (20-20)^2 + (30-20)^2) / 3 = 200/3 = 66.67
        # std dev = sqrt(66.67) ≈ 8.16
        assert result > 8.0
        assert result < 8.2


class TestMeasureLatency:
    """Tests for measure_latency function."""

    def test_measure_latency_empty(self):
        """Test latency metrics with empty list."""
        metrics = measure_latency([])

        assert metrics.p50_ms == 0.0
        assert metrics.samples == 0

    def test_measure_latency_single_value(self):
        """Test latency metrics with single value."""
        metrics = measure_latency([25.0])

        assert metrics.p50_ms == 25.0
        assert metrics.mean_ms == 25.0
        assert metrics.min_ms == 25.0
        assert metrics.max_ms == 25.0
        assert metrics.samples == 1

    def test_measure_latency_multiple_values(self):
        """Test latency metrics with multiple values."""
        latencies = [10.0, 20.0, 30.0, 40.0, 50.0]
        metrics = measure_latency(latencies)

        assert metrics.p50_ms == 30.0
        assert metrics.mean_ms == 30.0
        assert metrics.min_ms == 10.0
        assert metrics.max_ms == 50.0
        assert metrics.samples == 5


class TestMeasureRelevance:
    """Tests for measure_relevance function."""

    def test_measure_relevance_empty(self):
        """Test relevance metrics with empty results."""
        metrics = measure_relevance([])

        assert metrics.mean_score == 0.0

    def test_measure_relevance_with_results(self):
        """Test relevance metrics with results."""
        from scripts.governance.retrieval_baseline import RetrievalResult

        results = [
            [
                RetrievalResult(doc_id="1", score=0.9),
                RetrievalResult(doc_id="2", score=0.8),
            ],
            [RetrievalResult(doc_id="3", score=0.7)],
        ]

        metrics = measure_relevance(results)

        assert abs(metrics.mean_score - (0.9 + 0.8 + 0.7) / 3) < 0.0001
        assert metrics.min_score == 0.7
        assert metrics.max_score == 0.9


class TestCalculateCoverage:
    """Tests for calculate_coverage function."""

    def test_calculate_coverage_all_empty(self):
        """Test coverage when all results are empty."""

        results = [[], [], []]
        metrics = calculate_coverage(3, results)

        assert metrics.total_queries == 3
        assert metrics.queries_with_results == 0
        assert metrics.coverage_ratio == 0.0
        assert metrics.empty_results_count == 3

    def test_calculate_coverage_all_have_results(self):
        """Test coverage when all queries have results."""
        from scripts.governance.retrieval_baseline import RetrievalResult

        results = [
            [RetrievalResult(doc_id="1", score=0.9)],
            [RetrievalResult(doc_id="2", score=0.8)],
        ]
        metrics = calculate_coverage(2, results)

        assert metrics.total_queries == 2
        assert metrics.queries_with_results == 2
        assert metrics.coverage_ratio == 1.0
        assert metrics.empty_results_count == 0

    def test_calculate_coverage_mixed(self):
        """Test coverage with mixed results."""
        from scripts.governance.retrieval_baseline import RetrievalResult

        results = [
            [RetrievalResult(doc_id="1", score=0.9)],
            [],
            [RetrievalResult(doc_id="2", score=0.8)],
        ]
        metrics = calculate_coverage(3, results)

        assert metrics.total_queries == 3
        assert metrics.queries_with_results == 2
        assert metrics.coverage_ratio == 2 / 3
        assert metrics.empty_results_count == 1


class TestCreateRetrievalBaseline:
    """Tests for create_retrieval_baseline function."""

    def test_create_baseline_no_clients(self):
        """Test creating baseline with no clients."""
        test_queries = ["query1", "query2"]
        baseline = create_retrieval_baseline(test_queries, None)

        assert baseline.metadata["baseline_type"] == "retrieval_quality"
        assert baseline.metadata["story_id"] == "ST-GOV-MINI-001"
        assert baseline.metadata["test_queries_count"] == 2
        assert "capture_time" in baseline.metadata

        # Should have latency metrics
        assert baseline.latency.samples > 0

    def test_create_baseline_with_default_queries(self):
        """Test creating baseline with default queries."""
        baseline = create_retrieval_baseline(DEFAULT_TEST_QUERIES[:3], None)

        assert baseline.metadata["test_queries_count"] == 3
        assert len(baseline.query_results) == 3


class TestSaveBaseline:
    """Tests for save_baseline function."""

    def test_save_baseline_json(self, tmp_path):
        """Test saving baseline as JSON."""
        baseline = RetrievalBaselineData()
        baseline.metadata = {"capture_time": "2026-01-01T00:00:00Z"}

        filepath = save_baseline(baseline, tmp_path, "json")

        assert filepath.exists()
        assert filepath.suffix == ".json"

        with open(filepath) as f:
            data = json.load(f)
        assert data["metadata"]["capture_time"] == "2026-01-01T00:00:00Z"

    def test_save_baseline_creates_directory(self, tmp_path):
        """Test that save_baseline creates output directory."""
        baseline = RetrievalBaselineData()
        output_dir = tmp_path / "nested" / "dir"

        filepath = save_baseline(baseline, output_dir, "json")

        assert output_dir.exists()
        assert filepath.exists()


class TestDefaultTestQueries:
    """Tests for default test queries."""

    def test_default_queries_not_empty(self):
        """Test that default queries list is not empty."""
        assert len(DEFAULT_TEST_QUERIES) > 0

    def test_default_queries_contain_expected_patterns(self):
        """Test that default queries contain expected patterns."""
        queries_lower = [q.lower() for q in DEFAULT_TEST_QUERIES]

        # Check for expected query types
        assert any("trading" in q for q in queries_lower)
        assert any("risk" in q for q in queries_lower)
        assert any("incident" in q for q in queries_lower)
        assert any("agent" in q for q in queries_lower)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
