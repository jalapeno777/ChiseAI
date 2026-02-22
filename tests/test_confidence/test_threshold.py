"""Tests for threshold calibration module.

Tests cover:
- ThresholdMode enum
- ThresholdConfig validation
- ThresholdAdjustment dataclass
- ThresholdCalibrator calibration logic
- ThresholdManager operations
- Mode switching
- Edge cases and boundary conditions
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from confidence.ece_tracker import ECEHistoryPoint
from confidence.threshold import (
    CalibrationResult,
    ModeSwitchRecord,
    ThresholdAdjustment,
    ThresholdCalibrator,
    ThresholdConfig,
    ThresholdManager,
    ThresholdMode,
)

if TYPE_CHECKING:
    pass


class TestThresholdMode:
    """Tests for ThresholdMode enum."""

    def test_dynamic_mode(self):
        """Test DYNAMIC mode value."""
        assert ThresholdMode.DYNAMIC.value == "dynamic"

    def test_fixed_mode(self):
        """Test FIXED mode value."""
        assert ThresholdMode.FIXED.value == "fixed"

    def test_mode_comparison(self):
        """Test mode comparison."""
        assert ThresholdMode.DYNAMIC != ThresholdMode.FIXED
        assert ThresholdMode.DYNAMIC == ThresholdMode.DYNAMIC


class TestThresholdConfig:
    """Tests for ThresholdConfig dataclass."""

    def test_basic_creation(self):
        """Test basic config creation."""
        config = ThresholdConfig(
            strategy_id="grid_btc_1h",
            mode=ThresholdMode.DYNAMIC,
            current_threshold=0.65,
        )

        assert config.strategy_id == "grid_btc_1h"
        assert config.mode == ThresholdMode.DYNAMIC
        assert config.current_threshold == 0.65
        assert config.min_threshold == 0.40
        assert config.max_threshold == 0.95

    def test_custom_bounds(self):
        """Test config with custom bounds."""
        config = ThresholdConfig(
            strategy_id="test_strategy",
            mode=ThresholdMode.FIXED,
            current_threshold=0.50,
            min_threshold=0.30,
            max_threshold=0.90,
        )

        assert config.min_threshold == 0.30
        assert config.max_threshold == 0.90
        assert config.current_threshold == 0.50

    def test_custom_adjustment_steps(self):
        """Test config with custom adjustment steps."""
        config = ThresholdConfig(
            strategy_id="test_strategy",
            mode=ThresholdMode.DYNAMIC,
            current_threshold=0.65,
            adjustment_step_up=0.10,
            adjustment_step_down=0.05,
        )

        assert config.adjustment_step_up == 0.10
        assert config.adjustment_step_down == 0.05

    def test_custom_ece_thresholds(self):
        """Test config with custom ECE thresholds."""
        config = ThresholdConfig(
            strategy_id="test_strategy",
            mode=ThresholdMode.DYNAMIC,
            current_threshold=0.65,
            ece_high_threshold=0.20,
            ece_low_threshold=0.03,
        )

        assert config.ece_high_threshold == 0.20
        assert config.ece_low_threshold == 0.03

    def test_threshold_out_of_range_high(self):
        """Test error when current_threshold > 1."""
        with pytest.raises(ValueError, match="current_threshold"):
            ThresholdConfig(
                strategy_id="test",
                mode=ThresholdMode.DYNAMIC,
                current_threshold=1.5,
            )

    def test_threshold_out_of_range_low(self):
        """Test error when current_threshold < 0."""
        with pytest.raises(ValueError, match="current_threshold"):
            ThresholdConfig(
                strategy_id="test",
                mode=ThresholdMode.DYNAMIC,
                current_threshold=-0.1,
            )

    def test_min_greater_than_max(self):
        """Test error when min >= max."""
        with pytest.raises(ValueError, match="min_threshold"):
            ThresholdConfig(
                strategy_id="test",
                mode=ThresholdMode.DYNAMIC,
                current_threshold=0.65,
                min_threshold=0.90,
                max_threshold=0.40,
            )

    def test_current_outside_bounds(self):
        """Test error when current outside min/max."""
        with pytest.raises(ValueError, match="current_threshold"):
            ThresholdConfig(
                strategy_id="test",
                mode=ThresholdMode.DYNAMIC,
                current_threshold=0.30,
                min_threshold=0.40,
                max_threshold=0.95,
            )

    def test_min_threshold_out_of_range(self):
        """Test error when min_threshold out of range."""
        with pytest.raises(ValueError, match="min_threshold"):
            ThresholdConfig(
                strategy_id="test",
                mode=ThresholdMode.DYNAMIC,
                current_threshold=0.65,
                min_threshold=-0.1,
            )

    def test_max_threshold_out_of_range(self):
        """Test error when max_threshold out of range."""
        with pytest.raises(ValueError, match="max_threshold"):
            ThresholdConfig(
                strategy_id="test",
                mode=ThresholdMode.DYNAMIC,
                current_threshold=0.65,
                max_threshold=1.5,
            )

    def test_threshold_at_bounds(self):
        """Test threshold at exact bounds."""
        config = ThresholdConfig(
            strategy_id="test",
            mode=ThresholdMode.DYNAMIC,
            current_threshold=0.40,
            min_threshold=0.40,
            max_threshold=0.95,
        )
        assert config.current_threshold == 0.40

        config2 = ThresholdConfig(
            strategy_id="test",
            mode=ThresholdMode.DYNAMIC,
            current_threshold=0.95,
            min_threshold=0.40,
            max_threshold=0.95,
        )
        assert config2.current_threshold == 0.95


class TestThresholdAdjustment:
    """Tests for ThresholdAdjustment dataclass."""

    def test_basic_creation(self):
        """Test basic adjustment creation."""
        adjustment = ThresholdAdjustment(
            timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
            strategy_id="grid_btc_1h",
            old_value=0.60,
            new_value=0.65,
            reason="ECE too high",
        )

        assert adjustment.strategy_id == "grid_btc_1h"
        assert adjustment.old_value == 0.60
        assert adjustment.new_value == 0.65
        assert adjustment.reason == "ECE too high"
        assert adjustment.adjustment_type == "auto"

    def test_change_amount(self):
        """Test change_amount property."""
        adjustment = ThresholdAdjustment(
            timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
            strategy_id="test",
            old_value=0.60,
            new_value=0.65,
            reason="test",
        )

        assert adjustment.change_amount == pytest.approx(0.05)

    def test_change_amount_negative(self):
        """Test change_amount for decrease."""
        adjustment = ThresholdAdjustment(
            timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
            strategy_id="test",
            old_value=0.70,
            new_value=0.65,
            reason="test",
        )

        assert adjustment.change_amount == pytest.approx(-0.05)

    def test_change_percent(self):
        """Test change_percent property."""
        adjustment = ThresholdAdjustment(
            timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
            strategy_id="test",
            old_value=0.50,
            new_value=0.55,
            reason="test",
        )

        assert adjustment.change_percent == pytest.approx(10.0)

    def test_change_percent_zero_old(self):
        """Test change_percent when old_value is 0."""
        adjustment = ThresholdAdjustment(
            timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
            strategy_id="test",
            old_value=0.0,
            new_value=0.05,
            reason="test",
        )

        assert adjustment.change_percent == 0.0

    def test_with_ece_values(self):
        """Test adjustment with ECE values."""
        adjustment = ThresholdAdjustment(
            timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
            strategy_id="test",
            old_value=0.60,
            new_value=0.65,
            reason="High ECE",
            ece_before=0.18,
            ece_after=0.12,
            adjustment_type="auto",
            triggered_by="ece_high",
        )

        assert adjustment.ece_before == 0.18
        assert adjustment.ece_after == 0.12
        assert adjustment.triggered_by == "ece_high"


class TestCalibrationResult:
    """Tests for CalibrationResult dataclass."""

    def test_basic_creation(self):
        """Test basic result creation."""
        result = CalibrationResult(
            strategy_id="grid_btc_1h",
            ece_before=0.18,
            ece_after=0.12,
            threshold_before=0.60,
            threshold_after=0.65,
            adjustment_made=True,
            adjustment_reason="ECE too high",
            recommended_action="increase",
            confidence_improvement=0.03,
        )

        assert result.strategy_id == "grid_btc_1h"
        assert result.adjustment_made is True
        assert result.recommended_action == "increase"

    def test_ece_improvement(self):
        """Test ece_improvement property."""
        result = CalibrationResult(
            strategy_id="test",
            ece_before=0.18,
            ece_after=0.12,
            threshold_before=0.60,
            threshold_after=0.65,
            adjustment_made=True,
            adjustment_reason="test",
            recommended_action="increase",
            confidence_improvement=0.03,
        )

        assert result.ece_improvement == 0.06

    def test_ece_improvement_none(self):
        """Test ece_improvement when ece_after is None."""
        result = CalibrationResult(
            strategy_id="test",
            ece_before=0.18,
            ece_after=None,
            threshold_before=0.60,
            threshold_after=0.65,
            adjustment_made=True,
            adjustment_reason="test",
            recommended_action="increase",
            confidence_improvement=0.03,
        )

        assert result.ece_improvement is None

    def test_is_better_calibrated(self):
        """Test is_better_calibrated property."""
        result = CalibrationResult(
            strategy_id="test",
            ece_before=0.18,
            ece_after=0.12,
            threshold_before=0.60,
            threshold_after=0.65,
            adjustment_made=True,
            adjustment_reason="test",
            recommended_action="increase",
            confidence_improvement=0.03,
        )

        assert result.is_better_calibrated is True

    def test_is_better_calibrated_worse(self):
        """Test is_better_calibrated when ECE increased."""
        result = CalibrationResult(
            strategy_id="test",
            ece_before=0.10,
            ece_after=0.15,
            threshold_before=0.60,
            threshold_after=0.65,
            adjustment_made=True,
            adjustment_reason="test",
            recommended_action="increase",
            confidence_improvement=0.03,
        )

        assert result.is_better_calibrated is False


class TestModeSwitchRecord:
    """Tests for ModeSwitchRecord dataclass."""

    def test_basic_creation(self):
        """Test basic mode switch record creation."""
        record = ModeSwitchRecord(
            timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
            strategy_id="grid_btc_1h",
            old_mode=ThresholdMode.DYNAMIC,
            new_mode=ThresholdMode.FIXED,
            reason="Testing manual override",
            old_threshold=0.65,
            new_threshold=0.70,
        )

        assert record.strategy_id == "grid_btc_1h"
        assert record.old_mode == ThresholdMode.DYNAMIC
        assert record.new_mode == ThresholdMode.FIXED
        assert record.old_threshold == 0.65
        assert record.new_threshold == 0.70


class TestThresholdCalibrator:
    """Tests for ThresholdCalibrator class."""

    def test_initialization_defaults(self):
        """Test calibrator with default parameters."""
        calibrator = ThresholdCalibrator()

        assert calibrator.default_min_threshold == 0.40
        assert calibrator.default_max_threshold == 0.95
        assert calibrator.default_step_up == 0.05
        assert calibrator.default_step_down == 0.03
        assert calibrator.default_ece_high == 0.15
        assert calibrator.default_ece_low == 0.05

    def test_initialization_custom(self):
        """Test calibrator with custom parameters."""
        calibrator = ThresholdCalibrator(
            default_min_threshold=0.30,
            default_max_threshold=0.90,
            default_step_up=0.10,
            default_step_down=0.05,
            default_ece_high=0.20,
            default_ece_low=0.03,
        )

        assert calibrator.default_min_threshold == 0.30
        assert calibrator.default_max_threshold == 0.90
        assert calibrator.default_step_up == 0.10
        assert calibrator.default_step_down == 0.05
        assert calibrator.default_ece_high == 0.20
        assert calibrator.default_ece_low == 0.03

    def test_calculate_adjustment_high_ece(self):
        """Test adjustment calculation for high ECE."""
        calibrator = ThresholdCalibrator()

        new_threshold, reason, action = calibrator.calculate_adjustment(
            current_threshold=0.60,
            ece=0.18,
        )

        assert new_threshold == 0.65
        assert action == "increase"
        assert "ECE" in reason
        assert "high" in reason.lower()

    def test_calculate_adjustment_low_ece_poor_win_rate(self):
        """Test adjustment calculation for low ECE with poor win rate."""
        calibrator = ThresholdCalibrator()

        new_threshold, reason, action = calibrator.calculate_adjustment(
            current_threshold=0.70,
            ece=0.03,
            win_rate=0.45,
        )

        assert new_threshold == pytest.approx(0.67)
        assert action == "decrease"
        assert "win rate" in reason.lower()

    def test_calculate_adjustment_low_ece_good_win_rate(self):
        """Test no adjustment for low ECE with good win rate."""
        calibrator = ThresholdCalibrator()

        new_threshold, reason, action = calibrator.calculate_adjustment(
            current_threshold=0.70,
            ece=0.03,
            win_rate=0.55,
        )

        assert new_threshold == 0.70
        assert action == "maintain"

    def test_calculate_adjustment_no_win_rate(self):
        """Test no adjustment for low ECE without win rate."""
        calibrator = ThresholdCalibrator()

        new_threshold, reason, action = calibrator.calculate_adjustment(
            current_threshold=0.70,
            ece=0.03,
            win_rate=None,
        )

        assert new_threshold == 0.70
        assert action == "maintain"

    def test_calculate_adjustment_normal_ece(self):
        """Test no adjustment for normal ECE."""
        calibrator = ThresholdCalibrator()

        new_threshold, reason, action = calibrator.calculate_adjustment(
            current_threshold=0.65,
            ece=0.10,
        )

        assert new_threshold == 0.65
        assert action == "maintain"
        assert "No adjustment" in reason

    def test_calculate_adjustment_at_max_bound(self):
        """Test adjustment respects max bound."""
        calibrator = ThresholdCalibrator()

        new_threshold, reason, action = calibrator.calculate_adjustment(
            current_threshold=0.93,
            ece=0.18,
        )

        assert new_threshold == 0.95  # Clamped to max

    def test_calculate_adjustment_at_min_bound(self):
        """Test adjustment respects min bound."""
        calibrator = ThresholdCalibrator()

        new_threshold, reason, action = calibrator.calculate_adjustment(
            current_threshold=0.42,
            ece=0.03,
            win_rate=0.45,
        )

        assert new_threshold == 0.40  # Clamped to min

    @pytest.mark.asyncio
    async def test_calibrate_with_history(self):
        """Test calibration with ECE history."""
        calibrator = ThresholdCalibrator()

        ece_history = [
            ECEHistoryPoint(
                timestamp=datetime(2024, 1, 1, tzinfo=UTC),
                ece=0.10,
                n_bins=10,
                total_samples=100,
            ),
            ECEHistoryPoint(
                timestamp=datetime(2024, 1, 2, tzinfo=UTC),
                ece=0.18,
                n_bins=10,
                total_samples=100,
            ),
        ]

        config = ThresholdConfig(
            strategy_id="test",
            mode=ThresholdMode.DYNAMIC,
            current_threshold=0.60,
        )

        result = await calibrator.calibrate("test", ece_history, config=config)

        assert result.strategy_id == "test"
        assert result.ece_before == 0.18
        assert result.threshold_after == 0.65
        assert result.adjustment_made is True
        assert result.recommended_action == "increase"

    @pytest.mark.asyncio
    async def test_calibrate_empty_history(self):
        """Test calibration with empty history."""
        calibrator = ThresholdCalibrator()

        config = ThresholdConfig(
            strategy_id="test",
            mode=ThresholdMode.DYNAMIC,
            current_threshold=0.60,
        )

        result = await calibrator.calibrate("test", [], config=config)

        assert result.strategy_id == "test"
        assert result.adjustment_made is False
        assert "No ECE history" in result.adjustment_reason

    @pytest.mark.asyncio
    async def test_calibrate_with_win_rate(self):
        """Test calibration with win rate."""
        calibrator = ThresholdCalibrator()

        ece_history = [
            ECEHistoryPoint(
                timestamp=datetime(2024, 1, 1, tzinfo=UTC),
                ece=0.03,
                n_bins=10,
                total_samples=100,
            ),
        ]

        config = ThresholdConfig(
            strategy_id="test",
            mode=ThresholdMode.DYNAMIC,
            current_threshold=0.70,
        )

        result = await calibrator.calibrate(
            "test", ece_history, win_rate=0.45, config=config
        )

        assert result.adjustment_made is True
        assert result.threshold_after == pytest.approx(0.67)
        assert result.recommended_action == "decrease"

    def test_set_fixed_threshold(self):
        """Test setting fixed threshold."""
        calibrator = ThresholdCalibrator()

        config, adjustment = calibrator.set_fixed_threshold(
            strategy_id="test",
            value=0.75,
            reason="Manual override for testing",
        )

        assert config.mode == ThresholdMode.FIXED
        assert config.current_threshold == 0.75
        assert adjustment.old_value == 0.65  # Default
        assert adjustment.new_value == 0.75
        assert adjustment.adjustment_type == "manual"

    def test_set_fixed_threshold_with_config(self):
        """Test setting fixed threshold with existing config."""
        calibrator = ThresholdCalibrator()

        existing_config = ThresholdConfig(
            strategy_id="test",
            mode=ThresholdMode.DYNAMIC,
            current_threshold=0.60,
        )

        config, adjustment = calibrator.set_fixed_threshold(
            strategy_id="test",
            value=0.75,
            reason="Manual override",
            config=existing_config,
        )

        assert adjustment.old_value == 0.60
        assert config.min_threshold == 0.40  # Preserved from existing

    def test_set_fixed_threshold_clamping(self):
        """Test fixed threshold is clamped to bounds."""
        calibrator = ThresholdCalibrator()

        config, adjustment = calibrator.set_fixed_threshold(
            strategy_id="test",
            value=0.99,  # Above max
            reason="Test",
        )

        assert config.current_threshold == 0.95  # Clamped
        assert adjustment.new_value == 0.95

    def test_switch_mode_dynamic_to_fixed(self):
        """Test switching from dynamic to fixed mode."""
        calibrator = ThresholdCalibrator()

        existing_config = ThresholdConfig(
            strategy_id="test",
            mode=ThresholdMode.DYNAMIC,
            current_threshold=0.65,
        )

        config, mode_switch = calibrator.switch_mode(
            strategy_id="test",
            new_mode=ThresholdMode.FIXED,
            reason="Testing manual mode",
            current_config=existing_config,
        )

        assert config.mode == ThresholdMode.FIXED
        assert mode_switch.old_mode == ThresholdMode.DYNAMIC
        assert mode_switch.new_mode == ThresholdMode.FIXED
        assert mode_switch.old_threshold == 0.65

    def test_switch_mode_fixed_to_dynamic(self):
        """Test switching from fixed to dynamic mode."""
        calibrator = ThresholdCalibrator()

        existing_config = ThresholdConfig(
            strategy_id="test",
            mode=ThresholdMode.FIXED,
            current_threshold=0.70,
        )

        config, mode_switch = calibrator.switch_mode(
            strategy_id="test",
            new_mode=ThresholdMode.DYNAMIC,
            reason="Enable auto-calibration",
            current_config=existing_config,
        )

        assert config.mode == ThresholdMode.DYNAMIC
        assert mode_switch.old_mode == ThresholdMode.FIXED
        assert mode_switch.new_mode == ThresholdMode.DYNAMIC

    def test_switch_mode_with_new_threshold(self):
        """Test mode switch with new threshold value."""
        calibrator = ThresholdCalibrator()

        existing_config = ThresholdConfig(
            strategy_id="test",
            mode=ThresholdMode.DYNAMIC,
            current_threshold=0.65,
        )

        config, mode_switch = calibrator.switch_mode(
            strategy_id="test",
            new_mode=ThresholdMode.FIXED,
            reason="Manual mode with new threshold",
            current_config=existing_config,
            new_threshold=0.80,
        )

        assert config.current_threshold == 0.80
        assert mode_switch.new_threshold == 0.80

    def test_switch_mode_no_config(self):
        """Test mode switch without existing config."""
        calibrator = ThresholdCalibrator()

        config, mode_switch = calibrator.switch_mode(
            strategy_id="test",
            new_mode=ThresholdMode.DYNAMIC,
            reason="Initial setup",
        )

        assert config.mode == ThresholdMode.DYNAMIC
        assert config.current_threshold == 0.65  # Default


class TestThresholdManager:
    """Tests for ThresholdManager class."""

    def test_initialization(self):
        """Test manager initialization."""
        manager = ThresholdManager()

        assert manager.get_all_strategies() == []
        assert manager._calibrator is not None

    def test_initialization_with_calibrator(self):
        """Test manager with custom calibrator."""
        calibrator = ThresholdCalibrator(default_step_up=0.10)
        manager = ThresholdManager(calibrator=calibrator)

        assert manager._calibrator.default_step_up == 0.10

    def test_register_strategy(self):
        """Test strategy registration."""
        manager = ThresholdManager()

        config = manager.register_strategy(
            strategy_id="grid_btc_1h",
            mode=ThresholdMode.DYNAMIC,
            initial_threshold=0.65,
        )

        assert config.strategy_id == "grid_btc_1h"
        assert config.mode == ThresholdMode.DYNAMIC
        assert manager.is_registered("grid_btc_1h") is True
        assert manager.get_threshold("grid_btc_1h") == 0.65

    def test_register_strategy_with_bounds(self):
        """Test strategy registration with custom bounds."""
        manager = ThresholdManager()

        config = manager.register_strategy(
            strategy_id="test",
            mode=ThresholdMode.DYNAMIC,
            initial_threshold=0.50,
            min_threshold=0.30,
            max_threshold=0.90,
        )

        assert config.min_threshold == 0.30
        assert config.max_threshold == 0.90

    def test_get_threshold_not_registered(self):
        """Test getting threshold for unregistered strategy."""
        manager = ThresholdManager()

        with pytest.raises(KeyError, match="not registered"):
            manager.get_threshold("unknown")

    def test_get_config(self):
        """Test getting full config."""
        manager = ThresholdManager()
        manager.register_strategy("test", ThresholdMode.DYNAMIC, 0.65)

        config = manager.get_config("test")

        assert config.strategy_id == "test"
        assert config.mode == ThresholdMode.DYNAMIC
        assert config.current_threshold == 0.65

    def test_update_threshold(self):
        """Test threshold update."""
        manager = ThresholdManager()
        manager.register_strategy("test", ThresholdMode.DYNAMIC, 0.60)

        adjustment = manager.update_threshold(
            strategy_id="test",
            new_threshold=0.70,
            reason="Manual adjustment",
        )

        assert adjustment.old_value == 0.60
        assert adjustment.new_value == 0.70
        assert manager.get_threshold("test") == 0.70

    def test_update_threshold_clamping(self):
        """Test threshold update respects bounds."""
        manager = ThresholdManager()
        manager.register_strategy("test", ThresholdMode.DYNAMIC, 0.60)

        adjustment = manager.update_threshold(
            strategy_id="test",
            new_threshold=0.99,  # Above max
            reason="Test",
        )

        assert adjustment.new_value == 0.95  # Clamped
        assert manager.get_threshold("test") == 0.95

    def test_update_threshold_not_registered(self):
        """Test updating unregistered strategy."""
        manager = ThresholdManager()

        with pytest.raises(KeyError, match="not registered"):
            manager.update_threshold("unknown", 0.70, "test")

    def test_get_adjustment_history(self):
        """Test getting adjustment history."""
        manager = ThresholdManager()
        manager.register_strategy("test", ThresholdMode.DYNAMIC, 0.60)

        manager.update_threshold("test", 0.65, "First")
        manager.update_threshold("test", 0.70, "Second")

        history = manager.get_adjustment_history("test")

        assert len(history) == 2
        assert history[0].new_value == 0.65
        assert history[1].new_value == 0.70

    def test_get_adjustment_history_empty(self):
        """Test getting empty adjustment history."""
        manager = ThresholdManager()
        manager.register_strategy("test", ThresholdMode.DYNAMIC, 0.60)

        history = manager.get_adjustment_history("test")

        assert history == []

    def test_switch_mode(self):
        """Test mode switching."""
        manager = ThresholdManager()
        manager.register_strategy("test", ThresholdMode.DYNAMIC, 0.65)

        config, mode_switch = manager.switch_mode(
            strategy_id="test",
            new_mode=ThresholdMode.FIXED,
            reason="Testing",
        )

        assert config.mode == ThresholdMode.FIXED
        assert mode_switch.old_mode == ThresholdMode.DYNAMIC
        assert mode_switch.new_mode == ThresholdMode.FIXED

    def test_get_mode_switch_history(self):
        """Test getting mode switch history."""
        manager = ThresholdManager()
        manager.register_strategy("test", ThresholdMode.DYNAMIC, 0.65)

        manager.switch_mode("test", ThresholdMode.FIXED, "First")
        manager.switch_mode("test", ThresholdMode.DYNAMIC, "Second")

        history = manager.get_mode_switch_history("test")

        assert len(history) == 2
        assert history[0].new_mode == ThresholdMode.FIXED
        assert history[1].new_mode == ThresholdMode.DYNAMIC

    def test_get_all_strategies(self):
        """Test getting all registered strategies."""
        manager = ThresholdManager()

        manager.register_strategy("strategy_a", ThresholdMode.DYNAMIC, 0.65)
        manager.register_strategy("strategy_b", ThresholdMode.FIXED, 0.70)

        strategies = manager.get_all_strategies()

        assert len(strategies) == 2
        assert "strategy_a" in strategies
        assert "strategy_b" in strategies

    def test_is_registered(self):
        """Test is_registered check."""
        manager = ThresholdManager()

        assert manager.is_registered("test") is False

        manager.register_strategy("test", ThresholdMode.DYNAMIC, 0.65)

        assert manager.is_registered("test") is True

    @pytest.mark.asyncio
    async def test_run_calibration_dynamic(self):
        """Test running calibration in dynamic mode."""
        manager = ThresholdManager()
        manager.register_strategy("test", ThresholdMode.DYNAMIC, 0.60)

        ece_history = [
            ECEHistoryPoint(
                timestamp=datetime(2024, 1, 1, tzinfo=UTC),
                ece=0.18,
                n_bins=10,
                total_samples=100,
            ),
        ]

        result = await manager.run_calibration("test", ece_history)

        assert result.adjustment_made is True
        assert result.threshold_after == 0.65
        assert manager.get_threshold("test") == 0.65

    @pytest.mark.asyncio
    async def test_run_calibration_fixed(self):
        """Test running calibration in fixed mode."""
        manager = ThresholdManager()
        manager.register_strategy("test", ThresholdMode.FIXED, 0.60)

        ece_history = [
            ECEHistoryPoint(
                timestamp=datetime(2024, 1, 1, tzinfo=UTC),
                ece=0.18,
                n_bins=10,
                total_samples=100,
            ),
        ]

        result = await manager.run_calibration("test", ece_history)

        assert result.adjustment_made is False
        assert "FIXED mode" in result.adjustment_reason
        assert manager.get_threshold("test") == 0.60  # Unchanged

    @pytest.mark.asyncio
    async def test_run_calibration_no_adjustment(self):
        """Test running calibration when no adjustment needed."""
        manager = ThresholdManager()
        manager.register_strategy("test", ThresholdMode.DYNAMIC, 0.65)

        ece_history = [
            ECEHistoryPoint(
                timestamp=datetime(2024, 1, 1, tzinfo=UTC),
                ece=0.08,  # Normal ECE
                n_bins=10,
                total_samples=100,
            ),
        ]

        result = await manager.run_calibration("test", ece_history)

        assert result.adjustment_made is False
        assert manager.get_threshold("test") == 0.65  # Unchanged

    def test_unregister_strategy(self):
        """Test strategy unregistration."""
        manager = ThresholdManager()
        manager.register_strategy("test", ThresholdMode.DYNAMIC, 0.65)

        result = manager.unregister_strategy("test")

        assert result is True
        assert manager.is_registered("test") is False

    def test_unregister_strategy_not_found(self):
        """Test unregistering non-existent strategy."""
        manager = ThresholdManager()

        result = manager.unregister_strategy("unknown")

        assert result is False


class TestThresholdCalibrationEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_threshold_at_exact_bounds(self):
        """Test thresholds at exact min/max bounds."""
        config = ThresholdConfig(
            strategy_id="test",
            mode=ThresholdMode.DYNAMIC,
            current_threshold=0.40,
            min_threshold=0.40,
            max_threshold=0.95,
        )
        assert config.current_threshold == 0.40

        config2 = ThresholdConfig(
            strategy_id="test",
            mode=ThresholdMode.DYNAMIC,
            current_threshold=0.95,
            min_threshold=0.40,
            max_threshold=0.95,
        )
        assert config2.current_threshold == 0.95

    def test_adjustment_at_max_boundary(self):
        """Test adjustment when at max boundary."""
        calibrator = ThresholdCalibrator()

        new_threshold, reason, action = calibrator.calculate_adjustment(
            current_threshold=0.95,
            ece=0.20,
        )

        assert new_threshold == 0.95  # Cannot go higher

    def test_adjustment_at_min_boundary(self):
        """Test adjustment when at min boundary."""
        calibrator = ThresholdCalibrator()

        new_threshold, reason, action = calibrator.calculate_adjustment(
            current_threshold=0.40,
            ece=0.03,
            win_rate=0.45,
        )

        assert new_threshold == 0.40  # Cannot go lower

    def test_ece_exactly_at_thresholds(self):
        """Test ECE exactly at high/low thresholds."""
        calibrator = ThresholdCalibrator()

        # Exactly at high threshold - should NOT trigger
        new_threshold, reason, action = calibrator.calculate_adjustment(
            current_threshold=0.60,
            ece=0.15,  # Exactly at threshold
        )
        assert action == "maintain"

        # Exactly at low threshold - should NOT trigger (needs win_rate < 50%)
        new_threshold, reason, action = calibrator.calculate_adjustment(
            current_threshold=0.60,
            ece=0.05,  # Exactly at threshold
            win_rate=0.45,
        )
        assert action == "maintain"

    def test_very_high_ece(self):
        """Test with very high ECE."""
        calibrator = ThresholdCalibrator()

        new_threshold, reason, action = calibrator.calculate_adjustment(
            current_threshold=0.60,
            ece=0.50,  # Very high ECE
        )

        assert action == "increase"
        assert new_threshold == 0.65

    def test_very_low_ece(self):
        """Test with very low ECE."""
        calibrator = ThresholdCalibrator()

        new_threshold, reason, action = calibrator.calculate_adjustment(
            current_threshold=0.70,
            ece=0.01,  # Very low ECE
            win_rate=0.45,
        )

        assert action == "decrease"

    def test_win_rate_at_boundary(self):
        """Test win rate exactly at 50% boundary."""
        calibrator = ThresholdCalibrator()

        # Exactly 50% - should NOT trigger decrease
        new_threshold, reason, action = calibrator.calculate_adjustment(
            current_threshold=0.70,
            ece=0.03,
            win_rate=0.50,
        )
        assert action == "maintain"

        # Just below 50% - should trigger
        new_threshold, reason, action = calibrator.calculate_adjustment(
            current_threshold=0.70,
            ece=0.03,
            win_rate=0.49,
        )
        assert action == "decrease"

    def test_multiple_strategies_isolation(self):
        """Test that strategies are isolated from each other."""
        manager = ThresholdManager()

        manager.register_strategy("strategy_a", ThresholdMode.DYNAMIC, 0.60)
        manager.register_strategy("strategy_b", ThresholdMode.DYNAMIC, 0.70)

        manager.update_threshold("strategy_a", 0.65, "Test")

        assert manager.get_threshold("strategy_a") == 0.65
        assert manager.get_threshold("strategy_b") == 0.70

        history_a = manager.get_adjustment_history("strategy_a")
        history_b = manager.get_adjustment_history("strategy_b")

        assert len(history_a) == 1
        assert len(history_b) == 0

    def test_timestamp_preservation(self):
        """Test that timestamps are preserved correctly."""
        manager = ThresholdManager()
        manager.register_strategy("test", ThresholdMode.DYNAMIC, 0.60)

        adjustment = manager.update_threshold("test", 0.65, "Test")

        # Timestamp should be recent
        assert adjustment.timestamp.tzinfo is not None
        assert adjustment.timestamp > datetime(2024, 1, 1, tzinfo=UTC)

    def test_negative_threshold_change(self):
        """Test handling of negative threshold changes."""
        manager = ThresholdManager()
        manager.register_strategy("test", ThresholdMode.DYNAMIC, 0.70)

        adjustment = manager.update_threshold("test", 0.60, "Decrease")

        assert adjustment.change_amount == pytest.approx(-0.10)
        assert adjustment.change_percent < 0

    def test_zero_threshold_change(self):
        """Test handling of zero threshold change."""
        manager = ThresholdManager()
        manager.register_strategy("test", ThresholdMode.DYNAMIC, 0.65)

        adjustment = manager.update_threshold("test", 0.65, "No change")

        assert adjustment.change_amount == 0.0
        assert adjustment.change_percent == 0.0


class TestThresholdCalibrationIntegration:
    """Integration tests for threshold calibration."""

    @pytest.mark.asyncio
    async def test_full_calibration_workflow(self):
        """Test complete calibration workflow."""
        manager = ThresholdManager()

        # Register strategy
        manager.register_strategy("grid_btc_1h", ThresholdMode.DYNAMIC, 0.60)

        # Simulate high ECE - should increase threshold
        ece_history = [
            ECEHistoryPoint(
                timestamp=datetime(2024, 1, 1, tzinfo=UTC),
                ece=0.20,
                n_bins=10,
                total_samples=100,
            ),
        ]

        result = await manager.run_calibration("grid_btc_1h", ece_history)

        assert result.adjustment_made is True
        assert result.threshold_after == pytest.approx(0.65)
        assert manager.get_threshold("grid_btc_1h") == pytest.approx(0.65)

    @pytest.mark.asyncio
    async def test_calibration_improves_ece(self):
        """Test that calibration improves ECE over time."""
        manager = ThresholdManager()
        manager.register_strategy("test", ThresholdMode.DYNAMIC, 0.60)

        # First calibration - high ECE
        ece_history_1 = [
            ECEHistoryPoint(
                timestamp=datetime(2024, 1, 1, tzinfo=UTC),
                ece=0.20,
                n_bins=10,
                total_samples=100,
            ),
        ]

        result1 = await manager.run_calibration("test", ece_history_1)
        assert result1.adjustment_made is True
        assert result1.threshold_after > result1.threshold_before

        # Second calibration - improved ECE
        ece_history_2 = [
            ECEHistoryPoint(
                timestamp=datetime(2024, 1, 2, tzinfo=UTC),
                ece=0.08,
                n_bins=10,
                total_samples=100,
            ),
        ]

        result2 = await manager.run_calibration("test", ece_history_2)
        assert result2.adjustment_made is False  # No adjustment needed

    @pytest.mark.asyncio
    async def test_mode_switch_prevents_calibration(self):
        """Test that fixed mode prevents automatic calibration."""
        manager = ThresholdManager()
        manager.register_strategy("test", ThresholdMode.DYNAMIC, 0.60)

        # Switch to fixed mode
        manager.switch_mode("test", ThresholdMode.FIXED, "Testing")

        # Try calibration - should not adjust
        ece_history = [
            ECEHistoryPoint(
                timestamp=datetime(2024, 1, 1, tzinfo=UTC),
                ece=0.20,
                n_bins=10,
                total_samples=100,
            ),
        ]

        result = await manager.run_calibration("test", ece_history)

        assert result.adjustment_made is False
        assert manager.get_threshold("test") == 0.60  # Unchanged

    def test_audit_trail_completeness(self):
        """Test that audit trail captures all changes."""
        manager = ThresholdManager()
        manager.register_strategy("test", ThresholdMode.DYNAMIC, 0.60)

        # Make various changes
        manager.update_threshold("test", 0.65, "First")
        manager.switch_mode("test", ThresholdMode.FIXED, "Second")
        manager.update_threshold("test", 0.70, "Third")
        manager.switch_mode("test", ThresholdMode.DYNAMIC, "Fourth")

        # Check audit trail
        adjustments = manager.get_adjustment_history("test")
        mode_switches = manager.get_mode_switch_history("test")

        assert len(adjustments) == 2  # Two threshold updates
        assert len(mode_switches) == 2  # Two mode switches

        # Verify all changes are recorded
        assert adjustments[0].new_value == 0.65
        assert adjustments[1].new_value == 0.70
        assert mode_switches[0].new_mode == ThresholdMode.FIXED
        assert mode_switches[1].new_mode == ThresholdMode.DYNAMIC
