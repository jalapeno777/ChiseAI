"""Paper Trading Orchestrator.

Connects all paper trading components into an end-to-end workflow:
signal → risk validation → order placement → position tracking → metrics export.

Targets:
- Signal → Order placement: <500ms
- Order fill simulation: <200ms
- Position tracking update: <100ms
- Total pipeline: <2 seconds
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import json
import logging
import os
import time
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from discord_alerts.trade_notifier import TradeNotifier
    from execution.kill_switch.executor import KillSwitchExecutor
    from execution.llm.trade_decision_enhancer import TradeDecisionEnhancer
    from execution.paper.models import PaperOrder, PaperTradeResult
    from execution.paper.order_simulator import OrderSimulator
    from execution.paper.risk_enforcer import PaperRiskEnforcer
    from execution.paper.signal_consumer import SignalConsumer
    from execution.paper.trade_journal import TradeJournal
    from execution.paper.trade_journal_service import TradeJournalService
    from execution.telemetry.collector import ExecutionCollector
    from portfolio.paper_tracker import PaperPositionTracker
    from signal_generation.models import Signal
    from signal_generation.signal_generator import SignalGenerator

from execution.llm.trade_decision_enhancer import TradeDecisionEnhancer
from execution.paper.canary_metrics import CanaryMetrics
from execution.paper.models import (
    OrderSide,
    OrderState,
    OrderType,
    PaperOrder,
    PaperTradeResult,
    TradeStatus,
)
from execution.paper.paper_kill_switch import (
    PaperKillSwitchManager,
)
from execution.paper.reason_codes import (
    ReasonCodeMapper,
)
from execution.paper.trade_journal import TradeJournal
from execution.paper.trade_journal_persistence import TradeJournalRedisPersistence
from execution.paper.trade_journal_service import TradeJournalService
from execution.reconciliation.service import (
    OutcomeReconciliationService,
    ReconciliationMonitor,
)
from ml.feedback.bybit_fill_listener import BybitFillListener, BybitListenerConfig
from ml.models.signal_outcome import SignalOutcome, SignalOutcomeStatus

logger = logging.getLogger(__name__)


class PaperTradingOrchestrator:
    """Orchestrates the end-to-end paper trading workflow.

    Pipeline:
    1. Consume signal from SignalGenerator
    2. Validate via RiskEnforcer
    3. Calculate position size
    4. Place order via OrderSimulator
    5. Track position on fill
    6. Export metrics to telemetry
    7. Check kill-switch conditions

    Attributes:
        signal_generator: Source of trading signals
        order_simulator: Simulates order placement and fills
        position_tracker: Tracks open positions
        risk_enforcer: Validates orders against risk limits
        telemetry: Collects and exports execution metrics
        kill_switch: Emergency position closure
        portfolio_value: Current portfolio value
        running: Whether the orchestrator is active
    """

    # Latency targets in milliseconds
    TARGET_SIGNAL_TO_ORDER_MS = 500
    TARGET_FILL_SIMULATION_MS = 200
    TARGET_POSITION_UPDATE_MS = 100
    TARGET_TOTAL_PIPELINE_MS = 2000

    # Health key configuration
    HEALTH_KEY = "paper:orchestrator:health"
    HEALTH_TTL_SECONDS = 120

    def __init__(
        self,
        signal_generator: SignalGenerator,
        order_simulator: OrderSimulator,
        position_tracker: PaperPositionTracker,
        risk_enforcer: PaperRiskEnforcer,
        telemetry_collector: ExecutionCollector,
        kill_switch: KillSwitchExecutor,
        portfolio_value: float = 10000.0,
        trade_notifier: TradeNotifier | None = None,
        signal_consumer: SignalConsumer | None = None,
        outcome_capture: Any | None = None,
        decision_enhancer: TradeDecisionEnhancer | None = None,
        trade_journal: TradeJournal | None = None,
        symbol_registry: Any | None = None,
        trade_journal_persistence: TradeJournalRedisPersistence | None = None,
        session_id: str | None = None,
        redis_client: Any | None = None,
        paper_kill_switch: PaperKillSwitchManager | None = None,
    ):
        """Initialize paper trading orchestrator.

        Args:
            signal_generator: Source of trading signals
            order_simulator: Order simulation engine
            position_tracker: Position tracking
            risk_enforcer: Risk validation
            telemetry_collector: Metrics collection
            kill_switch: Emergency kill switch
            portfolio_value: Starting portfolio value
            trade_notifier: Optional Discord trade notifier for alerts
            signal_consumer: Optional SignalConsumer for Redis signal bridge
            decision_enhancer: Optional TradeDecisionEnhancer for LLM-enhanced decisions
            trade_journal: Optional TradeJournal for trade lifecycle tracking
            symbol_registry: Optional SymbolPositionRegistry for symbol-level locking
            trade_journal_persistence: Optional persistence layer for trade journal
            session_id: Optional session ID for journal recovery
            redis_client: Optional Redis client for health key writes
            paper_kill_switch: Optional PaperKillSwitchManager for paper trading kill switch.
        """
        self.signal_generator = signal_generator
        self.order_simulator = order_simulator
        self.position_tracker = position_tracker
        self.risk_enforcer = risk_enforcer
        self.telemetry = telemetry_collector
        self.kill_switch = kill_switch
        self.portfolio_value = portfolio_value
        self.trade_notifier = trade_notifier
        self._signal_consumer = signal_consumer
        self.outcome_capture = outcome_capture
        self.decision_enhancer = decision_enhancer or TradeDecisionEnhancer()
        self.symbol_registry = symbol_registry
        self._redis = redis_client
        self._paper_kill_switch = paper_kill_switch

        # Optional BybitFillListener for async fill notifications (polling-first fallback)
        self._fill_listener: BybitFillListener | None = None
        self._fill_listener_redis: Any | None = redis_client

        # ST-FILL-004: ReconciliationMonitor for safety net reconciliation (alert-only)
        self._reconciliation_monitor: ReconciliationMonitor | None = None

        # PAPER-FORENSIC-001: Extract and store connector provenance
        self._connector_provenance = self._extract_connector_provenance(order_simulator)
        logger.info(
            f"[ORCHESTRATOR-INIT] Connector provenance: {self._connector_provenance}"
        )

        # PAPER-FORENSIC-001: Update outcome_capture with extracted provenance
        # This ensures SignalOutcome records get populated with correct venue/mode/source
        if self.outcome_capture and hasattr(
            self.outcome_capture, "set_connector_provenance"
        ):
            self.outcome_capture.set_connector_provenance(self._connector_provenance)
            logger.info(
                f"[ORCHESTRATOR-INIT] Updated outcome_capture with provenance: "
                f"{self._connector_provenance}"
            )

        # Initialize trade journal service if trade_journal is provided
        self.trade_journal_service: TradeJournalService | None = None
        self.trade_journal: TradeJournal | None = None

        if trade_journal_persistence is not None:
            # Create TradeJournalService with persistence layer
            self.trade_journal_service = TradeJournalService(
                session_id=session_id,
                persistence=trade_journal_persistence,
            )
            # If existing journal provided, copy entries to service
            if trade_journal is not None:
                for entry in trade_journal.get_all_entries():
                    self.trade_journal_service.journal._entries[entry.entry_id] = entry
            # Attempt recovery if session_id is provided
            if session_id:
                recovered = self.trade_journal_service.recover(session_id)
                if recovered:
                    logger.info(f"Recovered trade journal for session {session_id}")
            self.trade_journal = self.trade_journal_service.journal
        elif trade_journal is not None:
            # Use existing journal directly (backward compatibility)
            self.trade_journal = trade_journal

        self._running = False
        self._signal_queue: asyncio.Queue[Signal] = asyncio.Queue()
        self._processing_task: asyncio.Task | None = None
        self._metrics: dict[str, Any] = {
            "signals_processed": 0,
            "trades_executed": 0,
            "trades_rejected": 0,
            "trades_failed": 0,
            "total_latency_ms": 0.0,
            "avg_latency_ms": 0.0,
            # Per-gate rejection counters (DEBUG)
            "gate_g1_throttle_count": 0,
            "gate_g2_paper_kill_count": 0,
            "gate_g3_live_kill_count": 0,
            "gate_g4_no_price_count": 0,
            "gate_g5_risk_reject_count": 0,
            "gate_g6_llm_reject_count": 0,
            "gate_g7_same_dir_skip_count": 0,
            "gate_g8_order_not_filled_count": 0,
            "gate_g9_exception_count": 0,
        }
        self._symbol_eval_interval_seconds = max(
            0, int(os.getenv("SYMBOL_EVAL_INTERVAL_SECONDS", "300"))
        )
        self._last_symbol_processed_ts: dict[tuple[str, str], float] = {}
        self._lock = asyncio.Lock()
        self._position_locks: dict[str, asyncio.Lock] = {}

        # PT-FIX-2: Minimum hold period and debouncing for opposite-signal closes
        self._min_hold_seconds = int(os.getenv("MIN_HOLD_SECONDS", "300"))
        self._opposite_signal_count: dict[str, int] = {}  # keyed by position_id

        # PT-FIX-3: SL/TP monitoring loop
        self._sltp_task: asyncio.Task | None = None
        self._sltp_poll_interval = int(os.getenv("SLTP_POLL_INTERVAL", "20"))
        self._sltp_last_price: dict[str, tuple[float, float]] = (
            {}
        )  # symbol -> (price, timestamp)
        self._sltp_stats = {"positions_checked": 0, "triggers_executed": 0}

        # G-EXIT-24H: Canary metrics for tracking position closes
        self._canary_metrics = CanaryMetrics(redis_client=redis_client)

        logger.info(
            f"PaperTradingOrchestrator initialized: portfolio=${portfolio_value:.2f}"
        )

    def _get_position_lock(self, position_id: str) -> asyncio.Lock:
        """Get or create an asyncio.Lock for a specific position.

        Used to prevent race conditions between the SL/TP monitoring loop
        and signal processing when both attempt to close the same position
        concurrently.
        """
        if position_id not in self._position_locks:
            self._position_locks[position_id] = asyncio.Lock()
        return self._position_locks[position_id]

    def _extract_connector_provenance(self, order_simulator: Any) -> dict[str, str]:
        """Extract provenance information from the order simulator/connector.

        PAPER-FORENSIC-001: Extracts venue, mode, and source from the connector
        to populate SignalOutcome provenance fields.

        Args:
            order_simulator: The order simulator or connector instance

        Returns:
            Dictionary with execution_venue, execution_mode, execution_source
        """
        # Default provenance (fallback)
        provenance = {
            "execution_venue": "unknown",
            "execution_mode": "unknown",
            "execution_source": "unknown",
        }

        # Check if it's a BybitDemoConnector
        if hasattr(order_simulator, "get_provenance"):
            # BybitDemoConnector has get_provenance() method
            try:
                prov = order_simulator.get_provenance()
                provenance = {
                    "execution_venue": "bybit_demo",
                    "execution_mode": "demo",
                    "execution_source": "bybit_demo_connector",
                    "endpoint": getattr(prov, "endpoint", "unknown"),
                    "api_key_prefix": getattr(prov, "api_key_prefix", "****"),
                }
                logger.info(
                    f"[PROVENANCE-EXTRACT] BybitDemoConnector detected: {provenance}"
                )
            except Exception as e:
                logger.warning(
                    f"[PROVENANCE-EXTRACT] Failed to extract BybitDemoConnector provenance: {e}"
                )
                provenance = {
                    "execution_venue": "bybit_demo",
                    "execution_mode": "demo",
                    "execution_source": "bybit_demo_connector",
                }
        elif type(order_simulator).__name__ == "OrderSimulator":
            # OrderSimulator (local simulation)
            provenance = {
                "execution_venue": "local_sim",
                "execution_mode": "paper",
                "execution_source": "order_simulator",
            }
            logger.info(f"[PROVENANCE-EXTRACT] OrderSimulator detected: {provenance}")
        else:
            # Unknown connector type - log for debugging
            logger.warning(
                f"[PROVENANCE-EXTRACT] Unknown connector type: {type(order_simulator).__name__}. "
                f"Using default provenance."
            )

        return provenance

    def get_connector_provenance(self) -> dict[str, str]:
        """Get the connector provenance information.

        PAPER-FORENSIC-001: Runtime verification of connector type and provenance.

        Returns:
            Dictionary with execution_venue, execution_mode, execution_source
        """
        return self._connector_provenance.copy()

    async def _update_health(self, status: str = "running") -> None:
        """Update health key in Redis with current orchestrator status.

        Writes a JSON payload to ``paper:orchestrator:health`` with a 120s TTL.
        The payload includes status, ISO-8601 timestamp, and processed signal count.

        Args:
            status: Current status string (``"running"`` or ``"stopped"``).
        """
        if self._redis is None:
            return
        try:
            payload = json.dumps(
                {
                    "status": status,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "processed_count": self._metrics.get("signals_processed", 0),
                }
            )
            await self._redis.setex(self.HEALTH_KEY, self.HEALTH_TTL_SECONDS, payload)
        except Exception:
            logger.debug("Failed to update orchestrator health key", exc_info=True)

    def _emit_gate_outcomes(
        self,
        assessment: Any,
        signal: Any,
        correlation_id: str,
    ) -> None:
        """Emit per-gate outcome metrics for observability.

        Extracts pass/fail outcomes for each named gate (risk, signal_quality,
        confidence) from the risk assessment and emits structured log lines.

        Args:
            assessment: RiskAssessment from risk_enforcer.validate_order().
            signal: Original Signal being processed.
            correlation_id: Correlation ID for tracing.
        """
        violation_rules = {v.rule for v in assessment.violations}

        # Risk gate: overall assessment approval
        risk_reason = (
            "; ".join(v.message for v in assessment.violations)
            if assessment.violations
            else "no_violations"
        )
        logger.info(
            f"gate_outcome gate=risk outcome={'pass' if assessment.approved else 'fail'} "
            f"reason={risk_reason} correlation_id={correlation_id}"
        )

        # Confidence gate: pass if no confidence violation
        if "confidence" in violation_rules:
            conf_reason = next(
                v.message for v in assessment.violations if v.rule == "confidence"
            )
            logger.info(
                f"gate_outcome gate=confidence outcome=fail "
                f"reason={conf_reason} correlation_id={correlation_id}"
            )
        else:
            logger.info(
                f"gate_outcome gate=confidence outcome=pass "
                f"reason=confidence={signal.confidence:.2%} correlation_id={correlation_id}"
            )

        # Signal quality gate: pass if no blocking violations
        blocking_rules = {
            v.rule for v in assessment.violations if v.severity == "block"
        }
        if blocking_rules:
            logger.info(
                f"gate_outcome gate=signal_quality outcome=fail "
                f"reason=blocking_violations={sorted(blocking_rules)} "
                f"correlation_id={correlation_id}"
            )
        else:
            logger.info(
                f"gate_outcome gate=signal_quality outcome=pass "
                f"reason=no_blocking_violations correlation_id={correlation_id}"
            )

    async def _get_paper_kill_switch(self) -> PaperKillSwitchManager | None:
        """Get or create PaperKillSwitchManager.

        Note: Does NOT pass self._redis to the manager because the orchestrator's
        Redis client may be synchronous (used for health keys), while
        PaperKillSwitchManager requires an async client. The manager creates
        its own async connection when needed.

        Returns:
            PaperKillSwitchManager instance or None if not configured
        """
        if self._paper_kill_switch is None:
            self._paper_kill_switch = PaperKillSwitchManager()
        return self._paper_kill_switch

    async def start(self) -> None:
        """Start the orchestrator and begin processing signals."""
        self._running = True

        # Start telemetry collector
        if self.telemetry:
            await self.telemetry.start()

        # Start signal processing loop
        self._processing_task = asyncio.create_task(self._processing_loop())

        # Start signal consumer if provided
        if self._signal_consumer:
            logger.info("Starting signal consumer...")
            await self._signal_consumer.start()
            logger.info("Signal consumer started successfully")
        else:
            logger.warning(
                "No signal consumer configured - Redis signal bridge disabled"
            )

        # Write initial health key
        await self._update_health("running")

        # Start BybitFillListener if feature flag is enabled (polling-first fallback)
        if os.getenv("BYBIT_FILL_LISTENER_ENABLED", "false").lower() == "true":
            try:
                await self.start_fill_listener()
            except Exception as e:
                logger.error(f"Failed to start BybitFillListener: {e}")
        else:
            logger.debug(
                "BybitFillListener disabled (BYBIT_FILL_LISTENER_ENABLED != true)"
            )

        # ST-FILL-004: Start ReconciliationMonitor if feature flag is enabled (alert-only)
        await self._start_reconciliation_monitor()

        # PT-FIX-3: Start SL/TP monitoring loop
        self._sltp_task = asyncio.create_task(self._sltp_monitoring_loop())
        logger.info(
            "SL/TP monitoring loop started (poll_interval=%ds)",
            self._sltp_poll_interval,
        )

        logger.info("PaperTradingOrchestrator started")

    async def _start_reconciliation_monitor(self) -> None:
        """Start the reconciliation monitor if enabled by feature flag.

        ST-FILL-004: The ReconciliationMonitor runs OutcomeReconciliationService
        on a schedule and emits alerts when discrepancies exceed thresholds.
        Alert-only policy: NEVER auto-closes positions or triggers liquidation.

        The monitor respects:
        - reconciliation_monitor_enabled: Overall enable/disable
        - reconciliation_check_interval_seconds: How often to run checks
        - reconciliation_auto_backfill: Whether to backfill missed fills
        """
        from src.config.feature_flags import get_feature_flags

        flags = get_feature_flags()

        # Check if reconciliation monitor is enabled
        if not flags.is_reconciliation_monitor_enabled():
            logger.debug(
                "ReconciliationMonitor disabled "
                "(reconciliation_monitor_enabled != true)"
            )
            return

        # Check if already running
        if self._reconciliation_monitor is not None:
            logger.warning("ReconciliationMonitor already running")
            return

        try:
            # Create OutcomeReconciliationService with orchestrator's telemetry
            reconciliation_service = OutcomeReconciliationService(
                telemetry_exporter=self.telemetry,
                redis_client=self._redis,
            )

            # Create ReconciliationMonitor with feature-flag-configured interval and backfill
            check_interval = flags.get_reconciliation_check_interval_seconds()
            backfill_enabled = flags.is_reconciliation_auto_backfill_enabled()

            self._reconciliation_monitor = ReconciliationMonitor(
                reconciliation_service=reconciliation_service,
                redis_client=self._redis,
                check_interval_seconds=check_interval,
                backfill_enabled=backfill_enabled,
            )

            await self._reconciliation_monitor.start()
            logger.info(
                f"ReconciliationMonitor started with check interval={check_interval}s, "
                f"backfill={'enabled' if backfill_enabled else 'disabled'}"
            )

        except Exception as e:
            logger.error(f"Failed to start ReconciliationMonitor: {e}")
            self._reconciliation_monitor = None

    async def start_fill_listener(
        self, config: BybitListenerConfig | None = None
    ) -> None:
        """Start the Bybit fill listener for async fill notifications.

        This is a polling-first fallback: the listener provides async notifications
        when fills occur outside the normal polling cycle.

        Args:
            config: Optional listener configuration. If not provided, reads from
                environment variables BYBIT_DEMO_API_KEY and BYBIT_DEMO_API_SECRET.
        """
        if self._fill_listener is not None:
            logger.warning("Fill listener already running")
            return

        if config is None:
            config = BybitListenerConfig(
                api_key=os.getenv("BYBIT_DEMO_API_KEY", ""),
                api_secret=os.getenv("BYBIT_DEMO_API_SECRET", ""),
            )

        self._fill_listener = BybitFillListener(
            config=config, redis_client=self._fill_listener_redis
        )
        self._fill_listener.on_fill(self._on_bybit_fill)
        await self._fill_listener.start()
        logger.info("BybitFillListener started")

    async def _on_bybit_fill(self, outcome: SignalOutcome) -> None:
        """Handle async fill notification from BybitFillListener.

        This callback is invoked when the WebSocket listener receives a fill event.
        It updates the corresponding order state and triggers position tracking.

        Args:
            outcome: SignalOutcome from the fill event
        """
        order_id = outcome.order_id
        if not order_id:
            logger.debug("Fill callback received with no order_id")
            return

        logger.debug(
            f"Fill callback received: order_id={order_id}, "
            f"exec_id={outcome.order_id}, symbol={outcome.symbol}"
        )

        # Find the corresponding order in order_simulator
        orders = getattr(self.order_simulator, "_orders", {})
        order = orders.get(order_id)

        if not order:
            logger.debug(f"Fill callback for unknown order: {order_id}")
            return

        # Update order with fill data if not already filled
        if order.state != OrderState.FILLED:
            order.state = OrderState.FILLED
            order.filled_quantity = outcome.fill_quantity or order.quantity
            order.avg_fill_price = outcome.fill_price
            order.filled_at = outcome.fill_timestamp
            logger.info(f"Async fill applied via listener: order_id={order_id}")
        else:
            logger.debug(f"Order already filled, ignoring duplicate: {order_id}")

    async def stop(self) -> None:
        """Stop the orchestrator gracefully."""
        self._running = False

        # Cancel processing task
        if self._processing_task and not self._processing_task.done():
            self._processing_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._processing_task

        # Stop signal consumer if running
        if self._signal_consumer:
            await self._signal_consumer.stop()

        # Stop BybitFillListener if running
        if self._fill_listener is not None:
            await self._fill_listener.stop()
            self._fill_listener = None
            logger.info("BybitFillListener stopped")

        # ST-FILL-004: Stop ReconciliationMonitor if running
        if self._reconciliation_monitor is not None:
            await self._reconciliation_monitor.stop()
            self._reconciliation_monitor = None
            logger.info("ReconciliationMonitor stopped")

        # PT-FIX-3: Cancel SL/TP monitoring task
        if self._sltp_task and not self._sltp_task.done():
            self._sltp_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._sltp_task
            logger.info("SL/TP monitoring loop stopped")

        # Stop telemetry
        if self.telemetry:
            await self.telemetry.stop()

        # Delete health key on graceful stop (Option A: explicit delete)
        if self._redis is not None:
            try:
                await self._redis.delete(self.HEALTH_KEY)
            except Exception:
                logger.debug(
                    "Failed to delete orchestrator health key on stop",
                    exc_info=True,
                )

        logger.info("PaperTradingOrchestrator stopped")

    async def start_consumer(self) -> None:
        """Start the signal consumer independently.

        This allows starting the Redis signal bridge without restarting
        the entire orchestrator.
        """
        if self._signal_consumer:
            await self._signal_consumer.start()
            logger.info("Signal consumer started")
        else:
            logger.warning("No signal consumer configured")

    async def stop_consumer(self) -> None:
        """Stop the signal consumer independently.

        This allows stopping the Redis signal bridge without stopping
        the entire orchestrator.
        """
        if self._signal_consumer:
            await self._signal_consumer.stop()
            logger.info("Signal consumer stopped")
        else:
            logger.warning("No signal consumer configured")

    async def _processing_loop(self) -> None:
        """Main signal processing loop."""
        while self._running:
            try:
                # Get signal from queue with timeout
                signal = await asyncio.wait_for(self._signal_queue.get(), timeout=1.0)

                # Process signal
                result = await self.process_signal(signal)

                # Update metrics (signals_processed is incremented in process_signal)
                async with self._lock:
                    if result.status == TradeStatus.EXECUTED:
                        self._metrics["trades_executed"] += 1
                    elif result.status == TradeStatus.REJECTED:
                        self._metrics["trades_rejected"] += 1
                    elif result.status == TradeStatus.FAILED:
                        self._metrics["trades_failed"] += 1
                    # SKIPPED status doesn't increment any metric - just logged

                # Refresh health key after processing a signal
                await self._update_health("running")

            except TimeoutError:
                # No signals in queue, continue loop
                # Refresh health key to prevent TTL expiry during idle periods
                await self._update_health("running")
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in processing loop: {e}", exc_info=True)
                # Continue processing - don't crash the loop

    async def submit_signal(self, signal: Signal) -> None:
        """Submit a signal for processing.

        Args:
            signal: Trading signal to process
        """
        await self._signal_queue.put(signal)
        logger.debug(f"Signal submitted: {signal.token} {signal.direction.value}")

    async def process_signal(self, signal: Signal) -> PaperTradeResult:
        """Process a single signal through the full pipeline.

        Pipeline:
        1. Check kill-switch state
        2. Validate risk constraints
        3. Calculate position size
        4. Create and place order
        5. Track position on fill
        6. Record trade metrics

        Args:
            signal: Trading signal to process

        Returns:
            PaperTradeResult with execution details
        """
        correlation_id = str(uuid.uuid4())
        start_time = time.perf_counter()

        logger.info(
            f"Processing signal: {signal.token} {signal.direction.value} "
            f"(correlation_id={correlation_id})"
        )

        # Always count this as a processed signal
        async with self._lock:
            self._metrics["signals_processed"] += 1

        try:
            # Enforce global per-symbol-per-timeframe cadence across all ingress paths.
            symbol_key = signal.token.upper().strip()
            throttle_key = symbol_key  # Per-symbol throttle (not per-timeframe)
            if symbol_key and self._symbol_eval_interval_seconds > 0:
                now_ts = time.time()
                last_ts = self._last_symbol_processed_ts.get(throttle_key, 0.0)
                if (now_ts - last_ts) < self._symbol_eval_interval_seconds:
                    logger.info(
                        "Signal throttled for %s: %.1fs < %ss (correlation_id=%s)",
                        symbol_key,
                        now_ts - last_ts,
                        self._symbol_eval_interval_seconds,
                        correlation_id,
                    )
                    async with self._lock:
                        self._metrics["trades_rejected"] += 1
                        self._metrics["gate_g1_throttle_count"] += 1
                    logger.debug(
                        "G1_THROTTLE triggered, count: %d (correlation_id=%s)",
                        self._metrics["gate_g1_throttle_count"],
                        correlation_id,
                    )
                    # Error rate tracking: G1_THROTTLE
                    try:
                        from execution.alerts.error_rate_integration import (
                            ErrorCategory,
                            ErrorRateTracker,
                        )

                        ErrorRateTracker().record_operation(
                            ErrorCategory.VALIDATION,
                            success=False,
                            error_details={
                                "gate": "G1_THROTTLE",
                                "symbol": signal.token,
                                "reason": "per_symbol_cadence",
                            },
                        )
                    except Exception as ert_exc:
                        logger.debug("ErrorRateTracker G1_THROTTLE failed: %s", ert_exc)
                    # ST-ICT-Q3: Record signal rejection at throttle gate
                    if self.outcome_capture:
                        try:
                            await self.outcome_capture.on_signal_rejected(
                                signal,
                                "G1_THROTTLE",
                                "Signal throttled by per-symbol cadence",
                                correlation_id,
                            )
                        except Exception as e:
                            logger.warning(
                                f"outcome_capture.on_signal_rejected(G1) failed: {e}"
                            )
                    return PaperTradeResult(
                        signal=signal,
                        status=TradeStatus.REJECTED,
                        reject_reason=[
                            (
                                "Signal throttled by per-symbol cadence: "
                                f"{symbol_key} within "
                                f"{self._symbol_eval_interval_seconds}s"
                            )
                        ],
                        correlation_id=correlation_id,
                    )
                self._last_symbol_processed_ts[throttle_key] = now_ts

            # G1.5_SYMBOL_COOLDOWN — Minimum cooldown between ANY trades on same symbol
            cooldown_seconds = max(
                int(os.environ.get("SYMBOL_COOLDOWN_SECONDS", "300")), 60
            )
            cooldown_key = f"cooldown:symbol:{signal.token.upper().strip()}"
            if self._redis is not None:
                try:
                    last_trade_ts = await self._redis.get(cooldown_key)
                    if last_trade_ts:
                        elapsed = time.time() - float(last_trade_ts)
                        if elapsed < cooldown_seconds:
                            logger.info(
                                "G1.5_SYMBOL_COOLDOWN rejected %s — "
                                "cooldown %ds/%ds (correlation_id=%s)",
                                signal.token,
                                int(elapsed),
                                cooldown_seconds,
                                correlation_id,
                            )
                            async with self._lock:
                                self._metrics["trades_rejected"] += 1
                                self._metrics["gate_g1_5_cooldown_count"] = (
                                    self._metrics.get("gate_g1_5_cooldown_count", 0) + 1
                                )
                            # ST-ICT-Q3: Record signal rejection at cooldown gate
                            if self.outcome_capture:
                                try:
                                    await self.outcome_capture.on_signal_rejected(
                                        signal,
                                        "G1.5_SYMBOL_COOLDOWN",
                                        f"Symbol cooldown: {int(elapsed)}s/{cooldown_seconds}s",
                                        correlation_id,
                                    )
                                except Exception as e:
                                    logger.warning(
                                        f"outcome_capture.on_signal_rejected(G1.5) failed: {e}"
                                    )
                            return PaperTradeResult(
                                signal=signal,
                                status=TradeStatus.REJECTED,
                                reject_reason=[
                                    f"Symbol cooldown: {signal.token} — "
                                    f"{int(elapsed)}s/{cooldown_seconds}s"
                                ],
                                correlation_id=correlation_id,
                            )
                except Exception as cooldown_exc:
                    logger.debug(
                        "G1.5_SYMBOL_COOLDOWN check failed (non-blocking): %s",
                        cooldown_exc,
                    )

            # PAPER-009: Check paper trading kill switch before any processing
            paper_kill_switch = await self._get_paper_kill_switch()
            if paper_kill_switch:
                paper_kill_status = await paper_kill_switch.get_status()
                if paper_kill_status.active:
                    logger.critical(
                        f"PAPER KILL SWITCH ACTIVE - blocking trade execution: "
                        f"reason='{paper_kill_status.reason}' "
                        f"activated_by='{paper_kill_status.activated_by}' "
                        f"ttl_remaining={paper_kill_status.ttl_remaining}s "
                        f"(correlation_id={correlation_id})"
                    )
                    async with self._lock:
                        self._metrics["trades_rejected"] += 1
                        self._metrics["gate_g2_paper_kill_count"] += 1
                    logger.debug(
                        "G2_PAPER_KILL triggered, count: %d (correlation_id=%s)",
                        self._metrics["gate_g2_paper_kill_count"],
                        correlation_id,
                    )
                    # Error rate tracking: G2_PAPER_KILL
                    try:
                        from execution.alerts.error_rate_integration import (
                            ErrorCategory,
                            ErrorRateTracker,
                        )

                        ErrorRateTracker().record_operation(
                            ErrorCategory.EXECUTION,
                            success=False,
                            error_details={
                                "gate": "G2_PAPER_KILL",
                                "reason": paper_kill_status.reason,
                            },
                        )
                    except Exception as ert_exc:
                        logger.debug(
                            "ErrorRateTracker G2_PAPER_KILL failed: %s", ert_exc
                        )
                    # ST-ICT-Q3: Record signal rejection at paper kill gate
                    if self.outcome_capture:
                        try:
                            await self.outcome_capture.on_signal_rejected(
                                signal,
                                "G2_PAPER_KILL",
                                f"Paper kill switch active: {paper_kill_status.reason}",
                                correlation_id,
                            )
                        except Exception as e:
                            logger.warning(
                                f"outcome_capture.on_signal_rejected(G2) failed: {e}"
                            )
                    return PaperTradeResult(
                        signal=signal,
                        status=TradeStatus.REJECTED,
                        reject_reason=[
                            f"Paper kill switch active: {paper_kill_status.reason}"
                        ],
                        correlation_id=correlation_id,
                    )

            # Step 1: Check kill-switch state (live trading kill switch)
            if self.kill_switch.state.value == "triggered":
                logger.warning(
                    f"Signal rejected: kill-switch triggered (correlation_id={correlation_id})"
                )
                async with self._lock:
                    self._metrics["trades_rejected"] += 1
                    self._metrics["gate_g3_live_kill_count"] += 1
                logger.debug(
                    "G3_LIVE_KILL triggered, count: %d (correlation_id=%s)",
                    self._metrics["gate_g3_live_kill_count"],
                    correlation_id,
                )
                # Error rate tracking: G3_LIVE_KILL
                try:
                    from execution.alerts.error_rate_integration import (
                        ErrorCategory,
                        ErrorRateTracker,
                    )

                    ErrorRateTracker().record_operation(
                        ErrorCategory.EXECUTION,
                        success=False,
                        error_details={
                            "gate": "G3_LIVE_KILL",
                            "reason": "kill_switch_triggered",
                        },
                    )
                except Exception as ert_exc:
                    logger.debug("ErrorRateTracker G3_LIVE_KILL failed: %s", ert_exc)
                # ST-ICT-Q3: Record signal rejection at live kill gate
                if self.outcome_capture:
                    try:
                        await self.outcome_capture.on_signal_rejected(
                            signal,
                            "G3_LIVE_KILL",
                            "Kill-switch triggered",
                            correlation_id,
                        )
                    except Exception as e:
                        logger.warning(
                            f"outcome_capture.on_signal_rejected(G3) failed: {e}"
                        )
                return PaperTradeResult(
                    signal=signal,
                    status=TradeStatus.REJECTED,
                    # TODO: When models.py is updated, use RejectReason enum directly
                    reject_reason=["Kill-switch triggered"],
                    correlation_id=correlation_id,
                )

            # Step 1.5: Get market price early (needed for position management)
            entry_price = None
            market_data = getattr(self.order_simulator, "market_data", None)
            if market_data is not None and hasattr(market_data, "get_price"):
                entry_price = market_data.get_price(signal.token)

            # If no price available, try to set a default price for known symbols
            if entry_price is None or entry_price <= 0:
                # For live demo connector, try a direct ticker refresh first.
                if hasattr(self.order_simulator, "get_market_price"):
                    try:
                        live_price_result = self.order_simulator.get_market_price(
                            signal.token
                        )
                        if asyncio.iscoroutine(live_price_result):
                            live_price = await live_price_result
                        else:
                            live_price = live_price_result
                        if live_price is not None and live_price > 0:
                            entry_price = float(live_price)
                    except Exception as e:
                        logger.debug(
                            "Live market price refresh failed for %s: %s",
                            signal.token,
                            e,
                        )

            if entry_price is None or entry_price <= 0:
                default_price = self._get_default_price(signal.token)
                if default_price is not None:
                    logger.warning(
                        f"No market price for {signal.token}, using default price "
                        f"${default_price:,.2f} (correlation_id={correlation_id})"
                    )
                    if hasattr(self.order_simulator, "set_market_price"):
                        self.order_simulator.set_market_price(
                            signal.token, default_price
                        )
                    entry_price = default_price
                else:
                    logger.warning(
                        f"No valid market price for {signal.token} (price={entry_price}). "
                        f"Cannot create order (correlation_id={correlation_id})"
                    )
                    async with self._lock:
                        self._metrics["trades_rejected"] += 1
                        self._metrics["gate_g4_no_price_count"] += 1
                    logger.debug(
                        "G4_NO_PRICE triggered, count: %d (correlation_id=%s)",
                        self._metrics["gate_g4_no_price_count"],
                        correlation_id,
                    )
                    # Error rate tracking: G4_NO_PRICE
                    try:
                        from execution.alerts.error_rate_integration import (
                            ErrorCategory,
                            ErrorRateTracker,
                        )

                        ErrorRateTracker().record_operation(
                            ErrorCategory.VALIDATION,
                            success=False,
                            error_details={
                                "gate": "G4_NO_PRICE",
                                "symbol": signal.token,
                                "reason": "no_market_price",
                            },
                        )
                    except Exception as ert_exc:
                        logger.debug("ErrorRateTracker G4_NO_PRICE failed: %s", ert_exc)
                    # ST-ICT-Q3: Record signal rejection at no-price gate
                    if self.outcome_capture:
                        try:
                            await self.outcome_capture.on_signal_rejected(
                                signal,
                                "G4_NO_PRICE",
                                f"No market price available for {signal.token}",
                                correlation_id,
                            )
                        except Exception as e:
                            logger.warning(
                                f"outcome_capture.on_signal_rejected(G4) failed: {e}"
                            )
                    return PaperTradeResult(
                        signal=signal,
                        status=TradeStatus.REJECTED,
                        # TODO: When models.py is updated, use RejectReason enum directly
                        reject_reason=[f"No market price available for {signal.token}"],
                        correlation_id=correlation_id,
                    )

            # Step 1.6: Check for existing position and close if opposite signal
            current_positions = await self.position_tracker.get_open_positions()
            existing_position = None
            for pos in current_positions:
                if pos.symbol.upper() == signal.token.upper():
                    existing_position = pos
                    break

            if existing_position:
                # Check if position should be closed due to time limit (for burn-in testing)
                position_age_seconds = (
                    datetime.now(UTC) - existing_position.opened_at
                ).total_seconds()

                # Close if position is older than 60 seconds (for burn-in testing)
                # Only active when POC_MODE=true env var is set
                # POC_MODE is the ONLY allowed bypass path for burn-in testing
                if os.getenv(
                    "POC_MODE", "false"
                ).lower() == "true" and position_age_seconds > int(
                    os.getenv("POC_MODE_BURN_IN_SECONDS", "300")
                ):
                    logger.debug("Burn-in testing is enabled via POC_MODE=true")
                    # PT-FIX-2: Use current market price, not entry_price
                    exit_price = await self._get_current_market_price(signal.token)
                    if exit_price is None:
                        logger.warning(
                            "No market price for burn-in close of %s, "
                            "falling back to entry_price (degraded mode)",
                            signal.token,
                        )
                        exit_price = entry_price
                    # Acquire per-position lock before closing
                    pos_lock = self._get_position_lock(existing_position.position_id)
                    async with pos_lock:
                        # Re-check position still exists (TOCTOU safety)
                        current_open = await self.position_tracker.get_open_positions()
                        if any(
                            p.position_id == existing_position.position_id
                            for p in current_open
                        ):
                            await self.close_position(
                                existing_position.position_id,
                                exit_price,
                                reason="time_limit",
                            )
                            logger.info(
                                f"Time-based close: position "
                                f"{existing_position.position_id} "
                                f"after {position_age_seconds:.0f}s"
                            )
                        else:
                            logger.debug(
                                "Burn-in: position %s already closed, skipping",
                                existing_position.position_id,
                            )
                    existing_position = None  # Allow new position to open
                else:
                    # Check if signal is opposite direction
                    current_side = existing_position.side  # "long" or "short"
                    signal_side = signal.direction.value.lower()  # "long" or "short"

                    if current_side != signal_side:
                        # PT-FIX-2: Minimum hold period check
                        if position_age_seconds < self._min_hold_seconds:
                            logger.debug(
                                "Skipping opposite-signal close for %s: "
                                "position age %.0fs < min hold %ds",
                                signal.token,
                                position_age_seconds,
                                self._min_hold_seconds,
                            )
                            return PaperTradeResult(
                                signal=signal,
                                status=TradeStatus.REJECTED,
                                reject_reason=[
                                    f"Position held for {position_age_seconds:.0f}s, "
                                    f"minimum hold period is {self._min_hold_seconds}s"
                                ],
                                correlation_id=correlation_id,
                            )

                        # PT-FIX-2: Debouncing — require 2 consecutive opposite signals
                        pos_id = existing_position.position_id
                        self._opposite_signal_count[pos_id] = (
                            self._opposite_signal_count.get(pos_id, 0) + 1
                        )
                        if self._opposite_signal_count[pos_id] < 2:
                            logger.debug(
                                "Opposite signal debounce count %d/2 for position %s",
                                self._opposite_signal_count[pos_id],
                                pos_id,
                            )
                            return PaperTradeResult(
                                signal=signal,
                                status=TradeStatus.REJECTED,
                                reject_reason=[
                                    f"Opposite signal debounce: "
                                    f"{self._opposite_signal_count[pos_id]}/2"
                                ],
                                correlation_id=correlation_id,
                            )

                        # PT-FIX-2: Use current market price, not entry_price
                        exit_price = await self._get_current_market_price(signal.token)
                        if exit_price is None:
                            logger.warning(
                                "No market price for opposite-signal close of %s, "
                                "falling back to entry_price (degraded mode)",
                                signal.token,
                            )
                            exit_price = entry_price
                        # Close existing position
                        # Acquire per-position lock before closing
                        opp_pos_lock = self._get_position_lock(pos_id)
                        async with opp_pos_lock:
                            # Re-check position still exists (TOCTOU safety)
                            current_open = (
                                await self.position_tracker.get_open_positions()
                            )
                            if any(p.position_id == pos_id for p in current_open):
                                await self.close_position(
                                    existing_position.position_id, exit_price
                                )
                                logger.info(
                                    f"Closed position "
                                    f"{existing_position.position_id} for "
                                    f"{signal.token} "
                                    f"(opposite signal: {current_side} -> "
                                    f"{signal_side}, "
                                    f"exit_price={exit_price})"
                                )
                            else:
                                logger.debug(
                                    "Opposite-signal: position %s already "
                                    "closed, skipping",
                                    pos_id,
                                )
                        # Reset debounce counter
                        self._opposite_signal_count.pop(pos_id, None)
                        existing_position = None  # Allow new position to open
                    else:
                        # Same direction - skip this signal
                        # PT-FIX-2: Reset opposite-signal debounce counter
                        self._opposite_signal_count.pop(
                            existing_position.position_id, None
                        )
                        logger.debug(
                            f"Already in {signal_side} position for {signal.token}, skipping"
                        )
                        async with self._lock:
                            self._metrics["gate_g7_same_dir_skip_count"] += 1
                        logger.debug(
                            "G7_SAME_DIR_SKIP triggered, count: %d (correlation_id=%s)",
                            self._metrics["gate_g7_same_dir_skip_count"],
                            correlation_id,
                        )
                        # Error rate tracking: G7_SAME_DIR_SKIP (success=True)
                        try:
                            from execution.alerts.error_rate_integration import (
                                ErrorCategory,
                                ErrorRateTracker,
                            )

                            ErrorRateTracker().record_operation(
                                ErrorCategory.VALIDATION,
                                success=True,
                                error_details={
                                    "gate": "G7_SAME_DIR_SKIP",
                                    "symbol": signal.token,
                                    "side": signal.direction.value,
                                },
                            )
                        except Exception as ert_exc:
                            logger.debug(
                                "ErrorRateTracker G7_SAME_DIR_SKIP failed: %s", ert_exc
                            )
                        # ST-ICT-Q3: Record signal skip at same-dir gate
                        if self.outcome_capture:
                            try:
                                await self.outcome_capture.on_signal_rejected(
                                    signal,
                                    "G7_SAME_DIR_SKIP",
                                    f"Already in {signal_side} position for {signal.token}",
                                    correlation_id,
                                )
                            except Exception as e:
                                logger.warning(
                                    f"outcome_capture.on_signal_rejected(G7) failed: {e}"
                                )
                        return PaperTradeResult(
                            signal=signal,
                            status=TradeStatus.SKIPPED,
                            correlation_id=correlation_id,
                        )

            # Step 1.7: LLM-enhanced decision (behind feature flag)
            # Store full LLM decision payload for notifications
            llm_decision_payload: dict[str, Any] | None = None

            # Debug logging for LLM enhancer status
            logger.debug(
                f"LLM enhancer status: enabled={self.decision_enhancer.enabled if self.decision_enhancer else False}, "
                f"chain_initialized={self.decision_enhancer._chain is not None if self.decision_enhancer else False}"
            )

            if self.decision_enhancer and self.decision_enhancer.enabled:
                logger.info(
                    f"Calling LLM enhancer for signal {signal.token} - "
                    f"chain_ready={self.decision_enhancer._chain is not None}"
                )
                try:
                    enhanced = await self.decision_enhancer.enhance_decision(
                        signal,
                        market_context={
                            "price": entry_price,
                            "timeframe": str(getattr(signal, "timeframe", "1h")),
                        },
                    )
                    if not enhanced.go_no_go:
                        # NO-GO signal: reject and return immediately
                        logger.info(
                            f"Signal rejected by LLM: {signal.token} - {enhanced.rationale}"
                        )
                        async with self._lock:
                            self._metrics["trades_rejected"] += 1
                            self._metrics["gate_g6_llm_reject_count"] += 1
                        logger.debug(
                            "G6_LLM_REJECT triggered, count: %d (correlation_id=%s)",
                            self._metrics["gate_g6_llm_reject_count"],
                            correlation_id,
                        )
                        # Error rate tracking: G6_LLM_REJECT
                        try:
                            from execution.alerts.error_rate_integration import (
                                ErrorCategory,
                                ErrorRateTracker,
                            )

                            ErrorRateTracker().record_operation(
                                ErrorCategory.VALIDATION,
                                success=False,
                                error_details={
                                    "gate": "G6_LLM_REJECT",
                                    "reason": enhanced.rationale,
                                    "provider": enhanced.provider,
                                },
                            )
                        except Exception as ert_exc:
                            logger.debug(
                                "ErrorRateTracker G6_LLM_REJECT failed: %s", ert_exc
                            )
                        # ST-ICT-Q3: Record signal rejection at LLM gate
                        if self.outcome_capture:
                            try:
                                await self.outcome_capture.on_signal_rejected(
                                    signal,
                                    "G6_LLM_REJECT",
                                    f"LLM rejection: {enhanced.rationale}",
                                    correlation_id,
                                )
                            except Exception as e:
                                logger.warning(
                                    f"outcome_capture.on_signal_rejected(G6) failed: {e}"
                                )
                        return PaperTradeResult(
                            signal=signal,
                            status=TradeStatus.REJECTED,
                            reject_reason=[f"LLM rejection: {enhanced.rationale}"],
                            correlation_id=correlation_id,
                        )

                    # GO signal: store LLM recommendations for later comparison
                    # with risk enforcer (risk enforcer remains authoritative)
                    logger.debug(
                        f"LLM enhanced decision: {signal.token} "
                        f"confidence={enhanced.confidence} provider={enhanced.provider}"
                    )
                    llm_position_size = enhanced.position_size
                    llm_stop_loss = enhanced.stop_loss
                    llm_take_profit = enhanced.take_profit
                    llm_risk_rec = enhanced.risk_recommendation

                    llm_decision_payload = {
                        "decision": "GO",
                        "confidence": enhanced.confidence,
                        "provider": enhanced.provider,
                        "rationale": enhanced.rationale,
                        "position_size": enhanced.position_size,
                        "stop_loss": enhanced.stop_loss,
                        "take_profit": enhanced.take_profit,
                        "risk_recommendation": enhanced.risk_recommendation,
                        "fallback_used": enhanced.fallback_used,
                        "latency_ms": enhanced.latency_ms,
                    }
                except Exception as e:
                    logger.warning(
                        f"LLM enhancement failed, proceeding with base signal: {e}"
                    )
                    # Continue with base signal - don't block on LLM error
                    llm_position_size = None
                    llm_stop_loss = None
                    llm_take_profit = None
                    llm_risk_rec = ""
                    llm_decision_payload = None
            else:
                llm_position_size = None
                llm_stop_loss = None
                llm_take_profit = None
                llm_risk_rec = ""
                llm_decision_payload = None

            # Step 2: Validate risk
            risk_start = time.perf_counter()
            current_positions = await self.position_tracker.get_open_positions()

            # B-03: Calculate current drawdown from DrawdownMonitor if available
            # Pass drawdown to risk_enforcer so kill-switch can trigger at >= 15%
            current_drawdown_pct = 0.0
            if (
                self.kill_switch
                and hasattr(self.kill_switch, "drawdown_monitor")
                and self.kill_switch.drawdown_monitor is not None
            ):
                try:
                    drawdown_metrics = (
                        self.kill_switch.drawdown_monitor.calculate_rolling_drawdown()
                    )
                    current_drawdown_pct = drawdown_metrics.current_drawdown_pct
                    logger.debug(
                        f"Calculated drawdown: {current_drawdown_pct:.2%} "
                        f"(correlation_id={correlation_id})"
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to calculate drawdown, using 0.0: {e} "
                        f"(correlation_id={correlation_id})"
                    )

            assessment = await self.risk_enforcer.validate_order(
                signal=signal,
                portfolio_value=self.portfolio_value,
                current_positions=current_positions,
                current_drawdown_pct=current_drawdown_pct,
                entry_price=entry_price,
            )

            (time.perf_counter() - risk_start) * 1000

            # Q4: Emit per-gate outcome metrics for observability
            self._emit_gate_outcomes(assessment, signal, correlation_id)

            if not assessment.approved:
                logger.warning(
                    f"Signal rejected by risk enforcer: {assessment.violations} "
                    f"(correlation_id={correlation_id})"
                )
                async with self._lock:
                    self._metrics["trades_rejected"] += 1
                    self._metrics["gate_g5_risk_reject_count"] += 1
                logger.debug(
                    "G5_RISK_REJECT triggered, count: %d (correlation_id=%s)",
                    self._metrics["gate_g5_risk_reject_count"],
                    correlation_id,
                )
                # Error rate tracking: G5_RISK_REJECT
                try:
                    from execution.alerts.error_rate_integration import (
                        ErrorCategory,
                        ErrorRateTracker,
                    )

                    ErrorRateTracker().record_operation(
                        ErrorCategory.VALIDATION,
                        success=False,
                        error_details={
                            "gate": "G5_RISK_REJECT",
                            "violations": [v.message for v in assessment.violations],
                        },
                    )
                except Exception as ert_exc:
                    logger.debug("ErrorRateTracker G5_RISK_REJECT failed: %s", ert_exc)
                # ST-ICT-Q3: Record signal rejection at risk gate
                if self.outcome_capture:
                    try:
                        await self.outcome_capture.on_signal_rejected(
                            signal,
                            "G5_RISK_REJECT",
                            str(assessment.violations),
                            correlation_id,
                        )
                    except Exception as e:
                        logger.warning(
                            f"outcome_capture.on_signal_rejected(G5) failed: {e}"
                        )
                return PaperTradeResult(
                    signal=signal,
                    status=TradeStatus.REJECTED,
                    # TODO: When models.py is updated, use RejectReason enum directly
                    reject_reason=assessment.violations,
                    correlation_id=correlation_id,
                )

            # B-04: Symbol registry check - enforce one-trade-per-symbol invariant
            # Use correlation_id as provisional position_id (stored in position.metadata later)
            symbol_acquired = False
            if self.symbol_registry:
                try:
                    symbol_acquired = await self.symbol_registry.try_acquire_symbol(
                        signal.token,
                        correlation_id,  # Use correlation_id as position_id
                    )
                    if not symbol_acquired:
                        logger.warning(
                            f"Symbol {signal.token} already held by another position, "
                            f"rejecting signal (correlation_id={correlation_id})"
                        )
                        async with self._lock:
                            self._metrics["trades_rejected"] += 1
                        return PaperTradeResult(
                            signal=signal,
                            status=TradeStatus.REJECTED,
                            reject_reason=[f"Symbol {signal.token} already in use"],
                            correlation_id=correlation_id,
                        )
                except Exception as e:
                    # Redis failures should not block trading - log and proceed
                    logger.warning(
                        f"Symbol registry acquisition failed for {signal.token}, "
                        f"proceeding without symbol lock: {e} "
                        f"(correlation_id={correlation_id})"
                    )
                    symbol_acquired = True  # Proceed as if acquired
            else:
                symbol_acquired = True  # No registry configured, proceed

            # Step 3: Apply LLM recommendations with risk enforcer as authoritative
            # Use most conservative position size: min(LLM suggestion, risk enforcer cap)
            final_position_size = assessment.position_size
            if llm_position_size is not None:
                # Risk enforcer cap is authoritative - take the minimum
                final_position_size = min(llm_position_size, assessment.position_size)
                logger.debug(
                    f"Position sizing for {signal.token}: "
                    f"LLM={llm_position_size}, RiskCap={assessment.position_size}, "
                    f"Using={final_position_size}"
                )

            # Log LLM risk recommendations for observability (risk enforcer remains authoritative)
            if llm_stop_loss or llm_take_profit or llm_risk_rec:
                logger.info(
                    f"LLM risk guidance for {signal.token}: "
                    f"SL={llm_stop_loss}, TP={llm_take_profit}, "
                    f"Note={llm_risk_rec[:50] if llm_risk_rec else ''}"
                )

            # Step 4: Create order
            order = self._create_order(
                signal,
                final_position_size,
                entry_price,
                correlation_id,
                recommended_stop_loss=llm_stop_loss,
                recommended_take_profit=llm_take_profit,
            )

            # Step 5: Place order (with latency check)
            order_start = time.perf_counter()
            filled_order = await self.order_simulator.place_order(
                symbol=order.symbol,
                side=order.side,
                order_type=order.order_type,
                quantity=order.quantity,
                price=order.price,
                take_profit=order.metadata.get("take_profit"),
                stop_loss=order.metadata.get("stop_loss"),
            )
            order_latency_ms = (time.perf_counter() - order_start) * 1000

            if order_latency_ms > self.TARGET_SIGNAL_TO_ORDER_MS:
                logger.warning(
                    f"Order placement latency {order_latency_ms:.1f}ms exceeds target "
                    f"{self.TARGET_SIGNAL_TO_ORDER_MS}ms (correlation_id={correlation_id})"
                )

            # Step 5: Handle fill
            if filled_order.state == OrderState.FILLED:
                # PAPER-FIX-005: Log fill event for observability
                logger.info(
                    "[FILL-RECORDED] symbol=%s direction=%s fill_price=%.2f "
                    "quantity=%.6f order_id=%s (correlation_id=%s)",
                    filled_order.symbol,
                    filled_order.side,
                    filled_order.avg_fill_price,
                    filled_order.filled_quantity,
                    filled_order.order_id,
                    correlation_id,
                )
                position_start = time.perf_counter()
                position = await self._open_position(
                    filled_order,
                    signal,
                    correlation_id,
                    llm_decision=llm_decision_payload,
                )
                position_latency_ms = (time.perf_counter() - position_start) * 1000

                if position_latency_ms > self.TARGET_POSITION_UPDATE_MS:
                    logger.warning(
                        f"Position update latency {position_latency_ms:.1f}ms exceeds target "
                        f"{self.TARGET_POSITION_UPDATE_MS}ms (correlation_id={correlation_id})"
                    )

                # Step 6: Record trade metrics
                await self._record_trade(position, signal, correlation_id)

                # Q2: Emit SignalOutcome at OPEN - track trade opening with PENDING status
                # ST-PIPELINE-Q2: Wire confidence_score and signal_type as top-level fields
                open_outcome = SignalOutcome(
                    signal_id=signal.signal_id if signal.signal_id else None,
                    order_id=filled_order.order_id,
                    symbol=signal.token,
                    side="Buy" if signal.direction.value == "long" else "Sell",
                    direction=signal.direction.value.upper(),
                    fill_price=filled_order.avg_fill_price,
                    fill_quantity=filled_order.filled_quantity,
                    fill_timestamp=(
                        filled_order.filled_at
                        if hasattr(filled_order, "filled_at") and filled_order.filled_at
                        else datetime.now(UTC)
                    ),
                    entry_price=filled_order.avg_fill_price,
                    entry_time=(
                        filled_order.filled_at
                        if hasattr(filled_order, "filled_at") and filled_order.filled_at
                        else datetime.now(UTC)
                    ),
                    position_size=filled_order.filled_quantity,
                    status=SignalOutcomeStatus.PENDING,
                    # ST-PIPELINE-Q2: Signal-to-outcome correlation fields
                    confidence_score=signal.confidence,
                    signal_type="OPEN",
                    metadata={
                        **self._connector_provenance,
                        "correlation_id": correlation_id,
                    },
                )
                logger.debug(
                    f"SignalOutcome emitted at OPEN: outcome_id={open_outcome.outcome_id} "
                    f"symbol={open_outcome.symbol} status={open_outcome.status.value} "
                    f"confidence={open_outcome.confidence_score} "
                    f"signal_type={open_outcome.signal_type} "
                    f"(correlation_id={correlation_id})"
                )

                # Wire outcome_capture.on_trade_open() to persist PENDING outcome
                if self.outcome_capture:
                    try:
                        await self.outcome_capture.on_trade_open(
                            open_outcome, correlation_id
                        )
                    except Exception as e:
                        logger.warning(f"outcome_capture.on_trade_open failed: {e}")

                # Calculate total latency
                total_latency_ms = (time.perf_counter() - start_time) * 1000

                # Update running average
                async with self._lock:
                    total_signals = self._metrics["signals_processed"] + 1
                    self._metrics["total_latency_ms"] += total_latency_ms
                    self._metrics["avg_latency_ms"] = (
                        self._metrics["total_latency_ms"] / total_signals
                    )

                if total_latency_ms > self.TARGET_TOTAL_PIPELINE_MS:
                    logger.warning(
                        f"Total pipeline latency {total_latency_ms:.1f}ms exceeds target "
                        f"{self.TARGET_TOTAL_PIPELINE_MS}ms (correlation_id={correlation_id})"
                    )

                logger.info(
                    f"Trade executed: {signal.token} position={position.position_id} "
                    f"latency={total_latency_ms:.1f}ms (correlation_id={correlation_id})"
                )

                # ErrorRateTracker: record successful order execution
                try:
                    from execution.alerts.error_rate_tracker import (
                        ErrorCategory,
                        ErrorRateTracker,
                    )

                    ErrorRateTracker().record_operation(
                        ErrorCategory.EXECUTION,
                        success=True,
                        error_details={
                            "symbol": signal.token,
                            "order_id": filled_order.order_id,
                        },
                    )
                except Exception as ert_exc:
                    logger.debug(
                        "ErrorRateTracker ORDER_EXECUTION_SUCCESS failed: %s", ert_exc
                    )

                # PAPER-FORENSIC-001: Log connector type and provenance on each trade
                prov = self._connector_provenance
                logger.info(
                    f"[TRADE-PROVENANCE] {signal.token} position={position.position_id} "
                    f"venue={prov.get('execution_venue', 'unknown')}, "
                    f"mode={prov.get('execution_mode', 'unknown')}, "
                    f"source={prov.get('execution_source', 'unknown')}"
                )

                async with self._lock:
                    self._metrics["trades_executed"] += 1

                # Wire outcome_capture.on_trade_result() if configured
                if self.outcome_capture:
                    try:
                        result_for_capture = PaperTradeResult(
                            signal=signal,
                            status=TradeStatus.EXECUTED,
                            order=filled_order,
                            position=position,
                            latency_ms=total_latency_ms,
                            correlation_id=correlation_id,
                        )
                        await self.outcome_capture.on_trade_result(result_for_capture)
                    except Exception as e:
                        logger.warning(f"outcome_capture.on_trade_result failed: {e}")

                return PaperTradeResult(
                    signal=signal,
                    status=TradeStatus.EXECUTED,
                    order=filled_order,
                    position=position,
                    latency_ms=total_latency_ms,
                    correlation_id=correlation_id,
                )
            else:
                # Order not filled
                logger.warning(
                    f"Order not filled: state={filled_order.state.value} "
                    f"(correlation_id={correlation_id})"
                )
                async with self._lock:
                    self._metrics["trades_failed"] += 1
                    self._metrics["gate_g8_order_not_filled_count"] += 1
                logger.debug(
                    "G8_ORDER_NOT_FILLED triggered, count: %d (correlation_id=%s)",
                    self._metrics["gate_g8_order_not_filled_count"],
                    correlation_id,
                )
                # B-04: Release symbol if order was not filled
                # (symbol was acquired before order placement)
                if self.symbol_registry and symbol_acquired:
                    try:
                        released = await self.symbol_registry.release_symbol(
                            signal.token,
                            correlation_id,
                        )
                        if released:
                            logger.debug(
                                f"Released symbol {signal.token} after order not filled "
                                f"(correlation_id={correlation_id})"
                            )
                    except Exception as e:
                        logger.warning(
                            f"Failed to release symbol {signal.token} after order not filled: {e}"
                        )

                # ST-ICT-Q3: Record signal rejection at order-not-filled gate
                if self.outcome_capture:
                    try:
                        await self.outcome_capture.on_signal_rejected(
                            signal,
                            "G8_ORDER_NOT_FILLED",
                            f"Order state: {filled_order.state.value}",
                            correlation_id,
                        )
                    except Exception as e:
                        logger.warning(
                            f"outcome_capture.on_signal_rejected(G8) failed: {e}"
                        )
                return PaperTradeResult(
                    signal=signal,
                    status=TradeStatus.FAILED,
                    order=filled_order,
                    # TODO: When models.py is updated, use RejectReason enum directly
                    reject_reason=[f"Order state: {filled_order.state.value}"],
                    correlation_id=correlation_id,
                )

        except Exception as e:
            # Log error with correlation ID but don't crash
            logger.error(
                f"Error processing signal: {e} (correlation_id={correlation_id})",
                exc_info=True,
            )

            async with self._lock:
                self._metrics["trades_failed"] += 1
                self._metrics["gate_g9_exception_count"] += 1
            logger.debug(
                "G9_EXCEPTION triggered, count: %d (correlation_id=%s)",
                self._metrics["gate_g9_exception_count"],
                correlation_id,
            )
            # ST-ICT-Q3: Record signal rejection at exception gate
            if self.outcome_capture:
                try:
                    await self.outcome_capture.on_signal_rejected(
                        signal,
                        "G9_EXCEPTION",
                        str(e),
                        correlation_id,
                    )
                except Exception as cap_e:
                    logger.warning(
                        f"outcome_capture.on_signal_rejected(G9) failed: {cap_e}"
                    )
            return PaperTradeResult(
                signal=signal,
                status=TradeStatus.FAILED,
                # TODO: When models.py is updated, use RejectReason enum directly
                reject_reason=[str(e)],
                correlation_id=correlation_id,
            )

    def _create_order(
        self,
        signal: Signal,
        position_size: float,
        entry_price: float,
        correlation_id: str,
        recommended_stop_loss: float | None = None,
        recommended_take_profit: float | None = None,
    ) -> PaperOrder:
        """Create an order from a signal.

        Args:
            signal: Trading signal
            position_size: Calculated position size
            entry_price: Entry price for the order
            correlation_id: Correlation ID for tracing
            recommended_stop_loss: Optional SL from LLM/risk stack
            recommended_take_profit: Optional TP from LLM/risk stack

        Returns:
            PaperOrder ready for placement

        Raises:
            ValueError: If entry_price is not positive
        """
        # Validate entry price
        if entry_price <= 0:
            raise ValueError(f"Entry price must be positive, got: {entry_price}")

        # Map signal direction to order side
        side = OrderSide.BUY if signal.direction.value == "long" else OrderSide.SELL

        # Create market order (could be extended for limit orders)
        order = PaperOrder(
            order_id=str(uuid.uuid4()),
            symbol=signal.token,
            side=side.value,  # Use string value, not enum
            order_type=OrderType.MARKET.value,  # Use string value, not enum
            quantity=position_size,
            price=entry_price,  # Set the entry price
        )

        # Store correlation_id and stop-loss in metadata
        order.metadata["correlation_id"] = correlation_id
        effective_stop_loss = recommended_stop_loss or signal.stop_loss
        if effective_stop_loss:
            order.metadata["stop_loss"] = effective_stop_loss
            order.metadata["stop_loss_method"] = signal.stop_loss_method or "unknown"
        # Use recommended_take_profit (from LLM) or fall back to signal.take_profit
        effective_take_profit = recommended_take_profit or signal.take_profit
        if effective_take_profit:
            order.metadata["take_profit"] = effective_take_profit

        logger.debug(
            f"Created {order.order_type} order: {order.symbol} "
            f"{order.side} {order.quantity} @ ${entry_price:,.2f} "
            f"(value=${order.quantity * entry_price:,.2f})"
        )

        return order

    async def _open_position(
        self,
        filled_order: PaperOrder,
        signal: Signal,
        correlation_id: str,
        llm_decision: dict[str, Any] | None = None,
    ) -> Any:
        """Open a position from a filled order.

        Args:
            filled_order: The filled order
            signal: Original signal
            correlation_id: Correlation ID
            llm_decision: Optional LLM decision payload for notifications

        Returns:
            New PaperPosition
        """
        # Determine position side from signal
        side = signal.direction.value  # "long" or "short"

        # Build metadata dict
        metadata: dict[str, Any] = {
            "signal_id": signal.signal_id,
            "order_id": filled_order.order_id,
            "correlation_id": correlation_id,
            "stop_loss": signal.stop_loss,
            "take_profit": signal.take_profit,
            "stop_loss_method": signal.stop_loss_method,
            "confidence": signal.confidence,
        }

        # Store LLM decision in position metadata if available
        if llm_decision:
            metadata["llm_decision"] = llm_decision

        # Open position via tracker
        position = await self.position_tracker.open_position(
            symbol=filled_order.symbol,
            side=side,
            entry_price=filled_order.avg_fill_price,
            quantity=filled_order.filled_quantity,
            metadata=metadata,
        )

        logger.debug(f"Opened position: {position.position_id}")

        # Create trade journal entry using service (if available) for persistence
        if self.trade_journal_service:
            entry = None
            try:
                entry = self.trade_journal_service.create_entry(
                    position=position,
                    signal=signal,
                    correlation_id=correlation_id,
                )
                # Store entry_id in position metadata for later reference
                # Initialize metadata dict if needed
                if position.metadata is None:
                    position.metadata = {}
                position.metadata["journal_entry_id"] = entry.entry_id
                logger.info(
                    f"Trade journal entry created and persisted: {entry.entry_id} "
                    f"for position {position.position_id}"
                )
            except Exception as e:
                logger.warning(
                    f"Failed to create trade journal entry: {e}",
                    exc_info=True,
                )
        elif self.trade_journal:
            # Fallback to direct journal usage (backward compatibility)
            entry = None
            try:
                entry = self.trade_journal.create_entry(
                    position=position,
                    signal=signal,
                    correlation_id=correlation_id,
                )
                # Store entry_id in position metadata for later reference
                # Initialize metadata dict if needed
                if position.metadata is None:
                    position.metadata = {}
                position.metadata["journal_entry_id"] = entry.entry_id
                logger.info(
                    f"Trade journal entry created: {entry.entry_id} "
                    f"for position {position.position_id}"
                )
            except Exception as e:
                logger.warning(
                    f"Failed to create trade journal entry: {e}",
                    exc_info=True,
                )

        # Send Discord notification if notifier is configured
        if self.trade_notifier:
            try:
                outcome = self.trade_notifier.create_outcome_from_paper_position(
                    position=position,
                    order=filled_order,
                    signal_id=signal.signal_id,
                )
                result = await self.trade_notifier.send_trade_open_notification(
                    outcome, llm_decision=llm_decision
                )

                if result.success:
                    logger.info(
                        f"Discord trade open alert sent: position={position.position_id} "
                        f"message_id={result.message_id}"
                    )
                else:
                    logger.warning(
                        f"Discord trade open alert failed: position={position.position_id} "
                        f"error={result.error}"
                    )
            except Exception as e:
                logger.error(
                    f"Failed to send Discord trade open notification: {e}",
                    exc_info=True,
                )

        # Set symbol cooldown after position open
        await self._set_symbol_cooldown(position.symbol)

        return position

    async def _record_trade(
        self,
        position: Any,
        signal: Signal,
        correlation_id: str,
    ) -> None:
        """Record trade in telemetry.

        Args:
            position: The opened position
            signal: Original signal
            correlation_id: Correlation ID
        """
        try:
            from execution.telemetry.metrics import PositionEvent, PositionSide

            # Create position event for telemetry
            side = PositionSide.LONG if position.side == "long" else PositionSide.SHORT

            event = PositionEvent(
                position_id=position.position_id,
                symbol=position.symbol,
                side=side,
                entry_price=position.entry_price,
                current_price=position.entry_price,
                quantity=position.quantity,
                unrealized_pnl=0.0,
                environment="paper",
            )

            # Update equity
            if self.telemetry:
                await self.telemetry.set_equity(self.portfolio_value)

            logger.debug(f"Recorded position: {event.position_id}")

        except Exception as e:
            # Log error but don't fail the trade
            logger.error(f"Failed to record trade: {e}")

    async def close_position(
        self,
        position_id: str,
        exit_price: float,
        reason: str = "manual",
    ) -> tuple[Any, float] | None:
        """Close a position.

        Args:
            position_id: Position to close
            exit_price: Exit price
            reason: Reason for closure

        Returns:
            Tuple of (position, realized_pnl) or None if not found
        """
        try:
            position, realized_pnl = await self.position_tracker.close_position(
                position_id=position_id,
                exit_price=exit_price,
            )

            logger.info(
                f"Closed position {position_id}: PnL={realized_pnl:.4f}, reason={reason}"
            )

            # B-04: Release symbol from registry after successful position close
            if self.symbol_registry:
                try:
                    # Retrieve correlation_id from position metadata (stored during symbol acquisition)
                    registry_position_id = (
                        position.metadata.get("correlation_id")
                        if position.metadata
                        else None
                    )
                    if registry_position_id:
                        released = await self.symbol_registry.release_symbol(
                            position.symbol,
                            registry_position_id,
                        )
                        if released:
                            logger.debug(
                                f"Released symbol {position.symbol} from registry "
                                f"(position_id={registry_position_id})"
                            )
                        else:
                            logger.warning(
                                f"Failed to release symbol {position.symbol}: "
                                f"position_id mismatch or already released "
                                f"(expected={registry_position_id})"
                            )
                    else:
                        logger.debug(
                            f"No correlation_id in position metadata for {position.symbol}, "
                            f"skipping symbol registry release"
                        )
                except Exception as e:
                    # Log but don't fail the close
                    logger.warning(
                        f"Symbol registry release failed for {position.symbol}: {e}"
                    )

            # Close trade journal entry using service (if available) for persistence
            entry_id = (
                position.metadata.get("journal_entry_id") if position.metadata else None
            )
            if entry_id:
                try:
                    # Map close reason to ExitReason enum using unified mapper
                    exit_reason = ReasonCodeMapper.map_close_reason_string_to_enum(
                        reason
                    )

                    if self.trade_journal_service:
                        self.trade_journal_service.close_entry(
                            entry_id=entry_id,
                            exit_price=exit_price,
                            exit_reason=exit_reason,
                            pnl=realized_pnl,
                        )
                        logger.info(
                            f"Trade journal entry closed and persisted: {entry_id} with PnL {realized_pnl:.4f}"
                        )
                    elif self.trade_journal:
                        # Fallback to direct journal usage (backward compatibility)
                        self.trade_journal.close_entry(
                            entry_id=entry_id,
                            exit_price=exit_price,
                            exit_reason=exit_reason,
                            pnl=realized_pnl,
                        )
                        logger.info(
                            f"Trade journal entry closed: {entry_id} with PnL {realized_pnl:.4f}"
                        )
                except Exception as e:
                    logger.warning(
                        f"Failed to close trade journal entry {entry_id}: {e}",
                        exc_info=True,
                    )

            # Update portfolio value
            self.portfolio_value += realized_pnl
            if self.telemetry:
                maybe_awaitable = self.telemetry.set_equity(self.portfolio_value)
                if inspect.isawaitable(maybe_awaitable):
                    await maybe_awaitable

            # Wire outcome_capture.on_position_close() if configured
            if self.outcome_capture:
                try:
                    # Get correlation_id from position metadata if available
                    correlation_id = None
                    if position.metadata:
                        correlation_id = position.metadata.get("correlation_id")
                    await self.outcome_capture.on_position_close(
                        position=position,
                        exit_price=exit_price,
                        realized_pnl=realized_pnl,
                        reason=reason,
                        correlation_id=correlation_id,
                    )
                except Exception as e:
                    logger.warning(f"outcome_capture.on_position_close failed: {e}")

            # Send Discord notification if notifier is configured
            if self.trade_notifier:
                try:
                    outcome = self.trade_notifier.create_outcome_from_paper_position(
                        position=position,
                        signal_id=(
                            position.metadata.get("signal_id")
                            if position.metadata
                            else None
                        ),
                        pnl=realized_pnl,
                        exit_price=exit_price,
                    )
                    # Extract LLM decision from position metadata
                    llm_decision = (
                        position.metadata.get("llm_decision")
                        if position.metadata
                        else None
                    )
                    result = await self.trade_notifier.send_trade_close_notification(
                        outcome, llm_decision=llm_decision
                    )

                    if result.success:
                        logger.info(
                            f"Discord trade close alert sent: position={position_id} "
                            f"message_id={result.message_id}"
                        )
                    else:
                        logger.warning(
                            f"Discord trade close alert failed: position={position_id} "
                            f"error={result.error}"
                        )
                except Exception as e:
                    logger.error(
                        f"Failed to send Discord trade close notification: {e}",
                        exc_info=True,
                    )

            # G-EXIT-24H: Record canary close for instrumentation
            try:
                await self._canary_metrics.record_canary_close_async(
                    position_id=position.position_id,
                    realized_pnl=realized_pnl,
                    timestamp=datetime.now(UTC).timestamp(),
                    metadata={
                        "symbol": position.symbol,
                        "side": position.side,
                        "reason": reason,
                    },
                )
                logger.info(
                    f"[G-EXIT-24H] Canary close recorded: position_id={position.position_id}, "
                    f"realized_pnl={realized_pnl:.4f}"
                )
            except Exception as e:
                logger.warning(f"[G-EXIT-24H] Failed to record canary close: {e}")

            # Set symbol cooldown after position close
            if position is not None:
                await self._set_symbol_cooldown(position.symbol)

            # Clean up per-position lock to prevent memory leaks
            self._position_locks.pop(position_id, None)

            return position, realized_pnl

        except Exception as e:
            logger.error(f"Failed to close position {position_id}: {e}")
            return None

    async def _set_symbol_cooldown(self, symbol: str) -> None:
        """Set cooldown key in Redis after a trade on a symbol.

        This is fire-and-forget — a failure here must never block trading.

        Args:
            symbol: Trading pair symbol (e.g. "BTC/USDT")
        """
        if self._redis is None:
            return
        try:
            cooldown_seconds = max(
                int(os.environ.get("SYMBOL_COOLDOWN_SECONDS", "300")), 60
            )
            cooldown_key = f"cooldown:symbol:{symbol.upper().strip()}"
            await self._redis.setex(cooldown_key, cooldown_seconds, str(time.time()))
            logger.debug("Set symbol cooldown for %s (%ds)", symbol, cooldown_seconds)
        except Exception as e:
            logger.debug("Failed to set symbol cooldown for %s: %s", symbol, e)

    async def _get_current_market_price(self, symbol: str) -> float | None:
        """Get current market price for a symbol from live data sources.

        Tries market_data.get_price first, then falls back to
        order_simulator.get_market_price. Does NOT use hardcoded defaults.

        Args:
            symbol: Trading pair symbol (e.g., "BTC/USDT")

        Returns:
            Current market price, or None if unavailable
        """
        # Try market_data.get_price first
        market_data = getattr(self.order_simulator, "market_data", None)
        if market_data is not None and hasattr(market_data, "get_price"):
            price = market_data.get_price(symbol)
            if price is not None and price > 0:
                return float(price)

        # Fallback: order_simulator.get_market_price (may be coroutine)
        if hasattr(self.order_simulator, "get_market_price"):
            try:
                result = self.order_simulator.get_market_price(symbol)
                if asyncio.iscoroutine(result):
                    result = await result
                if result is not None and result > 0:
                    return float(result)
            except Exception as e:
                logger.debug(
                    "get_market_price failed for %s in _get_current_market_price: %s",
                    symbol,
                    e,
                )

        return None

    def _get_default_price(self, symbol: str) -> float | None:
        """Get default market price for a known symbol.

        DEPRECATED: Hardcoded price defaults removed as they become stale
        and dangerous (e.g., BTC hardcoded at $65K was 40% below actual).

        Always returns None — callers must handle the absence of price data
        by skipping the operation or fetching live data.

        Args:
            symbol: Trading pair symbol (e.g., "BTC/USDT", "BTCUSDT")

        Returns:
            Always None — hardcoded defaults are removed
        """
        logger.warning(
            "No default price available for %s. "
            "Hardcoded defaults removed to prevent stale price usage. "
            "Ensure live price feeds are operational.",
            symbol,
        )
        return None

    async def _sltp_monitoring_loop(self) -> None:
        """Periodically check open positions for SL/TP triggers.

        PT-FIX-3: Runs every _sltp_poll_interval seconds while the orchestrator
        is active. For each open position, fetches current price, validates
        freshness, and evaluates SL/TP conditions. Triggers close_position()
        when a level is hit.
        """
        logger.info("SL/TP monitoring loop entering main cycle")
        stats_interval = 300  # Log stats every 5 minutes
        last_stats_time = time.monotonic()

        while self._running:
            try:
                await asyncio.sleep(self._sltp_poll_interval)

                if not self._running:
                    break

                # Get all open positions
                open_positions = await self.position_tracker.get_open_positions()
                if not open_positions:
                    continue

                positions_checked = 0
                triggers = 0

                for position in open_positions:
                    try:
                        # Per-position lock: skip if another operation
                        # (e.g. signal processing) is already acting on
                        # this position.
                        position_lock = self._get_position_lock(position.position_id)
                        if position_lock.locked():
                            logger.debug(
                                "SL/TP: Position %s is locked by another "
                                "operation, skipping",
                                position.position_id,
                            )
                            continue

                        async with position_lock:
                            # Re-check if position is still open (may have
                            # been closed while waiting or in a prior
                            # iteration).
                            current_positions = (
                                await self.position_tracker.get_open_positions()
                            )
                            if not any(
                                p.position_id == position.position_id
                                for p in current_positions
                            ):
                                logger.debug(
                                    "SL/TP: Position %s no longer open, skipping",
                                    position.position_id,
                                )
                                continue

                            # Fetch current price
                            current_price = await self._get_current_market_price(
                                position.symbol
                            )
                            if current_price is None:
                                logger.debug(
                                    "SL/TP: No price for %s, skipping position %s",
                                    position.symbol,
                                    position.position_id,
                                )
                                continue

                            # Price freshness check
                            now = time.monotonic()
                            last_entry = self._sltp_last_price.get(position.symbol)
                            if last_entry is not None:
                                last_val, last_ts = last_entry
                                if last_val == current_price and (now - last_ts) > 60.0:
                                    logger.warning(
                                        "SL/TP: Stale price for %s (%.2f "
                                        "unchanged for %.0fs), skipping "
                                        "position %s",
                                        position.symbol,
                                        current_price,
                                        now - last_ts,
                                        position.position_id,
                                    )
                                    continue
                            self._sltp_last_price[position.symbol] = (
                                current_price,
                                now,
                            )

                            # Check SL/TP conditions
                            trigger = self._check_position_sltp(position, current_price)
                            positions_checked += 1

                            if trigger is not None:
                                trigger_type, trigger_level = trigger
                                logger.info(
                                    "SL/TP TRIGGER: position=%s symbol=%s "
                                    "side=%s entry=%.2f current=%.2f "
                                    "level=%.2f type=%s",
                                    position.position_id,
                                    position.symbol,
                                    position.side,
                                    position.entry_price,
                                    current_price,
                                    trigger_level,
                                    trigger_type,
                                )
                                await self.close_position(
                                    position_id=position.position_id,
                                    exit_price=current_price,
                                    reason=trigger_type,
                                )
                                triggers += 1
                                self._sltp_stats["triggers_executed"] += 1

                    except Exception as e:
                        logger.error(
                            "SL/TP: Error checking position %s: %s",
                            getattr(position, "position_id", "unknown"),
                            e,
                            exc_info=True,
                        )

                self._sltp_stats["positions_checked"] += positions_checked

                # Periodic stats logging
                now = time.monotonic()
                if (now - last_stats_time) >= stats_interval:
                    logger.info(
                        "SL/TP stats: checked=%d triggers=%d open=%d",
                        self._sltp_stats["positions_checked"],
                        self._sltp_stats["triggers_executed"],
                        len(open_positions),
                    )
                    last_stats_time = now

            except asyncio.CancelledError:
                logger.info("SL/TP monitoring loop cancelled")
                raise
            except Exception as e:
                logger.error("SL/TP monitoring loop error: %s", e, exc_info=True)

    @staticmethod
    def _check_position_sltp(
        position: Any, current_price: float
    ) -> tuple[str, float] | None:
        """Check if a position's SL or TP level has been hit.

        PT-FIX-3: Evaluates stop-loss and take-profit conditions based on
        position side (long/short) and current market price.

        Args:
            position: PaperPosition with metadata containing stop_loss/take_profit
            current_price: Current market price for the position's symbol

        Returns:
            Tuple of (reason, trigger_level) if triggered, None otherwise.
            reason is "stop_loss_hit" or "take_profit_hit".
        """
        metadata = getattr(position, "metadata", None) or {}
        stop_loss = metadata.get("stop_loss")
        take_profit = metadata.get("take_profit")

        if stop_loss is None and take_profit is None:
            return None

        side = position.side
        # Normalize side to lowercase for comparison
        side_str = str(side).lower()

        # Check stop-loss
        if stop_loss is not None and stop_loss > 0:
            if side_str == "long" and current_price <= stop_loss:
                return ("stop_loss_hit", stop_loss)
            if side_str == "short" and current_price >= stop_loss:
                return ("stop_loss_hit", stop_loss)

        # Check take-profit
        if take_profit is not None and take_profit > 0:
            if side_str == "long" and current_price >= take_profit:
                return ("take_profit_hit", take_profit)
            if side_str == "short" and current_price <= take_profit:
                return ("take_profit_hit", take_profit)

        return None

    def get_metrics(self) -> dict[str, Any]:
        """Get orchestrator metrics.

        Returns:
            Dictionary with performance metrics
        """
        return self._metrics.copy()

    def get_journal_stats(self) -> dict[str, Any] | None:
        """Get trade journal statistics.

        Returns:
            Dictionary with journal statistics or None if no journal configured
        """
        if self.trade_journal_service:
            return self.trade_journal_service.get_stats()
        elif self.trade_journal:
            return self.trade_journal.get_stats()
        return None

    def recover_journal(self, session_id: str) -> bool:
        """Recover journal from Redis.

        Loads all entries from Redis and populates the in-memory journal.

        Args:
            session_id: The session ID to recover

        Returns:
            True if recovery was successful, False otherwise
        """
        if self.trade_journal_service is None:
            logger.warning("No trade journal service configured, cannot recover")
            return False

        recovered = self.trade_journal_service.recover(session_id)
        if recovered:
            self.trade_journal = self.trade_journal_service.journal
            logger.info(f"Recovered trade journal for session {session_id}")
        else:
            logger.info(f"No existing journal found for session {session_id}")

        return recovered

    def is_journal_persistence_healthy(self) -> bool:
        """Check if journal persistence layer is healthy.

        Returns:
            True if Redis persistence is working, False otherwise
        """
        if self.trade_journal_service is None:
            return False
        return self.trade_journal_service.is_persistence_healthy()

    async def get_portfolio_summary(self) -> dict[str, Any]:
        """Get current portfolio summary.

        Returns:
            Portfolio summary with positions and PnL
        """
        # Get positions (without price updates for speed)
        open_positions = await self.position_tracker.get_open_positions()
        closed_positions = await self.position_tracker.get_closed_positions()

        total_unrealized = sum(p.unrealized_pnl for p in open_positions)
        total_realized = sum(p.realized_pnl for p in closed_positions)

        return {
            "portfolio_value": self.portfolio_value,
            "open_positions": len(open_positions),
            "closed_positions": len(closed_positions),
            "total_unrealized_pnl": total_unrealized,
            "total_realized_pnl": total_realized,
            "total_pnl": total_unrealized + total_realized,
            "metrics": self._metrics.copy(),
        }
