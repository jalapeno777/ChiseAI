"""Failure pattern matchers for self-healing engine.

Provides pattern matchers for detecting various failure types:
- Redis disconnections
- API timeouts
- Circuit breaker trips
- Database connection failures
- Resource exhaustion (memory, disk, CPU)
- Service health failures

For ST-NS-040: Self-Healing Engine with Action Sandboxing
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any

from src.autonomous_control_plane.models.healing import (
    FailurePatternMatch,
    FailurePatternType,
    LogEntry,
)


class BaseFailurePattern(ABC):
    """Base class for failure pattern matchers."""

    pattern_type: FailurePatternType
    priority: int = 0

    @abstractmethod
    def match(self, log_entry: LogEntry) -> FailurePatternMatch:
        """Match log entry against this pattern.

        Args:
            log_entry: Log entry to match

        Returns:
            Match result with confidence and extracted fields
        """
        pass


class RedisDisconnectPattern(BaseFailurePattern):
    """Pattern for Redis connection failures."""

    pattern_type = FailurePatternType.REDIS_DISCONNECT
    priority = 10

    # Patterns that indicate Redis disconnection
    PATTERNS = [
        re.compile(r"redis.*connection.*(?:error|failed|refused|reset)", re.IGNORECASE),
        re.compile(r"connection.*(?:error|failed).*redis", re.IGNORECASE),
        re.compile(r"redis.*timeout", re.IGNORECASE),
        re.compile(r"broken.*pipe.*redis", re.IGNORECASE),
        re.compile(r"redis.*socket.*error", re.IGNORECASE),
        re.compile(
            r"(?:error|exception).*redis.*(?:connect|connection)", re.IGNORECASE
        ),
    ]

    def match(self, log_entry: LogEntry) -> FailurePatternMatch:
        """Match Redis disconnection patterns."""
        text = f"{log_entry.source} {log_entry.message}"

        for pattern in self.PATTERNS:
            if pattern.search(text):
                return FailurePatternMatch(
                    matched=True,
                    pattern_type=self.pattern_type,
                    confidence=0.9,
                    extracted_fields={
                        "source": log_entry.source,
                        "error_type": "connection_failure",
                    },
                    priority=self.priority,
                )

        return FailurePatternMatch.no_match()


class APITimeoutPattern(BaseFailurePattern):
    """Pattern for API timeout errors."""

    pattern_type = FailurePatternType.API_TIMEOUT
    priority = 9

    PATTERNS = [
        re.compile(r"timeout.*(?:api|request|connection)", re.IGNORECASE),
        re.compile(r"(?:api|request).*timeout", re.IGNORECASE),
        re.compile(r"read.*timeout", re.IGNORECASE),
        re.compile(r"connect.*timeout", re.IGNORECASE),
        re.compile(r"httpx.*timeout", re.IGNORECASE),
        re.compile(r"aiohttp.*timeout", re.IGNORECASE),
        re.compile(r"requests.*timeout", re.IGNORECASE),
    ]

    def match(self, log_entry: LogEntry) -> FailurePatternMatch:
        """Match API timeout patterns."""
        text = f"{log_entry.source} {log_entry.message}"

        for pattern in self.PATTERNS:
            if pattern.search(text):
                # Try to extract the API endpoint if available
                endpoint = self._extract_endpoint(log_entry.message)

                return FailurePatternMatch(
                    matched=True,
                    pattern_type=self.pattern_type,
                    confidence=0.85,
                    extracted_fields={
                        "source": log_entry.source,
                        "error_type": "timeout",
                        "endpoint": endpoint,
                    },
                    priority=self.priority,
                )

        return FailurePatternMatch.no_match()

    def _extract_endpoint(self, message: str) -> str | None:
        """Extract API endpoint from message."""
        # Look for URL patterns
        url_pattern = re.compile(r"https?://[^\s\"']+|/api/[^\s\"']*")
        match = url_pattern.search(message)
        return match.group(0) if match else None


class CircuitBreakerOpenPattern(BaseFailurePattern):
    """Pattern for circuit breaker state transitions to OPEN."""

    pattern_type = FailurePatternType.CIRCUIT_BREAKER_OPEN
    priority = 10

    PATTERNS = [
        re.compile(r"circuit.*breaker.*open", re.IGNORECASE),
        re.compile(r"circuit.*open.*breaker", re.IGNORECASE),
        re.compile(r"circuitbreaker.*open", re.IGNORECASE),
        re.compile(r"circuit.*breaker.*threshold.*reached", re.IGNORECASE),
        re.compile(r"(?:closing|transitioning).*circuit.*breaker", re.IGNORECASE),
    ]

    def match(self, log_entry: LogEntry) -> FailurePatternMatch:
        """Match circuit breaker open patterns."""
        text = f"{log_entry.source} {log_entry.message}"

        for pattern in self.PATTERNS:
            if pattern.search(text):
                # Extract circuit name if available
                circuit_name = self._extract_circuit_name(log_entry.message)

                return FailurePatternMatch(
                    matched=True,
                    pattern_type=self.pattern_type,
                    confidence=0.95,
                    extracted_fields={
                        "source": log_entry.source,
                        "circuit_name": circuit_name,
                        "error_type": "circuit_open",
                    },
                    priority=self.priority,
                )

        return FailurePatternMatch.no_match()

    def _extract_circuit_name(self, message: str) -> str | None:
        """Extract circuit breaker name from message."""
        # Look for quoted names or names after 'circuit'
        patterns = [
            re.compile(r"circuit\s+['\"]([^'\"]+)['\"]", re.IGNORECASE),
            re.compile(r"circuit\s+(\w+)", re.IGNORECASE),
            re.compile(r"['\"]([^'\"]+)['\"].*circuit", re.IGNORECASE),
        ]

        for pattern in patterns:
            match = pattern.search(message)
            if match:
                return match.group(1)

        return None


class DatabaseConnectionPattern(BaseFailurePattern):
    """Pattern for database connection failures."""

    pattern_type = FailurePatternType.DATABASE_CONNECTION
    priority = 10

    PATTERNS = [
        re.compile(
            r"(?:postgres|postgresql|mysql|sqlite).*connection.*(?:error|failed|refused)",
            re.IGNORECASE,
        ),
        re.compile(r"database.*connection.*(?:error|failed|refused)", re.IGNORECASE),
        re.compile(r"connection.*(?:error|failed).*database", re.IGNORECASE),
        re.compile(r"(?:psycopg|asyncpg|sqlalchemy).*error", re.IGNORECASE),
        re.compile(r"could not connect to.*database", re.IGNORECASE),
        re.compile(r"database.*unreachable", re.IGNORECASE),
    ]

    def match(self, log_entry: LogEntry) -> FailurePatternMatch:
        """Match database connection patterns."""
        text = f"{log_entry.source} {log_entry.message}"

        for pattern in self.PATTERNS:
            if pattern.search(text):
                return FailurePatternMatch(
                    matched=True,
                    pattern_type=self.pattern_type,
                    confidence=0.9,
                    extracted_fields={
                        "source": log_entry.source,
                        "error_type": "connection_failure",
                    },
                    priority=self.priority,
                )

        return FailurePatternMatch.no_match()


class MemoryExhaustionPattern(BaseFailurePattern):
    """Pattern for high memory usage alerts."""

    pattern_type = FailurePatternType.MEMORY_EXHAUSTION
    priority = 8

    PATTERNS = [
        re.compile(
            r"memory.*(?:exhausted|critical|high|threshold|limit)", re.IGNORECASE
        ),
        re.compile(r"(?:high|critical).*memory.*usage", re.IGNORECASE),
        re.compile(r"memory.*usage.*(?:above|exceeds|critical)", re.IGNORECASE),
        re.compile(r"out of memory|oom", re.IGNORECASE),
        re.compile(r"memoryerror|memory.*error", re.IGNORECASE),
        re.compile(r"cannot allocate memory", re.IGNORECASE),
    ]

    def match(self, log_entry: LogEntry) -> FailurePatternMatch:
        """Match memory exhaustion patterns."""
        text = f"{log_entry.source} {log_entry.message}"

        for pattern in self.PATTERNS:
            if pattern.search(text):
                # Try to extract memory percentage
                memory_pct = self._extract_memory_percentage(log_entry.message)

                return FailurePatternMatch(
                    matched=True,
                    pattern_type=self.pattern_type,
                    confidence=0.85,
                    extracted_fields={
                        "source": log_entry.source,
                        "error_type": "memory_exhaustion",
                        "memory_percent": memory_pct,
                    },
                    priority=self.priority,
                )

        return FailurePatternMatch.no_match()

    def _extract_memory_percentage(self, message: str) -> float | None:
        """Extract memory percentage from message."""
        # Look for patterns like "85%" or "85 percent" or "85.5%"
        patterns = [
            re.compile(r"(\d+\.?\d*)\s*%"),
            re.compile(r"(\d+\.?\d*)\s+percent", re.IGNORECASE),
        ]

        for pattern in patterns:
            match = pattern.search(message)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    pass

        return None


class DiskSpacePattern(BaseFailurePattern):
    """Pattern for low disk space warnings."""

    pattern_type = FailurePatternType.DISK_SPACE
    priority = 7

    PATTERNS = [
        re.compile(r"disk.*(?:full|low|critical|space)", re.IGNORECASE),
        re.compile(r"(?:low|no|critical).*disk.*space", re.IGNORECASE),
        re.compile(r"disk.*space.*(?:low|critical|exhausted)", re.IGNORECASE),
        re.compile(r"no space left on device", re.IGNORECASE),
        re.compile(r"filesystem.*full", re.IGNORECASE),
    ]

    def match(self, log_entry: LogEntry) -> FailurePatternMatch:
        """Match disk space patterns."""
        text = f"{log_entry.source} {log_entry.message}"

        for pattern in self.PATTERNS:
            if pattern.search(text):
                # Try to extract disk percentage
                disk_pct = self._extract_disk_percentage(log_entry.message)

                return FailurePatternMatch(
                    matched=True,
                    pattern_type=self.pattern_type,
                    confidence=0.85,
                    extracted_fields={
                        "source": log_entry.source,
                        "error_type": "disk_space",
                        "disk_percent": disk_pct,
                    },
                    priority=self.priority,
                )

        return FailurePatternMatch.no_match()

    def _extract_disk_percentage(self, message: str) -> float | None:
        """Extract disk usage percentage from message."""
        patterns = [
            re.compile(r"(\d+\.?\d*)\s*%.*(?:disk|full|used)"),
            re.compile(r"(?:disk|usage).*(\d+\.?\d*)\s*%"),
        ]

        for pattern in patterns:
            match = pattern.search(message)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    pass

        return None


class CPUSpikePattern(BaseFailurePattern):
    """Pattern for CPU usage spike detection."""

    pattern_type = FailurePatternType.CPU_SPIKE
    priority = 6

    PATTERNS = [
        re.compile(r"cpu.*(?:spike|high|critical|threshold|usage)", re.IGNORECASE),
        re.compile(r"(?:high|critical).*cpu.*usage", re.IGNORECASE),
        re.compile(r"cpu.*usage.*(?:above|exceeds|critical|spike)", re.IGNORECASE),
        re.compile(r"cpu.*load.*(?:high|critical)", re.IGNORECASE),
    ]

    def match(self, log_entry: LogEntry) -> FailurePatternMatch:
        """Match CPU spike patterns."""
        text = f"{log_entry.source} {log_entry.message}"

        for pattern in self.PATTERNS:
            if pattern.search(text):
                # Try to extract CPU percentage
                cpu_pct = self._extract_cpu_percentage(log_entry.message)

                return FailurePatternMatch(
                    matched=True,
                    pattern_type=self.pattern_type,
                    confidence=0.8,
                    extracted_fields={
                        "source": log_entry.source,
                        "error_type": "cpu_spike",
                        "cpu_percent": cpu_pct,
                    },
                    priority=self.priority,
                )

        return FailurePatternMatch.no_match()

    def _extract_cpu_percentage(self, message: str) -> float | None:
        """Extract CPU percentage from message."""
        patterns = [
            re.compile(r"cpu.*?(\d+\.?\d*)\s*%"),
            re.compile(r"(\d+\.?\d*)\s*%.*?cpu"),
        ]

        for pattern in patterns:
            match = pattern.search(message)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    pass

        return None


class InfluxDBWritePattern(BaseFailurePattern):
    """Pattern for InfluxDB write failures."""

    pattern_type = FailurePatternType.INFLUXDB_WRITE
    priority = 8

    PATTERNS = [
        re.compile(r"influxdb.*(?:write|insert).*fail", re.IGNORECASE),
        re.compile(r"influx.*(?:error|exception|timeout)", re.IGNORECASE),
        re.compile(r"failed.*write.*influx", re.IGNORECASE),
        re.compile(r"influx.*(?:connection|buffer).*error", re.IGNORECASE),
        re.compile(r"influx.*(?:rate|quota).*limit", re.IGNORECASE),
    ]

    def match(self, log_entry: LogEntry) -> FailurePatternMatch:
        """Match InfluxDB write failure patterns."""
        text = f"{log_entry.source} {log_entry.message}"

        for pattern in self.PATTERNS:
            if pattern.search(text):
                return FailurePatternMatch(
                    matched=True,
                    pattern_type=self.pattern_type,
                    confidence=0.9,
                    extracted_fields={
                        "source": log_entry.source,
                        "error_type": "write_failure",
                    },
                    priority=self.priority,
                )

        return FailurePatternMatch.no_match()


class DeadLetterQueuePattern(BaseFailurePattern):
    """Pattern for dead letter queue depth threshold exceeded."""

    pattern_type = FailurePatternType.DEAD_LETTER_QUEUE
    priority = 9

    PATTERNS = [
        re.compile(
            r"dead.?letter.*queue.*(?:depth|size|threshold|exceeded)", re.IGNORECASE
        ),
        re.compile(r"dlq.*(?:depth|size|threshold|exceeded)", re.IGNORECASE),
        re.compile(r"(?:queue|dlq).*dead.?letter", re.IGNORECASE),
        re.compile(r"(?:messages|items).*dead.?letter", re.IGNORECASE),
    ]

    def match(self, log_entry: LogEntry) -> FailurePatternMatch:
        """Match dead letter queue patterns."""
        text = f"{log_entry.source} {log_entry.message}"

        for pattern in self.PATTERNS:
            if pattern.search(text):
                # Try to extract queue depth
                depth = self._extract_queue_depth(log_entry.message)

                return FailurePatternMatch(
                    matched=True,
                    pattern_type=self.pattern_type,
                    confidence=0.85,
                    extracted_fields={
                        "source": log_entry.source,
                        "error_type": "queue_depth_exceeded",
                        "queue_depth": depth,
                    },
                    priority=self.priority,
                )

        return FailurePatternMatch.no_match()

    def _extract_queue_depth(self, message: str) -> int | None:
        """Extract queue depth from message."""
        patterns = [
            re.compile(r"depth[:\s]+(\d+)", re.IGNORECASE),
            re.compile(r"(\d+)\s*(?:messages|items)", re.IGNORECASE),
            re.compile(r"size[:\s]+(\d+)", re.IGNORECASE),
        ]

        for pattern in patterns:
            match = pattern.search(message)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    pass

        return None


class ServiceUnhealthyPattern(BaseFailurePattern):
    """Pattern for service health check failures."""

    pattern_type = FailurePatternType.SERVICE_UNHEALTHY
    priority = 10

    PATTERNS = [
        re.compile(r"health.*check.*(?:fail|error|unhealthy)", re.IGNORECASE),
        re.compile(r"service.*(?:unhealthy|down|unavailable)", re.IGNORECASE),
        re.compile(r"(?:unhealthy|unavailable).*service", re.IGNORECASE),
        re.compile(r"health.*endpoint.*(?:fail|error|down)", re.IGNORECASE),
        re.compile(r"service.*health.*(?:critical|error)", re.IGNORECASE),
    ]

    def match(self, log_entry: LogEntry) -> FailurePatternMatch:
        """Match service unhealthy patterns."""
        text = f"{log_entry.source} {log_entry.message}"

        for pattern in self.PATTERNS:
            if pattern.search(text):
                # Extract service name if available
                service_name = self._extract_service_name(
                    log_entry.message, log_entry.source
                )

                return FailurePatternMatch(
                    matched=True,
                    pattern_type=self.pattern_type,
                    confidence=0.85,
                    extracted_fields={
                        "source": log_entry.source,
                        "error_type": "health_check_failure",
                        "service_name": service_name,
                    },
                    priority=self.priority,
                )

        return FailurePatternMatch.no_match()

    def _extract_service_name(self, message: str, source: str) -> str | None:
        """Extract service name from message or source."""
        # Look for quoted names or names after 'service'
        patterns = [
            re.compile(r"service\s+['\"]([^'\"]+)['\"]", re.IGNORECASE),
            re.compile(r"service\s+(\w+)", re.IGNORECASE),
        ]

        for pattern in patterns:
            match = pattern.search(message)
            if match:
                return match.group(1)

        # Return source as fallback
        return source if source else None


# List of all available patterns
ALL_PATTERNS: list[type[BaseFailurePattern]] = [
    RedisDisconnectPattern,
    APITimeoutPattern,
    CircuitBreakerOpenPattern,
    DatabaseConnectionPattern,
    MemoryExhaustionPattern,
    DiskSpacePattern,
    CPUSpikePattern,
    InfluxDBWritePattern,
    DeadLetterQueuePattern,
    ServiceUnhealthyPattern,
]
