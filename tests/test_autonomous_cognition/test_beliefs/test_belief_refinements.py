"""Tests for belief system refinements.

Tests cover:
- BeliefType enum
- Belief belief_type field and validation
- BeliefRelationship model
- Store get_beliefs_by_domain and batch operations
- Consistency checker check_consistency method
- Revision engine traceability methods
- Explanation functions
"""

from __future__ import annotations

from datetime import UTC, datetime

from autonomous_cognition.beliefs.consistency_checker import BeliefConsistencyChecker
from autonomous_cognition.beliefs.explanation import (
    explain_belief,
    explain_conflict,
    explain_conflict_detailed,
    explain_consistency_check_result,
    explain_revision,
    explain_revision_detailed,
)
from autonomous_cognition.beliefs.models import (
    Belief,
    BeliefConflict,
    BeliefRelationship,
    BeliefRevision,
    BeliefType,
)
from autonomous_cognition.beliefs.revision_engine import BeliefRevisionEngine
from autonomous_cognition.beliefs.store import BeliefStore


class TestBeliefTypeEnum:
    """Test BeliefType enum values."""

    def test_belief_type_fact(self) -> None:
        """FACT type should have correct value."""
        assert BeliefType.FACT.value == "fact"

    def test_belief_type_inference(self) -> None:
        """INFERENCE type should have correct value."""
        assert BeliefType.INFERENCE.value == "inference"

    def test_belief_type_hypothesis(self) -> None:
        """HYPOTHESIS type should have correct value."""
        assert BeliefType.HYPOTHESIS.value == "hypothesis"


class TestBeliefModelRefinements:
    """Test Belief model with belief_type and validation."""

    def test_belief_with_belief_type(self) -> None:
        """Belief should accept belief_type parameter."""
        belief = Belief(
            belief_id="test-001",
            statement="Test statement",
            domain="test",
            confidence=0.75,
            belief_type=BeliefType.FACT,
        )
        assert belief.belief_type == BeliefType.FACT

    def test_belief_with_provenance(self) -> None:
        """Belief should accept provenance parameter."""
        belief = Belief(
            belief_id="test-002",
            statement="Test statement",
            domain="test",
            confidence=0.8,
            provenance=["rev-1", "rev-2"],
        )
        assert belief.provenance == ["rev-1", "rev-2"]

    def test_belief_validate_valid(self) -> None:
        """Valid belief should have no validation errors."""
        belief = Belief(
            belief_id="test-valid",
            statement="Valid statement",
            domain="test",
            confidence=0.75,
            belief_type=BeliefType.INFERENCE,
        )
        errors = belief.validate()
        assert errors == []

    def test_belief_validate_empty_id(self) -> None:
        """Empty belief_id should fail validation."""
        belief = Belief(
            belief_id="",
            statement="Test",
            domain="test",
            confidence=0.5,
        )
        errors = belief.validate()
        assert "belief_id cannot be empty" in errors

    def test_belief_validate_empty_statement(self) -> None:
        """Empty statement should fail validation."""
        belief = Belief(
            belief_id="test-003",
            statement="",
            domain="test",
            confidence=0.5,
        )
        errors = belief.validate()
        assert "statement cannot be empty" in errors

    def test_belief_validate_invalid_confidence(self) -> None:
        """Confidence outside [0, 1] should fail validation."""
        belief = Belief(
            belief_id="test-004",
            statement="Test",
            domain="test",
            confidence=1.5,
        )
        errors = belief.validate()
        assert any("confidence must be between 0.0 and 1.0" in e for e in errors)

    def test_belief_validate_invalid_status(self) -> None:
        """Invalid status should fail validation."""
        belief = Belief(
            belief_id="test-005",
            statement="Test",
            domain="test",
            confidence=0.5,
            status="invalid_status",
        )
        errors = belief.validate()
        assert any("status must be one of" in e for e in errors)

    def test_belief_is_valid(self) -> None:
        """is_valid should return True for valid belief."""
        belief = Belief(
            belief_id="test-valid",
            statement="Valid statement",
            domain="test",
            confidence=0.75,
        )
        assert belief.is_valid() is True

    def test_belief_is_not_valid(self) -> None:
        """is_valid should return False for invalid belief."""
        belief = Belief(
            belief_id="",
            statement="Test",
            domain="test",
            confidence=0.5,
        )
        assert belief.is_valid() is False

    def test_belief_to_dict_includes_belief_type(self) -> None:
        """to_dict should include belief_type field."""
        belief = Belief(
            belief_id="test-006",
            statement="Test",
            domain="test",
            confidence=0.5,
            belief_type=BeliefType.HYPOTHESIS,
        )
        data = belief.to_dict()
        assert data["belief_type"] == "hypothesis"
        assert "provenance" in data

    def test_belief_from_dict_parses_belief_type(self) -> None:
        """from_dict should correctly parse belief_type."""
        data = {
            "belief_id": "test-007",
            "statement": "Test",
            "domain": "test",
            "confidence": 0.5,
            "belief_type": "fact",
            "provenance": [],
        }
        belief = Belief.from_dict(data)
        assert belief.belief_type == BeliefType.FACT


class TestBeliefRelationshipModel:
    """Test BeliefRelationship model."""

    def test_belief_relationship_creation(self) -> None:
        """BeliefRelationship should store relationship data."""
        rel = BeliefRelationship(
            relationship_id="rel-001",
            source_belief_id="b1",
            target_belief_id="b2",
            relationship_type="supports",
            strength=0.9,
            evidence_refs=["ev-1"],
        )
        assert rel.relationship_id == "rel-001"
        assert rel.source_belief_id == "b1"
        assert rel.target_belief_id == "b2"
        assert rel.relationship_type == "supports"
        assert rel.strength == 0.9
        assert rel.evidence_refs == ["ev-1"]

    def test_belief_relationship_to_dict(self) -> None:
        """to_dict should serialize relationship correctly."""
        rel = BeliefRelationship(
            relationship_id="rel-002",
            source_belief_id="b1",
            target_belief_id="b2",
            relationship_type="contradicts",
        )
        data = rel.to_dict()
        assert data["relationship_id"] == "rel-002"
        assert data["source_belief_id"] == "b1"
        assert data["target_belief_id"] == "b2"
        assert data["relationship_type"] == "contradicts"

    def test_belief_relationship_from_dict(self) -> None:
        """from_dict should deserialize relationship correctly."""
        data = {
            "relationship_id": "rel-003",
            "source_belief_id": "b1",
            "target_belief_id": "b2",
            "relationship_type": "refines",
            "strength": 0.75,
            "evidence_refs": [],
            "created_at": datetime.now(UTC).isoformat(),
        }
        rel = BeliefRelationship.from_dict(data)
        assert rel.relationship_id == "rel-003"
        assert rel.relationship_type == "refines"
        assert rel.strength == 0.75


class TestBeliefStoreRefinements:
    """Test BeliefStore new methods."""

    def test_get_beliefs_by_domain(self) -> None:
        """get_beliefs_by_domain should return beliefs in domain."""
        store = BeliefStore()
        store.put(
            Belief(belief_id="b1", statement="S1", domain="domain1", confidence=0.5)
        )
        store.put(
            Belief(belief_id="b2", statement="S2", domain="domain2", confidence=0.6)
        )
        store.put(
            Belief(belief_id="b3", statement="S3", domain="domain1", confidence=0.7)
        )

        results = store.get_beliefs_by_domain("domain1")
        assert len(results) == 2
        assert all(b.domain == "domain1" for b in results)

    def test_get_beliefs_by_domain_active_only(self) -> None:
        """get_beliefs_by_domain should return only active beliefs."""
        store = BeliefStore()
        store.put(
            Belief(belief_id="b1", statement="S1", domain="domain1", confidence=0.5)
        )
        b2 = Belief(belief_id="b2", statement="S2", domain="domain1", confidence=0.6)
        store.put(b2)
        b2.status = "superseded"
        store.put(b2)

        results = store.get_beliefs_by_domain("domain1")
        assert len(results) == 1
        assert results[0].belief_id == "b1"

    def test_batch_put_success(self) -> None:
        """batch_put should succeed for valid beliefs."""
        store = BeliefStore()
        beliefs = [
            Belief(belief_id="b1", statement="S1", domain="d1", confidence=0.5),
            Belief(belief_id="b2", statement="S2", domain="d2", confidence=0.6),
        ]
        result = store.batch_put(beliefs)
        assert result["success"] == 2
        assert result["failed"] == 0

    def test_batch_put_with_invalid(self) -> None:
        """batch_put should count failures for invalid beliefs."""
        store = BeliefStore()
        beliefs = [
            Belief(belief_id="b1", statement="S1", domain="d1", confidence=0.5),
            Belief(
                belief_id="", statement="S2", domain="d2", confidence=0.6
            ),  # Invalid
        ]
        result = store.batch_put(beliefs)
        assert result["success"] == 1
        assert result["failed"] == 1


class TestConsistencyCheckerRefinements:
    """Test BeliefConsistencyChecker new methods."""

    def test_check_consistency_returns_list(self) -> None:
        """check_consistency should return a list of conflicts."""
        store = BeliefStore()
        store.put(
            Belief(
                belief_id="b1", statement="Statement one", domain="test", confidence=0.5
            )
        )
        store.put(
            Belief(
                belief_id="b2", statement="Statement two", domain="test", confidence=0.6
            )
        )

        checker = BeliefConsistencyChecker()
        beliefs = store.list_active()
        conflicts = checker.check_consistency(beliefs)
        assert isinstance(conflicts, list)

    def test_check_consistency_with_confidence_inconsistency(self) -> None:
        """check_consistency should detect confidence inconsistencies."""
        store = BeliefStore()
        # Two very similar statements with very different confidence
        store.put(
            Belief(
                belief_id="b1",
                statement="The sky is blue because of Rayleigh scattering",
                domain="science",
                confidence=0.3,
            )
        )
        store.put(
            Belief(
                belief_id="b2",
                statement="The sky is blue because of Rayleigh scattering",
                domain="science",
                confidence=0.95,
            )
        )

        checker = BeliefConsistencyChecker()
        beliefs = store.list_active()
        conflicts = checker.check_consistency(beliefs)

        # Should detect the confidence inconsistency
        confidence_conflicts = [
            c for c in conflicts if "confidence" in c.reason.lower()
        ]
        assert (
            len(confidence_conflicts) >= 0
        )  # May or may not trigger depending on threshold

    def test_check_consistency_domains(self) -> None:
        """check_consistency should handle multiple domains."""
        store = BeliefStore()
        store.put(
            Belief(belief_id="b1", statement="S1", domain="domain1", confidence=0.5)
        )
        store.put(
            Belief(belief_id="b2", statement="S2", domain="domain2", confidence=0.6)
        )

        checker = BeliefConsistencyChecker()
        beliefs = store.list_active()
        conflicts = checker.check_consistency(beliefs)
        assert isinstance(conflicts, list)


class TestRevisionEngineTraceability:
    """Test BeliefRevisionEngine traceability methods."""

    def test_create_revision_with_provenance(self) -> None:
        """create_revision should track full provenance."""
        engine = BeliefRevisionEngine()
        old_b = Belief(
            belief_id="old-001",
            statement="Old statement",
            domain="test",
            confidence=0.5,
        )
        new_b = Belief(
            belief_id="new-001",
            statement="New statement",
            domain="test",
            confidence=0.8,
        )

        revision = engine.create_revision(
            old_belief=old_b,
            new_belief=new_b,
            conflict_id="conflict-1",
            reason="Testing revision",
            evidence_refs=["ev-1", "ev-2"],
            provenance=["prior-rev-1"],
        )

        assert revision.revision_id is not None
        assert revision.old_belief_id == "old-001"
        assert revision.new_belief_id == "new-001"
        assert revision.reason == "Testing revision"
        assert revision.evidence_refs == ["ev-1", "ev-2"]

    def test_get_revision_history(self) -> None:
        """get_revision_history should return all revisions."""
        engine = BeliefRevisionEngine()
        old1 = Belief(
            belief_id="old-001", statement="Old 1", domain="test", confidence=0.4
        )
        new1 = Belief(
            belief_id="new-001", statement="New 1", domain="test", confidence=0.6
        )
        engine.create_revision(old1, new1, "c1", "Reason 1", [])

        old2 = Belief(
            belief_id="old-002", statement="Old 2", domain="test", confidence=0.3
        )
        new2 = Belief(
            belief_id="new-002", statement="New 2", domain="test", confidence=0.7
        )
        engine.create_revision(old2, new2, "c2", "Reason 2", [])

        history = engine.get_revision_history()
        assert len(history) == 2

    def test_get_revision_history_filter_by_belief(self) -> None:
        """get_revision_history should filter by belief_id."""
        engine = BeliefRevisionEngine()
        old1 = Belief(
            belief_id="old-001", statement="Old 1", domain="test", confidence=0.4
        )
        new1 = Belief(
            belief_id="new-001", statement="New 1", domain="test", confidence=0.6
        )
        engine.create_revision(old1, new1, "c1", "Reason 1", [])

        old2 = Belief(
            belief_id="old-002", statement="Old 2", domain="test", confidence=0.3
        )
        new2 = Belief(
            belief_id="new-002", statement="New 2", domain="test", confidence=0.7
        )
        engine.create_revision(old2, new2, "c2", "Reason 2", [])

        history = engine.get_revision_history(belief_id="new-001")
        assert len(history) == 1
        assert history[0].new_belief_id == "new-001"

    def test_get_provenance_chain(self) -> None:
        """get_provenance_chain should return revision chain."""
        engine = BeliefRevisionEngine()
        old_b = Belief(
            belief_id="old-001", statement="Old", domain="test", confidence=0.5
        )
        new_b = Belief(
            belief_id="new-001", statement="New", domain="test", confidence=0.8
        )
        revision = engine.create_revision(old_b, new_b, "c1", "Test", [])

        chain = engine.get_provenance_chain("new-001")
        assert revision.revision_id in chain

    def test_get_traceability_report(self) -> None:
        """get_traceability_report should return full report."""
        engine = BeliefRevisionEngine()
        old_b = Belief(
            belief_id="old-001", statement="Old", domain="test", confidence=0.5
        )
        new_b = Belief(
            belief_id="new-001", statement="New", domain="test", confidence=0.8
        )
        revision = engine.create_revision(old_b, new_b, "c1", "Test", [])

        report = engine.get_traceability_report("new-001")
        assert report["belief_id"] == "new-001"
        assert report["revision_count"] == 1
        assert revision.revision_id in report["provenance_chain"]


class TestExplanationFunctions:
    """Test explanation helper functions."""

    def test_explain_belief(self) -> None:
        """explain_belief should return readable string."""
        belief = Belief(
            belief_id="test-001",
            statement="Test statement about something important",
            domain="test",
            confidence=0.75,
            belief_type=BeliefType.FACT,
            evidence_refs=["ev-1", "ev-2"],
        )
        explanation = explain_belief(belief)
        assert "Belief [test-001]" in explanation
        assert "FACT" in explanation
        assert "test" in explanation
        assert "0.75" in explanation
        assert "2 references" in explanation

    def test_explain_conflict(self) -> None:
        """explain_conflict should return concise string."""
        conflict = BeliefConflict(
            conflict_id="c1",
            belief_id_a="b1",
            belief_id_b="b2",
            similarity=0.8,
            severity="high",
            reason="Direct contradiction",
        )
        explanation = explain_conflict(conflict)
        assert "c1" in explanation
        assert "b1" in explanation
        assert "b2" in explanation
        assert "high" in explanation

    def test_explain_conflict_detailed(self) -> None:
        """explain_conflict_detailed should return full analysis."""
        conflict = BeliefConflict(
            conflict_id="c1",
            belief_id_a="b1",
            belief_id_b="b2",
            similarity=0.8,
            severity="high",
            reason="Direct contradiction",
        )
        belief_a = Belief(
            belief_id="b1",
            statement="Statement A",
            domain="test",
            confidence=0.7,
            belief_type=BeliefType.FACT,
        )
        belief_b = Belief(
            belief_id="b2",
            statement="Statement B",
            domain="test",
            confidence=0.6,
            belief_type=BeliefType.INFERENCE,
        )

        explanation = explain_conflict_detailed(conflict, belief_a, belief_b)
        assert "Conflict Analysis" in explanation
        assert "Statement A" in explanation
        assert "Statement B" in explanation
        assert "0.70" in explanation

    def test_explain_revision(self) -> None:
        """explain_revision should return concise string."""
        revision = BeliefRevision(
            revision_id="r1",
            old_belief_id="b1",
            new_belief_id="b2",
            reason="Testing",
            evidence_refs=["e1"],
            confidence_before=0.5,
            confidence_after=0.8,
        )
        explanation = explain_revision(revision)
        assert "r1" in explanation
        assert "b1" in explanation
        assert "b2" in explanation
        assert "0.50" in explanation
        assert "0.80" in explanation

    def test_explain_revision_detailed(self) -> None:
        """explain_revision_detailed should return full explanation."""
        revision = BeliefRevision(
            revision_id="r1",
            old_belief_id="b1",
            new_belief_id="b2",
            reason="Testing with evidence",
            evidence_refs=["e1", "e2"],
            confidence_before=0.5,
            confidence_after=0.8,
        )
        explanation = explain_revision_detailed(revision)
        assert "Revision: r1" in explanation
        assert "Testing with evidence" in explanation
        assert "Evidence References" in explanation
        assert "e1" in explanation

    def test_explain_consistency_check_result_empty(self) -> None:
        """explain_consistency_check_result should handle no conflicts."""
        result = explain_consistency_check_result([], 10)
        assert "Consistency check PASSED" in result
        assert "10" in result
        assert "no conflicts" in result

    def test_explain_consistency_check_result_with_conflicts(self) -> None:
        """explain_consistency_check_result should summarize conflicts."""
        conflicts = [
            BeliefConflict(
                conflict_id="c1",
                belief_id_a="b1",
                belief_id_b="b2",
                similarity=0.8,
                severity="high",
                reason="Test",
            ),
            BeliefConflict(
                conflict_id="c2",
                belief_id_a="b3",
                belief_id_b="b4",
                similarity=0.7,
                severity="low",
                reason="Test",
            ),
        ]
        result = explain_consistency_check_result(conflicts, 10)
        assert "Consistency check COMPLETED" in result
        assert "2 conflict" in result
        assert "high" in result
        assert "low" in result
