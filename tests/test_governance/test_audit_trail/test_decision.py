"""
Tests for audit trail decision models.

ST-GOV-009: Decision Audit Trail Export
"""

from datetime import UTC, datetime

from src.governance.audit_trail.decision import (
    ConstitutionPrinciple,
    Decision,
    DecisionOutcome,
    DecisionType,
)


class TestDecisionType:
    """Tests for DecisionType enum."""

    def test_decision_type_values(self):
        """Test that all expected decision types exist."""
        assert DecisionType.PR_MERGE == "pr_merge"
        assert DecisionType.PR_REJECT == "pr_reject"
        assert DecisionType.BRANCH_CREATE == "branch_create"
        assert DecisionType.DEPLOY_PROMOTE == "deploy_promote"
        assert DecisionType.TASK_DELEGATE == "task_delegate"
        assert DecisionType.QUALITY_GATE_PASS == "quality_gate_pass"
        assert DecisionType.INCIDENT_ESCALATE == "incident_escalate"
        assert DecisionType.CONSTITUTION_VIOLATION == "constitution_violation"

    def test_decision_type_is_string(self):
        """Test that DecisionType is a string enum."""
        assert isinstance(DecisionType.PR_MERGE.value, str)


class TestDecisionOutcome:
    """Tests for DecisionOutcome enum."""

    def test_outcome_values(self):
        """Test that all expected outcomes exist."""
        assert DecisionOutcome.SUCCESS == "success"
        assert DecisionOutcome.FAILURE == "failure"
        assert DecisionOutcome.PENDING == "pending"
        assert DecisionOutcome.ROLLED_BACK == "rolled_back"
        assert DecisionOutcome.ESCALATED == "escalated"
        assert DecisionOutcome.DEFERRED == "deferred"


class TestConstitutionPrinciple:
    """Tests for ConstitutionPrinciple enum."""

    def test_principle_values(self):
        """Test that all expected principles exist."""
        assert ConstitutionPrinciple.P001 == "P001"
        assert ConstitutionPrinciple.P002 == "P002"
        assert ConstitutionPrinciple.P003 == "P003"
        assert ConstitutionPrinciple.P010 == "P010"


class TestDecision:
    """Tests for Decision model."""

    def test_decision_creation_default(self):
        """Test creating a decision with defaults."""
        decision = Decision()

        assert decision.decision_id is not None
        assert decision.agent_id == "unknown"
        assert decision.decision_type == DecisionType.TASK_COMPLETE
        assert decision.outcome == DecisionOutcome.PENDING
        assert decision.context == {}
        assert decision.rationale == ""
        assert decision.constitution_principles == []

    def test_decision_creation_full(self):
        """Test creating a decision with all fields."""
        timestamp = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)

        decision = Decision(
            decision_id="test-decision-001",
            timestamp=timestamp,
            agent_id="jarvis-001",
            decision_type=DecisionType.PR_MERGE,
            context={"pr_id": 230, "story_id": "ST-AUTO-001"},
            rationale="All CI checks passed",
            outcome=DecisionOutcome.SUCCESS,
            constitution_principles=[
                ConstitutionPrinciple.P002,
                ConstitutionPrinciple.P003,
            ],
            story_id="ST-AUTO-001",
            metadata={"reviewer": "merlin"},
        )

        assert decision.decision_id == "test-decision-001"
        assert decision.timestamp == timestamp
        assert decision.agent_id == "jarvis-001"
        assert decision.decision_type == DecisionType.PR_MERGE
        assert decision.context["pr_id"] == 230
        assert decision.rationale == "All CI checks passed"
        assert decision.outcome == DecisionOutcome.SUCCESS
        assert len(decision.constitution_principles) == 2
        assert decision.story_id == "ST-AUTO-001"
        assert decision.metadata["reviewer"] == "merlin"

    def test_decision_to_dict(self):
        """Test converting decision to dictionary."""
        decision = Decision(
            decision_id="test-001",
            agent_id="jarvis-001",
            decision_type=DecisionType.PR_MERGE,
            context={"pr_id": 100},
            rationale="Test rationale",
            outcome=DecisionOutcome.SUCCESS,
            constitution_principles=[ConstitutionPrinciple.P002],
        )

        data = decision.to_dict()

        assert data["decision_id"] == "test-001"
        assert data["agent_id"] == "jarvis-001"
        assert data["decision_type"] == "pr_merge"
        assert data["context"]["pr_id"] == 100
        assert data["rationale"] == "Test rationale"
        assert data["outcome"] == "success"
        assert data["constitution_principles"] == ["P002"]
        assert "timestamp" in data

    def test_decision_from_dict(self):
        """Test creating decision from dictionary."""
        data = {
            "decision_id": "test-002",
            "timestamp": "2024-01-15T10:30:00+00:00",
            "agent_id": "jarvis-002",
            "decision_type": "task_delegate",
            "context": {"task": "implement"},
            "rationale": "Delegated to worker",
            "outcome": "success",
            "constitution_principles": ["P005"],
            "story_id": "ST-TEST",
            "metadata": {},
        }

        decision = Decision.from_dict(data)

        assert decision.decision_id == "test-002"
        assert decision.agent_id == "jarvis-002"
        assert decision.decision_type == DecisionType.TASK_DELEGATE
        assert decision.outcome == DecisionOutcome.SUCCESS
        assert decision.constitution_principles == [ConstitutionPrinciple.P005]
        assert decision.story_id == "ST-TEST"

    def test_decision_roundtrip(self):
        """Test that to_dict and from_dict are inverses."""
        original = Decision(
            decision_id="roundtrip-001",
            agent_id="jarvis-001",
            decision_type=DecisionType.DEPLOY_PROMOTE,
            context={"env": "staging"},
            rationale="Promoting to staging",
            outcome=DecisionOutcome.SUCCESS,
            constitution_principles=[
                ConstitutionPrinciple.P001,
                ConstitutionPrinciple.P008,
            ],
            story_id="ST-DEPLOY",
            metadata={"version": "1.2.3"},
        )

        data = original.to_dict()
        restored = Decision.from_dict(data)

        assert restored.decision_id == original.decision_id
        assert restored.agent_id == original.agent_id
        assert restored.decision_type == original.decision_type
        assert restored.context == original.context
        assert restored.rationale == original.rationale
        assert restored.outcome == original.outcome
        assert restored.constitution_principles == original.constitution_principles
        assert restored.story_id == original.story_id
        assert restored.metadata == original.metadata

    def test_decision_hash_and_equality(self):
        """Test that decisions are hashable and comparable."""
        d1 = Decision(decision_id="same-id")
        d2 = Decision(decision_id="same-id")
        d3 = Decision(decision_id="different-id")

        assert d1 == d2
        assert d1 != d3
        assert hash(d1) == hash(d2)

        # Can use in sets
        decisions = {d1, d2, d3}
        assert len(decisions) == 2  # d1 and d2 are the same
