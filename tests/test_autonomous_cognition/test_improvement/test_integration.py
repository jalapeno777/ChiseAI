"""Integration tests for the improvement module.
Tests that all components work together correctly.
"""

from __future__ import annotations

import pytest

from autonomous_cognition.improvement import (
    BoundaryConfig,
    BoundaryEnforcer,
    EscalationManager,
    EscalationType,
    ImprovementCycleOrchestrator,
    ImprovementPhase,
    ImprovementProposal,
    RiskLevel,
)


class TestImprovementIntegration:
    """Integration tests for improvement components working together."""

    def test_cycle_with_boundary_enforcement(self):
        """Test that the orchestrator respects boundary enforcement."""
        config = BoundaryConfig(
            allowed_paths=["src/autonomous_cognition/"],
            max_risk_level=RiskLevel.MEDIUM,
        )
        enforcer = BoundaryEnforcer(config)
        orch = ImprovementCycleOrchestrator(boundary_enforcer=enforcer)

        orch.start_cycle()
        orch.assess()

        # Safe proposal should pass
        proposal = ImprovementProposal(
            proposal_id="safe-1",
            description="Safe improvement",
            files=["src/autonomous_cognition/improvement/test.py"],
            risk_level="low",
        )
        result = orch.propose(proposal)
        assert result.proposal_id == "safe-1"
        assert orch.current_phase == ImprovementPhase.VALIDATING

    def test_cycle_blocked_by_boundary(self):
        """Test that boundary violations block proposals in the orchestrator."""
        config = BoundaryConfig(
            allowed_paths=["src/autonomous_cognition/"],
            blocked_paths=[".woodpecker.yml"],
        )
        enforcer = BoundaryEnforcer(config)
        orch = ImprovementCycleOrchestrator(boundary_enforcer=enforcer)

        orch.start_cycle()
        orch.assess()

        # Proposal targeting blocked file should fail
        proposal = ImprovementProposal(
            proposal_id="blocked-1",
            description="Bad proposal",
            files=[".woodpecker.yml"],
            risk_level="low",
        )
        with pytest.raises(ValueError, match="blocked by boundaries"):
            orch.propose(proposal)

    def test_escalation_on_boundary_violation(self):
        """Test that boundary violations create escalation events."""
        enforcer = BoundaryEnforcer()
        escalation_mgr = EscalationManager()

        proposal = {
            "files": [".woodpecker.yml"],
            "risk_level": "low",
            "changes": {},
        }
        violations = enforcer.check_proposal(proposal)
        assert len(violations) > 0

        # Create escalation for the violation
        event = escalation_mgr.create_escalation(
            EscalationType.BOUNDARY_VIOLATION,
            violations[0].description,
            severity=violations[0].severity,
        )
        assert event.escalation_type == EscalationType.BOUNDARY_VIOLATION
        assert len(escalation_mgr.get_pending_escalations()) == 1

    def test_full_cycle_with_escalation_on_rollback(self):
        """Test a cycle that fails and creates an escalation event."""
        escalation_mgr = EscalationManager()
        orch = ImprovementCycleOrchestrator()

        orch.start_cycle()
        orch.assess()
        orch.propose(ImprovementProposal(proposal_id="p1", description="test"))
        orch.validate()

        # Apply fails -> rollback
        result = orch.apply(lambda: False)
        assert result is False
        assert orch.current_phase == ImprovementPhase.ROLLED_BACK

        # Create escalation for the rollback
        event = escalation_mgr.create_escalation(
            EscalationType.VALIDATION_FAILED,
            f"Cycle rolled back: {orch._cycle_result.error if orch._cycle_result else 'unknown'}",
            severity="high",
        )
        assert event.severity == "high"
        assert len(escalation_mgr.get_pending_escalations()) == 1
