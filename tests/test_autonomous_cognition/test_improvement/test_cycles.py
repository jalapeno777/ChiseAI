"""Tests for improvement cycle orchestration."""

from __future__ import annotations

import pytest

from autonomous_cognition.improvement.cycles import (
    ImprovementCycleOrchestrator,
    ImprovementCycleResult,
    ImprovementPhase,
    ImprovementProposal,
)


class TestImprovementPhase:
    """Tests for ImprovementPhase enum."""

    def test_phase_values(self):
        """Test phase enum values."""
        assert ImprovementPhase.IDLE.value == "idle"
        assert ImprovementPhase.ASSESSING.value == "assessing"
        assert ImprovementPhase.COMPLETED.value == "completed"
        assert ImprovementPhase.ROLLED_BACK.value == "rolled_back"


class TestImprovementProposal:
    """Tests for ImprovementProposal dataclass."""

    def test_proposal_creation(self):
        """Test proposal creation."""
        proposal = ImprovementProposal(
            proposal_id="prop-1",
            description="Add feature X",
            files=["src/test.py"],
            risk_level="low",
        )
        assert proposal.proposal_id == "prop-1"
        assert proposal.risk_level == "low"
        assert "src/test.py" in proposal.files

    def test_proposal_to_dict(self):
        """Test proposal serialization."""
        proposal = ImprovementProposal(
            proposal_id="prop-1",
            description="Test",
        )
        d = proposal.to_dict()
        assert d["proposal_id"] == "prop-1"
        assert "description" in d


class TestImprovementCycleResult:
    """Tests for ImprovementCycleResult."""

    def test_result_create(self):
        """Test factory method."""
        result = ImprovementCycleResult.create("cycle-1")
        assert result.cycle_id == "cycle-1"
        assert result.started_at != ""
        assert result.final_phase == ImprovementPhase.IDLE

    def test_result_to_dict(self):
        """Test serialization."""
        result = ImprovementCycleResult.create()
        d = result.to_dict()
        assert "cycle_id" in d
        assert "started_at" in d


class TestImprovementCycleOrchestrator:
    """Tests for ImprovementCycleOrchestrator."""

    def test_start_cycle(self):
        """Test starting a cycle."""
        orch = ImprovementCycleOrchestrator()
        result = orch.start_cycle("test-cycle")
        assert result.cycle_id == "test-cycle"
        assert orch.current_phase == ImprovementPhase.ASSESSING
        assert orch.is_active is True

    def test_start_cycle_already_active(self):
        """Test that starting a cycle while active raises error."""
        orch = ImprovementCycleOrchestrator()
        orch.start_cycle()
        with pytest.raises(ValueError, match="Cycle already active"):
            orch.start_cycle()

    def test_full_successful_cycle(self):
        """Test a complete successful cycle through all phases."""
        orch = ImprovementCycleOrchestrator()
        orch.start_cycle()

        # Assess
        assessment = orch.assess(lambda: {"score": 0.9})
        assert assessment["score"] == 0.9
        assert orch.current_phase == ImprovementPhase.PROPOSING

        # Propose
        proposal = ImprovementProposal(
            proposal_id="prop-1",
            description="Test improvement",
            files=["src/autonomous_cognition/test.py"],
            risk_level="low",
            line_counts={"src/autonomous_cognition/test.py": 25},
        )
        orch.propose(proposal)
        assert orch.current_phase == ImprovementPhase.VALIDATING

        # Validate
        assert orch.validate(lambda: True) is True
        assert orch.current_phase == ImprovementPhase.APPLYING

        # Apply
        assert orch.apply(lambda: True) is True
        assert orch.current_phase == ImprovementPhase.VERIFYING

        # Verify
        assert orch.verify(lambda: True) is True
        assert orch.current_phase == ImprovementPhase.COMPLETED
        assert orch.is_active is False

    def test_validation_failure(self):
        """Test cycle failure during validation."""
        orch = ImprovementCycleOrchestrator()
        orch.start_cycle()
        orch.assess()
        orch.propose(ImprovementProposal(proposal_id="p1", description="test"))
        result = orch.validate(lambda: False)
        assert result is False
        assert orch.current_phase == ImprovementPhase.FAILED

    def test_apply_failure_triggers_rollback(self):
        """Test that apply failure triggers rollback."""
        orch = ImprovementCycleOrchestrator()
        orch.start_cycle()
        orch.assess()
        orch.propose(ImprovementProposal(proposal_id="p1", description="test"))
        orch.validate()
        result = orch.apply(lambda: False)
        assert result is False
        assert orch.current_phase == ImprovementPhase.ROLLED_BACK

    def test_verify_failure_triggers_rollback(self):
        """Test that verify failure triggers rollback."""
        orch = ImprovementCycleOrchestrator()
        orch.start_cycle()
        orch.assess()
        orch.propose(ImprovementProposal(proposal_id="p1", description="test"))
        orch.validate()
        orch.apply()
        result = orch.verify(lambda: False)
        assert result is False
        assert orch.current_phase == ImprovementPhase.ROLLED_BACK

    def test_emergency_stop(self):
        """Test emergency stop blocks all operations."""
        orch = ImprovementCycleOrchestrator()
        orch.start_cycle()
        orch.activate_emergency_stop("critical issue")
        assert orch.current_phase == ImprovementPhase.FAILED
        with pytest.raises(ValueError, match="Emergency stop"):
            orch.assess()

    def test_checkpoints_created(self):
        """Test that checkpoints are created at phase boundaries."""
        orch = ImprovementCycleOrchestrator()
        orch.start_cycle()
        orch.assess()
        orch.propose(ImprovementProposal(proposal_id="p1", description="test"))
        checkpoints = orch.get_checkpoints()
        assert len(checkpoints) >= 3  # At least: start, assess, propose

    def test_invalid_transition_raises(self):
        """Test that invalid phase transitions raise errors."""
        orch = ImprovementCycleOrchestrator()
        # Can't assess without starting
        with pytest.raises(ValueError, match="Expected phase"):
            orch.assess()
