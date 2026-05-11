#!/usr/bin/env python3
"""Trading activity runner script - CLI entry point for running trading activity.

This script provides a unified interface for running trading activities in different
modes: paper, live, backtest, and dry_run. It handles environment bootstrapping,
configuration management, metrics collection, and graceful shutdown.

Usage:
    python scripts/run_trading_activity.py --mode paper --duration 1800
    python scripts/run_trading_activity.py --mode backtest --config path/to/config.yaml
    python scripts/run_trading_activity.py --mode live --confidence-threshold 0.8

Output:
    - _bmad-output/trading-activity-report-<timestamp>.json
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import logging
import os
import signal
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Handle case where config was already imported from a different location
if "config" in sys.modules:
    # Remove the cached config module to ensure we import from src
    del sys.modules["config"]
    # Also remove any config submodules
    for mod_name in list(sys.modules.keys()):
        if mod_name.startswith("config."):
            del sys.modules[mod_name]

from config.bootstrap import bootstrap
from config.trading_mode import ModuleType, TradingMode, TradingModeConfig

# Trading components for actual wiring
from data_ingestion.ohlcv_fetcher import CCXTAdapter, OHLCVFetcher
from data_ingestion.timeframe_config import Timeframe
from execution.connectors.bybit_demo_connector import BybitDemoConnector
from execution.incident_reporter import publish_execution_incident
from execution.kill_switch.executor import KillSwitchExecutor
from execution.outcome_capture.integration import OutcomeCaptureIntegration
from execution.paper import (
    MarketDataProvider,
    OrderSimulator,
    PaperPositionTracker,
    create_simulator,
)
from execution.paper.orchestrator import PaperTradingOrchestrator
from execution.paper.risk_enforcer import PaperRiskEnforcer
from execution.paper.risk_models import RiskCheck
from execution.paper.signal_consumer import SignalConsumer
from execution.telemetry.collector import ExecutionCollector
from execution.telemetry.exporter import ExecutionTelemetryExporter
from signal_generation.models import SignalStatus
from signal_generation.signal_generator import SignalGenerator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _is_local_test_env() -> bool:
    environment = os.getenv("ENVIRONMENT", "").strip().lower()
    pytest_active = bool(os.getenv("PYTEST_CURRENT_TEST"))
    return environment in {"local", "test", "dev"} or pytest_active


def _allow_simulator_fallback() -> bool:
    raw = os.getenv("ALLOW_SIMULATOR_FALLBACK", "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        try:
            from audit.override_audit import log_override_if_active

            log_override_if_active(
                "ALLOW_SIMULATOR_FALLBACK", reason="allow simulator in trading"
            )
        except Exception:
            pass  # audit is best-effort
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return _is_local_test_env()


@dataclass
class TradingActivityMetrics:
    """Metrics collected during trading activity execution.

    Attributes:
        signals_generated: Total number of signals generated
        paper_trades_opened: Number of paper trades opened
        paper_trades_closed: Number of paper trades closed
        risk_gate_checks_executed: Number of risk gate checks performed
        provider_usage: Dictionary tracking provider usage counts
        start_time: When the activity started
        snapshots: List of periodic metric snapshots
    """

    signals_generated: int = 0
    paper_trades_opened: int = 0
    paper_trades_closed: int = 0
    risk_gate_checks_executed: int = 0
    provider_usage: dict[str, int] = field(default_factory=dict)
    start_time: datetime = field(default_factory=lambda: datetime.now(UTC))
    snapshots: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary for serialization."""
        return {
            "signals_generated": self.signals_generated,
            "paper_trades_opened": self.paper_trades_opened,
            "paper_trades_closed": self.paper_trades_closed,
            "risk_gate_checks_executed": self.risk_gate_checks_executed,
            "provider_usage": self.provider_usage,
            "start_time": self.start_time.isoformat(),
            "snapshots": self.snapshots,
        }


class TradingModeLoader:
    """Loads and manages trading mode configuration and modules.

    This class is responsible for:
    - Loading configuration for the specified trading mode
    - Initializing required modules based on mode requirements
    - Providing module status tracking
    - Graceful startup and shutdown
    """

    def __init__(self, config: TradingModeConfig) -> None:
        """Initialize the loader with trading mode configuration.

        Args:
            config: TradingModeConfig with mode and module settings
        """
        self.config = config
        self._modules: dict[ModuleType, Any] = {}
        self._running = False
        self._shutdown_event = asyncio.Event()
        self._start_time: datetime | None = None

        # Trading components (initialized in load())
        self.ohlcv_fetcher: OHLCVFetcher | None = None
        self.signal_generator: SignalGenerator | None = None
        self.paper_orchestrator: PaperTradingOrchestrator | None = None
        self.order_simulator: OrderSimulator | None = None
        self.position_tracker: PaperPositionTracker | None = None
        self.risk_enforcer: PaperRiskEnforcer | None = None
        self.telemetry_collector: ExecutionCollector | None = None
        self.kill_switch: KillSwitchExecutor | None = None

        logger.info(f"TradingModeLoader initialized for mode: {config.mode.name}")

    async def load(self) -> bool:
        """Load and initialize all required modules.

        Returns:
            True if all modules loaded successfully, False otherwise
        """
        logger.info(f"Loading modules for {self.config.mode.name} mode...")

        required_modules = self.config.get_required_modules()
        logger.info(f"Required modules: {[m.name for m in required_modules]}")

        # Validate configuration before loading
        validation_errors = self.config.get_validation_errors()
        if validation_errors:
            for error in validation_errors:
                logger.error(f"Config validation error: {error}")
            return False

        try:
            # Initialize modules based on configuration
            for module_type in required_modules:
                await self._initialize_module(module_type)

            # Initialize paper trading orchestrator if in paper mode
            if self.config.mode == TradingMode.PAPER:
                await self._initialize_paper_orchestrator()

            self._running = True
            self._start_time = datetime.now(UTC)
            logger.info("All modules loaded successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to load modules: {e}", exc_info=True)
            return False

    async def _initialize_module(self, module_type: ModuleType) -> None:
        """Initialize a specific module type.

        Args:
            module_type: The module type to initialize
        """
        logger.info(f"Initializing module: {module_type.name}")

        if module_type == ModuleType.MARKET_DATA:
            exchange_id = os.getenv("SIGNAL_EXCHANGE_ID", "bybit").strip().lower()
            self.ohlcv_fetcher = OHLCVFetcher(
                exchange_adapter=CCXTAdapter(exchange_id=exchange_id)
            )
            self._modules[module_type] = {
                "name": module_type.name,
                "loaded": True,
                "healthy": True,
                "instance": "OHLCVFetcher",
                "initialized_at": datetime.now(UTC).isoformat(),
            }

        elif module_type == ModuleType.SIGNAL_GENERATOR:
            self.signal_generator = SignalGenerator(
                config=None  # Uses default config with 75% threshold
            )
            self._modules[module_type] = {
                "name": module_type.name,
                "loaded": True,
                "healthy": True,
                "instance": "SignalGenerator",
                "initialized_at": datetime.now(UTC).isoformat(),
            }

        elif module_type == ModuleType.PAPER_EXECUTOR:
            executor_mode = (
                os.getenv("PAPER_ORDER_EXECUTOR", "simulator").strip().lower()
            )
            allow_fallback = _allow_simulator_fallback()
            bybit_requested = executor_mode == "bybit_demo"

            if bybit_requested:
                try:
                    market_data = MarketDataProvider()
                    try:
                        connector = BybitDemoConnector.from_env(market_data=market_data)
                    except TypeError:
                        connector = BybitDemoConnector.from_env()
                    if getattr(connector, "market_data", None) is None:
                        connector.market_data = market_data
                    self.order_simulator = connector
                    instance_name = "BybitDemoConnector"
                except Exception as exc:
                    if not allow_fallback:
                        await publish_execution_incident(
                            incident_type="bybit_connector_init_failure",
                            severity="P1",
                            title="Bybit demo connector initialization failed",
                            message=str(exc),
                            context={
                                "executor_mode": executor_mode,
                                "allow_simulator_fallback": allow_fallback,
                            },
                        )
                        raise RuntimeError(
                            "Bybit demo connector initialization failed and simulator fallback is disabled."
                        ) from exc
                    logger.warning(
                        "Bybit demo connector init failed (%s); using local simulator fallback",
                        exc,
                    )
                    self.order_simulator = create_simulator()
                    instance_name = "OrderSimulator"
            else:
                self.order_simulator = create_simulator()
                instance_name = "OrderSimulator"
            self.position_tracker = PaperPositionTracker()
            self._modules[module_type] = {
                "name": module_type.name,
                "loaded": True,
                "healthy": True,
                "instance": instance_name,
                "initialized_at": datetime.now(UTC).isoformat(),
            }

        elif module_type == ModuleType.RISK_MANAGER:
            risk_config = RiskCheck(
                min_confidence=self.config.signal_confidence_threshold,
                max_position_pct=self.config.max_position_size_pct,
            )
            self.risk_enforcer = PaperRiskEnforcer(config=risk_config)
            self.kill_switch = KillSwitchExecutor()
            self._modules[module_type] = {
                "name": module_type.name,
                "loaded": True,
                "healthy": True,
                "instance": "PaperRiskEnforcer",
                "initialized_at": datetime.now(UTC).isoformat(),
            }

        else:
            # Generic placeholder for other modules
            self._modules[module_type] = {
                "name": module_type.name,
                "loaded": True,
                "healthy": True,
                "initialized_at": datetime.now(UTC).isoformat(),
            }

        logger.info(f"Module {module_type.name} initialized")

    async def _initialize_paper_orchestrator(self) -> None:
        """Initialize the paper trading orchestrator."""
        if not all(
            [
                self.signal_generator,
                self.order_simulator,
                self.position_tracker,
                self.risk_enforcer,
            ]
        ):
            logger.warning("Cannot initialize orchestrator - missing dependencies")
            return

        # Create telemetry exporter (mock for now)
        try:
            exporter = ExecutionTelemetryExporter(
                influxdb_client=None,  # Will work in dry-run mode
            )
            self.telemetry_collector = ExecutionCollector(
                exporter=exporter,
                environment="paper",
            )
        except Exception as e:
            logger.warning(f"Failed to create telemetry collector: {e}")
            self.telemetry_collector = None

        # Create outcome capture integration for Discord alerts
        outcome_capture = OutcomeCaptureIntegration()

        # Create signal consumer to bridge Redis signals to orchestrator
        # Note: SignalConsumer will be started when orchestrator.start() is called
        signal_consumer = SignalConsumer(
            orchestrator=None,  # Will be set below
            poll_interval=5.0,  # Poll every 5 seconds
        )

        self.paper_orchestrator = PaperTradingOrchestrator(
            signal_generator=self.signal_generator,
            order_simulator=self.order_simulator,
            position_tracker=self.position_tracker,
            risk_enforcer=self.risk_enforcer,
            telemetry_collector=self.telemetry_collector,
            kill_switch=self.kill_switch,
            portfolio_value=self.config.paper_portfolio_value,
            outcome_capture=outcome_capture,
            signal_consumer=signal_consumer,
        )

        # Wire the orchestrator to the signal consumer
        signal_consumer.orchestrator = self.paper_orchestrator

        await self.paper_orchestrator.start()
        logger.info(
            "Paper trading orchestrator initialized and started with SignalConsumer"
        )

    async def shutdown(self) -> None:
        """Shutdown all modules gracefully."""
        logger.info("Shutting down TradingModeLoader...")
        self._running = False
        self._shutdown_event.set()

        # Stop paper orchestrator if running
        if self.paper_orchestrator:
            try:
                await self.paper_orchestrator.stop()
                logger.info("Paper orchestrator stopped")
            except Exception as e:
                logger.error(f"Error stopping paper orchestrator: {e}")

        # Shutdown modules in reverse order
        for module_type, module in reversed(list(self._modules.items())):
            try:
                logger.info(f"Shutting down module: {module_type.name}")
                module["healthy"] = False
                module["shutdown_at"] = datetime.now(UTC).isoformat()
            except Exception as e:
                logger.error(f"Error shutting down {module_type.name}: {e}")

        logger.info("Shutdown complete")

    def get_module_status(self) -> dict[str, Any]:
        """Get status of all loaded modules.

        Returns:
            Dictionary with module status information
        """
        return {
            "mode": self.config.mode.name,
            "running": self._running,
            "modules": {
                module_type.name: status
                for module_type, status in self._modules.items()
            },
            "uptime_seconds": self._get_uptime_seconds(),
        }

    def _get_uptime_seconds(self) -> float:
        """Calculate uptime in seconds."""
        if self._start_time is None:
            return 0.0
        return (datetime.now(UTC) - self._start_time).total_seconds()

    def is_running(self) -> bool:
        """Check if the loader is running.

        Returns:
            True if running, False otherwise
        """
        return self._running

    async def wait_for_shutdown(self) -> None:
        """Wait for shutdown signal."""
        await self._shutdown_event.wait()


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description="Run trading activity in various modes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run paper trading for 30 minutes (default)
    python scripts/run_trading_activity.py --mode paper
    
    # Run backtest with custom config
    python scripts/run_trading_activity.py --mode backtest --config config.yaml
    
    # Run live trading with higher confidence threshold
    python scripts/run_trading_activity.py --mode live --confidence-threshold 0.85
    
    # Dry run mode for testing without execution
    python scripts/run_trading_activity.py --mode dry_run --duration 300
        """,
    )

    parser.add_argument(
        "--mode",
        type=str,
        choices=["paper", "live", "backtest", "dry_run"],
        default="paper",
        help="Trading mode to run (default: paper)",
    )

    parser.add_argument(
        "--duration",
        type=int,
        default=1800,
        help="Duration to run in seconds (default: 1800 = 30 minutes)",
    )

    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to configuration file (optional)",
    )

    parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=0.75,
        help="Minimum confidence threshold for signals (default: 0.75)",
    )

    parser.add_argument(
        "--portfolio-value",
        type=float,
        default=10000.0,
        help="Starting portfolio value for paper trading (default: 10000.0)",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    return parser.parse_args()


def create_config_from_args(args: argparse.Namespace) -> TradingModeConfig:
    """Create TradingModeConfig from command line arguments.

    Args:
        args: Parsed command line arguments

    Returns:
        Configured TradingModeConfig instance
    """
    mode_map = {
        "paper": TradingMode.PAPER,
        "live": TradingMode.LIVE,
        "backtest": TradingMode.BACKTEST,
        "dry_run": TradingMode.DRY_RUN,
    }

    mode = mode_map[args.mode]

    if mode == TradingMode.PAPER:
        config = TradingModeConfig.create_paper_config(
            portfolio_value=args.portfolio_value,
            signal_threshold=args.confidence_threshold,
        )
    elif mode == TradingMode.BACKTEST:
        config = TradingModeConfig.create_backtest_config(
            signal_threshold=args.confidence_threshold,
        )
    elif mode == TradingMode.DRY_RUN:
        config = TradingModeConfig.create_dry_run_config(
            signal_threshold=args.confidence_threshold,
        )
    else:  # LIVE mode
        config = TradingModeConfig(
            mode=TradingMode.LIVE,
            enabled_modules={
                ModuleType.SIGNAL_GENERATOR,
                ModuleType.RISK_MANAGER,
                ModuleType.MARKET_DATA,
            },
            signal_confidence_threshold=args.confidence_threshold,
        )

    # Load additional config from file if provided
    if args.config and Path(args.config).exists():
        logger.info(f"Loading additional config from: {args.config}")
        # In production, this would merge file config with CLI args

    return config


async def collect_metrics_snapshot(
    loader: TradingModeLoader,
    metrics: TradingActivityMetrics,
) -> dict[str, Any]:
    """Collect a metrics snapshot.

    Args:
        loader: TradingModeLoader instance
        metrics: Current metrics object

    Returns:
        Dictionary with snapshot data
    """
    module_status = loader.get_module_status()

    snapshot = {
        "timestamp": datetime.now(UTC).isoformat(),
        "uptime_seconds": module_status.get("uptime_seconds", 0),
        "signals_generated": metrics.signals_generated,
        "paper_trades_opened": metrics.paper_trades_opened,
        "paper_trades_closed": metrics.paper_trades_closed,
        "risk_gate_checks_executed": metrics.risk_gate_checks_executed,
        "module_status": module_status,
    }

    return snapshot


async def run_trading_loop(
    loader: TradingModeLoader,
    metrics: TradingActivityMetrics,
    duration_seconds: int,
) -> None:
    """Run the main trading loop with periodic metrics collection.

    Args:
        loader: TradingModeLoader instance
        metrics: Metrics tracking object
        duration_seconds: How long to run
    """
    start_time = time.time()
    last_metrics_log = start_time
    metrics_interval = 60  # Log every 60 seconds

    run_forever = duration_seconds <= 0
    if run_forever:
        logger.info("Starting trading loop with no duration limit")
    else:
        logger.info(f"Starting trading loop for {duration_seconds} seconds...")

    while loader.is_running():
        current_time = time.time()
        elapsed = current_time - start_time

        # Check if duration exceeded
        if not run_forever and elapsed >= duration_seconds:
            logger.info(f"Duration limit ({duration_seconds}s) reached")
            break

        # Collect and log metrics every 60 seconds
        if current_time - last_metrics_log >= metrics_interval:
            snapshot = await collect_metrics_snapshot(loader, metrics)
            metrics.snapshots.append(snapshot)

            logger.info(
                f"[Metrics] Uptime: {elapsed:.0f}s | "
                f"Signals: {metrics.signals_generated} | "
                f"Trades Opened: {metrics.paper_trades_opened} | "
                f"Trades Closed: {metrics.paper_trades_closed} | "
                f"Risk Checks: {metrics.risk_gate_checks_executed}"
            )

            last_metrics_log = current_time

        # Execute actual trading activity
        await _execute_trading_cycle(loader, metrics)

        await asyncio.sleep(1)  # 1-second iteration cycle

    logger.info("Trading loop completed")


async def _execute_trading_cycle(
    loader: TradingModeLoader,
    metrics: TradingActivityMetrics,
) -> None:
    """Execute a single trading cycle.

    Performs the core trading workflow:
    1. Fetch market data
    2. Generate signals
    3. Validate risk constraints
    4. Execute paper trades (if applicable)
    5. Update metrics

    Args:
        loader: TradingModeLoader with initialized components
        metrics: Metrics tracking object to update
    """
    try:
        # Only run trading cycle in PAPER mode with orchestrator
        if loader.config.mode != TradingMode.PAPER:
            return

        if not loader.paper_orchestrator:
            return

        # Get components
        fetcher = loader.ohlcv_fetcher
        generator = loader.signal_generator
        orchestrator = loader.paper_orchestrator

        if fetcher is None or generator is None:
            return

        # Trading parameters from deployment configuration
        symbols_raw = os.getenv("TRADING_SYMBOLS", "BTC/USDT")
        symbols = [s.strip() for s in symbols_raw.split(",") if s.strip()]
        timeframe_raw = os.getenv("TRADING_TIMEFRAME", "1h").strip().lower()
        timeframe = {
            "1m": Timeframe.MINUTE_1,
            "5m": Timeframe.MINUTE_5,
            "15m": Timeframe.MINUTE_15,
            "1h": Timeframe.HOUR_1,
            "4h": Timeframe.HOUR_4,
            "1d": Timeframe.DAY_1,
        }.get(timeframe_raw, Timeframe.HOUR_1)

        eval_interval_seconds = int(os.getenv("SYMBOL_EVAL_INTERVAL_SECONDS", "300"))
        if not hasattr(loader, "_last_symbol_eval_ts"):
            loader._last_symbol_eval_ts = {}
        now_ts = time.time()
        due_symbols = []
        for symbol in symbols:
            last_ts = loader._last_symbol_eval_ts.get(symbol.upper(), 0.0)
            if (now_ts - last_ts) >= eval_interval_seconds:
                due_symbols.append(symbol)

        if not due_symbols:
            return

        for symbol in due_symbols:
            # Gate to at most one full evaluation per symbol per interval.
            loader._last_symbol_eval_ts[symbol.upper()] = now_ts

            # Step 1: Fetch market data
            try:
                ohlcv_data = await fetcher.fetch(
                    symbol=symbol,
                    timeframe=timeframe,
                    limit=100,  # Last 100 candles
                )
                if not ohlcv_data:
                    logger.debug("No OHLCV data fetched for %s", symbol)
                    continue
            except Exception as e:
                logger.debug(f"Failed to fetch OHLCV data for {symbol}: {e}")
                continue

            # Step 2: Generate signals
            try:
                current_price = ohlcv_data[-1].close_price if ohlcv_data else None
                signal = generator.generate_signal(
                    token=symbol,
                    timeframe=timeframe,
                    ohlcv_data=ohlcv_data,
                    current_price=current_price,
                )
                metrics.signals_generated += 1
                logger.debug(
                    f"Signal generated: {symbol} {signal.direction.value} "
                    f"confidence={signal.confidence:.2%}"
                )
            except Exception as e:
                logger.debug(f"Signal generation failed for {symbol}: {e}")
                continue

            # Step 3: Run risk check (count even if no actionable signal)
            metrics.risk_gate_checks_executed += 1

            # Step 4: Only process actionable signals
            if signal.status != SignalStatus.ACTIONABLE:
                logger.debug(
                    f"Signal not actionable for {symbol}: {signal.status.value}"
                )
                continue

            if signal.confidence < loader.config.signal_confidence_threshold:
                logger.debug(
                    f"Signal below threshold for {symbol}: {signal.confidence:.2%} < "
                    f"{loader.config.signal_confidence_threshold:.2%}"
                )
                continue

            # Step 5: Execute paper trade via orchestrator
            try:
                if orchestrator.order_simulator and hasattr(
                    orchestrator.order_simulator, "set_market_price"
                ):
                    current_price = ohlcv_data[-1].close_price if ohlcv_data else None
                    if current_price is None:
                        logger.warning(
                            "No valid price for %s, skipping set_market_price "
                            "(mock price injection prevented)",
                            symbol,
                        )
                    else:
                        orchestrator.order_simulator.set_market_price(
                            symbol, current_price
                        )
                        logger.debug(f"Set market price for {symbol}: {current_price}")
                elif (
                    orchestrator.order_simulator
                    and hasattr(orchestrator.order_simulator, "market_data")
                    and getattr(orchestrator.order_simulator, "market_data", None)
                    is not None
                    and hasattr(orchestrator.order_simulator.market_data, "set_price")
                ):
                    current_price = ohlcv_data[-1].close_price if ohlcv_data else None
                    if current_price is None:
                        logger.warning(
                            "No valid price for %s, skipping set_market_price "
                            "(mock price injection prevented)",
                            symbol,
                        )
                    else:
                        orchestrator.order_simulator.market_data.set_price(
                            symbol, current_price
                        )
                        logger.debug(
                            f"Set connector market_data price for {symbol}: {current_price}"
                        )

                initial_closed = 0
                if orchestrator.position_tracker:
                    try:
                        closed_positions = (
                            await orchestrator.position_tracker.get_closed_positions()
                        )
                        initial_closed = len(closed_positions)
                    except Exception:
                        initial_closed = 0

                process_result = orchestrator.process_signal(signal)
                if inspect.isawaitable(process_result):
                    result = await process_result
                else:
                    result = process_result

                if result.status.value == "executed":
                    metrics.paper_trades_opened += 1
                    logger.info(
                        f"Paper trade executed: {symbol} {signal.direction.value} "
                        f"confidence={signal.confidence:.2%}"
                    )
                elif result.status.value == "rejected":
                    logger.debug(
                        f"Signal rejected by risk gate: {result.reject_reason}"
                    )

                if orchestrator.position_tracker:
                    try:
                        final_closed_positions = (
                            await orchestrator.position_tracker.get_closed_positions()
                        )
                        final_closed = len(final_closed_positions)
                        newly_closed = final_closed - initial_closed
                        if newly_closed > 0:
                            metrics.paper_trades_closed += newly_closed
                            logger.info(f"Closed {newly_closed} position(s)")
                    except Exception as e:
                        logger.debug(f"Failed to check closed positions: {e}")

            except Exception as e:
                logger.warning(f"Failed to execute paper trade for {symbol}: {e}")

    except Exception as e:
        logger.error(f"Error in trading cycle: {e}", exc_info=True)
        # Don't crash the loop on errors


def generate_report(
    args: argparse.Namespace,
    metrics: TradingActivityMetrics,
    loader: TradingModeLoader,
) -> dict[str, Any]:
    """Generate final trading activity report.

    Args:
        args: Command line arguments
        metrics: Collected metrics
        loader: TradingModeLoader instance

    Returns:
        Report dictionary
    """
    end_time = datetime.now(UTC)
    duration = (end_time - metrics.start_time).total_seconds()

    # Determine final verdict based on activity
    if metrics.signals_generated > 0:
        if metrics.paper_trades_opened > 0:
            verdict = "ACTIVE_TRADING"
        else:
            verdict = "SIGNALS_ONLY"
    else:
        verdict = "NO_ACTIVITY"

    report = {
        "report_type": "trading_activity",
        "generated_at": end_time.isoformat(),
        "duration_seconds": duration,
        "mode": args.mode,
        "configuration": {
            "confidence_threshold": args.confidence_threshold,
            "portfolio_value": args.portfolio_value,
            "config_file": args.config,
        },
        "metrics": {
            "signals_generated": metrics.signals_generated,
            "trades_opened": metrics.paper_trades_opened,
            "trades_closed": metrics.paper_trades_closed,
            "risk_checks": metrics.risk_gate_checks_executed,
        },
        "provider_usage": metrics.provider_usage,
        "module_status": loader.get_module_status(),
        "final_verdict": verdict,
        "snapshots": metrics.snapshots,
    }

    return report


def save_report(report: dict[str, Any]) -> Path:
    """Save report to JSON file.

    Args:
        report: Report dictionary

    Returns:
        Path to saved report file
    """
    output_dir = Path("_bmad-output")
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    filename = f"trading-activity-report-{timestamp}.json"
    filepath = output_dir / filename

    with open(filepath, "w") as f:
        json.dump(report, f, indent=2)

    logger.info(f"Report saved to: {filepath}")
    return filepath


async def main() -> int:
    """Main entry point for trading activity runner.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    # Parse arguments
    args = parse_arguments()

    # Configure logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Bootstrap environment
    logger.info("Bootstrapping environment...")
    bootstrap(load_env=True, verbose=args.verbose)

    # Create configuration
    logger.info(f"Creating configuration for mode: {args.mode}")
    config = create_config_from_args(args)

    # Validate configuration
    validation_errors = config.get_validation_errors()
    if validation_errors:
        logger.error("Configuration validation failed:")
        for error in validation_errors:
            logger.error(f"  - {error}")
        return 1

    # Create loader
    loader = TradingModeLoader(config)

    # Initialize metrics
    metrics = TradingActivityMetrics()

    # Setup signal handlers for graceful shutdown
    loop = asyncio.get_event_loop()

    def signal_handler(sig: int, frame: Any) -> None:
        """Handle shutdown signals."""
        sig_name = signal.Signals(sig).name
        logger.info(f"Received {sig_name}, initiating graceful shutdown...")
        asyncio.create_task(loader.shutdown())

    # Register signal handlers
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler, sig, None)

    try:
        # Load modules
        logger.info("Loading trading modules...")
        if not await loader.load():
            logger.error("Failed to load modules")
            return 1

        # Run trading loop
        await run_trading_loop(loader, metrics, args.duration)

    except asyncio.CancelledError:
        logger.info("Trading loop cancelled")
    except Exception as e:
        logger.error(f"Error during trading activity: {e}", exc_info=True)
        return 1
    finally:
        # Ensure shutdown is called
        await loader.shutdown()

    # Generate and save report
    logger.info("Generating final report...")
    report = generate_report(args, metrics, loader)
    report_path = save_report(report)

    # Print summary
    print("\n" + "=" * 60)
    print("TRADING ACTIVITY SUMMARY")
    print("=" * 60)
    print(f"Mode: {args.mode}")
    print(f"Duration: {report['duration_seconds']:.1f} seconds")
    print(f"Signals Generated: {metrics.signals_generated}")
    print(f"Trades Opened: {metrics.paper_trades_opened}")
    print(f"Trades Closed: {metrics.paper_trades_closed}")
    print(f"Risk Checks: {metrics.risk_gate_checks_executed}")
    print(f"Final Verdict: {report['final_verdict']}")
    print(f"Report: {report_path}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
