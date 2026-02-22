"""Outcome Capture Service for trade result processing.

This module provides the main service for capturing trade outcomes from
Bybit fills, storing them in PostgreSQL, and matching them to signals.
It orchestrates the fill listener, database storage, and signal matching.

For ST-LAUNCH-018: Outcome Capture Service Implementation
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from ml.feedback.bybit_fill_listener import (
    BybitFillListener,
    BybitListenerConfig,
)
from ml.models.signal_outcome import (
    OutcomeMatchResult,
    SignalOutcome,
    SignalOutcomeStatus,
)

logger = logging.getLogger(__name__)


@dataclass
class OutcomeCaptureConfig:
    """Configuration for outcome capture service.

    Attributes:
        bybit_config: Bybit WebSocket listener configuration
        match_window_hours: Hours to look back for signal matching
        enable_signal_matching: Whether to match fills to signals
        enable_pnl_calculation: Whether to calculate PnL
        batch_size: Number of outcomes to batch insert
        flush_interval_seconds: How often to flush batched outcomes
        max_pending_outcomes: Maximum pending outcomes before forced flush
    """

    bybit_config: BybitListenerConfig = field(default_factory=BybitListenerConfig)
    match_window_hours: float = 24.0
    enable_signal_matching: bool = True
    enable_pnl_calculation: bool = True
    batch_size: int = 100
    flush_interval_seconds: int = 30
    max_pending_outcomes: int = 500


@dataclass
class CaptureMetrics:
    """Metrics for outcome capture service.

    Attributes:
        fills_received: Total fills received from WebSocket
        outcomes_stored: Total outcomes stored in database
        signals_matched: Total outcomes matched to signals
        duplicates_filtered: Duplicate fills filtered
        errors_encountered: Number of errors
        last_fill_timestamp: Timestamp of last fill received
        avg_latency_seconds: Average processing latency
    """

    fills_received: int = 0
    outcomes_stored: int = 0
    signals_matched: int = 0
    duplicates_filtered: int = 0
    errors_encountered: int = 0
    last_fill_timestamp: datetime | None = None
    avg_latency_seconds: float = 0.0
    _latency_sum: float = field(default=0.0, repr=False)
    _latency_count: int = field(default=0, repr=False)

    def record_latency(self, latency_seconds: float) -> None:
        """Record a latency measurement."""
        self._latency_sum += latency_seconds
        self._latency_count += 1
        self.avg_latency_seconds = self._latency_sum / self._latency_count

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "fills_received": self.fills_received,
            "outcomes_stored": self.outcomes_stored,
            "signals_matched": self.signals_matched,
            "duplicates_filtered": self.duplicates_filtered,
            "errors_encountered": self.errors_encountered,
            "last_fill_timestamp": (
                self.last_fill_timestamp.isoformat()
                if self.last_fill_timestamp
                else None
            ),
            "avg_latency_seconds": round(self.avg_latency_seconds, 3),
        }


class OutcomeCaptureService:
    """Service for capturing trade outcomes from Bybit fills.

    This service coordinates:
    - WebSocket connection to Bybit execution channel
    - Fill event parsing and validation
    - Outcome storage in PostgreSQL
    - Signal matching using order metadata
    - Deduplication via Redis
    - Error handling and recovery

    Usage:
        config = OutcomeCaptureConfig()
        service = OutcomeCaptureService(
            config=config,
            db_pool=postgres_pool,
            redis_client=redis_client,
        )

        await service.start()

        # Run until stopped
        try:
            await service.run_forever()
        except KeyboardInterrupt:
            await service.stop()
    """

    def __init__(
        self,
        config: OutcomeCaptureConfig | None = None,
        db_pool: Any | None = None,
        redis_client: Any | None = None,
        signal_tracker: Any | None = None,
    ):
        """Initialize the service.

        Args:
            config: Service configuration
            db_pool: PostgreSQL connection pool
            redis_client: Redis client for deduplication
            signal_tracker: Signal tracker for matching fills to signals
        """
        self.config = config or OutcomeCaptureConfig()
        self.db_pool = db_pool
        self.redis = redis_client
        self.signal_tracker = signal_tracker
        self.metrics = CaptureMetrics()

        self._listener: BybitFillListener | None = None
        self._running = False
        self._pending_outcomes: list[SignalOutcome] = []
        self._flush_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Start the outcome capture service."""
        if self._running:
            logger.warning("Service already running")
            return

        self._running = True

        # Initialize listener
        self._listener = BybitFillListener(
            config=self.config.bybit_config,
            redis_client=self.redis,
        )

        # Register callbacks
        self._listener.on_fill(self._on_fill)
        self._listener.on_error(self._on_error)

        # Start listener
        await self._listener.start()

        # Start background flush task
        self._flush_task = asyncio.create_task(self._flush_loop())

        logger.info("Outcome capture service started")

    async def stop(self) -> None:
        """Stop the service gracefully."""
        self._running = False

        # Stop listener
        if self._listener:
            await self._listener.stop()
            self._listener = None

        # Cancel flush task
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        # Final flush of pending outcomes
        async with self._lock:
            if self._pending_outcomes:
                await self._store_outcomes(self._pending_outcomes)
                self._pending_outcomes.clear()

        logger.info("Outcome capture service stopped")

    async def run_forever(self) -> None:
        """Run until explicitly stopped."""
        try:
            if self._listener:
                await self._listener.run_forever()
        except asyncio.CancelledError:
            await self.stop()
            raise

    def get_metrics(self) -> CaptureMetrics:
        """Get current metrics."""
        return self.metrics

    def get_status(self) -> dict[str, Any]:
        """Get service status."""
        return {
            "running": self._running,
            "listener_connected": (
                self._listener.state.is_connected if self._listener else False
            ),
            "listener_authenticated": (
                self._listener.state.is_authenticated if self._listener else False
            ),
            "pending_outcomes": len(self._pending_outcomes),
            "metrics": self.metrics.to_dict(),
        }

    async def process_outcome(
        self,
        outcome: SignalOutcome,
        match_to_signal: bool = True,
    ) -> OutcomeMatchResult:
        """Process a single outcome (for testing or manual processing).

        Args:
            outcome: Signal outcome to process
            match_to_signal: Whether to attempt signal matching

        Returns:
            OutcomeMatchResult with match details
        """
        start_time = datetime.now(UTC)

        try:
            # Match to signal if enabled
            if match_to_signal and self.config.enable_signal_matching:
                match_result = await self._match_to_signal(outcome)
                outcome.signal_id = match_result.signal_id
                outcome.status = (
                    SignalOutcomeStatus.MATCHED
                    if match_result.matched
                    else SignalOutcomeStatus.FILLED
                )
            else:
                match_result = OutcomeMatchResult(
                    outcome=outcome,
                    matched=False,
                    match_method="skipped",
                )

            # Store outcome
            await self._store_outcome(outcome)

            # Update metrics
            self.metrics.outcomes_stored += 1
            if match_result.matched:
                self.metrics.signals_matched += 1

            # Record latency
            latency = (datetime.now(UTC) - start_time).total_seconds()
            self.metrics.record_latency(latency)

            return match_result

        except Exception as e:
            logger.error(f"Error processing outcome: {e}")
            self.metrics.errors_encountered += 1
            return OutcomeMatchResult(
                outcome=outcome,
                matched=False,
                error=str(e),
            )

    def _on_fill(self, outcome: SignalOutcome) -> None:
        """Handle fill event from listener.

        Args:
            outcome: Parsed signal outcome
        """
        asyncio.create_task(self._handle_fill_async(outcome))

    async def _handle_fill_async(self, outcome: SignalOutcome) -> None:
        """Handle fill event asynchronously.

        Args:
            outcome: Parsed signal outcome
        """
        start_time = datetime.now(UTC)
        self.metrics.fills_received += 1
        self.metrics.last_fill_timestamp = start_time

        try:
            # Match to signal if enabled
            if self.config.enable_signal_matching and self.signal_tracker:
                match_result = await self._match_to_signal(outcome)
                if match_result.matched:
                    outcome.signal_id = match_result.signal_id
                    outcome.status = SignalOutcomeStatus.MATCHED
                    self.metrics.signals_matched += 1

            # Add to pending batch
            async with self._lock:
                self._pending_outcomes.append(outcome)

                # Force flush if max pending reached
                if len(self._pending_outcomes) >= self.config.max_pending_outcomes:
                    await self._flush_outcomes()

            # Record latency
            latency = (datetime.now(UTC) - start_time).total_seconds()
            self.metrics.record_latency(latency)

            logger.debug(f"Processed fill: {outcome.order_id} in {latency:.3f}s")

        except Exception as e:
            logger.error(f"Error handling fill: {e}")
            self.metrics.errors_encountered += 1

    def _on_error(self, error: Exception) -> None:
        """Handle error from listener.

        Args:
            error: Exception that occurred
        """
        logger.error(f"Listener error: {error}")
        self.metrics.errors_encountered += 1

    async def _match_to_signal(self, outcome: SignalOutcome) -> OutcomeMatchResult:
        """Match outcome to originating signal.

        Args:
            outcome: Signal outcome to match

        Returns:
            OutcomeMatchResult with match details
        """
        if not self.signal_tracker:
            return OutcomeMatchResult(
                outcome=outcome,
                matched=False,
                match_method="no_tracker",
            )

        try:
            # Look for signals in the match window
            window_start = outcome.fill_timestamp - timedelta(
                hours=self.config.match_window_hours
            )
            window_end = outcome.fill_timestamp

            # Query signals for this symbol
            signals = await self.signal_tracker.get_signal_history(
                token=outcome.symbol.replace("USDT", ""),
                start_time_ms=int(window_start.timestamp() * 1000),
                end_time_ms=int(window_end.timestamp() * 1000),
                with_outcomes_only=False,
            )

            if not signals:
                return OutcomeMatchResult(
                    outcome=outcome,
                    matched=False,
                    match_method="no_signals",
                )

            # Try to match by order_id in metadata
            best_match = None
            best_confidence = 0.0

            for signal_with_outcome in signals:
                signal = signal_with_outcome.signal
                confidence = self._calculate_match_confidence(outcome, signal)

                if confidence > best_confidence:
                    best_confidence = confidence
                    best_match = signal

            if best_match and best_confidence > 0.5:
                return OutcomeMatchResult(
                    outcome=outcome,
                    signal_id=UUID(best_match.signal_id),
                    confidence=best_confidence,
                    matched=True,
                    match_method="metadata",
                )

            return OutcomeMatchResult(
                outcome=outcome,
                matched=False,
                confidence=best_confidence,
                match_method="no_match",
            )

        except Exception as e:
            logger.error(f"Signal matching error: {e}")
            return OutcomeMatchResult(
                outcome=outcome,
                matched=False,
                error=str(e),
            )

    def _calculate_match_confidence(
        self,
        outcome: SignalOutcome,
        signal: Any,
    ) -> float:
        """Calculate match confidence between outcome and signal.

        Args:
            outcome: Signal outcome
            signal: Signal record

        Returns:
            Confidence score 0.0-1.0
        """
        confidence = 0.0

        # Symbol match
        signal_symbol = signal.token.upper()
        outcome_symbol = outcome.symbol.replace("USDT", "").upper()
        if signal_symbol == outcome_symbol:
            confidence += 0.3

        # Direction match
        signal_direction = signal.direction.value.upper()
        outcome_side = outcome.side.upper()
        if (signal_direction == "LONG" and outcome_side == "BUY") or (
            signal_direction == "SHORT" and outcome_side == "SELL"
        ):
            confidence += 0.3

        # Time proximity (within 1 hour = full points)
        signal_time = datetime.fromtimestamp(signal.timestamp / 1000, tz=UTC)
        time_diff = abs((outcome.fill_timestamp - signal_time).total_seconds())
        if time_diff < 3600:  # 1 hour
            confidence += 0.4
        elif time_diff < 7200:  # 2 hours
            confidence += 0.2

        return min(confidence, 1.0)

    async def _flush_loop(self) -> None:
        """Background loop to periodically flush pending outcomes."""
        while self._running:
            try:
                await asyncio.sleep(self.config.flush_interval_seconds)

                async with self._lock:
                    if self._pending_outcomes:
                        await self._flush_outcomes()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Flush loop error: {e}")

    async def _flush_outcomes(self) -> None:
        """Flush pending outcomes to database."""
        if not self._pending_outcomes:
            return

        outcomes_to_store = self._pending_outcomes[:]
        self._pending_outcomes.clear()

        try:
            await self._store_outcomes(outcomes_to_store)
            self.metrics.outcomes_stored += len(outcomes_to_store)
            logger.debug(f"Flushed {len(outcomes_to_store)} outcomes")
        except Exception as e:
            logger.error(f"Failed to flush outcomes: {e}")
            # Re-add to pending for retry
            self._pending_outcomes.extend(outcomes_to_store)

    async def _store_outcome(self, outcome: SignalOutcome) -> None:
        """Store a single outcome in database.

        Args:
            outcome: Outcome to store
        """
        await self._store_outcomes([outcome])

    async def _store_outcomes(self, outcomes: list[SignalOutcome]) -> None:
        """Store multiple outcomes in database.

        Args:
            outcomes: List of outcomes to store
        """
        if not self.db_pool or not outcomes:
            return

        try:
            async with self.db_pool.acquire() as conn:
                # Build insert query
                values = []
                for outcome in outcomes:
                    values.append(
                        (
                            str(outcome.outcome_id),
                            str(outcome.signal_id) if outcome.signal_id else None,
                            outcome.order_id,
                            outcome.symbol,
                            outcome.side,
                            float(outcome.fill_price),
                            float(outcome.fill_quantity),
                            outcome.fill_timestamp,
                            outcome.outcome_type.value,
                            float(outcome.pnl) if outcome.pnl else None,
                            float(outcome.fee) if outcome.fee else None,
                            outcome.status.value,
                            outcome.created_at,
                        )
                    )

                await conn.executemany(
                    """
                    INSERT INTO signal_outcomes (
                        outcome_id, signal_id, order_id, symbol, side,
                        fill_price, fill_quantity, fill_timestamp,
                        outcome_type, pnl, fee, status, created_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                    ON CONFLICT (outcome_id) DO NOTHING
                    """,
                    values,
                )

        except Exception as e:
            logger.error(f"Database error storing outcomes: {e}")
            raise

    async def __aenter__(self) -> OutcomeCaptureService:
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.stop()
