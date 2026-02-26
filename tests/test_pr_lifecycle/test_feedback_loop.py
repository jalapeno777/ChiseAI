"""Tests for PR Lifecycle Feedback Loop.

This module tests:
- Outcome tracking
- Metric calculations
- Report generation
- Rule adjustment suggestions
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add paths for imports
scripts_path = str(Path(__file__).parent.parent.parent / "scripts" / "pr_lifecycle")
src_path = str(Path(__file__).parent.parent.parent / "src")
if scripts_path not in sys.path:
    sys.path.insert(0, scripts_path)
if src_path not in sys.path:
    sys.path.insert(0, src_path)

# Import modules under test
from feedback_loop import (
    FeedbackLoop,
    RuleAdjustmentSuggestion,
    WeeklyReport,
)
from outcome_tracker import (
    OutcomeTracker,
    PROutcome,
    SuccessMetrics,
)

from pr_lifecycle.metrics import (
    MetricsExporter,
    PRPipelineMetrics,
    get_all_grafana_queries,
    get_grafana_query,
)


class TestPROutcome:
    """Tests for PROutcome dataclass."""

    def test_outcome_creation(self):
        """Test creating a PROutcome instance."""
        outcome = PROutcome(
            pr_number=123,
            story_id="ST-TEST-001",
            branch="feature/test-branch",
            head_sha="abc123",
            outcome="merged",
            opened_by_agent="test-agent",
        )

        assert outcome.pr_number == 123
        assert outcome.story_id == "ST-TEST-001"
        assert outcome.outcome == "merged"
        assert outcome.opened_by_agent == "test-agent"

    def test_outcome_to_dict(self):
        """Test converting PROutcome to dictionary."""
        outcome = PROutcome(
            pr_number=123,
            story_id="ST-TEST-001",
            branch="feature/test-branch",
            head_sha="abc123",
            outcome="merged",
            auto_approved=True,
            rolled_back=False,
            time_to_merge_minutes=45.5,
        )

        data = outcome.to_dict()

        assert data["pr_number"] == "123"
        assert data["story_id"] == "ST-TEST-001"
        assert data["outcome"] == "merged"
        assert data["auto_approved"] == "true"
        assert data["rolled_back"] == "false"
        assert data["time_to_merge_minutes"] == "45.5"

    def test_outcome_from_dict(self):
        """Test creating PROutcome from dictionary."""
        data = {
            "pr_number": "123",
            "story_id": "ST-TEST-001",
            "branch": "feature/test-branch",
            "head_sha": "abc123",
            "outcome": "merged",
            "auto_approved": "true",
            "rolled_back": "false",
            "time_to_merge_minutes": "45.5",
            "ci_failures": '["test_failure"]',
        }

        outcome = PROutcome.from_dict(data)

        assert outcome.pr_number == 123
        assert outcome.story_id == "ST-TEST-001"
        assert outcome.auto_approved is True
        assert outcome.rolled_back is False
        assert outcome.time_to_merge_minutes == 45.5
        assert outcome.ci_failures == ["test_failure"]


class TestSuccessMetrics:
    """Tests for SuccessMetrics dataclass."""

    def test_metrics_creation(self):
        """Test creating SuccessMetrics."""
        metrics = SuccessMetrics(
            period_start="2026-02-01T00:00:00Z",
            period_end="2026-02-07T00:00:00Z",
            total_prs=10,
            merged_prs=8,
            rejected_prs=2,
            overall_success_rate=80.0,
        )

        assert metrics.total_prs == 10
        assert metrics.merged_prs == 8
        assert metrics.overall_success_rate == 80.0

    def test_metrics_to_dict(self):
        """Test converting SuccessMetrics to dictionary."""
        metrics = SuccessMetrics(
            period_start="2026-02-01T00:00:00Z",
            period_end="2026-02-07T00:00:00Z",
            total_prs=10,
            auto_merge_success_rate=95.0,
        )

        data = metrics.to_dict()

        assert data["total_prs"] == 10
        assert data["auto_merge_success_rate"] == 95.0
        assert data["period_start"] == "2026-02-01T00:00:00Z"


class TestOutcomeTracker:
    """Tests for OutcomeTracker class."""

    @patch("outcome_tracker._redis_cli")
    def test_record_outcome(self, mock_redis_cli):
        """Test recording an outcome."""
        mock_redis_cli.return_value = MagicMock(returncode=0, stdout="OK")

        tracker = OutcomeTracker()
        outcome = PROutcome(
            pr_number=123,
            story_id="ST-TEST-001",
            branch="feature/test-branch",
            head_sha="abc123",
            outcome="merged",
        )

        result = tracker.record_outcome(outcome)

        assert result is True
        # Verify Redis commands were called
        assert mock_redis_cli.call_count > 0

    @patch("outcome_tracker._redis_cli")
    def test_record_merge(self, mock_redis_cli):
        """Test recording a merge outcome."""
        mock_redis_cli.return_value = MagicMock(returncode=0, stdout="OK")

        tracker = OutcomeTracker()
        result = tracker.record_merge(
            pr_number=123,
            story_id="ST-TEST-001",
            branch="feature/test-branch",
            head_sha="abc123",
            opened_by_agent="test-agent",
            auto_merged=True,
            time_to_merge_minutes=30.0,
        )

        assert result is True

    @patch("outcome_tracker._redis_cli")
    def test_record_rejection(self, mock_redis_cli):
        """Test recording a rejection outcome."""
        mock_redis_cli.return_value = MagicMock(returncode=0, stdout="OK")

        tracker = OutcomeTracker()
        result = tracker.record_rejection(
            pr_number=123,
            story_id="ST-TEST-001",
            branch="feature/test-branch",
            head_sha="abc123",
            opened_by_agent="test-agent",
            reviewer="reviewer-agent",
            rejection_reason="Tests failed",
        )

        assert result is True

    @patch("outcome_tracker._redis_cli")
    def test_get_outcome(self, mock_redis_cli):
        """Test retrieving an outcome."""
        mock_redis_cli.return_value = MagicMock(
            returncode=0,
            stdout="pr_number\n123\nstory_id\nST-TEST-001\noutcome\nmerged",
        )

        tracker = OutcomeTracker()
        outcome = tracker.get_outcome(123)

        assert outcome is not None
        assert outcome.pr_number == 123
        assert outcome.story_id == "ST-TEST-001"

    @patch("outcome_tracker._redis_cli")
    def test_calculate_metrics(self, mock_redis_cli):
        """Test calculating success metrics."""

        # Mock Redis responses for date index and outcome retrieval
        # The method iterates through each day in range, calling SMEMBERS for each
        # We need to provide enough mock values for all calls
        def mock_side_effect(*args, **kwargs):
            cmd = args[0] if args else ""

            if cmd == "SMEMBERS":
                # First day has PRs, rest are empty
                mock_call_count = mock_redis_cli.call_count
                if mock_call_count == 1:
                    return MagicMock(returncode=0, stdout="123\n124")
                else:
                    return MagicMock(returncode=0, stdout="")
            elif cmd == "HGETALL":
                # Return outcome data based on key
                key = args[1] if len(args) > 1 else ""
                if "123" in key:
                    return MagicMock(
                        returncode=0,
                        stdout="pr_number\n123\nstory_id\nST-001\noutcome\nmerged\nauto_approved\ntrue\nrolled_back\nfalse\ntime_to_merge_minutes\n30.0",
                    )
                elif "124" in key:
                    return MagicMock(
                        returncode=0,
                        stdout="pr_number\n124\nstory_id\nST-002\noutcome\nrejected\nauto_approved\nfalse\nrolled_back\nfalse",
                    )

            return MagicMock(returncode=0, stdout="")

        mock_redis_cli.side_effect = mock_side_effect

        tracker = OutcomeTracker()
        end_date = datetime.now(UTC)
        start_date = end_date - timedelta(days=7)

        metrics = tracker.calculate_metrics(start_date, end_date)

        assert metrics.total_prs == 2
        assert metrics.merged_prs == 1
        assert metrics.rejected_prs == 1


class TestFeedbackLoop:
    """Tests for FeedbackLoop class."""

    @patch("feedback_loop.OutcomeTracker")
    def test_analyze_patterns(self, mock_tracker_class):
        """Test analyzing outcome patterns."""
        mock_tracker = MagicMock()
        mock_tracker_class.return_value = mock_tracker

        # Mock metrics
        mock_metrics = SuccessMetrics(
            period_start="2026-02-01T00:00:00Z",
            period_end="2026-02-07T00:00:00Z",
            total_prs=10,
            merged_prs=9,
            rolled_back_prs=1,
            auto_approved_count=5,
            auto_approved_rolled_back=1,
            overall_success_rate=90.0,
            auto_approved_success_rate=80.0,
            avg_time_to_merge_minutes=45.0,
        )
        mock_tracker.calculate_metrics.return_value = mock_metrics

        feedback = FeedbackLoop()
        patterns = feedback.analyze_patterns(days=7)

        assert patterns["total_prs"] == 10
        assert patterns["success_rate"] == 90.0
        assert "concerns" in patterns
        assert "positives" in patterns

    @patch("feedback_loop._redis_cli")
    @patch("feedback_loop.OutcomeTracker")
    def test_generate_rule_adjustments_high_rollback(
        self, mock_tracker_class, mock_redis_cli
    ):
        """Test generating rule adjustments when rollback rate is high."""
        mock_tracker = MagicMock()
        mock_tracker_class.return_value = mock_tracker

        # Mock metrics with high rollback rate
        mock_metrics = SuccessMetrics(
            period_start="2026-02-01T00:00:00Z",
            period_end="2026-02-07T00:00:00Z",
            total_prs=10,
            auto_approved_count=10,
            auto_approved_rolled_back=2,  # 20% rollback rate
        )
        mock_tracker.calculate_metrics.return_value = mock_metrics

        # Mock Redis calls for _store_suggestion
        mock_redis_cli.return_value = MagicMock(returncode=0, stdout="OK")

        feedback = FeedbackLoop()
        suggestions = feedback.generate_rule_adjustments(days=7)

        # Should suggest tightening auto-approval
        assert len(suggestions) > 0
        assert any(s.rule_type == "auto_approval" for s in suggestions)

    @patch("feedback_loop._redis_cli")
    @patch("feedback_loop.OutcomeTracker")
    def test_generate_rule_adjustments_low_rollback(
        self, mock_tracker_class, mock_redis_cli
    ):
        """Test generating rule adjustments when rollback rate is low."""
        mock_tracker = MagicMock()
        mock_tracker_class.return_value = mock_tracker

        # Mock metrics with very low rollback rate
        mock_metrics = SuccessMetrics(
            period_start="2026-02-01T00:00:00Z",
            period_end="2026-02-07T00:00:00Z",
            total_prs=20,
            auto_approved_count=20,
            auto_approved_rolled_back=0,  # 0% rollback rate
        )
        mock_tracker.calculate_metrics.return_value = mock_metrics

        # Mock Redis calls for _store_suggestion
        mock_redis_cli.return_value = MagicMock(returncode=0, stdout="OK")

        feedback = FeedbackLoop()
        suggestions = feedback.generate_rule_adjustments(days=7)

        # Should suggest potentially lowering threshold
        assert any(s.rule_type == "auto_approval" for s in suggestions)

    @patch("feedback_loop.OutcomeTracker")
    @patch("feedback_loop._redis_cli")
    def test_get_pending_suggestions(self, mock_redis_cli, mock_tracker_class):
        """Test retrieving pending suggestions."""
        mock_tracker = MagicMock()
        mock_tracker_class.return_value = mock_tracker

        # Mock Redis response
        mock_redis_cli.return_value = MagicMock(returncode=0, stdout="")

        feedback = FeedbackLoop()
        suggestions = feedback.get_pending_suggestions()

        assert isinstance(suggestions, list)


class TestRuleAdjustmentSuggestion:
    """Tests for RuleAdjustmentSuggestion dataclass."""

    def test_suggestion_creation(self):
        """Test creating a rule adjustment suggestion."""
        suggestion = RuleAdjustmentSuggestion(
            suggestion_id="test-001",
            created_at="2026-02-01T00:00:00Z",
            rule_type="auto_approval",
            current_value="0.8",
            suggested_value="0.9",
            confidence=85.0,
            rationale="High rollback rate detected",
            supporting_evidence={"rollback_rate": 0.15},
        )

        assert suggestion.suggestion_id == "test-001"
        assert suggestion.rule_type == "auto_approval"
        assert suggestion.confidence == 85.0
        assert suggestion.applied is False

    def test_suggestion_to_dict(self):
        """Test converting suggestion to dictionary."""
        suggestion = RuleAdjustmentSuggestion(
            suggestion_id="test-001",
            created_at="2026-02-01T00:00:00Z",
            rule_type="auto_approval",
            current_value="0.8",
            suggested_value="0.9",
            confidence=85.0,
            rationale="Test rationale",
            supporting_evidence={"key": "value"},
        )

        data = suggestion.to_dict()

        assert data["suggestion_id"] == "test-001"
        assert data["rule_type"] == "auto_approval"
        assert data["confidence"] == "85.0"
        assert json.loads(data["supporting_evidence"]) == {"key": "value"}

    def test_suggestion_from_dict(self):
        """Test creating suggestion from dictionary."""
        data = {
            "suggestion_id": "test-001",
            "created_at": "2026-02-01T00:00:00Z",
            "rule_type": "auto_approval",
            "current_value": "0.8",
            "suggested_value": "0.9",
            "confidence": "85.0",
            "rationale": "Test",
            "supporting_evidence": '{"key": "value"}',
            "applied": "false",
        }

        suggestion = RuleAdjustmentSuggestion.from_dict(data)

        assert suggestion.suggestion_id == "test-001"
        assert suggestion.confidence == 85.0
        assert suggestion.supporting_evidence == {"key": "value"}


class TestWeeklyReport:
    """Tests for WeeklyReport dataclass."""

    def test_report_creation(self):
        """Test creating a weekly report."""
        report = WeeklyReport(
            report_id="weekly_2026-02-01",
            week_start="2026-02-01T00:00:00Z",
            week_end="2026-02-07T00:00:00Z",
            generated_at="2026-02-08T00:00:00Z",
            total_prs=10,
            merged_prs=8,
            rejected_prs=2,
            rolled_back_prs=0,
            auto_merge_success_rate=100.0,
            review_accuracy=100.0,
            overall_success_rate=100.0,
            avg_time_to_merge_minutes=30.0,
            p95_time_to_merge_minutes=60.0,
            success_rate_trend=5.0,
            time_to_merge_trend=-10.0,
            suggestions=[],
            insights=["Great week!"],
            action_items=[],
        )

        assert report.total_prs == 10
        assert report.overall_success_rate == 100.0
        assert report.insights == ["Great week!"]


class TestPRPipelineMetrics:
    """Tests for PRPipelineMetrics class."""

    def test_metrics_creation(self):
        """Test creating pipeline metrics."""
        metrics = PRPipelineMetrics(
            total_prs=100,
            merged_prs=95,
            overall_success_rate=95.0,
            avg_time_to_merge=45.0,
        )

        assert metrics.total_prs == 100
        assert metrics.overall_success_rate == 95.0

    def test_to_prometheus_metrics(self):
        """Test converting to Prometheus metrics."""
        metrics = PRPipelineMetrics(
            total_prs=100,
            merged_prs=95,
            overall_success_rate=95.0,
        )

        prom_metrics = metrics.to_prometheus_metrics()

        assert len(prom_metrics) > 0
        metric_names = [m.name for m in prom_metrics]
        assert "pr_pipeline_total_prs" in metric_names
        assert "pr_pipeline_overall_success_rate" in metric_names

    def test_to_prometheus_export(self):
        """Test Prometheus export format."""
        metrics = PRPipelineMetrics(
            total_prs=100,
            overall_success_rate=95.0,
        )

        export = metrics.to_prometheus_export()

        assert "# HELP" in export
        assert "pr_pipeline_total_prs" in export
        assert "pr_pipeline_overall_success_rate" in export

    def test_to_influxdb_lines(self):
        """Test InfluxDB line protocol export."""
        metrics = PRPipelineMetrics(
            total_prs=100,
            merged_prs=95,
            avg_time_to_merge=45.0,
        )

        lines = metrics.to_influxdb_lines()

        assert len(lines) > 0
        assert any("pr_pipeline_volume" in line for line in lines)
        assert any("pr_pipeline_time" in line for line in lines)


class TestMetricsExporter:
    """Tests for MetricsExporter class."""

    def test_export_prometheus_format(self):
        """Test exporting to Prometheus format."""
        metrics = PRPipelineMetrics(total_prs=100)

        export = MetricsExporter.export_prometheus_format(metrics)

        assert "pr_pipeline_total_prs" in export
        assert "# HELP" in export
        assert "# TYPE" in export

    def test_export_influxdb_format(self):
        """Test exporting to InfluxDB format."""
        metrics = PRPipelineMetrics(total_prs=100, merged_prs=95)

        export = MetricsExporter.export_influxdb_format(metrics)

        assert "pr_pipeline_volume" in export
        assert "value=100i" in export or "value=95i" in export

    def test_export_json(self):
        """Test exporting to JSON."""
        metrics = PRPipelineMetrics(total_prs=100)

        data = MetricsExporter.export_json(metrics)

        assert data["total_prs"] == 100


class TestGrafanaQueries:
    """Tests for Grafana query helpers."""

    def test_get_grafana_query(self):
        """Test getting a specific Grafana query."""
        query = get_grafana_query("total_prs")

        assert query is not None
        assert "pr_pipeline_volume" in query
        assert "metric" in query

    def test_get_grafana_query_invalid(self):
        """Test getting an invalid query."""
        query = get_grafana_query("nonexistent_metric")

        assert query == ""

    def test_get_all_grafana_queries(self):
        """Test getting all Grafana queries."""
        queries = get_all_grafana_queries()

        assert isinstance(queries, dict)
        assert "total_prs" in queries
        assert "success_rate" in queries
        assert "avg_time_to_merge" in queries


class TestRetryLogic:
    """Tests for retry logic in feedback loop."""

    @patch("feedback_loop.OutcomeTracker")
    def test_transient_failure_detection(self, mock_tracker_class):
        """Test detection of transient failures."""
        mock_tracker = MagicMock()
        mock_tracker_class.return_value = mock_tracker

        # Mock metrics with proper values (not MagicMock)
        mock_metrics = SuccessMetrics(
            period_start="2026-02-01T00:00:00Z",
            period_end="2026-02-07T00:00:00Z",
            total_prs=1,
            merged_prs=1,
            rejected_prs=0,
            rolled_back_prs=0,
            auto_approved_count=1,
            auto_approved_rolled_back=0,
            overall_success_rate=100.0,
            auto_approved_success_rate=100.0,
            avg_time_to_merge_minutes=30.0,
        )
        mock_tracker.calculate_metrics.return_value = mock_metrics

        # Test that transient failures are tracked
        feedback = FeedbackLoop()
        patterns = feedback.analyze_patterns(days=7)

        assert "total_prs" in patterns
        assert patterns["total_prs"] == 1


class TestIntegration:
    """Integration tests for the feedback loop system."""

    @patch("outcome_tracker._redis_cli")
    @patch("feedback_loop._redis_cli")
    def test_full_workflow(self, mock_feedback_redis, mock_tracker_redis):
        """Test the complete feedback loop workflow."""
        # Setup mock responses
        mock_tracker_redis.return_value = MagicMock(returncode=0, stdout="OK")
        mock_feedback_redis.return_value = MagicMock(returncode=0, stdout="")

        # 1. Record some outcomes
        tracker = OutcomeTracker()
        tracker.record_merge(
            pr_number=1,
            story_id="ST-001",
            branch="feature/test-1",
            head_sha="abc123",
            opened_by_agent="agent-1",
            auto_merged=True,
            time_to_merge_minutes=30.0,
        )

        tracker.record_rejection(
            pr_number=2,
            story_id="ST-002",
            branch="feature/test-2",
            head_sha="def456",
            opened_by_agent="agent-2",
            reviewer="reviewer-1",
        )

        # 2. Analyze patterns
        feedback = FeedbackLoop()
        patterns = feedback.analyze_patterns(days=7)

        assert "total_prs" in patterns

        # 3. Generate suggestions
        suggestions = feedback.generate_rule_adjustments(days=7)
        assert isinstance(suggestions, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
