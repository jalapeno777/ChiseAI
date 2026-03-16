"""Signal Consumer for Redis → Orchestrator bridge.

Polls Redis for actionable signals and submits them to the paper trading
orchestrator for execution.

Part of P0-REPAIR-001: Fix Signal Consumer
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from execution.paper.orchestrator import PaperTradingOrchestrator
    from signal_generation.models import Signal

import contextlib

from signal_generation.models import SignalDirection, SignalStatus

logger = logging.getLogger(__name__)


class SignalConsumer:
    """Consumes signals from Redis and submits them to the orchestrator.

    This class bridges the gap between Redis signal storage and the paper
    trading orchestrator. It polls Redis for signals with status="actionable",
    converts them to Signal objects, and submits them for execution.

    Attributes:
        orchestrator: The paper trading orchestrator instance
        redis_client: Redis client for signal retrieval
        poll_interval: Seconds between polling cycles
        running: Whether the consumer is actively polling
        processed_signals: Set of signal IDs that have been processed
    """

    DEFAULT_POLL_INTERVAL = 5.0  # seconds
    REDIS_KEY_PATTERN = "paper:signal:*"
    PROCESSED_SET_KEY = "paper:signals:processed"

    def __init__(
        self,
        orchestrator: PaperTradingOrchestrator,
        redis_client: Any | None = None,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        symbol_throttle_seconds: float | None = None,
    ):
        """Initialize the signal consumer.

        Args:
            orchestrator: Paper trading orchestrator instance
            redis_client: Redis client (if None, creates new connection)
            poll_interval: Seconds between polling cycles
            symbol_throttle_seconds: Minimum seconds between submissions per symbol.
                If None, uses SYMBOL_EVAL_INTERVAL_SECONDS env (default 300s).
        """
        self.orchestrator = orchestrator
        self.poll_interval = poll_interval
        if symbol_throttle_seconds is None:
            symbol_throttle_seconds = float(
                os.getenv("SYMBOL_EVAL_INTERVAL_SECONDS", "300")
            )
        self.symbol_throttle_seconds = max(0.0, float(symbol_throttle_seconds))
        symbols_raw = os.getenv("TRADING_SYMBOLS", "BTC/USDT")
        self.allowed_symbols = {
            s.strip().upper() for s in symbols_raw.split(",") if s.strip()
        }
        self._running = False
        self._poll_task: asyncio.Task | None = None
        self._processed_signals: set[str] = set()
        self._last_symbol_submit_ts: dict[str, float] = {}

        # Initialize Redis client
        if redis_client is not None:
            self._redis = redis_client
            self._owns_redis = False
        else:
            self._redis = None
            self._owns_redis = True

        logger.info(
            "SignalConsumer initialized: poll_interval=%ss, symbol_throttle_seconds=%ss, allowed_symbols=%s",
            poll_interval,
            self.symbol_throttle_seconds,
            sorted(self.allowed_symbols),
        )

    async def _get_redis(self) -> Any:
        """Get or create Redis client."""
        if self._redis is None:
            import redis.asyncio as redis

            self._redis = redis.Redis(
                host="host.docker.internal",
                port=6380,
                decode_responses=True,
            )
        return self._redis

    async def start(self) -> None:
        """Start the signal consumer polling loop."""
        if self._running:
            logger.warning("SignalConsumer already running")
            return

        self._running = True
        start_time = datetime.now(UTC)

        # Load previously processed signals from Redis set
        await self._load_processed_signals()

        # Start polling task
        self._poll_task = asyncio.create_task(self._polling_loop())

        # Set health marker in Redis
        await self._set_health_marker(start_time)

        logger.info(
            f"SignalConsumer started: poll_interval={self.poll_interval}s, "
            f"processed_signals={len(self._processed_signals)}"
        )

    async def stop(self) -> None:
        """Stop the signal consumer gracefully."""
        if not self._running:
            return

        self._running = False

        # Cancel polling task
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._poll_task

        # Close Redis connection if we own it
        if self._owns_redis and self._redis:
            await self._redis.close()
            self._redis = None

        # Clear health marker
        await self._clear_health_marker()

        logger.info("SignalConsumer stopped")

    async def _load_processed_signals(self) -> None:
        """Load the set of already processed signal IDs from Redis."""
        try:
            redis = await self._get_redis()
            processed = await redis.smembers(self.PROCESSED_SET_KEY)
            self._processed_signals = set(processed)
            logger.debug(f"Loaded {len(self._processed_signals)} processed signal IDs")
        except Exception as e:
            logger.warning(f"Failed to load processed signals: {e}")
            self._processed_signals = set()

    async def _set_health_marker(self, start_time: datetime) -> None:
        """Set a health marker in Redis to indicate consumer is active.

        Args:
            start_time: When the consumer was started
        """
        try:
            redis = await self._get_redis()
            health_data = {
                "status": "active",
                "started_at": start_time.isoformat(),
                "poll_interval": str(self.poll_interval),
                "processed_count": str(len(self._processed_signals)),
            }
            await redis.hset("paper:signal_consumer:health", mapping=health_data)
            logger.debug("Health marker set in Redis")
        except Exception as e:
            logger.warning(f"Failed to set health marker: {e}")

    async def _clear_health_marker(self) -> None:
        """Clear the health marker when consumer stops."""
        try:
            redis = await self._get_redis()
            await redis.delete("paper:signal_consumer:health")
            logger.debug("Health marker cleared from Redis")
        except Exception as e:
            logger.warning(f"Failed to clear health marker: {e}")

    async def _mark_signal_processed(self, signal_id: str) -> None:
        """Mark a signal as processed in Redis.

        Args:
            signal_id: The unique signal identifier
        """
        try:
            redis = await self._get_redis()
            await redis.sadd(self.PROCESSED_SET_KEY, signal_id)
            self._processed_signals.add(signal_id)
        except Exception as e:
            logger.warning(f"Failed to mark signal {signal_id} as processed: {e}")

    async def _update_signal_status(self, redis_key: str, new_status: str) -> None:
        """Update the status field of a signal in Redis.

        Args:
            redis_key: Full Redis key for the signal hash
            new_status: New status value
        """
        try:
            redis = await self._get_redis()
            await redis.hset(redis_key, "status", new_status)
        except Exception as e:
            logger.warning(f"Failed to update status for {redis_key}: {e}")

    async def _get_signal_data(self, redis: Any, key: str) -> dict[str, Any] | None:
        """Get signal data from Redis, handling both hash and string (JSON) formats.

        Signals can be stored in two formats:
        - Hash format (from continuous_signal_generator.py): Use HGETALL
        - String format (from OutcomePersistence.persist_signal): Use GET + JSON parse

        Args:
            redis: Redis client
            key: Signal key to retrieve

        Returns:
            Dictionary with signal data or None if not found/invalid
        """
        import json

        try:
            key_type = await redis.type(key)
            if key_type == "hash":
                signal_data = await redis.hgetall(key)
                if signal_data:
                    return signal_data
                return None

            if key_type == "string":
                raw_data = await redis.get(key)
                if raw_data:
                    return json.loads(raw_data)
                return None

            if key_type not in ("none", "hash", "string"):
                logger.debug("Skipping key %s with unsupported type %s", key, key_type)

            return None

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON for signal {key}: {e}")
            return None
        except Exception as e:
            logger.warning(f"Failed to get signal data for {key}: {e}")
            return None

    async def _polling_loop(self) -> None:
        """Main polling loop for signal consumption."""
        while self._running:
            try:
                await self._poll_once()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in polling loop: {e}", exc_info=True)

            # Wait before next poll
            await asyncio.sleep(self.poll_interval)

    async def _poll_once(self) -> int:
        """Perform a single polling cycle.

        Returns:
            Number of signals processed
        """
        processed_count = 0

        try:
            redis = await self._get_redis()

            # Scan for signal keys
            cursor = 0
            signal_keys = []

            while True:
                cursor, keys = await redis.scan(
                    cursor=cursor,
                    match=self.REDIS_KEY_PATTERN,
                    count=100,
                )
                signal_keys.extend(keys)

                if cursor == 0:
                    break

            logger.debug(f"Found {len(signal_keys)} signal keys in Redis")

            # Process each signal
            for key in signal_keys:
                try:
                    # Try to get signal data - handle both hash and string (JSON) formats
                    signal_data = await self._get_signal_data(redis, key)

                    if not signal_data:
                        continue

                    signal_id = signal_data.get("signal_id", "")

                    # Skip if already in processed set
                    if signal_id in self._processed_signals:
                        continue

                    # Only process actionable signals
                    status = signal_data.get("status", "")
                    if status != "actionable":
                        continue

                    # Convert to Signal object and submit
                    signal = self._convert_to_signal(signal_data)
                    if signal:
                        token = (signal.token or "").upper().strip()
                        if self.allowed_symbols and token not in self.allowed_symbols:
                            await self._update_signal_status(key, "consumed")
                            await self._mark_signal_processed(signal.signal_id)
                            logger.debug(
                                "Skipping signal %s for non-allowed symbol %s",
                                signal.signal_id,
                                token,
                            )
                            continue
                        submitted = await self._submit_signal(signal, key)
                        if submitted:
                            processed_count += 1

                except Exception as e:
                    logger.error(f"Error processing signal {key}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error during poll cycle: {e}")

        if processed_count > 0:
            logger.info(f"Processed {processed_count} signals in this cycle")

        return processed_count

    def _convert_to_signal(self, signal_data: dict[str, str]) -> Signal | None:
        """Convert Redis hash data to Signal object.

        Args:
            signal_data: Dictionary from Redis HGETALL

        Returns:
            Signal object or None if conversion fails
        """
        try:
            from signal_generation.models import Signal

            # Parse direction
            direction_str = signal_data.get("direction", "neutral").lower()
            direction = SignalDirection(direction_str)

            # Parse confidence
            confidence = float(signal_data.get("confidence", "0.0"))

            # Parse timestamp
            timestamp_str = signal_data.get("timestamp", "")
            if timestamp_str:
                # Handle ISO format with timezone
                timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            else:
                timestamp = datetime.now(UTC)

            # Parse status
            status_str = signal_data.get("status", "logged_only")
            status = SignalStatus(status_str)

            # Create Signal object
            signal = Signal(
                token=signal_data.get("token", ""),
                direction=direction,
                confidence=confidence,
                base_score=confidence * 100,  # Convert to 0-100 scale
                timestamp=timestamp,
                status=status,
                timeframe=signal_data.get("timeframe", "1h"),
                signal_id=signal_data.get("signal_id", ""),
            )

            return signal

        except Exception as e:
            logger.error(f"Failed to convert signal data: {e}")
            return None

    async def _submit_signal(self, signal: Signal, redis_key: str) -> bool:
        """Submit a signal to the orchestrator.

        Args:
            signal: The Signal object to submit
            redis_key: Redis key for updating status

        Returns:
            True if submitted successfully
        """
        try:
            symbol = (signal.token or "").upper().strip()
            now_ts = time.time()

            if symbol and self.symbol_throttle_seconds > 0:
                last_ts = self._last_symbol_submit_ts.get(symbol, 0.0)
                if (now_ts - last_ts) < self.symbol_throttle_seconds:
                    await self._update_signal_status(redis_key, "consumed")
                    await self._mark_signal_processed(signal.signal_id)
                    logger.info(
                        "Skipped signal %s for %s due throttle (%.1fs < %.1fs)",
                        signal.signal_id,
                        symbol,
                        now_ts - last_ts,
                        self.symbol_throttle_seconds,
                    )
                    return False

            # Submit to orchestrator
            await self.orchestrator.submit_signal(signal)
            if symbol:
                self._last_symbol_submit_ts[symbol] = now_ts

            # Mark as consumed in Redis
            await self._update_signal_status(redis_key, "consumed")

            # Add to processed set
            await self._mark_signal_processed(signal.signal_id)

            logger.info(
                f"Submitted signal {signal.signal_id} to orchestrator: "
                f"{signal.token} {signal.direction.value}"
            )

            return True

        except Exception as e:
            logger.error(f"Failed to submit signal {signal.signal_id}: {e}")
            return False

    def get_stats(self) -> dict[str, Any]:
        """Get consumer statistics.

        Returns:
            Dictionary with consumer stats
        """
        return {
            "running": self._running,
            "poll_interval": self.poll_interval,
            "symbol_throttle_seconds": self.symbol_throttle_seconds,
            "processed_count": len(self._processed_signals),
        }

    async def reset_processed_set(self) -> None:
        """Clear the processed signals set (for testing/debugging)."""
        try:
            redis = await self._get_redis()
            await redis.delete(self.PROCESSED_SET_KEY)
            self._processed_signals.clear()
            logger.info("Cleared processed signals set")
        except Exception as e:
            logger.error(f"Failed to clear processed set: {e}")

    async def check_health(self) -> dict[str, Any]:
        """Check the health status of the signal consumer.

        Returns:
            Dictionary with health status information
        """
        health = {
            "healthy": self._running,
            "running": self._running,
            "poll_task_active": self._poll_task is not None
            and not self._poll_task.done(),
            "processed_count": len(self._processed_signals),
            "poll_interval": self.poll_interval,
        }

        # Check Redis health marker
        try:
            redis = await self._get_redis()
            marker = await redis.hgetall("paper:signal_consumer:health")
            health["redis_marker"] = marker if marker else None
        except Exception as e:
            health["redis_marker_error"] = str(e)

        return health
