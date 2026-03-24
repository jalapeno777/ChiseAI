"""Tests for Phase 2 belief graph and revision components."""

from __future__ import annotations

from autonomous_cognition.beliefs.consistency_checker import BeliefConsistencyChecker
from autonomous_cognition.beliefs.models import Belief, EvidenceRecord
from autonomous_cognition.beliefs.revision_engine import BeliefRevisionEngine


def test_belief_conflict_detection() -> None:
    """Checker should detect contradiction-like belief conflicts."""
    checker = BeliefConsistencyChecker()
    beliefs = [
        Belief(
            belief_id="b1",
            statement="This strategy is valid and active.",
            domain="strategy",
            confidence=0.8,
        ),
        Belief(
            belief_id="b2",
            statement="This strategy is no longer valid and obsolete.",
            domain="strategy",
            confidence=0.7,
        ),
    ]
    conflicts = checker.detect_conflicts(beliefs)
    assert len(conflicts) >= 1


def test_belief_revision_applied_when_confidence_gap_exists() -> None:
    """Revision engine should supersede lower-confidence conflicting belief."""
    checker = BeliefConsistencyChecker()
    high = Belief(
        belief_id="high",
        statement="Use guarded promotion gates for safety.",
        domain="governance",
        confidence=0.82,
        evidence_refs=[
            "self_assessment_daily",
            "runtime_health_window",
            "governance_stability_window",
        ],
    )
    low = Belief(
        belief_id="low",
        statement="Use no promotion gates and override safety checks.",
        domain="governance",
        confidence=0.6,
    )
    conflicts = checker.detect_conflicts([high, low])
    engine = BeliefRevisionEngine(min_confidence_delta=0.1)
    evidence_index = {
        "self_assessment_daily": [
            EvidenceRecord(
                evidence_id="self_assessment_daily",
                source="test",
                source_family="self_assessment_current",
                is_llm_judgment=True,
                timestamp="2026-03-14T00:00:00+00:00",
                reliability=0.9,
                summary="High confidence governance check",
                metrics={"confirmed_runs": 3, "causal_strength": 0.5},
            )
        ],
        "runtime_health_window": [
            EvidenceRecord(
                evidence_id="runtime_health_window",
                source="test-runtime",
                source_family="runtime_telemetry",
                is_llm_judgment=False,
                timestamp="2026-03-14T00:00:00+00:00",
                reliability=0.9,
                summary="Runtime non-regression stable",
                metrics={"confirmed_runs": 3, "causal_strength": 0.8},
            )
        ],
        "governance_stability_window": [
            EvidenceRecord(
                evidence_id="governance_stability_window",
                source="test-governance",
                source_family="governance_metrics",
                is_llm_judgment=False,
                timestamp="2026-03-14T00:00:00+00:00",
                reliability=0.9,
                summary="Constitution violations stayed zero",
                metrics={"confirmed_runs": 3, "causal_strength": 0.75},
            )
        ],
    }
    revisions = engine.apply_revisions(
        beliefs={high.belief_id: high, low.belief_id: low},
        conflicts=conflicts,
        evidence_index=evidence_index,
    )
    assert len(revisions) >= 1
    assert low.status == "superseded"


def test_belief_revision_blocked_without_sufficient_evidence() -> None:
    """Revision should be blocked when winning belief lacks evidence support."""
    checker = BeliefConsistencyChecker()
    a = Belief(
        belief_id="a",
        statement="This strategy is valid and active.",
        domain="memory",
        confidence=0.9,
        evidence_refs=["missing_evidence_ref"],
    )
    b = Belief(
        belief_id="b",
        statement="This strategy is no longer valid and obsolete.",
        domain="memory",
        confidence=0.6,
    )
    conflicts = checker.detect_conflicts([a, b])
    engine = BeliefRevisionEngine(min_confidence_delta=0.1)
    revisions = engine.apply_revisions(
        beliefs={a.belief_id: a, b.belief_id: b},
        conflicts=conflicts,
        evidence_index={},
    )
    assert revisions == []
    assert len(engine.last_blocked_revisions) >= 1
    assert engine.last_blocked_revisions[0]["reason"].startswith(
        "insufficient_evidence"
    )


def test_belief_revision_blocked_when_source_diversity_is_low() -> None:
    """Revision should be blocked when winner lacks enough distinct evidence families."""
    checker = BeliefConsistencyChecker()
    a = Belief(
        belief_id="a",
        statement="This strategy is valid and active.",
        domain="memory",
        confidence=0.9,
        evidence_refs=["self_assessment_daily"],
    )
    b = Belief(
        belief_id="b",
        statement="This strategy is no longer valid and obsolete.",
        domain="memory",
        confidence=0.6,
    )
    conflicts = checker.detect_conflicts([a, b])
    engine = BeliefRevisionEngine(min_confidence_delta=0.1)
    evidence_index = {
        "self_assessment_daily": [
            EvidenceRecord(
                evidence_id="self_assessment_daily",
                source="test",
                source_family="self_assessment_current",
                is_llm_judgment=True,
                timestamp="2026-03-14T00:00:00+00:00",
                reliability=0.95,
                summary="Single-source evidence only",
                metrics={"confirmed_runs": 3, "causal_strength": 0.4},
            )
        ]
    }
    revisions = engine.apply_revisions(
        beliefs={a.belief_id: a, b.belief_id: b},
        conflicts=conflicts,
        evidence_index=evidence_index,
    )
    assert revisions == []
    assert len(engine.last_blocked_revisions) >= 1
    assert engine.last_blocked_revisions[0]["reason"].startswith(
        "insufficient_source_diversity"
    )


def test_belief_revision_blocked_when_causal_support_is_low() -> None:
    """Revision should be blocked when causal support is too weak."""
    checker = BeliefConsistencyChecker()
    a = Belief(
        belief_id="a",
        statement="This strategy is valid and active.",
        domain="memory",
        confidence=0.9,
        evidence_refs=[
            "self_assessment_daily",
            "runtime_health_window",
            "governance_stability_window",
        ],
    )
    b = Belief(
        belief_id="b",
        statement="This strategy is no longer valid and obsolete.",
        domain="memory",
        confidence=0.5,
    )
    conflicts = checker.detect_conflicts([a, b])
    engine = BeliefRevisionEngine(min_confidence_delta=0.1)
    low_causal = {"confirmed_runs": 3, "causal_strength": 0.1}
    evidence_index = {
        "self_assessment_daily": [
            EvidenceRecord(
                evidence_id="self_assessment_daily",
                source="test",
                source_family="self_assessment_current",
                is_llm_judgment=True,
                timestamp="2026-03-14T00:00:00+00:00",
                reliability=0.95,
                summary="Low-causal evidence",
                metrics=low_causal,
            )
        ],
        "runtime_health_window": [
            EvidenceRecord(
                evidence_id="runtime_health_window",
                source="test-runtime",
                source_family="runtime_telemetry",
                is_llm_judgment=False,
                timestamp="2026-03-14T00:00:00+00:00",
                reliability=0.95,
                summary="Low-causal evidence",
                metrics=low_causal,
            )
        ],
        "governance_stability_window": [
            EvidenceRecord(
                evidence_id="governance_stability_window",
                source="test-governance",
                source_family="governance_metrics",
                is_llm_judgment=False,
                timestamp="2026-03-14T00:00:00+00:00",
                reliability=0.95,
                summary="Low-causal evidence",
                metrics=low_causal,
            )
        ],
    }
    revisions = engine.apply_revisions(
        beliefs={a.belief_id: a, b.belief_id: b},
        conflicts=conflicts,
        evidence_index=evidence_index,
    )
    assert revisions == []
    assert engine.last_blocked_revisions[0]["reason"].startswith(
        "insufficient_causal_support"
    )
