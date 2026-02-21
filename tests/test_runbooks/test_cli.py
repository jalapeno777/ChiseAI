"""
Tests for the runbook CLI module.
"""

from pathlib import Path
from unittest.mock import Mock, patch
import argparse

from runbooks.cli import cmd_list, cmd_execute, cmd_show, cmd_history, main


class TestCmdList:
    """Tests for the list command."""

    def test_list_empty_runbooks(self, capsys):
        """Test listing when no runbooks exist."""
        with patch("runbooks.cli.RunbookParser") as mock_parser_class:
            mock_parser = Mock()
            mock_parser.list_runbooks.return_value = []
            mock_parser_class.return_value = mock_parser

            args = argparse.Namespace()
            result = cmd_list(args)

            assert result == 1
            captured = capsys.readouterr()
            assert "No runbooks found" in captured.out

    def test_list_runbooks(self, capsys):
        """Test listing runbooks."""
        with patch("runbooks.cli.RunbookParser") as mock_parser_class:
            mock_parser = Mock()
            mock_parser.list_runbooks.return_value = ["test1", "test2"]

            # Mock parsed runbook
            mock_runbook = Mock()
            mock_runbook.is_executable = True
            mock_runbook.metadata.category = "test"
            mock_runbook.metadata.severity = "standard"
            mock_parser.parse.return_value = mock_runbook

            mock_parser_class.return_value = mock_parser

            args = argparse.Namespace()
            result = cmd_list(args)

            assert result == 0
            captured = capsys.readouterr()
            assert "test1" in captured.out
            assert "test2" in captured.out


class TestCmdExecute:
    """Tests for the execute command."""

    def test_execute_runbook_success(self):
        """Test executing a runbook successfully."""
        with patch("runbooks.cli.RunbookExecutor") as mock_executor_class:
            mock_executor = Mock()
            mock_result = Mock()
            mock_result.success = True
            mock_result.to_json.return_value = '{"success": true}'
            mock_executor.execute.return_value = mock_result
            mock_executor_class.return_value = mock_executor

            args = argparse.Namespace(runbook_name="test", dry_run=False, json=False)
            result = cmd_execute(args)

            assert result == 0
            mock_executor.execute.assert_called_once_with("test", dry_run=False)

    def test_execute_runbook_failure(self):
        """Test executing a runbook that fails."""
        with patch("runbooks.cli.RunbookExecutor") as mock_executor_class:
            mock_executor = Mock()
            mock_result = Mock()
            mock_result.success = False
            mock_result.to_json.return_value = '{"success": false}'
            mock_executor.execute.return_value = mock_result
            mock_executor_class.return_value = mock_executor

            args = argparse.Namespace(runbook_name="test", dry_run=False, json=False)
            result = cmd_execute(args)

            assert result == 1


class TestCmdShow:
    """Tests for the show command."""

    def test_show_runbook(self, capsys):
        """Test showing runbook details."""
        with patch("runbooks.cli.RunbookParser") as mock_parser_class:
            mock_parser = Mock()
            mock_runbook = Mock()
            mock_runbook.name = "test"
            mock_runbook.path = Path("/test.md")
            mock_runbook.metadata.title = "Test Runbook"
            mock_runbook.metadata.category = "test"
            mock_runbook.metadata.severity = "standard"
            mock_runbook.is_executable = True
            mock_runbook.metadata.story_id = "ST-001"
            mock_runbook.metadata.maintainers = ["alice"]
            mock_runbook.metadata.estimated_time = "10 minutes"
            mock_runbook.steps = []
            mock_parser.parse.return_value = mock_runbook
            mock_parser_class.return_value = mock_parser

            args = argparse.Namespace(runbook_name="test")
            result = cmd_show(args)

            assert result == 0
            captured = capsys.readouterr()
            assert "Test Runbook" in captured.out
            assert "test" in captured.out

    def test_show_nonexistent_runbook(self, capsys):
        """Test showing a runbook that doesn't exist."""
        with patch("runbooks.cli.RunbookParser") as mock_parser_class:
            mock_parser = Mock()
            mock_parser.parse.side_effect = FileNotFoundError()
            mock_parser_class.return_value = mock_parser

            args = argparse.Namespace(runbook_name="nonexistent")
            result = cmd_show(args)

            assert result == 1
            captured = capsys.readouterr()
            assert "not found" in captured.err


class TestCmdHistory:
    """Tests for the history command."""

    def test_history_empty(self, capsys):
        """Test history when no logs exist."""
        with patch("runbooks.cli.RunbookExecutor") as mock_executor_class:
            mock_executor = Mock()
            mock_executor.get_execution_history.return_value = []
            mock_executor.log_dir = Path("/logs")
            mock_executor_class.return_value = mock_executor

            args = argparse.Namespace(runbook_name=None, limit=10)
            result = cmd_history(args)

            assert result == 0
            captured = capsys.readouterr()
            assert "No execution history" in captured.out

    def test_history_with_logs(self, capsys, tmp_path):
        """Test history with log files."""
        with patch("runbooks.cli.RunbookExecutor") as mock_executor_class:
            mock_executor = Mock()

            # Create mock log files
            log_file = tmp_path / "test_20240101_120000.json"
            log_file.write_text(
                '{"execution": {"runbook_name": "test", "success": true, "start_time": "2024-01-01T12:00:00Z", "execution_time_seconds": 5.0}}'
            )

            mock_executor.get_execution_history.return_value = [log_file]
            mock_executor.log_dir = tmp_path
            mock_executor_class.return_value = mock_executor

            args = argparse.Namespace(runbook_name=None, limit=10)
            result = cmd_history(args)

            assert result == 0
            captured = capsys.readouterr()
            assert "test" in captured.out


class TestMain:
    """Tests for the main entry point."""

    def test_main_no_command(self, capsys):
        """Test main with no command."""
        result = main([])
        assert result == 1

    def test_main_list_command(self):
        """Test main with list command."""
        with patch("runbooks.cli.cmd_list") as mock_list:
            mock_list.return_value = 0
            result = main(["list"])
            assert result == 0
            mock_list.assert_called_once()

    def test_main_execute_command(self):
        """Test main with execute command."""
        with patch("runbooks.cli.cmd_execute") as mock_execute:
            mock_execute.return_value = 0
            result = main(["execute", "test"])
            assert result == 0
            mock_execute.assert_called_once()

    def test_main_show_command(self):
        """Test main with show command."""
        with patch("runbooks.cli.cmd_show") as mock_show:
            mock_show.return_value = 0
            result = main(["show", "test"])
            assert result == 0
            mock_show.assert_called_once()

    def test_main_history_command(self):
        """Test main with history command."""
        with patch("runbooks.cli.cmd_history") as mock_history:
            mock_history.return_value = 0
            result = main(["history"])
            assert result == 0
            mock_history.assert_called_once()
