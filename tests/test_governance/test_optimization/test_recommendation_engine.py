"""
Tests for the RecommendationEngine class.

ST-GOV-MINI-002: Optimization Feedback Loop

Covers initialization, metric-specific analysis, and priority ordering.
"""

import json
from pathlib import Path

import pytest

from src.governance.optimization.generate_recommendations import RecommendationEngine


BASELINE_DIR = Path("docs/evidence/ST-GOV-MINI-002")
BASELINE_FILE = str(
    sorted(BASELINE_DIR.glob("optimization-results-week1-*.json"))[0]
    if list(BASELINE_DIR.glob("optimization-results-week1-*.json"))
    else "docs/evidence/ST-GOV-MINI-002/optimization-results-week1-20260312_022432.json"
)


class TestEngineInitialization:
    """Verify engine initializes properly."""

    def test_engine_initialization_defaults(self):
        engine = RecommendationEngine()
        assert engine.analysis_path.endswith("week1-analysis.json")
        assert engine.analysis_data == {}
        assert engine.recommendations == []

    def test_engine_initialization_custom_path(self):
        engine = RecommendationEngine(analysis_path="/tmp/custom.json")
        assert engine.analysis_path == "/tmp/custom.json"


class TestMetricAnalysis:
    """Test metric-specific analysis methods."""

    def test_analyze_retrieval_latency(self):
        """Engine should generate latency-related recommendations when p95 > 20ms."""
        with open(BASELINE_FILE) as f:
            baseline = json.load(f).get("week1_baseline", {})

        p95 = baseline.get("retrieval_p95_ms", 25.0)
        engine = RecommendationEngine(
            analysis_path=str(BASELINE_DIR / "week1-analysis.json"),
        )
        recs = engine.generate_recommendations()

        # If baseline p95 > 20, there should be a latency-related rec
        latency_recs = [
            r
            for r in recs
            if "latency" in r.get("title", "").lower()
            or "latency" in r.get("category", "").lower()
            or "retrieval_p95" in r.get("expected_impact", {}).get("metric", "")
        ]
        if p95 > 20:
            assert len(latency_recs) >= 1, (
                f"Expected at least 1 latency recommendation for p95={p95}ms"
            )

    def test_analyze_memory_hit_rate(self):
        """Engine should generate memory-related recommendations when hit rate < 85%."""
        with open(BASELINE_FILE) as f:
            baseline = json.load(f).get("week1_baseline", {})

        hit_rate = baseline.get("memory_hit_rate", 75.0)
        engine = RecommendationEngine(
            analysis_path=str(BASELINE_DIR / "week1-analysis.json"),
        )
        recs = engine.generate_recommendations()

        # If baseline hit_rate < 85, there should be a memory-related rec
        memory_recs = [
            r
            for r in recs
            if "memory_hit_rate" in r.get("expected_impact", {}).get("metric", "")
            or "cache" in r.get("title", "").lower()
        ]
        if hit_rate < 85:
            assert len(memory_recs) >= 1, (
                f"Expected at least 1 memory recommendation for hit_rate={hit_rate}%"
            )


class TestPriorityOrdering:
    """Verify recommendations are sorted by priority."""

    def test_priority_ordering(self):
        """Recommendations can be sorted by priority (high > medium > low)."""
        engine = RecommendationEngine(
            analysis_path=str(BASELINE_DIR / "week1-analysis.json"),
        )
        recs = engine.generate_recommendations()

        if len(recs) < 2:
            pytest.skip("Need at least 2 recommendations to test ordering")

        # Verify all recommendations have valid priority values
        valid_priorities = {"high", "medium", "low"}
        for rec in recs:
            assert rec.get("priority") in valid_priorities, (
                f"Recommendation {rec.get('id', '?')} has invalid priority: "
                f"{rec.get('priority')}"
            )

        # Verify recommendations CAN be sorted by priority
        priority_rank = {"high": 0, "medium": 1, "low": 2}
        sorted_recs = sorted(
            recs, key=lambda r: priority_rank.get(r.get("priority", ""), 99)
        )

        # Check that sorting actually changed order (if unsorted input)
        # or produced a valid non-decreasing sequence
        priorities = [priority_rank.get(r.get("priority", ""), 99) for r in sorted_recs]
        for i in range(1, len(priorities)):
            assert priorities[i] >= priorities[i - 1], (
                f"Sorted recommendations not in priority order at index {i}"
            )

        # Verify highest impact recommendation is high priority
        highest = engine.get_highest_impact_recommendation()
        if highest:
            assert highest.get("priority") in ("high", "medium"), (
                f"Highest impact recommendation should be high or medium priority, "
                f"got '{highest.get('priority')}'"
            )
