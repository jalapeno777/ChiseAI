"""Unit tests for scripts/autocog/weekly_review.py"""

import json
import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.autocog.weekly_review import (
    _LESSON_BLOCK_PATTERN,
    CalibrationResult,
    DeferredItemsReview,
    LessonsReview,
    WeeklyReviewResult,
    _read_latest_assessment_from_redis,
    assess_risks,
    build_discord_embed,
    compute_week_key,
    parse_week_key,
    promote_lessons_to_qdrant,
    run_calibration,
    run_deferred_items_review,
    run_lessons_review,
    week_key_to_redis_key,
)


class TestComputeWeekKey(unittest.TestCase):
    """Tests for compute_week_key."""

    def test_current_week_format(self):
        """Week key should match ISO format YYYY-Www."""
        key = compute_week_key()
        self.assertRegex(key, r"^\d{4}-W\d{2}$")

    def test_specific_date(self):
        """Week key for a known date should be correct."""
        # 2026-04-12 is a Sunday, which is in ISO week 15 of 2026
        dt = datetime(2026, 4, 12, tzinfo=UTC)
        key = compute_week_key(dt)
        self.assertEqual(key, "2026-W15")

    def test_monday_start_of_week(self):
        """Monday should be in the same week as the following Sunday."""
        monday = datetime(2026, 4, 6, tzinfo=UTC)
        sunday = datetime(2026, 4, 12, tzinfo=UTC)
        self.assertEqual(compute_week_key(monday), compute_week_key(sunday))


class TestParseWeekKey(unittest.TestCase):
    """Tests for parse_week_key."""

    def test_valid_week_key(self):
        year, week = parse_week_key("2026-W15")
        self.assertEqual(year, 2026)
        self.assertEqual(week, 15)

    def test_week_01(self):
        year, week = parse_week_key("2026-W01")
        self.assertEqual(year, 2026)
        self.assertEqual(week, 1)

    def test_invalid_format_raises(self):
        with self.assertRaises(ValueError):
            parse_week_key("2026-15")
        with self.assertRaises(ValueError):
            parse_week_key("invalid")
        with self.assertRaises(ValueError):
            parse_week_key("W15")


class TestWeekKeyToRedisKey(unittest.TestCase):
    """Tests for week_key_to_redis_key."""

    def test_conversion(self):
        self.assertEqual(
            week_key_to_redis_key("2026-W15"),
            "bmad:chiseai:autocog:weekly:2026-W15",
        )


class TestReadLatestAssessmentFromRedis(unittest.TestCase):
    """Tests for _read_latest_assessment_from_redis (the fallback function)."""

    @patch("scripts.autocog.weekly_review._redis_get")
    def test_no_data(self, mock_get):
        """Should return fallback when no Redis data."""
        mock_get.return_value = None
        result = _read_latest_assessment_from_redis()
        self.assertIsNone(result["overall_score"])
        self.assertEqual(result["source"], "redis_fallback")

    @patch("scripts.autocog.weekly_review._redis_get")
    def test_with_valid_data(self, mock_get):
        """Should parse Redis data correctly."""
        mock_get.return_value = json.dumps(
            {
                "overall_score": 0.85,
                "dimensions": {"memory_health": 0.9},
                "findings": ["All good"],
                "recommendations": ["Keep going"],
                "status": "ok",
            }
        )
        result = _read_latest_assessment_from_redis()
        self.assertAlmostEqual(result["overall_score"], 0.85)
        self.assertEqual(result["source"], "redis_fallback")
        self.assertEqual(result["dimensions"]["memory_health"], 0.9)

    @patch("scripts.autocog.weekly_review._redis_get")
    def test_corrupt_data(self, mock_get):
        """Should handle corrupt Redis data gracefully."""
        mock_get.return_value = "not-json{{{"
        result = _read_latest_assessment_from_redis()
        self.assertEqual(result["status"], "error")
        self.assertIsNone(result["overall_score"])

    @patch("scripts.autocog.weekly_review._redis_get")
    def test_dict_payload(self, mock_get):
        """Should handle dict payload (non-string)."""
        mock_get.return_value = {
            "overall_score": 0.75,
            "dimensions": {},
            "findings": [],
            "recommendations": [],
            "status": "ok",
        }
        result = _read_latest_assessment_from_redis()
        self.assertAlmostEqual(result["overall_score"], 0.75)


class TestRunCalibration(unittest.TestCase):
    """Tests for run_calibration."""

    @patch("scripts.autocog.weekly_review._redis_scan")
    def test_no_calibration_keys(self, mock_scan):
        mock_scan.return_value = []
        result = run_calibration("2026-W15")
        self.assertEqual(result.total_predictions, 0)
        self.assertEqual(result.calibration_error, 0.0)
        self.assertEqual(result.bias_type, "none")

    @patch("scripts.autocog.weekly_review._redis_hgetall")
    @patch("scripts.autocog.weekly_review._redis_scan")
    def test_with_matched_data(self, mock_scan, mock_hgetall):
        mock_scan.return_value = [
            "bmad:chiseai:metacog:calibration:agent:jarvis:weekly:2026-W15:task1",
            "bmad:chiseai:metacog:calibration:agent:jarvis:weekly:2026-W15:task2",
        ]
        mock_hgetall.side_effect = [
            {"confidence": "0.8", "actual": "1.0", "predicted": "0.8"},
            {"confidence": "0.6", "actual": "0.0", "predicted": "0.6"},
        ]
        result = run_calibration("2026-W15")
        self.assertEqual(result.total_predictions, 2)
        self.assertEqual(result.matched_outcomes, 2)
        self.assertAlmostEqual(result.avg_confidence, 0.7)
        self.assertAlmostEqual(result.avg_actual, 0.5)
        self.assertGreater(result.calibration_error, 0.0)
        self.assertEqual(result.bias_type, "overconfidence")

    @patch("scripts.autocog.weekly_review._redis_hgetall")
    @patch("scripts.autocog.weekly_review._redis_scan")
    def test_boolean_outcomes(self, mock_scan, mock_hgetall):
        mock_scan.return_value = [
            "bmad:chiseai:metacog:calibration:agent:jarvis:weekly:2026-W15:task1",
        ]
        mock_hgetall.return_value = {
            "confidence": "0.9",
            "actual": "success",
            "predicted": "0.9",
        }
        result = run_calibration("2026-W15")
        self.assertEqual(result.matched_outcomes, 1)
        self.assertAlmostEqual(result.avg_actual, 1.0)

    @patch("scripts.autocog.weekly_review._redis_hgetall")
    @patch("scripts.autocog.weekly_review._redis_scan")
    def test_underconfidence_bias(self, mock_scan, mock_hgetall):
        mock_scan.return_value = [
            "bmad:chiseai:metacog:calibration:agent:jarvis:weekly:2026-W15:task1",
        ]
        mock_hgetall.return_value = {
            "confidence": "0.3",
            "actual": "0.9",
            "predicted": "0.3",
        }
        result = run_calibration("2026-W15")
        self.assertEqual(result.bias_type, "underconfidence")

    @patch("scripts.autocog.weekly_review._redis_hgetall")
    @patch("scripts.autocog.weekly_review._redis_scan")
    def test_empty_hgetall(self, mock_scan, mock_hgetall):
        """Should handle empty hash responses."""
        mock_scan.return_value = ["key1"]
        mock_hgetall.return_value = {}
        result = run_calibration("2026-W15")
        self.assertEqual(result.total_predictions, 0)


class TestRunLessonsReview(unittest.TestCase):
    """Tests for run_lessons_review."""

    @patch("scripts.autocog.weekly_review.LESSONS_PATH", Path("/nonexistent/path"))
    def test_missing_lessons_file(self):
        result = run_lessons_review(datetime.now(UTC) - timedelta(days=7))
        self.assertEqual(result.total_lessons, 0)
        self.assertEqual(result.new_this_week, 0)

    def test_parses_lessons(self):
        """Should parse lessons from file content."""
        content = """```text
LESSON
- id: LESSON-20260410-test
- context: Test context
- trigger: Test trigger
- actionable_rule: Always do X before Y
- applies_to:
  - dev
- expected_outcome: X happens before Y
- evidence_ref: test
- added_utc: 2026-04-10T00:00:00Z
```

```text
LESSON
- id: LESSON-20260301-old
- context: Old lesson
- trigger: Old trigger
- actionable_rule: Always do Z
- applies_to:
  - dev
- expected_outcome: Z is done
- evidence_ref: old
- added_utc: 2026-03-01T00:00:00Z
```
"""
        # Test the regex extraction directly
        blocks = _LESSON_BLOCK_PATTERN.findall(content)
        self.assertEqual(len(blocks), 2)

        # Test the full function with patched Path
        import os
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            tmp_path = f.name

        try:
            week_start = datetime(2026, 4, 8, tzinfo=UTC)
            with patch("scripts.autocog.weekly_review.LESSONS_PATH", Path(tmp_path)):
                result = run_lessons_review(week_start)
            self.assertEqual(result.total_lessons, 2)
            self.assertEqual(result.new_this_week, 1)
            self.assertEqual(len(result.prevention_rules), 2)
            self.assertIn("Always do X before Y", result.prevention_rules)
            self.assertIn("Always do Z", result.prevention_rules)
        finally:
            os.unlink(tmp_path)


class TestPromoteLessonsToQdrant(unittest.TestCase):
    """Tests for promote_lessons_to_qdrant."""

    def test_no_new_lessons(self):
        review = LessonsReview(new_this_week=0)
        result = promote_lessons_to_qdrant(review)
        self.assertEqual(result, 0)

    @patch("scripts.autocog.weekly_review.LESSONS_PATH")
    def test_qdrant_unavailable(self, mock_path):
        mock_path.exists.return_value = False
        review = LessonsReview(new_this_week=2)
        result = promote_lessons_to_qdrant(review)
        self.assertEqual(result, 0)


class TestRunDeferredItemsReview(unittest.TestCase):
    """Tests for run_deferred_items_review."""

    @patch("scripts.autocog.weekly_review._redis_hgetall")
    def test_no_deferred_items(self, mock_hgetall):
        mock_hgetall.return_value = {}
        result = run_deferred_items_review()
        self.assertEqual(result.total_deferred, 0)

    @patch("scripts.autocog.weekly_review._redis_hgetall")
    def test_with_items(self, mock_hgetall):
        mock_hgetall.return_value = {
            "task1": json.dumps(
                {
                    "description": "Fix X",
                    "deferred_at": "2026-04-10T00:00:00Z",
                    "priority": "medium",
                }
            ),
            "task2": json.dumps(
                {
                    "description": "Fix Y",
                    "deferred_at": "2026-03-01T00:00:00Z",
                    "priority": "low",
                }
            ),
        }
        result = run_deferred_items_review()
        self.assertEqual(result.total_deferred, 2)
        self.assertEqual(result.stale_items, 1)

    @patch("scripts.autocog.weekly_review._redis_hgetall")
    def test_string_values(self, mock_hgetall):
        """Should handle non-JSON string values."""
        mock_hgetall.return_value = {"task1": "raw string value"}
        result = run_deferred_items_review()
        self.assertEqual(result.total_deferred, 1)
        self.assertEqual(result.items[0]["raw"], "raw string value")


class TestAssessRisks(unittest.TestCase):
    """Tests for assess_risks."""

    def test_no_risks(self):
        assessment = {"overall_score": 0.85}
        calibration = CalibrationResult(calibration_error=0.02, bias_type="none")
        deferred = DeferredItemsReview(total_deferred=2)
        risks = assess_risks(assessment, calibration, deferred)
        self.assertEqual(len(risks), 0)

    def test_critical_score(self):
        assessment = {"overall_score": 0.4}
        calibration = CalibrationResult()
        deferred = DeferredItemsReview()
        risks = assess_risks(assessment, calibration, deferred)
        self.assertTrue(any("CRITICAL" in r for r in risks))

    def test_high_calibration_error(self):
        assessment = {"overall_score": 0.85}
        calibration = CalibrationResult(
            calibration_error=0.25, bias_type="overconfidence"
        )
        deferred = DeferredItemsReview()
        risks = assess_risks(assessment, calibration, deferred)
        self.assertTrue(any("HIGH" in r for r in risks))

    def test_stale_deferred_items(self):
        assessment = {"overall_score": 0.85}
        calibration = CalibrationResult()
        deferred = DeferredItemsReview(stale_items=3)
        risks = assess_risks(assessment, calibration, deferred)
        self.assertTrue(any("14 days" in r for r in risks))

    def test_too_many_deferred_items(self):
        assessment = {"overall_score": 0.85}
        calibration = CalibrationResult()
        deferred = DeferredItemsReview(total_deferred=15)
        risks = assess_risks(assessment, calibration, deferred)
        self.assertTrue(any("backlog" in r.lower() for r in risks))

    def test_degraded_score(self):
        assessment = {"overall_score": 0.6}
        calibration = CalibrationResult()
        deferred = DeferredItemsReview()
        risks = assess_risks(assessment, calibration, deferred)
        self.assertTrue(any("WARNING" in r for r in risks))

    def test_no_score(self):
        """Should handle missing score gracefully."""
        assessment = {"overall_score": None}
        calibration = CalibrationResult()
        deferred = DeferredItemsReview()
        risks = assess_risks(assessment, calibration, deferred)
        self.assertEqual(len(risks), 0)

    def test_medium_calibration_error(self):
        assessment = {"overall_score": 0.85}
        calibration = CalibrationResult(
            calibration_error=0.15, bias_type="overconfidence"
        )
        deferred = DeferredItemsReview()
        risks = assess_risks(assessment, calibration, deferred)
        self.assertTrue(any("MEDIUM" in r for r in risks))


class TestBuildDiscordEmbed(unittest.TestCase):
    """Tests for build_discord_embed."""

    def test_basic_embed_structure(self):
        result = WeeklyReviewResult(
            week_key="2026-W15",
            generated_at="2026-04-12T00:00:00Z",
            overall_score=0.85,
            dimensions={"memory_health": 0.9, "infrastructure_health": 0.8},
            findings=["All systems nominal"],
            recommendations=["Continue monitoring"],
            calibration=CalibrationResult(calibration_error=0.05, bias_type="none"),
            lessons_review=LessonsReview(new_this_week=3),
            deferred_items=DeferredItemsReview(total_deferred=2),
            risks=[],
            status="ok",
        )
        embed = build_discord_embed(result)
        self.assertIn("title", embed)
        self.assertIn("fields", embed)
        self.assertIn("footer", embed)
        self.assertEqual(embed["title"], "\U0001f4ca Weekly Review: 2026-W15")
        self.assertTrue(len(embed["fields"]) > 0)

    def test_embed_with_risks(self):
        result = WeeklyReviewResult(
            week_key="2026-W15",
            generated_at="2026-04-12T00:00:00Z",
            overall_score=0.4,
            risks=["CRITICAL: Score below 0.5"],
            status="critical",
        )
        embed = build_discord_embed(result)
        field_names = [f["name"] for f in embed["fields"]]
        self.assertIn("\u26a0\ufe0f Risk Details", field_names)

    def test_embed_no_score(self):
        result = WeeklyReviewResult(
            week_key="2026-W15",
            generated_at="2026-04-12T00:00:00Z",
            overall_score=None,
            status="unknown",
        )
        embed = build_discord_embed(result)
        score_field = next(
            (f for f in embed["fields"] if f["name"] == "Overall Score"), None
        )
        self.assertIsNotNone(score_field)
        self.assertEqual(score_field["value"], "N/A")

    def test_embed_truncated_findings(self):
        """Should truncate findings to 5 items."""
        findings = [f"Finding {i}" for i in range(10)]
        result = WeeklyReviewResult(
            week_key="2026-W15",
            generated_at="2026-04-12T00:00:00Z",
            findings=findings,
        )
        embed = build_discord_embed(result)
        findings_field = next(
            (f for f in embed["fields"] if f["name"] == "Findings"), None
        )
        self.assertIsNotNone(findings_field)
        self.assertIn("5 more", findings_field["value"])


class TestRunWeeklyReview(unittest.TestCase):
    """Tests for run_weekly_review integration."""

    @patch("scripts.autocog.weekly_review.emit_discord_notification")
    @patch("scripts.autocog.weekly_review.persist_weekly_result")
    @patch("scripts.autocog.weekly_review.promote_lessons_to_qdrant")
    @patch("scripts.autocog.weekly_review.run_deferred_items_review")
    @patch("scripts.autocog.weekly_review.run_lessons_review")
    @patch("scripts.autocog.weekly_review.run_calibration")
    @patch("scripts.autocog.weekly_review.run_self_assessment")
    @patch("scripts.autocog.weekly_review._redis_get")
    def test_dry_run_skips_persistence(
        self,
        mock_redis_get,
        mock_assessment,
        mock_calibration,
        mock_lessons,
        mock_deferred,
        mock_promote,
        mock_persist,
        mock_discord,
    ):
        mock_redis_get.return_value = None
        mock_assessment.return_value = {
            "overall_score": 0.85,
            "dimensions": {},
            "findings": [],
            "recommendations": [],
            "status": "ok",
        }
        mock_calibration.return_value = CalibrationResult()
        mock_lessons.return_value = LessonsReview()
        mock_deferred.return_value = DeferredItemsReview()

        from scripts.autocog.weekly_review import run_weekly_review

        result = run_weekly_review(dry_run=True)

        mock_persist.assert_not_called()
        mock_discord.assert_not_called()
        mock_promote.assert_not_called()
        self.assertEqual(result.overall_score, 0.85)

    @patch("scripts.autocog.weekly_review.emit_discord_notification")
    @patch("scripts.autocog.weekly_review.persist_weekly_result")
    @patch("scripts.autocog.weekly_review.promote_lessons_to_qdrant")
    @patch("scripts.autocog.weekly_review.run_deferred_items_review")
    @patch("scripts.autocog.weekly_review.run_lessons_review")
    @patch("scripts.autocog.weekly_review.run_calibration")
    @patch("scripts.autocog.weekly_review.run_self_assessment")
    @patch("scripts.autocog.weekly_review._redis_get")
    def test_normal_run_persists(
        self,
        mock_redis_get,
        mock_assessment,
        mock_calibration,
        mock_lessons,
        mock_deferred,
        mock_promote,
        mock_persist,
        mock_discord,
    ):
        mock_redis_get.return_value = None
        mock_assessment.return_value = {
            "overall_score": 0.85,
            "dimensions": {},
            "findings": ["OK"],
            "recommendations": ["Keep going"],
            "status": "ok",
        }
        mock_calibration.return_value = CalibrationResult()
        mock_lessons.return_value = LessonsReview()
        mock_deferred.return_value = DeferredItemsReview()
        mock_promote.return_value = 0

        from scripts.autocog.weekly_review import run_weekly_review

        result = run_weekly_review(dry_run=False)

        mock_persist.assert_called_once()
        mock_discord.assert_called_once()
        mock_promote.assert_called_once()

    @patch("scripts.autocog.weekly_review.emit_discord_notification")
    @patch("scripts.autocog.weekly_review.persist_weekly_result")
    @patch("scripts.autocog.weekly_review.promote_lessons_to_qdrant")
    @patch("scripts.autocog.weekly_review.run_deferred_items_review")
    @patch("scripts.autocog.weekly_review.run_lessons_review")
    @patch("scripts.autocog.weekly_review.run_calibration")
    @patch("scripts.autocog.weekly_review.run_self_assessment")
    @patch("scripts.autocog.weekly_review._redis_get")
    def test_force_overrides_existing(
        self,
        mock_redis_get,
        mock_assessment,
        mock_calibration,
        mock_lessons,
        mock_deferred,
        mock_promote,
        mock_persist,
        mock_discord,
    ):
        """Force should regenerate even when cached review exists."""
        from dataclasses import asdict

        cached_result = WeeklyReviewResult(
            week_key="2026-W15",
            generated_at="2026-04-10T00:00:00Z",
            overall_score=0.5,
            status="ok",
        )
        mock_redis_get.return_value = json.dumps(asdict(cached_result))

        mock_assessment.return_value = {
            "overall_score": 0.9,
            "dimensions": {},
            "findings": ["Fresh run"],
            "recommendations": [],
            "status": "ok",
        }
        mock_calibration.return_value = CalibrationResult()
        mock_lessons.return_value = LessonsReview()
        mock_deferred.return_value = DeferredItemsReview()
        mock_promote.return_value = 0

        from scripts.autocog.weekly_review import run_weekly_review

        result = run_weekly_review(week_key="2026-W15", dry_run=True, force=True)
        # With force, it should NOT return cached - it runs full pipeline
        mock_assessment.assert_called()

    @patch("scripts.autocog.weekly_review.emit_discord_notification")
    @patch("scripts.autocog.weekly_review.persist_weekly_result")
    @patch("scripts.autocog.weekly_review.promote_lessons_to_qdrant")
    @patch("scripts.autocog.weekly_review.run_deferred_items_review")
    @patch("scripts.autocog.weekly_review.run_lessons_review")
    @patch("scripts.autocog.weekly_review.run_calibration")
    @patch("scripts.autocog.weekly_review.run_self_assessment")
    @patch("scripts.autocog.weekly_review._redis_get")
    def test_cached_returned_without_force(
        self,
        mock_redis_get,
        mock_assessment,
        mock_calibration,
        mock_lessons,
        mock_deferred,
        mock_promote,
        mock_persist,
        mock_discord,
    ):
        """Without force and without dry_run, cached result should be returned."""
        from dataclasses import asdict

        cached_result = WeeklyReviewResult(
            week_key="2026-W15",
            generated_at="2026-04-10T00:00:00Z",
            overall_score=0.5,
            status="ok",
        )
        mock_redis_get.return_value = json.dumps(asdict(cached_result))

        from scripts.autocog.weekly_review import run_weekly_review

        # Note: cache check only runs when dry_run=False and force=False
        result = run_weekly_review(week_key="2026-W15", dry_run=False, force=False)
        # Should return cached result (assessment should NOT be called)
        self.assertEqual(result.overall_score, 0.5)
        mock_assessment.assert_not_called()

    @patch("scripts.autocog.weekly_review.emit_discord_notification")
    @patch("scripts.autocog.weekly_review.persist_weekly_result")
    @patch("scripts.autocog.weekly_review.promote_lessons_to_qdrant")
    @patch("scripts.autocog.weekly_review.run_deferred_items_review")
    @patch("scripts.autocog.weekly_review.run_lessons_review")
    @patch("scripts.autocog.weekly_review.run_calibration")
    @patch("scripts.autocog.weekly_review.run_self_assessment")
    @patch("scripts.autocog.weekly_review._redis_get")
    def test_critical_status_from_risks(
        self,
        mock_redis_get,
        mock_assessment,
        mock_calibration,
        mock_lessons,
        mock_deferred,
        mock_promote,
        mock_persist,
        mock_discord,
    ):
        """Critical risks should set status to critical."""
        mock_redis_get.return_value = None
        mock_assessment.return_value = {
            "overall_score": 0.3,  # Critical
            "dimensions": {},
            "findings": [],
            "recommendations": [],
            "status": "failed",
        }
        mock_calibration.return_value = CalibrationResult()
        mock_lessons.return_value = LessonsReview()
        mock_deferred.return_value = DeferredItemsReview()
        mock_promote.return_value = 0

        from scripts.autocog.weekly_review import run_weekly_review

        result = run_weekly_review(dry_run=True)
        self.assertEqual(result.status, "critical")


class TestDataclasses(unittest.TestCase):
    """Tests for dataclass defaults."""

    def test_calibration_result_defaults(self):
        result = CalibrationResult()
        self.assertEqual(result.total_predictions, 0)
        self.assertEqual(result.calibration_error, 0.0)
        self.assertEqual(result.bias_type, "none")
        self.assertEqual(result.pairs, [])

    def test_lessons_review_defaults(self):
        result = LessonsReview()
        self.assertEqual(result.total_lessons, 0)
        self.assertEqual(result.new_this_week, 0)
        self.assertEqual(result.prevention_rules, [])

    def test_deferred_items_review_defaults(self):
        result = DeferredItemsReview()
        self.assertEqual(result.total_deferred, 0)
        self.assertEqual(result.items, [])
        self.assertEqual(result.stale_items, 0)

    def test_weekly_review_result_defaults(self):
        result = WeeklyReviewResult()
        self.assertEqual(result.week_key, "")
        self.assertEqual(result.status, "ok")
        self.assertIsNone(result.overall_score)
        self.assertEqual(result.risks, [])
        self.assertIsInstance(result.calibration, CalibrationResult)
        self.assertIsInstance(result.lessons_review, LessonsReview)
        self.assertIsInstance(result.deferred_items, DeferredItemsReview)


class TestCLIArgs(unittest.TestCase):
    """Tests for CLI argument parsing."""

    def test_default_args(self):
        # Just verify main() returns 0 with --help or no args
        # (actual parsing tested by running the script)
        pass

    def test_invalid_week_key(self):
        """Should return error code 1 for invalid week key."""
        import subprocess

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.autocog.weekly_review",
                "--week",
                "invalid",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 1)

    def test_dry_run_flag(self):
        """Should accept --dry-run flag."""
        import subprocess

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.autocog.weekly_review",
                "--dry-run",
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        # Should succeed (exit 0) even if Redis is unavailable
        self.assertEqual(result.returncode, 0)
        # Should output JSON
        try:
            data = json.loads(result.stdout)
            self.assertIn("week_key", data)
        except json.JSONDecodeError:
            # If not JSON, should at least have printed something
            self.assertTrue(len(result.stdout) > 0)

    def test_force_flag(self):
        """Should accept --force flag."""
        import subprocess

        result = subprocess.run(
            [sys.executable, "-m", "scripts.autocog.weekly_review", "--force"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
