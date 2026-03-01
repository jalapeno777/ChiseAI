"""
Parser for iterlog markdown files.

# SAFETY: No risk cap logic modified
# SAFETY: No promotion gate logic modified
# SAFETY: No live trading flow modified
"""

import re
from datetime import datetime
from pathlib import Path

from .. import Issue, IssueCategory, IssueSource


class IterlogParser:
    """
    Parse iterlog files from docs/tempmemories/iterlog-*.md

    Extracts blockers, errors, slowdowns, and timeouts.

    # SAFETY: No risk cap logic modified
    # SAFETY: No promotion gate logic modified
    # SAFETY: No live trading flow modified
    """

    # Patterns to detect issues in iterlog content
    ISSUE_PATTERNS = {
        "blocker:": IssueCategory.OTHER,
        "error:": IssueCategory.TOOL_ERROR,
        "slowdown:": IssueCategory.ENV_SLOWDOWN,
        "timeout:": IssueCategory.ENV_SLOWDOWN,
        "failed:": IssueCategory.TOOL_ERROR,
        "permission denied": IssueCategory.FILE_ACCESS,
        "file not found": IssueCategory.FILE_ACCESS,
        "connection refused": IssueCategory.DB_CONNECTIVITY,
        "connection error": IssueCategory.DB_CONNECTIVITY,
        "redis": IssueCategory.DB_CONNECTIVITY,
        "postgres": IssueCategory.DB_CONNECTIVITY,
        "qdrant": IssueCategory.DB_CONNECTIVITY,
        "influxdb": IssueCategory.DB_CONNECTIVITY,
    }

    # File access patterns
    FILE_ACCESS_PATTERNS = [
        r"permission denied",
        r"file not found",
        r"no such file",
        r"access denied",
        r"read-only",
    ]

    # Database connectivity patterns
    DB_CONNECTIVITY_PATTERNS = [
        r"connection refused",
        r"connection error",
        r"could not connect",
        r"redis.*error",
        r"postgres.*error",
        r"qdrant.*error",
        r"influxdb.*error",
        r"database.*unavailable",
        r"redis.*timeout",
        r"postgres.*timeout",
    ]

    # Environment slowdown patterns
    ENV_SLOWDOWN_PATTERNS = [
        r"slowdown:",
        r"timeout:",
        r"high latency",
        r"resource exhaustion",
        r"out of memory",
        r"slow response",
        r"delay:",
    ]

    # Tool error patterns
    TOOL_ERROR_PATTERNS = [
        r"error:",
        r"failed:",
        r"importerror",
        r"modulenotfound",
        r"attributeerror",
        r"typeerror",
        r"valueerror",
        r"keyerror",
        r"traceback",
        r"exception:",
    ]

    def __init__(self, base_path: str = "docs/tempmemories"):
        """
        Initialize parser.

        Args:
            base_path: Base directory for iterlog files
        """
        self.base_path = Path(base_path)

    def parse_file(self, file_path: Path) -> list[Issue]:
        """
        Parse a single iterlog file.

        Args:
            file_path: Path to the iterlog file

        Returns:
            List of detected issues
        """
        issues = []

        if not file_path.exists():
            return issues

        content = file_path.read_text()
        file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)

        # Extract story_id from frontmatter if present
        story_id = self._extract_story_id(content)

        # Look for issue patterns in content
        lines = content.split("\n")
        for line_num, line in enumerate(lines, 1):
            detected = self._detect_issues_in_line(line)
            for category, description in detected:
                issue = Issue(
                    category=category,
                    description=description,
                    source=IssueSource.ITERLOG,
                    timestamp=file_mtime,
                    raw_text=line.strip(),
                    story_id=story_id,
                    file_path=str(file_path),
                    line_number=line_num,
                )
                issues.append(issue)

        return issues

    def parse_all(self, pattern: str = "iterlog-*.md") -> list[Issue]:
        """
        Parse all iterlog files matching pattern.

        Args:
            pattern: Glob pattern for iterlog files

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

    def parse_since(self, since: datetime, pattern: str = "*.md") -> list[Issue]:
        """
        Parse iterlog files modified since a given time.

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
    ) -> list[Issue]:
        """Parse file with explicit timestamp."""
        issues = []

        if not file_path.exists():
            return issues

        content = file_path.read_text()
        story_id = self._extract_story_id(content)

        lines = content.split("\n")
        for line_num, line in enumerate(lines, 1):
            detected = self._detect_issues_in_line(line)
            for category, description in detected:
                issue = Issue(
                    category=category,
                    description=description,
                    source=IssueSource.ITERLOG,
                    timestamp=timestamp,
                    raw_text=line.strip(),
                    story_id=story_id,
                    file_path=str(file_path),
                    line_number=line_num,
                )
                issues.append(issue)

        return issues

    def _extract_story_id(self, content: str) -> str | None:
        """Extract story_id from frontmatter."""
        # Look for story_id in YAML frontmatter
        match = re.search(r"^story_id:\s*(.+)$", content, re.MULTILINE)
        if match:
            return match.group(1).strip()
        return None

    def _detect_issues_in_line(self, line: str) -> list[tuple[IssueCategory, str]]:
        """
        Detect issues in a single line.

        Returns list of (category, description) tuples.
        """
        detected = []
        line_lower = line.lower()

        # Check for file access issues
        for pattern in self.FILE_ACCESS_PATTERNS:
            if re.search(pattern, line_lower):
                detected.append((IssueCategory.FILE_ACCESS, line.strip()))
                return detected  # Return early - one issue per line

        # Check for database connectivity issues
        for pattern in self.DB_CONNECTIVITY_PATTERNS:
            if re.search(pattern, line_lower):
                detected.append((IssueCategory.DB_CONNECTIVITY, line.strip()))
                return detected

        # Check for environment slowdown
        for pattern in self.ENV_SLOWDOWN_PATTERNS:
            if re.search(pattern, line_lower):
                detected.append((IssueCategory.ENV_SLOWDOWN, line.strip()))
                return detected

        # Check for tool errors
        for pattern in self.TOOL_ERROR_PATTERNS:
            if re.search(pattern, line_lower):
                detected.append((IssueCategory.TOOL_ERROR, line.strip()))
                return detected

        # Check for explicit issue markers
        for marker, category in self.ISSUE_PATTERNS.items():
            if marker in line_lower:
                detected.append((category, line.strip()))
                return detected

        return detected
