"""Outcome Capture Integration for paper trading.

Provides integration between paper trading execution and outcome persistence,
including Discord notifications via TradeNotifier.

For NOTIFIER-TEST-001: Sanity Trade with Discord Notifications
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

if TYPE_CHECKING:
    from execution.paper.models import PaperTradeResult
    from ml.models.signal_outcome import SignalOutcome

logger = logging.getLogger(__name__)


@dataclass
class OutcomeCaptureResult:
    """Result of outcome capture attempt.

    Attributes:
        success: Whether capture was successful
        outcome_id: The canonical outcome ID
        correlation_id: Correlation ID linking the event chain
        discord_message_id: Discord message ID (if notification sent)
        persisted_to: Where outcome was persisted ("postgres", "redis", "memory")
        error: Error message if failed
    """

    success: bool
    outcome_id: str | None = None
    correlation_id: str | None = None
    discord_message_id: str | None = None
    persisted_to: str | None = None
    error: str | None = None


class OutcomeCaptureIntegration:
    """Integration for capturing trade outcomes and sending notifications.

    Handles:
    - Converting PaperTradeResult to SignalOutcome
    - Sending Discord notifications via TradeNotifier
    - Persisting outcomes to PostgreSQL (or Redis as fallback)
    - Tracking correlation IDs for event chain linking

    Attributes:
        trade_notifier: TradeNotifier instance for Discord alerts
        redis_client: Redis client for fallback persistence
        db_pool: PostgreSQL connection pool (if available)
        correlation_id: Current correlation ID for tracing
    """

    def __init__(
        self,
        trade_notifier: Any | None = None,
        redis_client: Any | None = None,
        db_pool: Any | None = None,
    ) -> None:
        """Initialize outcome capture integration.

        Args:
            trade_notifier: TradeNotifier instance (created if None)
            redis_client: Redis client for fallback persistence
            db_pool: PostgreSQL connection pool
        """
        self._trade_notifier = trade_notifier
        self._redis = redis_client
        self._db_pool = db_pool
        self._correlation_id: str = ""

        # Lazy initialization flags
        self._notifier_initialized = False

    async def _get_notifier(self) -> Any:
        """Get or create TradeNotifier instance."""
        if self._trade_notifier is None and not self._notifier_initialized:
            try:
                from discord_alerts.trade_notifier import TradeNotifier

                self._trade_notifier = TradeNotifier()
                self._notifier_initialized = True
            except Exception as e:
                logger.warning(f"Failed to initialize TradeNotifier: {e}")
                self._notifier_initialized = True  # Don't retry
        return self._trade_notifier

    async def _get_redis(self) -> Any | None:
        """Get or create Redis client."""
        if self._redis is None:
            try:
                import redis as redis_lib

                redis_host = os.getenv("REDIS_HOST", "host.docker.internal")
                redis_port = int(os.getenv("REDIS_PORT", "6380"))
                self._redis = redis_lib.Redis(
                    host=redis_host,
                    port=redis_port,
                    decode_responses=True,
                )
                # Test connection
                self._redis.ping()
            except Exception as e:
                logger.debug(f"Redis not available: {e}")
                self._redis = None
        return self._redis

    async def _get_db_pool(self) -> Any | None:
        """Get or create PostgreSQL connection pool."""
        if self._db_pool is None:
            try:
                import asyncpg

                db_host = os.getenv("POSTGRES_HOST", "host.docker.internal")
                db_port = int(os.getenv("POSTGRES_PORT", "5434"))
                db_name = os.getenv("POSTGRES_DB", "chiseai")
                db_user = os.getenv("POSTGRES_USER", "chiseai")
                db_pass = os.getenv("POSTGRES_PASSWORD", "chiseai")

                dsn = f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
                self._db_pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
            except Exception as e:
                logger.debug(f"PostgreSQL not available: {e}")
                self._db_pool = None
        return self._db_pool

    def _generate_correlation_id(self) -> str:
        """Generate a new correlation ID."""
        self._correlation_id = str(uuid4())
        return self._correlation_id

    def _convert_to_signal_outcome(
        self,
        trade_result: PaperTradeResult,
        correlation_id: str,
    ) -> SignalOutcome:
        """Convert PaperTradeResult to SignalOutcome.

        Args:
            trade_result: The paper trade result
            correlation_id: Correlation ID for tracing

        Returns:
            SignalOutcome instance
        """
        from ml.models.signal_outcome import (
            OutcomeType,
            SignalOutcome,
            SignalOutcomeStatus,
        )

        # Extract signal information
        signal = trade_result.signal
        signal_id = None
        symbol = ""
        direction = ""
        confidence = 0.0

        if signal:
            signal_id = getattr(signal, "signal_id", None)
            symbol = getattr(signal, "token", "") or getattr(signal, "symbol", "")
            direction_attr = getattr(signal, "direction", None)
            direction = (
                direction_attr.value
                if hasattr(direction_attr, "value")
                else str(direction_attr)
            )
            confidence = getattr(signal, "confidence", 0.0)

        # Extract order information
        order = trade_result.order
        order_id = order.order_id if order else ""
        fill_price = Decimal("0")
        fill_quantity = Decimal("0")
        entry_time = datetime.now(UTC)

        if order and order.fills:
            # Use first fill for entry data
            first_fill = order.fills[0]
            fill_price = Decimal(str(first_fill.price))
            fill_quantity = Decimal(str(first_fill.quantity))
            entry_time = first_fill.timestamp
        elif order:
            fill_price = (
                Decimal(str(order.avg_fill_price))
                if order.avg_fill_price
                else Decimal("0")
            )
            fill_quantity = Decimal(str(order.filled_quantity))

        # Determine side from direction
        side = (
            "Buy"
            if direction.upper() == "LONG"
            else "Sell"
            if direction.upper() == "SHORT"
            else ""
        )

        # Create outcome
        outcome = SignalOutcome(
            signal_id=UUID(signal_id) if signal_id else None,
            order_id=order_id,
            symbol=symbol,
            side=side,
            direction=direction.upper(),
            fill_price=fill_price,
            fill_quantity=fill_quantity,
            fill_timestamp=entry_time,
            outcome_type=OutcomeType.UNKNOWN,
            status=SignalOutcomeStatus.FILLED
            if trade_result.status.value == "executed"
            else SignalOutcomeStatus.ERROR,
            entry_price=fill_price,
            entry_time=entry_time,
            position_size=fill_quantity,
            leverage=Decimal("1.0"),
            entry_reason="signal_trigger",
            metadata={
                "correlation_id": correlation_id,
                "latency_ms": trade_result.latency_ms,
                "confidence": confidence,
                "trade_status": trade_result.status.value
                if hasattr(trade_result.status, "value")
                else str(trade_result.status),
            },
        )

        return outcome

    async def _persist_to_postgres(self, outcome: SignalOutcome) -> bool:
        """Persist outcome to PostgreSQL.

        Args:
            outcome: The SignalOutcome to persist

        Returns:
            True if successful, False otherwise
        """
        pool = await self._get_db_pool()
        if pool is None:
            return False

        try:
            async with pool.acquire() as conn:
                # Check if table exists, create if not
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS signal_outcomes (
                        outcome_id UUID PRIMARY KEY,
                        signal_id UUID,
                        order_id TEXT,
                        symbol TEXT,
                        token TEXT,
                        side TEXT,
                        direction TEXT,
                        fill_price NUMERIC,
                        fill_quantity NUMERIC,
                        fill_timestamp TIMESTAMPTZ,
                        outcome_type TEXT,
                        pnl NUMERIC,
                        fee NUMERIC,
                        status TEXT,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        entry_price NUMERIC,
                        exit_price NUMERIC,
                        entry_time TIMESTAMPTZ,
                        exit_time TIMESTAMPTZ,
                        leverage NUMERIC,
                        entry_reason TEXT,
                        position_size NUMERIC,
                        metadata JSONB
                    )
                    """
                )

                # Insert outcome
                await conn.execute(
                    """
                    INSERT INTO signal_outcomes (
                        outcome_id, signal_id, order_id, symbol, token, side, direction,
                        fill_price, fill_quantity, fill_timestamp, outcome_type, pnl, fee,
                        status, entry_price, exit_price, entry_time, exit_time,
                        leverage, entry_reason, position_size, metadata
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14,
                              $15, $16, $17, $18, $19, $20, $21, $22)
                    ON CONFLICT (outcome_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        exit_price = EXCLUDED.exit_price,
                        exit_time = EXCLUDED.exit_time,
                        pnl = EXCLUDED.pnl,
                        metadata = EXCLUDED.metadata
                    """,
                    outcome.outcome_id,
                    outcome.signal_id,
                    outcome.order_id,
                    outcome.symbol,
                    outcome.token,
                    outcome.side,
                    outcome.direction,
                    float(outcome.fill_price),
                    float(outcome.fill_quantity),
                    outcome.fill_timestamp,
                    outcome.outcome_type.value,
                    float(outcome.pnl) if outcome.pnl else None,
                    float(outcome.fee) if outcome.fee else None,
                    outcome.status.value,
                    float(outcome.entry_price),
                    float(outcome.exit_price) if outcome.exit_price else None,
                    outcome.entry_time,
                    outcome.exit_time,
                    float(outcome.leverage),
                    outcome.entry_reason,
                    float(outcome.position_size),
                    json.dumps(outcome.metadata),
                )

            logger.info(f"Persisted outcome {outcome.outcome_id} to PostgreSQL")
            return True

        except Exception as e:
            logger.error(f"Failed to persist to PostgreSQL: {e}")
            return False

    async def _persist_to_redis(self, outcome: SignalOutcome) -> bool:
        """Persist outcome to Redis as fallback.

        Args:
            outcome: The SignalOutcome to persist

        Returns:
            True if successful, False otherwise
        """
        redis = await self._get_redis()
        if redis is None:
            return False

        try:
            # Store outcome as JSON
            key = f"chiseai:outcomes:{outcome.outcome_id}"
            redis.set(key, json.dumps(outcome.to_dict()))

            # Also add to index for querying
            index_key = "chiseai:outcomes:index"
            redis.lpush(index_key, str(outcome.outcome_id))
            redis.ltrim(index_key, 0, 9999)  # Keep last 10000

            # Set TTL (7 days)
            redis.expire(key, 604800)
            redis.expire(index_key, 604800)

            logger.info(f"Persisted outcome {outcome.outcome_id} to Redis")
            return True

        except Exception as e:
            logger.error(f"Failed to persist to Redis: {e}")
            return False

    async def _persist_outcome(self, outcome: SignalOutcome) -> tuple[bool, str]:
        """Persist outcome to storage.

        Tries PostgreSQL first, falls back to Redis.

        Args:
            outcome: The SignalOutcome to persist

        Returns:
            Tuple of (success, storage_type)
        """
        # Try PostgreSQL first
        if await self._persist_to_postgres(outcome):
            return True, "postgres"

        # Fall back to Redis
        if await self._persist_to_redis(outcome):
            return True, "redis"

        return False, "none"

    async def on_trade_result(
        self,
        trade_result: PaperTradeResult,
    ) -> OutcomeCaptureResult:
        """Handle trade result - convert, notify, persist.

        Args:
            trade_result: The paper trade result

        Returns:
            OutcomeCaptureResult with outcome_id and correlation_id
        """
        # Generate correlation ID
        correlation_id = self._generate_correlation_id()

        try:
            # Convert to SignalOutcome
            outcome = self._convert_to_signal_outcome(trade_result, correlation_id)
            logger.info(f"Converted trade result to outcome: {outcome.outcome_id}")

            # Send Discord notification for trade opens
            discord_message_id = None
            notifier = await self._get_notifier()
            if notifier and trade_result.status.value == "executed":
                try:
                    notification_result = await notifier.send_trade_open_notification(
                        outcome
                    )
                    if notification_result.success:
                        discord_message_id = notification_result.message_id
                        logger.info(f"Discord notification sent: {discord_message_id}")
                    else:
                        logger.warning(
                            f"Discord notification failed: {notification_result.error}"
                        )
                except Exception as e:
                    logger.error(f"Failed to send Discord notification: {e}")

            # Persist outcome
            persisted, storage_type = await self._persist_outcome(outcome)
            if not persisted:
                logger.error("Failed to persist outcome to any storage")
                return OutcomeCaptureResult(
                    success=False,
                    outcome_id=str(outcome.outcome_id),
                    correlation_id=correlation_id,
                    discord_message_id=discord_message_id,
                    error="Failed to persist outcome",
                )

            logger.info(
                f"Outcome captured: {outcome.outcome_id} (correlation: {correlation_id})"
            )

            return OutcomeCaptureResult(
                success=True,
                outcome_id=str(outcome.outcome_id),
                correlation_id=correlation_id,
                discord_message_id=discord_message_id,
                persisted_to=storage_type,
            )

        except Exception as e:
            logger.exception("Failed to capture trade outcome")
            return OutcomeCaptureResult(
                success=False,
                correlation_id=correlation_id,
                error=str(e),
            )

    async def on_position_close(
        self,
        position: Any,
        exit_price: float,
        realized_pnl: float,
        correlation_id: str | None = None,
        reason: str = "manual",
    ) -> OutcomeCaptureResult:
        """Handle position close - convert, notify, persist.

        Args:
            position: The closed position object
            exit_price: The exit price
            realized_pnl: The realized PnL
            correlation_id: Correlation ID for tracing (from position metadata or new)
            reason: Reason for closing the position

        Returns:
            OutcomeCaptureResult with outcome_id and correlation_id
        """
        from ml.models.signal_outcome import (
            OutcomeType,
            SignalOutcome,
            SignalOutcomeStatus,
        )

        # Get or generate correlation_id
        if correlation_id is None:
            correlation_id = (
                position.metadata.get("correlation_id") if position.metadata else None
            )
        if correlation_id is None:
            correlation_id = self._generate_correlation_id()

        try:
            # Extract metadata from position
            signal_id = (
                position.metadata.get("signal_id") if position.metadata else None
            )
            order_id = position.metadata.get("order_id") if position.metadata else None
            leverage = (
                Decimal(str(position.metadata.get("leverage", 1.0)))
                if position.metadata
                else Decimal("1.0")
            )

            # Determine side from position side
            side = "Buy" if position.side == "long" else "Sell"
            direction = position.side.upper()

            # Parse signal_id as UUID if valid, otherwise store in metadata
            signal_uuid = None
            if signal_id:
                try:
                    signal_uuid = UUID(signal_id)
                except ValueError:
                    # signal_id is not a valid UUID, store it in metadata instead
                    logger.debug(
                        f"signal_id '{signal_id}' is not a valid UUID, storing in metadata"
                    )

            # Create SignalOutcome for the closed position
            outcome = SignalOutcome(
                outcome_id=uuid4(),
                signal_id=signal_uuid,
                order_id=order_id or "",
                symbol=position.symbol,
                side=side,
                direction=direction,
                entry_price=Decimal(str(position.entry_price)),
                exit_price=Decimal(str(exit_price)),
                entry_time=position.opened_at,
                exit_time=datetime.now(UTC),
                pnl=Decimal(str(realized_pnl)),
                position_size=Decimal(str(position.quantity)),
                leverage=leverage,
                fill_price=Decimal(
                    str(exit_price)
                ),  # For close, fill_price is exit_price
                fill_quantity=Decimal(str(position.quantity)),
                fill_timestamp=datetime.now(UTC),
                outcome_type=OutcomeType.MANUAL_CLOSE
                if reason == "manual"
                else OutcomeType.UNKNOWN,
                status=SignalOutcomeStatus.CLOSED,
                metadata={
                    "correlation_id": correlation_id,
                    "close_reason": reason,
                    "position_id": getattr(position, "position_id", ""),
                    "original_signal_id": signal_id
                    if signal_id and not signal_uuid
                    else None,
                },
            )

            logger.info(
                f"Created close outcome: {outcome.outcome_id} for position {getattr(position, 'position_id', 'unknown')}"
            )

            # Send Discord close notification
            discord_message_id = None
            notifier = await self._get_notifier()
            if notifier:
                try:
                    notification_result = await notifier.send_trade_close_notification(
                        outcome
                    )
                    if notification_result.success:
                        discord_message_id = notification_result.message_id
                        logger.info(
                            f"Discord close notification sent: {discord_message_id}"
                        )
                    else:
                        logger.warning(
                            f"Discord close notification failed: {notification_result.error}"
                        )
                except Exception as e:
                    logger.error(f"Failed to send Discord close notification: {e}")

            # Persist outcome
            persisted, storage_type = await self._persist_outcome(outcome)
            if not persisted:
                logger.error("Failed to persist close outcome to any storage")
                return OutcomeCaptureResult(
                    success=False,
                    outcome_id=str(outcome.outcome_id),
                    correlation_id=correlation_id,
                    discord_message_id=discord_message_id,
                    error="Failed to persist close outcome",
                )

            logger.info(
                f"Close outcome captured: {outcome.outcome_id} (correlation: {correlation_id})"
            )

            return OutcomeCaptureResult(
                success=True,
                outcome_id=str(outcome.outcome_id),
                correlation_id=correlation_id,
                discord_message_id=discord_message_id,
                persisted_to=storage_type,
            )

        except Exception as e:
            logger.exception("Failed to capture position close outcome")
            return OutcomeCaptureResult(
                success=False,
                correlation_id=correlation_id,
                error=str(e),
            )

    async def close(self) -> None:
        """Close resources."""
        if self._trade_notifier:
            try:
                await self._trade_notifier.close()
            except Exception as e:
                logger.debug(f"Error closing notifier: {e}")

        if self._db_pool:
            try:
                await self._db_pool.close()
            except Exception as e:
                logger.debug(f"Error closing DB pool: {e}")
