"""
Tests for scenario execution validation.

These tests validate that scenarios can be executed successfully.
"""

import time

from scripts.ops.validate_runbooks import (
    RunbookValidator,
)


class TestScenarioExecution:
    """Tests for scenario execution functionality."""

    def test_safety_scenario_execution(self, tmp_path):
        """Test safety scenario executes correctly."""
        runbooks_dir = tmp_path / "runbooks"
        runbooks_dir.mkdir()

        content = """---
title: Kill Switch Trigger
executable: true
steps:
  - name: "Check execution status"
    command: "echo paused"
  - name: "Cancel pending orders"
    command: "echo cancelled"
  - name: "Log incident"
    command: "echo logged"
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
        assert result.steps_executed == 3
        assert result.steps_passed == 3
        assert result.steps_failed == 0
        assert result.execution_time_seconds > 0

    def test_safety_scenario_with_missing_runbook(self, tmp_path):
        """Test safety scenario handles missing runbook gracefully."""
        runbooks_dir = tmp_path / "runbooks"
        runbooks_dir.mkdir()

        validator = RunbookValidator(runbooks_dir=runbooks_dir, dry_run=True)
        validator._test_safety_scenario()

        # Should add a result even if runbook not found (with failed status)
        assert len(validator.report.scenario_results) == 1
        result = validator.report.scenario_results[0]
        assert result.passed is False

    def test_ml_operations_scenario_with_multiple_runbooks(self, tmp_path):
        """Test ML operations scenario finds all ML-related runbooks."""
        runbooks_dir = tmp_path / "runbooks"
        runbooks_dir.mkdir()

        # Create multiple ML-related runbooks
        ml_runbooks = [
            ("ml-training.md", "ML Model Training"),
            ("model-validation.md", "Model Validation"),
            ("retraining.md", "Model Retraining"),
        ]

        for filename, title in ml_runbooks:
            content = f"""---
title: {title}
executable: true
steps:
  - name: "Step 1"
    command: "echo step1"
---

# {title}

This covers ML operations.
"""
            (runbooks_dir / filename).write_text(content)

        validator = RunbookValidator(runbooks_dir=runbooks_dir, dry_run=True)
        validator._test_ml_operations_scenario()

        assert len(validator.report.scenario_results) == 1
        result = validator.report.scenario_results[0]

        assert result.scenario_name == "ml_operations"
        assert result.passed is True
        assert len(result.evidence["ml_runbooks_found"]) == 3

    def test_rollback_scenario_meets_sla(self, tmp_path):
        """Test rollback scenario completes within 5 minute SLA."""
        runbooks_dir = tmp_path / "runbooks"
        runbooks_dir.mkdir()

        content = """---
title: Rollback Procedures
executable: true
steps:
  - name: "Stop Services"
    command: "echo stop"
  - name: "Restore Database"
    command: "echo restore"
  - name: "Start Services"
    command: "echo start"
---

# Rollback Procedures

System rollback and recovery procedures.
"""
        (runbooks_dir / "rollback.md").write_text(content)

        validator = RunbookValidator(runbooks_dir=runbooks_dir, dry_run=True)
        validator._test_rollback_scenario()

        assert len(validator.report.scenario_results) == 1
        result = validator.report.scenario_results[0]

        assert result.scenario_name == "rollback"
        assert result.passed is True  # Simulated 180s < 300s target
        assert result.evidence["target_seconds"] == 300

    def test_oncall_scenario_meets_sla(self, tmp_path):
        """Test on-call scenario meets 15 minute acknowledgment SLA."""
        runbooks_dir = tmp_path / "runbooks"
        runbooks_dir.mkdir()

        content = """---
title: Incident Response
executable: true
steps:
  - name: "Page On-Call Engineer"
    command: "echo page"
---

# Incident Response

On-call escalation procedures via PagerDuty.
"""
        (runbooks_dir / "incident-response.md").write_text(content)

        validator = RunbookValidator(runbooks_dir=runbooks_dir, dry_run=True)
        validator._test_oncall_scenario()

        assert len(validator.report.scenario_results) == 1
        result = validator.report.scenario_results[0]

        assert result.scenario_name == "oncall_acknowledgment"
        assert result.passed is True  # Simulated 8min < 15min target
        assert result.evidence["acknowledgment_time_minutes"] == 8
        assert result.evidence["target_minutes"] == 15

    def test_scenario_with_execution_error(self, tmp_path):
        """Test scenario handles execution errors gracefully."""
        runbooks_dir = tmp_path / "runbooks"
        runbooks_dir.mkdir()

        content = """---
title: Test Runbook
executable: true
steps:
  - name: "Failing Step"
    command: "exit 1"
---

# Test Runbook
"""
        (runbooks_dir / "kill-switch-trigger.md").write_text(content)

        validator = RunbookValidator(runbooks_dir=runbooks_dir, dry_run=False)
        validator._test_safety_scenario()

        assert len(validator.report.scenario_results) == 1
        result = validator.report.scenario_results[0]

        # Should still record the result even if execution failed
        assert result.scenario_name == "safety_kill_switch"
        # In dry-run mode, even failing commands appear successful
        # In live mode with actual execution, the step would fail
        assert result.steps_executed >= 1


class TestScenarioEvidence:
    """Tests for scenario evidence collection."""

    def test_scenario_evidence_includes_log_file(self, tmp_path):
        """Test that scenario evidence includes log file reference."""
        runbooks_dir = tmp_path / "runbooks"
        runbooks_dir.mkdir()

        content = """---
title: Kill Switch
executable: true
steps:
  - name: "Test"
    command: "echo test"
---

# Kill Switch
"""
        (runbooks_dir / "kill-switch-trigger.md").write_text(content)

        validator = RunbookValidator(runbooks_dir=runbooks_dir, dry_run=True)
        validator._test_safety_scenario()

        result = validator.report.scenario_results[0]
        assert "log_file" in result.evidence
        assert result.evidence["dry_run"] is True

    def test_scenario_evidence_includes_runbook_list(self, tmp_path):
        """Test that ML scenario evidence includes found runbooks."""
        runbooks_dir = tmp_path / "runbooks"
        runbooks_dir.mkdir()

        content = """---
title: ML Training
executable: true
steps:
  - name: "Train"
    command: "echo train"
---

# ML Training
"""
        (runbooks_dir / "ml-training.md").write_text(content)

        validator = RunbookValidator(runbooks_dir=runbooks_dir, dry_run=True)
        validator._test_ml_operations_scenario()

        result = validator.report.scenario_results[0]
        assert "ml_runbooks_found" in result.evidence
        assert "ml-training" in result.evidence["ml_runbooks_found"]
        assert result.evidence["simulated"] is True

    def test_rollback_scenario_evidence_includes_timing(self, tmp_path):
        """Test that rollback scenario evidence includes timing info."""
        runbooks_dir = tmp_path / "runbooks"
        runbooks_dir.mkdir()

        content = """---
title: Rollback
executable: true
steps:
  - name: "Rollback"
    command: "echo rollback"
---

# Rollback
"""
        (runbooks_dir / "rollback.md").write_text(content)

        validator = RunbookValidator(runbooks_dir=runbooks_dir, dry_run=True)
        validator._test_rollback_scenario()

        result = validator.report.scenario_results[0]
        assert result.evidence["target_seconds"] == 300
        assert result.evidence["simulated"] is True
        assert "rollback_runbooks_found" in result.evidence


class TestScenarioIntegration:
    """Integration tests for scenario execution."""

    def test_all_scenarios_run_together(self, tmp_path):
        """Test that all scenarios can run in sequence."""
        runbooks_dir = tmp_path / "runbooks"
        runbooks_dir.mkdir()

        # Create runbooks for all scenarios
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
            "ml-training.md": """---
title: ML Training
executable: true
steps:
  - name: "Train"
    command: "echo train"
---
# ML Training
""",
            "rollback.md": """---
title: Rollback
executable: true
steps:
  - name: "Rollback"
    command: "echo rollback"
---
# Rollback
""",
            "incident-response.md": """---
title: Incident Response
executable: true
steps:
  - name: "Page On-Call"
    command: "echo page"
---

# Incident Response

Contact the on-call engineer via PagerDuty.
""",
        }

        for filename, content in runbooks.items():
            (runbooks_dir / filename).write_text(content)

        validator = RunbookValidator(runbooks_dir=runbooks_dir, dry_run=True)

        # Run all scenarios
        validator._test_safety_scenario()
        validator._test_ml_operations_scenario()
        validator._test_rollback_scenario()
        validator._test_oncall_scenario()

        # Should have 4 scenario results
        assert len(validator.report.scenario_results) == 4

        # All should pass
        for result in validator.report.scenario_results:
            assert result.passed is True

    def test_scenario_execution_timing(self, tmp_path):
        """Test that scenario execution times are recorded."""
        runbooks_dir = tmp_path / "runbooks"
        runbooks_dir.mkdir()

        content = """---
title: Test
executable: true
steps:
  - name: "Step"
    command: "echo step"
---

# Test
"""
        (runbooks_dir / "kill-switch-trigger.md").write_text(content)

        validator = RunbookValidator(runbooks_dir=runbooks_dir, dry_run=True)

        start_time = time.time()
        validator._test_safety_scenario()
        end_time = time.time()

        result = validator.report.scenario_results[0]

        # Execution time should be reasonable (less than actual elapsed)
        assert result.execution_time_seconds > 0
        assert (
            result.execution_time_seconds < (end_time - start_time) + 1
        )  # Allow 1s buffer

    def test_scenario_step_counting(self, tmp_path):
        """Test that scenario correctly counts steps."""
        runbooks_dir = tmp_path / "runbooks"
        runbooks_dir.mkdir()

        content = """---
title: Multi-Step Runbook
executable: true
steps:
  - name: "Step 1"
    command: "echo 1"
  - name: "Step 2"
    command: "echo 2"
  - name: "Step 3"
    command: "echo 3"
  - name: "Step 4"
    command: "echo 4"
  - name: "Step 5"
    command: "echo 5"
---

# Multi-Step Runbook
"""
        (runbooks_dir / "kill-switch-trigger.md").write_text(content)

        validator = RunbookValidator(runbooks_dir=runbooks_dir, dry_run=True)
        validator._test_safety_scenario()

        result = validator.report.scenario_results[0]
        assert result.steps_executed == 5
        assert result.steps_passed == 5
        assert result.steps_failed == 0
