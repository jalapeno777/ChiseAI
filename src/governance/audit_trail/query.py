"""
Query interface for the audit trail.

Provides flexible querying of audit entries by:
- Agent ID
- Time range
- Decision type
- Outcome
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from src.governance.audit_trail.decision import DecisionOutcome, DecisionType
from src.governance.audit_trail.trail import AuditTrailEntry

logger = logging.getLogger(__name__)


class SortOrder(str, Enum):
    """Sort order for query results."""

    ASC = "asc"
    DESC = "desc"


@runtime_checkable
class RedisClient(Protocol):
    """Protocol for Redis client interface."""

    def zrangebyscore(
        self,
        name: str,
        min_score: float,
        max_score: float,
        withscores: bool = False,
    ) -> list[Any]: ...

    def lrange(self, name: str, start: int, stop: int) -> list[bytes]: ...

    def zrange(
        self, name: str, start: int, stop: int, withscores: bool = False
    ) -> list[Any]: ...


@dataclass
class QueryFilter:
    """
    Filter criteria for audit trail queries.

    All filters are optional and combined with AND logic.

    Attributes:
        agent_id: Filter by agent ID
        agent_ids: Filter by multiple agent IDs (OR within this filter)
        decision_types: Filter by decision types
        outcomes: Filter by outcomes
        start_time: Filter entries after this time
        end_time: Filter entries before this time
        story_id: Filter by story ID
        constitution_principle: Filter by constitution principle
    """

    agent_id: str | None = None
    agent_ids: list[str] | None = None
    decision_types: list[DecisionType] | None = None
    outcomes: list[DecisionOutcome] | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    story_id: str | None = None
    constitution_principle: str | None = None

    def matches(self, entry: AuditTrailEntry) -> bool:
        """
        Check if an entry matches this filter.

        Args:
            entry: Entry to check

        Returns:
            True if entry matches all filter criteria
        """
        # Check agent ID
        if self.agent_id is not None and entry.agent_id != self.agent_id:
            return False

        # Check agent IDs (OR logic)
        if self.agent_ids is not None and entry.agent_id not in self.agent_ids:
            return False

        # Check decision types
        if (
            self.decision_types is not None
            and entry.decision_type not in self.decision_types
        ):
            return False

        # Check outcomes
        if self.outcomes is not None and entry.outcome not in self.outcomes:
            return False

        # Check time range
        if self.start_time is not None and entry.timestamp < self.start_time:
            return False

        if self.end_time is not None and entry.timestamp > self.end_time:
            return False

        # Check story ID (in context)
        if self.story_id is not None:
            if entry.context.get("story_id") != self.story_id:
                return False

        # Check constitution principle
        if self.constitution_principle is not None:
            if self.constitution_principle not in entry.constitution_principles:
                return False

        return True

    def to_dict(self) -> dict[str, Any]:
        """Convert filter to dictionary."""
        result: dict[str, Any] = {}
        if self.agent_id is not None:
            result["agent_id"] = self.agent_id
        if self.agent_ids is not None:
            result["agent_ids"] = self.agent_ids
        if self.decision_types is not None:
            result["decision_types"] = [dt.value for dt in self.decision_types]
        if self.outcomes is not None:
            result["outcomes"] = [o.value for o in self.outcomes]
        if self.start_time is not None:
            result["start_time"] = self.start_time.isoformat()
        if self.end_time is not None:
            result["end_time"] = self.end_time.isoformat()
        if self.story_id is not None:
            result["story_id"] = self.story_id
        if self.constitution_principle is not None:
            result["constitution_principle"] = self.constitution_principle
        return result


@dataclass
class QueryResult:
    """
    Result of an audit trail query.

    Attributes:
        entries: List of matching entries
        total_count: Total number of matching entries (before pagination)
        page: Current page number
        page_size: Number of entries per page
        has_more: Whether there are more results
        query_time_ms: Time taken to execute query in milliseconds
    """

    entries: list[AuditTrailEntry] = field(default_factory=list)
    total_count: int = 0
    page: int = 1
    page_size: int = 100
    has_more: bool = False
    query_time_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "entries": [e.to_dict() for e in self.entries],
            "total_count": self.total_count,
            "page": self.page,
            "page_size": self.page_size,
            "has_more": self.has_more,
            "query_time_ms": self.query_time_ms,
        }


class AuditTrailQuery:
    """
    Query interface for the audit trail.

    Provides methods to query audit entries by various criteria.

    Example:
        >>> query = AuditTrailQuery(redis_client=my_redis)
        >>> result = query.by_agent("jarvis-001", days=7)
        >>> for entry in result.entries:
        ...     print(entry.decision_id, entry.decision_type)
    """

    # Redis key patterns (must match trail.py)
    ENTRIES_KEY = "governance:audit_trail:entries"
    INDEX_AGENT_PREFIX = "governance:audit_trail:index:agent"
    INDEX_TYPE_PREFIX = "governance:audit_trail:index:type"
    INDEX_OUTCOME_PREFIX = "governance:audit_trail:index:outcome"
    INDEX_TIME_KEY = "governance:audit_trail:index:time"

    def __init__(
        self,
        redis_client: RedisClient | None = None,
        in_memory_entries: list[AuditTrailEntry] | None = None,
    ):
        """
        Initialize query interface.

        Args:
            redis_client: Redis client for persistence
            in_memory_entries: Optional list of in-memory entries for testing
        """
        self._redis = redis_client
        self._in_memory_entries = in_memory_entries or []

    def _load_all_entries(self) -> list[AuditTrailEntry]:
        """Load all entries from Redis or in-memory."""
        if self._redis is not None:
            try:
                entries = self._redis.lrange(self.ENTRIES_KEY, 0, -1)
                return [
                    AuditTrailEntry.from_dict(json.loads(e.decode())) for e in entries
                ]
            except Exception as e:
                logger.error(f"Failed to load entries from Redis: {e}")

        return self._in_memory_entries

    def query(
        self,
        filter_criteria: QueryFilter | None = None,
        page: int = 1,
        page_size: int = 100,
        sort_order: SortOrder = SortOrder.DESC,
    ) -> QueryResult:
        """
        Execute a query with optional filtering and pagination.

        Args:
            filter_criteria: Optional filter criteria
            page: Page number (1-indexed)
            page_size: Number of entries per page
            sort_order: Sort order (asc or desc)

        Returns:
            QueryResult with matching entries
        """
        import time

        start_time = time.perf_counter()

        # Load entries
        all_entries = self._load_all_entries()

        # Apply filter
        if filter_criteria is not None:
            all_entries = [e for e in all_entries if filter_criteria.matches(e)]

        # Sort entries
        all_entries.sort(
            key=lambda e: e.timestamp, reverse=(sort_order == SortOrder.DESC)
        )

        # Paginate
        total_count = len(all_entries)
        offset = (page - 1) * page_size
        paginated = all_entries[offset : offset + page_size]
        has_more = offset + page_size < total_count

        query_time_ms = (time.perf_counter() - start_time) * 1000

        return QueryResult(
            entries=paginated,
            total_count=total_count,
            page=page,
            page_size=page_size,
            has_more=has_more,
            query_time_ms=query_time_ms,
        )

    def by_agent(
        self,
        agent_id: str,
        days: int | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> QueryResult:
        """
        Query entries by agent ID.

        Args:
            agent_id: Agent ID to filter by
            days: Number of days to look back (optional)
            start_time: Start of time range (optional)
            end_time: End of time range (optional)
            page: Page number
            page_size: Entries per page

        Returns:
            QueryResult with matching entries
        """
        # Calculate time range from days
        if days is not None:
            end_time = end_time or datetime.now(UTC)
            start_time = start_time or datetime.now(UTC) - timedelta(days=days)

        filter_criteria = QueryFilter(
            agent_id=agent_id,
            start_time=start_time,
            end_time=end_time,
        )

        return self.query(filter_criteria, page, page_size)

    def by_time_range(
        self,
        start_time: datetime,
        end_time: datetime,
        page: int = 1,
        page_size: int = 100,
    ) -> QueryResult:
        """
        Query entries by time range.

        Args:
            start_time: Start of time range
            end_time: End of time range
            page: Page number
            page_size: Entries per page

        Returns:
            QueryResult with matching entries
        """
        filter_criteria = QueryFilter(
            start_time=start_time,
            end_time=end_time,
        )

        return self.query(filter_criteria, page, page_size)

    def by_decision_type(
        self,
        decision_types: list[DecisionType],
        agent_id: str | None = None,
        days: int | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> QueryResult:
        """
        Query entries by decision type(s).

        Args:
            decision_types: List of decision types to filter by
            agent_id: Optional agent ID filter
            days: Optional days to look back
            page: Page number
            page_size: Entries per page

        Returns:
            QueryResult with matching entries
        """
        start_time = None
        end_time = None

        if days is not None:
            end_time = datetime.now(UTC)
            start_time = datetime.now(UTC) - timedelta(days=days)

        filter_criteria = QueryFilter(
            decision_types=decision_types,
            agent_id=agent_id,
            start_time=start_time,
            end_time=end_time,
        )

        return self.query(filter_criteria, page, page_size)

    def by_outcome(
        self,
        outcomes: list[DecisionOutcome],
        agent_id: str | None = None,
        days: int | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> QueryResult:
        """
        Query entries by outcome(s).

        Args:
            outcomes: List of outcomes to filter by
            agent_id: Optional agent ID filter
            days: Optional days to look back
            page: Page number
            page_size: Entries per page

        Returns:
            QueryResult with matching entries
        """
        start_time = None
        end_time = None

        if days is not None:
            end_time = datetime.now(UTC)
            start_time = datetime.now(UTC) - timedelta(days=days)

        filter_criteria = QueryFilter(
            outcomes=outcomes,
            agent_id=agent_id,
            start_time=start_time,
            end_time=end_time,
        )

        return self.query(filter_criteria, page, page_size)

    def by_story(
        self,
        story_id: str,
        page: int = 1,
        page_size: int = 100,
    ) -> QueryResult:
        """
        Query entries by story ID.

        Args:
            story_id: Story ID to filter by
            page: Page number
            page_size: Entries per page

        Returns:
            QueryResult with matching entries
        """
        filter_criteria = QueryFilter(story_id=story_id)
        return self.query(filter_criteria, page, page_size)

    def by_constitution_principle(
        self,
        principle: str,
        agent_id: str | None = None,
        days: int | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> QueryResult:
        """
        Query entries by constitution principle.

        Args:
            principle: Constitution principle to filter by (e.g., "P002")
            agent_id: Optional agent ID filter
            days: Optional days to look back
            page: Page number
            page_size: Entries per page

        Returns:
            QueryResult with matching entries
        """
        start_time = None
        end_time = None

        if days is not None:
            end_time = datetime.now(UTC)
            start_time = datetime.now(UTC) - timedelta(days=days)

        filter_criteria = QueryFilter(
            constitution_principle=principle,
            agent_id=agent_id,
            start_time=start_time,
            end_time=end_time,
        )

        return self.query(filter_criteria, page, page_size)

    def get_recent(
        self,
        limit: int = 100,
        agent_id: str | None = None,
    ) -> QueryResult:
        """
        Get most recent entries.

        Args:
            limit: Maximum number of entries to return
            agent_id: Optional agent ID filter

        Returns:
            QueryResult with recent entries
        """
        filter_criteria = QueryFilter(agent_id=agent_id) if agent_id else None
        return self.query(filter_criteria, page=1, page_size=limit)

    def count_by_agent(self, days: int = 30) -> dict[str, int]:
        """
        Count entries by agent.

        Args:
            days: Number of days to look back

        Returns:
            Dictionary mapping agent_id to count
        """
        entries = self._load_all_entries()

        cutoff = datetime.now(UTC) - timedelta(days=days)
        counts: dict[str, int] = {}

        for entry in entries:
            if entry.timestamp >= cutoff:
                counts[entry.agent_id] = counts.get(entry.agent_id, 0) + 1

        return counts

    def count_by_decision_type(self, days: int = 30) -> dict[str, int]:
        """
        Count entries by decision type.

        Args:
            days: Number of days to look back

        Returns:
            Dictionary mapping decision_type to count
        """
        entries = self._load_all_entries()

        cutoff = datetime.now(UTC) - timedelta(days=days)
        counts: dict[str, int] = {}

        for entry in entries:
            if entry.timestamp >= cutoff:
                key = entry.decision_type.value
                counts[key] = counts.get(key, 0) + 1

        return counts

    def count_by_outcome(self, days: int = 30) -> dict[str, int]:
        """
        Count entries by outcome.

        Args:
            days: Number of days to look back

        Returns:
            Dictionary mapping outcome to count
        """
        entries = self._load_all_entries()

        cutoff = datetime.now(UTC) - timedelta(days=days)
        counts: dict[str, int] = {}

        for entry in entries:
            if entry.timestamp >= cutoff:
                key = entry.outcome.value
                counts[key] = counts.get(key, 0) + 1

        return counts
