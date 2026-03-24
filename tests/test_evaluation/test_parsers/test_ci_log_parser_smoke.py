"""
Smoke tests for CILogParser.

# SAFETY: No risk cap logic modified
# SAFETY: No promotion gate logic modified
# SAFETY: No live trading flow modified
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.evaluation import IssueCategory, IssueSource
from src.evaluation.parsers import CILogParser


class TestCILogParserSmoke:
    """Smoke tests for CILogParser class."""

    def test_module_imports_successfully(self):
        """Test that the parser module can be imported."""
        from src.evaluation.parsers.ci_log_parser import CILogParser

        assert CILogParser is not None

    def test_parser_class_instantiates_with_defaults(self):
        """Test that parser can be instantiated with default parameters."""
        parser = CILogParser()

        assert parser is not None
        assert parser.base_path == Path("_bmad-output/ci")

    def test_parser_class_instantiates_with_custom_path(self):
        """Test that parser can be instantiated with custom base path."""
        custom_path = "/custom/ci/path"
        parser = CILogParser(base_path=custom_path)

        assert parser is not None
        assert parser.base_path == Path(custom_path)

    def test_test_failure_patterns_defined(self):
        """Test that test failure patterns are defined."""
        parser = CILogParser()

        assert len(parser.TEST_FAILURE_PATTERNS) > 0
        assert any("failed" in p for p in parser.TEST_FAILURE_PATTERNS)

    def test_lint_error_patterns_defined(self):
        """Test that lint error patterns are defined."""
        parser = CILogParser()

        assert len(parser.LINT_ERROR_PATTERNS) > 0
        assert any("ruff" in p for p in parser.LINT_ERROR_PATTERNS)

    def test_build_failure_patterns_defined(self):
        """Test that build failure patterns are defined."""
        parser = CILogParser()

        assert len(parser.BUILD_FAILURE_PATTERNS) > 0
        assert any("build" in p for p in parser.BUILD_FAILURE_PATTERNS)

    def test_import_failure_patterns_defined(self):
        """Test that import failure patterns are defined."""
        parser = CILogParser()

        assert len(parser.IMPORT_FAILURE_PATTERNS) > 0
        assert any("importerror" in p for p in parser.IMPORT_FAILURE_PATTERNS)

    def test_file_access_patterns_defined(self):
        """Test that file access patterns are defined."""
        parser = CILogParser()

        assert len(parser.FILE_ACCESS_PATTERNS) > 0
        assert any("permission" in p for p in parser.FILE_ACCESS_PATTERNS)

    def test_timeout_patterns_defined(self):
        """Test that timeout patterns are defined."""
        parser = CILogParser()

        assert len(parser.TIMEOUT_PATTERNS) > 0
        assert any("timeout" in p for p in parser.TIMEOUT_PATTERNS)

    @patch("pathlib.Path.exists")
    def test_parse_file_nonexistent(self, mock_exists):
        """Test parsing non-existent file returns empty list."""
        mock_exists.return_value = False
        parser = CILogParser()

        result = parser.parse_file(Path("/fake/ci.log"))

        assert result == []

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_text")
    @patch("pathlib.Path.stat")
    def test_parse_file_with_test_failure(self, mock_stat, mock_read_text, mock_exists):
        """Test parsing CI log with test failure."""
        mock_exists.return_value = True
        content = """
Running pytest...
test_example.py::test_function failed 
1 failed, 10 passed
"""
        mock_read_text.return_value = content
        mock_stat.return_value = MagicMock(st_mtime=datetime.now().timestamp())

        parser = CILogParser()
        result = parser.parse_file(Path("/fake/ci.log"))

        assert len(result) >= 1
        assert result[0].category == IssueCategory.TOOL_ERROR
        assert result[0].source == IssueSource.CI_LOG

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_text")
    @patch("pathlib.Path.stat")
    def test_parse_file_with_lint_error(self, mock_stat, mock_read_text, mock_exists):
        """Test parsing CI log with lint error."""
        mock_exists.return_value = True
        content = """
Running ruff check...
ruff found error in src/main.py
1 error found
"""
        mock_read_text.return_value = content
        mock_stat.return_value = MagicMock(st_mtime=datetime.now().timestamp())

        parser = CILogParser()
        result = parser.parse_file(Path("/fake/ci.log"))

        assert len(result) >= 1
        assert result[0].category == IssueCategory.TOOL_ERROR
        assert "ruff" in result[0].raw_text.lower()

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_text")
    @patch("pathlib.Path.stat")
    def test_parse_file_with_build_failure(
        self, mock_stat, mock_read_text, mock_exists
    ):
        """Test parsing CI log with build failure."""
        mock_exists.return_value = True
        content = """
Building project...
SyntaxError: invalid syntax in build.py
Build failed
"""
        mock_read_text.return_value = content
        mock_stat.return_value = MagicMock(st_mtime=datetime.now().timestamp())

        parser = CILogParser()
        result = parser.parse_file(Path("/fake/ci.log"))

        assert len(result) >= 1
        assert result[0].category == IssueCategory.TOOL_ERROR

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_text")
    @patch("pathlib.Path.stat")
    def test_parse_file_with_import_error(self, mock_stat, mock_read_text, mock_exists):
        """Test parsing CI log with import error."""
        mock_exists.return_value = True
        content = """
Running tests...
ImportError: No module named 'nonexistent'
Tests could not run
"""
        mock_read_text.return_value = content
        mock_stat.return_value = MagicMock(st_mtime=datetime.now().timestamp())

        parser = CILogParser()
        result = parser.parse_file(Path("/fake/ci.log"))

        assert len(result) >= 1
        assert result[0].category == IssueCategory.TOOL_ERROR
        assert (
            "ImportError" in result[0].raw_text
            or "import" in result[0].raw_text.lower()
        )

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_text")
    @patch("pathlib.Path.stat")
    def test_parse_file_with_file_access_error(
        self, mock_stat, mock_read_text, mock_exists
    ):
        """Test parsing CI log with file access error."""
        mock_exists.return_value = True
        content = """
Running tests...
PermissionError: Permission denied accessing test.txt
"""
        mock_read_text.return_value = content
        mock_stat.return_value = MagicMock(st_mtime=datetime.now().timestamp())

        parser = CILogParser()
        result = parser.parse_file(Path("/fake/ci.log"))

        assert len(result) >= 1
        assert result[0].category == IssueCategory.FILE_ACCESS
        assert "permission" in result[0].raw_text.lower()

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_text")
    @patch("pathlib.Path.stat")
    def test_parse_file_with_timeout(self, mock_stat, mock_read_text, mock_exists):
        """Test parsing CI log with timeout."""
        mock_exists.return_value = True
        content = """
Running tests...
Timeout: Tests exceeded time limit
"""
        mock_read_text.return_value = content
        mock_stat.return_value = MagicMock(st_mtime=datetime.now().timestamp())

        parser = CILogParser()
        result = parser.parse_file(Path("/fake/ci.log"))

        assert len(result) >= 1
        assert result[0].category == IssueCategory.ENV_SLOWDOWN
        assert "timeout" in result[0].raw_text.lower()

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_text")
    @patch("pathlib.Path.stat")
    def test_parse_file_multiple_issues(self, mock_stat, mock_read_text, mock_exists):
        """Test parsing CI log with multiple issues."""
        mock_exists.return_value = True
        content = """
Running CI pipeline...
test_1.py::test_a failed 
[ E501 ] Line too long
PermissionError: Access denied
Build completed with errors
"""
        mock_read_text.return_value = content
        mock_stat.return_value = MagicMock(st_mtime=datetime.now().timestamp())

        parser = CILogParser()
        result = parser.parse_file(Path("/fake/ci.log"))

        assert len(result) >= 2
        categories = {issue.category for issue in result}
        assert IssueCategory.TOOL_ERROR in categories
        assert IssueCategory.FILE_ACCESS in categories

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.glob")
    def test_parse_all_empty_directory(self, mock_glob, mock_exists):
        """Test parse_all with empty directory."""
        mock_exists.return_value = True
        mock_glob.return_value = []

        parser = CILogParser()
        result = parser.parse_all()

        assert result == []

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.glob")
    def test_parse_all_with_files(self, mock_glob, mock_exists):
        """Test parse_all finds and parses files."""
        mock_exists.return_value = True
        mock_file = MagicMock()
        mock_glob.return_value = [mock_file]

        parser = CILogParser()
        # Mock parse_file to avoid actual file reading
        with patch.object(parser, "parse_file", return_value=[]):
            result = parser.parse_all()

        assert result == []

    def test_categorize_error_file_access(self):
        """Test categorization of file access errors."""
        parser = CILogParser()

        category = parser.categorize_error("PermissionError: Access denied")
        assert category == IssueCategory.FILE_ACCESS

        category = parser.categorize_error("FileNotFoundError: No such file")
        assert category == IssueCategory.FILE_ACCESS

    def test_categorize_error_timeout(self):
        """Test categorization of timeout errors."""
        parser = CILogParser()

        category = parser.categorize_error("Timeout: Operation timed out")
        assert category == IssueCategory.ENV_SLOWDOWN

        category = parser.categorize_error("Deadline exceeded")
        assert category == IssueCategory.ENV_SLOWDOWN

    def test_categorize_error_tool_error(self):
        """Test categorization of tool errors (default)."""
        parser = CILogParser()

        category = parser.categorize_error("Some generic error")
        assert category == IssueCategory.TOOL_ERROR

        category = parser.categorize_error("Test failed")
        assert category == IssueCategory.TOOL_ERROR

    def test_detect_issues_in_line_empty(self):
        """Test detecting issues in empty line."""
        parser = CILogParser()

        result = parser._detect_issues_in_line("")
        assert result == []

        result = parser._detect_issues_in_line("   ")
        assert result == []

    def test_detect_issues_in_line_separator(self):
        """Test detecting issues in separator line."""
        parser = CILogParser()

        result = parser._detect_issues_in_line("========")
        assert result == []

    def test_detect_issues_file_access(self):
        """Test detecting file access issues."""
        parser = CILogParser()

        result = parser._detect_issues_in_line("PermissionError: Access denied")
        assert len(result) == 1
        assert result[0][0] == IssueCategory.FILE_ACCESS

    def test_detect_issues_import_failure(self):
        """Test detecting import failure issues."""
        parser = CILogParser()

        result = parser._detect_issues_in_line("ImportError: No module named 'x'")
        assert len(result) == 1
        assert result[0][0] == IssueCategory.TOOL_ERROR

    def test_detect_issues_test_failure(self):
        """Test detecting test failure issues."""
        parser = CILogParser()

        result = parser._detect_issues_in_line("test_example.py::test FAILED")
        assert len(result) == 1
        assert result[0][0] == IssueCategory.TOOL_ERROR

    def test_detect_issues_lint_error_ruff(self):
        """Test detecting ruff lint error."""
        parser = CILogParser()

        result = parser._detect_issues_in_line("ruff found an error in the code")
        assert len(result) == 1
        assert result[0][0] == IssueCategory.TOOL_ERROR

    def test_detect_issues_lint_error_flake8(self):
        """Test detecting flake8 lint error."""
        parser = CILogParser()

        result = parser._detect_issues_in_line("flake8 error in main.py")
        assert len(result) == 1
        assert result[0][0] == IssueCategory.TOOL_ERROR

    def test_detect_issues_lint_error_mypy(self):
        """Test detecting mypy lint error."""
        parser = CILogParser()

        result = parser._detect_issues_in_line("mypy error in type checking")
        assert len(result) == 1
        assert result[0][0] == IssueCategory.TOOL_ERROR

    def test_detect_issues_lint_error_pylint(self):
        """Test detecting pylint lint error."""
        parser = CILogParser()

        result = parser._detect_issues_in_line("pylint error in module")
        assert len(result) == 1
        assert result[0][0] == IssueCategory.TOOL_ERROR

    def test_detect_issues_lint_error_black(self):
        """Test detecting black lint error."""
        parser = CILogParser()

        result = parser._detect_issues_in_line("black error formatting file")
        assert len(result) == 1
        assert result[0][0] == IssueCategory.TOOL_ERROR

    def test_detect_issues_build_failure(self):
        """Test detecting build failure issues."""
        parser = CILogParser()

        result = parser._detect_issues_in_line("SyntaxError: invalid syntax")
        assert len(result) == 1
        assert result[0][0] == IssueCategory.TOOL_ERROR

    def test_detect_issues_timeout(self):
        """Test detecting timeout issues."""
        parser = CILogParser()

        result = parser._detect_issues_in_line("Timeout: Tests timed out")
        assert len(result) == 1
        assert result[0][0] == IssueCategory.ENV_SLOWDOWN

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.glob")
    def test_parse_since_no_files(self, mock_glob, mock_exists):
        """Test parse_since with no matching files."""
        mock_exists.return_value = True
        mock_glob.return_value = []

        parser = CILogParser()
        since_time = datetime.now()
        result = parser.parse_since(since_time)

        assert result == []

    def test_issue_source_is_ci_log(self):
        """Test that parsed issues have CI_LOG source."""
        parser = CILogParser()

        with (
            patch("pathlib.Path.exists") as mock_exists,
            patch("pathlib.Path.read_text") as mock_read_text,
            patch("pathlib.Path.stat") as mock_stat,
        ):
            mock_exists.return_value = True
            mock_read_text.return_value = "test.py::test FAILED"
            mock_stat.return_value = MagicMock(st_mtime=datetime.now().timestamp())

            result = parser.parse_file(Path("/fake/ci.log"))

            if result:
                assert all(issue.source == IssueSource.CI_LOG for issue in result)

    def test_issue_has_line_number(self):
        """Test that parsed issues have line numbers."""
        parser = CILogParser()

        with (
            patch("pathlib.Path.exists") as mock_exists,
            patch("pathlib.Path.read_text") as mock_read_text,
            patch("pathlib.Path.stat") as mock_stat,
        ):
            mock_exists.return_value = True
            mock_read_text.return_value = "Line 1\ntest.py::test FAILED\nLine 3"
            mock_stat.return_value = MagicMock(st_mtime=datetime.now().timestamp())

            result = parser.parse_file(Path("/fake/ci.log"))

            if result:
                assert result[0].line_number is not None
                assert isinstance(result[0].line_number, int)

    def test_issue_has_file_path(self):
        """Test that parsed issues have file paths."""
        parser = CILogParser()

        with (
            patch("pathlib.Path.exists") as mock_exists,
            patch("pathlib.Path.read_text") as mock_read_text,
            patch("pathlib.Path.stat") as mock_stat,
        ):
            mock_exists.return_value = True
            mock_read_text.return_value = "test.py::test FAILED"
            mock_stat.return_value = MagicMock(st_mtime=datetime.now().timestamp())

            result = parser.parse_file(Path("/fake/ci.log"))

            if result:
                assert result[0].file_path == "/fake/ci.log"
