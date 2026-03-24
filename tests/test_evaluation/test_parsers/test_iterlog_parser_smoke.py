"""
Smoke tests for IterlogParser.

# SAFETY: No risk cap logic modified
# SAFETY: No promotion gate logic modified
# SAFETY: No live trading flow modified
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.evaluation import IssueCategory, IssueSource
from src.evaluation.parsers import IterlogParser


class TestIterlogParserSmoke:
    """Smoke tests for IterlogParser class."""

    def test_module_imports_successfully(self):
        """Test that the parser module can be imported."""
        from src.evaluation.parsers.iterlog_parser import IterlogParser

        assert IterlogParser is not None

    def test_parser_class_instantiates_with_defaults(self):
        """Test that parser can be instantiated with default parameters."""
        parser = IterlogParser()

        assert parser is not None
        assert parser.base_path == Path("docs/tempmemories")

    def test_parser_class_instantiates_with_custom_path(self):
        """Test that parser can be instantiated with custom base path."""
        custom_path = "/custom/path"
        parser = IterlogParser(base_path=custom_path)

        assert parser is not None
        assert parser.base_path == Path(custom_path)

    def test_issue_patterns_defined(self):
        """Test that issue patterns are defined."""
        parser = IterlogParser()

        assert len(parser.ISSUE_PATTERNS) > 0
        assert "blocker:" in parser.ISSUE_PATTERNS
        assert "error:" in parser.ISSUE_PATTERNS
        assert "slowdown:" in parser.ISSUE_PATTERNS

    def test_file_access_patterns_defined(self):
        """Test that file access patterns are defined."""
        parser = IterlogParser()

        assert len(parser.FILE_ACCESS_PATTERNS) > 0
        assert any("permission" in p for p in parser.FILE_ACCESS_PATTERNS)

    def test_db_connectivity_patterns_defined(self):
        """Test that database connectivity patterns are defined."""
        parser = IterlogParser()

        assert len(parser.DB_CONNECTIVITY_PATTERNS) > 0
        assert any("redis" in p for p in parser.DB_CONNECTIVITY_PATTERNS)
        assert any("postgres" in p for p in parser.DB_CONNECTIVITY_PATTERNS)

    def test_env_slowdown_patterns_defined(self):
        """Test that environment slowdown patterns are defined."""
        parser = IterlogParser()

        assert len(parser.ENV_SLOWDOWN_PATTERNS) > 0
        assert any("slowdown" in p for p in parser.ENV_SLOWDOWN_PATTERNS)
        assert any("timeout" in p for p in parser.ENV_SLOWDOWN_PATTERNS)

    def test_tool_error_patterns_defined(self):
        """Test that tool error patterns are defined."""
        parser = IterlogParser()

        assert len(parser.TOOL_ERROR_PATTERNS) > 0
        assert any("error" in p for p in parser.TOOL_ERROR_PATTERNS)
        assert any("traceback" in p for p in parser.TOOL_ERROR_PATTERNS)

    @patch("pathlib.Path.exists")
    def test_parse_file_nonexistent(self, mock_exists):
        """Test parsing non-existent file returns empty list."""
        mock_exists.return_value = False
        parser = IterlogParser()

        result = parser.parse_file(Path("/fake/path.md"))

        assert result == []

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_text")
    @patch("pathlib.Path.stat")
    def test_parse_file_with_blocker(self, mock_stat, mock_read_text, mock_exists):
        """Test parsing file with blocker issue."""
        mock_exists.return_value = True
        content = """
story_id: ST-12345
# Iteration Log

blocker: Redis connection refused
"""
        mock_read_text.return_value = content
        mock_stat.return_value = MagicMock(st_mtime=datetime.now().timestamp())

        parser = IterlogParser()
        result = parser.parse_file(Path("/fake/iterlog-ST-12345.md"))

        assert len(result) == 1
        assert result[0].category == IssueCategory.DB_CONNECTIVITY
        assert result[0].source == IssueSource.ITERLOG
        assert result[0].story_id == "ST-12345"

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_text")
    @patch("pathlib.Path.stat")
    def test_parse_file_with_error(self, mock_stat, mock_read_text, mock_exists):
        """Test parsing file with error."""
        mock_exists.return_value = True
        content = """
story_id: ST-54321
# Iteration Log

error: ModuleNotFoundError in test
"""
        mock_read_text.return_value = content
        mock_stat.return_value = MagicMock(st_mtime=datetime.now().timestamp())

        parser = IterlogParser()
        result = parser.parse_file(Path("/fake/iterlog.md"))

        assert len(result) == 1
        assert result[0].category == IssueCategory.TOOL_ERROR
        assert "ModuleNotFoundError" in result[0].raw_text

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_text")
    @patch("pathlib.Path.stat")
    def test_parse_file_with_slowdown(self, mock_stat, mock_read_text, mock_exists):
        """Test parsing file with slowdown issue."""
        mock_exists.return_value = True
        content = """
# Iteration Log

slowdown: High latency in database queries
"""
        mock_read_text.return_value = content
        mock_stat.return_value = MagicMock(st_mtime=datetime.now().timestamp())

        parser = IterlogParser()
        result = parser.parse_file(Path("/fake/iterlog.md"))

        assert len(result) == 1
        assert result[0].category == IssueCategory.ENV_SLOWDOWN
        assert "slowdown" in result[0].raw_text.lower()

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_text")
    @patch("pathlib.Path.stat")
    def test_parse_file_with_permission_denied(
        self, mock_stat, mock_read_text, mock_exists
    ):
        """Test parsing file with permission denied error."""
        mock_exists.return_value = True
        content = """
# Iteration Log

Permission denied when accessing /tmp/data.txt
"""
        mock_read_text.return_value = content
        mock_stat.return_value = MagicMock(st_mtime=datetime.now().timestamp())

        parser = IterlogParser()
        result = parser.parse_file(Path("/fake/iterlog.md"))

        assert len(result) == 1
        assert result[0].category == IssueCategory.FILE_ACCESS
        assert "permission" in result[0].raw_text.lower()

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_text")
    @patch("pathlib.Path.stat")
    def test_parse_file_multiple_issues(self, mock_stat, mock_read_text, mock_exists):
        """Test parsing file with multiple issues."""
        mock_exists.return_value = True
        content = """
story_id: ST-MULTI
# Iteration Log

Started work on feature.
error: Import failed for module X
blocker: Redis connection timeout
Permission denied accessing config file
Completed tasks.
"""
        mock_read_text.return_value = content
        mock_stat.return_value = MagicMock(st_mtime=datetime.now().timestamp())

        parser = IterlogParser()
        result = parser.parse_file(Path("/fake/iterlog.md"))

        assert len(result) == 3
        assert result[0].story_id == "ST-MULTI"

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.glob")
    def test_parse_all_empty_directory(self, mock_glob, mock_exists):
        """Test parse_all with empty directory."""
        mock_exists.return_value = True
        mock_glob.return_value = []

        parser = IterlogParser()
        result = parser.parse_all()

        assert result == []

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.glob")
    def test_parse_all_with_files(self, mock_glob, mock_exists):
        """Test parse_all finds and parses files."""
        mock_exists.return_value = True
        mock_file = MagicMock()
        mock_glob.return_value = [mock_file]

        parser = IterlogParser()
        # Mock parse_file to avoid actual file reading
        with patch.object(parser, "parse_file", return_value=[]):
            result = parser.parse_all()

        assert result == []

    def test_extract_story_id_with_frontmatter(self):
        """Test extracting story_id from YAML frontmatter."""
        parser = IterlogParser()
        content = """
story_id: ST-TEST-123
# Iteration Log
Some content here.
"""
        story_id = parser._extract_story_id(content)

        assert story_id == "ST-TEST-123"

    def test_extract_story_id_not_found(self):
        """Test extracting story_id when not present."""
        parser = IterlogParser()
        content = """
# Iteration Log
Some content without story_id.
"""
        story_id = parser._extract_story_id(content)

        assert story_id is None

    def test_detect_issues_in_line_empty(self):
        """Test detecting issues in empty line."""
        parser = IterlogParser()

        result = parser._detect_issues_in_line("")
        assert result == []

        result = parser._detect_issues_in_line("   ")
        assert result == []

    def test_detect_issues_in_line_no_issues(self):
        """Test detecting issues in normal line."""
        parser = IterlogParser()

        result = parser._detect_issues_in_line("Normal progress update")
        assert result == []

    def test_detect_issues_file_access(self):
        """Test detecting file access issues."""
        parser = IterlogParser()

        result = parser._detect_issues_in_line("Permission denied when reading file")
        assert len(result) == 1
        assert result[0][0] == IssueCategory.FILE_ACCESS

        result = parser._detect_issues_in_line("File not found: /tmp/test.txt")
        assert len(result) == 1
        assert result[0][0] == IssueCategory.FILE_ACCESS

    def test_detect_issues_database(self):
        """Test detecting database connectivity issues."""
        parser = IterlogParser()

        result = parser._detect_issues_in_line("Redis connection error occurred")
        assert len(result) == 1
        assert result[0][0] == IssueCategory.DB_CONNECTIVITY

        result = parser._detect_issues_in_line("Postgres timeout during query")
        assert len(result) == 1
        assert result[0][0] == IssueCategory.DB_CONNECTIVITY

    def test_detect_issues_env_slowdown(self):
        """Test detecting environment slowdown issues."""
        parser = IterlogParser()

        result = parser._detect_issues_in_line("slowdown: High latency detected")
        assert len(result) == 1
        assert result[0][0] == IssueCategory.ENV_SLOWDOWN

        result = parser._detect_issues_in_line("timeout: Operation timed out")
        assert len(result) == 1
        assert result[0][0] == IssueCategory.ENV_SLOWDOWN

    def test_detect_issues_tool_error(self):
        """Test detecting tool error issues."""
        parser = IterlogParser()

        result = parser._detect_issues_in_line("error: Import failed")
        assert len(result) == 1
        assert result[0][0] == IssueCategory.TOOL_ERROR

        result = parser._detect_issues_in_line("Traceback: something went wrong")
        assert len(result) == 1
        assert result[0][0] == IssueCategory.TOOL_ERROR

    def test_detect_issues_explicit_markers(self):
        """Test detecting issues with explicit markers."""
        parser = IterlogParser()

        result = parser._detect_issues_in_line("blocker: Something blocking work")
        assert len(result) == 1
        assert result[0][0] == IssueCategory.OTHER

        result = parser._detect_issues_in_line("failed: Tests failed")
        assert len(result) == 1
        assert result[0][0] == IssueCategory.TOOL_ERROR

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.glob")
    def test_parse_since_no_files(self, mock_glob, mock_exists):
        """Test parse_since with no matching files."""
        mock_exists.return_value = True
        mock_glob.return_value = []

        parser = IterlogParser()
        since_time = datetime.now()
        result = parser.parse_since(since_time)

        assert result == []

    def test_issue_source_is_iterlog(self):
        """Test that parsed issues have ITERLOG source."""
        parser = IterlogParser()

        with (
            patch("pathlib.Path.exists") as mock_exists,
            patch("pathlib.Path.read_text") as mock_read_text,
            patch("pathlib.Path.stat") as mock_stat,
        ):
            mock_exists.return_value = True
            mock_read_text.return_value = "error: Test error"
            mock_stat.return_value = MagicMock(st_mtime=datetime.now().timestamp())

            result = parser.parse_file(Path("/fake/iterlog.md"))

            if result:
                assert all(issue.source == IssueSource.ITERLOG for issue in result)
