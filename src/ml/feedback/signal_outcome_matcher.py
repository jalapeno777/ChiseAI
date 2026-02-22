"""Signal-to-Outcome Matcher Service.

This module provides the main service for matching trade outcomes (from Bybit fills)
to their originating signals. It builds on top of the outcome capture service and
provides sophisticated matching logic with configurable time windows per timeframe.

Key Features:
- Match outcomes to signals with >95% confidence
- Timeframe-specific matching windows
- Database updates with match metadata
- InfluxDB metrics export for monitoring

For ST-LAUNCH-006: Signal-to-Outcome Matching
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from influxdb_client import InfluxDBClient

from src.ml.models.signal_outcome import (
    OutcomeMatchResult,
    OutcomeType,
    SignalOutcome,
    SignalOutcomeStatus,
)

logger = logging.getLogger(__name__)


# Timeframe to matching window mapping (in hours)
# Based on task requirements:
# - 1m: 30min (0.5h)
# - 5m: 2h
# - 15m: 6h
# - 1h: 24h
# - 4h: 72h (3d)
# - 1d: 168h (7d)
DEFAULT_MATCH_WINDOWS: dict[str, float] = {
    "1m": 0.5,
    "3m": 1.0,
    "5m": 2.0,
    "15m": 6.0,
    "30m": 12.0,
    "1h": 24.0,
    "2h": 36.0,
    "4h": 72.0,
    "6h": 96.0,
    "8h": 120.0,
    "12h": 144.0,
    "1d": 168.0,
    "3d": 336.0,
    "1w": 504.0,
}


@dataclass
class SignalMatcherConfig:
    """Configuration for signal-outcome matching.

    Attributes:
        default_match_window_hours: Default window if timeframe not specified
        timeframe_windows: Per-timeframe matching windows (hours)
        min_confidence_threshold: Minimum confidence for valid match (0.0-1.0)
        symbol_match_weight: Weight for symbol matching in confidence calc
        direction_match_weight: Weight for direction matching in confidence calc
        time_proximity_weight: Weight for time proximity in confidence calc
        enable_influxdb_export: Whether to export metrics to InfluxDB
        influxdb_bucket: InfluxDB bucket for metrics
        influxdb_org: InfluxDB organization
        batch_size: Number of outcomes to process in batch
        max_concurrent_matches: Maximum concurrent matching operations
    """

    default_match_window_hours: float = 24.0
    timeframe_windows: dict[str, float] = field(default_factory=dict)
    min_confidence_threshold: float = 0.95
    symbol_match_weight: float = 0.3
    direction_match_weight: float = 0.3
    time_proximity_weight: float = 0.4
    enable_influxdb_export: bool = True
    influxdb_bucket: str = "signal_matches"
    influxdb_org: str = "chiseai"
    batch_size: int = 100
    max_concurrent_matches: int = 10

    def __post_init__(self) -> None:
        """Merge default windows with custom windows."""
        merged = DEFAULT_MATCH_WINDOWS.copy()
        merged.update(self.timeframe_windows)
        self.timeframe_windows = merged

    def get_window_for_timeframe(self, timeframe: str | None) -> float:
        """Get matching window for a specific timeframe.

        Args:
            timeframe: Timeframe string (e.g., "1h", "4h")

        Returns:
            Matching window in hours
        """
        if timeframe and timeframe in self.timeframe_windows:
            return self.timeframe_windows[timeframe]
        return self.default_match_window_hours


@dataclass
class MatchMetadata:
    """Metadata for a signal-outcome match.

    Attributes:
        matched_signal_id: UUID of the matched signal
        match_confidence: Confidence score (0.0-1.0)
        match_method: Method used for matching
        match_timestamp: When the match was made
        timeframe: Timeframe of the signal
        window_hours: Matching window used (hours)
        symbol_match: Whether symbol matched
        direction_match: Whether direction matched
        time_diff_seconds: Time difference between signal and outcome
    """

    matched_signal_id: UUID | None = None
    match_confidence: float = 0.0
    match_method: str = ""
    match_timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    timeframe: str = ""
    window_hours: float = 0.0
    symbol_match: bool = False
    direction_match: bool = False
    time_diff_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            "matched_signal_id": str(self.matched_signal_id)
            if self.matched_signal_id
            else None,
            "match_confidence": round(self.match_confidence, 4),
            "match_method": self.match_method,
            "match_timestamp": self.match_timestamp.isoformat(),
            "timeframe": self.timeframe,
            "window_hours": self.window_hours,
            "symbol_match": self.symbol_match,
            "direction_match": self.direction_match,
            "time_diff_seconds": round(self.time_diff_seconds, 2),
        }


@dataclass
class MatcherMetrics:
    """Metrics for signal matching operations.

    Attributes:
        outcomes_processed: Total outcomes processed
        outcomes_matched: Total outcomes matched to signals
        outcomes_unmatched: Total outcomes not matched
        high_confidence_matches: Matches with confidence >= 0.95
        avg_confidence: Average match confidence
        avg_match_latency_seconds: Average time to match
        errors_encountered: Number of errors
        last_match_timestamp: Timestamp of last successful match
    """

    outcomes_processed: int = 0
    outcomes_matched: int = 0
    outcomes_unmatched: int = 0
    high_confidence_matches: int = 0
    avg_confidence: float = 0.0
    avg_match_latency_seconds: float = 0.0
    errors_encountered: int = 0
    last_match_timestamp: datetime | None = None
    _confidence_sum: float = field(default=0.0, repr=False)
    _latency_sum: float = field(default=0.0, repr=False)
    _match_count: int = field(default=0, repr=False)

    def record_match(self, confidence: float, latency_seconds: float) -> None:
        """Record a successful match."""
        self.outcomes_matched += 1
        self._confidence_sum += confidence
        self._match_count += 1
        self.avg_confidence = self._confidence_sum / self._match_count
        self._latency_sum += latency_seconds
        self.avg_match_latency_seconds = self._latency_sum / self._match_count
        self.last_match_timestamp = datetime.now(UTC)

        if confidence >= 0.95:
            self.high_confidence_matches += 1

    def record_unmatched(self) -> None:
        """Record an unmatched outcome."""
        self.outcomes_unmatched += 1

    def record_error(self) -> None:
        """Record an error."""
        self.errors_encountered += 1

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "outcomes_processed": self.outcomes_processed,
            "outcomes_matched": self.outcomes_matched,
            "outcomes_unmatched": self.outcomes_unmatched,
            "high_confidence_matches": self.high_confidence_matches,
            "avg_confidence": round(self.avg_confidence, 4),
            "avg_match_latency_seconds": round(self.avg_match_latency_seconds, 3),
            "errors_encountered": self.errors_encountered,
            "last_match_timestamp": (
                self.last_match_timestamp.isoformat()
                if self.last_match_timestamp
                else None
            ),
        }


class SignalOutcomeMatcher:
    """Service for matching trade outcomes to originating signals.

    This service provides sophisticated matching logic that:
    - Queries outcomes from the signal_outcomes table
    - Matches them to signals using order_id, symbol, timestamp
    - Calculates confidence scores (target: >95%)
    - Updates outcomes with match metadata
    - Exports metrics to InfluxDB

    Usage:
        config = SignalMatcherConfig(min_confidence_threshold=0.95)
        matcher = SignalOutcomeMatcher(
            config=config,
            db_pool=postgres_pool,
            influxdb_client=influx_client,
        )

        # Process pending outcomes
        await matcher.process_pending_outcomes()

        # Or match a specific outcome
        result = await matcher.match_outcome(outcome)
    """

    def __init__(
        self,
        config: SignalMatcherConfig | None = None,
        db_pool: Any | None = None,
        influxdb_client: InfluxDBClient | None = None,
        signal_tracker: Any | None = None,
    ):
        """Initialize the matcher.

        Args:
            config: Matcher configuration
            db_pool: PostgreSQL connection pool
            influxdb_client: InfluxDB client for metrics export
            signal_tracker: Signal tracker for querying signals
        """
        self.config = config or SignalMatcherConfig()
        self.db_pool = db_pool
        self.influxdb = influxdb_client
        self.signal_tracker = signal_tracker
        self.metrics = MatcherMetrics()

        self._running = False
        self._semaphore = asyncio.Semaphore(self.config.max_concurrent_matches)

    async def process_pending_outcomes(
        self,
        limit: int | None = None,
        min_age_minutes: float = 5.0,
    ) -> list[OutcomeMatchResult]:
        """Process pending outcomes that haven't been matched yet.

        Args:
            limit: Maximum number of outcomes to process (None for all)
            min_age_minutes: Minimum age of outcomes before matching

        Returns:
            List of match results
        """
        if not self.db_pool:
            logger.warning(
                "No database pool available, cannot process pending outcomes"
            )
            return []

        results: list[OutcomeMatchResult] = []
        batch_size = self.config.batch_size
        offset = 0
        limit = limit or batch_size

        try:
            async with self.db_pool.acquire() as conn:
                # Query pending outcomes (status = 'filled' but no signal_id)
                rows = await conn.fetch(
                    """
                    SELECT outcome_id, order_id, symbol, side, fill_price,
                           fill_quantity, fill_timestamp, outcome_type, metadata
                    FROM signal_outcomes
                    WHERE status = 'filled'
                      AND signal_id IS NULL
                      AND created_at < NOW() - INTERVAL '%s minutes'
                    ORDER BY fill_timestamp ASC
                    LIMIT %s
                    """,
                    min_age_minutes,
                    limit,
                )

            if not rows:
                logger.debug("No pending outcomes to process")
                return []

            logger.info(f"Processing {len(rows)} pending outcomes")

            # Process outcomes concurrently with semaphore
            tasks = []
            for row in rows:
                outcome = self._row_to_outcome(row)
                task = asyncio.create_task(self._match_with_semaphore(outcome))
                tasks.append(task)

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Filter out exceptions
            valid_results = []
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"Match task failed: {result}")
                    self.metrics.record_error()
                else:
                    valid_results.append(result)

            # Update database with match results
            await self._update_outcomes_with_matches(valid_results)

            # Export metrics to InfluxDB
            if self.config.enable_influxdb_export:
                await self._export_metrics_to_influxdb()

            return valid_results

        except Exception as e:
            logger.error(f"Error processing pending outcomes: {e}")
            self.metrics.record_error()
            return []

    async def match_outcome(
        self,
        outcome: SignalOutcome,
        timeframe: str | None = None,
    ) -> OutcomeMatchResult:
        """Match a single outcome to its originating signal.

        Args:
            outcome: The outcome to match
            timeframe: Optional timeframe hint for the signal

        Returns:
            OutcomeMatchResult with match details
        """
        start_time = datetime.now(UTC)
        self.metrics.outcomes_processed += 1

        try:
            # Try to match by order_id first (highest confidence)
            match_result = await self._match_by_order_id(outcome)

            if not match_result.matched and self.signal_tracker:
                # Fall back to fuzzy matching
                match_result = await self._match_by_fuzzy(outcome, timeframe)

            # Record metrics
            latency = (datetime.now(UTC) - start_time).total_seconds()
            if match_result.matched:
                self.metrics.record_match(match_result.confidence, latency)
            else:
                self.metrics.record_unmatched()

            return match_result

        except Exception as e:
            logger.error(f"Error matching outcome {outcome.outcome_id}: {e}")
            self.metrics.record_error()
            return OutcomeMatchResult(
                outcome=outcome,
                matched=False,
                error=str(e),
            )

    async def get_match_statistics(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict[str, Any]:
        """Get match statistics from database.

        Args:
            start_time: Start of time range
            end_time: End of time range

        Returns:
            Statistics dictionary
        """
        if not self.db_pool:
            return {}

        start_time = start_time or datetime.now(UTC) - timedelta(days=1)
        end_time = end_time or datetime.now(UTC)

        try:
            async with self.db_pool.acquire() as conn:
                stats = await conn.fetchrow(
                    """
                    SELECT
                        COUNT(*) as total_outcomes,
                        COUNT(signal_id) as matched_outcomes,
                        AVG(match_confidence) as avg_confidence,
                        COUNT(CASE WHEN match_confidence >= 0.95 THEN 1 END) as high_confidence_matches,
                        COUNT(CASE WHEN outcome_type = 'tp_hit' THEN 1 END) as tp_hits,
                        COUNT(CASE WHEN outcome_type = 'sl_hit' THEN 1 END) as sl_hits,
                        COUNT(CASE WHEN outcome_type = 'manual_close' THEN 1 END) as manual_closes,
                        COUNT(CASE WHEN outcome_type = 'expired' THEN 1 END) as expired
                    FROM signal_outcomes
                    WHERE fill_timestamp BETWEEN $1 AND $2
                    """,
                    start_time,
                    end_time,
                )

            if stats:
                return {
                    "total_outcomes": stats["total_outcomes"],
                    "matched_outcomes": stats["matched_outcomes"],
                    "match_rate": (
                        stats["matched_outcomes"] / stats["total_outcomes"]
                        if stats["total_outcomes"] > 0
                        else 0.0
                    ),
                    "avg_confidence": float(stats["avg_confidence"] or 0),
                    "high_confidence_rate": (
                        stats["high_confidence_matches"] / stats["matched_outcomes"]
                        if stats["matched_outcomes"] > 0
                        else 0.0
                    ),
                    "outcome_breakdown": {
                        "tp_hit": stats["tp_hits"],
                        "sl_hit": stats["sl_hits"],
                        "manual_close": stats["manual_closes"],
                        "expired": stats["expired"],
                    },
                }
            return {}

        except Exception as e:
            logger.error(f"Error getting match statistics: {e}")
            return {}

    def get_metrics(self) -> MatcherMetrics:
        """Get current metrics."""
        return self.metrics

    async def _match_with_semaphore(
        self,
        outcome: SignalOutcome,
    ) -> OutcomeMatchResult:
        """Match outcome with concurrency control."""
        async with self._semaphore:
            return await self.match_outcome(outcome)

    async def _match_by_order_id(
        self,
        outcome: SignalOutcome,
    ) -> OutcomeMatchResult:
        """Try to match outcome by order_id in metadata.

        This is the highest confidence match method.
        """
        if not self.signal_tracker or not outcome.order_id:
            return OutcomeMatchResult(
                outcome=outcome,
                matched=False,
                match_method="no_order_id",
            )

        try:
            # Query signals that might have this order_id in metadata
            # This requires the signal tracker to support metadata queries
            window_hours = self.config.default_match_window_hours
            window_start = outcome.fill_timestamp - timedelta(hours=window_hours)

            signals = await self.signal_tracker.get_signal_history(
                token=outcome.symbol.replace("USDT", ""),
                start_time=int(window_start.timestamp() * 1000),
                end_time=int(outcome.fill_timestamp.timestamp() * 1000),
                with_outcomes_only=False,
            )

            # Look for signals with matching order_id in metadata
            for signal_with_outcome in signals:
                signal = signal_with_outcome.signal
                signal_metadata = getattr(signal, "metadata", {}) or {}
                signal_orders = signal_metadata.get("order_ids", [])

                if outcome.order_id in signal_orders:
                    # Direct order_id match - highest confidence
                    return OutcomeMatchResult(
                        outcome=outcome,
                        signal_id=UUID(signal.signal_id),
                        confidence=1.0,
                        matched=True,
                        match_method="order_id_exact",
                    )

            return OutcomeMatchResult(
                outcome=outcome,
                matched=False,
                match_method="order_id_not_found",
            )

        except Exception as e:
            logger.warning(f"Order ID matching failed: {e}")
            return OutcomeMatchResult(
                outcome=outcome,
                matched=False,
                error=str(e),
            )

    async def _match_by_fuzzy(
        self,
        outcome: SignalOutcome,
        timeframe: str | None = None,
    ) -> OutcomeMatchResult:
        """Match outcome using fuzzy matching (symbol, direction, time).

        Args:
            outcome: The outcome to match
            timeframe: Optional timeframe hint

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
            # Determine matching window based on timeframe
            window_hours = self.config.get_window_for_timeframe(timeframe)
            window_start = outcome.fill_timestamp - timedelta(hours=window_hours)

            # Query signals in the window
            token = outcome.symbol.replace("USDT", "")
            signals = await self.signal_tracker.get_signal_history(
                token=token,
                start_time=int(window_start.timestamp() * 1000),
                end_time=int(outcome.fill_timestamp.timestamp() * 1000),
                with_outcomes_only=False,
            )

            if not signals:
                return OutcomeMatchResult(
                    outcome=outcome,
                    matched=False,
                    match_method="no_signals",
                )

            # Find best match by confidence
            best_match = None
            best_confidence = 0.0
            best_metadata = None

            for signal_with_outcome in signals:
                signal = signal_with_outcome.signal
                confidence, metadata = self._calculate_match_confidence(
                    outcome, signal, window_hours
                )

                if confidence > best_confidence:
                    best_confidence = confidence
                    best_match = signal
                    best_metadata = metadata

            # Check if confidence meets threshold
            if best_match and best_confidence >= self.config.min_confidence_threshold:
                return OutcomeMatchResult(
                    outcome=outcome,
                    signal_id=UUID(best_match.signal_id),
                    confidence=best_confidence,
                    matched=True,
                    match_method="fuzzy",
                )

            return OutcomeMatchResult(
                outcome=outcome,
                matched=False,
                confidence=best_confidence,
                match_method="below_threshold",
            )

        except Exception as e:
            logger.error(f"Fuzzy matching error: {e}")
            return OutcomeMatchResult(
                outcome=outcome,
                matched=False,
                error=str(e),
            )

    def _calculate_match_confidence(
        self,
        outcome: SignalOutcome,
        signal: Any,
        window_hours: float,
    ) -> tuple[float, MatchMetadata]:
        """Calculate match confidence between outcome and signal.

        Args:
            outcome: Signal outcome
            signal: Signal record
            window_hours: Matching window in hours

        Returns:
            Tuple of (confidence score, match metadata)
        """
        confidence = 0.0
        metadata = MatchMetadata(
            timeframe=getattr(signal, "timeframe", ""),
            window_hours=window_hours,
        )

        # Symbol match
        signal_symbol = getattr(signal, "token", "").upper()
        outcome_symbol = outcome.symbol.replace("USDT", "").upper()
        if signal_symbol == outcome_symbol:
            confidence += self.config.symbol_match_weight
            metadata.symbol_match = True

        # Direction match
        signal_direction = getattr(signal, "direction", None)
        if signal_direction:
            direction_value = (
                signal_direction.value.upper()
                if hasattr(signal_direction, "value")
                else str(signal_direction).upper()
            )
            outcome_side = outcome.side.upper()

            if (direction_value == "LONG" and outcome_side == "BUY") or (
                direction_value == "SHORT" and outcome_side == "SELL"
            ):
                confidence += self.config.direction_match_weight
                metadata.direction_match = True

        # Time proximity (closer = higher confidence)
        signal_time_ms = getattr(signal, "timestamp", 0)
        signal_time = datetime.fromtimestamp(signal_time_ms / 1000, tz=UTC)
        time_diff = abs((outcome.fill_timestamp - signal_time).total_seconds())
        metadata.time_diff_seconds = time_diff

        # Calculate time proximity score
        # Full weight if within 10% of window, linear decay after
        window_seconds = window_hours * 3600
        if time_diff < window_seconds * 0.1:
            confidence += self.config.time_proximity_weight
        elif time_diff < window_seconds:
            # Linear decay
            time_score = 1.0 - (time_diff / window_seconds)
            confidence += self.config.time_proximity_weight * time_score

        metadata.match_confidence = min(confidence, 1.0)
        return min(confidence, 1.0), metadata

    async def _update_outcomes_with_matches(
        self,
        results: list[OutcomeMatchResult],
    ) -> None:
        """Update database with match results.

        Args:
            results: List of match results to persist
        """
        if not self.db_pool:
            return

        updates = []
        for result in results:
            if result.matched and result.signal_id:
                updates.append(
                    {
                        "outcome_id": str(result.outcome.outcome_id),
                        "signal_id": str(result.signal_id),
                        "confidence": result.confidence,
                        "method": result.match_method,
                    }
                )

        if not updates:
            return

        try:
            async with self.db_pool.acquire() as conn:
                for update in updates:
                    await conn.execute(
                        """
                        UPDATE signal_outcomes
                        SET signal_id = $1,
                            status = 'matched',
                            match_confidence = $2,
                            match_method = $3,
                            matched_at = NOW()
                        WHERE outcome_id = $4
                        """,
                        update["signal_id"],
                        update["confidence"],
                        update["method"],
                        update["outcome_id"],
                    )

            logger.info(f"Updated {len(updates)} outcomes with match results")

        except Exception as e:
            logger.error(f"Error updating outcomes: {e}")
            self.metrics.record_error()

    async def _export_metrics_to_influxdb(self) -> None:
        """Export match metrics to InfluxDB."""
        if not self.influxdb or not self.config.enable_influxdb_export:
            return

        try:
            from influxdb_client import Point
            from influxdb_client.client.write_api import SYNCHRONOUS

            write_api = self.influxdb.write_api(write_options=SYNCHRONOUS)

            # Create point for matcher metrics
            point = (
                Point("signal_matcher_metrics")
                .tag("service", "signal_outcome_matcher")
                .field("outcomes_processed", self.metrics.outcomes_processed)
                .field("outcomes_matched", self.metrics.outcomes_matched)
                .field("outcomes_unmatched", self.metrics.outcomes_unmatched)
                .field("high_confidence_matches", self.metrics.high_confidence_matches)
                .field("avg_confidence", self.metrics.avg_confidence)
                .field(
                    "avg_match_latency_seconds", self.metrics.avg_match_latency_seconds
                )
                .field("errors_encountered", self.metrics.errors_encountered)
                .time(datetime.now(UTC))
            )

            write_api.write(
                bucket=self.config.influxdb_bucket,
                org=self.config.influxdb_org,
                record=point,
            )

            logger.debug("Exported matcher metrics to InfluxDB")

        except Exception as e:
            logger.warning(f"Failed to export metrics to InfluxDB: {e}")

    def _row_to_outcome(self, row: Any) -> SignalOutcome:
        """Convert database row to SignalOutcome.

        Args:
            row: Database row

        Returns:
            SignalOutcome instance
        """
        return SignalOutcome(
            outcome_id=UUID(str(row["outcome_id"])),
            order_id=row["order_id"] or "",
            symbol=row["symbol"],
            side=row["side"],
            fill_price=Decimal(str(row["fill_price"])),
            fill_quantity=Decimal(str(row["fill_quantity"])),
            fill_timestamp=row["fill_timestamp"],
            outcome_type=OutcomeType(row["outcome_type"]),
            metadata=row["metadata"] or {},
            status=SignalOutcomeStatus.FILLED,
        )

    async def __aenter__(self) -> SignalOutcomeMatcher:
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        pass
