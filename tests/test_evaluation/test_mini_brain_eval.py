"""Tests for Mini BrainEval module.

# SAFETY: No risk cap logic modified
# SAFETY: No promotion gate logic modified
# SAFETY: No live trading flow modified
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, mock_open, patch

import pytest

from evaluation.mini_brain_eval import MiniBrainEval
from evaluation.schemas.mini_eval import (
    Issue,
    IssueCategory,
    IssueSeverity,
    MiniEvalResult,
    Mitigation,
    MitigationResult,
)


class TestIssue:
    """Tests for Issue dataclass."""

    def test_creation(self) -> None:
        """Test basic creation."""
        issue = Issue(
            issue_id="test-id",
            category="file_access",
            severity="P1",
            description="Test issue",
            source="test",
            timestamp="2024-01-01T00:00:00Z",
        )
        assert issue.issue_id == "test-id"
        assert issue.category == "file_access"
        assert issue.severity == "P1"
        assert issue.description == "Test issue"

    def test_invalid_category(self) -> None:
        """Test that invalid category is rejected."""
        with pytest.raises(ValueError, match="Invalid category"):
            Issue(
                issue_id="test-id",
                category="invalid_category",
                severity="P1",
                description="Test",
                source="test",
                timestamp="2024-01-01T00:00:00Z",
            )

    def test_invalid_severity(self) -> None:
        """Test that invalid severity is rejected."""
        with pytest.raises(ValueError, match="Invalid severity"):
            Issue(
                issue_id="test-id",
                category="file_access",
                severity="P5",
                description="Test",
                source="test",
                timestamp="2024-01-01T00:00:00Z",
            )

    def test_to_dict(self) -> None:
        """Test serialization."""
        issue = Issue(
            issue_id="test-id",
            category="db_connectivity",
            severity="P0",
            description="Connection failed",
            source="test_source",
            timestamp="2024-01-01T00:00:00Z",
        )
        data = issue.to_dict()
        assert data["issue_id"] == "test-id"
        assert data["category"] == "db_connectivity"
        assert data["severity"] == "P0"
        assert data["source"] == "test_source"

    def test_from_dict(self) -> None:
        """Test deserialization."""
        data = {
            "issue_id": "test-id",
            "category": "tool_error",
            "severity": "P2",
            "description": "Tool failed",
            "source": "test",
            "timestamp": "2024-01-01T00:00:00Z",
        }
        issue = Issue.from_dict(data)
        assert issue.issue_id == "test-id"
        assert issue.category == "tool_error"
        assert issue.severity == "P2"

    def test_create_factory(self) -> None:
        """Test factory method with auto-generated fields."""
        issue = Issue.create(
            category=IssueCategory.ENV_SLOWDOWN,
            severity=IssueSeverity.P1,
            description="High latency detected",
            source="monitoring",
        )
        assert issue.issue_id is not None
        assert len(issue.issue_id) > 0  # UUID generated
        assert issue.category == "env_slowdown"
        assert issue.severity == "P1"
        assert issue.timestamp is not None


class TestMitigation:
    """Tests for Mitigation dataclass."""

    def test_creation(self) -> None:
        """Test basic creation."""
        mitigation = Mitigation(
            mitigation_id="mit-id",
            issue_id="issue-id",
            action="Restarted service",
            result="success",
            timestamp="2024-01-01T00:00:00Z",
        )
        assert mitigation.mitigation_id == "mit-id"
        assert mitigation.issue_id == "issue-id"
        assert mitigation.action == "Restarted service"
        assert mitigation.result == "success"

    def test_invalid_result(self) -> None:
        """Test that invalid result is rejected."""
        with pytest.raises(ValueError, match="Invalid result"):
            Mitigation(
                mitigation_id="mit-id",
                issue_id="issue-id",
                action="Test",
                result="unknown",
                timestamp="2024-01-01T00:00:00Z",
            )

    def test_to_dict(self) -> None:
        """Test serialization."""
        mitigation = Mitigation(
            mitigation_id="mit-id",
            issue_id="issue-id",
            action="Checked permissions",
            result="partial",
            timestamp="2024-01-01T00:00:00Z",
        )
        data = mitigation.to_dict()
        assert data["mitigation_id"] == "mit-id"
        assert data["result"] == "partial"

    def test_from_dict(self) -> None:
        """Test deserialization."""
        data = {
            "mitigation_id": "mit-id",
            "issue_id": "issue-id",
            "action": "Retry operation",
            "result": "failure",
            "timestamp": "2024-01-01T00:00:00Z",
        }
        mitigation = Mitigation.from_dict(data)
        assert mitigation.mitigation_id == "mit-id"
        assert mitigation.result == "failure"

    def test_create_factory(self) -> None:
        """Test factory method with auto-generated fields."""
        mitigation = Mitigation.create(
            issue_id="test-issue-id",
            action="Restarted service",
            result=MitigationResult.SUCCESS,
        )
        assert mitigation.mitigation_id is not None
        assert mitigation.issue_id == "test-issue-id"
        assert mitigation.result == "success"
        assert mitigation.timestamp is not None


class TestMiniEvalResult:
    """Tests for MiniEvalResult dataclass."""

    def test_creation(self) -> None:
        """Test basic creation."""
        result = MiniEvalResult(
            eval_id="eval-123",
            timestamp="2024-01-01T00:00:00Z",
            cadence="6h",
            kpis={"accuracy": 0.95},
        )
        assert result.eval_id == "eval-123"
        assert result.cadence == "6h"
        assert result.kpis["accuracy"] == 0.95

    def test_invalid_cadence(self) -> None:
        """Test that invalid cadence is rejected."""
        with pytest.raises(ValueError, match="Invalid cadence"):
            MiniEvalResult(
                eval_id="eval-123",
                timestamp="2024-01-01T00:00:00Z",
                cadence="invalid",
            )

    def test_valid_cadences(self) -> None:
        """Test that valid cadences are accepted."""
        for cadence in ["6h", "daily", "weekly"]:
            result = MiniEvalResult(
                eval_id="eval-123",
                timestamp="2024-01-01T00:00:00Z",
                cadence=cadence,
            )
            assert result.cadence == cadence

    def test_to_dict(self) -> None:
        """Test serialization."""
        issue = Issue.create(
            category=IssueCategory.FILE_ACCESS,
            severity=IssueSeverity.P2,
            description="File not found",
            source="test",
        )
        mitigation = Mitigation.create(
            issue_id=issue.issue_id,
            action="Checked path",
            result=MitigationResult.PARTIAL,
        )
        result = MiniEvalResult(
            eval_id="eval-123",
            timestamp="2024-01-01T00:00:00Z",
            cadence="daily",
            kpis={"accuracy": 0.95},
            proxies={"cpu": 50.0},
            data_freshness={"redis": "fresh"},
            issues=[issue],
            mitigations=[mitigation],
        )
        data = result.to_dict()
        assert data["eval_id"] == "eval-123"
        assert data["cadence"] == "daily"
        assert data["kpis"]["accuracy"] == 0.95
        assert len(data["issues"]) == 1
        assert len(data["mitigations"]) == 1

    def test_to_json(self) -> None:
        """Test JSON serialization."""
        result = MiniEvalResult.create(cadence="6h", kpis={"test": 1.0})
        json_str = result.to_json()
        assert "eval_id" in json_str
        assert "cadence" in json_str
        # Should be valid JSON
        parsed = json.loads(json_str)
        assert parsed["cadence"] == "6h"

    def test_from_dict(self) -> None:
        """Test deserialization."""
        data = {
            "eval_id": "eval-123",
            "timestamp": "2024-01-01T00:00:00Z",
            "cadence": "weekly",
            "kpis": {"f1": 0.9},
            "proxies": {},
            "data_freshness": {},
            "issues": [],
            "mitigations": [],
        }
        result = MiniEvalResult.from_dict(data)
        assert result.eval_id == "eval-123"
        assert result.cadence == "weekly"
        assert result.kpis["f1"] == 0.9

    def test_from_json(self) -> None:
        """Test JSON deserialization."""
        json_str = json.dumps(
            {
                "eval_id": "eval-123",
                "timestamp": "2024-01-01T00:00:00Z",
                "cadence": "6h",
                "kpis": {},
                "proxies": {},
                "data_freshness": {},
                "issues": [],
                "mitigations": [],
            }
        )
        result = MiniEvalResult.from_json(json_str)
        assert result.eval_id == "eval-123"
        assert result.cadence == "6h"

    def test_create_factory(self) -> None:
        """Test factory method with auto-generated fields."""
        result = MiniEvalResult.create(
            cadence="daily",
            kpis={"accuracy": 0.95},
            proxies={"cpu": 45.0},
        )
        assert result.eval_id is not None
        assert result.timestamp is not None
        assert result.cadence == "daily"
        assert result.kpis["accuracy"] == 0.95
        assert result.proxies["cpu"] == 45.0

    def test_add_issue(self) -> None:
        """Test adding issues."""
        result = MiniEvalResult.create(cadence="6h")
        issue = Issue.create(
            category=IssueCategory.DB_CONNECTIVITY,
            severity=IssueSeverity.P1,
            description="DB timeout",
            source="test",
        )
        result.add_issue(issue)
        assert len(result.issues) == 1
        assert result.issues[0].category == "db_connectivity"

    def test_add_mitigation(self) -> None:
        """Test adding mitigations."""
        result = MiniEvalResult.create(cadence="6h")
        mitigation = Mitigation.create(
            issue_id="issue-123",
            action="Retry",
            result=MitigationResult.SUCCESS,
        )
        result.add_mitigation(mitigation)
        assert len(result.mitigations) == 1
        assert result.mitigations[0].action == "Retry"

    def test_has_critical_issues(self) -> None:
        """Test checking for critical issues."""
        result = MiniEvalResult.create(cadence="6h")
        assert not result.has_critical_issues()

        # Add non-critical issue
        result.add_issue(
            Issue.create(
                category=IssueCategory.OTHER,
                severity=IssueSeverity.P2,
                description="Minor issue",
                source="test",
            )
        )
        assert not result.has_critical_issues()

        # Add critical issue
        result.add_issue(
            Issue.create(
                category=IssueCategory.OTHER,
                severity=IssueSeverity.P0,
                description="Critical issue",
                source="test",
            )
        )
        assert result.has_critical_issues()

    def test_get_issues_by_severity(self) -> None:
        """Test filtering issues by severity."""
        result = MiniEvalResult.create(cadence="6h")
        result.add_issue(
            Issue.create(
                category=IssueCategory.OTHER,
                severity=IssueSeverity.P1,
                description="High priority",
                source="test",
            )
        )
        result.add_issue(
            Issue.create(
                category=IssueCategory.OTHER,
                severity=IssueSeverity.P2,
                description="Medium priority",
                source="test",
            )
        )

        p1_issues = result.get_issues_by_severity(IssueSeverity.P1)
        assert len(p1_issues) == 1
        assert p1_issues[0].description == "High priority"

    def test_get_issues_by_category(self) -> None:
        """Test filtering issues by category."""
        result = MiniEvalResult.create(cadence="6h")
        result.add_issue(
            Issue.create(
                category=IssueCategory.FILE_ACCESS,
                severity=IssueSeverity.P1,
                description="File issue",
                source="test",
            )
        )
        result.add_issue(
            Issue.create(
                category=IssueCategory.DB_CONNECTIVITY,
                severity=IssueSeverity.P1,
                description="DB issue",
                source="test",
            )
        )

        file_issues = result.get_issues_by_category(IssueCategory.FILE_ACCESS)
        assert len(file_issues) == 1
        assert file_issues[0].description == "File issue"

    def test_get_mitigations_for_issue(self) -> None:
        """Test getting mitigations for a specific issue."""
        result = MiniEvalResult.create(cadence="6h")
        issue = Issue.create(
            category=IssueCategory.OTHER,
            severity=IssueSeverity.P1,
            description="Test issue",
            source="test",
        )
        result.add_issue(issue)
        result.add_mitigation(
            Mitigation.create(
                issue_id=issue.issue_id,
                action="Fixed",
                result=MitigationResult.SUCCESS,
            )
        )
        result.add_mitigation(
            Mitigation.create(
                issue_id="other-issue",
                action="Other fix",
                result=MitigationResult.SUCCESS,
            )
        )

        mitigations = result.get_mitigations_for_issue(issue.issue_id)
        assert len(mitigations) == 1
        assert mitigations[0].action == "Fixed"


class TestMiniBrainEval:
    """Tests for MiniBrainEval class."""

    def test_creation(self) -> None:
        """Test basic creation."""
        evaluator = MiniBrainEval()
        assert evaluator.redis_client is None
        assert evaluator.influxdb_client is None
        assert evaluator.brain_evaluator is None
        assert evaluator.qdrant_client is None

    def test_creation_with_clients(self) -> None:
        """Test creation with mock clients."""
        mock_redis = MagicMock()
        mock_influx = MagicMock()
        mock_brain = MagicMock()
        mock_qdrant = MagicMock()

        evaluator = MiniBrainEval(
            redis_client=mock_redis,
            influxdb_client=mock_influx,
            brain_evaluator=mock_brain,
            qdrant_client=mock_qdrant,
        )
        assert evaluator.redis_client == mock_redis
        assert evaluator.influxdb_client == mock_influx
        assert evaluator.brain_evaluator == mock_brain
        assert evaluator.qdrant_client == mock_qdrant

    def test_run_6h_eval(self) -> None:
        """Test 6h evaluation run."""
        mock_redis = MagicMock()
        mock_brain = MagicMock()

        # Mock BrainEvaluator to return some evaluations
        from brain.evaluation import (
            EvaluationMetrics,
            EvaluationResult,
            EvaluationStatus,
        )

        mock_brain.list_evaluations.return_value = [
            EvaluationResult(
                version="1.0.0",
                status=EvaluationStatus.PASSED,
                metrics=EvaluationMetrics(accuracy=0.95, precision=0.90),
                started_at="2024-01-01T00:00:00Z",
            )
        ]

        evaluator = MiniBrainEval(
            redis_client=mock_redis,
            brain_evaluator=mock_brain,
        )

        result = evaluator.run_6h_eval()

        assert result.cadence == "6h"
        assert result.eval_id is not None
        assert "avg_accuracy" in result.kpis
        assert mock_redis.set.called

    def test_run_daily_eval(self) -> None:
        """Test daily evaluation run."""
        mock_redis = MagicMock()
        # Track calls manually since side_effect doesn't set .called
        calls = []

        def mock_set(key, value, ex=None):
            calls.append((key, value, ex))
            json.loads(value)  # Verify it's valid JSON
            return True

        mock_redis.set = mock_set

        evaluator = MiniBrainEval(redis_client=mock_redis)
        result = evaluator.run_daily_eval()

        assert result.cadence == "daily"
        assert result.eval_id is not None
        assert len(calls) > 0  # Redis set was called

    def test_run_weekly_eval(self) -> None:
        """Test weekly evaluation run."""
        mock_redis = MagicMock()
        # Track calls manually
        calls = []

        def mock_set(key, value, ex=None):
            calls.append((key, value, ex))
            json.loads(value)  # Verify it's valid JSON
            return True

        mock_redis.set = mock_set
        # Mock scan to return empty for trend analysis
        mock_redis.scan.return_value = (0, [])

        evaluator = MiniBrainEval(redis_client=mock_redis)
        result = evaluator.run_weekly_eval()

        assert result.cadence == "weekly"
        assert result.eval_id is not None
        assert len(calls) > 0  # Redis set was called

    def test_collect_kpis_no_evaluator(self) -> None:
        """Test KPI collection without BrainEvaluator."""
        evaluator = MiniBrainEval()
        kpis = evaluator.collect_kpis()

        assert kpis["status"] == "no_evaluator"

    def test_collect_kpis_with_evaluator(self) -> None:
        """Test KPI collection with BrainEvaluator."""
        from brain.evaluation import (
            EvaluationMetrics,
            EvaluationResult,
            EvaluationStatus,
        )

        mock_brain = MagicMock()
        mock_brain.list_evaluations.return_value = [
            EvaluationResult(
                version="1.0.0",
                status=EvaluationStatus.PASSED,
                metrics=EvaluationMetrics(
                    accuracy=0.95,
                    precision=0.90,
                    recall=0.85,
                    f1_score=0.875,
                ),
                started_at="2024-01-01T00:00:00Z",
            ),
            EvaluationResult(
                version="1.1.0",
                status=EvaluationStatus.PASSED,
                metrics=EvaluationMetrics(
                    accuracy=0.92,
                    precision=0.88,
                    recall=0.82,
                    f1_score=0.85,
                ),
                started_at="2024-01-02T00:00:00Z",
            ),
        ]

        evaluator = MiniBrainEval(brain_evaluator=mock_brain)
        kpis = evaluator.collect_kpis()

        assert kpis["evaluations_count"] == 2
        assert kpis["passed_count"] == 2
        assert "avg_accuracy" in kpis
        assert "avg_precision" in kpis
        assert "latest_version" in kpis

    def test_check_data_freshness_no_clients(self) -> None:
        """Test data freshness check without clients."""
        evaluator = MiniBrainEval()
        freshness = evaluator.check_data_freshness()

        assert freshness["redis"] == "no_client"
        assert freshness["influxdb"] == "no_client"
        assert freshness["qdrant"] == "no_client"

    def test_check_data_freshness_with_redis(self) -> None:
        """Test data freshness check with Redis."""
        mock_redis = MagicMock()
        mock_redis.ping.return_value = True

        evaluator = MiniBrainEval(redis_client=mock_redis)
        freshness = evaluator.check_data_freshness()

        assert freshness["redis"] == "fresh"
        mock_redis.ping.assert_called_once()

    def test_check_data_freshness_redis_error(self) -> None:
        """Test data freshness check when Redis fails."""
        mock_redis = MagicMock()
        mock_redis.ping.side_effect = Exception("Connection refused")

        evaluator = MiniBrainEval(redis_client=mock_redis)
        freshness = evaluator.check_data_freshness()

        assert "stale" in freshness["redis"]
        assert "Connection refused" in freshness["redis"]

    def test_detect_issues_with_sample_log(self) -> None:
        """Test issue detection with sample log content."""
        evaluator = MiniBrainEval()

        sample_log = """
        2024-01-01 00:00:00 ERROR ConnectionRefusedError: database connection failed
        2024-01-01 00:00:01 ERROR FileNotFoundError: config file missing
        2024-01-01 00:00:02 WARNING High latency detected in query
        """

        issues = evaluator.detect_issues(log_source=sample_log)

        assert len(issues) >= 2  # At least DB and file issues

        # Check that we detected the right categories
        categories = {issue.category for issue in issues}
        assert "db_connectivity" in categories
        assert "file_access" in categories

    def test_detect_issues_file_not_found(self) -> None:
        """Test issue detection when log file doesn't exist."""
        evaluator = MiniBrainEval()

        issues = evaluator.detect_issues(log_source="/nonexistent/path.log")

        assert len(issues) == 0

    def test_detect_issues_empty_log(self) -> None:
        """Test issue detection with empty log."""
        evaluator = MiniBrainEval()

        issues = evaluator.detect_issues(log_source="")

        assert len(issues) == 0

    def test_detect_issues_from_file(self) -> None:
        """Test issue detection from log file."""
        evaluator = MiniBrainEval()

        log_content = (
            "FileNotFoundError: missing file\nTimeoutError: operation timed out"
        )

        with patch("builtins.open", mock_open(read_data=log_content)):
            issues = evaluator.detect_issues(log_source="/tmp/test.log")

        assert len(issues) >= 2

    def test_determine_severity_critical(self) -> None:
        """Test severity determination for critical issues."""
        evaluator = MiniBrainEval()

        severity = evaluator._determine_severity(
            "db_connectivity", "CRITICAL: database connection failed"
        )
        assert severity == IssueSeverity.P0

    def test_determine_severity_by_category(self) -> None:
        """Test severity determination by category."""
        evaluator = MiniBrainEval()

        # DB connectivity defaults to P1
        severity = evaluator._determine_severity("db_connectivity", "normal error")
        assert severity == IssueSeverity.P1

        # File access defaults to P2
        severity = evaluator._determine_severity("file_access", "normal error")
        assert severity == IssueSeverity.P2

        # Unknown category defaults to P3
        severity = evaluator._determine_severity("other", "normal error")
        assert severity == IssueSeverity.P3

    def test_mitigate_issue_file_access(self) -> None:
        """Test mitigation for file access issues."""
        evaluator = MiniBrainEval()

        issue = Issue.create(
            category=IssueCategory.FILE_ACCESS,
            severity=IssueSeverity.P2,
            description="File not found",
            source="test",
        )

        mitigation = evaluator._mitigate_issue(issue)

        assert mitigation is not None
        assert "permissions" in mitigation.action.lower()
        assert mitigation.result == "partial"

    def test_mitigate_issue_db_connectivity(self) -> None:
        """Test mitigation for DB connectivity issues."""
        evaluator = MiniBrainEval()

        issue = Issue.create(
            category=IssueCategory.DB_CONNECTIVITY,
            severity=IssueSeverity.P1,
            description="Connection failed",
            source="test",
        )

        mitigation = evaluator._mitigate_issue(issue)

        assert mitigation is not None
        assert "database" in mitigation.action.lower()
        assert mitigation.result == "partial"

    def test_mitigate_issue_unknown_category(self) -> None:
        """Test mitigation for unknown category."""
        evaluator = MiniBrainEval()

        issue = Issue.create(
            category=IssueCategory.OTHER,
            severity=IssueSeverity.P3,
            description="Unknown issue",
            source="test",
        )

        mitigation = evaluator._mitigate_issue(issue)

        assert mitigation is None

    def test_store_result_redis(self) -> None:
        """Test storing result in Redis."""
        mock_redis = MagicMock()

        # Mock set to accept any JSON-serializable value
        def mock_set(key, value, ex=None):
            # Verify it's valid JSON
            json.loads(value)
            return True

        mock_redis.set.side_effect = mock_set

        evaluator = MiniBrainEval(redis_client=mock_redis)

        result = MiniEvalResult.create(cadence="6h", kpis={"test": 1.0})
        evaluator._store_result(result)

        assert mock_redis.set.called
        call_args = mock_redis.set.call_args
        assert "mini" in call_args[0][0]  # Key contains 'mini'
        assert "6h" in call_args[0][0]  # Key contains cadence

    def test_get_recent_results(self) -> None:
        """Test getting recent results from Redis."""
        mock_redis = MagicMock()

        # Create a sample result
        result = MiniEvalResult.create(cadence="6h", kpis={"test": 1.0})

        mock_redis.scan.return_value = (
            0,
            ["bmad:chiseai:brain:eval:mini:6h:2024-01-01"],
        )
        mock_redis.get.return_value = result.to_json()

        evaluator = MiniBrainEval(redis_client=mock_redis)
        results = evaluator.get_recent_results(limit=5)

        assert len(results) == 1
        assert results[0].cadence == "6h"

    def test_get_recent_results_no_redis(self) -> None:
        """Test getting recent results without Redis."""
        evaluator = MiniBrainEval()
        results = evaluator.get_recent_results()

        assert results == []

    def test_get_recent_results_by_cadence(self) -> None:
        """Test getting recent results filtered by cadence."""
        mock_redis = MagicMock()

        result = MiniEvalResult.create(cadence="daily", kpis={"test": 1.0})

        mock_redis.scan.return_value = (
            0,
            ["bmad:chiseai:brain:eval:mini:daily:2024-01-01"],
        )
        mock_redis.get.return_value = result.to_json()

        evaluator = MiniBrainEval(redis_client=mock_redis)
        results = evaluator.get_recent_results(cadence="daily")

        assert len(results) == 1
        assert results[0].cadence == "daily"

    def test_serialization_roundtrip(self) -> None:
        """Test that serialization and deserialization work correctly."""
        # Create a complex result
        result = MiniEvalResult.create(
            cadence="daily",
            kpis={"accuracy": 0.95, "count": 100},
            proxies={"cpu": 45.5},
            data_freshness={"redis": "fresh", "influxdb": "stale"},
        )

        issue = Issue.create(
            category=IssueCategory.TOOL_ERROR,
            severity=IssueSeverity.P1,
            description="Tool failed",
            source="test",
        )
        result.add_issue(issue)

        mitigation = Mitigation.create(
            issue_id=issue.issue_id,
            action="Retry",
            result=MitigationResult.SUCCESS,
        )
        result.add_mitigation(mitigation)

        # Serialize and deserialize
        json_str = result.to_json()
        restored = MiniEvalResult.from_json(json_str)

        assert restored.eval_id == result.eval_id
        assert restored.cadence == result.cadence
        assert restored.kpis == result.kpis
        assert len(restored.issues) == 1
        assert restored.issues[0].category == "tool_error"
        assert len(restored.mitigations) == 1
        assert restored.mitigations[0].action == "Retry"

    def test_redis_storage_key_pattern(self) -> None:
        """Test that Redis storage uses correct key pattern."""
        mock_redis = MagicMock()
        evaluator = MiniBrainEval(redis_client=mock_redis)

        result = MiniEvalResult.create(cadence="6h")
        evaluator._store_result(result)

        # Verify key pattern: bmad:chiseai:brain:eval:mini:<cadence>:<timestamp>
        call_args = mock_redis.set.call_args
        key = call_args[0][0]
        assert key.startswith("bmad:chiseai:brain:eval:mini:6h:")

    def test_redis_storage_ttl(self) -> None:
        """Test that Redis storage uses correct TTL."""
        mock_redis = MagicMock()
        evaluator = MiniBrainEval(redis_client=mock_redis)

        result = MiniEvalResult.create(cadence="6h")
        evaluator._store_result(result)

        # Verify TTL is 30 days (86400 * 30 = 2592000)
        call_kwargs = mock_redis.set.call_args[1]
        assert call_kwargs.get("ex") == 2592000
