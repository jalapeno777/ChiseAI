"""Tests for B1 Baseline Experiment."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.ict.experiments.b1_baseline import B1BaselineExperiment


class TestB1BaselineExperiment:
    """Tests for B1BaselineExperiment class."""

    @pytest.fixture
    def mock_collector(self):
        """Create a mock ICT data collector."""
        collector = MagicMock()
        collector.collect_signal = AsyncMock(return_value="sig-123")
        collector.record_outcome = AsyncMock()
        collector.stop_collection = AsyncMock()
        collector.start_collection = AsyncMock()
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
        """Create a B1 baseline experiment."""
        return B1BaselineExperiment(
            collector=mock_collector,
            registry=mock_registry,
        )

    def test_experiment_key_properties(self, experiment):
        """Test experiment key has correct properties."""
        assert experiment.experiment_key.experiment_id == "ICT-B1"
        assert experiment.experiment_key.variant == "baseline"

    def test_start_experiment(self, experiment, mock_registry):
        """Test starting the experiment."""
        result = experiment.start()
        assert result is True
        assert experiment.is_running() is True
        mock_registry.register_experiment.assert_called_once()

    def test_start_already_running(self, experiment):
        """Test starting already running experiment."""
        experiment.start()
        result = experiment.start()
        assert result is False

    @pytest.mark.asyncio
    async def test_stop_experiment(self, experiment, mock_collector):
        """Test stopping the experiment."""
        experiment.start()
        result = await experiment.stop()
        assert result is True
        assert experiment.is_running() is False
        mock_collector.stop_collection.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_not_running(self, experiment):
        """Test stopping non-running experiment."""
        result = await experiment.stop()
        assert result is False

    @pytest.mark.asyncio
    async def test_record_signal(self, experiment, mock_collector):
        """Test recording a signal."""
        experiment.start()
        signal_id = await experiment.record_signal(
            symbol="BTC/USDT",
            signal_type="entry",
            confidence=0.85,
        )
        assert signal_id == "sig-123"
        mock_collector.collect_signal.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_outcome(self, experiment, mock_collector):
        """Test recording an outcome."""
        await experiment.record_outcome(
            position_id="pos-123",
            signal_id="sig-456",
            outcome="profit",
            pnl=100.0,
        )
        mock_collector.record_outcome.assert_called_once()

    def test_is_running_initially_false(self, experiment):
        """Test experiment is not running initially."""
        assert experiment.is_running() is False
