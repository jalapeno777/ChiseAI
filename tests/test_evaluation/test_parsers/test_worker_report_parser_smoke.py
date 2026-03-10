"""
Smoke tests for WorkerReportParser.

# SAFETY: No risk cap logic modified
# SAFETY: No promotion gate logic modified
# SAFETY: No live trading flow modified
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.evaluation import IssueCategory, IssueSource
from src.evaluation.parsers import WorkerReportParser


class TestWorkerReportParserSmoke:
    """Smoke tests for WorkerReportParser class."""

    def test_module_imports_successfully(self):
        """Test that the parser module can be imported."""
        from src.evaluation.parsers.worker_report_parser import WorkerReportParser

        assert WorkerReportParser is not None

    def test_parser_class_instantiates_with_defaults(self):
        """Test that parser can be instantiated with default parameters."""
        parser = WorkerReportParser()

        assert parser is not None
        assert parser.base_path == Path("docs/tempmemories")

    def test_parser_class_instantiates_with_custom_path(self):
        """Test that parser can be instantiated with custom base path."""
        custom_path = "/custom/path"
        parser = WorkerReportParser(base_path=custom_path)

        assert parser is not None
        assert parser.base_path == Path(custom_path)

    def test_parse_text_with_empty_string(self):
        """Test parsing empty text returns empty list."""
        parser = WorkerReportParser()
        issues = parser.parse_text("")

        assert isinstance(issues, list)
        assert len(issues) == 0

    def test_parse_text_with_no_issues(self):
        """Test parsing text with no issue markers returns empty list."""
        parser = WorkerReportParser()
        text = """
This is a normal worker report.
Everything went fine today.
Completed all tasks successfully.
"""
        issues = parser.parse_text(text)

        assert isinstance(issues, list)
        assert len(issues) == 0

    def test_parse_text_with_blocker_marker(self):
        """Test parsing text with blocker marker detects issue."""
        parser = WorkerReportParser()
        text = """
Completed some tasks today.
blocker: Unable to connect to Redis server
More work was done.
"""
        issues = parser.parse_text(text)

        assert isinstance(issues, list)
        assert len(issues) == 1
        # Blocker with Redis connection refused categorizes as DB_CONNECTIVITY
        assert issues[0].source == IssueSource.WORKER_REPORT
        assert "Redis" in issues[0].raw_text

    def test_parse_text_with_error_marker(self):
        """Test parsing text with error marker detects issue."""
        parser = WorkerReportParser()
        text = """
Started work on feature.
error: ModuleNotFoundError when importing test module
Continuing with other tasks.
"""
        issues = parser.parse_text(text)

        assert isinstance(issues, list)
        assert len(issues) == 1
        assert issues[0].category == IssueCategory.TOOL_ERROR
        assert "ModuleNotFoundError" in issues[0].raw_text

    def test_parse_text_with_permission_denied(self):
        """Test parsing text with permission denied detects file access issue."""
        parser = WorkerReportParser()
        text = """
Working on file operations.
error: permission denied when writing to /tmp/test.txt
Completed other tasks.
"""
        issues = parser.parse_text(text)

        assert isinstance(issues, list)
        assert len(issues) == 1
        assert issues[0].category == IssueCategory.FILE_ACCESS
        assert "permission" in issues[0].raw_text.lower()

    def test_parse_text_with_timeout(self):
        """Test parsing text with timeout detects slowdown issue."""
        parser = WorkerReportParser()
        text = """
Running database queries.
timeout: Query took too long to complete
Moving to next task.
"""
        issues = parser.parse_text(text)

        assert isinstance(issues, list)
        assert len(issues) == 1
        assert issues[0].category == IssueCategory.ENV_SLOWDOWN
        assert "timeout" in issues[0].raw_text.lower()

    def test_parse_text_with_multiple_issues(self):
        """Test parsing text with multiple issues."""
        parser = WorkerReportParser()
        text = """
Started work.
error: Something went wrong
blocker: Redis connection failed
warning: Permission denied accessing file
All done.
"""
        issues = parser.parse_text(text)

        assert isinstance(issues, list)
        assert len(issues) == 3

    def test_parse_text_with_custom_timestamp(self):
        """Test parsing text with custom timestamp."""
        parser = WorkerReportParser()
        custom_time = datetime(2024, 1, 15, 10, 30, 0)
        text = "error: Test error occurred"

        issues = parser.parse_text(text, timestamp=custom_time)

        assert len(issues) == 1
        assert issues[0].timestamp == custom_time

    def test_extract_story_id_from_content(self):
        """Test extracting story_id from content."""
        parser = WorkerReportParser()
        text = """
story_id: ST-12345
Completed work on this story.
error: Something failed
"""
        issues = parser.parse_text(text)

        assert len(issues) == 1
        assert issues[0].story_id == "ST-12345"

    def test_extract_story_id_alternative_format(self):
        """Test extracting story_id with different format."""
        parser = WorkerReportParser()
        text = """
Story: CH-987
Work report
error: Issue found
"""
        issues = parser.parse_text(text)

        assert len(issues) == 1
        assert issues[0].story_id == "CH-987"

    def test_categorize_issue_file_access(self):
        """Test categorization of file access issues."""
        parser = WorkerReportParser()

        category = parser._categorize_issue("permission denied when accessing file")
        assert category == IssueCategory.FILE_ACCESS

        category = parser._categorize_issue("file not found error")
        assert category == IssueCategory.FILE_ACCESS

    def test_categorize_issue_database(self):
        """Test categorization of database issues."""
        parser = WorkerReportParser()

        category = parser._categorize_issue("redis error occurred")
        assert category == IssueCategory.DB_CONNECTIVITY

        category = parser._categorize_issue("postgres connection refused")
        assert category == IssueCategory.DB_CONNECTIVITY

    def test_categorize_issue_slowdown(self):
        """Test categorization of slowdown issues."""
        parser = WorkerReportParser()

        category = parser._categorize_issue("slow response from api")
        assert category == IssueCategory.ENV_SLOWDOWN

        category = parser._categorize_issue("timeout while waiting")
        assert category == IssueCategory.ENV_SLOWDOWN

    def test_categorize_issue_default(self):
        """Test default categorization for unknown issues."""
        parser = WorkerReportParser()

        category = parser._categorize_issue("generic error message")
        assert category == IssueCategory.TOOL_ERROR

    @patch("pathlib.Path.exists")
    def test_parse_file_nonexistent(self, mock_exists):
        """Test parsing non-existent file returns empty list."""
        mock_exists.return_value = False
        parser = WorkerReportParser()

        result = parser.parse_file(Path("/fake/path.md"))

        assert result == []

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_text")
    @patch("pathlib.Path.stat")
    def test_parse_file_with_issues(self, mock_stat, mock_read_text, mock_exists):
        """Test parsing file with issues."""
        mock_exists.return_value = True
        mock_read_text.return_value = "error: Test error in file\nblocker: Redis down"
        mock_stat.return_value = MagicMock(st_mtime=datetime.now().timestamp())

        parser = WorkerReportParser()
        result = parser.parse_file(Path("/fake/worker-report.md"))

        assert len(result) == 2
        assert all(issue.source == IssueSource.WORKER_REPORT for issue in result)

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.glob")
    def test_parse_all_empty_directory(self, mock_glob, mock_exists):
        """Test parse_all with empty directory."""
        mock_exists.return_value = True
        mock_glob.return_value = []

        parser = WorkerReportParser()
        result = parser.parse_all()

        assert result == []

    def test_detect_issues_in_line_empty(self):
        """Test detecting issues in empty line."""
        parser = WorkerReportParser()

        result = parser._detect_issues_in_line("")
        assert result == []

        result = parser._detect_issues_in_line("   ")
        assert result == []

    def test_issue_markers_defined(self):
        """Test that issue markers are defined."""
        parser = WorkerReportParser()

        assert len(parser.ISSUE_MARKERS) > 0
        assert "blocker:" in parser.ISSUE_MARKERS
        assert "error:" in parser.ISSUE_MARKERS

    def test_status_patterns_defined(self):
        """Test that status patterns are defined."""
        parser = WorkerReportParser()

        assert len(parser.STATUS_PATTERNS) > 0
        assert "failed" in parser.STATUS_PATTERNS
        assert "error" in parser.STATUS_PATTERNS

    def test_file_access_patterns_defined(self):
        """Test that file access patterns are defined."""
        parser = WorkerReportParser()

        assert len(parser.FILE_ACCESS_PATTERNS) > 0
        assert any("permission" in p for p in parser.FILE_ACCESS_PATTERNS)

    def test_db_patterns_defined(self):
        """Test that database patterns are defined."""
        parser = WorkerReportParser()

        assert len(parser.DB_PATTERNS) > 0
        assert any("redis" in p for p in parser.DB_PATTERNS)
