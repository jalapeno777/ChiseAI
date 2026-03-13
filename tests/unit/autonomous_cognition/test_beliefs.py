"""Tests for Phase 2 belief graph and revision components."""

from __future__ import annotations

from autonomous_cognition.beliefs.consistency_checker import BeliefConsistencyChecker
from autonomous_cognition.beliefs.models import Belief
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
        confidence=0.9,
    )
    low = Belief(
        belief_id="low",
        statement="Use no promotion gates and override safety checks.",
        domain="governance",
        confidence=0.6,
    )
    conflicts = checker.detect_conflicts([high, low])
    engine = BeliefRevisionEngine(min_confidence_delta=0.1)
    revisions = engine.apply_revisions(
        beliefs={high.belief_id: high, low.belief_id: low},
        conflicts=conflicts,
    )
    assert len(revisions) >= 1
    assert low.status == "superseded"

