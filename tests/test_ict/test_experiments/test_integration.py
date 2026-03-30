"""Integration tests for experiment framework."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from src.ict.data_collection.collector import ICTDataCollector
from src.ict.experiments.b1_baseline import B1BaselineExperiment
from src.ict.experiments.b2_enhanced import B2EnhancedExperiment
from src.ict.experiments.factory import ExperimentFactory
from src.ict.experiments.key_schema import ExperimentKey
from src.ict.experiments.registry import ExperimentRegistry


class TestExperimentFactory:
    """Tests for ExperimentFactory."""

    def test_create_b1_experiment(self):
        """Test creating B1 experiment via factory."""
        collector = MagicMock(spec=ICTDataCollector)
        exp = ExperimentFactory.create_experiment("ICT-B1", collector)
        assert isinstance(exp, B1BaselineExperiment)

    def test_create_b2_experiment(self):
        """Test creating B2 experiment via factory."""
        collector = MagicMock(spec=ICTDataCollector)
        exp = ExperimentFactory.create_experiment("ICT-B2", collector)
        assert isinstance(exp, B2EnhancedExperiment)

    def test_create_unknown_experiment_raises(self):
        """Test creating unknown experiment raises ValueError."""
        collector = MagicMock(spec=ICTDataCollector)
        with pytest.raises(ValueError) as exc_info:
            ExperimentFactory.create_experiment("ICT-B99", collector)
        assert "Unknown experiment ID" in str(exc_info.value)

    def test_list_experiments(self):
        """Test listing all available experiments."""
        experiments = ExperimentFactory.list_experiments()
        assert "ICT-B1" in experiments
        assert "ICT-B2" in experiments
        assert "ICT-B3" in experiments
        assert "ICT-B4" in experiments
        assert "ICT-B5" in experiments

    def test_is_valid_experiment(self):
        """Test checking valid experiment IDs."""
        assert ExperimentFactory.is_valid_experiment("ICT-B1") is True
        assert ExperimentFactory.is_valid_experiment("ICT-B5") is True
        assert ExperimentFactory.is_valid_experiment("ICT-B99") is False


class TestFullFlowIntegration:
    """Integration tests for full experiment flow."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        mock = MagicMock()
        mock.hset = MagicMock(return_value=True)
        mock.expire = MagicMock(return_value=True)
        mock.keys = MagicMock(return_value=[])
        mock.exists = MagicMock(return_value=False)
        mock.sadd = MagicMock(return_value=1)
        mock.srem = MagicMock(return_value=1)
        return mock

    @pytest.mark.asyncio
    async def test_b1_signal_to_outcome_flow(self, mock_redis):
        """Test B1: signal collection -> outcome recording flow."""
        collector = ICTDataCollector(redis_client=mock_redis)
        await collector.start_collection()

        # Record a signal
        signal_id = await collector.collect_signal(
            symbol="BTC/USDT",
            signal_type="entry",
            confidence=0.85,
            experiment_key="ict:exp:ICT-B1:baseline:20260329",
        )
        assert signal_id is not None

        # Record outcome
        await collector.record_outcome(
            position_id="pos-123",
            signal_id=signal_id,
            outcome="profit",
            pnl=50.0,
        )

        await collector.stop_collection()

    @pytest.mark.asyncio
    async def test_multiple_experiments_isolated(self, mock_redis):
        """Test multiple experiments don't contaminate each other."""
        registry = ExperimentRegistry(redis_client=mock_redis)
        collector = ICTDataCollector(redis_client=mock_redis)

        # Create two experiments
        exp1 = B1BaselineExperiment(collector=collector, registry=registry)
        exp2 = B2EnhancedExperiment(collector=collector, registry=registry)

        # Start both
        exp1.start()
        exp2.start()

        # Record signals for each
        sig1 = await exp1.record_signal(
            symbol="BTC/USDT", signal_type="entry", confidence=0.8
        )
        sig2 = await exp2.record_signal(
            symbol="ETH/USDT", signal_type="entry", confidence=0.75
        )

        # Keys should be different due to different experiment IDs
        assert exp1.experiment_key.key_format() != exp2.experiment_key.key_format()

        # Stop both
        await exp1.stop()
        await exp2.stop()

    @pytest.mark.asyncio
    async def test_b2_kill_switch_prevents_signals(self, mock_redis):
        """Test B2 kill switch blocks further signals."""
        registry = ExperimentRegistry(redis_client=mock_redis)
        collector = ICTDataCollector(redis_client=mock_redis)

        exp = B2EnhancedExperiment(
            collector=collector,
            registry=registry,
        )
        exp.risk_limits.kill_switch_threshold = 0.01  # Very low for testing

        exp.start()

        # Trigger kill switch
        await exp.record_outcome(
            position_id="pos-1",
            signal_id="sig-1",
            outcome="loss",
            pnl=-0.02,
        )

        # New signals should be blocked
        result = await exp.record_signal(
            symbol="BTC/USDT",
            signal_type="entry",
            confidence=0.9,
        )

        assert result is None
        assert exp.is_kill_switch_active() is True


class TestExperimentKeyFormatIntegration:
    """Integration tests for experiment key formatting."""

    def test_keys_have_consistent_format(self):
        """Test all experiment keys follow consistent format."""
        from datetime import datetime

        key = ExperimentKey(
            experiment_id="ICT-B1",
            variant="baseline",
            started_at=datetime(2026, 3, 29),
        )

        formatted = key.key_format()
        # Format: ict:exp:{experiment_id}:{variant}:{YYYYMMDD}
        parts = formatted.split(":")
        assert len(parts) == 5
        assert parts[0] == "ict"
        assert parts[1] == "exp"
        assert parts[2] == "ICT-B1"
        assert parts[3] == "baseline"
        assert parts[4] == "20260329"
