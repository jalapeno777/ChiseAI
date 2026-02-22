"""Unit tests for Dynamic Threshold Adjustment System.

Tests for DynamicThresholdEngine and ThresholdGuardrails including:
- Velocity limits (max ±5% per day)
- 24h cooldown between adjustments
- Oscillation detection (3+ direction changes in 7 days triggers 48h freeze)
- ECE-based adjustment when ECE > 0.10
- Manual override pauses auto-adjustment for 7 days
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta

import pytest

sys.path.insert(0, "src")

from confidence.ece import SignalType
from ml.calibration.dynamic_threshold import (
    COOLDOWN_HOURS,
    ECE_ADJUSTMENT_THRESHOLD,
    MAX_DAILY_CHANGE_PERCENT,
    MAX_THRESHOLD,
    MIN_THRESHOLD,
    OSCILLATION_DIRECTION_CHANGES,
    OSCILLATION_FREEZE_HOURS,
    OSCILLATION_WINDOW_DAYS,
    AdjustmentHistory,
    DynamicThresholdConfig,
    DynamicThresholdEngine,
    ThresholdAdjustmentRecord,
)
from ml.calibration.threshold_guardrails import (
    AuditEventType,
    GuardrailConfig,
    ManualOverride,
    OverrideReason,
    ThresholdGuardrails,
)


class MockECEProvider:
    """Mock ECE provider for testing."""

    def __init__(self, ece_values: dict | None = None):
        self.ece_values = ece_values or {}

    async def get_ece_for_strategy(
        self,
        strategy_id: str,
        signal_type: SignalType | None = None,
        days: int = 7,
    ) -> float | None:
        key = (strategy_id, signal_type)
        return self.ece_values.get(key)


class TestThresholdAdjustmentRecord:
    """Tests for ThresholdAdjustmentRecord."""

    def test_creation(self):
        """Test creating a threshold adjustment record."""
        record = ThresholdAdjustmentRecord(
            timestamp=datetime.now(UTC),
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            old_threshold=0.60,
            new_threshold=0.65,
            change_amount=0.05,
            change_percent=8.33,
            ece_before=0.12,
            ece_after=0.10,
            reason="ECE > threshold",
            triggered_by="ece_high",
        )

        assert record.strategy_id == "grid_btc_1h"
        assert record.signal_type == SignalType.ENTRY
        assert record.old_threshold == 0.60
        assert record.new_threshold == 0.65
        assert record.change_amount == 0.05

    def test_to_dict(self):
        """Test conversion to dictionary."""
        now = datetime.now(UTC)
        record = ThresholdAdjustmentRecord(
            timestamp=now,
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            old_threshold=0.60,
            new_threshold=0.65,
            change_amount=0.05,
            change_percent=8.33,
            ece_before=0.12,
            ece_after=0.10,
            reason="ECE > threshold",
            triggered_by="ece_high",
        )

        d = record.to_dict()
        assert d["strategy_id"] == "grid_btc_1h"
        assert d["signal_type"] == "entry"
        assert d["timestamp"] == now.isoformat()
        assert d["old_threshold"] == 0.60


class TestAdjustmentHistory:
    """Tests for AdjustmentHistory."""

    def test_add_and_retrieve(self):
        """Test adding and retrieving adjustments."""
        history = AdjustmentHistory()

        record = ThresholdAdjustmentRecord(
            timestamp=datetime.now(UTC),
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            old_threshold=0.60,
            new_threshold=0.65,
            change_amount=0.05,
            change_percent=8.33,
            ece_before=0.12,
            ece_after=None,
            reason="Test",
            triggered_by="ece_high",
        )

        history.add(record)
        assert len(history.adjustments) == 1

    def test_cleanup_old(self):
        """Test cleanup of old adjustments."""
        history = AdjustmentHistory(max_history_days=7)
        now = datetime.now(UTC)

        # Add old adjustment
        old_record = ThresholdAdjustmentRecord(
            timestamp=now - timedelta(days=10),
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            old_threshold=0.60,
            new_threshold=0.65,
            change_amount=0.05,
            change_percent=8.33,
            ece_before=0.12,
            ece_after=None,
            reason="Test",
            triggered_by="ece_high",
        )

        # Add recent adjustment
        recent_record = ThresholdAdjustmentRecord(
            timestamp=now,
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            old_threshold=0.65,
            new_threshold=0.70,
            change_amount=0.05,
            change_percent=7.69,
            ece_before=0.11,
            ece_after=None,
            reason="Test",
            triggered_by="ece_high",
        )

        history.add(old_record)
        history.add(recent_record)
        history._cleanup_old()

        assert len(history.adjustments) == 1
        assert history.adjustments[0] == recent_record

    def test_count_direction_changes_no_changes(self):
        """Test direction change counting with no changes."""
        history = AdjustmentHistory()
        now = datetime.now(UTC)

        # Two increases - no direction change
        history.add(
            ThresholdAdjustmentRecord(
                timestamp=now - timedelta(days=2),
                strategy_id="grid_btc_1h",
                signal_type=SignalType.ENTRY,
                old_threshold=0.60,
                new_threshold=0.65,
                change_amount=0.05,
                change_percent=8.33,
                ece_before=0.12,
                ece_after=None,
                reason="Test",
                triggered_by="ece_high",
            )
        )

        history.add(
            ThresholdAdjustmentRecord(
                timestamp=now - timedelta(days=1),
                strategy_id="grid_btc_1h",
                signal_type=SignalType.ENTRY,
                old_threshold=0.65,
                new_threshold=0.70,
                change_amount=0.05,
                change_percent=7.69,
                ece_before=0.11,
                ece_after=None,
                reason="Test",
                triggered_by="ece_high",
            )
        )

        count = history.count_direction_changes("grid_btc_1h", SignalType.ENTRY, 7)
        assert count == 0

    def test_count_direction_changes_with_changes(self):
        """Test direction change counting with multiple changes."""
        history = AdjustmentHistory()
        now = datetime.now(UTC)

        # Increase -> Decrease -> Increase = 2 direction changes
        adjustments = [
            (0.60, 0.65, 0.05),  # Increase
            (0.65, 0.60, -0.05),  # Decrease (change 1)
            (0.60, 0.55, -0.05),  # Decrease (no change)
            (0.55, 0.60, 0.05),  # Increase (change 2)
        ]

        for i, (old, new, change) in enumerate(adjustments):
            history.add(
                ThresholdAdjustmentRecord(
                    timestamp=now - timedelta(days=4 - i),
                    strategy_id="grid_btc_1h",
                    signal_type=SignalType.ENTRY,
                    old_threshold=old,
                    new_threshold=new,
                    change_amount=change,
                    change_percent=change / old * 100 if old else 0,
                    ece_before=0.12,
                    ece_after=None,
                    reason="Test",
                    triggered_by="ece_high",
                )
            )

        count = history.count_direction_changes("grid_btc_1h", SignalType.ENTRY, 7)
        assert count == 2


class TestDynamicThresholdConfig:
    """Tests for DynamicThresholdConfig."""

    def test_default_values(self):
        """Test default configuration values."""
        config = DynamicThresholdConfig()

        assert config.min_threshold == MIN_THRESHOLD
        assert config.max_threshold == MAX_THRESHOLD
        assert config.max_daily_change_percent == MAX_DAILY_CHANGE_PERCENT
        assert config.ece_threshold == ECE_ADJUSTMENT_THRESHOLD
        assert config.cooldown_hours == COOLDOWN_HOURS
        assert config.oscillation_window_days == OSCILLATION_WINDOW_DAYS
        assert config.oscillation_freeze_hours == OSCILLATION_FREEZE_HOURS
        assert config.oscillation_direction_changes == OSCILLATION_DIRECTION_CHANGES

    def test_custom_values(self):
        """Test custom configuration values."""
        config = DynamicThresholdConfig(
            min_threshold=0.45,
            max_threshold=0.90,
            max_daily_change_percent=0.03,
            ece_threshold=0.08,
            cooldown_hours=12,
            oscillation_window_days=5,
        )

        assert config.min_threshold == 0.45
        assert config.max_threshold == 0.90
        assert config.max_daily_change_percent == 0.03
        assert config.ece_threshold == 0.08
        assert config.cooldown_hours == 12
        assert config.oscillation_window_days == 5

    def test_validation_min_threshold(self):
        """Test validation of min_threshold."""
        with pytest.raises(ValueError, match="min_threshold must be in"):
            DynamicThresholdConfig(min_threshold=-0.1)

        with pytest.raises(ValueError, match="min_threshold must be in"):
            DynamicThresholdConfig(min_threshold=1.5)

    def test_validation_max_threshold(self):
        """Test validation of max_threshold."""
        with pytest.raises(ValueError, match="max_threshold must be in"):
            DynamicThresholdConfig(max_threshold=-0.1)

        with pytest.raises(ValueError, match="max_threshold must be in"):
            DynamicThresholdConfig(max_threshold=1.5)

    def test_validation_threshold_order(self):
        """Test validation that min < max."""
        with pytest.raises(ValueError, match="min_threshold must be < max_threshold"):
            DynamicThresholdConfig(min_threshold=0.60, max_threshold=0.50)


class TestDynamicThresholdEngine:
    """Tests for DynamicThresholdEngine."""

    @pytest.fixture
    def ece_provider(self):
        """Create mock ECE provider."""
        provider = MockECEProvider()
        return provider

    @pytest.fixture
    def engine(self, ece_provider):
        """Create dynamic threshold engine."""
        return DynamicThresholdEngine(ece_provider=ece_provider)

    @pytest.mark.asyncio
    async def test_no_ece_provider(self):
        """Test behavior when no ECE provider configured."""
        engine = DynamicThresholdEngine(ece_provider=None)

        result = await engine.evaluate_and_adjust(
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            current_threshold=0.65,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_no_ece_data(self, engine, ece_provider):
        """Test behavior when no ECE data available."""
        ece_provider.ece_values = {}

        result = await engine.evaluate_and_adjust(
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            current_threshold=0.65,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_no_adjustment_needed_ece_good(self, engine, ece_provider):
        """Test when ECE is good (no adjustment needed)."""
        ece_provider.ece_values = {
            ("grid_btc_1h", SignalType.ENTRY): 0.06,  # Between 0.05 and 0.10
        }

        result = await engine.evaluate_and_adjust(
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            current_threshold=0.65,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_adjustment_ece_high(self, engine, ece_provider):
        """Test adjustment when ECE is high."""
        ece_provider.ece_values = {
            ("grid_btc_1h", SignalType.ENTRY): 0.15,  # > 0.10 threshold
        }

        result = await engine.evaluate_and_adjust(
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            current_threshold=0.65,
        )

        assert result is not None
        assert result.old_threshold == 0.65
        assert result.new_threshold > 0.65  # Should increase
        assert result.ece_before == 0.15
        assert result.triggered_by == "ece_high"

    @pytest.mark.asyncio
    async def test_adjustment_ece_low(self, engine, ece_provider):
        """Test adjustment when ECE is very low."""
        ece_provider.ece_values = {
            ("grid_btc_1h", SignalType.ENTRY): 0.03,  # < 0.05
        }

        result = await engine.evaluate_and_adjust(
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            current_threshold=0.65,
        )

        assert result is not None
        assert result.old_threshold == 0.65
        assert result.new_threshold < 0.65  # Should decrease
        assert result.ece_before == 0.03
        assert result.triggered_by == "ece_low"

    @pytest.mark.asyncio
    async def test_velocity_limit_increase(self, engine, ece_provider):
        """Test that velocity limit is applied for increases."""
        ece_provider.ece_values = {
            ("grid_btc_1h", SignalType.ENTRY): 0.25,  # Very high ECE
        }

        result = await engine.evaluate_and_adjust(
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            current_threshold=0.65,
        )

        # Max change should be 5% of 0.65 = 0.0325
        max_change = 0.65 * MAX_DAILY_CHANGE_PERCENT
        assert result is not None
        assert (
            result.change_amount <= max_change + 0.001
        )  # Allow small floating point error

    @pytest.mark.asyncio
    async def test_cooldown_enforcement(self, engine, ece_provider):
        """Test that 24h cooldown is enforced."""
        ece_provider.ece_values = {
            ("grid_btc_1h", SignalType.ENTRY): 0.15,
        }

        # First adjustment
        result1 = await engine.evaluate_and_adjust(
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            current_threshold=0.65,
        )
        assert result1 is not None

        # Second adjustment immediately should fail due to cooldown
        result2 = await engine.evaluate_and_adjust(
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            current_threshold=result1.new_threshold,
        )
        assert result2 is None

    @pytest.mark.asyncio
    async def test_cooldown_expired(self, engine, ece_provider):
        """Test that adjustment works after cooldown expires."""
        ece_provider.ece_values = {
            ("grid_btc_1h", SignalType.ENTRY): 0.15,
        }

        # First adjustment
        result1 = await engine.evaluate_and_adjust(
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            current_threshold=0.65,
        )
        assert result1 is not None

        # Simulate cooldown expired by manipulating last adjustment time
        past = datetime.now(UTC) - timedelta(hours=COOLDOWN_HOURS + 1)
        engine._last_adjustment[("grid_btc_1h", SignalType.ENTRY)] = past

        # Second adjustment should now work
        result2 = await engine.evaluate_and_adjust(
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            current_threshold=result1.new_threshold,
        )
        assert result2 is not None

    @pytest.mark.asyncio
    async def test_oscillation_detection_freeze(self, engine, ece_provider):
        """Test oscillation detection triggers freeze."""
        now = datetime.now(UTC)

        # Create history with 3 direction changes
        adjustments = [
            (0.60, 0.65, 0.05),  # Increase
            (0.65, 0.60, -0.05),  # Decrease (change 1)
            (0.60, 0.55, -0.05),  # Decrease
            (0.55, 0.60, 0.05),  # Increase (change 2)
            (0.60, 0.55, -0.05),  # Decrease (change 3)
        ]

        for i, (old, new, change) in enumerate(adjustments):
            engine._history.add(
                ThresholdAdjustmentRecord(
                    timestamp=now - timedelta(days=6 - i),
                    strategy_id="grid_btc_1h",
                    signal_type=SignalType.ENTRY,
                    old_threshold=old,
                    new_threshold=new,
                    change_amount=change,
                    change_percent=change / old * 100 if old else 0,
                    ece_before=0.12,
                    ece_after=None,
                    reason="Test",
                    triggered_by="ece_high",
                )
            )

        # Next adjustment should trigger freeze
        ece_provider.ece_values = {
            ("grid_btc_1h", SignalType.ENTRY): 0.15,
        }

        # Set last adjustment to be outside cooldown
        past = now - timedelta(hours=COOLDOWN_HOURS + 1)
        engine._last_adjustment[("grid_btc_1h", SignalType.ENTRY)] = past

        result = await engine.evaluate_and_adjust(
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            current_threshold=0.55,
        )

        # Adjustment should still work, but freeze should be applied after
        assert result is not None

        # Check that freeze is now active
        assert engine._is_frozen("grid_btc_1h", SignalType.ENTRY)

        # Try another adjustment - should be blocked
        engine._last_adjustment[("grid_btc_1h", SignalType.ENTRY)] = past

        result2 = await engine.evaluate_and_adjust(
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            current_threshold=result.new_threshold,
        )

        assert result2 is None

    @pytest.mark.asyncio
    async def test_min_threshold_bound(self, engine, ece_provider):
        """Test minimum threshold boundary."""
        ece_provider.ece_values = {
            ("grid_btc_1h", SignalType.ENTRY): 0.03,  # Very low ECE
        }

        # Start near minimum
        result = await engine.evaluate_and_adjust(
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            current_threshold=0.41,
        )

        assert result is not None
        assert result.new_threshold >= MIN_THRESHOLD

    @pytest.mark.asyncio
    async def test_max_threshold_bound(self, engine, ece_provider):
        """Test maximum threshold boundary."""
        ece_provider.ece_values = {
            ("grid_btc_1h", SignalType.ENTRY): 0.25,  # Very high ECE
        }

        # Start near maximum
        result = await engine.evaluate_and_adjust(
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            current_threshold=0.94,
        )

        assert result is not None
        assert result.new_threshold <= MAX_THRESHOLD

    def test_get_time_until_next_adjustment_no_cooldown(self, engine):
        """Test getting time when no cooldown."""
        result = engine.get_time_until_next_adjustment("grid_btc_1h", SignalType.ENTRY)
        assert result is None

    def test_get_time_until_next_adjustment_with_cooldown(self, engine):
        """Test getting time when in cooldown."""
        now = datetime.now(UTC)
        engine._last_adjustment[("grid_btc_1h", SignalType.ENTRY)] = now - timedelta(
            hours=12
        )

        result = engine.get_time_until_next_adjustment("grid_btc_1h", SignalType.ENTRY)

        assert result is not None
        assert result.total_seconds() > 0
        assert result.total_seconds() <= 12 * 3600

    def test_get_adjustment_summary_empty(self, engine):
        """Test summary with no adjustments."""
        summary = engine.get_adjustment_summary()

        assert summary["total_adjustments"] == 0
        assert summary["by_strategy"] == {}
        assert summary["avg_change_magnitude"] == 0.0

    def test_reset(self, engine, ece_provider):
        """Test reset functionality."""
        now = datetime.now(UTC)

        # Add some state
        engine._history.add(
            ThresholdAdjustmentRecord(
                timestamp=now,
                strategy_id="grid_btc_1h",
                signal_type=SignalType.ENTRY,
                old_threshold=0.60,
                new_threshold=0.65,
                change_amount=0.05,
                change_percent=8.33,
                ece_before=0.12,
                ece_after=None,
                reason="Test",
                triggered_by="ece_high",
            )
        )
        engine._last_adjustment[("grid_btc_1h", SignalType.ENTRY)] = now
        engine._freeze_until[("grid_btc_1h", SignalType.ENTRY)] = now + timedelta(
            hours=48
        )

        # Reset
        engine.reset()

        assert len(engine._history.adjustments) == 0
        assert len(engine._last_adjustment) == 0
        assert len(engine._freeze_until) == 0


class TestThresholdGuardrails:
    """Tests for ThresholdGuardrails."""

    @pytest.fixture
    def guardrails(self):
        """Create threshold guardrails."""
        return ThresholdGuardrails()

    def test_enable_manual_override(self, guardrails):
        """Test enabling manual override."""
        override = guardrails.enable_manual_override(
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            reason="Market volatility",
            user_id="user123",
        )

        assert override.strategy_id == "grid_btc_1h"
        assert override.signal_type == SignalType.ENTRY
        assert override.reason == "Market volatility"
        assert override.user_id == "user123"
        assert override.is_active

    def test_manual_override_duration(self, guardrails):
        """Test that manual override has correct duration."""
        override = guardrails.enable_manual_override(
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            reason="Test",
            user_id="user123",
        )

        expected_duration = timedelta(days=7)
        actual_duration = override.expires_at - override.enabled_at

        # Allow 1 second tolerance
        assert abs((actual_duration - expected_duration).total_seconds()) < 1

    def test_get_manual_override_active(self, guardrails):
        """Test getting active manual override."""
        guardrails.enable_manual_override(
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            reason="Test",
            user_id="user123",
        )

        override = guardrails.get_manual_override("grid_btc_1h", SignalType.ENTRY)

        assert override is not None
        assert override.is_active

    def test_get_manual_override_none(self, guardrails):
        """Test getting override when none exists."""
        override = guardrails.get_manual_override("grid_btc_1h", SignalType.ENTRY)

        assert override is None

    def test_get_manual_override_expired(self, guardrails):
        """Test that expired overrides are cleaned up."""
        # Create override in the past
        past = datetime.now(UTC) - timedelta(days=8)
        override = ManualOverride(
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            enabled_at=past - timedelta(days=7),
            expires_at=past,
            reason="Test",
            override_reason=OverrideReason.OTHER,
            user_id="user123",
        )
        guardrails._overrides[("grid_btc_1h", SignalType.ENTRY)] = override

        # Should return None since expired
        result = guardrails.get_manual_override("grid_btc_1h", SignalType.ENTRY)
        assert result is None

    def test_disable_manual_override(self, guardrails):
        """Test disabling manual override."""
        guardrails.enable_manual_override(
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            reason="Test",
            user_id="user123",
        )

        result = guardrails.disable_manual_override(
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            user_id="user456",
        )

        assert result is True
        assert guardrails.get_manual_override("grid_btc_1h", SignalType.ENTRY) is None

    def test_disable_manual_override_none(self, guardrails):
        """Test disabling when no override exists."""
        result = guardrails.disable_manual_override(
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            user_id="user456",
        )

        assert result is False

    def test_can_auto_adjust_allowed(self, guardrails):
        """Test can_auto_adjust when allowed."""
        can_adjust, reason = guardrails.can_auto_adjust("grid_btc_1h", SignalType.ENTRY)

        assert can_adjust is True
        assert reason == ""

    def test_can_auto_adjust_blocked_override(self, guardrails):
        """Test can_auto_adjust blocked by manual override."""
        guardrails.enable_manual_override(
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            reason="Test",
            user_id="user123",
        )

        can_adjust, reason = guardrails.can_auto_adjust("grid_btc_1h", SignalType.ENTRY)

        assert can_adjust is False
        assert "Manual override active" in reason

    def test_can_auto_adjust_blocked_freeze(self, guardrails):
        """Test can_auto_adjust blocked by oscillation freeze."""
        future = datetime.now(UTC) + timedelta(hours=24)
        guardrails._frozen_until[("grid_btc_1h", SignalType.ENTRY)] = future

        can_adjust, reason = guardrails.can_auto_adjust("grid_btc_1h", SignalType.ENTRY)

        assert can_adjust is False
        assert "Oscillation freeze" in reason

    def test_enforce_boundaries_no_clamp(self, guardrails):
        """Test boundary enforcement with valid value."""
        threshold, enforced, reason = guardrails.enforce_boundaries(0.65)

        assert threshold == 0.65
        assert enforced is False
        assert reason == ""

    def test_enforce_boundaries_clamp_low(self, guardrails):
        """Test boundary enforcement with low value."""
        threshold, enforced, reason = guardrails.enforce_boundaries(0.30)

        assert threshold == 0.40
        assert enforced is True
        assert "minimum" in reason

    def test_enforce_boundaries_clamp_high(self, guardrails):
        """Test boundary enforcement with high value."""
        threshold, enforced, reason = guardrails.enforce_boundaries(0.98)

        assert threshold == 0.95
        assert enforced is True
        assert "maximum" in reason

    def test_record_threshold_change(self, guardrails):
        """Test recording threshold change."""
        entry = guardrails.record_threshold_change(
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            old_threshold=0.60,
            new_threshold=0.65,
            reason="ECE high",
        )

        assert entry.event_type == AuditEventType.THRESHOLD_CHANGE
        assert entry.strategy_id == "grid_btc_1h"
        assert entry.old_value == 0.60
        assert entry.new_value == 0.65

    def test_detect_oscillation_no_changes(self, guardrails):
        """Test oscillation detection with no direction changes."""
        oscillation, count = guardrails.detect_oscillation(
            "grid_btc_1h", SignalType.ENTRY
        )

        assert oscillation is False
        assert count == 0

    def test_detect_oscillation_with_changes(self, guardrails):
        """Test oscillation detection with direction changes."""
        datetime.now(UTC)

        # Create adjustments with 3 direction changes
        adjustments = [
            (0.60, 0.65),  # Increase
            (0.65, 0.60),  # Decrease (change 1)
            (0.60, 0.55),  # Decrease
            (0.55, 0.60),  # Increase (change 2)
            (0.60, 0.55),  # Decrease (change 3)
        ]

        for i, (old, new) in enumerate(adjustments):
            guardrails._adjustment_history.append(
                guardrails.record_threshold_change(
                    strategy_id="grid_btc_1h",
                    signal_type=SignalType.ENTRY,
                    old_threshold=old,
                    new_threshold=new,
                    reason="Test",
                )
            )

        oscillation, count = guardrails.detect_oscillation(
            "grid_btc_1h", SignalType.ENTRY
        )

        assert oscillation is True
        assert count >= 3

    def test_apply_oscillation_freeze(self, guardrails):
        """Test applying oscillation freeze."""
        now = datetime.now(UTC)

        # Create adjustments with 3 direction changes
        adjustments = [
            (0.60, 0.65),  # Increase
            (0.65, 0.60),  # Decrease (change 1)
            (0.60, 0.55),  # Decrease
            (0.55, 0.60),  # Increase (change 2)
            (0.60, 0.55),  # Decrease (change 3)
        ]

        for old, new in adjustments:
            guardrails._adjustment_history.append(
                guardrails.record_threshold_change(
                    strategy_id="grid_btc_1h",
                    signal_type=SignalType.ENTRY,
                    old_threshold=old,
                    new_threshold=new,
                    reason="Test",
                )
            )

        freeze_until = guardrails.apply_oscillation_freeze(
            "grid_btc_1h", SignalType.ENTRY
        )

        assert freeze_until is not None
        assert freeze_until > now
        assert (
            guardrails._frozen_until[("grid_btc_1h", SignalType.ENTRY)] == freeze_until
        )

    def test_apply_oscillation_freeze_no_oscillation(self, guardrails):
        """Test applying oscillation freeze when no oscillation."""
        freeze_until = guardrails.apply_oscillation_freeze(
            "grid_btc_1h", SignalType.ENTRY
        )

        assert freeze_until is None

    def test_clear_oscillation_freeze(self, guardrails):
        """Test clearing oscillation freeze."""
        future = datetime.now(UTC) + timedelta(hours=48)
        guardrails._frozen_until[("grid_btc_1h", SignalType.ENTRY)] = future

        result = guardrails.clear_oscillation_freeze(
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            user_id="user123",
        )

        assert result is True
        assert ("grid_btc_1h", SignalType.ENTRY) not in guardrails._frozen_until

    def test_clear_oscillation_freeze_none(self, guardrails):
        """Test clearing freeze when none exists."""
        result = guardrails.clear_oscillation_freeze(
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            user_id="user123",
        )

        assert result is False

    def test_get_audit_log(self, guardrails):
        """Test getting audit log."""
        guardrails.record_threshold_change(
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            old_threshold=0.60,
            new_threshold=0.65,
            reason="Test",
        )

        entries = guardrails.get_audit_log(days=1)

        assert len(entries) == 1
        assert entries[0].strategy_id == "grid_btc_1h"

    def test_get_audit_log_filtered(self, guardrails):
        """Test getting filtered audit log."""
        guardrails.record_threshold_change(
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            old_threshold=0.60,
            new_threshold=0.65,
            reason="Test",
        )
        guardrails.record_threshold_change(
            strategy_id="grid_eth_1h",
            signal_type=SignalType.EXIT,
            old_threshold=0.60,
            new_threshold=0.65,
            reason="Test",
        )

        entries = guardrails.get_audit_log(strategy_id="grid_btc_1h")

        assert len(entries) == 1
        assert entries[0].strategy_id == "grid_btc_1h"

    def test_get_active_overrides(self, guardrails):
        """Test getting active overrides."""
        guardrails.enable_manual_override(
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            reason="Test",
            user_id="user123",
        )
        guardrails.enable_manual_override(
            strategy_id="grid_eth_1h",
            signal_type=SignalType.EXIT,
            reason="Test",
            user_id="user123",
        )

        overrides = guardrails.get_active_overrides()

        assert len(overrides) == 2

    def test_get_frozen_strategies(self, guardrails):
        """Test getting frozen strategies."""
        future = datetime.now(UTC) + timedelta(hours=48)
        guardrails._frozen_until[("grid_btc_1h", SignalType.ENTRY)] = future
        guardrails._frozen_until[("grid_eth_1h", SignalType.EXIT)] = future

        frozen = guardrails.get_frozen_strategies()

        assert len(frozen) == 2

    def test_validate_threshold_change_allowed(self, guardrails):
        """Test validation when change is allowed."""
        is_valid, reason, final_threshold = guardrails.validate_threshold_change(
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            proposed_threshold=0.70,
        )

        assert is_valid is True
        assert final_threshold == 0.70

    def test_validate_threshold_change_blocked_override(self, guardrails):
        """Test validation when blocked by override."""
        guardrails.enable_manual_override(
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            reason="Test",
            user_id="user123",
        )

        is_valid, reason, final_threshold = guardrails.validate_threshold_change(
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            proposed_threshold=0.70,
        )

        assert is_valid is False
        assert "Manual override" in reason

    def test_validate_threshold_change_clamped(self, guardrails):
        """Test validation with boundary enforcement."""
        is_valid, reason, final_threshold = guardrails.validate_threshold_change(
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            proposed_threshold=0.30,  # Below minimum
        )

        assert is_valid is True
        assert final_threshold == 0.40
        assert "minimum" in reason

    def test_get_summary(self, guardrails):
        """Test getting summary."""
        summary = guardrails.get_summary()

        assert "active_overrides" in summary
        assert "frozen_strategies" in summary
        assert "total_audit_entries" in summary
        assert "config" in summary

    def test_reset(self, guardrails):
        """Test reset functionality."""
        # Add some state
        guardrails.enable_manual_override(
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            reason="Test",
            user_id="user123",
        )
        guardrails._frozen_until[("grid_btc_1h", SignalType.ENTRY)] = datetime.now(UTC)
        guardrails.record_threshold_change(
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            old_threshold=0.60,
            new_threshold=0.65,
            reason="Test",
        )

        # Reset
        guardrails.reset()

        assert len(guardrails._overrides) == 0
        assert len(guardrails._frozen_until) == 0
        assert len(guardrails._audit_log) == 0


class TestManualOverride:
    """Tests for ManualOverride class."""

    def test_is_active(self):
        """Test is_active property."""
        future = datetime.now(UTC) + timedelta(days=3)
        override = ManualOverride(
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            enabled_at=datetime.now(UTC),
            expires_at=future,
            reason="Test",
            override_reason=OverrideReason.MANUAL_ADJUSTMENT,
            user_id="user123",
        )

        assert override.is_active is True

    def test_is_active_expired(self):
        """Test is_active when expired."""
        past = datetime.now(UTC) - timedelta(days=1)
        override = ManualOverride(
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            enabled_at=past - timedelta(days=7),
            expires_at=past,
            reason="Test",
            override_reason=OverrideReason.MANUAL_ADJUSTMENT,
            user_id="user123",
        )

        assert override.is_active is False

    def test_time_remaining(self):
        """Test time_remaining method."""
        future = datetime.now(UTC) + timedelta(hours=24)
        override = ManualOverride(
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            enabled_at=datetime.now(UTC),
            expires_at=future,
            reason="Test",
            override_reason=OverrideReason.MANUAL_ADJUSTMENT,
            user_id="user123",
        )

        remaining = override.time_remaining()
        assert remaining.total_seconds() > 0
        assert remaining.total_seconds() <= 24 * 3600

    def test_time_remaining_expired(self):
        """Test time_remaining when expired."""
        past = datetime.now(UTC) - timedelta(days=1)
        override = ManualOverride(
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            enabled_at=past - timedelta(days=7),
            expires_at=past,
            reason="Test",
            override_reason=OverrideReason.MANUAL_ADJUSTMENT,
            user_id="user123",
        )

        remaining = override.time_remaining()
        assert remaining == timedelta(0)

    def test_to_dict(self):
        """Test to_dict method."""
        now = datetime.now(UTC)
        future = now + timedelta(days=7)
        override = ManualOverride(
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            enabled_at=now,
            expires_at=future,
            reason="Test",
            override_reason=OverrideReason.MANUAL_ADJUSTMENT,
            user_id="user123",
            threshold_value=0.70,
        )

        d = override.to_dict()
        assert d["strategy_id"] == "grid_btc_1h"
        assert d["signal_type"] == "entry"
        assert d["is_active"] is True
        assert d["threshold_value"] == 0.70


class TestGuardrailConfig:
    """Tests for GuardrailConfig."""

    def test_default_values(self):
        """Test default configuration values."""
        config = GuardrailConfig()

        assert config.min_threshold == 0.40
        assert config.max_threshold == 0.95
        assert config.manual_override_duration_days == 7
        assert config.oscillation_window_days == 7
        assert config.oscillation_freeze_hours == 48
        assert config.oscillation_direction_changes == 3

    def test_validation(self):
        """Test configuration validation."""
        with pytest.raises(ValueError):
            GuardrailConfig(min_threshold=-0.1)

        with pytest.raises(ValueError):
            GuardrailConfig(max_threshold=1.5)

        with pytest.raises(ValueError, match="min_threshold must be < max_threshold"):
            GuardrailConfig(min_threshold=0.60, max_threshold=0.50)


class TestIntegration:
    """Integration tests for DynamicThresholdEngine and ThresholdGuardrails."""

    @pytest.mark.asyncio
    async def test_full_workflow_with_guardrails(self):
        """Test full workflow with both engine and guardrails."""
        # Create components
        ece_provider = MockECEProvider()
        engine = DynamicThresholdEngine(ece_provider=ece_provider)
        guardrails = ThresholdGuardrails()

        # Set high ECE to trigger adjustment
        ece_provider.ece_values = {
            ("grid_btc_1h", SignalType.ENTRY): 0.15,
        }

        # First adjustment should work
        result = await engine.evaluate_and_adjust(
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            current_threshold=0.65,
        )

        assert result is not None

        # Record in guardrails
        guardrails.record_threshold_change(
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            old_threshold=result.old_threshold,
            new_threshold=result.new_threshold,
            reason=result.reason,
        )

        # Enable manual override
        guardrails.enable_manual_override(
            strategy_id="grid_btc_1h",
            signal_type=SignalType.ENTRY,
            reason="Market volatility",
            user_id="user123",
        )

        # Check auto-adjustment is blocked
        can_adjust, reason = guardrails.can_auto_adjust("grid_btc_1h", SignalType.ENTRY)
        assert can_adjust is False
        assert "Manual override" in reason

    @pytest.mark.asyncio
    async def test_oscillation_detection_integration(self):
        """Test oscillation detection with realistic sequence."""
        ece_provider = MockECEProvider()
        engine = DynamicThresholdEngine(ece_provider=ece_provider)
        guardrails = ThresholdGuardrails()

        now = datetime.now(UTC)
        strategy_id = "grid_btc_1h"
        signal_type = SignalType.ENTRY

        # Simulate 5 days of oscillating adjustments
        ece_sequence = [0.15, 0.03, 0.15, 0.03, 0.15]  # High, low, high, low, high
        threshold = 0.65

        for i, ece in enumerate(ece_sequence):
            # Set ECE
            ece_provider.ece_values = {(strategy_id, signal_type): ece}

            # Manually set adjustment time to be outside cooldown
            engine._last_adjustment[(strategy_id, signal_type)] = now - timedelta(
                hours=COOLDOWN_HOURS + 1 + i
            )

            # Try to adjust
            result = await engine.evaluate_and_adjust(
                strategy_id=strategy_id,
                signal_type=signal_type,
                current_threshold=threshold,
            )

            if result:
                # Record in guardrails
                guardrails.record_threshold_change(
                    strategy_id=strategy_id,
                    signal_type=signal_type,
                    old_threshold=result.old_threshold,
                    new_threshold=result.new_threshold,
                    reason=result.reason,
                )
                threshold = result.new_threshold

        # Should have oscillation detected
        oscillation, count = guardrails.detect_oscillation(strategy_id, signal_type)
        assert oscillation is True
        assert count >= 3

        # Apply freeze
        freeze_until = guardrails.apply_oscillation_freeze(strategy_id, signal_type)
        assert freeze_until is not None

        # Verify freeze is active
        can_adjust, reason = guardrails.can_auto_adjust(strategy_id, signal_type)
        assert can_adjust is False
        assert "Oscillation freeze" in reason


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
