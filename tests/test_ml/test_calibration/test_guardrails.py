"""Unit tests for Calibration Adjustment Guardrails.

Tests for AdjustmentGuardrails class including velocity limits,
cooldown periods, oscillation detection, and extreme value protection.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta

import pytest

sys.path.insert(0, "src")

from ml.calibration.dynamic import (
    DEFAULT_COOLDOWN_MINUTES,
    DEFAULT_VELOCITY_LIMIT,
    MAX_ADJUSTMENT_PER_STEP,
    MAX_THRESHOLD,
    MIN_THRESHOLD,
    AdjustmentGuardrails,
    DynamicThresholdAdjuster,
    ThresholdAdjustment,
)


class TestAdjustmentGuardrails:
    """Tests for AdjustmentGuardrails class."""

    @pytest.fixture
    def guardrails(self):
        """Create guardrails instance."""
        return AdjustmentGuardrails()

    @pytest.fixture
    def adjustment_history(self):
        """Create sample adjustment history."""
        now = datetime.now(UTC)
        return [
            ThresholdAdjustment(
                timestamp=now - timedelta(minutes=5),
                signal_type="LONG",
                old_threshold=0.60,
                new_threshold=0.65,
                change_amount=0.05,
                ece_before=0.18,
                ece_after=None,
                reason="Test increase",
            ),
            ThresholdAdjustment(
                timestamp=now - timedelta(minutes=30),
                signal_type="LONG",
                old_threshold=0.55,
                new_threshold=0.60,
                change_amount=0.05,
                ece_before=0.20,
                ece_after=None,
                reason="Test increase",
            ),
            ThresholdAdjustment(
                timestamp=now - timedelta(minutes=45),
                signal_type="SHORT",
                old_threshold=0.60,
                new_threshold=0.55,
                change_amount=-0.05,
                ece_before=0.08,
                ece_after=None,
                reason="Test decrease",
            ),
        ]

    def test_initialization(self, guardrails):
        """Test guardrails initialization."""
        assert guardrails.velocity_limit == DEFAULT_VELOCITY_LIMIT
        assert guardrails.cooldown_minutes == DEFAULT_COOLDOWN_MINUTES
        assert guardrails.max_adjustment_size == MAX_ADJUSTMENT_PER_STEP
        assert guardrails.min_threshold == MIN_THRESHOLD
        assert guardrails.max_threshold == MAX_THRESHOLD

    def test_initialization_custom_values(self):
        """Test guardrails with custom values."""
        guardrails = AdjustmentGuardrails(
            velocity_limit=5,
            cooldown_minutes=20,
            max_adjustment_size=0.08,
            min_threshold=0.45,
            max_threshold=0.90,
        )

        assert guardrails.velocity_limit == 5
        assert guardrails.cooldown_minutes == 20
        assert guardrails.max_adjustment_size == 0.08
        assert guardrails.min_threshold == 0.45
        assert guardrails.max_threshold == 0.90

    def test_check_velocity_limit_allowed(self, guardrails, adjustment_history):
        """Test velocity limit check when under limit."""
        # Only 1 adjustment in last hour for LONG
        allowed, reason = guardrails.check_velocity_limit("LONG", adjustment_history)

        assert allowed is True
        assert reason == ""

    def test_check_velocity_limit_exceeded(self, guardrails):
        """Test velocity limit check when limit exceeded."""
        now = datetime.now(UTC)
        # Create 3 adjustments in last hour (at the limit)
        history = [
            ThresholdAdjustment(
                timestamp=now - timedelta(minutes=i * 15),
                signal_type="LONG",
                old_threshold=0.60,
                new_threshold=0.65,
                change_amount=0.05,
                ece_before=0.18,
                ece_after=None,
                reason="Test",
            )
            for i in range(DEFAULT_VELOCITY_LIMIT)
        ]

        allowed, reason = guardrails.check_velocity_limit("LONG", history)

        assert allowed is False
        assert "Velocity limit exceeded" in reason
        assert "3 adjustments" in reason

    def test_check_velocity_limit_different_signal(
        self, guardrails, adjustment_history
    ):
        """Test velocity limit check for different signal type."""
        # SHORT has only 1 adjustment
        allowed, reason = guardrails.check_velocity_limit("SHORT", adjustment_history)

        assert allowed is True
        assert reason == ""

    def test_check_cooldown_allowed(self, guardrails, adjustment_history):
        """Test cooldown check when enough time passed."""
        now = datetime.now(UTC)
        last_adjustments = {"LONG": now - timedelta(minutes=20)}

        allowed, reason = guardrails.check_cooldown("LONG", last_adjustments)

        assert allowed is True
        assert reason == ""

    def test_check_cooldown_blocked(self, guardrails):
        """Test cooldown check when still in cooldown."""
        now = datetime.now(UTC)
        last_adjustments = {"LONG": now - timedelta(minutes=5)}

        allowed, reason = guardrails.check_cooldown("LONG", last_adjustments)

        assert allowed is False
        assert "Cooldown active" in reason
        assert "remaining" in reason

    def test_check_cooldown_no_previous(self, guardrails):
        """Test cooldown check with no previous adjustment."""
        last_adjustments = {}

        allowed, reason = guardrails.check_cooldown("LONG", last_adjustments)

        assert allowed is True
        assert reason == ""

    def test_check_adjustment_size_allowed(self, guardrails):
        """Test adjustment size check within limits."""
        allowed, reason = guardrails.check_adjustment_size(0.05)

        assert allowed is True
        assert reason == ""

    def test_check_adjustment_size_blocked(self, guardrails):
        """Test adjustment size check exceeding limits."""
        allowed, reason = guardrails.check_adjustment_size(0.15)

        assert allowed is False
        assert "exceeds maximum" in reason
        assert "0.100" in reason

    def test_check_adjustment_size_negative(self, guardrails):
        """Test adjustment size check with negative value."""
        allowed, reason = guardrails.check_adjustment_size(-0.12)

        assert allowed is False
        assert "exceeds maximum" in reason

    def test_check_oscillation_allowed(self, guardrails):
        """Test oscillation check when no flip-flop."""
        now = datetime.now(UTC)
        # Last adjustment was increase, proposing increase
        history = [
            ThresholdAdjustment(
                timestamp=now - timedelta(minutes=10),
                signal_type="LONG",
                old_threshold=0.60,
                new_threshold=0.65,
                change_amount=0.05,
                ece_before=0.18,
                ece_after=None,
                reason="Test",
            )
        ]

        allowed, reason = guardrails.check_oscillation("LONG", 0.05, history)

        assert allowed is True
        assert reason == ""

    def test_check_oscillation_blocked(self, guardrails):
        """Test oscillation check when flip-flop detected."""
        now = datetime.now(UTC)
        # Last adjustment was increase, proposing decrease
        history = [
            ThresholdAdjustment(
                timestamp=now - timedelta(minutes=10),
                signal_type="LONG",
                old_threshold=0.60,
                new_threshold=0.65,
                change_amount=0.05,
                ece_before=0.18,
                ece_after=None,
                reason="Test",
            )
        ]

        allowed, reason = guardrails.check_oscillation("LONG", -0.05, history)

        assert allowed is False
        assert "Oscillation detected" in reason
        assert "increase" in reason
        assert "decrease" in reason

    def test_check_oscillation_old_adjustment(self, guardrails):
        """Test oscillation check with old adjustment (outside window)."""
        now = datetime.now(UTC)
        # Adjustment outside 30-minute window
        history = [
            ThresholdAdjustment(
                timestamp=now - timedelta(hours=1),
                signal_type="LONG",
                old_threshold=0.60,
                new_threshold=0.65,
                change_amount=0.05,
                ece_before=0.18,
                ece_after=None,
                reason="Test",
            )
        ]

        # Should allow even though direction flipped (outside window)
        allowed, reason = guardrails.check_oscillation("LONG", -0.05, history)

        assert allowed is True
        assert reason == ""

    def test_check_extreme_values_allowed(self, guardrails):
        """Test extreme values check within bounds."""
        allowed, reason = guardrails.check_extreme_values(0.60, 0.05)

        assert allowed is True
        assert reason == ""

    def test_check_extreme_values_too_low(self, guardrails):
        """Test extreme values check when result too low."""
        allowed, reason = guardrails.check_extreme_values(0.42, -0.05)

        assert allowed is False
        assert "below minimum" in reason

    def test_check_extreme_values_too_high(self, guardrails):
        """Test extreme values check when result too high."""
        allowed, reason = guardrails.check_extreme_values(0.90, 0.10)

        assert allowed is False
        assert "above maximum" in reason

    def test_validate_adjustment_all_pass(self, guardrails):
        """Test full validation when all checks pass."""
        history = []
        last_adjustments = {}

        allowed, reason = guardrails.validate_adjustment(
            signal_type="LONG",
            proposed_change=0.05,
            current_threshold=0.60,
            last_adjustment_times=last_adjustments,
            history=history,
        )

        assert allowed is True
        assert reason == ""

    def test_validate_adjustment_velocity_blocked(self, guardrails):
        """Test full validation when velocity check fails."""
        now = datetime.now(UTC)
        # Create history at velocity limit
        history = [
            ThresholdAdjustment(
                timestamp=now - timedelta(minutes=i * 15),
                signal_type="LONG",
                old_threshold=0.60,
                new_threshold=0.65,
                change_amount=0.05,
                ece_before=0.18,
                ece_after=None,
                reason="Test",
            )
            for i in range(DEFAULT_VELOCITY_LIMIT)
        ]

        allowed, reason = guardrails.validate_adjustment(
            signal_type="LONG",
            proposed_change=0.05,
            current_threshold=0.60,
            last_adjustment_times={},
            history=history,
        )

        assert allowed is False
        assert "Velocity limit exceeded" in reason

    def test_validate_adjustment_cooldown_blocked(self, guardrails):
        """Test full validation when cooldown check fails."""
        now = datetime.now(UTC)
        last_adjustments = {"LONG": now - timedelta(minutes=5)}

        allowed, reason = guardrails.validate_adjustment(
            signal_type="LONG",
            proposed_change=0.05,
            current_threshold=0.60,
            last_adjustment_times=last_adjustments,
            history=[],
        )

        assert allowed is False
        assert "Cooldown active" in reason


class TestDynamicThresholdAdjusterWithGuardrails:
    """Tests for DynamicThresholdAdjuster guardrail integration."""

    @pytest.fixture
    def controller(self):
        """Create a mock controller."""
        from ml.calibration.controller import ThresholdController, ThresholdMode
        from ml.calibration.data_collector import CalibrationDataCollector
        from ml.calibration.optimizer import ThresholdOptimizer
        from ml.calibration.storage import InMemoryCalibrationStorage

        storage = InMemoryCalibrationStorage()
        collector = CalibrationDataCollector(storage=storage)
        optimizer = ThresholdOptimizer(collector)
        controller = ThresholdController(optimizer, mode=ThresholdMode.DYNAMIC)
        return controller

    def test_initialization_with_guardrails(self, controller):
        """Test adjuster initialization with guardrails."""
        adjuster = DynamicThresholdAdjuster(
            controller,
            velocity_limit=3,
            cooldown_minutes=15,
            enable_guardrails=True,
        )

        assert adjuster.enable_guardrails is True
        assert adjuster.guardrails.velocity_limit == 3
        assert adjuster.guardrails.cooldown_minutes == 15

    def test_initialization_without_guardrails(self, controller):
        """Test adjuster initialization without guardrails."""
        adjuster = DynamicThresholdAdjuster(
            controller,
            enable_guardrails=False,
        )

        assert adjuster.enable_guardrails is False

    def test_guardrails_enabled_by_default(self, controller):
        """Test that guardrails are enabled by default."""
        adjuster = DynamicThresholdAdjuster(controller)

        assert adjuster.enable_guardrails is True


class TestGuardrailConstants:
    """Tests for guardrail constants."""

    def test_default_velocity_limit(self):
        """Test default velocity limit value."""
        assert DEFAULT_VELOCITY_LIMIT == 3

    def test_default_cooldown_minutes(self):
        """Test default cooldown minutes."""
        assert DEFAULT_COOLDOWN_MINUTES == 15

    def test_max_adjustment_per_step(self):
        """Test max adjustment per step (increased to 0.10)."""
        assert MAX_ADJUSTMENT_PER_STEP == 0.10

    def test_threshold_bounds(self):
        """Test threshold bounds."""
        assert MIN_THRESHOLD == 0.40
        assert MAX_THRESHOLD == 0.95


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
