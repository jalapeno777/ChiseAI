"""
Parser for CI log files.

# SAFETY: No risk cap logic modified
# SAFETY: No promotion gate logic modified
# SAFETY: No live trading flow modified
"""

import re
from datetime import datetime
from pathlib import Path


class CILogParser:
    """
    Parse CI log files from _bmad-output/ci/*.log

    Extracts test failures, lint errors, and build failures.

    # SAFETY: No risk cap logic modified
    # SAFETY: No promotion gate logic modified
    # SAFETY: No live trading flow modified
    """

    # Import Issue at class level to avoid circular imports
    from .. import Issue, IssueCategory, IssueSource

    # Test failure patterns
    TEST_FAILURE_PATTERNS = [
        r"failed\s+",  # Match "FAILED " (lowercase after conversion)
        r"error\s+",
        r"test failed",
        r"assertionerror",
        r"assertion.*failed",
        r"test.*error",
    ]

    # Lint error patterns
    LINT_ERROR_PATTERNS = [
        r"ruff.*error",
        r"black.*error",
        r"mypy.*error",
        r"pylint.*error",
        r"flake8.*error",
        r"lint.*error",
        r"\[E\d+\]",  # Ruff/Flake8 error codes
    ]

    # Build failure patterns
    BUILD_FAILURE_PATTERNS = [
        r"build failed",
        r"compilation error",
        r"compile error",
        r"syntaxerror",
        r"indentionerror",
        r"importerror",
        r"modulenotfounderror",
    ]

    # Import failure patterns
    IMPORT_FAILURE_PATTERNS = [
        r"importerror:",
        r"modulenotfounderror:",
        r"cannot import name",
        r"no module named",
    ]

    # File access patterns in CI
    FILE_ACCESS_PATTERNS = [
        r"filenotfounderror",
        r"permissionerror",
        r"permission denied",
        r"no such file or directory",
        r"file not found",
    ]

    # Timeout patterns
    TIMEOUT_PATTERNS = [
        r"timeout",
        r"timed out",
        r"deadline exceeded",
    ]

    def __init__(self, base_path: str = "_bmad-output/ci"):
        """
        Initialize parser.

        Args:
            base_path: Base directory for CI log files
        """
        self.base_path = Path(base_path)

    def parse_file(self, file_path: Path) -> list["Issue"]:
        """
        Parse a single CI log file.

        Args:
            file_path: Path to the CI log file

        Returns:
            List of detected issues
        """
        from .. import Issue, IssueSource

        issues = []

        if not file_path.exists():
            return issues

        content = file_path.read_text()
        file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)

        lines = content.split("\n")
        for line_num, line in enumerate(lines, 1):
            detected = self._detect_issues_in_line(line)
            for category, description in detected:
                issue = Issue(
                    category=category,
                    description=description,
                    source=IssueSource.CI_LOG,
                    timestamp=file_mtime,
                    raw_text=line.strip(),
                    file_path=str(file_path),
                    line_number=line_num,
                )
                issues.append(issue)

        return issues

    def parse_all(self, pattern: str = "*.log") -> list["Issue"]:
        """
        Parse all CI log files matching pattern.

        Args:
            pattern: Glob pattern for log files

        Returns:
            List of all detected issues
        """

        all_issues = []

        if not self.base_path.exists():
            return all_issues

        for file_path in self.base_path.glob(pattern):
            issues = self.parse_file(file_path)
            all_issues.extend(issues)

        return all_issues

    def parse_since(self, since: datetime, pattern: str = "*.log") -> list["Issue"]:
        """
        Parse CI log files modified since a given time.

        Args:
            since: Cutoff time for file modification
            pattern: Glob pattern for files

        Returns:
            List of issues from recent files
        """

        all_issues = []

        if not self.base_path.exists():
            return all_issues

        for file_path in self.base_path.glob(pattern):
            file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
            if file_mtime >= since:
                issues = self._parse_file_with_time(file_path, file_mtime)
                all_issues.extend(issues)

        return all_issues

    def _parse_file_with_time(
        self, file_path: Path, timestamp: datetime
    ) -> list["Issue"]:
        """Parse file with explicit timestamp."""
        from .. import Issue, IssueSource

        issues = []

        if not file_path.exists():
            return issues

        content = file_path.read_text()

        lines = content.split("\n")
        for line_num, line in enumerate(lines, 1):
            detected = self._detect_issues_in_line(line)
            for category, description in detected:
                issue = Issue(
                    category=category,
                    description=description,
                    source=IssueSource.CI_LOG,
                    timestamp=timestamp,
                    raw_text=line.strip(),
                    file_path=str(file_path),
                    line_number=line_num,
                )
                issues.append(issue)

        return issues

    def _detect_issues_in_line(self, line: str) -> list[tuple["IssueCategory", str]]:
        """
        Detect issues in a single line.

        Returns list of (category, description) tuples.
        """
        from .. import IssueCategory

        detected = []
        line_lower = line.lower()

        # Skip empty lines or lines that are just separators
        if not line.strip() or line.strip().startswith("="):
            return detected

        # Check for file access issues
        for pattern in self.FILE_ACCESS_PATTERNS:
            if re.search(pattern, line_lower):
                detected.append((IssueCategory.FILE_ACCESS, line.strip()))
                return detected

        # Check for import failures (tool errors)
        for pattern in self.IMPORT_FAILURE_PATTERNS:
            if re.search(pattern, line_lower):
                detected.append((IssueCategory.TOOL_ERROR, line.strip()))
                return detected

        # Check for test failures
        for pattern in self.TEST_FAILURE_PATTERNS:
            if re.search(pattern, line_lower):
                detected.append((IssueCategory.TOOL_ERROR, line.strip()))
                return detected

        # Check for lint errors
        for pattern in self.LINT_ERROR_PATTERNS:
            if re.search(pattern, line_lower):
                detected.append((IssueCategory.TOOL_ERROR, line.strip()))
                return detected

        # Check for build failures
        for pattern in self.BUILD_FAILURE_PATTERNS:
            if re.search(pattern, line_lower):
                detected.append((IssueCategory.TOOL_ERROR, line.strip()))
                return detected

        # Check for timeouts
        for pattern in self.TIMEOUT_PATTERNS:
            if re.search(pattern, line_lower):
                detected.append((IssueCategory.ENV_SLOWDOWN, line.strip()))
                return detected

        return detected

    def categorize_error(self, error_text: str) -> "IssueCategory":
        """
        Categorize an error message.

        Args:
            error_text: The error message to categorize

        Returns:
            The appropriate issue category
        """
        from .. import IssueCategory

        error_lower = error_text.lower()

        # Check file access
        for pattern in self.FILE_ACCESS_PATTERNS:
            if re.search(pattern, error_lower):
                return IssueCategory.FILE_ACCESS

        # Check timeouts
        for pattern in self.TIMEOUT_PATTERNS:
            if re.search(pattern, error_lower):
                return IssueCategory.ENV_SLOWDOWN

        # Default to tool error
        return IssueCategory.TOOL_ERROR
