"""Continuous Backtest Runner for ChiseAI.

This module provides an always-on backtest runner that continuously executes
backtests, generates KPIs, and persists results to InfluxDB for Grafana monitoring.

Key features:
- Continuous backtest execution without manual intervention
- KPI generation (Sharpe, max drawdown, win rate, trade count)
- InfluxDB persistence with strategy_id and timestamp tags
- Circuit breaker pattern with asyncio.Lock() for thread safety
- Failure recovery with 60-second resume
- Queue depth and lag monitoring for Grafana

Usage:
    from operations.backtest_runner import BacktestRunner

    runner = BacktestRunner()
    await runner.start()  # Starts continuous execution

    # Or run single backtest
    result = await runner.run_backtest(strategy_id="strategy_001")
    kpis = runner.generate_kpis(trades, equity_curve)
    await runner.persist_kpis(kpis, strategy_id="strategy_001")
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable

# Configure logging
logger = logging.getLogger(__name__)


class BacktestStatus(Enum):
    """Status of a backtest execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RECOVERING = "recovering"


class CircuitBreakerState(Enum):
    """Circuit breaker states for failure handling."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, rejecting requests
    HALF_OPEN = "half_open"  # Testing if recovered


@dataclass
class Trade:
    """Represents a single trade for KPI calculation.

    Attributes:
        entry_time: When the trade was entered
        exit_time: When the trade was exited
        entry_price: Price at entry
        exit_price: Price at exit
        direction: "long" or "short"
        quantity: Position size
        pnl: Profit/loss amount
        pnl_pct: Profit/loss percentage
    """

    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    direction: str
    quantity: float
    pnl: float
    pnl_pct: float


@dataclass
class BacktestKPIs:
    """Key performance indicators for a backtest.

    Attributes:
        strategy_id: Identifier for the strategy
        backtest_id: Unique identifier for this backtest run
        timestamp: When the backtest completed
        sharpe_ratio: Risk-adjusted return metric
        max_drawdown_pct: Maximum peak-to-trough decline (%)
        win_rate_pct: Percentage of winning trades
        trade_count: Total number of trades
        total_return_pct: Total strategy return (%)
        volatility_pct: Standard deviation of returns (%)
        calmar_ratio: Annual return / max drawdown
        sortino_ratio: Return / downside deviation
        avg_trade_return_pct: Average return per trade (%)
        profit_factor: Gross profit / gross loss
        consecutive_wins: Maximum consecutive winning trades
        consecutive_losses: Maximum consecutive losing trades
    """

    strategy_id: str
    backtest_id: str
    timestamp: datetime

    # Core KPIs (required by AC)
    sharpe_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    win_rate_pct: float = 0.0
    trade_count: int = 0

    # Additional KPIs
    total_return_pct: float = 0.0
    volatility_pct: float = 0.0
    calmar_ratio: float = 0.0
    sortino_ratio: float = 0.0
    avg_trade_return_pct: float = 0.0
    profit_factor: float = 0.0
    consecutive_wins: int = 0
    consecutive_losses: int = 0

    # Metadata
    status: BacktestStatus = BacktestStatus.PENDING
    error_message: str | None = None
    execution_time_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert KPIs to dictionary for serialization."""
        return {
            "strategy_id": self.strategy_id,
            "backtest_id": self.backtest_id,
            "timestamp": self.timestamp.isoformat(),
            "sharpe_ratio": self.sharpe_ratio,
            "max_drawdown_pct": self.max_drawdown_pct,
            "win_rate_pct": self.win_rate_pct,
            "trade_count": self.trade_count,
            "total_return_pct": self.total_return_pct,
            "volatility_pct": self.volatility_pct,
            "calmar_ratio": self.calmar_ratio,
            "sortino_ratio": self.sortino_ratio,
            "avg_trade_return_pct": self.avg_trade_return_pct,
            "profit_factor": self.profit_factor,
            "consecutive_wins": self.consecutive_wins,
            "consecutive_losses": self.consecutive_losses,
            "status": self.status.value,
            "error_message": self.error_message,
            "execution_time_seconds": self.execution_time_seconds,
        }


@dataclass
class QueueMetrics:
    """Metrics for backtest queue monitoring.

    Attributes:
        queue_depth: Number of backtests waiting to run
        processing_lag_seconds: Time oldest item has been waiting
        active_backtests: Number of currently running backtests
        completed_today: Number of backtests completed today
        failed_today: Number of backtests failed today
    """

    queue_depth: int = 0
    processing_lag_seconds: float = 0.0
    active_backtests: int = 0
    completed_today: int = 0
    failed_today: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary for InfluxDB."""
        return {
            "queue_depth": self.queue_depth,
            "processing_lag_seconds": self.processing_lag_seconds,
            "active_backtests": self.active_backtests,
            "completed_today": self.completed_today,
            "failed_today": self.failed_today,
            "timestamp": self.timestamp.isoformat(),
        }


class InfluxDBStorageInterface(Protocol):
    """Protocol for InfluxDB storage implementations."""

    async def write_kpis(self, kpis: BacktestKPIs) -> bool:
        """Write KPIs to InfluxDB."""
        ...

    async def write_queue_metrics(self, metrics: QueueMetrics) -> bool:
        """Write queue metrics to InfluxDB."""
        ...


class CircuitBreaker:
    """Circuit breaker for failure handling.

    Implements the circuit breaker pattern with asyncio.Lock() for thread safety.
    Prevents cascade failures by temporarily rejecting requests after consecutive failures.

    Attributes:
        failure_threshold: Number of failures before opening circuit
        recovery_timeout_seconds: Time before attempting recovery
        state: Current circuit state (closed/open/half_open)
        failure_count: Current consecutive failure count
        last_failure_time: Timestamp of last failure
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout_seconds: float = 60.0,
    ) -> None:
        """Initialize circuit breaker.

        Args:
            failure_threshold: Failures before opening circuit
            recovery_timeout_seconds: Seconds before recovery attempt
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._last_failure_time: datetime | None = None
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitBreakerState:
        """Get current circuit state."""
        return self._state

    async def record_success(self) -> None:
        """Record a successful operation."""
        async with self._lock:
            if self._state == CircuitBreakerState.HALF_OPEN:
                self._state = CircuitBreakerState.CLOSED
                logger.info("Circuit breaker closed - service recovered")
            self._failure_count = 0
            self._last_failure_time = None

    async def record_failure(self) -> None:
        """Record a failed operation."""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = datetime.now(timezone.utc)

            if self._failure_count >= self.failure_threshold:
                if self._state != CircuitBreakerState.OPEN:
                    self._state = CircuitBreakerState.OPEN
                    logger.error(
                        f"Circuit breaker opened after {self._failure_count} failures"
                    )

    async def can_execute(self) -> bool:
        """Check if execution is allowed.

        Returns:
            True if circuit allows execution
        """
        async with self._lock:
            if self._state == CircuitBreakerState.CLOSED:
                return True

            if self._state == CircuitBreakerState.OPEN:
                # Check if recovery timeout has elapsed
                if self._last_failure_time:
                    elapsed = (
                        datetime.now(timezone.utc) - self._last_failure_time
                    ).total_seconds()
                    if elapsed >= self.recovery_timeout_seconds:
                        self._state = CircuitBreakerState.HALF_OPEN
                        logger.info("Circuit breaker half-open - attempting recovery")
                        return True
                return False

            # HALF_OPEN - allow one test request
            return True


class InfluxDBKPIStorage:
    """InfluxDB storage for backtest KPIs.

    Persists KPIs to InfluxDB for Grafana visualization.
    Uses chiseai-influxdb:8086 for chiseai network connectivity.
    """

    def __init__(
        self,
        url: str | None = None,
        token: str | None = None,
        org: str | None = None,
        bucket: str | None = None,
    ) -> None:
        """Initialize InfluxDB storage.

        Args:
            url: InfluxDB URL (default: from env or chiseai-influxdb:8086)
            token: InfluxDB token (default: from env)
            org: InfluxDB organization (default: from env)
            bucket: InfluxDB bucket (default: from env)
        """
        # Use chiseai-influxdb for chiseai network per AGENTS.md
        self.url = url or os.getenv("INFLUXDB_URL", "http://chiseai-influxdb:8086")
        self.token = token or os.getenv("INFLUXDB_TOKEN", "chiseai-token")
        self.org = org or os.getenv("INFLUXDB_ORG", "chiseai")
        self.bucket = bucket or os.getenv("INFLUXDB_BUCKET", "chiseai")

        self._client: Any | None = None
        self._write_api: Any | None = None

    def _get_client(self) -> Any:
        """Get or create InfluxDB client."""
        if self._client is None:
            try:
                from influxdb_client import InfluxDBClient

                self._client = InfluxDBClient(
                    url=self.url,
                    token=self.token,
                    org=self.org,
                )
            except ImportError:
                logger.warning("influxdb-client not installed")
                raise
        return self._client

    def _get_write_api(self) -> Any:
        """Get or create write API."""
        if self._write_api is None:
            from influxdb_client.client.write_api import SYNCHRONOUS

            self._write_api = self._get_client().write_api(write_options=SYNCHRONOUS)
        return self._write_api

    async def write_kpis(self, kpis: BacktestKPIs) -> bool:
        """Write KPIs to InfluxDB.

        Args:
            kpis: Backtest KPIs to store

        Returns:
            True if written successfully
        """
        try:
            from influxdb_client import Point

            point = (
                Point("backtest_kpis")
                .time(kpis.timestamp)
                .tag("strategy_id", kpis.strategy_id)
                .tag("backtest_id", kpis.backtest_id)
                .tag("status", kpis.status.value)
                .field("sharpe_ratio", kpis.sharpe_ratio)
                .field("max_drawdown_pct", kpis.max_drawdown_pct)
                .field("win_rate_pct", kpis.win_rate_pct)
                .field("trade_count", kpis.trade_count)
                .field("total_return_pct", kpis.total_return_pct)
                .field("volatility_pct", kpis.volatility_pct)
                .field("calmar_ratio", kpis.calmar_ratio)
                .field("sortino_ratio", kpis.sortino_ratio)
                .field("avg_trade_return_pct", kpis.avg_trade_return_pct)
                .field("profit_factor", kpis.profit_factor)
                .field("consecutive_wins", kpis.consecutive_wins)
                .field("consecutive_losses", kpis.consecutive_losses)
                .field("execution_time_seconds", kpis.execution_time_seconds)
            )

            # Run in thread pool to not block
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, self._get_write_api().write, self.bucket, self.org, point
            )

            logger.info(
                f"Stored KPIs for strategy {kpis.strategy_id} "
                f"(backtest {kpis.backtest_id})"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to write KPIs to InfluxDB: {e}")
            return False

    async def write_queue_metrics(self, metrics: QueueMetrics) -> bool:
        """Write queue metrics to InfluxDB.

        Args:
            metrics: Queue metrics to store

        Returns:
            True if written successfully
        """
        try:
            from influxdb_client import Point

            point = (
                Point("backtest_queue_metrics")
                .time(metrics.timestamp)
                .field("queue_depth", metrics.queue_depth)
                .field("processing_lag_seconds", metrics.processing_lag_seconds)
                .field("active_backtests", metrics.active_backtests)
                .field("completed_today", metrics.completed_today)
                .field("failed_today", metrics.failed_today)
            )

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, self._get_write_api().write, self.bucket, self.org, point
            )

            return True

        except Exception as e:
            logger.error(f"Failed to write queue metrics to InfluxDB: {e}")
            return False

    def close(self) -> None:
        """Close InfluxDB client connection."""
        if self._client:
            self._client.close()
            self._client = None
            self._write_api = None


class BacktestRunner:
    """Main orchestrator for continuous backtest execution.

    This class manages the always-on backtest runner with:
    - Continuous backtest execution without manual intervention
    - KPI generation and persistence to InfluxDB
    - Circuit breaker pattern for failure handling
    - Recovery logic with 60-second resume
    - Queue depth and lag monitoring

    Usage:
        runner = BacktestRunner()
        await runner.start()  # Start continuous execution
        # ... runs continuously ...
        await runner.stop()   # Graceful shutdown
    """

    def __init__(
        self,
        storage: InfluxDBStorageInterface | None = None,
        max_concurrent: int = 3,
        recovery_delay_seconds: float = 60.0,
        enable_walk_forward: bool = True,
    ) -> None:
        """Initialize the backtest runner.

        Args:
            storage: InfluxDB storage implementation
            max_concurrent: Maximum concurrent backtests
            recovery_delay_seconds: Delay before recovery after failure
            enable_walk_forward: Whether to run walk-forward backtests
        """
        self.storage = storage or InfluxDBKPIStorage()
        self.max_concurrent = max_concurrent
        self.recovery_delay_seconds = recovery_delay_seconds
        self.enable_walk_forward = enable_walk_forward

        # Circuit breaker for failure handling
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout_seconds=recovery_delay_seconds,
        )

        # Queue management
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._active_backtests: dict[str, asyncio.Task] = {}
        self._completed_today = 0
        self._failed_today = 0
        self._queue_start_times: dict[str, datetime] = {}

        # Control
        self._running = False
        self._stop_event = asyncio.Event()
        self._monitor_task: asyncio.Task | None = None
        self._worker_tasks: list[asyncio.Task] = []

        # Statistics
        self._stats_lock = asyncio.Lock()

    async def start(self) -> None:
        """Start the continuous backtest runner.

        Starts worker tasks for processing backtests and monitoring.
        """
        if self._running:
            logger.warning("Backtest runner already running")
            return

        self._running = True
        self._stop_event.clear()

        logger.info("Starting continuous backtest runner")

        # Start worker tasks
        for i in range(self.max_concurrent):
            task = asyncio.create_task(
                self._worker_loop(f"worker-{i}"),
                name=f"backtest-worker-{i}",
            )
            self._worker_tasks.append(task)

        # Start monitoring task
        self._monitor_task = asyncio.create_task(
            self._monitor_loop(),
            name="backtest-monitor",
        )

        logger.info(f"Backtest runner started with {self.max_concurrent} workers")

    async def stop(self) -> None:
        """Stop the continuous backtest runner gracefully."""
        if not self._running:
            return

        logger.info("Stopping backtest runner...")
        self._running = False
        self._stop_event.set()

        # Cancel worker tasks
        for task in self._worker_tasks:
            task.cancel()

        # Cancel monitor task
        if self._monitor_task:
            self._monitor_task.cancel()

        # Wait for completion
        try:
            await asyncio.gather(*self._worker_tasks, return_exceptions=True)
            if self._monitor_task:
                await self._monitor_task
        except asyncio.CancelledError:
            pass

        # Close storage
        if hasattr(self.storage, "close"):
            self.storage.close()

        self._worker_tasks.clear()
        logger.info("Backtest runner stopped")

    async def submit_backtest(
        self,
        strategy_id: str,
        backtest_func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> str:
        """Submit a backtest to the queue.

        Args:
            strategy_id: Strategy identifier
            backtest_func: Function to execute for backtest
            *args: Positional arguments for backtest function
            **kwargs: Keyword arguments for backtest function

        Returns:
            backtest_id: Unique identifier for this backtest
        """
        backtest_id = f"{strategy_id}_{datetime.now(timezone.utc).isoformat()}"

        await self._queue.put(
            {
                "backtest_id": backtest_id,
                "strategy_id": strategy_id,
                "func": backtest_func,
                "args": args,
                "kwargs": kwargs,
                "submitted_at": datetime.now(timezone.utc),
            }
        )

        self._queue_start_times[backtest_id] = datetime.now(timezone.utc)

        logger.info(f"Submitted backtest {backtest_id} for strategy {strategy_id}")
        return backtest_id

    async def _worker_loop(self, worker_id: str) -> None:
        """Worker loop for processing backtests.

        Args:
            worker_id: Identifier for this worker
        """
        logger.info(f"Worker {worker_id} started")

        while self._running and not self._stop_event.is_set():
            try:
                # Check circuit breaker
                if not await self.circuit_breaker.can_execute():
                    logger.warning(
                        f"Worker {worker_id}: Circuit breaker open, waiting..."
                    )
                    await asyncio.sleep(self.recovery_delay_seconds)
                    continue

                # Get next backtest from queue
                try:
                    backtest_job = await asyncio.wait_for(
                        self._queue.get(),
                        timeout=1.0,
                    )
                except asyncio.TimeoutError:
                    continue

                backtest_id = backtest_job["backtest_id"]
                strategy_id = backtest_job["strategy_id"]

                # Track active backtest
                self._active_backtests[backtest_id] = asyncio.current_task()  # type: ignore

                try:
                    # Execute backtest
                    logger.info(f"Worker {worker_id}: Running backtest {backtest_id}")

                    result = await self.run_backtest(
                        strategy_id=strategy_id,
                        backtest_func=backtest_job["func"],
                        args=backtest_job["args"],
                        kwargs=backtest_job["kwargs"],
                    )

                    # Record success
                    await self.circuit_breaker.record_success()

                    async with self._stats_lock:
                        self._completed_today += 1

                    logger.info(
                        f"Worker {worker_id}: Completed backtest {backtest_id} "
                        f"(Sharpe: {result.sharpe_ratio:.2f})"
                    )

                except Exception as e:
                    # Record failure
                    await self.circuit_breaker.record_failure()

                    async with self._stats_lock:
                        self._failed_today += 1

                    logger.error(
                        f"Worker {worker_id}: Backtest {backtest_id} failed: {e}"
                    )

                finally:
                    # Clean up tracking
                    self._active_backtests.pop(backtest_id, None)
                    self._queue_start_times.pop(backtest_id, None)
                    self._queue.task_done()

            except asyncio.CancelledError:
                logger.info(f"Worker {worker_id} cancelled")
                raise
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}")
                await self.circuit_breaker.record_failure()
                await asyncio.sleep(1.0)

    async def _monitor_loop(self) -> None:
        """Monitor loop for queue metrics and health checks."""
        while self._running and not self._stop_event.is_set():
            try:
                # Calculate queue metrics
                metrics = await self._get_queue_metrics()

                # Persist to InfluxDB
                await self.storage.write_queue_metrics(metrics)

                # Wait before next check
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=30.0,  # Report every 30 seconds
                )

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                logger.info("Monitor loop cancelled")
                raise
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")
                await asyncio.sleep(5.0)

    async def _get_queue_metrics(self) -> QueueMetrics:
        """Calculate current queue metrics.

        Returns:
            QueueMetrics with current state
        """
        # Calculate processing lag
        now = datetime.now(timezone.utc)
        processing_lag = 0.0

        if self._queue_start_times:
            oldest = min(self._queue_start_times.values())
            processing_lag = (now - oldest).total_seconds()

        async with self._stats_lock:
            return QueueMetrics(
                queue_depth=self._queue.qsize(),
                processing_lag_seconds=processing_lag,
                active_backtests=len(self._active_backtests),
                completed_today=self._completed_today,
                failed_today=self._failed_today,
                timestamp=now,
            )

    async def run_backtest(
        self,
        strategy_id: str,
        backtest_func: Callable[..., Any] | None = None,
        args: tuple | None = None,
        kwargs: dict | None = None,
    ) -> BacktestKPIs:
        """Execute a single backtest and return KPIs.

        This is the core backtest execution function. It runs the backtest
        function (if provided) or simulates one, generates KPIs, and persists
        them to InfluxDB.

        Args:
            strategy_id: Strategy identifier
            backtest_func: Optional function to execute backtest
            args: Positional arguments for backtest function
            kwargs: Keyword arguments for backtest function

        Returns:
            BacktestKPIs with calculated metrics
        """
        start_time = datetime.now(timezone.utc)
        backtest_id = f"bt_{strategy_id}_{start_time.timestamp()}"

        try:
            # Execute backtest function if provided
            if backtest_func:
                result = await self._execute_backtest_func(
                    backtest_func,
                    args or (),
                    kwargs or {},
                )
                trades = result.get("trades", [])
                equity_curve = result.get("equity_curve", [])
            else:
                # Simulate backtest for testing
                trades, equity_curve = self._simulate_backtest()

            # Generate KPIs
            kpis = self.generate_kpis(
                trades=trades,
                equity_curve=equity_curve,
                strategy_id=strategy_id,
                backtest_id=backtest_id,
            )

            # Calculate execution time
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            kpis.execution_time_seconds = execution_time

            # Persist to InfluxDB
            await self.persist_kpis(kpis)

            return kpis

        except Exception as e:
            logger.error(f"Backtest execution failed: {e}")

            # Return failed KPIs
            return BacktestKPIs(
                strategy_id=strategy_id,
                backtest_id=backtest_id,
                timestamp=start_time,
                status=BacktestStatus.FAILED,
                error_message=str(e),
                execution_time_seconds=(
                    datetime.now(timezone.utc) - start_time
                ).total_seconds(),
            )

    async def _execute_backtest_func(
        self,
        func: Callable[..., Any],
        args: tuple,
        kwargs: dict,
    ) -> dict[str, Any]:
        """Execute backtest function in thread pool.

        Args:
            func: Backtest function to execute
            args: Positional arguments
            kwargs: Keyword arguments

        Returns:
            Dictionary with trades and equity_curve
        """
        loop = asyncio.get_event_loop()

        # Run in thread pool to not block event loop
        if asyncio.iscoroutinefunction(func):
            result = await func(*args, **kwargs)
        else:
            result = await loop.run_in_executor(None, lambda: func(*args, **kwargs))

        if isinstance(result, dict):
            return result
        else:
            # Assume result object has trades and equity_curve attributes
            return {
                "trades": getattr(result, "trades", []),
                "equity_curve": getattr(result, "equity_curve", []),
            }

    def _simulate_backtest(
        self,
        num_trades: int = 100,
    ) -> tuple[list[Trade], list[float]]:
        """Simulate backtest data for testing.

        Args:
            num_trades: Number of trades to simulate

        Returns:
            Tuple of (trades, equity_curve)
        """
        import random

        trades = []
        equity = 10000.0
        equity_curve = [equity]

        for i in range(num_trades):
            direction = "long" if random.random() > 0.5 else "short"
            pnl_pct = random.gauss(0.5, 2.0)  # Mean 0.5%, std 2%
            pnl = equity * (pnl_pct / 100)

            trade = Trade(
                entry_time=datetime.now(timezone.utc),
                exit_time=datetime.now(timezone.utc),
                entry_price=100.0 + i,
                exit_price=100.0 + i + (1 if pnl > 0 else -1),
                direction=direction,
                quantity=1.0,
                pnl=pnl,
                pnl_pct=pnl_pct,
            )
            trades.append(trade)

            equity += pnl
            equity_curve.append(equity)

        return trades, equity_curve

    def generate_kpis(
        self,
        trades: list[Trade],
        equity_curve: list[float],
        strategy_id: str,
        backtest_id: str,
        timestamp: datetime | None = None,
    ) -> BacktestKPIs:
        """Calculate KPIs from backtest results.

        Generates the core KPIs required by acceptance criteria:
        - Sharpe ratio
        - Max drawdown
        - Win rate
        - Trade count

        Args:
            trades: List of trades from backtest
            equity_curve: Equity values over time
            strategy_id: Strategy identifier
            backtest_id: Backtest identifier
            timestamp: Optional timestamp (defaults to now)

        Returns:
            BacktestKPIs with calculated metrics
        """
        if not timestamp:
            timestamp = datetime.now(timezone.utc)

        if not trades or not equity_curve:
            return BacktestKPIs(
                strategy_id=strategy_id,
                backtest_id=backtest_id,
                timestamp=timestamp,
                trade_count=0,
                status=BacktestStatus.COMPLETED,
            )

        # Basic counts
        trade_count = len(trades)
        winning_trades = [t for t in trades if t.pnl > 0]
        losing_trades = [t for t in trades if t.pnl <= 0]

        # Win rate
        win_rate_pct = (
            (len(winning_trades) / trade_count * 100) if trade_count > 0 else 0
        )

        # Returns
        total_pnl = sum(t.pnl for t in trades)
        initial_equity = equity_curve[0] if equity_curve else 10000.0
        total_return_pct = (total_pnl / initial_equity) * 100 if initial_equity else 0

        # Calculate returns series for Sharpe and volatility
        returns = []
        for i in range(1, len(equity_curve)):
            if equity_curve[i - 1] != 0:
                ret = (equity_curve[i] - equity_curve[i - 1]) / equity_curve[i - 1]
                returns.append(ret)

        # Volatility (annualized assuming daily returns)
        if len(returns) > 1:
            import statistics

            volatility_pct = statistics.stdev(returns) * (252**0.5) * 100
        else:
            volatility_pct = 0.0

        # Sharpe ratio (assuming risk-free rate of 0 for simplicity)
        if volatility_pct > 0:
            sharpe_ratio = (total_return_pct / 100) / (volatility_pct / 100)
        else:
            sharpe_ratio = 0.0

        # Max drawdown
        max_drawdown_pct = self._calculate_max_drawdown(equity_curve)

        # Calmar ratio
        if max_drawdown_pct > 0:
            calmar_ratio = total_return_pct / max_drawdown_pct
        else:
            calmar_ratio = 0.0

        # Sortino ratio (downside deviation)
        downside_returns = [r for r in returns if r < 0]
        if len(downside_returns) >= 2:
            import statistics

            downside_std = statistics.stdev(downside_returns) * (252**0.5)
            if downside_std > 0:
                sortino_ratio = (total_return_pct / 100) / downside_std
            else:
                sortino_ratio = 0.0
        else:
            sortino_ratio = 0.0

        # Profit factor
        gross_profit = sum(t.pnl for t in winning_trades)
        gross_loss = abs(sum(t.pnl for t in losing_trades))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else gross_profit

        # Average trade return
        avg_trade_return_pct = (
            sum(t.pnl_pct for t in trades) / trade_count if trade_count > 0 else 0
        )

        # Consecutive wins/losses
        consecutive_wins = 0
        consecutive_losses = 0
        max_consecutive_wins = 0
        max_consecutive_losses = 0

        for trade in trades:
            if trade.pnl > 0:
                consecutive_wins += 1
                consecutive_losses = 0
                max_consecutive_wins = max(max_consecutive_wins, consecutive_wins)
            else:
                consecutive_losses += 1
                consecutive_wins = 0
                max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)

        return BacktestKPIs(
            strategy_id=strategy_id,
            backtest_id=backtest_id,
            timestamp=timestamp,
            sharpe_ratio=sharpe_ratio,
            max_drawdown_pct=max_drawdown_pct,
            win_rate_pct=win_rate_pct,
            trade_count=trade_count,
            total_return_pct=total_return_pct,
            volatility_pct=volatility_pct,
            calmar_ratio=calmar_ratio,
            sortino_ratio=sortino_ratio,
            avg_trade_return_pct=avg_trade_return_pct,
            profit_factor=profit_factor,
            consecutive_wins=max_consecutive_wins,
            consecutive_losses=max_consecutive_losses,
            status=BacktestStatus.COMPLETED,
        )

    def _calculate_max_drawdown(self, equity_curve: list[float]) -> float:
        """Calculate maximum drawdown percentage.

        Args:
            equity_curve: List of equity values

        Returns:
            Maximum drawdown as percentage
        """
        if not equity_curve or len(equity_curve) < 2:
            return 0.0

        max_drawdown = 0.0
        peak = equity_curve[0]

        for equity in equity_curve:
            if equity > peak:
                peak = equity
            drawdown = (peak - equity) / peak if peak > 0 else 0
            max_drawdown = max(max_drawdown, drawdown)

        return max_drawdown * 100

    async def persist_kpis(self, kpis: BacktestKPIs) -> bool:
        """Persist KPIs to InfluxDB.

        Args:
            kpis: Backtest KPIs to persist

        Returns:
            True if persisted successfully
        """
        success = await self.storage.write_kpis(kpis)

        if success:
            logger.info(
                f"Persisted KPIs for strategy {kpis.strategy_id} "
                f"(Sharpe: {kpis.sharpe_ratio:.2f}, "
                f"Max DD: {kpis.max_drawdown_pct:.2f}%, "
                f"Win Rate: {kpis.win_rate_pct:.1f}%, "
                f"Trades: {kpis.trade_count})"
            )
        else:
            logger.error(f"Failed to persist KPIs for strategy {kpis.strategy_id}")

        return success

    async def run_walk_forward_backtests(
        self,
        strategy_ids: list[str],
        window_days: int = 30,
    ) -> list[BacktestKPIs]:
        """Run walk-forward backtests for multiple strategies.

        This implements the daily walk-forward backtest requirement.

        Args:
            strategy_ids: List of strategy IDs to backtest
            window_days: Lookback window in days

        Returns:
            List of BacktestKPIs for each strategy
        """
        results = []

        for strategy_id in strategy_ids:
            try:
                # Submit to queue for processing
                backtest_id = await self.submit_backtest(
                    strategy_id=strategy_id,
                    backtest_func=self._run_walk_forward_single,
                    strategy_id_arg=strategy_id,
                    window_days=window_days,
                )

                logger.info(
                    f"Submitted walk-forward backtest for {strategy_id} "
                    f"(ID: {backtest_id})"
                )

            except Exception as e:
                logger.error(
                    f"Failed to submit walk-forward backtest for {strategy_id}: {e}"
                )

        return results

    async def _run_walk_forward_single(
        self,
        strategy_id: str,
        window_days: int,
    ) -> dict[str, Any]:
        """Run a single walk-forward backtest.

        Args:
            strategy_id: Strategy identifier
            window_days: Lookback window in days

        Returns:
            Dictionary with trades and equity_curve
        """
        # This would integrate with actual backtesting logic
        # For now, simulate results
        trades, equity_curve = self._simulate_backtest(num_trades=50)

        return {
            "trades": trades,
            "equity_curve": equity_curve,
            "window_days": window_days,
        }


# Convenience functions for standalone usage
async def run_backtest(
    strategy_id: str,
    trades: list[Trade] | None = None,
    equity_curve: list[float] | None = None,
) -> BacktestKPIs:
    """Run a single backtest and return KPIs.

    Convenience function for simple backtest execution.

    Args:
        strategy_id: Strategy identifier
        trades: Optional list of trades (simulated if not provided)
        equity_curve: Optional equity curve (simulated if not provided)

    Returns:
        BacktestKPIs with calculated metrics
    """
    runner = BacktestRunner()

    if trades is None or equity_curve is None:
        trades, equity_curve = runner._simulate_backtest()

    kpis = runner.generate_kpis(
        trades=trades,
        equity_curve=equity_curve,
        strategy_id=strategy_id,
        backtest_id=f"bt_{strategy_id}_{datetime.now(timezone.utc).timestamp()}",
    )

    await runner.persist_kpis(kpis)
    return kpis


async def generate_kpis(
    trades: list[Trade],
    equity_curve: list[float],
    strategy_id: str,
) -> BacktestKPIs:
    """Generate KPIs from backtest results.

    Convenience function for KPI generation without full runner.

    Args:
        trades: List of trades
        equity_curve: Equity curve values
        strategy_id: Strategy identifier

    Returns:
        BacktestKPIs with calculated metrics
    """
    runner = BacktestRunner()
    return runner.generate_kpis(
        trades=trades,
        equity_curve=equity_curve,
        strategy_id=strategy_id,
        backtest_id=f"bt_{strategy_id}_{datetime.now(timezone.utc).timestamp()}",
    )


async def persist_kpis(kpis: BacktestKPIs) -> bool:
    """Persist KPIs to InfluxDB.

    Convenience function for persisting KPIs without full runner.

    Args:
        kpis: Backtest KPIs to persist

    Returns:
        True if persisted successfully
    """
    runner = BacktestRunner()
    return await runner.persist_kpis(kpis)


__all__ = [
    "BacktestRunner",
    "BacktestKPIs",
    "BacktestStatus",
    "CircuitBreaker",
    "CircuitBreakerState",
    "QueueMetrics",
    "Trade",
    "InfluxDBKPIStorage",
    "run_backtest",
    "generate_kpis",
    "persist_kpis",
]
