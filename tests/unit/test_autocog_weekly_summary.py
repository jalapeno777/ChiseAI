"""Unit tests for autocog_weekly_summary.py"""

import json
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.autocog_weekly_summary import (
    analyze_cycles,
    analyze_experiments,
    analyze_self_assessments,
    generate_recommendations,
    infer_cycle_mode,
    load_cycles,
    load_self_assessments,
    parse_timestamp,
    summary_to_json,
    summary_to_markdown,
)


class TestInferCycleMode(unittest.TestCase):
    """Tests for infer_cycle_mode function."""

    def test_belief_consistency_mode(self):
        """Cycles with belief conflicts should return belief_consistency."""
        cycle = {"belief_conflicts": 1, "belief_revisions": 0}
        self.assertEqual(infer_cycle_mode(cycle), "belief_consistency")

    def test_improvement_mode(self):
        """Cycles running experiments should return improvement."""
        cycle = {"experiments_run": 2, "belief_conflicts": 0}
        self.assertEqual(infer_cycle_mode(cycle), "improvement")

    def test_constitution_audit_mode(self):
        """Cycles with constitution violations should return constitution_audit."""
        cycle = {"constitution_violations": 1, "belief_conflicts": 0}
        self.assertEqual(infer_cycle_mode(cycle), "constitution_audit")

    def test_skip_rate_alert_mode(self):
        """Cycles with skip rate alerts should return full."""
        cycle = {
            "belief_conflicts": 0,
            "metrics": {"skip_rate_check": {"alert_triggered": True}},
        }
        self.assertEqual(infer_cycle_mode(cycle), "full")

    def test_autonomy_tune_mode(self):
        """Cycles with autonomy level changes should return autonomy_tune."""
        cycle = {
            "belief_conflicts": 0,
            "autonomy_level_before": "supervised",
            "autonomy_level_after": "bounded",
            "metrics": {},
        }
        self.assertEqual(infer_cycle_mode(cycle), "autonomy_tune")

    def test_default_full_mode(self):
        """Default mode should be full."""
        cycle = {
            "belief_conflicts": 0,
            "autonomy_level_before": "bounded",
            "autonomy_level_after": "bounded",
            "metrics": {},
        }
        self.assertEqual(infer_cycle_mode(cycle), "full")

    def test_explicit_mode(self):
        """Explicit mode field should take precedence."""
        cycle = {"mode": "calibration", "belief_conflicts": 1}
        self.assertEqual(infer_cycle_mode(cycle), "calibration")


class TestParseTimestamp(unittest.TestCase):
    """Tests for parse_timestamp function."""

    def test_iso_format_with_z(self):
        """Should parse ISO format with Z suffix."""
        result = parse_timestamp("2026-03-29T00:25:04.085967Z")
        self.assertEqual(result.year, 2026)
        self.assertEqual(result.month, 3)
        self.assertEqual(result.day, 29)

    def test_iso_format_with_offset(self):
        """Should parse ISO format with timezone offset."""
        result = parse_timestamp("2026-03-29T00:25:04.085967+00:00")
        self.assertEqual(result.year, 2026)
        self.assertEqual(result.month, 3)
        self.assertEqual(result.day, 29)


class TestAnalyzeCycles(unittest.TestCase):
    """Tests for analyze_cycles function."""

    def test_empty_cycles(self):
        """Empty cycles list should produce zero summary."""

        summary, anomalies = analyze_cycles([])
        self.assertEqual(summary.total_cycles, 0)
        self.assertEqual(anomalies.skip_rate_alerts, 0)

    def test_completed_vs_failed(self):
        """Should correctly count completed and failed cycles."""
        cycles = [
            {"status": "completed", "started_at": "2026-03-29T00:00:00Z"},
            {"status": "completed", "started_at": "2026-03-29T01:00:00Z"},
            {"status": "failed", "started_at": "2026-03-29T02:00:00Z"},
        ]
        summary, _ = analyze_cycles(cycles)
        self.assertEqual(summary.total_cycles, 3)
        self.assertEqual(summary.completed_cycles, 2)
        self.assertEqual(summary.failed_cycles, 1)

    def test_belief_conflicts_counted(self):
        """Should sum belief conflicts across cycles."""
        cycles = [
            {"belief_conflicts": 2, "started_at": "2026-03-29T00:00:00Z"},
            {"belief_conflicts": 3, "started_at": "2026-03-29T01:00:00Z"},
        ]
        summary, _ = analyze_cycles(cycles)
        self.assertEqual(summary.belief_conflicts_detected, 5)

    def test_autonomy_changes_counted(self):
        """Should count cycles with autonomy level changes."""
        cycles = [
            {
                "autonomy_level_before": "supervised",
                "autonomy_level_after": "bounded",
                "started_at": "2026-03-29T00:00:00Z",
            },
            {
                "autonomy_level_before": "bounded",
                "autonomy_level_after": "bounded",
                "started_at": "2026-03-29T01:00:00Z",
            },
        ]
        summary, _ = analyze_cycles(cycles)
        self.assertEqual(summary.autonomy_changes, 1)

    def test_skip_rate_alert_detected(self):
        """Should detect skip rate alerts."""
        cycles = [
            {
                "started_at": "2026-03-29T00:00:00Z",
                "metrics": {
                    "skip_rate_check": {
                        "alert_triggered": True,
                        "alert_message": "SKIP RATE ALERT: 86.7%",
                    }
                },
            }
        ]
        _, anomalies = analyze_cycles(cycles)
        self.assertEqual(anomalies.skip_rate_alerts, 1)
        self.assertEqual(len(anomalies.warnings), 1)


class TestAnalyzeExperiments(unittest.TestCase):
    """Tests for analyze_experiments function."""

    def test_no_experiments(self):
        """Cycles with no experiments should produce zero summary."""

        cycles = [
            {"experiments_run": 0},
            {"experiments_run": 0},
        ]
        summary = analyze_experiments(cycles)
        self.assertEqual(summary.total_experiments, 0)
        self.assertEqual(summary.promoted, 0)
        self.assertEqual(summary.rejected, 0)

    def test_promoted_experiments(self):
        """Should correctly count promoted experiments."""
        cycles = [
            {"experiments_run": 2, "promotions": 2, "rejections": 0},
        ]
        summary = analyze_experiments(cycles)
        self.assertEqual(summary.total_experiments, 2)
        self.assertEqual(summary.promoted, 2)
        self.assertEqual(summary.experiments_by_outcome["promoted"], 2)

    def test_rejected_experiments(self):
        """Should correctly count rejected experiments."""
        cycles = [
            {"experiments_run": 3, "promotions": 0, "rejections": 3},
        ]
        summary = analyze_experiments(cycles)
        self.assertEqual(summary.total_experiments, 3)
        self.assertEqual(summary.rejected, 3)
        self.assertEqual(summary.experiments_by_outcome["rejected"], 3)

    def test_mixed_outcome(self):
        """Should correctly categorize mixed outcomes."""
        cycles = [
            {"experiments_run": 2, "promotions": 1, "rejections": 1},
        ]
        summary = analyze_experiments(cycles)
        self.assertEqual(summary.experiments_by_outcome["mixed"], 2)


class TestAnalyzeSelfAssessments(unittest.TestCase):
    """Tests for analyze_self_assessments function."""

    def test_empty_assessments(self):
        """Empty assessments should produce zero summary."""

        trend = analyze_self_assessments([])
        self.assertIsNone(trend.start_score)
        self.assertEqual(trend.score_count, 0)

    def test_score_trend(self):
        """Should track start, end, min, max scores."""
        assessments = [
            {
                "overall_score": 0.7,
                "created_at": "2026-03-29T00:00:00Z",
                "assessment_date": "2026-03-29",
                "dimensions": {},
            },
            {
                "overall_score": 0.8,
                "created_at": "2026-03-29T06:00:00Z",
                "assessment_date": "2026-03-29",
                "dimensions": {},
            },
            {
                "overall_score": 0.75,
                "created_at": "2026-03-29T12:00:00Z",
                "assessment_date": "2026-03-29",
                "dimensions": {},
            },
        ]
        trend = analyze_self_assessments(assessments)
        self.assertEqual(trend.start_score, 0.7)
        self.assertEqual(trend.end_score, 0.75)
        self.assertEqual(trend.min_score, 0.7)
        self.assertEqual(trend.max_score, 0.8)
        self.assertAlmostEqual(trend.avg_score, 0.75, places=2)
        self.assertEqual(trend.score_count, 3)

    def test_dimension_averages(self):
        """Should calculate dimension averages correctly."""
        assessments = [
            {
                "overall_score": 0.8,
                "created_at": "2026-03-29T00:00:00Z",
                "assessment_date": "2026-03-29",
                "dimensions": {"safety_alignment": 0.9, "memory_health": 0.7},
            },
            {
                "overall_score": 0.8,
                "created_at": "2026-03-29T06:00:00Z",
                "assessment_date": "2026-03-29",
                "dimensions": {"safety_alignment": 1.0, "memory_health": 0.8},
            },
        ]
        trend = analyze_self_assessments(assessments)
        self.assertAlmostEqual(trend.dimension_averages["safety_alignment"], 0.95)
        self.assertAlmostEqual(trend.dimension_averages["memory_health"], 0.75)


class TestGenerateRecommendations(unittest.TestCase):
    """Tests for generate_recommendations function."""

    def test_skip_rate_recommendation(self):
        """Should recommend addressing skip rate when alerts exist."""
        from scripts.autocog_weekly_summary import (
            AnomalyReport,
            CycleSummary,
            ExperimentSummary,
            SelfAssessmentTrend,
        )

        cycles = CycleSummary(total_cycles=5)
        experiments = ExperimentSummary()
        assessments = SelfAssessmentTrend()
        anomalies = AnomalyReport(skip_rate_alerts=3)

        recs = generate_recommendations(cycles, experiments, assessments, anomalies)
        self.assertTrue(any("skip rate" in r.lower() for r in recs))

    def test_no_experiments_recommendation(self):
        """Should recommend enabling experiments when none run."""
        from scripts.autocog_weekly_summary import (
            AnomalyReport,
            CycleSummary,
            ExperimentSummary,
            SelfAssessmentTrend,
        )

        cycles = CycleSummary()
        experiments = ExperimentSummary(total_experiments=0)
        assessments = SelfAssessmentTrend()
        anomalies = AnomalyReport()

        recs = generate_recommendations(cycles, experiments, assessments, anomalies)
        self.assertTrue(any("experiment" in r.lower() for r in recs))

    def test_score_decline_recommendation(self):
        """Should recommend investigation when score declines significantly."""
        from scripts.autocog_weekly_summary import (
            AnomalyReport,
            CycleSummary,
            ExperimentSummary,
            SelfAssessmentTrend,
        )

        cycles = CycleSummary()
        experiments = ExperimentSummary()
        assessments = SelfAssessmentTrend(start_score=0.9, end_score=0.7, score_count=5)
        anomalies = AnomalyReport()

        recs = generate_recommendations(cycles, experiments, assessments, anomalies)
        self.assertTrue(
            any("declined" in r.lower() or "investigate" in r.lower() for r in recs)
        )


class TestSummaryOutput(unittest.TestCase):
    """Tests for summary output generation."""

    def setUp(self):
        """Set up test fixtures."""
        from scripts.autocog_weekly_summary import (
            AnomalyReport,
            CycleSummary,
            ExperimentSummary,
            SelfAssessmentTrend,
            WeeklySummary,
        )

        self.summary = WeeklySummary(
            generated_at="2026-03-29T12:00:00+00:00",
            period_start="2026-03-22",
            period_end="2026-03-29",
            cycles=CycleSummary(
                total_cycles=10,
                completed_cycles=9,
                failed_cycles=1,
                by_mode={"full": 7, "belief_consistency": 3},
                belief_conflicts_detected=5,
                autonomy_changes=2,
            ),
            experiments=ExperimentSummary(
                total_experiments=4,
                experiments_by_outcome={"promoted": 3, "rejected": 1},
                promoted=3,
                rejected=1,
            ),
            self_assessment_trend=SelfAssessmentTrend(
                start_score=0.75,
                end_score=0.82,
                start_date="2026-03-22",
                end_date="2026-03-29",
                min_score=0.70,
                max_score=0.85,
                avg_score=0.78,
                score_count=10,
            ),
            anomalies=AnomalyReport(skip_rate_alerts=1, warnings=["Test warning"]),
            recommendations=["Test recommendation"],
        )

    def test_summary_to_json(self):
        """Should convert summary to valid JSON-serializable dict."""
        json_data = summary_to_json(self.summary)

        self.assertEqual(json_data["period"]["start"], "2026-03-22")
        self.assertEqual(json_data["period"]["end"], "2026-03-29")
        self.assertEqual(json_data["cycles"]["total"], 10)
        self.assertEqual(json_data["experiments"]["total_run"], 4)
        self.assertEqual(json_data["self_assessment_trend"]["start_score"], 0.75)
        self.assertEqual(json_data["anomalies"]["skip_rate_alerts"], 1)

        # Should be JSON serializable
        json_str = json.dumps(json_data)
        parsed = json.loads(json_str)
        self.assertEqual(parsed["cycles"]["total"], 10)

    def test_summary_to_markdown(self):
        """Should convert summary to readable markdown."""
        md = summary_to_markdown(self.summary)

        self.assertIn("2026-03-22 to 2026-03-29", md)
        self.assertIn("Total Cycles", md)
        self.assertIn("10", md)
        self.assertIn("Self-Assessment Trend", md)
        self.assertIn("Recommendations", md)
        self.assertIn("Test recommendation", md)


class TestIntegration(unittest.TestCase):
    """Integration tests using temporary directories."""

    def setUp(self):
        """Create temp directories with test data."""
        self.temp_cycles = tempfile.TemporaryDirectory()
        self.temp_assessments = tempfile.TemporaryDirectory()

        # Create test cycles
        now = datetime.now(UTC)
        for i in range(3):
            cycle = {
                "run_id": f"test-cycle-{i}",
                "started_at": (now - timedelta(hours=i)).isoformat(),
                "completed_at": (
                    now - timedelta(hours=i) + timedelta(seconds=10)
                ).isoformat(),
                "status": "completed",
                "belief_conflicts": i,
                "experiments_run": 1 if i == 0 else 0,
                "promotions": 1 if i == 0 else 0,
                "rejections": 0,
                "autonomy_level_before": "bounded",
                "autonomy_level_after": "bounded",
                "metrics": {},
            }
            path = Path(self.temp_cycles.name) / f"autocog-test-{i}.json"
            with open(path, "w") as f:
                json.dump(cycle, f)

        # Create test self-assessments
        for i in range(2):
            sa = {
                "assessment_id": f"sa-{i}",
                "overall_score": 0.7 + (i * 0.1),
                "created_at": (now - timedelta(days=i)).isoformat(),
                "assessment_date": (now - timedelta(days=i)).strftime("%Y-%m-%d"),
                "dimensions": {"safety_alignment": 0.8, "memory_health": 0.7},
            }
            path = Path(self.temp_assessments.name) / f"self_assessment_test-{i}.json"
            with open(path, "w") as f:
                json.dump(sa, f)

    def tearDown(self):
        """Clean up temp directories."""
        self.temp_cycles.cleanup()
        self.temp_assessments.cleanup()

    @patch.object(Path, "exists", return_value=True)
    def test_load_cycles_from_temp(self, mock_exists):
        """Should load cycles from temporary directory."""
        import scripts.autocog_weekly_summary as aws

        original_cycles_dir = aws.CYCLES_DIR
        aws.CYCLES_DIR = Path(self.temp_cycles.name)

        try:
            cycles = load_cycles(days=7)
            self.assertEqual(len(cycles), 3)
        finally:
            aws.CYCLES_DIR = original_cycles_dir

    @patch.object(Path, "exists", return_value=True)
    def test_load_self_assessments_from_temp(self, mock_exists):
        """Should load self-assessments from temporary directory."""
        import scripts.autocog_weekly_summary as aws

        original_assessments_dir = aws.SELF_ASSESSMENTS_DIR
        aws.SELF_ASSESSMENTS_DIR = Path(self.temp_assessments.name)

        try:
            assessments = load_self_assessments(days=7)
            self.assertEqual(len(assessments), 2)
        finally:
            aws.SELF_ASSESSMENTS_DIR = original_assessments_dir


if __name__ == "__main__":
    unittest.main()
