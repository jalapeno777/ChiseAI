"""
Tests for SLA compliance validation.

These tests validate that runbooks meet their SLA requirements.
"""

import json

from scripts.ops.validate_runbooks import (
    RunbookValidator,
    ScenarioResult,
    SLAResult,
    ValidationReport,
)


class TestSLAResult:
    """Tests for SLAResult dataclass."""

    def test_sla_result_creation(self):
        """Test creating an SLAResult."""
        result = SLAResult(
            runbook_name="test-runbook",
            metric_name="response_time",
            target_value=30.0,
            actual_value=15.0,
            unit="seconds",
            passed=True,
        )

        assert result.runbook_name == "test-runbook"
        assert result.metric_name == "response_time"
        assert result.target_value == 30.0
        assert result.actual_value == 15.0
        assert result.unit == "seconds"
        assert result.passed is True

    def test_sla_result_to_dict(self):
        """Test converting SLAResult to dictionary."""
        result = SLAResult(
            runbook_name="test-runbook",
            metric_name="response_time",
            target_value=30.0,
            actual_value=15.0,
            unit="seconds",
            passed=True,
            details={"test": "data"},
        )

        d = result.to_dict()
        assert d["runbook_name"] == "test-runbook"
        assert d["metric_name"] == "response_time"
        assert d["target_value"] == 30.0
        assert d["actual_value"] == 15.0
        assert d["unit"] == "seconds"
        assert d["passed"] is True
        assert d["details"] == {"test": "data"}
        assert "timestamp" in d

    def test_sla_result_passed_when_under_target(self):
        """Test that result passes when actual < target."""
        result = SLAResult(
            runbook_name="test",
            metric_name="time",
            target_value=30.0,
            actual_value=25.0,
            unit="seconds",
            passed=True,
        )
        assert result.passed is True

    def test_sla_result_failed_when_over_target(self):
        """Test that result fails when actual > target."""
        result = SLAResult(
            runbook_name="test",
            metric_name="time",
            target_value=30.0,
            actual_value=35.0,
            unit="seconds",
            passed=False,
        )
        assert result.passed is False


class TestScenarioResult:
    """Tests for ScenarioResult dataclass."""

    def test_scenario_result_creation(self):
        """Test creating a ScenarioResult."""
        result = ScenarioResult(
            scenario_name="safety_test",
            runbook_name="kill-switch",
            passed=True,
            execution_time_seconds=45.0,
            steps_executed=5,
            steps_passed=5,
            steps_failed=0,
        )

        assert result.scenario_name == "safety_test"
        assert result.runbook_name == "kill-switch"
        assert result.passed is True
        assert result.execution_time_seconds == 45.0
        assert result.steps_executed == 5
        assert result.steps_passed == 5
        assert result.steps_failed == 0

    def test_scenario_result_with_error(self):
        """Test ScenarioResult with error message."""
        result = ScenarioResult(
            scenario_name="failed_test",
            runbook_name="test-runbook",
            passed=False,
            execution_time_seconds=10.0,
            steps_executed=3,
            steps_passed=1,
            steps_failed=2,
            error_message="Step 2 failed",
        )

        assert result.passed is False
        assert result.error_message == "Step 2 failed"

    def test_scenario_result_to_dict(self):
        """Test converting ScenarioResult to dictionary."""
        result = ScenarioResult(
            scenario_name="test",
            runbook_name="runbook",
            passed=True,
            execution_time_seconds=30.0,
            steps_executed=3,
            steps_passed=3,
            steps_failed=0,
            evidence={"key": "value"},
        )

        d = result.to_dict()
        assert d["scenario_name"] == "test"
        assert d["runbook_name"] == "runbook"
        assert d["passed"] is True
        assert d["execution_time_seconds"] == 30.0
        assert d["evidence"] == {"key": "value"}


class TestValidationReport:
    """Tests for ValidationReport dataclass."""

    def test_validation_report_creation(self):
        """Test creating a ValidationReport."""
        report = ValidationReport()

        assert report.timestamp is not None
        assert report.sla_results == []
        assert report.scenario_results == []
        assert report.summary == {}

    def test_validation_report_with_results(self):
        """Test ValidationReport with results."""
        report = ValidationReport()
        report.sla_results.append(
            SLAResult(
                runbook_name="test",
                metric_name="time",
                target_value=30.0,
                actual_value=15.0,
                unit="seconds",
                passed=True,
            )
        )
        report.scenario_results.append(
            ScenarioResult(
                scenario_name="test",
                runbook_name="runbook",
                passed=True,
                execution_time_seconds=30.0,
                steps_executed=3,
                steps_passed=3,
                steps_failed=0,
            )
        )

        assert len(report.sla_results) == 1
        assert len(report.scenario_results) == 1

    def test_validation_report_to_dict(self):
        """Test converting ValidationReport to dictionary."""
        report = ValidationReport()
        report.sla_results.append(
            SLAResult(
                runbook_name="test",
                metric_name="time",
                target_value=30.0,
                actual_value=15.0,
                unit="seconds",
                passed=True,
            )
        )
        report.summary = {"total": 1, "passed": 1}

        d = report.to_dict()
        assert "timestamp" in d
        assert len(d["sla_results"]) == 1
        assert d["summary"]["total"] == 1

    def test_validation_report_to_json(self):
        """Test converting ValidationReport to JSON."""
        report = ValidationReport()
        report.sla_results.append(
            SLAResult(
                runbook_name="test",
                metric_name="time",
                target_value=30.0,
                actual_value=15.0,
                unit="seconds",
                passed=True,
            )
        )

        json_str = report.to_json()
        assert "test" in json_str
        assert "time" in json_str

        # Should be valid JSON
        parsed = json.loads(json_str)
        assert parsed["sla_results"][0]["runbook_name"] == "test"


class TestRunbookValidatorSLA:
    """Tests for RunbookValidator SLA validation."""

    def test_validator_initialization(self, tmp_path):
        """Test validator initialization."""
        validator = RunbookValidator(runbooks_dir=tmp_path, dry_run=True)

        assert validator.dry_run is True
        assert validator.parser is not None
        assert validator.executor is not None

    def test_sla_requirements_defined(self):
        """Test that SLA requirements are properly defined."""
        validator = RunbookValidator(dry_run=True)

        assert "kill_switch_trigger" in validator.SLA_REQUIREMENTS
        assert "circuit_breaker_toggle" in validator.SLA_REQUIREMENTS
        assert "rollback" in validator.SLA_REQUIREMENTS
        assert "oncall_acknowledgment" in validator.SLA_REQUIREMENTS

        # Check targets
        assert validator.SLA_REQUIREMENTS["kill_switch_trigger"]["target_seconds"] == 30
        assert (
            validator.SLA_REQUIREMENTS["circuit_breaker_toggle"]["target_seconds"] == 60
        )
        assert validator.SLA_REQUIREMENTS["rollback"]["target_minutes"] == 5
        assert (
            validator.SLA_REQUIREMENTS["oncall_acknowledgment"]["target_minutes"] == 15
        )

    def test_validate_kill_switch_sla_pass(self, tmp_path):
        """Test kill switch SLA validation passes when under target."""
        # Create a mock kill-switch runbook
        runbooks_dir = tmp_path / "runbooks"
        runbooks_dir.mkdir()

        content = """---
title: Kill Switch Test
executable: true
steps:
  - name: "Test Step"
    command: "echo test"
---

# Kill Switch Test
"""
        (runbooks_dir / "kill-switch-trigger.md").write_text(content)

        validator = RunbookValidator(runbooks_dir=runbooks_dir, dry_run=True)
        validator._validate_kill_switch_sla()

        assert len(validator.report.sla_results) == 1
        result = validator.report.sla_results[0]
        assert result.runbook_name == "kill-switch-trigger"
        assert result.metric_name == "trigger_time"
        assert result.target_value == 30.0
        assert result.passed is True

    def test_validate_circuit_breaker_sla(self, tmp_path):
        """Test circuit breaker SLA validation."""
        runbooks_dir = tmp_path / "runbooks"
        runbooks_dir.mkdir()

        content = """---
title: Redis Failure Response
executable: true
steps:
  - name: "Check Circuit Breaker"
    command: "echo check"
---

# Redis Failure Response
"""
        (runbooks_dir / "redis-failure-response.md").write_text(content)

        validator = RunbookValidator(runbooks_dir=runbooks_dir, dry_run=True)
        validator._validate_circuit_breaker_sla()

        assert len(validator.report.sla_results) == 1
        result = validator.report.sla_results[0]
        assert result.runbook_name == "redis-failure-response"
        assert result.metric_name == "circuit_breaker_toggle_time"
        assert result.target_value == 60.0

    def test_validate_rollback_sla_found(self, tmp_path):
        """Test rollback SLA validation when rollback procedures exist."""
        runbooks_dir = tmp_path / "runbooks"
        runbooks_dir.mkdir()

        content = """---
title: Rollback Procedures
executable: true
steps:
  - name: "Step 1"
    command: "echo 1"
  - name: "Step 2"
    command: "echo 2"
  - name: "Step 3"
    command: "echo 3"
---

# Rollback Procedures

This runbook covers rollback and recovery procedures.
"""
        (runbooks_dir / "rollback.md").write_text(content)

        validator = RunbookValidator(runbooks_dir=runbooks_dir, dry_run=True)
        validator._validate_rollback_sla()

        assert len(validator.report.sla_results) == 1
        result = validator.report.sla_results[0]
        assert result.metric_name == "rollback_time"
        assert result.target_value == 300.0  # 5 minutes in seconds
        assert result.details["rollback_found"] is True

    def test_validate_oncall_sla_found(self, tmp_path):
        """Test on-call SLA validation when procedures exist."""
        runbooks_dir = tmp_path / "runbooks"
        runbooks_dir.mkdir()

        content = """---
title: On-Call Procedures
executable: true
steps:
  - name: "Acknowledge Alert"
    command: "echo ack"
---

# On-Call Procedures

Contact the on-call engineer via PagerDuty.
"""
        (runbooks_dir / "oncall.md").write_text(content)

        validator = RunbookValidator(runbooks_dir=runbooks_dir, dry_run=True)
        validator._validate_oncall_sla()

        assert len(validator.report.sla_results) == 1
        result = validator.report.sla_results[0]
        assert result.metric_name == "acknowledgment_time"
        assert result.target_value == 15.0  # 15 minutes
        assert result.details["oncall_found"] is True


class TestRunbookValidatorScenarios:
    """Tests for RunbookValidator scenario tests."""

    def test_safety_scenario(self, tmp_path):
        """Test safety scenario validation."""
        runbooks_dir = tmp_path / "runbooks"
        runbooks_dir.mkdir()

        content = """---
title: Kill Switch Trigger
executable: true
steps:
  - name: "Check Status"
    command: "echo status"
  - name: "Trigger Kill Switch"
    command: "echo trigger"
---

# Kill Switch Trigger
"""
        (runbooks_dir / "kill-switch-trigger.md").write_text(content)

        validator = RunbookValidator(runbooks_dir=runbooks_dir, dry_run=True)
        validator._test_safety_scenario()

        assert len(validator.report.scenario_results) == 1
        result = validator.report.scenario_results[0]
        assert result.scenario_name == "safety_kill_switch"
        assert result.runbook_name == "kill-switch-trigger"
        assert result.passed is True

    def test_ml_operations_scenario(self, tmp_path):
        """Test ML operations scenario validation."""
        runbooks_dir = tmp_path / "runbooks"
        runbooks_dir.mkdir()

        content = """---
title: ML Model Training
executable: true
steps:
  - name: "Start Training"
    command: "echo train"
---

# ML Model Training

This runbook covers ML model training and validation.
"""
        (runbooks_dir / "ml-training.md").write_text(content)

        validator = RunbookValidator(runbooks_dir=runbooks_dir, dry_run=True)
        validator._test_ml_operations_scenario()

        assert len(validator.report.scenario_results) == 1
        result = validator.report.scenario_results[0]
        assert result.scenario_name == "ml_operations"
        assert result.passed is True
        assert "ml-training" in result.evidence["ml_runbooks_found"]

    def test_rollback_scenario(self, tmp_path):
        """Test rollback scenario validation."""
        runbooks_dir = tmp_path / "runbooks"
        runbooks_dir.mkdir()

        content = """---
title: System Recovery
executable: true
steps:
  - name: "Initiate Rollback"
    command: "echo rollback"
---

# System Recovery

Procedures for system rollback and recovery.
"""
        (runbooks_dir / "recovery.md").write_text(content)

        validator = RunbookValidator(runbooks_dir=runbooks_dir, dry_run=True)
        validator._test_rollback_scenario()

        assert len(validator.report.scenario_results) == 1
        result = validator.report.scenario_results[0]
        assert result.scenario_name == "rollback"
        assert result.passed is True  # 180s < 300s target

    def test_oncall_scenario(self, tmp_path):
        """Test on-call scenario validation."""
        runbooks_dir = tmp_path / "runbooks"
        runbooks_dir.mkdir()

        content = """---
title: Incident Response
executable: true
steps:
  - name: "Page On-Call"
    command: "echo page"
---

# Incident Response

Escalation path includes on-call engineer.
"""
        (runbooks_dir / "incident-response.md").write_text(content)

        validator = RunbookValidator(runbooks_dir=runbooks_dir, dry_run=True)
        validator._test_oncall_scenario()

        assert len(validator.report.scenario_results) == 1
        result = validator.report.scenario_results[0]
        assert result.scenario_name == "oncall_acknowledgment"
        assert result.passed is True  # 8min < 15min target


class TestRunbookValidatorSummary:
    """Tests for RunbookValidator summary generation."""

    def test_generate_summary_all_pass(self):
        """Test summary generation when all tests pass."""
        validator = RunbookValidator(dry_run=True)

        # Add passing SLA results
        validator.report.sla_results.append(
            SLAResult(
                runbook_name="test1",
                metric_name="time",
                target_value=30.0,
                actual_value=15.0,
                unit="seconds",
                passed=True,
            )
        )
        validator.report.sla_results.append(
            SLAResult(
                runbook_name="test2",
                metric_name="time",
                target_value=60.0,
                actual_value=30.0,
                unit="seconds",
                passed=True,
            )
        )

        # Add passing scenario results
        validator.report.scenario_results.append(
            ScenarioResult(
                scenario_name="test",
                runbook_name="runbook",
                passed=True,
                execution_time_seconds=30.0,
                steps_executed=3,
                steps_passed=3,
                steps_failed=0,
            )
        )

        validator._generate_summary()

        assert validator.report.summary["sla_validation"]["passed"] == 2
        assert validator.report.summary["sla_validation"]["total"] == 2
        assert validator.report.summary["sla_validation"]["success_rate"] == 100.0

        assert validator.report.summary["scenario_validation"]["passed"] == 1
        assert validator.report.summary["scenario_validation"]["total"] == 1
        assert validator.report.summary["scenario_validation"]["success_rate"] == 100.0

        assert validator.report.summary["overall"]["passed"] == 3
        assert validator.report.summary["overall"]["total"] == 3
        assert validator.report.summary["overall"]["status"] == "PASS"

    def test_generate_summary_some_fail(self):
        """Test summary generation when some tests fail."""
        validator = RunbookValidator(dry_run=True)

        # Add mixed SLA results
        validator.report.sla_results.append(
            SLAResult(
                runbook_name="test1",
                metric_name="time",
                target_value=30.0,
                actual_value=15.0,
                unit="seconds",
                passed=True,
            )
        )
        validator.report.sla_results.append(
            SLAResult(
                runbook_name="test2",
                metric_name="time",
                target_value=60.0,
                actual_value=90.0,
                unit="seconds",
                passed=False,
            )
        )

        # Add failing scenario result
        validator.report.scenario_results.append(
            ScenarioResult(
                scenario_name="test",
                runbook_name="runbook",
                passed=False,
                execution_time_seconds=30.0,
                steps_executed=3,
                steps_passed=1,
                steps_failed=2,
            )
        )

        validator._generate_summary()

        assert validator.report.summary["sla_validation"]["passed"] == 1
        assert validator.report.summary["sla_validation"]["total"] == 2
        assert validator.report.summary["sla_validation"]["success_rate"] == 50.0

        assert validator.report.summary["scenario_validation"]["passed"] == 0
        assert validator.report.summary["scenario_validation"]["total"] == 1
        assert validator.report.summary["scenario_validation"]["success_rate"] == 0.0

        assert validator.report.summary["overall"]["passed"] == 1
        assert validator.report.summary["overall"]["total"] == 3
        assert validator.report.summary["overall"]["status"] == "FAIL"


class TestRunbookValidatorIntegration:
    """Integration tests for RunbookValidator."""

    def test_validate_all_integration(self, tmp_path):
        """Test complete validation workflow."""
        runbooks_dir = tmp_path / "runbooks"
        runbooks_dir.mkdir()

        # Create multiple runbooks
        runbooks = {
            "kill-switch-trigger.md": """---
title: Kill Switch
executable: true
steps:
  - name: "Trigger"
    command: "echo trigger"
---
# Kill Switch
""",
            "redis-failure-response.md": """---
title: Redis Failure
executable: true
steps:
  - name: "Check"
    command: "echo check"
---
# Redis Failure
""",
            "rollback.md": """---
title: Rollback
executable: true
steps:
  - name: "Rollback"
    command: "echo rollback"
---
# Rollback Procedures
""",
        }

        for filename, content in runbooks.items():
            (runbooks_dir / filename).write_text(content)

        validator = RunbookValidator(runbooks_dir=runbooks_dir, dry_run=True)
        report = validator.validate_all()

        assert report.timestamp is not None
        assert len(report.sla_results) > 0
        assert len(report.scenario_results) > 0
        assert "overall" in report.summary

    def test_empty_runbooks_directory(self, tmp_path):
        """Test validation with empty runbooks directory."""
        runbooks_dir = tmp_path / "runbooks"
        runbooks_dir.mkdir()

        validator = RunbookValidator(runbooks_dir=runbooks_dir, dry_run=True)
        report = validator.validate_all()

        # Should complete without errors even with no runbooks
        assert report.timestamp is not None
        assert report.summary is not None
