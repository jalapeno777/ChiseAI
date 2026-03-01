"""
Issue Ingestion Engine for brain evaluation.

# SAFETY: No risk cap logic modified
# SAFETY: No promotion gate logic modified
# SAFETY: No live trading flow modified
"""

from datetime import datetime, timedelta

from . import Issue, IssueCategory, IssueSource
from .parsers import CILogParser, IterlogParser, WorkerReportParser


class IssueIngestion:
    """
    Main issue ingestion engine that collects issues from multiple sources.

    # SAFETY: No risk cap logic modified
    # SAFETY: No promotion gate logic modified
    # SAFETY: No live trading flow modified
    """

    # Redis key patterns for iterlogs
    REDIS_ITERLOG_PATTERN = "bmad:chiseai:iterlog:story:*"

    def __init__(
        self,
        iterlog_path: str = "docs/tempmemories",
        ci_log_path: str = "_bmad-output/ci",
        worker_report_path: str = "docs/tempmemories",
        redis_client=None,
    ):
        """
        Initialize the issue ingestion engine.

        Args:
            iterlog_path: Path to iterlog markdown files
            ci_log_path: Path to CI log files
            worker_report_path: Path to worker report files
            redis_client: Optional Redis client for Redis-based ingestion
        """
        self.iterlog_parser = IterlogParser(iterlog_path)
        self.ci_log_parser = CILogParser(ci_log_path)
        self.worker_report_parser = WorkerReportParser(worker_report_path)
        self.redis_client = redis_client

        # Track seen fingerprints for deduplication
        self._seen_fingerprints: set[str] = set()

    def ingest_from_iterlogs(
        self, since: datetime | None = None, pattern: str = "*.md"
    ) -> list[Issue]:
        """
        Ingest issues from iterlog files.

        Args:
            since: Optional cutoff time (default: last 6 hours)
            pattern: Glob pattern for iterlog files

        Returns:
            List of deduplicated issues
        """
        if since is None:
            since = datetime.now() - timedelta(hours=6)

        issues = self.iterlog_parser.parse_since(since, pattern)
        return self._deduplicate_issues(issues)

    def ingest_from_ci_logs(
        self, since: datetime | None = None, pattern: str = "*.log"
    ) -> list[Issue]:
        """
        Ingest issues from CI log files.

        Args:
            since: Optional cutoff time (default: last 6 hours)
            pattern: Glob pattern for log files

        Returns:
            List of deduplicated issues
        """
        if since is None:
            since = datetime.now() - timedelta(hours=6)

        issues = self.ci_log_parser.parse_since(since, pattern)
        return self._deduplicate_issues(issues)

    def ingest_from_worker_reports(
        self, since: datetime | None = None, pattern: str = "worker-*.md"
    ) -> list[Issue]:
        """
        Ingest issues from worker report files.

        Args:
            since: Optional cutoff time (default: last 6 hours)
            pattern: Glob pattern for worker report files

        Returns:
            List of deduplicated issues
        """
        if since is None:
            since = datetime.now() - timedelta(hours=6)

        issues = self.worker_report_parser.parse_since(since, pattern)
        return self._deduplicate_issues(issues)

    def ingest_from_redis(
        self, since: datetime | None = None, pattern: str | None = None
    ) -> list[Issue]:
        """
        Ingest issues from Redis iterlog keys.

        Pattern: bmad:chiseai:iterlog:story:*

        Args:
            since: Optional cutoff time (default: last 6 hours)
            pattern: Redis key pattern (default: class constant)

        Returns:
            List of deduplicated issues
        """
        if since is None:
            since = datetime.now() - timedelta(hours=6)

        if pattern is None:
            pattern = self.REDIS_ITERLOG_PATTERN

        issues = []

        if self.redis_client is None:
            # Try to import and create a Redis client
            try:
                import redis

                # Try to connect to default Redis
                self.redis_client = redis.Redis(
                    host="localhost", port=6380, db=0, decode_responses=True
                )
            except Exception:
                # No Redis available, return empty list
                return issues

        try:
            # Scan for iterlog keys
            cursor = 0
            while True:
                cursor, keys = self.redis_client.scan(
                    cursor=cursor, match=pattern, count=100
                )

                for key in keys:
                    # Get the iterlog content from Redis
                    content = self.redis_client.get(key)
                    if content:
                        # Parse the content for issues
                        key_issues = self._parse_redis_iterlog(key, content, since)
                        issues.extend(key_issues)

                if cursor == 0:
                    break

        except Exception as e:
            # Log error but don't fail
            print(f"Warning: Redis ingestion failed: {e}")

        return self._deduplicate_issues(issues)

    def _parse_redis_iterlog(
        self, key: str, content: str, since: datetime
    ) -> list[Issue]:
        """
        Parse an iterlog stored in Redis.

        Args:
            key: The Redis key
            content: The iterlog content
            since: Cutoff time

        Returns:
            List of issues found in the iterlog
        """
        import re

        issues = []

        # Extract story_id from key (e.g., bmad:chiseai:iterlog:story:ST-001)
        story_id = None
        key_parts = key.split(":")
        if len(key_parts) >= 4:
            story_id = key_parts[-1]

        # Check if this iterlog is recent enough
        # Look for timestamp in content
        timestamp_match = re.search(
            r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})", content
        )

        if timestamp_match:
            try:
                timestamp = datetime.fromisoformat(timestamp_match.group(1))
                if timestamp < since:
                    return issues
            except ValueError:
                # Use current time if parsing fails
                timestamp = datetime.now()
        else:
            timestamp = datetime.now()

        # Parse content for issues
        lines = content.split("\n")
        for _line_num, line in enumerate(lines, 1):
            detected = self._detect_issues_in_text(line)
            for category, description in detected:
                issue = Issue(
                    category=category,
                    description=description,
                    source=IssueSource.REDIS,
                    timestamp=timestamp,
                    raw_text=line.strip(),
                    story_id=story_id,
                    metadata={"redis_key": key},
                )
                issues.append(issue)

        return issues

    def _detect_issues_in_text(self, text: str) -> list[tuple[IssueCategory, str]]:
        """
        Detect issues in text using common patterns.

        Args:
            text: Text to analyze

        Returns:
            List of (category, description) tuples
        """
        import re

        detected = []
        text_lower = text.lower()

        # Skip empty or separator lines
        if not text.strip() or text.strip().startswith("="):
            return detected

        # File access patterns
        file_patterns = [
            r"permission denied",
            r"file not found",
            r"no such file",
            r"access denied",
        ]
        for pattern in file_patterns:
            if re.search(pattern, text_lower):
                detected.append((IssueCategory.FILE_ACCESS, text.strip()))
                return detected

        # Database connectivity patterns
        db_patterns = [
            r"redis.*error",
            r"postgres.*error",
            r"qdrant.*error",
            r"connection refused",
            r"connection error",
        ]
        for pattern in db_patterns:
            if re.search(pattern, text_lower):
                detected.append((IssueCategory.DB_CONNECTIVITY, text.strip()))
                return detected

        # Environment slowdown patterns
        slowdown_patterns = [
            r"timeout",
            r"slowdown",
            r"high latency",
            r"resource exhaustion",
        ]
        for pattern in slowdown_patterns:
            if re.search(pattern, text_lower):
                detected.append((IssueCategory.ENV_SLOWDOWN, text.strip()))
                return detected

        # Tool error patterns
        error_patterns = [
            r"error:",
            r"failed:",
            r"exception:",
            r"importerror",
            r"traceback",
        ]
        for pattern in error_patterns:
            if re.search(pattern, text_lower):
                detected.append((IssueCategory.TOOL_ERROR, text.strip()))
                return detected

        return detected

    def ingest_all(
        self, since: datetime | None = None, include_redis: bool = True
    ) -> list[Issue]:
        """
        Ingest issues from all sources.

        Args:
            since: Optional cutoff time (default: last 6 hours)
            include_redis: Whether to include Redis-based ingestion

        Returns:
            List of all deduplicated issues
        """
        if since is None:
            since = datetime.now() - timedelta(hours=6)

        all_issues = []

        # Ingest from all sources (each already deduplicates)
        all_issues.extend(self.ingest_from_iterlogs(since))
        all_issues.extend(self.ingest_from_ci_logs(since))
        all_issues.extend(self.ingest_from_worker_reports(since))

        if include_redis:
            all_issues.extend(self.ingest_from_redis(since))

        # No final deduplication needed - each source method already deduplicates
        # and adds fingerprints to the seen set
        return all_issues

    def _deduplicate_issues(self, issues: list[Issue]) -> list[Issue]:
        """
        Deduplicate issues by fingerprint.

        Args:
            issues: List of issues to deduplicate

        Returns:
            Deduplicated list of issues
        """
        unique_issues = []

        for issue in issues:
            if issue.fingerprint not in self._seen_fingerprints:
                self._seen_fingerprints.add(issue.fingerprint)
                unique_issues.append(issue)

        return unique_issues

    def get_issue_counts_by_category(
        self, issues: list[Issue]
    ) -> dict[IssueCategory, int]:
        """
        Count issues by category.

        Args:
            issues: List of issues

        Returns:
            Dictionary mapping category to count
        """
        counts: dict[IssueCategory, int] = {}
        for category in IssueCategory:
            counts[category] = 0

        for issue in issues:
            counts[issue.category] += 1

        return counts

    def get_issue_counts_by_source(self, issues: list[Issue]) -> dict[IssueSource, int]:
        """
        Count issues by source.

        Args:
            issues: List of issues

        Returns:
            Dictionary mapping source to count
        """
        counts: dict[IssueSource, int] = {}
        for source in IssueSource:
            counts[source] = 0

        for issue in issues:
            counts[issue.source] += 1

        return counts

    def reset_deduplication(self) -> None:
        """Reset the seen fingerprints set."""
        self._seen_fingerprints.clear()


__all__ = ["IssueIngestion"]
