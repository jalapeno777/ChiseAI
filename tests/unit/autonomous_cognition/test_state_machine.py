"""Tests for state_machine.py - cycle state transitions and persistence."""

from __future__ import annotations

import json
import pickle

import pytest
from src.autonomous_cognition.state_machine import (
    AutonomousCycleStateMachine,
    CycleState,
)

# --- Fixtures ---


@pytest.fixture
def state_machine():
    """Create a fresh state machine for each test."""
    return AutonomousCycleStateMachine()


# --- Valid State Transition Tests ---


class TestValidStateTransitions:
    """Tests that verify valid state transitions are allowed."""

    def test_idle_to_self_assessing(self, state_machine):
        """IDLE -> SELF_ASSESSING should be allowed."""
        state_machine.transition(CycleState.SELF_ASSESSING)
        assert state_machine.state == CycleState.SELF_ASSESSING

    def test_self_assessing_to_belief_check(self, state_machine):
        """SELF_ASSESSING -> BELIEF_CHECK should be allowed."""
        state_machine.state = CycleState.SELF_ASSESSING
        state_machine.transition(CycleState.BELIEF_CHECK)
        assert state_machine.state == CycleState.BELIEF_CHECK

    def test_belief_check_to_improvement(self, state_machine):
        """BELIEF_CHECK -> IMPROVEMENT should be allowed."""
        state_machine.state = CycleState.BELIEF_CHECK
        state_machine.transition(CycleState.IMPROVEMENT)
        assert state_machine.state == CycleState.IMPROVEMENT

    def test_improvement_to_runtime_integration(self, state_machine):
        """IMPROVEMENT -> RUNTIME_INTEGRATION should be allowed."""
        state_machine.state = CycleState.IMPROVEMENT
        state_machine.transition(CycleState.RUNTIME_INTEGRATION)
        assert state_machine.state == CycleState.RUNTIME_INTEGRATION

    def test_runtime_integration_to_tuning(self, state_machine):
        """RUNTIME_INTEGRATION -> TUNING should be allowed."""
        state_machine.state = CycleState.RUNTIME_INTEGRATION
        state_machine.transition(CycleState.TUNING)
        assert state_machine.state == CycleState.TUNING

    def test_tuning_to_governance_audit(self, state_machine):
        """TUNING -> GOVERNANCE_AUDIT should be allowed."""
        state_machine.state = CycleState.TUNING
        state_machine.transition(CycleState.GOVERNANCE_AUDIT)
        assert state_machine.state == CycleState.GOVERNANCE_AUDIT

    def test_governance_audit_to_completed(self, state_machine):
        """GOVERNANCE_AUDIT -> COMPLETED should be allowed."""
        state_machine.state = CycleState.GOVERNANCE_AUDIT
        state_machine.transition(CycleState.COMPLETED)
        assert state_machine.state == CycleState.COMPLETED

    def test_full_valid_cycle(self, state_machine):
        """Complete valid cycle: IDLE -> COMPLETED should work through all states."""
        state_machine.transition(CycleState.SELF_ASSESSING)
        state_machine.transition(CycleState.BELIEF_CHECK)
        state_machine.transition(CycleState.IMPROVEMENT)
        state_machine.transition(CycleState.RUNTIME_INTEGRATION)
        state_machine.transition(CycleState.TUNING)
        state_machine.transition(CycleState.GOVERNANCE_AUDIT)
        state_machine.transition(CycleState.COMPLETED)

        assert state_machine.state == CycleState.COMPLETED


# --- Invalid State Transition Tests ---


class TestInvalidStateTransitions:
    """Tests that verify invalid transitions raise ValueError."""

    def test_idle_cannot_go_to_completed(self, state_machine):
        """IDLE -> COMPLETED should raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            state_machine.transition(CycleState.COMPLETED)
        assert "Invalid transition" in str(exc_info.value)

    def test_idle_cannot_go_to_belief_check(self, state_machine):
        """IDLE -> BELIEF_CHECK should raise ValueError (must go through SELF_ASSESSING)."""
        with pytest.raises(ValueError) as exc_info:
            state_machine.transition(CycleState.BELIEF_CHECK)
        assert "Invalid transition" in str(exc_info.value)

    def test_completed_is_terminal(self, state_machine):
        """COMPLETED state should be terminal - no transitions allowed."""
        state_machine.state = CycleState.COMPLETED
        with pytest.raises(ValueError):
            state_machine.transition(CycleState.IDLE)
        with pytest.raises(ValueError):
            state_machine.transition(CycleState.SELF_ASSESSING)

    def test_failed_is_terminal(self, state_machine):
        """FAILED state should be terminal - no transitions allowed."""
        state_machine.state = CycleState.FAILED
        with pytest.raises(ValueError):
            state_machine.transition(CycleState.IDLE)
        with pytest.raises(ValueError):
            state_machine.transition(CycleState.SELF_ASSESSING)

    def test_self_assessing_cannot_skip_to_improvement(self, state_machine):
        """SELF_ASSESSING -> IMPROVEMENT should raise ValueError."""
        state_machine.state = CycleState.SELF_ASSESSING
        with pytest.raises(ValueError):
            state_machine.transition(CycleState.IMPROVEMENT)

    def test_belief_check_cannot_skip_to_runtime_integration(self, state_machine):
        """BELIEF_CHECK -> RUNTIME_INTEGRATION should raise ValueError."""
        state_machine.state = CycleState.BELIEF_CHECK
        with pytest.raises(ValueError):
            state_machine.transition(CycleState.RUNTIME_INTEGRATION)

    def test_improvement_cannot_skip_to_tuning(self, state_machine):
        """IMPROVEMENT -> TUNING should raise ValueError."""
        state_machine.state = CycleState.IMPROVEMENT
        with pytest.raises(ValueError):
            state_machine.transition(CycleState.TUNING)

    def test_tuning_cannot_skip_to_completed(self, state_machine):
        """TUNING -> COMPLETED should raise ValueError (must go through GOVERNANCE_AUDIT)."""
        state_machine.state = CycleState.TUNING
        with pytest.raises(ValueError):
            state_machine.transition(CycleState.COMPLETED)


# --- Error State Transition Tests ---


class TestErrorStateTransitions:
    """Tests for transitions to FAILED state from any intermediate state."""

    def test_self_assessing_can_fail(self, state_machine):
        """SELF_ASSESSING -> FAILED should be allowed."""
        state_machine.state = CycleState.SELF_ASSESSING
        state_machine.transition(CycleState.FAILED)
        assert state_machine.state == CycleState.FAILED

    def test_belief_check_can_fail(self, state_machine):
        """BELIEF_CHECK -> FAILED should be allowed."""
        state_machine.state = CycleState.BELIEF_CHECK
        state_machine.transition(CycleState.FAILED)
        assert state_machine.state == CycleState.FAILED

    def test_improvement_can_fail(self, state_machine):
        """IMPROVEMENT -> FAILED should be allowed."""
        state_machine.state = CycleState.IMPROVEMENT
        state_machine.transition(CycleState.FAILED)
        assert state_machine.state == CycleState.FAILED

    def test_runtime_integration_can_fail(self, state_machine):
        """RUNTIME_INTEGRATION -> FAILED should be allowed."""
        state_machine.state = CycleState.RUNTIME_INTEGRATION
        state_machine.transition(CycleState.FAILED)
        assert state_machine.state == CycleState.FAILED

    def test_tuning_can_fail(self, state_machine):
        """TUNING -> FAILED should be allowed."""
        state_machine.state = CycleState.TUNING
        state_machine.transition(CycleState.FAILED)
        assert state_machine.state == CycleState.FAILED

    def test_governance_audit_can_fail(self, state_machine):
        """GOVERNANCE_AUDIT -> FAILED should be allowed."""
        state_machine.state = CycleState.GOVERNANCE_AUDIT
        state_machine.transition(CycleState.FAILED)
        assert state_machine.state == CycleState.FAILED


# --- State Persistence Tests ---


class TestStatePersistence:
    """Tests for state save/restore functionality."""

    def test_state_survives_pickle_roundtrip(self, state_machine):
        """State machine should survive pickle serialization."""
        state_machine.state = CycleState.RUNTIME_INTEGRATION
        pickled = pickle.dumps(state_machine)
        restored = pickle.loads(pickled)

        assert restored.state == CycleState.RUNTIME_INTEGRATION

    def test_json_serialize_cycle_state(self, state_machine):
        """CycleState enum should serialize to JSON string."""
        state_machine.state = CycleState.TUNING
        json_str = json.dumps({"state": state_machine.state.value})

        assert json_str == '{"state": "tuning"}'

    def test_json_deserialize_cycle_state(self, state_machine):
        """CycleState enum should deserialize from JSON string."""
        json_str = '{"state": "belief_check"}'
        data = json.loads(json_str)
        state = CycleState(data["state"])

        assert state == CycleState.BELIEF_CHECK

    def test_state_dict_serialization(self, state_machine):
        """State should be restorable from dict representation."""
        state_machine.state = CycleState.IMPROVEMENT

        # Serialize to dict
        state_dict = {"state": state_machine.state.value}

        # Restore from dict
        restored_state = CycleState(state_dict["state"])
        assert restored_state == CycleState.IMPROVEMENT


# --- Error Recovery Tests ---


class TestErrorRecovery:
    """Tests for error state and recovery patterns."""

    def test_can_recover_from_failed_to_idle_with_reset(self, state_machine):
        """Manual reset pattern: FAILED -> IDLE by creating new instance."""
        # Start cycle and let it fail
        state_machine.state = CycleState.SELF_ASSESSING
        state_machine.transition(CycleState.FAILED)
        assert state_machine.state == CycleState.FAILED

        # Recovery pattern: create new state machine (reset to IDLE)
        recovered_machine = AutonomousCycleStateMachine()
        assert recovered_machine.state == CycleState.IDLE

    def test_failed_machine_still_rejects_invalid_transitions(self, state_machine):
        """Even after failure, state machine should enforce transition rules."""
        state_machine.state = CycleState.FAILED

        # FAILED is terminal, so no transitions should work
        with pytest.raises(ValueError):
            state_machine.transition(CycleState.SELF_ASSESSING)

    def test_transition_from_terminal_completed_rejected(self, state_machine):
        """COMPLETED is terminal - any transition should be rejected."""
        state_machine.state = CycleState.COMPLETED

        with pytest.raises(ValueError):
            state_machine.transition(CycleState.IDLE)

        with pytest.raises(ValueError):
            state_machine.transition(CycleState.FAILED)

    def test_can_transition_to_failed_from_any_active_state(self, state_machine):
        """Any non-terminal state should be able to transition to FAILED."""
        active_states = [
            CycleState.SELF_ASSESSING,
            CycleState.BELIEF_CHECK,
            CycleState.IMPROVEMENT,
            CycleState.RUNTIME_INTEGRATION,
            CycleState.TUNING,
            CycleState.GOVERNANCE_AUDIT,
        ]

        for active_state in active_states:
            sm = AutonomousCycleStateMachine()
            sm.state = active_state
            # Should not raise - all active states can go to FAILED
            sm.transition(CycleState.FAILED)
            assert sm.state == CycleState.FAILED


# --- Edge Case Tests ---


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_initial_state_is_idle(self):
        """New state machine should start in IDLE state."""
        sm = AutonomousCycleStateMachine()
        assert sm.state == CycleState.IDLE

    def test_same_state_transition_rejected(self, state_machine):
        """Transitioning to the current state should raise ValueError."""
        state_machine.state = CycleState.SELF_ASSESSING
        with pytest.raises(ValueError):
            state_machine.transition(CycleState.SELF_ASSESSING)

    def test_error_message_contains_current_and_target_state(self, state_machine):
        """Error message should help debug which transition failed."""
        state_machine.state = CycleState.IDLE
        try:
            state_machine.transition(CycleState.COMPLETED)
        except ValueError as e:
            error_msg = str(e)
            assert "idle" in error_msg.lower()
            assert "completed" in error_msg.lower()

    def test_all_cycle_states_defined(self):
        """All expected cycle states should be defined in the enum."""
        expected_states = {
            "idle",
            "self_assessing",
            "belief_check",
            "improvement",
            "runtime_integration",
            "tuning",
            "governance_audit",
            "completed",
            "failed",
        }
        actual_states = {s.value for s in CycleState}
        assert actual_states == expected_states

    def test_state_is_string_enum(self):
        """CycleState should be a string enum for easy serialization."""
        assert isinstance(CycleState.IDLE, str)
        assert CycleState.IDLE == "idle"

    def test_state_machine_has_allowed_transitions_dict(self, state_machine):
        """State machine should have the _allowed transitions dictionary."""
        assert hasattr(state_machine, "_allowed")
        assert CycleState.IDLE in state_machine._allowed
        assert CycleState.COMPLETED in state_machine._allowed

    def test_terminal_states_have_empty_allowed_set(self, state_machine):
        """COMPLETED and FAILED should have empty allowed transitions."""
        assert state_machine._allowed[CycleState.COMPLETED] == set()
        assert state_machine._allowed[CycleState.FAILED] == set()
