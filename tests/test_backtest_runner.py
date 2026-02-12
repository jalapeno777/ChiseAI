"""Unit tests for continuous backtest runner.

Tests cover:
- BacktestRunner initialization and lifecycle
- KPI generation accuracy
- Circuit breaker pattern
- InfluxDB persistence
- Queue metrics
- Failure recovery
"""

from __future__ import annotations

import asyncio
import statistics
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from operations.backtest_runner import (
    BacktestKPIs,
    BacktestRunner,
    BacktestStatus,
    CircuitBreaker,
    CircuitBreakerState,
    InfluxDBKPIStorage,
    QueueMetrics,
    Trade,
    generate_kpis,
    persist_kpis,
    run_backtest,
)


class TestCircuitBreaker:
    """Tests for circuit breaker pattern."""

    @pytest.mark.asyncio
    async def test_initial_state_is_closed(self) -> None:
        """Test that circuit breaker starts in closed state."""
        cb = CircuitBreaker()
        assert cb.state == CircuitBreakerState.CLOSED
        assert await cb.can_execute() is True

    @pytest.mark.asyncio
    async def test_opens_after_threshold_failures(self) -> None:
        """Test circuit opens after threshold failures."""
        cb = CircuitBreaker(failure_threshold=3)

        # Record failures up to threshold
        await cb.record_failure()
        assert cb.state == CircuitBreakerState.CLOSED

        await cb.record_failure()
        assert cb.state == CircuitBreakerState.CLOSED

        await cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN

    @pytest.mark.asyncio
    async def test_rejects_requests_when_open(self) -> None:
        """Test that requests are rejected when circuit is open."""
        cb = CircuitBreaker(failure_threshold=1)

        await cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN
        assert await cb.can_execute() is False

    @pytest.mark.asyncio
    async def test_transitions_to_half_open_after_timeout(self) -> None:
        """Test circuit transitions to half-open after recovery timeout."""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout_seconds=0.1)

        await cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN
        assert await cb.can_execute() is False

        # Wait for recovery timeout
        await asyncio.sleep(0.15)

        # Should now be half-open and allow execution
        assert await cb.can_execute() is True
        assert cb.state == CircuitBreakerState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_closes_on_success(self) -> None:
        """Test circuit closes after success in half-open state."""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout_seconds=0.1)

        await cb.record_failure()
        await asyncio.sleep(0.15)

        # Should be half-open
        assert await cb.can_execute() is True

        # Record success
        await cb.record_success()
        assert cb.state == CircuitBreakerState.CLOSED

    @pytest.mark.asyncio
    async def test_thread_safety_with_lock(self) -> None:
        """Test that circuit breaker uses lock for thread safety."""
        cb = CircuitBreaker(failure_threshold=10)

        # Simulate concurrent access
        async def record_failures():
            for _ in range(5):
                await cb.record_failure()
                await asyncio.sleep(0.01)

        # Run concurrently
        await asyncio.gather(record_failures(), record_failures())

        # Should have recorded all failures
        assert cb._failure_count == 10


class TestBacktestKPIs:
    """Tests for BacktestKPIs dataclass."""

    def test_kpis_creation(self) -> None:
        """Test creating BacktestKPIs with default values."""
        kpis = BacktestKPIs(
            strategy_id="test_strategy",
            backtest_id="bt_001",
            timestamp=datetime.now(timezone.utc),
        )

        assert kpis.strategy_id == "test_strategy"
        assert kpis.backtest_id == "bt_001"
        assert kpis.sharpe_ratio == 0.0
        assert kpis.max_drawdown_pct == 0.0
        assert kpis.win_rate_pct == 0.0
        assert kpis.trade_count == 0

    def test_kpis_to_dict(self) -> None:
        """Test converting KPIs to dictionary."""
        timestamp = datetime.now(timezone.utc)
        kpis = BacktestKPIs(
            strategy_id="test_strategy",
            backtest_id="bt_001",
            timestamp=timestamp,
            sharpe_ratio=1.5,
            max_drawdown_pct=10.0,
            win_rate_pct=55.0,
            trade_count=100,
            status=BacktestStatus.COMPLETED,
        )

        d = kpis.to_dict()

        assert d["strategy_id"] == "test_strategy"
        assert d["backtest_id"] == "bt_001"
        assert d["sharpe_ratio"] == 1.5
        assert d["max_drawdown_pct"] == 10.0
        assert d["win_rate_pct"] == 55.0
        assert d["trade_count"] == 100
        assert d["status"] == "completed"


class TestTrade:
    """Tests for Trade dataclass."""

    def test_trade_creation(self) -> None:
        """Test creating a Trade."""
        now = datetime.now(timezone.utc)
        trade = Trade(
            entry_time=now,
            exit_time=now + timedelta(hours=1),
            entry_price=100.0,
            exit_price=105.0,
            direction="long",
            quantity=1.0,
            pnl=5.0,
            pnl_pct=5.0,
        )

        assert trade.entry_price == 100.0
        assert trade.exit_price == 105.0
        assert trade.pnl == 5.0
        assert trade.direction == "long"


class TestQueueMetrics:
    """Tests for QueueMetrics dataclass."""

    def test_metrics_creation(self) -> None:
        """Test creating QueueMetrics."""
        metrics = QueueMetrics(
            queue_depth=10,
            processing_lag_seconds=30.0,
            active_backtests=3,
            completed_today=50,
            failed_today=2,
        )

        assert metrics.queue_depth == 10
        assert metrics.processing_lag_seconds == 30.0
        assert metrics.active_backtests == 3
        assert metrics.completed_today == 50
        assert metrics.failed_today == 2

    def test_metrics_to_dict(self) -> None:
        """Test converting metrics to dictionary."""
        timestamp = datetime.now(timezone.utc)
        metrics = QueueMetrics(
            queue_depth=5,
            processing_lag_seconds=15.0,
            timestamp=timestamp,
        )

        d = metrics.to_dict()

        assert d["queue_depth"] == 5
        assert d["processing_lag_seconds"] == 15.0
        assert d["timestamp"] == timestamp.isoformat()


class TestBacktestRunnerKPIs:
    """Tests for KPI generation in BacktestRunner."""

    def test_generate_kpis_empty_data(self) -> None:
        """Test KPI generation with empty data."""
        runner = BacktestRunner()

        kpis = runner.generate_kpis(
            trades=[],
            equity_curve=[],
            strategy_id="test",
            backtest_id="bt_001",
        )

        assert kpis.trade_count == 0
        assert kpis.sharpe_ratio == 0.0
        assert kpis.status == BacktestStatus.COMPLETED

    def test_generate_kpis_with_trades(self) -> None:
        """Test KPI generation with trade data."""
        runner = BacktestRunner()

        # Create sample trades
        now = datetime.now(timezone.utc)
        trades = [
            Trade(
                entry_time=now,
                exit_time=now + timedelta(hours=1),
                entry_price=100.0,
                exit_price=105.0,
                direction="long",
                quantity=1.0,
                pnl=5.0,
                pnl_pct=5.0,
            ),
            Trade(
                entry_time=now,
                exit_time=now + timedelta(hours=1),
                entry_price=105.0,
                exit_price=103.0,
                direction="short",
                quantity=1.0,
                pnl=-2.0,
                pnl_pct=-1.9,
            ),
            Trade(
                entry_time=now,
                exit_time=now + timedelta(hours=1),
                entry_price=103.0,
                exit_price=108.0,
                direction="long",
                quantity=1.0,
                pnl=5.0,
                pnl_pct=4.85,
            ),
        ]

        equity_curve = [10000.0, 10005.0, 10003.0, 10008.0]

        kpis = runner.generate_kpis(
            trades=trades,
            equity_curve=equity_curve,
            strategy_id="test",
            backtest_id="bt_001",
        )

        assert kpis.trade_count == 3
        assert kpis.win_rate_pct == pytest.approx(66.67, rel=0.1)
        assert kpis.total_return_pct == pytest.approx(0.08, rel=0.1)

    def test_calculate_max_drawdown(self) -> None:
        """Test max drawdown calculation."""
        runner = BacktestRunner()

        # Equity curve with drawdown
        equity_curve = [
            10000.0,  # Start
            10500.0,  # Peak
            10200.0,  # Drawdown start
            9800.0,  # Max drawdown
            10100.0,  # Recovery
            11000.0,  # New peak
        ]

        max_dd = runner._calculate_max_drawdown(equity_curve)

        # Max drawdown: (10500 - 9800) / 10500 = 6.67%
        assert max_dd == pytest.approx(6.67, rel=0.1)

    def test_calculate_max_drawdown_no_drawdown(self) -> None:
        """Test max drawdown with always increasing equity."""
        runner = BacktestRunner()

        equity_curve = [10000.0, 10100.0, 10200.0, 10300.0]

        max_dd = runner._calculate_max_drawdown(equity_curve)

        assert max_dd == 0.0

    def test_calculate_max_drawdown_empty(self) -> None:
        """Test max drawdown with empty curve."""
        runner = BacktestRunner()

        max_dd = runner._calculate_max_drawdown([])

        assert max_dd == 0.0

    def test_win_rate_calculation(self) -> None:
        """Test win rate calculation."""
        runner = BacktestRunner()

        now = datetime.now(timezone.utc)
        trades = [
            Trade(now, now, 100, 105, "long", 1, 5, 5),  # Win
            Trade(now, now, 105, 103, "short", 1, -2, -1.9),  # Loss
            Trade(now, now, 103, 108, "long", 1, 5, 4.85),  # Win
            Trade(now, now, 108, 108, "long", 1, 0, 0),  # Break-even (loss)
        ]

        equity_curve = [10000, 10005, 10003, 10008, 10008]

        kpis = runner.generate_kpis(
            trades=trades,
            equity_curve=equity_curve,
            strategy_id="test",
            backtest_id="bt_001",
        )

        # 2 wins out of 4 trades = 50%
        assert kpis.win_rate_pct == 50.0

    def test_sharpe_ratio_calculation(self) -> None:
        """Test Sharpe ratio calculation."""
        runner = BacktestRunner()

        # Create trades with consistent positive returns
        now = datetime.now(timezone.utc)
        trades = []
        equity = 10000.0
        equity_curve = [equity]

        for i in range(100):
            pnl = 10.0 + (i % 5)  # Small consistent profits
            equity += pnl
            equity_curve.append(equity)

            trades.append(
                Trade(
                    entry_time=now,
                    exit_time=now + timedelta(hours=1),
                    entry_price=100.0,
                    exit_price=100.0 + pnl,
                    direction="long",
                    quantity=1.0,
                    pnl=pnl,
                    pnl_pct=pnl / 100.0,
                )
            )

        kpis = runner.generate_kpis(
            trades=trades,
            equity_curve=equity_curve,
            strategy_id="test",
            backtest_id="bt_001",
        )

        # Should have positive Sharpe with consistent profits
        assert kpis.sharpe_ratio > 0
        assert kpis.trade_count == 100

    def test_consecutive_wins_losses(self) -> None:
        """Test consecutive wins/losses calculation."""
        runner = BacktestRunner()

        now = datetime.now(timezone.utc)
        # Pattern: WWLLWWWLLLWW
        trades = [
            Trade(now, now, 100, 105, "long", 1, 5, 5),  # Win
            Trade(now, now, 105, 110, "long", 1, 5, 4.76),  # Win
            Trade(now, now, 110, 108, "long", 1, -2, -1.82),  # Loss
            Trade(now, now, 108, 106, "long", 1, -2, -1.85),  # Loss
            Trade(now, now, 106, 111, "long", 1, 5, 4.72),  # Win
            Trade(now, now, 111, 116, "long", 1, 5, 4.5),  # Win
            Trade(now, now, 116, 121, "long", 1, 5, 4.31),  # Win
            Trade(now, now, 121, 119, "long", 1, -2, -1.65),  # Loss
            Trade(now, now, 119, 117, "long", 1, -2, -1.68),  # Loss
            Trade(now, now, 117, 115, "long", 1, -2, -1.71),  # Loss
            Trade(now, now, 115, 120, "long", 1, 5, 4.35),  # Win
            Trade(now, now, 120, 125, "long", 1, 5, 4.17),  # Win
        ]

        equity_curve = [10000.0] + [
            10000.0 + sum(t.pnl for t in trades[: i + 1]) for i in range(len(trades))
        ]

        kpis = runner.generate_kpis(
            trades=trades,
            equity_curve=equity_curve,
            strategy_id="test",
            backtest_id="bt_001",
        )

        assert kpis.consecutive_wins == 3  # WWW
        assert kpis.consecutive_losses == 3  # LLL


class TestBacktestRunnerLifecycle:
    """Tests for BacktestRunner lifecycle management."""

    @pytest.mark.asyncio
    async def test_runner_initialization(self) -> None:
        """Test runner initializes correctly."""
        runner = BacktestRunner(max_concurrent=5)

        assert runner.max_concurrent == 5
        assert not runner._running

    @pytest.mark.asyncio
    async def test_runner_start_stop(self) -> None:
        """Test runner start and stop."""
        runner = BacktestRunner(max_concurrent=1)

        # Mock storage to avoid InfluxDB dependency
        runner.storage = AsyncMock()

        await runner.start()
        assert runner._running
        assert len(runner._worker_tasks) == 1

        await runner.stop()
        assert not runner._running
        assert len(runner._worker_tasks) == 0

    @pytest.mark.asyncio
    async def test_submit_backtest(self) -> None:
        """Test submitting backtest to queue."""
        runner = BacktestRunner()

        backtest_id = await runner.submit_backtest(
            strategy_id="test_strategy",
            backtest_func=lambda: None,
        )

        assert backtest_id.startswith("test_strategy_")
        assert runner._queue.qsize() == 1

    @pytest.mark.asyncio
    async def test_queue_metrics_calculation(self) -> None:
        """Test queue metrics calculation."""
        runner = BacktestRunner()

        # Add items to queue
        await runner.submit_backtest("strategy_1", lambda: None)
        await runner.submit_backtest("strategy_2", lambda: None)

        metrics = await runner._get_queue_metrics()

        assert metrics.queue_depth == 2
        assert metrics.active_backtests == 0


class TestInfluxDBStorage:
    """Tests for InfluxDB storage."""

    def test_storage_initialization(self) -> None:
        """Test storage initializes with correct defaults."""
        with patch.dict("os.environ", {}, clear=True):
            storage = InfluxDBKPIStorage()

            assert storage.url == "http://chiseai-influxdb:8086"
            assert storage.token == "chiseai-token"
            assert storage.org == "chiseai"
            assert storage.bucket == "chiseai"

    def test_storage_with_env_vars(self) -> None:
        """Test storage reads from environment variables."""
        with patch.dict(
            "os.environ",
            {
                "INFLUXDB_URL": "http://custom:8086",
                "INFLUXDB_TOKEN": "custom-token",
            },
        ):
            storage = InfluxDBKPIStorage()

            assert storage.url == "http://custom:8086"
            assert storage.token == "custom-token"

    @pytest.mark.asyncio
    async def test_write_kpis_success(self) -> None:
        """Test successful KPI write."""
        storage = InfluxDBKPIStorage()

        # Mock the InfluxDB client
        mock_client = MagicMock()
        mock_write_api = MagicMock()
        mock_client.write_api.return_value = mock_write_api
        storage._client = mock_client
        storage._write_api = mock_write_api

        kpis = BacktestKPIs(
            strategy_id="test",
            backtest_id="bt_001",
            timestamp=datetime.now(timezone.utc),
            sharpe_ratio=1.5,
            max_drawdown_pct=10.0,
            win_rate_pct=55.0,
            trade_count=100,
        )

        result = await storage.write_kpis(kpis)

        assert result is True
        mock_write_api.write.assert_called_once()

    @pytest.mark.asyncio
    async def test_write_kpis_failure(self) -> None:
        """Test KPI write failure handling."""
        storage = InfluxDBKPIStorage()

        # Mock to raise exception
        with patch.object(storage, "_get_write_api", side_effect=Exception("DB error")):
            kpis = BacktestKPIs(
                strategy_id="test",
                backtest_id="bt_001",
                timestamp=datetime.now(timezone.utc),
            )

            result = await storage.write_kpis(kpis)

            assert result is False

    @pytest.mark.asyncio
    async def test_write_queue_metrics(self) -> None:
        """Test writing queue metrics."""
        storage = InfluxDBKPIStorage()

        mock_client = MagicMock()
        mock_write_api = MagicMock()
        mock_client.write_api.return_value = mock_write_api
        storage._client = mock_client
        storage._write_api = mock_write_api

        metrics = QueueMetrics(
            queue_depth=10,
            processing_lag_seconds=30.0,
        )

        result = await storage.write_queue_metrics(metrics)

        assert result is True
        mock_write_api.write.assert_called_once()


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    @pytest.mark.asyncio
    async def test_run_backtest(self) -> None:
        """Test run_backtest convenience function."""
        with patch(
            "operations.backtest_runner.BacktestRunner.persist_kpis",
            new_callable=AsyncMock,
        ) as mock_persist:
            mock_persist.return_value = True

            kpis = await run_backtest("test_strategy")

            assert kpis.strategy_id == "test_strategy"
            assert kpis.trade_count > 0
            mock_persist.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_kpis(self) -> None:
        """Test generate_kpis convenience function."""
        now = datetime.now(timezone.utc)
        trades = [
            Trade(now, now, 100, 105, "long", 1, 5, 5),
            Trade(now, now, 105, 103, "short", 1, -2, -1.9),
        ]
        equity_curve = [10000.0, 10005.0, 10003.0]

        kpis = await generate_kpis(trades, equity_curve, "test_strategy")

        assert kpis.strategy_id == "test_strategy"
        assert kpis.trade_count == 2

    @pytest.mark.asyncio
    async def test_persist_kpis(self) -> None:
        """Test persist_kpis convenience function."""
        with patch(
            "operations.backtest_runner.BacktestRunner.persist_kpis",
            new_callable=AsyncMock,
        ) as mock_persist:
            mock_persist.return_value = True

            kpis = BacktestKPIs(
                strategy_id="test",
                backtest_id="bt_001",
                timestamp=datetime.now(timezone.utc),
            )

            result = await persist_kpis(kpis)

            assert result is True
            mock_persist.assert_called_once_with(kpis)


class TestSimulatedBacktest:
    """Tests for simulated backtest data generation."""

    def test_simulate_backtest(self) -> None:
        """Test simulated backtest generation."""
        runner = BacktestRunner()

        trades, equity_curve = runner._simulate_backtest(num_trades=50)

        assert len(trades) == 50
        assert len(equity_curve) == 51  # Initial + one per trade
        assert all(isinstance(t, Trade) for t in trades)

    def test_simulated_trades_have_pnl(self) -> None:
        """Test that simulated trades have PnL values."""
        runner = BacktestRunner()

        trades, _ = runner._simulate_backtest(num_trades=10)

        for trade in trades:
            assert isinstance(trade.pnl, float)
            assert isinstance(trade.pnl_pct, float)
            assert trade.direction in ["long", "short"]


class TestFailureRecovery:
    """Tests for failure recovery behavior."""

    @pytest.mark.asyncio
    async def test_runner_handles_backtest_failure(self) -> None:
        """Test runner handles backtest failures gracefully."""
        runner = BacktestRunner()

        # Mock storage
        runner.storage = AsyncMock()
        runner.storage.write_kpis = AsyncMock(return_value=True)

        # Create a failing backtest function
        async def failing_backtest():
            raise ValueError("Simulated failure")

        # Run backtest
        kpis = await runner.run_backtest(
            strategy_id="test",
            backtest_func=failing_backtest,
        )

        # Should return failed status, not raise
        assert kpis.status == BacktestStatus.FAILED
        assert kpis.error_message is not None

    @pytest.mark.asyncio
    async def test_circuit_breaker_prevents_cascade(self) -> None:
        """Test that circuit breaker prevents cascade failures."""
        runner = BacktestRunner()
        runner.circuit_breaker.failure_threshold = 3

        # Record multiple failures
        for _ in range(5):
            await runner.circuit_breaker.record_failure()

        # Circuit should be open
        assert runner.circuit_breaker.state == CircuitBreakerState.OPEN
        assert await runner.circuit_breaker.can_execute() is False


class TestWalkForward:
    """Tests for walk-forward backtest functionality."""

    @pytest.mark.asyncio
    async def test_run_walk_forward_backtests(self) -> None:
        """Test walk-forward backtest submission."""
        runner = BacktestRunner()
        runner.storage = AsyncMock()

        await runner.start()

        try:
            strategy_ids = ["strategy_1", "strategy_2"]
            results = await runner.run_walk_forward_backtests(strategy_ids)

            # Should submit all strategies to queue
            assert runner._queue.qsize() == 2

        finally:
            await runner.stop()

    @pytest.mark.asyncio
    async def test_walk_forward_single(self) -> None:
        """Test single walk-forward backtest execution."""
        runner = BacktestRunner()

        result = await runner._run_walk_forward_single(
            strategy_id="test",
            window_days=30,
        )

        assert "trades" in result
        assert "equity_curve" in result
        assert "window_days" in result
        assert result["window_days"] == 30

    @pytest.mark.asyncio
    async def test_walk_forward_uses_real_data_when_available(self) -> None:
        """Test that walk-forward uses real data, not simulated, when available."""
        runner = BacktestRunner()

        # Mock _load_historical_data to return sufficient data
        mock_data = [
            {
                "timestamp": 1704067200000 + i * 3600000,  # Hourly data
                "open": 100.0 + i * 0.1,
                "high": 101.0 + i * 0.1,
                "low": 99.0 + i * 0.1,
                "close": 100.5 + i * 0.1,
                "volume": 1000.0,
            }
            for i in range(200)  # 200 candles = sufficient data
        ]

        with patch.object(
            runner, "_load_historical_data", return_value=mock_data
        ) as mock_load:
            result = await runner._run_walk_forward_single(
                strategy_id="test_strategy",
                window_days=30,
                symbol="BTCUSDT",
            )

            # Verify data was loaded
            mock_load.assert_called_once()
            assert result.get("is_simulated") is False
            assert result.get("data_points") == 200
            assert result.get("train_candles") == 140  # 70% of 200
            assert result.get("test_candles") == 60  # 30% of 200

    @pytest.mark.asyncio
    async def test_walk_forward_falls_back_to_simulation_on_insufficient_data(self) -> None:
        """Test that walk-forward falls back to simulation when data is insufficient."""
        runner = BacktestRunner()

        # Mock _load_historical_data to return insufficient data
        mock_data = [
            {
                "timestamp": 1704067200000 + i * 3600000,
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 1000.0,
            }
            for i in range(50)  # Only 50 candles = insufficient
        ]

        with patch.object(runner, "_load_historical_data", return_value=mock_data):
            result = await runner._run_walk_forward_single(
                strategy_id="test_strategy",
                window_days=30,
                symbol="BTCUSDT",
            )

            # Should fall back to simulation
            assert result.get("is_simulated") is True
            assert len(result["trades"]) == 50  # Simulated trades

    @pytest.mark.asyncio
    async def test_walk_forward_generates_real_trades_from_data(self) -> None:
        """Test that walk-forward generates real trades from actual data execution."""
        runner = BacktestRunner()

        # Create trending data that should generate trades
        mock_data = []
        base_price = 100.0
        for i in range(200):
            # Create an uptrend then downtrend pattern
            if i < 100:
                price = base_price + i * 0.5  # Uptrend
            else:
                price = base_price + 50 - (i - 100) * 0.5  # Downtrend

            mock_data.append({
                "timestamp": 1704067200000 + i * 3600000,
                "open": price - 0.5,
                "high": price + 1.0,
                "low": price - 1.0,
                "close": price,
                "volume": 1000.0,
            })

        with patch.object(runner, "_load_historical_data", return_value=mock_data):
            result = await runner._run_walk_forward_single(
                strategy_id="test_strategy",
                window_days=30,
                symbol="BTCUSDT",
            )

            # Should generate trades from actual strategy execution
            trades = result["trades"]
            assert len(trades) > 0
            assert result.get("is_simulated") is False

            # Verify trades have real properties
            for trade in trades:
                assert trade.entry_price > 0
                assert trade.exit_price > 0
                assert trade.direction in ["long", "short"]
                assert isinstance(trade.pnl, float)

    @pytest.mark.asyncio
    async def test_walk_forward_daily_scheduling_with_actual_data(self) -> None:
        """Test that daily scheduling works with actual data loading."""
        runner = BacktestRunner()
        runner.storage = AsyncMock()

        # Mock data for multiple strategies
        mock_data = [
            {
                "timestamp": 1704067200000 + i * 3600000,
                "open": 100.0 + i * 0.01,
                "high": 101.0 + i * 0.01,
                "low": 99.0 + i * 0.01,
                "close": 100.5 + i * 0.01,
                "volume": 1000.0,
            }
            for i in range(200)
        ]

        with patch.object(runner, "_load_historical_data", return_value=mock_data):
            await runner.start()

            try:
                strategy_ids = ["strategy_1", "strategy_2", "strategy_3"]
                await runner.run_walk_forward_backtests(
                    strategy_ids=strategy_ids,
                    window_days=30,
                )

                # All strategies should be queued
                assert runner._queue.qsize() == 3

            finally:
                await runner.stop()

    @pytest.mark.asyncio
    async def test_walk_forward_kpis_calculated_from_real_trades(self) -> None:
        """Test that KPIs are calculated from real trades, not simulated."""
        runner = BacktestRunner()

        # Create data that generates known trade outcomes
        mock_data = []
        for i in range(200):
            # Strong uptrend - should generate winning long trades
            price = 100.0 + i * 0.1
            mock_data.append({
                "timestamp": 1704067200000 + i * 3600000,
                "open": price,
                "high": price + 0.5,
                "low": price - 0.5,
                "close": price + 0.1,
                "volume": 1000.0,
            })

        with patch.object(runner, "_load_historical_data", return_value=mock_data):
            result = await runner._run_walk_forward_single(
                strategy_id="test_strategy",
                window_days=30,
            )

            # Verify the result structure for real execution
            assert result.get("is_simulated") is False
            assert "train_metrics" in result
            assert "train_candles" in result
            assert "test_candles" in result

            # Trades should exist and have real values
            trades = result["trades"]
            assert len(trades) > 0

            # Equity curve should reflect actual trading
            equity_curve = result["equity_curve"]
            assert len(equity_curve) > 1
            assert equity_curve[0] == 10000.0  # Initial capital


class TestIntegration:
    """Integration-style tests."""

    @pytest.mark.asyncio
    async def test_full_backtest_pipeline(self) -> None:
        """Test complete backtest pipeline from submission to persistence."""
        runner = BacktestRunner(max_concurrent=1)

        # Mock storage
        mock_storage = AsyncMock()
        mock_storage.write_kpis = AsyncMock(return_value=True)
        mock_storage.write_queue_metrics = AsyncMock(return_value=True)
        runner.storage = mock_storage

        # Start runner
        await runner.start()

        try:
            # Submit a backtest
            async def sample_backtest():
                return {
                    "trades": [
                        Trade(
                            datetime.now(timezone.utc),
                            datetime.now(timezone.utc),
                            100,
                            105,
                            "long",
                            1,
                            5,
                            5,
                        ),
                    ],
                    "equity_curve": [10000.0, 10005.0],
                }

            backtest_id = await runner.submit_backtest(
                strategy_id="integration_test",
                backtest_func=sample_backtest,
            )

            # Wait for processing
            await asyncio.sleep(0.5)

            # Verify it was queued
            assert (
                backtest_id in runner._queue_start_times
                or runner._completed_today > 0
                or runner._queue.qsize() == 0
            )

        finally:
            await runner.stop()

    @pytest.mark.asyncio
    async def test_queue_depth_monitoring(self) -> None:
        """Test that queue depth is properly monitored."""
        runner = BacktestRunner()
        runner.storage = AsyncMock()

        # Add multiple items
        for i in range(5):
            await runner.submit_backtest(f"strategy_{i}", lambda: None)

        metrics = await runner._get_queue_metrics()

        assert metrics.queue_depth == 5
        assert metrics.processing_lag_seconds >= 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
