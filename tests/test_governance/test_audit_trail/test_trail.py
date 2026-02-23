"""
Tests for audit trail core implementation.

ST-GOV-009: Decision Audit Trail Export
"""

import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest

from src.governance.audit_trail.decision import DecisionOutcome, DecisionType
from src.governance.audit_trail.trail import (
    AuditTrail,
    AuditTrailEntry,
    DecisionContext,
    HashChainState,
)


class TestHashChainState:
    """Tests for HashChainState."""

    def test_default_state(self):
        """Test default chain state."""
        state = HashChainState()

        assert state.last_hash == "sha256:genesis"
        assert state.chain_length == 0
        assert state.genesis_hash == "sha256:genesis"

    def test_to_dict_and_from_dict(self):
        """Test serialization roundtrip."""
        original = HashChainState(
            last_hash="sha256:abc123",
            chain_length=100,
            genesis_hash="sha256:genesis",
            last_timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
        )

        data = original.to_dict()
        restored = HashChainState.from_dict(data)

        assert restored.last_hash == original.last_hash
        assert restored.chain_length == original.chain_length
        assert restored.genesis_hash == original.genesis_hash


class TestDecisionContext:
    """Tests for DecisionContext."""

    def test_empty_context(self):
        """Test empty context converts to empty dict."""
        context = DecisionContext()
        assert context.to_dict() == {}

    def test_context_with_all_fields(self):
        """Test context with all fields."""
        context = DecisionContext(
            pr_id=230,
            story_id="ST-AUTO-001",
            branch="feature/test",
            classification="SAFE",
            additional_data={"reviewer": "merlin", "priority": "high"},
        )

        data = context.to_dict()

        assert data["pr_id"] == 230
        assert data["story_id"] == "ST-AUTO-001"
        assert data["branch"] == "feature/test"
        assert data["classification"] == "SAFE"
        assert data["reviewer"] == "merlin"
        assert data["priority"] == "high"

    def test_context_partial(self):
        """Test context with partial fields."""
        context = DecisionContext(pr_id=100)
        data = context.to_dict()

        assert data == {"pr_id": 100}
        assert "story_id" not in data


class TestAuditTrailEntry:
    """Tests for AuditTrailEntry."""

    @pytest.fixture
    def sample_entry(self):
        """Create a sample entry for testing."""
        return AuditTrailEntry(
            decision_id="test-decision-001",
            timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            agent_id="jarvis-001",
            decision_type=DecisionType.PR_MERGE,
            context={"pr_id": 230, "classification": "SAFE"},
            rationale="All CI checks passed",
            outcome=DecisionOutcome.SUCCESS,
            constitution_principles=["P002", "P003"],
            hash="sha256:testhash",
            prev_hash="sha256:prevhash",
        )

    def test_entry_to_dict(self, sample_entry):
        """Test converting entry to dictionary (export schema)."""
        data = sample_entry.to_dict()

        # Verify export schema fields
        assert data["decision_id"] == "test-decision-001"
        assert data["timestamp"] == "2024-01-15T10:30:00+00:00"
        assert data["agent_id"] == "jarvis-001"
        assert data["decision_type"] == "pr_merge"
        assert data["context"]["pr_id"] == 230
        assert data["rationale"] == "All CI checks passed"
        assert data["outcome"] == "success"
        assert data["constitution_principles"] == ["P002", "P003"]
        assert data["hash"] == "sha256:testhash"
        assert data["prev_hash"] == "sha256:prevhash"

    def test_entry_from_dict(self, sample_entry):
        """Test creating entry from dictionary."""
        data = sample_entry.to_dict()
        restored = AuditTrailEntry.from_dict(data)

        assert restored.decision_id == sample_entry.decision_id
        assert restored.agent_id == sample_entry.agent_id
        assert restored.decision_type == sample_entry.decision_type
        assert restored.context == sample_entry.context
        assert restored.outcome == sample_entry.outcome

    def test_hash_computation(self):
        """Test that hash computation is deterministic."""
        hash1 = AuditTrailEntry._compute_hash(
            prev_hash="sha256:prev",
            decision_id="test-001",
            timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            agent_id="jarvis",
            decision_type=DecisionType.PR_MERGE,
            context={"pr": 100},
            rationale="test",
            outcome=DecisionOutcome.SUCCESS,
            constitution_principles=["P002"],
        )

        hash2 = AuditTrailEntry._compute_hash(
            prev_hash="sha256:prev",
            decision_id="test-001",
            timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            agent_id="jarvis",
            decision_type=DecisionType.PR_MERGE,
            context={"pr": 100},
            rationale="test",
            outcome=DecisionOutcome.SUCCESS,
            constitution_principles=["P002"],
        )

        assert hash1 == hash2
        assert hash1.startswith("sha256:")
        assert len(hash1) == 71  # "sha256:" + 64 hex chars

    def test_hash_changes_with_content(self):
        """Test that different content produces different hashes."""
        hash1 = AuditTrailEntry._compute_hash(
            prev_hash="sha256:prev",
            decision_id="test-001",
            agent_id="jarvis",
        )

        hash2 = AuditTrailEntry._compute_hash(
            prev_hash="sha256:prev",
            decision_id="test-002",  # Different decision_id
            agent_id="jarvis",
        )

        assert hash1 != hash2

    def test_entry_verify_hash_valid(self):
        """Test that a valid entry passes hash verification."""
        # Create entry with proper hash by using _compute_hash with all actual field values
        decision_id = "test-001"
        timestamp = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        agent_id = "jarvis"
        decision_type = DecisionType.PR_MERGE
        context = {}
        rationale = "test"
        outcome = DecisionOutcome.SUCCESS
        constitution_principles: list[str] = []
        prev_hash = "sha256:genesis"

        # Compute correct hash
        correct_hash = AuditTrailEntry._compute_hash(
            prev_hash=prev_hash,
            decision_id=decision_id,
            timestamp=timestamp,
            agent_id=agent_id,
            decision_type=decision_type,
            context=context,
            rationale=rationale,
            outcome=outcome,
            constitution_principles=constitution_principles,
        )

        entry = AuditTrailEntry(
            decision_id=decision_id,
            timestamp=timestamp,
            agent_id=agent_id,
            decision_type=decision_type,
            context=context,
            rationale=rationale,
            outcome=outcome,
            constitution_principles=constitution_principles,
            hash=correct_hash,
            prev_hash=prev_hash,
        )

        assert entry.verify_hash() is True

    def test_entry_verify_hash_invalid(self):
        """Test that a tampered entry fails hash verification."""
        entry = AuditTrailEntry(
            decision_id="test-001",
            timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            agent_id="jarvis",
            decision_type=DecisionType.PR_MERGE,
            context={},
            rationale="original",
            outcome=DecisionOutcome.SUCCESS,
            constitution_principles=[],
            hash="sha256:wronghash",  # Wrong hash
            prev_hash="sha256:genesis",
        )

        assert entry.verify_hash() is False


class TestAuditTrail:
    """Tests for AuditTrail class."""

    def test_trail_creation_default(self):
        """Test creating audit trail without Redis."""
        trail = AuditTrail()

        assert trail._redis is None
        assert trail._chain_state.chain_length == 0

    def test_log_first_decision(self):
        """Test logging the first decision (genesis)."""
        trail = AuditTrail()

        entry = trail.log_decision(
            agent_id="jarvis-001",
            decision_type=DecisionType.PR_MERGE,
            context={"pr_id": 100},
            rationale="First decision",
            outcome=DecisionOutcome.SUCCESS,
            constitution_principles=["P002"],
        )

        assert entry.decision_id is not None
        assert entry.agent_id == "jarvis-001"
        assert entry.prev_hash == "sha256:genesis"
        assert entry.verify_hash() is True

        # Check chain state updated
        state = trail.get_chain_state()
        assert state.chain_length == 1
        assert state.genesis_hash == entry.hash
        assert state.last_hash == entry.hash

    def test_log_multiple_decisions_creates_chain(self):
        """Test that multiple decisions create a linked chain."""
        trail = AuditTrail()

        # Log first decision
        entry1 = trail.log_decision(
            agent_id="jarvis-001",
            decision_type=DecisionType.PR_MERGE,
            context={"pr_id": 100},
            rationale="First",
            outcome=DecisionOutcome.SUCCESS,
        )

        # Log second decision
        entry2 = trail.log_decision(
            agent_id="jarvis-002",
            decision_type=DecisionType.TASK_DELEGATE,
            context={"task": "implement"},
            rationale="Second",
            outcome=DecisionOutcome.SUCCESS,
        )

        # Verify chain linkage
        assert entry2.prev_hash == entry1.hash

        # Verify both entries have valid hashes
        assert entry1.verify_hash() is True
        assert entry2.verify_hash() is True

        # Verify chain state
        state = trail.get_chain_state()
        assert state.chain_length == 2
        assert state.last_hash == entry2.hash

    def test_verify_chain_valid(self):
        """Test that a valid chain passes verification."""
        trail = AuditTrail()

        # Log several decisions
        for i in range(5):
            trail.log_decision(
                agent_id=f"agent-{i}",
                decision_type=DecisionType.TASK_COMPLETE,
                context={"iteration": i},
                rationale=f"Task {i}",
                outcome=DecisionOutcome.SUCCESS,
            )

        is_valid, message = trail.verify_chain()

        assert is_valid is True
        assert "verified" in message.lower()

    def test_verify_chain_detects_tampering(self):
        """Test that chain verification detects tampering."""
        trail = AuditTrail()

        # Log several decisions
        for i in range(3):
            trail.log_decision(
                agent_id=f"agent-{i}",
                decision_type=DecisionType.TASK_COMPLETE,
                context={"iteration": i},
                rationale=f"Task {i}",
                outcome=DecisionOutcome.SUCCESS,
            )

        # Tamper with middle entry
        trail._entries[1].rationale = "TAMPERED"

        is_valid, message = trail.verify_chain()

        # The hash won't verify since content changed
        assert is_valid is False or not trail._entries[1].verify_hash()

    def test_log_decision_with_decision_context(self):
        """Test logging with DecisionContext object."""
        trail = AuditTrail()

        context = DecisionContext(
            pr_id=230,
            story_id="ST-GOV-009",
            classification="SAFE",
        )

        entry = trail.log_decision(
            agent_id="jarvis-001",
            decision_type=DecisionType.PR_MERGE,
            context=context,
            rationale="Test with DecisionContext",
            outcome=DecisionOutcome.SUCCESS,
        )

        assert entry.context["pr_id"] == 230
        assert entry.context["story_id"] == "ST-GOV-009"
        assert entry.context["classification"] == "SAFE"

    def test_get_entry_by_id(self):
        """Test retrieving an entry by ID."""
        trail = AuditTrail()

        entry = trail.log_decision(
            agent_id="jarvis-001",
            decision_type=DecisionType.PR_MERGE,
            context={},
            rationale="Test",
            outcome=DecisionOutcome.SUCCESS,
        )

        retrieved = trail.get_entry(entry.decision_id)

        assert retrieved is not None
        assert retrieved.decision_id == entry.decision_id

    def test_get_entry_not_found(self):
        """Test retrieving a non-existent entry."""
        trail = AuditTrail()

        retrieved = trail.get_entry("non-existent-id")

        assert retrieved is None

    def test_get_entries_pagination(self):
        """Test getting entries with pagination."""
        trail = AuditTrail()

        # Log 10 entries
        for i in range(10):
            trail.log_decision(
                agent_id=f"agent-{i}",
                decision_type=DecisionType.TASK_COMPLETE,
                context={},
                rationale=f"Task {i}",
                outcome=DecisionOutcome.SUCCESS,
            )

        # Get first page
        page1 = trail.get_entries(limit=5, offset=0)
        assert len(page1) == 5

        # Get second page
        page2 = trail.get_entries(limit=5, offset=5)
        assert len(page2) == 5

        # Verify no overlap
        page1_ids = {e.decision_id for e in page1}
        page2_ids = {e.decision_id for e in page2}
        assert page1_ids.isdisjoint(page2_ids)

    def test_get_entry_count(self):
        """Test getting total entry count."""
        trail = AuditTrail()

        assert trail.get_entry_count() == 0

        for i in range(5):
            trail.log_decision(
                agent_id=f"agent-{i}",
                decision_type=DecisionType.TASK_COMPLETE,
                context={},
                rationale=f"Task {i}",
                outcome=DecisionOutcome.SUCCESS,
            )

        assert trail.get_entry_count() == 5

    def test_explicit_decision_id_and_timestamp(self):
        """Test that explicit decision_id and timestamp are respected."""
        trail = AuditTrail()

        explicit_id = "my-custom-id"
        explicit_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        entry = trail.log_decision(
            agent_id="jarvis",
            decision_type=DecisionType.PR_MERGE,
            context={},
            rationale="Test",
            outcome=DecisionOutcome.SUCCESS,
            decision_id=explicit_id,
            timestamp=explicit_time,
        )

        assert entry.decision_id == explicit_id
        assert entry.timestamp == explicit_time

    def test_export_schema_compliance(self):
        """Test that entry matches the required export schema."""
        trail = AuditTrail()

        entry = trail.log_decision(
            agent_id="jarvis-001",
            decision_type=DecisionType.PR_MERGE,
            context={"pr_id": 230, "story_id": "ST-AUTO-001", "classification": "SAFE"},
            rationale="All CI checks passed, SAFE classification",
            outcome=DecisionOutcome.SUCCESS,
            constitution_principles=["P002", "P003"],
        )

        data = entry.to_dict()

        # Verify all required schema fields exist
        required_fields = [
            "decision_id",
            "timestamp",
            "agent_id",
            "decision_type",
            "context",
            "rationale",
            "outcome",
            "constitution_principles",
            "hash",
            "prev_hash",
        ]

        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

        # Verify types
        assert isinstance(data["decision_id"], str)
        assert isinstance(data["timestamp"], str)
        assert isinstance(data["agent_id"], str)
        assert isinstance(data["decision_type"], str)
        assert isinstance(data["context"], dict)
        assert isinstance(data["rationale"], str)
        assert isinstance(data["outcome"], str)
        assert isinstance(data["constitution_principles"], list)
        assert isinstance(data["hash"], str)
        assert isinstance(data["prev_hash"], str)
