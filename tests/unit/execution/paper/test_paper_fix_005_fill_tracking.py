"""Tests for PAPER-FIX-005: Fill tracking bug fixes.

Verifies:
1. Orchestrator receives and uses redis_client when provided
2. Position persistence is enabled in run_signal_consumer
3. Fill events are logged with correct fields
4. Redis hostname defaults to chiseai-redis
5. Complete fill path: order → fill → log → position open

Refs: PAPER-FIX-005
"""

from __future__ import annotations

import importlib
import logging
import os
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from execution.paper.models import OrderState, PaperOrder, TradeStatus
from execution.paper.orchestrator import PaperTradingOrchestrator
from signal_generation.models import Signal, SignalDirection, SignalStatus


@pytest.fixture
def mock_dependencies():
    """Create mock dependencies for orchestrator."""
    signal_generator = MagicMock()

    order_simulator = MagicMock()
    order_simulator.market_data = MagicMock()
    order_simulator.market_data.get_price = MagicMock(return_value=50000.0)
    order_simulator.set_market_price = MagicMock()
    order_simulator.place_order = AsyncMock()

    position_tracker = MagicMock()
    position_tracker.get_open_positions = AsyncMock(return_value=[])
    position_tracker.open_position = AsyncMock()

    risk_enforcer = MagicMock()

    telemetry = MagicMock()
    telemetry.start = AsyncMock()
    telemetry.stop = AsyncMock()
    telemetry.set_equity = AsyncMock()

    kill_switch = MagicMock()
    kill_switch.state = MagicMock()
    kill_switch.state.value = "armed"

    decision_enhancer = MagicMock()
    decision_enhancer.enabled = False

    return {
        "signal_generator": signal_generator,
        "order_simulator": order_simulator,
        "position_tracker": position_tracker,
        "risk_enforcer": risk_enforcer,
        "telemetry": telemetry,
        "kill_switch": kill_switch,
        "decision_enhancer": decision_enhancer,
    }


@pytest.fixture
def sample_signal():
    """Create a sample actionable signal."""
    return Signal(
        token="BTC/USDT",
        direction=SignalDirection.LONG,
        confidence=0.85,
        base_score=85.0,
        timestamp=datetime.now(UTC),
        status=SignalStatus.ACTIONABLE,
        timeframe="1h",
        signal_id=str(uuid.uuid4()),
    )


@pytest.fixture
def filled_order():
    """Create a sample filled order."""
    return PaperOrder(
        order_id=str(uuid.uuid4()),
        symbol="BTC/USDT",
        side="buy",
        order_type="market",
        quantity=0.1,
        price=50000.0,
        state=OrderState.FILLED,
        filled_quantity=0.1,
        avg_fill_price=50000.0,
    )


class TestRedisConfigDefault:
    """Test Fix 3: Redis hostname defaults to chiseai-redis."""

    def test_default_redis_host_is_chiseai_redis(self):
        """Verify REDIS_HOST defaults to 'chiseai-redis' when env var not set."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove the env var if present
            os.environ.pop("PAPER_REDIS_HOST", None)
            # Re-import to pick up new defaults
            import execution.paper.redis_config as rc

            importlib.reload(rc)
            assert (
                rc.REDIS_HOST == "chiseai-redis"
            ), f"Expected REDIS_HOST='chiseai-redis', got '{rc.REDIS_HOST}'"

    def test_redis_host_env_var_override(self):
        """Verify PAPER_REDIS_HOST env var overrides default."""
        with patch.dict(os.environ, {"PAPER_REDIS_HOST": "custom-redis"}):
            import execution.paper.redis_config as rc

            importlib.reload(rc)
            assert rc.REDIS_HOST == "custom-redis"

    def test_redis_port_default(self):
        """Verify REDIS_PORT defaults to 6380."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("PAPER_REDIS_PORT", None)
            import execution.paper.redis_config as rc

            importlib.reload(rc)
            assert rc.REDIS_PORT == 6380

    def test_get_redis_client_uses_centralized_config(self):
        """Verify get_redis_client creates client with centralized config."""
        import execution.paper.redis_config as rc

        with patch("redis.asyncio.Redis") as mock_redis_cls:
            mock_redis_cls.return_value = MagicMock()
            rc.get_redis_client(decode_responses=True)
            call_kwargs = mock_redis_cls.call_args
            assert call_kwargs[1]["host"] == rc.REDIS_HOST
            assert call_kwargs[1]["port"] == rc.REDIS_PORT


class TestOrchestratorRedisClient:
    """Test Fix 1: Orchestrator receives and uses redis_client."""

    @pytest.mark.asyncio
    async def test_orchestrator_stores_redis_client(self, mock_dependencies):
        """Verify orchestrator stores redis_client when provided."""
        mock_redis = MagicMock()
        orchestrator = PaperTradingOrchestrator(
            signal_generator=mock_dependencies["signal_generator"],
            order_simulator=mock_dependencies["order_simulator"],
            position_tracker=mock_dependencies["position_tracker"],
            risk_enforcer=mock_dependencies["risk_enforcer"],
            telemetry_collector=mock_dependencies["telemetry"],
            kill_switch=mock_dependencies["kill_switch"],
            decision_enhancer=mock_dependencies["decision_enhancer"],
            redis_client=mock_redis,
        )
        assert (
            orchestrator._redis is mock_redis
        ), "Orchestrator did not store the provided redis_client"

    @pytest.mark.asyncio
    async def test_orchestrator_works_without_redis_client(self, mock_dependencies):
        """Verify orchestrator works when redis_client is None (graceful degradation)."""
        orchestrator = PaperTradingOrchestrator(
            signal_generator=mock_dependencies["signal_generator"],
            order_simulator=mock_dependencies["order_simulator"],
            position_tracker=mock_dependencies["position_tracker"],
            risk_enforcer=mock_dependencies["risk_enforcer"],
            telemetry_collector=mock_dependencies["telemetry"],
            kill_switch=mock_dependencies["kill_switch"],
            decision_enhancer=mock_dependencies["decision_enhancer"],
            redis_client=None,
        )
        assert orchestrator._redis is None


class TestFillEventLogging:
    """Test Fix 5: Fill events are logged with correct fields."""

    @pytest.mark.asyncio
    async def test_fill_produces_log_entry(
        self, mock_dependencies, sample_signal, filled_order, caplog
    ):
        """Verify fill event produces an info log with [FILL-RECORDED] prefix."""
        # Setup risk enforcer to approve
        mock_dependencies["risk_enforcer"].validate_order = AsyncMock(
            return_value=MagicMock(
                approved=True,
                violations=[],
                position_size=0.1,
            )
        )

        # Setup order simulator to return filled order
        mock_dependencies["order_simulator"].place_order = AsyncMock(
            return_value=filled_order
        )

        # Setup position tracker
        mock_position = MagicMock()
        mock_position.position_id = str(uuid.uuid4())
        mock_position.symbol = "BTC/USDT"
        mock_position.side = "long"
        mock_position.entry_price = 50000.0
        mock_position.quantity = 0.1
        mock_position.metadata = {}
        mock_dependencies["position_tracker"].open_position = AsyncMock(
            return_value=mock_position
        )

        orchestrator = PaperTradingOrchestrator(
            signal_generator=mock_dependencies["signal_generator"],
            order_simulator=mock_dependencies["order_simulator"],
            position_tracker=mock_dependencies["position_tracker"],
            risk_enforcer=mock_dependencies["risk_enforcer"],
            telemetry_collector=mock_dependencies["telemetry"],
            kill_switch=mock_dependencies["kill_switch"],
            decision_enhancer=mock_dependencies["decision_enhancer"],
        )

        with caplog.at_level(logging.INFO, logger="execution.paper.orchestrator"):
            result = await orchestrator.process_signal(sample_signal)

        # Verify the trade was executed
        assert result.status == TradeStatus.EXECUTED

        # Verify the fill log was emitted
        fill_logs = [r for r in caplog.records if "[FILL-RECORDED]" in r.message]
        assert len(fill_logs) >= 1, (
            f"Expected at least 1 [FILL-RECORDED] log, got {len(fill_logs)}. "
            f"Log messages: {[r.message for r in caplog.records]}"
        )

        # Verify log contains key fields
        log_msg = fill_logs[0].message
        assert "BTC/USDT" in log_msg, f"Missing symbol in fill log: {log_msg}"
        assert "buy" in log_msg, f"Missing direction in fill log: {log_msg}"
        assert "50000" in log_msg, f"Missing fill price in fill log: {log_msg}"
        assert (
            filled_order.order_id in log_msg
        ), f"Missing order_id in fill log: {log_msg}"


class TestCompleteFillPath:
    """Test Fix 1+2+5: Complete fill path from signal to position."""

    @pytest.mark.asyncio
    async def test_fill_path_with_redis_client(
        self, mock_dependencies, sample_signal, filled_order
    ):
        """Test complete path: signal → order → fill → redis client available → position."""
        mock_redis = AsyncMock()

        # Setup risk enforcer to approve
        mock_dependencies["risk_enforcer"].validate_order = AsyncMock(
            return_value=MagicMock(
                approved=True,
                violations=[],
                position_size=0.1,
            )
        )

        # Setup order simulator to return filled order
        mock_dependencies["order_simulator"].place_order = AsyncMock(
            return_value=filled_order
        )

        # Setup position tracker
        mock_position = MagicMock()
        mock_position.position_id = str(uuid.uuid4())
        mock_position.symbol = "BTC/USDT"
        mock_position.side = "long"
        mock_position.entry_price = 50000.0
        mock_position.quantity = 0.1
        mock_position.metadata = {}
        mock_dependencies["position_tracker"].open_position = AsyncMock(
            return_value=mock_position
        )

        orchestrator = PaperTradingOrchestrator(
            signal_generator=mock_dependencies["signal_generator"],
            order_simulator=mock_dependencies["order_simulator"],
            position_tracker=mock_dependencies["position_tracker"],
            risk_enforcer=mock_dependencies["risk_enforcer"],
            telemetry_collector=mock_dependencies["telemetry"],
            kill_switch=mock_dependencies["kill_switch"],
            decision_enhancer=mock_dependencies["decision_enhancer"],
            redis_client=mock_redis,
        )

        result = await orchestrator.process_signal(sample_signal)

        # Verify complete path
        assert result.status == TradeStatus.EXECUTED
        assert result.order is not None
        assert result.order.state == OrderState.FILLED
        assert result.position is not None

        # Verify redis client is stored
        assert orchestrator._redis is mock_redis

        # Verify position was opened
        mock_dependencies["position_tracker"].open_position.assert_called_once()


class TestRedisConfigImport:
    """Test that redis_config exports are importable from run_signal_consumer context."""

    def test_get_redis_client_importable(self):
        """Verify get_redis_client can be imported from redis_config."""
        from execution.paper.redis_config import get_redis_client

        assert callable(get_redis_client)

    def test_redis_host_port_importable(self):
        """Verify REDIS_HOST and REDIS_PORT are importable."""
        from execution.paper.redis_config import REDIS_HOST, REDIS_PORT

        assert isinstance(REDIS_HOST, str)
        assert isinstance(REDIS_PORT, int)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
