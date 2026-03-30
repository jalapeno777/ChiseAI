"""Tests for B2 Enhanced Experiment."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from src.ict.experiments.b2_enhanced import B2EnhancedExperiment, RiskLimits


class TestB2EnhancedExperiment:
    """Tests for B2EnhancedExperiment class."""

    @pytest.fixture
    def mock_collector(self):
        """Create a mock ICT data collector."""
        collector = MagicMock()
        collector.collect_signal = AsyncMock(return_value="sig-123")
        collector.record_outcome = AsyncMock()
        collector.stop_collection = AsyncMock()
        return collector

    @pytest.fixture
    def mock_registry(self):
        """Create a mock experiment registry."""
        registry = MagicMock()
        registry.register_experiment = MagicMock(return_value=True)
        registry.close_experiment = MagicMock(return_value=True)
        return registry

    @pytest.fixture
    def experiment(self, mock_collector, mock_registry):
        """Create a B2 enhanced experiment."""
        return B2EnhancedExperiment(
            collector=mock_collector,
            registry=mock_registry,
        )

    def test_experiment_key_properties(self, experiment):
        """Test experiment key has correct properties."""
        assert experiment.experiment_key.experiment_id == "ICT-B2"
        assert experiment.experiment_key.variant == "enhanced"

    def test_start_experiment(self, experiment, mock_registry):
        """Test starting the experiment."""
        result = experiment.start()
        assert result is True
        assert experiment.is_running() is True

    def test_kill_switch_initially_inactive(self, experiment):
        """Test kill switch is inactive initially."""
        assert experiment.is_kill_switch_active() is False

    def test_check_position_size_within_limit(self, experiment):
        """Test position size within limit."""
        result = experiment.check_position_size(0.5)
        assert result == 0.5

    def test_check_position_size_exceeds_limit(self, experiment):
        """Test position size capped at limit."""
        result = experiment.check_position_size(5.0)
        assert result == experiment.risk_limits.max_position_size

    def test_check_loss_limit_within(self, experiment):
        """Test loss within limit."""
        result = experiment.check_loss_limit(0.01)
        assert result is True

    def test_check_loss_limit_exceeds(self, experiment):
        """Test loss exceeds limit."""
        result = experiment.check_loss_limit(0.05)
        assert result is False

    def test_update_total_loss_profit(self, experiment):
        """Test updating with profit doesn't trigger kill switch."""
        result = experiment.update_total_loss(100.0)
        assert result is True
        assert experiment.is_kill_switch_active() is False

    def test_update_total_loss_triggers_kill_switch(self, experiment):
        """Test accumulating losses triggers kill switch."""
        # Set very low threshold for testing
        experiment.risk_limits.kill_switch_threshold = 0.05

        experiment.update_total_loss(-0.03)
        result = experiment.update_total_loss(-0.03)
        assert result is False
        assert experiment.is_kill_switch_active() is True

    @pytest.mark.asyncio
    async def test_record_signal_kill_switch_active(self, experiment, mock_collector):
        """Test signal recording blocked when kill switch active."""
        experiment.start()
        experiment._kill_switch_active = True

        result = await experiment.record_signal(
            symbol="BTC/USDT",
            signal_type="entry",
            confidence=0.85,
        )
        assert result is None
        mock_collector.collect_signal.assert_not_called()

    @pytest.mark.asyncio
    async def test_record_outcome_updates_loss(self, experiment, mock_collector):
        """Test outcome recording updates loss tracking."""
        await experiment.record_outcome(
            position_id="pos-123",
            signal_id="sig-456",
            outcome="loss",
            pnl=-10.0,
        )
        mock_collector.record_outcome.assert_called_once()


class TestRiskLimits:
    """Tests for RiskLimits dataclass."""

    def test_default_values(self):
        """Test default risk limit values."""
        limits = RiskLimits()
        assert limits.max_position_size == 1.0
        assert limits.max_loss_per_trade == 0.02
        assert limits.kill_switch_threshold == 0.10

    def test_custom_values(self):
        """Test custom risk limit values."""
        limits = RiskLimits(
            max_position_size=2.0,
            max_loss_per_trade=0.05,
            kill_switch_threshold=0.20,
        )
        assert limits.max_position_size == 2.0
        assert limits.max_loss_per_trade == 0.05
        assert limits.kill_switch_threshold == 0.20
