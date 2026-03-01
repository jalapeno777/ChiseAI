"""
Parser for worker completion reports.

# SAFETY: No risk cap logic modified
# SAFETY: No promotion gate logic modified
# SAFETY: No live trading flow modified
"""

import re
from datetime import datetime
from pathlib import Path


class WorkerReportParser:
    """
    Parse worker completion reports from handoffs.

    Extracts reported issues from worker handoff messages.

    # SAFETY: No risk cap logic modified
    # SAFETY: No promotion gate logic modified
    # SAFETY: No live trading flow modified
    """

    # Issue markers in worker reports
    ISSUE_MARKERS = [
        "blocker:",
        "error:",
        "issue:",
        "problem:",
        "failed:",
        "slowdown:",
        "timeout:",
        "warning:",
    ]

    # Status indicators
    STATUS_PATTERNS = {
        "blocked": r"\bblocked\b",
        "failed": r"\bfailed\b",
        "error": r"\berror\b",
        "timeout": r"\btimeout\b",
        "slow": r"\bslow\b|\bslowdown\b",
    }

    # File access patterns
    FILE_ACCESS_PATTERNS = [
        r"permission denied",
        r"file not found",
        r"no such file",
        r"access denied",
        r"read-only",
    ]

    # Database patterns
    DB_PATTERNS = [
        r"redis.*error",
        r"postgres.*error",
        r"qdrant.*error",
        r"database.*error",
        r"connection.*refused",
    ]

    def __init__(self, base_path: str = "docs/tempmemories"):
        """
        Initialize parser.

        Args:
            base_path: Base directory for worker reports
        """
        self.base_path = Path(base_path)

    def parse_file(self, file_path: Path) -> list["Issue"]:
        """
        Parse a single worker report file.

        Args:
            file_path: Path to the worker report file

        Returns:
            List of detected issues
        """
        from .. import Issue, IssueSource

        issues = []

        if not file_path.exists():
            return issues

        content = file_path.read_text()
        file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)

        # Extract story_id from content if present
        story_id = self._extract_story_id(content)

        # Look for issue markers in content
        lines = content.split("\n")
        for line_num, line in enumerate(lines, 1):
            detected = self._detect_issues_in_line(line)
            for category, description in detected:
                issue = Issue(
                    category=category,
                    description=description,
                    source=IssueSource.WORKER_REPORT,
                    timestamp=file_mtime,
                    raw_text=line.strip(),
                    story_id=story_id,
                    file_path=str(file_path),
                    line_number=line_num,
                )
                issues.append(issue)

        return issues

    def parse_all(self, pattern: str = "worker-*.md") -> list["Issue"]:
        """
        Parse all worker report files matching pattern.

        Args:
            pattern: Glob pattern for worker report files

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

    def parse_since(
        self, since: datetime, pattern: str = "worker-*.md"
    ) -> list["Issue"]:
        """
        Parse worker report files modified since a given time.

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

    def parse_text(self, text: str, timestamp: datetime | None = None) -> list["Issue"]:
        """
        Parse worker report text directly.

        Args:
            text: The worker report text
            timestamp: Optional timestamp (defaults to now)

        Returns:
            List of detected issues
        """
        from .. import Issue, IssueSource

        if timestamp is None:
            timestamp = datetime.now()

        issues = []
        story_id = self._extract_story_id(text)

        lines = text.split("\n")
        for line_num, line in enumerate(lines, 1):
            detected = self._detect_issues_in_line(line)
            for category, description in detected:
                issue = Issue(
                    category=category,
                    description=description,
                    source=IssueSource.WORKER_REPORT,
                    timestamp=timestamp,
                    raw_text=line.strip(),
                    story_id=story_id,
                    line_number=line_num,
                )
                issues.append(issue)

        return issues

    def _parse_file_with_time(
        self, file_path: Path, timestamp: datetime
    ) -> list["Issue"]:
        """Parse file with explicit timestamp."""
        from .. import Issue, IssueSource

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
                    source=IssueSource.WORKER_REPORT,
                    timestamp=timestamp,
                    raw_text=line.strip(),
                    story_id=story_id,
                    file_path=str(file_path),
                    line_number=line_num,
                )
                issues.append(issue)

        return issues

    def _extract_story_id(self, content: str) -> str | None:
        """Extract story_id from content."""
        # Look for story_id in various formats
        patterns = [
            r"story[_-]?id:\s*(.+)$",
            r"story:\s*(.+)$",
            r"STORY:\s*(.+)$",
            r"\b(ST-[A-Z0-9-]+)\b",
            r"\b(CH-[A-Z0-9-]+)\b",
            r"\b(FT-[A-Z0-9-]+)\b",
        ]

        for pattern in patterns:
            match = re.search(pattern, content, re.MULTILINE | re.IGNORECASE)
            if match:
                return match.group(1).strip()

        return None

    def _detect_issues_in_line(self, line: str) -> list[tuple["IssueCategory", str]]:
        """
        Detect issues in a single line.

        Returns list of (category, description) tuples.
        """

        detected = []
        line_lower = line.lower()

        # Skip empty lines
        if not line.strip():
            return detected

        # Check for issue markers
        has_marker = any(marker in line_lower for marker in self.ISSUE_MARKERS)

        if not has_marker:
            # Also check status patterns
            for _status, pattern in self.STATUS_PATTERNS.items():
                if re.search(pattern, line_lower):
                    has_marker = True
                    break

        if not has_marker:
            return detected

        # Categorize the issue
        category = self._categorize_issue(line_lower)
        detected.append((category, line.strip()))

        return detected

    def _categorize_issue(self, text: str) -> "IssueCategory":
        """Categorize an issue based on its content."""
        from .. import IssueCategory

        # Check for file access issues
        for pattern in self.FILE_ACCESS_PATTERNS:
            if re.search(pattern, text):
                return IssueCategory.FILE_ACCESS

        # Check for database issues
        for pattern in self.DB_PATTERNS:
            if re.search(pattern, text):
                return IssueCategory.DB_CONNECTIVITY

        # Check for timeout/slowdown
        if re.search(r"timeout|slow|slowdown", text):
            return IssueCategory.ENV_SLOWDOWN

        # Default to tool error
        return IssueCategory.TOOL_ERROR
