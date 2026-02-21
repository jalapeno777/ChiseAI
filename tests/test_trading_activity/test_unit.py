"""Unit tests for trading activity loop wiring.

Tests the _execute_trading_cycle function and TradingModeLoader
component initialization without external dependencies.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add src to path
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))

from scripts.run_trading_activity import (
    TradingModeLoader,
    TradingActivityMetrics,
    _execute_trading_cycle,
)
from config.trading_mode import TradingMode, TradingModeConfig, ModuleType
from signal_generation.models import Signal, SignalDirection, SignalStatus
from data_ingestion.ohlcv_fetcher import OHLCVData


class TestTradingModeLoader:
    """Test TradingModeLoader component initialization."""

    @pytest.fixture
    def paper_config(self) -> TradingModeConfig:
        """Create a paper trading config for testing."""
        return TradingModeConfig.create_paper_config(
            portfolio_value=10000.0,
            signal_threshold=0.75,
        )

    @pytest.fixture
    def loader(self, paper_config: TradingModeConfig) -> TradingModeLoader:
        """Create a TradingModeLoader for testing."""
        return TradingModeLoader(paper_config)

    @pytest.mark.asyncio
    async def test_loader_initializes_components_in_paper_mode(
        self,
        loader: TradingModeLoader,
    ) -> None:
        """Test that loader initializes all required components in paper mode."""
        # Mock the orchestrator start to avoid external dependencies
        with patch.object(
            loader, "_initialize_paper_orchestrator", new_callable=AsyncMock
        ):
            success = await loader.load()

        assert success is True
        assert loader._running is True
        assert loader._start_time is not None

        # Check that key components are initialized
        assert loader.ohlcv_fetcher is not None
        assert loader.signal_generator is not None
        assert loader.order_simulator is not None
        assert loader.position_tracker is not None
        assert loader.risk_enforcer is not None
        assert loader.kill_switch is not None

    @pytest.mark.asyncio
    async def test_loader_tracks_module_status(
        self,
        loader: TradingModeLoader,
    ) -> None:
        """Test that loader tracks module status correctly."""
        with patch.object(
            loader, "_initialize_paper_orchestrator", new_callable=AsyncMock
        ):
            await loader.load()

        status = loader.get_module_status()

        assert status["mode"] == "PAPER"
        assert status["running"] is True
        assert status["uptime_seconds"] >= 0.0
        assert "modules" in status

        # Check all expected modules are tracked
        modules = status["modules"]
        assert "MARKET_DATA" in modules
        assert "SIGNAL_GENERATOR" in modules
        assert "PAPER_EXECUTOR" in modules
        assert "RISK_MANAGER" in modules

    @pytest.mark.asyncio
    async def test_loader_shutdown_stops_orchestrator(
        self,
        loader: TradingModeLoader,
    ) -> None:
        """Test that shutdown properly stops the orchestrator."""
        with patch.object(
            loader, "_initialize_paper_orchestrator", new_callable=AsyncMock
        ):
            await loader.load()

        # Create a mock orchestrator
        mock_orchestrator = AsyncMock()
        loader.paper_orchestrator = mock_orchestrator

        await loader.shutdown()

        assert loader._running is False
        mock_orchestrator.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_loader_uptime_calculation(
        self,
        loader: TradingModeLoader,
    ) -> None:
        """Test that uptime is calculated correctly."""
        with patch.object(
            loader, "_initialize_paper_orchestrator", new_callable=AsyncMock
        ):
            await loader.load()

        # Wait a tiny bit
        await asyncio.sleep(0.01)

        uptime = loader._get_uptime_seconds()
        assert uptime >= 0.01

    @pytest.mark.asyncio
    async def test_loader_validation_fails_with_invalid_config(
        self,
    ) -> None:
        """Test that loader fails to load with invalid config."""
        invalid_config = TradingModeConfig(
            mode=TradingMode.PAPER,
            enabled_modules=set(),  # Missing required modules
            paper_portfolio_value=-1000,  # Invalid value
        )
        loader = TradingModeLoader(invalid_config)

        success = await loader.load()
        assert success is False


class TestExecuteTradingCycle:
    """Test the _execute_trading_cycle function."""

    @pytest.fixture
    def mock_loader(self) -> MagicMock:
        """Create a mock TradingModeLoader."""
        loader = MagicMock()
        loader.config.mode = TradingMode.PAPER
        loader.config.signal_confidence_threshold = 0.75
        loader.paper_orchestrator = MagicMock()
        loader.ohlcv_fetcher = AsyncMock()
        loader.signal_generator = MagicMock()
        return loader

    @pytest.fixture
    def metrics(self) -> TradingActivityMetrics:
        """Create a fresh metrics object."""
        return TradingActivityMetrics()

    @pytest.mark.asyncio
    async def test_cycle_skips_non_paper_mode(
        self,
        mock_loader: MagicMock,
        metrics: TradingActivityMetrics,
    ) -> None:
        """Test that cycle is skipped in non-paper mode."""
        mock_loader.config.mode = TradingMode.LIVE

        await _execute_trading_cycle(mock_loader, metrics)

        # No components should be called
        mock_loader.ohlcv_fetcher.fetch.assert_not_called()
        assert metrics.signals_generated == 0

    @pytest.mark.asyncio
    async def test_cycle_skips_without_orchestrator(
        self,
        mock_loader: MagicMock,
        metrics: TradingActivityMetrics,
    ) -> None:
        """Test that cycle is skipped without orchestrator."""
        mock_loader.paper_orchestrator = None

        await _execute_trading_cycle(mock_loader, metrics)

        assert metrics.signals_generated == 0

    @pytest.mark.asyncio
    async def test_cycle_fetches_market_data(
        self,
        mock_loader: MagicMock,
        metrics: TradingActivityMetrics,
    ) -> None:
        """Test that cycle fetches market data."""
        # Setup mock OHLCV data
        mock_ohlcv = [
            OHLCVData(
                timestamp=1609459200000,
                open_price=29000.0,
                high_price=31000.0,
                low_price=28000.0,
                close_price=30000.0,
                volume=100.0,
            )
        ]
        mock_loader.ohlcv_fetcher.fetch.return_value = mock_ohlcv

        # Setup mock signal (actionable)
        mock_signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=75.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
        )
        mock_loader.signal_generator.generate_signal.return_value = mock_signal

        # Setup mock orchestrator result
        mock_result = MagicMock()
        mock_result.status.value = "executed"
        mock_loader.paper_orchestrator.process_signal.return_value = mock_result

        await _execute_trading_cycle(mock_loader, metrics)

        # Verify fetch was called
        mock_loader.ohlcv_fetcher.fetch.assert_called_once()
        call_args = mock_loader.ohlcv_fetcher.fetch.call_args
        assert call_args.kwargs["symbol"] == "BTC/USDT"
        assert call_args.kwargs["limit"] == 100

    @pytest.mark.asyncio
    async def test_cycle_generates_signals(
        self,
        mock_loader: MagicMock,
        metrics: TradingActivityMetrics,
    ) -> None:
        """Test that cycle generates signals and updates metrics."""
        # Setup mock data
        mock_ohlcv = [
            OHLCVData(
                timestamp=1609459200000,
                open_price=29000.0,
                high_price=31000.0,
                low_price=28000.0,
                close_price=30000.0,
                volume=100.0,
            )
        ]
        mock_loader.ohlcv_fetcher.fetch.return_value = mock_ohlcv

        mock_signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=75.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
        )
        mock_loader.signal_generator.generate_signal.return_value = mock_signal

        mock_result = MagicMock()
        mock_result.status.value = "executed"
        mock_loader.paper_orchestrator.process_signal.return_value = mock_result

        await _execute_trading_cycle(mock_loader, metrics)

        # Verify signal generation
        mock_loader.signal_generator.generate_signal.assert_called_once()
        assert metrics.signals_generated == 1
        assert metrics.risk_gate_checks_executed == 1

    @pytest.mark.asyncio
    async def test_cycle_executes_trade_for_actionable_signal(
        self,
        mock_loader: MagicMock,
        metrics: TradingActivityMetrics,
    ) -> None:
        """Test that cycle executes trades for actionable signals."""
        # Setup mock data
        mock_ohlcv = [
            OHLCVData(
                timestamp=1609459200000,
                open_price=29000.0,
                high_price=31000.0,
                low_price=28000.0,
                close_price=30000.0,
                volume=100.0,
            )
        ]
        mock_loader.ohlcv_fetcher.fetch.return_value = mock_ohlcv

        mock_signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=75.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
        )
        mock_loader.signal_generator.generate_signal.return_value = mock_signal

        mock_result = MagicMock()
        mock_result.status.value = "executed"
        mock_loader.paper_orchestrator.process_signal.return_value = mock_result

        await _execute_trading_cycle(mock_loader, metrics)

        # Verify trade execution
        mock_loader.paper_orchestrator.process_signal.assert_called_once_with(
            mock_signal
        )
        assert metrics.paper_trades_opened == 1

    @pytest.mark.asyncio
    async def test_cycle_skips_non_actionable_signals(
        self,
        mock_loader: MagicMock,
        metrics: TradingActivityMetrics,
    ) -> None:
        """Test that cycle skips signals that aren't actionable."""
        # Setup mock data
        mock_ohlcv = [
            OHLCVData(
                timestamp=1609459200000,
                open_price=29000.0,
                high_price=31000.0,
                low_price=28000.0,
                close_price=30000.0,
                volume=100.0,
            )
        ]
        mock_loader.ohlcv_fetcher.fetch.return_value = mock_ohlcv

        # Non-actionable signal
        mock_signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.NEUTRAL,
            confidence=0.50,
            base_score=50.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.LOGGED_ONLY,
            timeframe="1h",
        )
        mock_loader.signal_generator.generate_signal.return_value = mock_signal

        await _execute_trading_cycle(mock_loader, metrics)

        # Signal should be generated but trade not executed
        assert metrics.signals_generated == 1
        assert metrics.risk_gate_checks_executed == 1
        assert metrics.paper_trades_opened == 0
        mock_loader.paper_orchestrator.process_signal.assert_not_called()

    @pytest.mark.asyncio
    async def test_cycle_skips_low_confidence_signals(
        self,
        mock_loader: MagicMock,
        metrics: TradingActivityMetrics,
    ) -> None:
        """Test that cycle skips signals below confidence threshold."""
        # Setup mock data
        mock_ohlcv = [
            OHLCVData(
                timestamp=1609459200000,
                open_price=29000.0,
                high_price=31000.0,
                low_price=28000.0,
                close_price=30000.0,
                volume=100.0,
            )
        ]
        mock_loader.ohlcv_fetcher.fetch.return_value = mock_ohlcv

        # Actionable but low confidence signal
        mock_signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.50,  # Below 0.75 threshold
            base_score=50.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
        )
        mock_loader.signal_generator.generate_signal.return_value = mock_signal

        await _execute_trading_cycle(mock_loader, metrics)

        # Signal generated but trade not executed due to low confidence
        assert metrics.signals_generated == 1
        assert metrics.risk_gate_checks_executed == 1
        assert metrics.paper_trades_opened == 0

    @pytest.mark.asyncio
    async def test_cycle_handles_fetch_failure(
        self,
        mock_loader: MagicMock,
        metrics: TradingActivityMetrics,
    ) -> None:
        """Test that cycle handles OHLCV fetch failure gracefully."""
        mock_loader.ohlcv_fetcher.fetch.side_effect = Exception("Network error")

        await _execute_trading_cycle(mock_loader, metrics)

        # No metrics should be updated
        assert metrics.signals_generated == 0
        assert metrics.risk_gate_checks_executed == 0

    @pytest.mark.asyncio
    async def test_cycle_handles_signal_generation_failure(
        self,
        mock_loader: MagicMock,
        metrics: TradingActivityMetrics,
    ) -> None:
        """Test that cycle handles signal generation failure gracefully."""
        mock_ohlcv = [
            OHLCVData(
                timestamp=1609459200000,
                open_price=29000.0,
                high_price=31000.0,
                low_price=28000.0,
                close_price=30000.0,
                volume=100.0,
            )
        ]
        mock_loader.ohlcv_fetcher.fetch.return_value = mock_ohlcv
        mock_loader.signal_generator.generate_signal.side_effect = Exception(
            "Indicator error"
        )

        await _execute_trading_cycle(mock_loader, metrics)

        # Fetch succeeded but signal generation failed
        assert metrics.signals_generated == 0
        assert metrics.risk_gate_checks_executed == 0

    @pytest.mark.asyncio
    async def test_cycle_sets_market_price_before_trade(
        self,
        mock_loader: MagicMock,
        metrics: TradingActivityMetrics,
    ) -> None:
        """Test that cycle sets market price before executing trade."""
        # Setup mock data
        mock_ohlcv = [
            OHLCVData(
                timestamp=1609459200000,
                open_price=29000.0,
                high_price=31000.0,
                low_price=28000.0,
                close_price=30000.0,
                volume=100.0,
            )
        ]
        mock_loader.ohlcv_fetcher.fetch.return_value = mock_ohlcv

        mock_signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=75.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
        )
        mock_loader.signal_generator.generate_signal.return_value = mock_signal

        mock_result = MagicMock()
        mock_result.status.value = "executed"
        mock_loader.paper_orchestrator.process_signal.return_value = mock_result

        # Setup order_simulator mock
        mock_loader.paper_orchestrator.order_simulator = MagicMock()

        await _execute_trading_cycle(mock_loader, metrics)

        # Verify market price was set (using same format as signal.token: "BTC/USDT")
        mock_loader.paper_orchestrator.order_simulator.set_market_price.assert_called_once_with(
            "BTC/USDT", 30000.0
        )

    @pytest.mark.asyncio
    async def test_price_cache_populated_before_trading(
        self,
        mock_loader: MagicMock,
        metrics: TradingActivityMetrics,
    ) -> None:
        """Test that price cache is populated before trading to prevent order rejection.

        This is a regression test for BURNIN-001: Orders were rejected because
        market_data.get_price() returned None due to empty price cache.
        """
        # Setup mock data with latest close price
        mock_ohlcv = [
            OHLCVData(
                timestamp=1609459200000,
                open_price=29000.0,
                high_price=31000.0,
                low_price=28000.0,
                close_price=30500.0,  # Latest price
                volume=100.0,
            ),
            OHLCVData(
                timestamp=1609459260000,
                open_price=30000.0,
                high_price=32000.0,
                low_price=29500.0,
                close_price=31500.0,  # This is the latest price that should be cached
                volume=150.0,
            ),
        ]
        mock_loader.ohlcv_fetcher.fetch.return_value = mock_ohlcv

        mock_signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=75.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
        )
        mock_loader.signal_generator.generate_signal.return_value = mock_signal

        mock_result = MagicMock()
        mock_result.status.value = "executed"
        mock_loader.paper_orchestrator.process_signal.return_value = mock_result

        # Setup order_simulator with real market_data to verify price is set
        from execution.paper.order_simulator import MarketDataProvider

        real_market_data = MarketDataProvider()

        # Create a mock order_simulator that wraps the real set_market_price behavior
        mock_order_sim = MagicMock()
        mock_order_sim.market_data = real_market_data

        # Make set_market_price actually set the price in the real market_data
        def side_effect_set_price(symbol, price):
            real_market_data.set_price(symbol, price)

        mock_order_sim.set_market_price.side_effect = side_effect_set_price
        mock_loader.paper_orchestrator.order_simulator = mock_order_sim

        await _execute_trading_cycle(mock_loader, metrics)

        # Verify the latest price from OHLCV was set in the cache
        # The price should be from the LAST candle (ohlcv_data[-1].close_price)
        cached_price = real_market_data.get_price("BTC/USDT")
        assert (
            cached_price is not None
        ), "Price cache should be populated before trading"
        assert cached_price == 31500.0, f"Expected 31500.0, got {cached_price}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
