"""Tests for brain rollback handler (ST-CHISE-005).

Tests cover:
- Rollback trigger validation
- System state verification
- Rollback step execution
- Emergency rollback with --force
- Post-mortem logging
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from src.brain.rollback_handler import (
    RollbackHandler,
    RollbackOutcome,
    RollbackStatus,
    RollbackStepResult,
    RollbackTrigger,
    SafetyCheckResult,
    SystemState,
    RollbackSafetyError,
)


class TestSystemState:
    """Test SystemState dataclass."""

    def test_creation(self):
        """Test state creation."""
        state = SystemState(
            timestamp=datetime.utcnow(),
            brain_version="v1.0.0",
            active_signals=True,
            active_trades_count=5,
            data_consistency_ok=True,
        )
        assert state.brain_version == "v1.0.0"
        assert state.active_trades_count == 5

    def test_to_dict(self):
        """Test conversion to dictionary."""
        now = datetime.utcnow()
        state = SystemState(
            timestamp=now,
            brain_version="v1.0.0",
            active_signals=False,
            active_trades_count=0,
            data_consistency_ok=True,
            last_error=None,
        )
        data = state.to_dict()
        assert data["brain_version"] == "v1.0.0"
        assert data["active_trades_count"] == 0


class TestRollbackStepResult:
    """Test RollbackStepResult dataclass."""

    def test_creation(self):
        """Test result creation."""
        result = RollbackStepResult(
            step_number=1,
            description="Stop signals",
            status=RollbackStatus.COMPLETED,
            started_at=datetime.utcnow(),
            output="Signals stopped",
            verification_passed=True,
        )
        assert result.step_number == 1
        assert result.verification_passed is True


class TestRollbackOutcome:
    """Test RollbackOutcome dataclass."""

    @pytest.fixture
    def sample_outcome(self):
        """Create sample rollback outcome."""
        return RollbackOutcome(
            rollback_id="RB-1234567890-test",
            trigger=RollbackTrigger.ECE_DEGRADATION,
            reason="ECE degradation > 0.15",
            from_version="v2.0.0",
            to_version="v1.0.0",
            initiated_at=datetime.utcnow(),
            initiated_by="system",
            status=RollbackStatus.COMPLETED,
            steps_results=[
                RollbackStepResult(
                    step_number=1,
                    description="Stop signals",
                    status=RollbackStatus.COMPLETED,
                    started_at=datetime.utcnow(),
                    completed_at=datetime.utcnow(),
                    duration_seconds=30.0,
                    output="Signals stopped",
                    verification_passed=True,
                ),
            ],
        )

    def test_creation(self):
        """Test outcome creation."""
        outcome = RollbackOutcome(
            rollback_id="RB-123",
            trigger=RollbackTrigger.HUMAN_REQUEST,
            reason="Manual rollback",
            from_version="v2.0.0",
            to_version="v1.0.0",
            initiated_at=datetime.utcnow(),
            initiated_by="admin",
        )
        assert outcome.rollback_id == "RB-123"
        assert outcome.trigger == RollbackTrigger.HUMAN_REQUEST

    def test_to_dict(self, sample_outcome):
        """Test conversion to dictionary."""
        data = sample_outcome.to_dict()
        assert data["rollback_id"] == "RB-1234567890-test"
        assert data["trigger"] == "ece_degradation"
        assert len(data["steps_results"]) == 1

    def test_to_markdown(self, sample_outcome):
        """Test markdown report generation."""
        md = sample_outcome.to_markdown()
        assert "# Rollback Post-Mortem" in md
        assert "RB-1234567890-test" in md
        assert "## Rollback Steps" in md
        assert "## Summary" in md


class TestRollbackHandler:
    """Test RollbackHandler functionality."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for logs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def handler(self, temp_dir):
        """Create rollback handler."""
        return RollbackHandler(
            logs_dir=temp_dir,
            current_version="v2.0.0",
            previous_version="v1.0.0",
        )

    @pytest.mark.asyncio
    async def test_verify_system_state(self, handler):
        """Test system state verification."""
        state = await handler.verify_system_state()

        assert state.brain_version == "v2.0.0"
        assert isinstance(state.active_signals, bool)
        assert isinstance(state.active_trades_count, int)
        assert isinstance(state.data_consistency_ok, bool)

    def test_validate_trigger_ece_degradation(self, handler):
        """Test ECE degradation trigger validation."""
        is_valid, reason = handler.validate_trigger(
            RollbackTrigger.ECE_DEGRADATION,
            value=0.20,  # Above 0.15 threshold
        )
        assert is_valid is True
        assert "0.20" in reason

    def test_validate_trigger_ece_not_met(self, handler):
        """Test ECE degradation trigger not met."""
        is_valid, reason = handler.validate_trigger(
            RollbackTrigger.ECE_DEGRADATION,
            value=0.10,  # Below 0.15 threshold
        )
        assert is_valid is False

    def test_validate_trigger_win_rate(self, handler):
        """Test win rate drop trigger validation."""
        is_valid, reason = handler.validate_trigger(
            RollbackTrigger.WIN_RATE_DROP,
            value=0.45,  # Below 0.50 threshold
        )
        assert is_valid is True

    def test_validate_trigger_max_drawdown(self, handler):
        """Test max drawdown trigger validation."""
        is_valid, reason = handler.validate_trigger(
            RollbackTrigger.MAX_DRAWDOWN,
            value=0.25,  # Above 0.20 threshold
        )
        assert is_valid is True

    def test_validate_trigger_human_request(self, handler):
        """Test human request trigger always valid."""
        is_valid, reason = handler.validate_trigger(
            RollbackTrigger.HUMAN_REQUEST,
        )
        assert is_valid is True

    def test_validate_trigger_safety_violation(self, handler):
        """Test safety violation trigger always valid."""
        is_valid, reason = handler.validate_trigger(
            RollbackTrigger.SAFETY_VIOLATION,
        )
        assert is_valid is True

    @pytest.mark.asyncio
    async def test_trigger_rollback_success(self, handler):
        """Test successful rollback."""
        outcome = await handler.trigger_rollback(
            trigger=RollbackTrigger.HUMAN_REQUEST,
            reason="Test rollback",
            initiated_by="test",
        )

        assert outcome.rollback_id.startswith("RB-")
        assert outcome.trigger == RollbackTrigger.HUMAN_REQUEST
        assert outcome.from_version == "v2.0.0"
        assert outcome.to_version == "v1.0.0"
        assert outcome.status == RollbackStatus.COMPLETED
        assert len(outcome.steps_results) == 5  # All steps executed

    @pytest.mark.asyncio
    async def test_trigger_rollback_with_force(self, handler):
        """Test rollback with force override."""
        outcome = await handler.trigger_rollback(
            trigger=RollbackTrigger.ECE_DEGRADATION,
            reason="ECE > 0.15",
            initiated_by="system",
            force=True,
        )

        assert outcome.force_override is True
        assert outcome.status == RollbackStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_rollback_logs_saved(self, handler, temp_dir):
        """Test that rollback logs are saved."""
        outcome = await handler.trigger_rollback(
            trigger=RollbackTrigger.HUMAN_REQUEST,
            reason="Test",
        )

        # Check files created
        json_file = temp_dir / f"{outcome.rollback_id}.json"
        md_file = temp_dir / f"{outcome.rollback_id}.md"

        assert json_file.exists()
        assert md_file.exists()

        # Verify JSON content
        with open(json_file) as f:
            data = json.load(f)
            assert data["rollback_id"] == outcome.rollback_id

    @pytest.mark.asyncio
    async def test_emergency_rollback(self, handler):
        """Test emergency rollback."""
        outcome = await handler.emergency_rollback(
            reason="Critical failure",
            force=True,
        )

        assert outcome.trigger == RollbackTrigger.HUMAN_REQUEST
        assert "EMERGENCY" in outcome.reason
        assert outcome.initiated_by == "emergency_cli"

    def test_get_last_outcome(self, handler):
        """Test getting last outcome."""
        assert handler.get_last_outcome() is None

    @pytest.mark.asyncio
    async def test_get_last_outcome_after_rollback(self, handler):
        """Test getting last outcome after rollback."""
        await handler.trigger_rollback(
            trigger=RollbackTrigger.HUMAN_REQUEST,
            reason="Test",
        )

        outcome = handler.get_last_outcome()
        assert outcome is not None
        assert outcome.rollback_id.startswith("RB-")

    def test_list_rollback_logs_empty(self, handler):
        """Test listing logs when empty."""
        logs = handler.list_rollback_logs()
        assert logs == []

    @pytest.mark.asyncio
    async def test_list_rollback_logs(self, handler):
        """Test listing rollback logs."""
        await handler.trigger_rollback(
            trigger=RollbackTrigger.HUMAN_REQUEST,
            reason="Test 1",
        )
        await handler.trigger_rollback(
            trigger=RollbackTrigger.HUMAN_REQUEST,
            reason="Test 2",
        )

        logs = handler.list_rollback_logs()
        assert len(logs) == 2

    def test_load_nonexistent_log(self, handler):
        """Test loading non-existent log."""
        outcome = handler.load_rollback_log("NONEXISTENT")
        assert outcome is None

    @pytest.mark.asyncio
    async def test_load_rollback_log(self, handler):
        """Test loading rollback log."""
        original = await handler.trigger_rollback(
            trigger=RollbackTrigger.HUMAN_REQUEST,
            reason="Test",
        )

        loaded = handler.load_rollback_log(original.rollback_id)
        assert loaded is not None
        assert loaded.rollback_id == original.rollback_id
        assert loaded.trigger == original.trigger
        assert loaded.from_version == original.from_version

    @pytest.mark.asyncio
    async def test_rollback_step_results(self, handler):
        """Test that all steps produce results."""
        outcome = await handler.trigger_rollback(
            trigger=RollbackTrigger.HUMAN_REQUEST,
            reason="Test",
        )

        assert len(outcome.steps_results) == 5

        # Check each step has required fields
        for step in outcome.steps_results:
            assert step.step_number > 0
            assert step.description
            assert step.started_at
            assert step.status in [RollbackStatus.COMPLETED, RollbackStatus.FAILED]

    @pytest.mark.asyncio
    async def test_rollback_timing(self, handler):
        """Test rollback timing is tracked."""
        outcome = await handler.trigger_rollback(
            trigger=RollbackTrigger.HUMAN_REQUEST,
            reason="Test",
        )

        assert outcome.initiated_at is not None
        assert outcome.started_at is not None
        assert outcome.completed_at is not None
        assert outcome.total_duration_seconds >= 0

    @pytest.mark.asyncio
    async def test_initial_state_captured(self, handler):
        """Test that initial state is captured."""
        outcome = await handler.trigger_rollback(
            trigger=RollbackTrigger.HUMAN_REQUEST,
            reason="Test",
        )

        assert outcome.initial_state is not None
        assert outcome.initial_state.brain_version == "v2.0.0"

    @pytest.mark.asyncio
    async def test_final_state_captured(self, handler):
        """Test that final state is captured."""
        outcome = await handler.trigger_rollback(
            trigger=RollbackTrigger.HUMAN_REQUEST,
            reason="Test",
        )

        assert outcome.final_state is not None


class TestRollbackTriggers:
    """Test rollback trigger thresholds."""

    def test_ece_threshold_value(self):
        """Test ECE threshold is 0.15."""
        handler = RollbackHandler()
        threshold = handler.TRIGGER_THRESHOLDS[RollbackTrigger.ECE_DEGRADATION]
        assert threshold["threshold"] == 0.15

    def test_win_rate_threshold_value(self):
        """Test win rate threshold is 0.50."""
        handler = RollbackHandler()
        threshold = handler.TRIGGER_THRESHOLDS[RollbackTrigger.WIN_RATE_DROP]
        assert threshold["threshold"] == 0.50

    def test_max_drawdown_threshold_value(self):
        """Test max drawdown threshold is 0.20."""
        handler = RollbackHandler()
        threshold = handler.TRIGGER_THRESHOLDS[RollbackTrigger.MAX_DRAWDOWN]
        assert threshold["threshold"] == 0.20


class TestRollbackSafetyError:
    """Test RollbackSafetyError exception."""

    def test_exception_creation(self):
        """Test exception can be raised and caught."""
        with pytest.raises(RollbackSafetyError) as exc_info:
            raise RollbackSafetyError("Test error message")

        assert "Test error message" in str(exc_info.value)
