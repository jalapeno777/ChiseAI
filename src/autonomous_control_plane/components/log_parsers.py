"""Log parsers for the LogMonitor.

Provides different parsers for various log formats:
- JSONLogParser: Structured JSON logs
- RegexLogParser: Pattern-based parsing with regex
- SimpleLogParser: Basic line parsing with common patterns

For PM-BATCH-2 CF-1: Log Monitor + Trigger Service
"""

from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any, cast

from autonomous_control_plane.models.healing import LogEntry

logger = logging.getLogger(__name__)


class BaseLogParser(ABC):
    """Base class for log parsers."""

    @abstractmethod
    def parse(self, line: str) -> LogEntry | None:
        """Parse a log line into a LogEntry.

        Args:
            line: Raw log line to parse

        Returns:
            LogEntry if parsing succeeded, None otherwise
        """
        pass


class JSONLogParser(BaseLogParser):
    """Parser for JSON structured logs.

    Expects JSON objects with timestamp, level, source, and message fields.
    Configurable field names for flexibility with different log formats.

    Example:
        {"timestamp": "2024-01-15T10:30:00Z", "level": "ERROR",
         "source": "redis", "message": "Connection refused"}
    """

    def __init__(
        self,
        timestamp_key: str = "timestamp",
        level_key: str = "level",
        message_key: str = "message",
        source_key: str = "source",
        timestamp_format: str | None = None,
    ):
        """Initialize JSON log parser.

        Args:
            timestamp_key: Key for timestamp field in JSON
            level_key: Key for log level field
            message_key: Key for message field
            source_key: Key for source/component field
            timestamp_format: Optional strptime format for timestamp parsing
        """
        self.timestamp_key = timestamp_key
        self.level_key = level_key
        self.message_key = message_key
        self.source_key = source_key
        self.timestamp_format = timestamp_format

    def parse(self, line: str) -> LogEntry | None:
        """Parse a JSON log line.

        Args:
            line: JSON formatted log line

        Returns:
            LogEntry if valid JSON with required fields, None otherwise
        """
        try:
            data = json.loads(line)
            if not isinstance(data, dict):
                return None

            # Extract timestamp
            timestamp = self._parse_timestamp(data.get(self.timestamp_key))

            # Extract level with normalization
            level = data.get(self.level_key, "INFO")
            level = self._normalize_level(level)

            # Extract source and message
            source = data.get(self.source_key, "unknown")
            message = data.get(self.message_key, "")

            # Build metadata from remaining fields
            metadata_fields = {
                self.timestamp_key,
                self.level_key,
                self.message_key,
                self.source_key,
            }
            metadata = {k: v for k, v in data.items() if k not in metadata_fields}

            return LogEntry(
                timestamp=timestamp,
                level=level,
                source=str(source),
                message=str(message),
                metadata=metadata,
            )
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.debug(f"Failed to parse JSON log line: {e}")
            return None

    def _parse_timestamp(self, ts: Any) -> datetime:
        """Parse timestamp from various formats.

        Args:
            ts: Timestamp value (string, number, or None)

        Returns:
            Parsed datetime or current time if parsing fails
        """
        if ts is None:
            return datetime.now(UTC)

        if isinstance(ts, (int, float)):
            # Unix timestamp (seconds or milliseconds)
            if ts > 1e10:  # Likely milliseconds
                ts = ts / 1000
            return datetime.fromtimestamp(ts, tz=UTC)

        if isinstance(ts, str):
            # Try ISO format first
            try:
                # Handle various ISO formats
                ts_clean = ts.replace("Z", "+00:00")
                return datetime.fromisoformat(ts_clean)
            except (ValueError, AttributeError):
                pass

            # Try custom format if provided
            if self.timestamp_format:
                try:
                    return datetime.strptime(ts, self.timestamp_format)
                except ValueError:
                    pass

        return datetime.now(UTC)

    @staticmethod
    def _normalize_level(level: str) -> str:
        """Normalize log level to standard format.

        Args:
            level: Raw log level string

        Returns:
            Normalized level (ERROR, WARN, INFO, DEBUG, CRITICAL, FATAL)
        """
        level_upper = str(level).upper()
        level_map = {
            "WARNING": "WARN",
            "ERR": "ERROR",
            "FATAL": "CRITICAL",
            "TRACE": "DEBUG",
        }
        return level_map.get(level_upper, level_upper)


class RegexLogParser(BaseLogParser):
    """Parser using regex patterns for custom log formats.

    Allows flexible pattern matching with named or positional groups
    for timestamp, level, source, and message fields.

    Example:
        pattern = r'(?P<ts>\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2}) '
                  r'\\[(?P<level>\\w+)\\] (?P<source>\\w+): (?P<msg>.*)'
        parser = RegexLogParser(pattern, use_named_groups=True)
    """

    def __init__(
        self,
        pattern: str,
        timestamp_group: int | str = 1,
        level_group: int | str = 2,
        source_group: int | str = 3,
        message_group: int | str = 4,
        use_named_groups: bool = False,
        timestamp_format: str | None = None,
    ):
        """Initialize regex log parser.

        Args:
            pattern: Regex pattern with capturing groups
            timestamp_group: Group index or name for timestamp
            level_group: Group index or name for log level
            source_group: Group index or name for source
            message_group: Group index or name for message
            use_named_groups: If True, treat group parameters as names
            timestamp_format: Optional strptime format for timestamp
        """
        self.pattern = re.compile(pattern)
        self.timestamp_group = timestamp_group
        self.level_group = level_group
        self.source_group = source_group
        self.message_group = message_group
        self.use_named_groups = use_named_groups
        self.timestamp_format = timestamp_format

    def parse(self, line: str) -> LogEntry | None:
        """Parse a log line using regex pattern.

        Args:
            line: Log line to parse

        Returns:
            LogEntry if pattern matches, None otherwise
        """
        match = self.pattern.match(line)
        if not match:
            return None

        try:
            if self.use_named_groups:
                timestamp = self._parse_timestamp(match.group(self.timestamp_group))
                level = self._normalize_level(match.group(self.level_group) or "INFO")
                source = match.group(self.source_group) or "unknown"
                message = match.group(self.message_group) or ""
            else:
                groups = match.groups()
                # These are always int when use_named_groups is False
                ts_group = cast(int, self.timestamp_group)
                level_group = cast(int, self.level_group)
                source_group = cast(int, self.source_group)
                msg_group = cast(int, self.message_group)

                timestamp = self._parse_timestamp(
                    groups[ts_group - 1] if len(groups) >= ts_group else None
                )
                level = self._normalize_level(
                    groups[level_group - 1] if len(groups) >= level_group else "INFO"
                )
                source = (
                    groups[source_group - 1]
                    if len(groups) >= source_group
                    else "unknown"
                )
                message = groups[msg_group - 1] if len(groups) >= msg_group else ""

            return LogEntry(
                timestamp=timestamp,
                level=level,
                source=source,
                message=message,
            )
        except (IndexError, AttributeError) as e:
            logger.debug(f"Regex parse error: {e}")
            return None

    def _parse_timestamp(self, ts: str | None) -> datetime:
        """Parse timestamp string.

        Args:
            ts: Timestamp string or None

        Returns:
            Parsed datetime or current time
        """
        if not ts:
            return datetime.now(UTC)

        # Try ISO format
        try:
            ts_clean = ts.replace("Z", "+00:00")
            return datetime.fromisoformat(ts_clean)
        except (ValueError, AttributeError):
            pass

        # Try custom format
        if self.timestamp_format:
            try:
                return datetime.strptime(ts, self.timestamp_format)
            except ValueError:
                pass

        # Try common formats
        common_formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%d/%b/%Y:%H:%M:%S",
            "%b %d %H:%M:%S",
        ]
        for fmt in common_formats:
            try:
                return datetime.strptime(ts, fmt)
            except ValueError:
                continue

        return datetime.now(UTC)

    @staticmethod
    def _normalize_level(level: str) -> str:
        """Normalize log level."""
        level_upper = str(level).upper()
        level_map = {
            "WARNING": "WARN",
            "ERR": "ERROR",
            "FATAL": "CRITICAL",
            "TRACE": "DEBUG",
        }
        return level_map.get(level_upper, level_upper)


class SimpleLogParser(BaseLogParser):
    """Simple parser for basic log lines.

    Handles common log formats with timestamp, level, source, and message.
    Falls back gracefully when exact format doesn't match.

    Supported formats:
    - "2024-01-15 10:30:00 ERROR [source] message"
    - "2024-01-15T10:30:00Z WARN component - message"
    - "[2024-01-15 10:30:00] INFO: source: message"
    """

    # Common log patterns in order of preference
    PATTERNS = [
        # ISO timestamp with T separator
        re.compile(
            r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)\s+"
            r"(\w+)\s+\[(\w+)\]\s+(.*)"
        ),
        # Standard timestamp with space separator
        re.compile(
            r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+" r"(\w+)\s+\[(\w+)\]\s+(.*)"
        ),
        # Timestamp in brackets
        re.compile(
            r"\[(\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2})\]\s+"
            r"(\w+):?\s+(\w+):?\s+(.*)"
        ),
        # Simple format: LEVEL source: message
        re.compile(r"(\w+)\s+(\w+):\s+(.*)"),
    ]

    def __init__(self, default_source: str = "unknown"):
        """Initialize simple log parser.

        Args:
            default_source: Default source name when not parsed
        """
        self.default_source = default_source

    def parse(self, line: str) -> LogEntry | None:
        """Parse a log line using common patterns.

        Args:
            line: Log line to parse

        Returns:
            LogEntry, always returns a valid entry even if parsing partially fails
        """
        line = line.strip()
        if not line:
            return None

        # Try each pattern
        for pattern in self.PATTERNS:
            match = pattern.match(line)
            if match:
                groups = match.groups()
                if len(groups) == 4:
                    # Full format with timestamp
                    return LogEntry(
                        timestamp=self._parse_timestamp(groups[0]),
                        level=self._normalize_level(groups[1]),
                        source=groups[2],
                        message=groups[3],
                    )
                elif len(groups) == 3:
                    # Format without timestamp (level, source, message)
                    return LogEntry(
                        timestamp=datetime.now(UTC),
                        level=self._normalize_level(groups[0]),
                        source=groups[1],
                        message=groups[2],
                    )

        # Fallback: treat entire line as message
        return LogEntry(
            timestamp=datetime.now(UTC),
            level="INFO",
            source=self.default_source,
            message=line,
        )

    def _parse_timestamp(self, ts: str) -> datetime:
        """Parse timestamp from string.

        Args:
            ts: Timestamp string

        Returns:
            Parsed datetime or current time
        """
        # Clean up ISO format
        ts_clean = ts.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(ts_clean)
        except (ValueError, AttributeError):
            pass

        # Try common formats
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(ts, fmt)
                return dt.replace(tzinfo=UTC)
            except ValueError:
                continue

        return datetime.now(UTC)

    @staticmethod
    def _normalize_level(level: str) -> str:
        """Normalize log level."""
        level_upper = str(level).upper()
        level_map = {
            "WARNING": "WARN",
            "ERR": "ERROR",
            "FATAL": "CRITICAL",
            "TRACE": "DEBUG",
        }
        return level_map.get(level_upper, level_upper)
