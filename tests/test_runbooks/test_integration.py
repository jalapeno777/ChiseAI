"""
Integration tests for the runbook executor framework.
"""

import json

from runbooks.executor import RunbookExecutor
from runbooks.parser import RunbookParser


class TestRunbookIntegration:
    """Integration tests for the complete runbook system."""

    def test_end_to_end_execution(self, tmp_path):
        """Test end-to-end runbook execution."""
        # Setup directories
        runbooks_dir = tmp_path / "runbooks"
        scripts_dir = tmp_path / "scripts"
        log_dir = tmp_path / "logs"
        runbooks_dir.mkdir()
        scripts_dir.mkdir()

        # Create a test runbook
        content = """---
title: Integration Test
category: test
executable: true
steps:
  - name: Echo Test
    command: echo integration test
  - name: Success Test
    command: "true"
---

# Integration Test

This is an integration test runbook.
"""
        (runbooks_dir / "integration.md").write_text(content)

        # Execute the runbook
        executor = RunbookExecutor(
            runbooks_dir=runbooks_dir,
            scripts_dir=scripts_dir,
            log_dir=log_dir,
            dry_run=False,
        )

        result = executor.execute("integration")

        # Verify results
        assert result.success is True
        assert result.runbook_name == "integration"
        assert result.total_steps == 2
        assert result.passed_steps == 2
        assert result.failed_steps == 0
        assert result.log_file is not None
        assert result.log_file.exists()

        # Verify log file content
        log_data = json.loads(result.log_file.read_text())
        assert log_data["execution"]["runbook_name"] == "integration"
        assert log_data["execution"]["success"] is True

    def test_dry_run_execution(self, tmp_path):
        """Test dry-run execution doesn't actually run commands."""
        runbooks_dir = tmp_path / "runbooks"
        runbooks_dir.mkdir()

        # Create a runbook that would fail if actually executed
        content = """---
title: Dry Run Test
executable: true
steps:
  - name: "Would Fail"
    command: "exit 1"
---
"""
        (runbooks_dir / "dryrun.md").write_text(content)

        executor = RunbookExecutor(runbooks_dir=runbooks_dir, dry_run=True)

        result = executor.execute("dryrun")

        # In dry-run mode, even failing commands appear successful
        assert result.dry_run is True
        assert result.success is True

    def test_execution_with_script_step(self, tmp_path):
        """Test execution with a script step."""
        runbooks_dir = tmp_path / "runbooks"
        scripts_dir = tmp_path / "scripts"
        runbooks_dir.mkdir()
        scripts_dir.mkdir()

        # Create a test script
        script_file = scripts_dir / "test_script.sh"
        script_file.write_text("#!/bin/bash\necho 'script output'")
        script_file.chmod(0o755)

        # Create a runbook referencing the script
        content = """---
title: Script Test
executable: true
steps:
  - name: "Run Script"
    script: "test_script.sh"
---
"""
        (runbooks_dir / "script_test.md").write_text(content)

        executor = RunbookExecutor(
            runbooks_dir=runbooks_dir, scripts_dir=scripts_dir, dry_run=False
        )

        result = executor.execute("script_test")

        assert result.success is True
        assert result.total_steps == 1
        assert result.passed_steps == 1

    def test_parser_and_executor_integration(self, tmp_path):
        """Test parser and executor working together."""
        runbooks_dir = tmp_path / "runbooks"
        runbooks_dir.mkdir()

        # Create runbook with complex frontmatter
        content = """---
title: Complex Test
category: operations
severity: critical
executable: true
estimated_time_to_resolve: 5 minutes
maintainers: alice, bob
story_id: ST-TEST-001
steps:
  - name: Step One
    command: echo step one
    description: First step
    timeout: 30
  - name: Step Two
    command: echo step two
    verify: step two
---

# Complex Test

This is a complex test runbook.
"""
        (runbooks_dir / "complex.md").write_text(content)

        # Parse with parser
        parser = RunbookParser(runbooks_dir)
        runbook = parser.parse("complex")

        assert runbook.name == "complex"
        assert runbook.metadata.title == "Complex Test"
        assert runbook.metadata.category == "operations"
        assert runbook.metadata.severity == "critical"
        assert runbook.metadata.story_id == "ST-TEST-001"
        assert len(runbook.metadata.maintainers) == 2
        assert len(runbook.steps) == 2

        # Execute with executor
        executor = RunbookExecutor(runbooks_dir=runbooks_dir)
        result = executor.execute("complex")

        assert result.success is True
        assert result.total_steps == 2

    def test_execution_failure_handling(self, tmp_path):
        """Test that execution stops on first failure."""
        runbooks_dir = tmp_path / "runbooks"
        runbooks_dir.mkdir()

        content = """---
title: Failure Test
executable: true
steps:
  - name: Success Step
    command: echo success
  - name: Fail Step
    command: exit 1
  - name: Never Runs
    command: echo never seen
---
"""
        (runbooks_dir / "failure.md").write_text(content)

        executor = RunbookExecutor(runbooks_dir=runbooks_dir, dry_run=False)
        result = executor.execute("failure")

        assert result.success is False
        assert result.failed_steps == 1
        # Third step should not have run
        # Note: total_steps counts all executable steps found, not just executed
        assert result.total_steps == 3

    def test_execution_history(self, tmp_path):
        """Test execution history tracking."""
        runbooks_dir = tmp_path / "runbooks"
        log_dir = tmp_path / "logs"
        runbooks_dir.mkdir()

        content = """---
title: History Test
executable: true
steps:
  - name: "Test"
    command: "true"
---
"""
        (runbooks_dir / "history.md").write_text(content)

        executor = RunbookExecutor(runbooks_dir=runbooks_dir, log_dir=log_dir)

        # Execute multiple times
        executor.execute("history")
        executor.execute("history")
        executor.execute("history")

        # Check history
        history = executor.get_execution_history(runbook_name="history")
        assert len(history) == 3

        # Check all history
        all_history = executor.get_execution_history()
        assert len(all_history) == 3

    def test_list_and_execute_workflow(self, tmp_path):
        """Test the list → execute workflow."""
        runbooks_dir = tmp_path / "runbooks"
        runbooks_dir.mkdir()

        # Create multiple runbooks
        for name in ["runbook_a", "runbook_b", "runbook_c"]:
            content = f"""---
title: {name.title()}
executable: true
steps:
  - name: Test
    command: echo {name}
---
"""
            (runbooks_dir / f"{name}.md").write_text(content)

        # List runbooks
        parser = RunbookParser(runbooks_dir)
        runbooks = parser.list_runbooks()

        assert len(runbooks) == 3
        assert "runbook_a" in runbooks
        assert "runbook_b" in runbooks
        assert "runbook_c" in runbooks

        # Execute each
        executor = RunbookExecutor(runbooks_dir=runbooks_dir)
        for name in runbooks:
            result = executor.execute(name)
            assert result.success is True
