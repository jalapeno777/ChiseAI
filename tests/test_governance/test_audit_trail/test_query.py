"""
Tests for audit trail query interface.

ST-GOV-009: Decision Audit Trail Export
"""

from datetime import UTC, datetime, timedelta

import pytest

from src.governance.audit_trail.decision import DecisionOutcome, DecisionType
from src.governance.audit_trail.query import (
    AuditTrailQuery,
    QueryFilter,
    QueryResult,
    SortOrder,
)
from src.governance.audit_trail.trail import AuditTrail, AuditTrailEntry


class TestQueryFilter:
    """Tests for QueryFilter."""

    def test_empty_filter_matches_all(self):
        """Test that an empty filter matches all entries."""
        filter_criteria = QueryFilter()

        entry = AuditTrailEntry(
            decision_id="test-001",
            timestamp=datetime.now(UTC),
            agent_id="any-agent",
            decision_type=DecisionType.PR_MERGE,
            context={},
            rationale="test",
            outcome=DecisionOutcome.SUCCESS,
            constitution_principles=[],
            hash="sha256:test",
            prev_hash="sha256:genesis",
        )

        assert filter_criteria.matches(entry) is True

    def test_filter_by_agent_id(self):
        """Test filtering by agent ID."""
        filter_criteria = QueryFilter(agent_id="jarvis-001")

        matching = AuditTrailEntry(
            decision_id="test-001",
            timestamp=datetime.now(UTC),
            agent_id="jarvis-001",
            decision_type=DecisionType.PR_MERGE,
            context={},
            rationale="test",
            outcome=DecisionOutcome.SUCCESS,
            constitution_principles=[],
            hash="sha256:test",
            prev_hash="sha256:genesis",
        )

        non_matching = AuditTrailEntry(
            decision_id="test-002",
            timestamp=datetime.now(UTC),
            agent_id="merlin-001",
            decision_type=DecisionType.PR_MERGE,
            context={},
            rationale="test",
            outcome=DecisionOutcome.SUCCESS,
            constitution_principles=[],
            hash="sha256:test",
            prev_hash="sha256:genesis",
        )

        assert filter_criteria.matches(matching) is True
        assert filter_criteria.matches(non_matching) is False

    def test_filter_by_agent_ids(self):
        """Test filtering by multiple agent IDs."""
        filter_criteria = QueryFilter(agent_ids=["jarvis-001", "merlin-001"])

        jarvis_entry = AuditTrailEntry(
            decision_id="test-001",
            timestamp=datetime.now(UTC),
            agent_id="jarvis-001",
            decision_type=DecisionType.PR_MERGE,
            context={},
            rationale="test",
            outcome=DecisionOutcome.SUCCESS,
            constitution_principles=[],
            hash="sha256:test",
            prev_hash="sha256:genesis",
        )

        merlin_entry = AuditTrailEntry(
            decision_id="test-002",
            timestamp=datetime.now(UTC),
            agent_id="merlin-001",
            decision_type=DecisionType.PR_MERGE,
            context={},
            rationale="test",
            outcome=DecisionOutcome.SUCCESS,
            constitution_principles=[],
            hash="sha256:test",
            prev_hash="sha256:genesis",
        )

        other_entry = AuditTrailEntry(
            decision_id="test-003",
            timestamp=datetime.now(UTC),
            agent_id="other-001",
            decision_type=DecisionType.PR_MERGE,
            context={},
            rationale="test",
            outcome=DecisionOutcome.SUCCESS,
            constitution_principles=[],
            hash="sha256:test",
            prev_hash="sha256:genesis",
        )

        assert filter_criteria.matches(jarvis_entry) is True
        assert filter_criteria.matches(merlin_entry) is True
        assert filter_criteria.matches(other_entry) is False

    def test_filter_by_decision_types(self):
        """Test filtering by decision types."""
        filter_criteria = QueryFilter(
            decision_types=[DecisionType.PR_MERGE, DecisionType.PR_REJECT]
        )

        merge_entry = AuditTrailEntry(
            decision_id="test-001",
            timestamp=datetime.now(UTC),
            agent_id="jarvis",
            decision_type=DecisionType.PR_MERGE,
            context={},
            rationale="test",
            outcome=DecisionOutcome.SUCCESS,
            constitution_principles=[],
            hash="sha256:test",
            prev_hash="sha256:genesis",
        )

        reject_entry = AuditTrailEntry(
            decision_id="test-002",
            timestamp=datetime.now(UTC),
            agent_id="jarvis",
            decision_type=DecisionType.PR_REJECT,
            context={},
            rationale="test",
            outcome=DecisionOutcome.FAILURE,
            constitution_principles=[],
            hash="sha256:test",
            prev_hash="sha256:genesis",
        )

        other_entry = AuditTrailEntry(
            decision_id="test-003",
            timestamp=datetime.now(UTC),
            agent_id="jarvis",
            decision_type=DecisionType.TASK_COMPLETE,
            context={},
            rationale="test",
            outcome=DecisionOutcome.SUCCESS,
            constitution_principles=[],
            hash="sha256:test",
            prev_hash="sha256:genesis",
        )

        assert filter_criteria.matches(merge_entry) is True
        assert filter_criteria.matches(reject_entry) is True
        assert filter_criteria.matches(other_entry) is False

    def test_filter_by_outcomes(self):
        """Test filtering by outcomes."""
        filter_criteria = QueryFilter(outcomes=[DecisionOutcome.SUCCESS])

        success_entry = AuditTrailEntry(
            decision_id="test-001",
            timestamp=datetime.now(UTC),
            agent_id="jarvis",
            decision_type=DecisionType.PR_MERGE,
            context={},
            rationale="test",
            outcome=DecisionOutcome.SUCCESS,
            constitution_principles=[],
            hash="sha256:test",
            prev_hash="sha256:genesis",
        )

        failure_entry = AuditTrailEntry(
            decision_id="test-002",
            timestamp=datetime.now(UTC),
            agent_id="jarvis",
            decision_type=DecisionType.PR_MERGE,
            context={},
            rationale="test",
            outcome=DecisionOutcome.FAILURE,
            constitution_principles=[],
            hash="sha256:test",
            prev_hash="sha256:genesis",
        )

        assert filter_criteria.matches(success_entry) is True
        assert filter_criteria.matches(failure_entry) is False

    def test_filter_by_time_range(self):
        """Test filtering by time range."""
        now = datetime.now(UTC)
        filter_criteria = QueryFilter(
            start_time=now - timedelta(hours=2),
            end_time=now - timedelta(hours=1),
        )

        old_entry = AuditTrailEntry(
            decision_id="test-001",
            timestamp=now - timedelta(hours=3),
            agent_id="jarvis",
            decision_type=DecisionType.PR_MERGE,
            context={},
            rationale="test",
            outcome=DecisionOutcome.SUCCESS,
            constitution_principles=[],
            hash="sha256:test",
            prev_hash="sha256:genesis",
        )

        in_range_entry = AuditTrailEntry(
            decision_id="test-002",
            timestamp=now - timedelta(hours=1.5),
            agent_id="jarvis",
            decision_type=DecisionType.PR_MERGE,
            context={},
            rationale="test",
            outcome=DecisionOutcome.SUCCESS,
            constitution_principles=[],
            hash="sha256:test",
            prev_hash="sha256:genesis",
        )

        new_entry = AuditTrailEntry(
            decision_id="test-003",
            timestamp=now - timedelta(minutes=30),
            agent_id="jarvis",
            decision_type=DecisionType.PR_MERGE,
            context={},
            rationale="test",
            outcome=DecisionOutcome.SUCCESS,
            constitution_principles=[],
            hash="sha256:test",
            prev_hash="sha256:genesis",
        )

        assert filter_criteria.matches(old_entry) is False
        assert filter_criteria.matches(in_range_entry) is True
        assert filter_criteria.matches(new_entry) is False

    def test_filter_by_story_id(self):
        """Test filtering by story ID in context."""
        filter_criteria = QueryFilter(story_id="ST-GOV-009")

        matching = AuditTrailEntry(
            decision_id="test-001",
            timestamp=datetime.now(UTC),
            agent_id="jarvis",
            decision_type=DecisionType.PR_MERGE,
            context={"story_id": "ST-GOV-009"},
            rationale="test",
            outcome=DecisionOutcome.SUCCESS,
            constitution_principles=[],
            hash="sha256:test",
            prev_hash="sha256:genesis",
        )

        non_matching = AuditTrailEntry(
            decision_id="test-002",
            timestamp=datetime.now(UTC),
            agent_id="jarvis",
            decision_type=DecisionType.PR_MERGE,
            context={"story_id": "ST-OTHER"},
            rationale="test",
            outcome=DecisionOutcome.SUCCESS,
            constitution_principles=[],
            hash="sha256:test",
            prev_hash="sha256:genesis",
        )

        assert filter_criteria.matches(matching) is True
        assert filter_criteria.matches(non_matching) is False

    def test_filter_by_constitution_principle(self):
        """Test filtering by constitution principle."""
        filter_criteria = QueryFilter(constitution_principle="P002")

        matching = AuditTrailEntry(
            decision_id="test-001",
            timestamp=datetime.now(UTC),
            agent_id="jarvis",
            decision_type=DecisionType.PR_MERGE,
            context={},
            rationale="test",
            outcome=DecisionOutcome.SUCCESS,
            constitution_principles=["P002", "P003"],
            hash="sha256:test",
            prev_hash="sha256:genesis",
        )

        non_matching = AuditTrailEntry(
            decision_id="test-002",
            timestamp=datetime.now(UTC),
            agent_id="jarvis",
            decision_type=DecisionType.PR_MERGE,
            context={},
            rationale="test",
            outcome=DecisionOutcome.SUCCESS,
            constitution_principles=["P001"],
            hash="sha256:test",
            prev_hash="sha256:genesis",
        )

        assert filter_criteria.matches(matching) is True
        assert filter_criteria.matches(non_matching) is False

    def test_combined_filters(self):
        """Test combining multiple filters (AND logic)."""
        filter_criteria = QueryFilter(
            agent_id="jarvis-001",
            decision_types=[DecisionType.PR_MERGE],
            outcomes=[DecisionOutcome.SUCCESS],
        )

        # All criteria match
        all_match = AuditTrailEntry(
            decision_id="test-001",
            timestamp=datetime.now(UTC),
            agent_id="jarvis-001",
            decision_type=DecisionType.PR_MERGE,
            context={},
            rationale="test",
            outcome=DecisionOutcome.SUCCESS,
            constitution_principles=[],
            hash="sha256:test",
            prev_hash="sha256:genesis",
        )

        # Agent doesn't match
        wrong_agent = AuditTrailEntry(
            decision_id="test-002",
            timestamp=datetime.now(UTC),
            agent_id="other",
            decision_type=DecisionType.PR_MERGE,
            context={},
            rationale="test",
            outcome=DecisionOutcome.SUCCESS,
            constitution_principles=[],
            hash="sha256:test",
            prev_hash="sha256:genesis",
        )

        # Type doesn't match
        wrong_type = AuditTrailEntry(
            decision_id="test-003",
            timestamp=datetime.now(UTC),
            agent_id="jarvis-001",
            decision_type=DecisionType.TASK_COMPLETE,
            context={},
            rationale="test",
            outcome=DecisionOutcome.SUCCESS,
            constitution_principles=[],
            hash="sha256:test",
            prev_hash="sha256:genesis",
        )

        assert filter_criteria.matches(all_match) is True
        assert filter_criteria.matches(wrong_agent) is False
        assert filter_criteria.matches(wrong_type) is False

    def test_to_dict(self):
        """Test filter serialization."""
        filter_criteria = QueryFilter(
            agent_id="jarvis-001",
            decision_types=[DecisionType.PR_MERGE],
            outcomes=[DecisionOutcome.SUCCESS],
        )

        data = filter_criteria.to_dict()

        assert data["agent_id"] == "jarvis-001"
        assert data["decision_types"] == ["pr_merge"]
        assert data["outcomes"] == ["success"]


class TestQueryResult:
    """Tests for QueryResult."""

    def test_empty_result(self):
        """Test empty result."""
        result = QueryResult()

        assert result.entries == []
        assert result.total_count == 0
        assert result.has_more is False

    def test_result_to_dict(self):
        """Test result serialization."""
        entry = AuditTrailEntry(
            decision_id="test-001",
            timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            agent_id="jarvis",
            decision_type=DecisionType.PR_MERGE,
            context={},
            rationale="test",
            outcome=DecisionOutcome.SUCCESS,
            constitution_principles=[],
            hash="sha256:test",
            prev_hash="sha256:genesis",
        )

        result = QueryResult(
            entries=[entry],
            total_count=1,
            page=1,
            page_size=100,
            has_more=False,
            query_time_ms=5.5,
        )

        data = result.to_dict()

        assert data["total_count"] == 1
        assert data["page"] == 1
        assert data["has_more"] is False
        assert len(data["entries"]) == 1
        assert data["query_time_ms"] == 5.5


class TestAuditTrailQuery:
    """Tests for AuditTrailQuery class."""

    @pytest.fixture
    def populated_trail(self):
        """Create a trail with sample entries."""
        trail = AuditTrail()

        # Log various entries
        trail.log_decision(
            agent_id="jarvis-001",
            decision_type=DecisionType.PR_MERGE,
            context={"pr_id": 100},
            rationale="PR merge by jarvis",
            outcome=DecisionOutcome.SUCCESS,
            constitution_principles=["P002"],
        )

        trail.log_decision(
            agent_id="merlin-001",
            decision_type=DecisionType.PR_REJECT,
            context={"pr_id": 101},
            rationale="PR reject by merlin",
            outcome=DecisionOutcome.FAILURE,
            constitution_principles=["P003"],
        )

        trail.log_decision(
            agent_id="jarvis-001",
            decision_type=DecisionType.TASK_DELEGATE,
            context={"task": "implement"},
            rationale="Task delegated by jarvis",
            outcome=DecisionOutcome.SUCCESS,
            constitution_principles=["P005"],
        )

        return trail

    def test_query_all_entries(self, populated_trail):
        """Test querying all entries."""
        query = AuditTrailQuery(in_memory_entries=populated_trail._entries)
        result = query.query()

        assert result.total_count == 3
        assert len(result.entries) == 3

    def test_query_by_agent(self, populated_trail):
        """Test querying by agent."""
        query = AuditTrailQuery(in_memory_entries=populated_trail._entries)
        result = query.by_agent("jarvis-001")

        assert result.total_count == 2
        for entry in result.entries:
            assert entry.agent_id == "jarvis-001"

    def test_query_by_decision_type(self, populated_trail):
        """Test querying by decision type."""
        query = AuditTrailQuery(in_memory_entries=populated_trail._entries)
        result = query.by_decision_type([DecisionType.PR_MERGE, DecisionType.PR_REJECT])

        assert result.total_count == 2
        for entry in result.entries:
            assert entry.decision_type in [
                DecisionType.PR_MERGE,
                DecisionType.PR_REJECT,
            ]

    def test_query_by_outcome(self, populated_trail):
        """Test querying by outcome."""
        query = AuditTrailQuery(in_memory_entries=populated_trail._entries)
        result = query.by_outcome([DecisionOutcome.SUCCESS])

        assert result.total_count == 2
        for entry in result.entries:
            assert entry.outcome == DecisionOutcome.SUCCESS

    def test_query_pagination(self, populated_trail):
        """Test query pagination."""
        query = AuditTrailQuery(in_memory_entries=populated_trail._entries)

        # Get first page
        page1 = query.query(page=1, page_size=2)
        assert len(page1.entries) == 2
        assert page1.has_more is True

        # Get second page
        page2 = query.query(page=2, page_size=2)
        assert len(page2.entries) == 1
        assert page2.has_more is False

    def test_query_sort_order(self, populated_trail):
        """Test query sort order."""
        query = AuditTrailQuery(in_memory_entries=populated_trail._entries)

        # Descending (newest first)
        desc = query.query(sort_order=SortOrder.DESC)
        desc_times = [e.timestamp for e in desc.entries]
        assert desc_times == sorted(desc_times, reverse=True)

        # Ascending (oldest first)
        asc = query.query(sort_order=SortOrder.ASC)
        asc_times = [e.timestamp for e in asc.entries]
        assert asc_times == sorted(asc_times)

    def test_get_recent(self, populated_trail):
        """Test getting recent entries."""
        query = AuditTrailQuery(in_memory_entries=populated_trail._entries)
        result = query.get_recent(limit=2)

        assert len(result.entries) == 2
        # Should be the newest entries (lpush stores newest first)
        assert result.entries[0].timestamp >= result.entries[1].timestamp

    def test_count_by_agent(self, populated_trail):
        """Test counting entries by agent."""
        query = AuditTrailQuery(in_memory_entries=populated_trail._entries)
        counts = query.count_by_agent()

        assert counts.get("jarvis-001") == 2
        assert counts.get("merlin-001") == 1

    def test_count_by_decision_type(self, populated_trail):
        """Test counting entries by decision type."""
        query = AuditTrailQuery(in_memory_entries=populated_trail._entries)
        counts = query.count_by_decision_type()

        assert counts.get("pr_merge") == 1
        assert counts.get("pr_reject") == 1
        assert counts.get("task_delegate") == 1

    def test_count_by_outcome(self, populated_trail):
        """Test counting entries by outcome."""
        query = AuditTrailQuery(in_memory_entries=populated_trail._entries)
        counts = query.count_by_outcome()

        assert counts.get("success") == 2
        assert counts.get("failure") == 1
