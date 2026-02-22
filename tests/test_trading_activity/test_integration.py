"""Integration tests for trading activity end-to-end flow.

Tests the complete signal → paper trade flow with mocked external dependencies
(exchange APIs, InfluxDB, etc.).
"""

from __future__ import annotations

import asyncio
import os

# Add src to path
import sys
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))

from scripts.run_trading_activity import (
    TradingActivityMetrics,
    TradingModeLoader,
    _execute_trading_cycle,
    run_trading_loop,
)

from config.trading_mode import TradingModeConfig
from signal_generation.models import Signal, SignalDirection, SignalStatus


class TestTradingActivityIntegration:
    """Integration tests for end-to-end trading flow."""

    @pytest.fixture
    async def paper_loader(self) -> TradingModeLoader:
        """Create and initialize a paper trading loader."""
        config = TradingModeConfig.create_paper_config(
            portfolio_value=10000.0,
            signal_threshold=0.75,
        )
        loader = TradingModeLoader(config)

        # Mock external dependencies
        with patch(
            "scripts.run_trading_activity.ExecutionTelemetryExporter"
        ) as mock_exporter:
            mock_exporter_instance = MagicMock()
            mock_exporter.return_value = mock_exporter_instance

            with patch.object(
                loader, "_initialize_paper_orchestrator", new_callable=AsyncMock
            ):
                success = await loader.load()

        assert success is True
        yield loader
        await loader.shutdown()

    @pytest.mark.asyncio
    async def test_end_to_end_signal_to_trade_flow(self) -> None:
        """Test complete flow from signal generation to paper trade execution."""
        # Setup
        config = TradingModeConfig.create_paper_config(
            portfolio_value=10000.0,
            signal_threshold=0.75,
        )
        loader = TradingModeLoader(config)
        metrics = TradingActivityMetrics()

        # Mock OHLCV fetcher
        mock_ohlcv_data = [
            MagicMock(
                timestamp=1609459200000,
                open_price=29000.0,
                high_price=31000.0,
                low_price=28000.0,
                close_price=30000.0,
                volume=100.0,
            )
            for _ in range(100)
        ]

        with patch.object(loader, "ohlcv_fetcher") as mock_fetcher:
            mock_fetcher.fetch = AsyncMock(return_value=mock_ohlcv_data)

            # Mock signal generator
            mock_signal = Signal(
                token="BTC/USDT",
                direction=SignalDirection.LONG,
                confidence=0.85,  # Above threshold
                base_score=75.0,
                timestamp=datetime.now(UTC),
                status=SignalStatus.ACTIONABLE,
                timeframe="1h",
            )

            with patch.object(loader, "signal_generator") as mock_generator:
                mock_generator.generate_signal = Mock(return_value=mock_signal)

                # Mock orchestrator
                mock_result = MagicMock()
                mock_result.status.value = "executed"

                with patch.object(loader, "paper_orchestrator") as mock_orchestrator:
                    mock_orchestrator.process_signal = AsyncMock(
                        return_value=mock_result
                    )
                    mock_orchestrator.order_simulator = MagicMock()

                    # Execute
                    await _execute_trading_cycle(loader, metrics)

        # Verify
        assert metrics.signals_generated == 1
        assert metrics.risk_gate_checks_executed == 1
        assert metrics.paper_trades_opened == 1

    @pytest.mark.asyncio
    async def test_risk_gate_blocks_low_confidence_trade(self) -> None:
        """Test that risk gate blocks trades with insufficient confidence."""
        config = TradingModeConfig.create_paper_config(
            portfolio_value=10000.0,
            signal_threshold=0.75,
        )
        loader = TradingModeLoader(config)
        metrics = TradingActivityMetrics()

        mock_ohlcv_data = [MagicMock() for _ in range(100)]

        with patch.object(loader, "ohlcv_fetcher") as mock_fetcher:
            mock_fetcher.fetch = AsyncMock(return_value=mock_ohlcv_data)

            # Low confidence signal
            mock_signal = Signal(
                token="BTC/USDT",
                direction=SignalDirection.SHORT,
                confidence=0.60,  # Below threshold
                base_score=60.0,
                timestamp=datetime.now(UTC),
                status=SignalStatus.ACTIONABLE,
                timeframe="1h",
            )

            with patch.object(loader, "signal_generator") as mock_generator:
                mock_generator.generate_signal = Mock(return_value=mock_signal)

                with patch.object(loader, "paper_orchestrator") as mock_orchestrator:
                    mock_orchestrator.order_simulator = MagicMock()

                    # Execute
                    await _execute_trading_cycle(loader, metrics)

        # Signal generated but trade blocked
        assert metrics.signals_generated == 1
        assert metrics.risk_gate_checks_executed == 1
        assert metrics.paper_trades_opened == 0  # Blocked
        mock_orchestrator.process_signal.assert_not_called()

    @pytest.mark.asyncio
    async def test_trading_loop_runs_multiple_cycles(self) -> None:
        """Test that trading loop runs multiple cycles and collects metrics."""
        config = TradingModeConfig.create_paper_config(
            portfolio_value=10000.0,
            signal_threshold=0.75,
        )
        loader = TradingModeLoader(config)
        metrics = TradingActivityMetrics()

        # Mock the cycle execution to count calls
        cycle_count = 0

        async def mock_execute(ldr, mtr):
            nonlocal cycle_count
            cycle_count += 1
            mtr.signals_generated += 1
            mtr.risk_gate_checks_executed += 1

        with patch(
            "scripts.run_trading_activity._execute_trading_cycle",
            side_effect=mock_execute,
        ):
            # Run for 3 iterations (3 seconds with mocked sleep)
            with patch("asyncio.sleep", new_callable=AsyncMock):
                # Stop the loader after a short time
                async def stop_after_delay():
                    await asyncio.sleep(0.1)
                    await loader.shutdown()

                # Start loader
                loader._running = True

                # Run loop with timeout
                try:
                    await asyncio.wait_for(
                        asyncio.gather(
                            run_trading_loop(loader, metrics, duration_seconds=5),
                            stop_after_delay(),
                        ),
                        timeout=2.0,
                    )
                except TimeoutError:
                    pass

        # Verify multiple cycles ran
        assert cycle_count >= 2
        assert metrics.signals_generated == cycle_count
        assert metrics.risk_gate_checks_executed == cycle_count

    @pytest.mark.asyncio
    async def test_metrics_collection_in_trading_loop(self) -> None:
        """Test that metrics are collected during trading loop execution."""
        config = TradingModeConfig.create_paper_config(
            portfolio_value=10000.0,
            signal_threshold=0.75,
        )
        loader = TradingModeLoader(config)
        metrics = TradingActivityMetrics()

        # Mock components to simulate activity
        mock_ohlcv_data = [MagicMock(close_price=30000.0) for _ in range(100)]
        mock_signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=75.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
        )
        mock_result = MagicMock()
        mock_result.status.value = "executed"

        loader.ohlcv_fetcher = AsyncMock()
        loader.ohlcv_fetcher.fetch.return_value = mock_ohlcv_data

        loader.signal_generator = Mock()
        loader.signal_generator.generate_signal.return_value = mock_signal

        loader.paper_orchestrator = AsyncMock()
        loader.paper_orchestrator.process_signal.return_value = mock_result
        loader.paper_orchestrator.order_simulator = MagicMock()

        loader._running = True

        # Execute a few cycles
        for _ in range(3):
            await _execute_trading_cycle(loader, metrics)

        # Verify metrics
        assert metrics.signals_generated == 3
        assert metrics.risk_gate_checks_executed == 3
        assert metrics.paper_trades_opened == 3

    @pytest.mark.asyncio
    async def test_multiple_signals_different_directions(self) -> None:
        """Test handling signals with different directions."""
        config = TradingModeConfig.create_paper_config(
            portfolio_value=10000.0,
            signal_threshold=0.75,
        )
        loader = TradingModeLoader(config)
        metrics = TradingActivityMetrics()

        mock_ohlcv_data = [MagicMock(close_price=30000.0) for _ in range(100)]
        loader.ohlcv_fetcher = AsyncMock()
        loader.ohlcv_fetcher.fetch.return_value = mock_ohlcv_data

        loader.paper_orchestrator = AsyncMock()
        loader.paper_orchestrator.order_simulator = MagicMock()

        # Simulate alternating LONG and SHORT signals
        directions = [
            SignalDirection.LONG,
            SignalDirection.SHORT,
            SignalDirection.LONG,
        ]

        for direction in directions:
            mock_signal = Signal(
                token="BTC/USDT",
                direction=direction,
                confidence=0.85,
                base_score=75.0,
                timestamp=datetime.now(UTC),
                status=SignalStatus.ACTIONABLE,
                timeframe="1h",
            )
            loader.signal_generator = Mock()
            loader.signal_generator.generate_signal.return_value = mock_signal

            mock_result = MagicMock()
            mock_result.status.value = "executed"
            loader.paper_orchestrator.process_signal.return_value = mock_result

            await _execute_trading_cycle(loader, metrics)

        # All signals should result in trades
        assert metrics.signals_generated == 3
        assert metrics.paper_trades_opened == 3

    @pytest.mark.asyncio
    async def test_empty_ohlcv_data_handling(self) -> None:
        """Test handling of empty OHLCV data response."""
        config = TradingModeConfig.create_paper_config(
            portfolio_value=10000.0,
            signal_threshold=0.75,
        )
        loader = TradingModeLoader(config)
        metrics = TradingActivityMetrics()

        # Return empty data
        loader.ohlcv_fetcher = AsyncMock()
        loader.ohlcv_fetcher.fetch.return_value = []

        loader.paper_orchestrator = MagicMock()

        await _execute_trading_cycle(loader, metrics)

        # No activity should be recorded
        assert metrics.signals_generated == 0
        assert metrics.risk_gate_checks_executed == 0
        assert metrics.paper_trades_opened == 0


class TestTradingActivityMetrics:
    """Tests for metrics collection and reporting."""

    def test_metrics_initialization(self) -> None:
        """Test that metrics initialize with correct default values."""
        metrics = TradingActivityMetrics()

        assert metrics.signals_generated == 0
        assert metrics.paper_trades_opened == 0
        assert metrics.paper_trades_closed == 0
        assert metrics.risk_gate_checks_executed == 0
        assert metrics.provider_usage == {}
        assert isinstance(metrics.start_time, datetime)
        assert metrics.snapshots == []

    def test_metrics_to_dict(self) -> None:
        """Test metrics serialization to dictionary."""
        metrics = TradingActivityMetrics()
        metrics.signals_generated = 5
        metrics.paper_trades_opened = 3
        metrics.risk_gate_checks_executed = 5
        metrics.snapshots = [{"test": "data"}]

        data = metrics.to_dict()

        assert data["signals_generated"] == 5
        assert data["paper_trades_opened"] == 3
        assert data["risk_gate_checks_executed"] == 5
        assert data["snapshots"] == [{"test": "data"}]
        assert "start_time" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
