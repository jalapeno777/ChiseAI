"""
Tests for the runbook executor module.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from runbooks.executor import ExecutionResult, RunbookExecutor, StepResult
from runbooks.parser import RunbookStep


class TestStepResult:
    """Tests for StepResult class."""

    def test_step_result_creation(self):
        """Test creating a StepResult."""
        result = StepResult(
            step_name="Test Step",
            success=True,
            return_code=0,
            stdout="output",
            stderr="",
            execution_time_ms=100.0,
        )

        assert result.step_name == "Test Step"
        assert result.success is True
        assert result.return_code == 0
        assert result.stdout == "output"
        assert result.execution_time_ms == 100.0

    def test_step_result_to_dict(self):
        """Test converting StepResult to dictionary."""
        result = StepResult(
            step_name="Test Step",
            success=True,
            return_code=0,
            stdout="output",
            stderr="",
            execution_time_ms=100.0,
            error_message=None,
        )

        d = result.to_dict()
        assert d["step_name"] == "Test Step"
        assert d["success"] is True
        assert d["return_code"] == 0
        assert "timestamp" in d


class TestExecutionResult:
    """Tests for ExecutionResult class."""

    def test_execution_result_creation(self):
        """Test creating an ExecutionResult."""
        start = datetime.now(UTC)
        end = datetime.now(UTC)

        result = ExecutionResult(
            runbook_name="test",
            success=True,
            dry_run=False,
            steps=[],
            start_time=start,
            end_time=end,
            total_steps=0,
            passed_steps=0,
            failed_steps=0,
        )

        assert result.runbook_name == "test"
        assert result.success is True
        assert result.execution_time_seconds >= 0

    def test_execution_result_to_dict(self):
        """Test converting ExecutionResult to dictionary."""
        start = datetime.now(UTC)
        end = datetime.now(UTC)

        result = ExecutionResult(
            runbook_name="test",
            success=True,
            dry_run=False,
            steps=[],
            start_time=start,
            end_time=end,
            total_steps=0,
            passed_steps=0,
            failed_steps=0,
            log_file=Path("/tmp/test.json"),
        )

        d = result.to_dict()
        assert d["runbook_name"] == "test"
        assert d["success"] is True
        assert d["log_file"] == "/tmp/test.json"

    def test_execution_result_to_json(self):
        """Test converting ExecutionResult to JSON."""
        start = datetime.now(UTC)
        end = datetime.now(UTC)

        result = ExecutionResult(
            runbook_name="test",
            success=True,
            dry_run=False,
            steps=[],
            start_time=start,
            end_time=end,
            total_steps=0,
            passed_steps=0,
            failed_steps=0,
        )

        json_str = result.to_json()
        assert "test" in json_str
        assert "success" in json_str

        # Should be valid JSON
        parsed = json.loads(json_str)
        assert parsed["runbook_name"] == "test"


class TestRunbookExecutor:
    """Tests for RunbookExecutor class."""

    def test_init_with_defaults(self, tmp_path):
        """Test executor initialization with default paths."""
        with patch("runbooks.executor.RunbookExecutor._find_repo_root") as mock_root:
            mock_root.return_value = tmp_path
            executor = RunbookExecutor()

            assert executor.dry_run is False
            assert executor.log_dir is not None

    def test_init_with_custom_paths(self, tmp_path):
        """Test executor initialization with custom paths."""
        runbooks_dir = tmp_path / "runbooks"
        scripts_dir = tmp_path / "scripts"
        log_dir = tmp_path / "logs"

        runbooks_dir.mkdir()
        scripts_dir.mkdir()

        executor = RunbookExecutor(
            runbooks_dir=runbooks_dir,
            scripts_dir=scripts_dir,
            log_dir=log_dir,
            dry_run=True,
        )

        assert executor.dry_run is True
        assert executor.log_dir == log_dir
        assert log_dir.exists()

    def test_list_runbooks(self, tmp_path):
        """Test listing runbooks through executor."""
        runbooks_dir = tmp_path / "runbooks"
        runbooks_dir.mkdir()
        (runbooks_dir / "test.md").write_text("# Test")

        executor = RunbookExecutor(runbooks_dir=runbooks_dir)
        runbooks = executor.list_runbooks()

        assert "test" in runbooks

    def test_execute_nonexistent_runbook(self, tmp_path):
        """Test executing a runbook that doesn't exist."""
        runbooks_dir = tmp_path / "runbooks"
        runbooks_dir.mkdir()

        executor = RunbookExecutor(runbooks_dir=runbooks_dir)
        result = executor.execute("nonexistent")

        assert result.success is False
        assert result.failed_steps == 1

    def test_execute_dry_run(self, tmp_path):
        """Test executing in dry-run mode."""
        runbooks_dir = tmp_path / "runbooks"
        runbooks_dir.mkdir()

        content = """---
title: Test
executable: true
steps:
  - name: "Test Step"
    command: "echo hello"
---

# Test
"""
        (runbooks_dir / "test.md").write_text(content)

        executor = RunbookExecutor(runbooks_dir=runbooks_dir, dry_run=True)
        result = executor.execute("test")

        assert result.dry_run is True
        assert result.total_steps == 1
        # In dry-run, steps are marked as successful
        assert result.passed_steps == 1

    def test_resolve_script_path_absolute(self, tmp_path):
        """Test resolving absolute script path."""
        executor = RunbookExecutor(runbooks_dir=tmp_path)

        abs_path = Path("/absolute/path/to/script.sh")
        resolved = executor._resolve_script_path(str(abs_path))

        assert resolved == abs_path

    def test_resolve_script_path_relative(self, tmp_path):
        """Test resolving relative script path."""
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()

        executor = RunbookExecutor(runbooks_dir=tmp_path, scripts_dir=scripts_dir)

        resolved = executor._resolve_script_path("test.sh")

        assert resolved == scripts_dir / "test.sh"

    def test_resolve_script_path_with_scripts_prefix(self, tmp_path):
        """Test resolving script path starting with scripts/."""
        with patch("runbooks.executor.RunbookExecutor._find_repo_root") as mock_root:
            mock_root.return_value = tmp_path

            scripts_dir = tmp_path / "scripts"
            scripts_dir.mkdir()

            executor = RunbookExecutor(runbooks_dir=tmp_path, scripts_dir=scripts_dir)

            resolved = executor._resolve_script_path("scripts/test.sh")

            assert resolved == tmp_path / "scripts" / "test.sh"

    def test_save_execution_log(self, tmp_path):
        """Test saving execution log."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir()

        start = datetime.now(UTC)
        end = datetime.now(UTC)

        result = ExecutionResult(
            runbook_name="test",
            success=True,
            dry_run=False,
            steps=[],
            start_time=start,
            end_time=end,
            total_steps=0,
            passed_steps=0,
            failed_steps=0,
        )

        executor = RunbookExecutor(runbooks_dir=tmp_path, log_dir=log_dir)
        log_file = executor._save_execution_log(result)

        assert log_file.exists()
        assert log_file.suffix == ".json"

        # Verify content
        data = json.loads(log_file.read_text())
        assert data["execution"]["runbook_name"] == "test"

    def test_get_execution_history(self, tmp_path):
        """Test getting execution history."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir()

        # Create some log files
        (log_dir / "test1_20240101_120000.json").write_text("{}")
        (log_dir / "test2_20240101_130000.json").write_text("{}")
        (log_dir / "other_20240101_140000.json").write_text("{}")

        executor = RunbookExecutor(runbooks_dir=tmp_path, log_dir=log_dir)

        # Get all history
        all_logs = executor.get_execution_history()
        assert len(all_logs) == 3

        # Get filtered history
        test_logs = executor.get_execution_history(runbook_name="test1")
        assert len(test_logs) == 1


class TestRunbookExecutorExecuteStep:
    """Tests for the _execute_step method."""

    def test_execute_step_dry_run(self, tmp_path):
        """Test executing step in dry-run mode."""
        executor = RunbookExecutor(runbooks_dir=tmp_path, dry_run=True)
        step = RunbookStep(name="Test", command="echo hello")

        result = executor._execute_step(step, dry_run=True)

        assert result.success is True
        assert result.return_code == 0
        assert "DRY-RUN" in result.stdout

    def test_execute_step_with_command(self, tmp_path):
        """Test executing step with command."""
        executor = RunbookExecutor(runbooks_dir=tmp_path, dry_run=False)
        step = RunbookStep(name="Test", command="echo 'hello world'")

        result = executor._execute_step(step, dry_run=False)

        assert result.success is True
        assert result.return_code == 0
        assert "hello world" in result.stdout

    def test_execute_step_with_failing_command(self, tmp_path):
        """Test executing step with failing command."""
        executor = RunbookExecutor(runbooks_dir=tmp_path, dry_run=False)
        step = RunbookStep(name="Test", command="exit 1")

        result = executor._execute_step(step, dry_run=False)

        assert result.success is False
        assert result.return_code == 1

    def test_execute_step_with_missing_script(self, tmp_path):
        """Test executing step with missing script."""
        executor = RunbookExecutor(runbooks_dir=tmp_path, dry_run=False)
        step = RunbookStep(name="Test", script="/nonexistent/script.sh")

        result = executor._execute_step(step, dry_run=False)

        assert result.success is False
        assert (
            "not found" in result.error_message.lower()
            or "Script not found" in result.error_message
        )

    def test_execute_step_without_action(self, tmp_path):
        """Test executing step without command or script."""
        executor = RunbookExecutor(runbooks_dir=tmp_path, dry_run=False)
        step = RunbookStep(name="Test")  # No command or script

        result = executor._execute_step(step, dry_run=False)

        assert result.success is False
        assert "No command or script" in result.error_message
