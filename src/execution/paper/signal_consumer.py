"""Signal Consumer for Redis → Orchestrator bridge.

Polls Redis for actionable signals and submits them to the paper trading
orchestrator for execution.

Part of P0-REPAIR-001: Fix Signal Consumer
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from execution.paper.orchestrator import PaperTradingOrchestrator
    from signal_generation.models import Signal

import contextlib

from execution.paper.paper_kill_switch import (
    PaperKillSwitchManager,
)
from execution.paper.redis_config import get_redis_client
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
    STREAM_KEY = "paper:signals:stream"
    CONSUMER_GROUP = "paper-signal-group"
    CONSUMER_NAME = "paper-signal-consumer"
    PROCESSED_SET_KEY = "paper:signals:processed"
    PROCESSING_KEY_PREFIX = "paper:signal:{signal_id}:processing"
    PROCESSING_MARKER_TTL = 60  # seconds - auto-expire if consumer crashes
    HEALTH_MARKER_KEY = "paper:signal_consumer:health"
    HEALTH_MARKER_TTL = 120  # seconds

    def __init__(
        self,
        orchestrator: PaperTradingOrchestrator,
        redis_client: Any | None = None,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        paper_kill_switch: PaperKillSwitchManager | None = None,
    ):
        """Initialize the signal consumer.

        Args:
            orchestrator: Paper trading orchestrator instance
            redis_client: Redis client (if None, creates new connection)
            poll_interval: Seconds between polling cycles
            paper_kill_switch: Optional PaperKillSwitchManager for paper trading kill switch.
                If None, creates new instance.

        Note:
            Symbol-level cadence throttling is NOT enforced here. The orchestrator
            owns the authoritative G1_THROTTLE gate (see orchestrator.py). Adding
            a second throttle at the consumer layer caused 100% signal blocking
            because the 30s signal generation interval fell within the 300s
            consumer throttle window (ST-PIPE-001).
        """
        self.orchestrator = orchestrator
        self.poll_interval = poll_interval
        symbols_raw = os.getenv("TRADING_SYMBOLS", "BTC/USDT")
        self.allowed_symbols = {
            s.strip().upper() for s in symbols_raw.split(",") if s.strip()
        }
        self._running = False
        self._poll_task: asyncio.Task | None = None
        self._processed_signals: set[str] = set()

        # Initialize Redis client
        if redis_client is not None:
            self._redis = redis_client
            self._owns_redis = False
        else:
            self._redis = None
            self._owns_redis = True

        # Initialize paper kill switch manager
        self._paper_kill_switch = paper_kill_switch

        logger.info(
            "SignalConsumer initialized: poll_interval=%ss, allowed_symbols=%s",
            poll_interval,
            sorted(self.allowed_symbols),
        )

    async def _get_redis(self) -> Any:
        """Get or create Redis client."""
        if self._redis is None:
            self._redis = get_redis_client(decode_responses=True)
        return self._redis

    async def _get_paper_kill_switch(self) -> PaperKillSwitchManager:
        """Get or create PaperKillSwitchManager.

        Returns:
            PaperKillSwitchManager instance
        """
        if self._paper_kill_switch is None:
            redis = await self._get_redis()
            self._paper_kill_switch = PaperKillSwitchManager(redis_client=redis)
        return self._paper_kill_switch

    async def _ensure_stream_group(self) -> None:
        """Ensure the consumer group exists on the stream.

        Creates the stream and consumer group if they don't exist.
        Handles BUSYGROUP error gracefully (group already exists).
        """
        try:
            redis = await self._get_redis()
            try:
                await redis.xgroup_create(
                    name=self.STREAM_KEY,
                    groupname=self.CONSUMER_GROUP,
                    id="$",
                    mkstream=True,
                )
                logger.info(
                    "Created consumer group '%s' on stream '%s'",
                    self.CONSUMER_GROUP,
                    self.STREAM_KEY,
                )
            except Exception as e:
                error_str = str(e).upper()
                if "BUSYGROUP" in error_str:
                    logger.debug(
                        "Consumer group '%s' already exists on stream '%s'",
                        self.CONSUMER_GROUP,
                        self.STREAM_KEY,
                    )
                else:
                    raise
        except Exception as e:
            logger.warning(
                "Failed to ensure stream group: %s. "
                "Will fall back to SCAN-based polling.",
                e,
            )

    async def _read_from_stream(self) -> list[tuple[str, dict[str, str]]]:
        """Read new messages from the stream using XREADGROUP.

        Returns:
            List of (message_id, fields_dict) tuples for unread messages.
            Empty list if no new messages or on error.
        """
        try:
            redis = await self._get_redis()
            result = await redis.xreadgroup(
                groupname=self.CONSUMER_GROUP,
                consumername=self.CONSUMER_NAME,
                streams={self.STREAM_KEY: ">"},
                count=100,
                block=1000,  # 1s blocking read
            )
            messages: list[tuple[str, dict[str, str]]] = []
            if result:
                for _stream_key, stream_messages in result:
                    for message_id, fields in stream_messages:
                        messages.append((message_id, fields))
            return messages
        except Exception as e:
            logger.warning("Failed to read from stream: %s", e)
            return []

    async def _ack_stream_message(self, message_id: str) -> None:
        """Acknowledge a stream message after successful processing.

        Args:
            message_id: The stream message ID to acknowledge.
        """
        try:
            redis = await self._get_redis()
            await redis.xack(self.STREAM_KEY, self.CONSUMER_GROUP, message_id)
            logger.debug("Acknowledged stream message %s", message_id)
        except Exception as e:
            logger.warning("Failed to ack stream message %s: %s", message_id, e)

    async def start(self) -> None:
        """Start the signal consumer polling loop."""
        if self._running:
            logger.warning("SignalConsumer already running")
            return

        self._running = True
        start_time = datetime.now(UTC)

        # Ensure consumer group exists for XREADGROUP
        await self._ensure_stream_group()

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
            await redis.hset(self.HEALTH_MARKER_KEY, mapping=health_data)
            await redis.expire(self.HEALTH_MARKER_KEY, self.HEALTH_MARKER_TTL)
            logger.debug(
                "Health marker set in Redis with TTL=%ds", self.HEALTH_MARKER_TTL
            )
        except Exception as e:
            logger.warning(f"Failed to set health marker: {e}")

    async def _clear_health_marker(self) -> None:
        """Clear the health marker when consumer stops."""
        try:
            redis = await self._get_redis()
            await redis.delete(self.HEALTH_MARKER_KEY)
            logger.debug("Health marker cleared from Redis")
        except Exception as e:
            logger.warning(f"Failed to clear health marker: {e}")

    async def _refresh_health_marker(self) -> None:
        """Refresh the health marker TTL and update stats.

        Called after each successful poll cycle. Updates the processed_count
        in the health hash and refreshes the TTL. If the consumer crashes,
        the marker will expire after HEALTH_MARKER_TTL seconds.
        """
        try:
            redis = await self._get_redis()
            # Update processed count in health data
            await redis.hset(
                self.HEALTH_MARKER_KEY,
                "processed_count",
                str(len(self._processed_signals)),
            )
            await redis.expire(self.HEALTH_MARKER_KEY, self.HEALTH_MARKER_TTL)
            logger.debug(
                "Health marker refreshed: TTL=%ds, processed=%d",
                self.HEALTH_MARKER_TTL,
                len(self._processed_signals),
            )
        except Exception as e:
            logger.warning(f"Failed to refresh health marker: {e}")

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

    async def _acquire_processing_lock(self, signal_id: str) -> bool:
        """Atomically acquire a processing lock for a signal.

        Uses Redis SET NX EX to ensure only one consumer instance processes
        a signal at a time. The lock auto-expires if the consumer crashes.

        Args:
            signal_id: The unique signal identifier

        Returns:
            True if lock was acquired, False if already held by another instance
        """
        try:
            redis = await self._get_redis()
            lock_key = self.PROCESSING_KEY_PREFIX.format(signal_id=signal_id)
            # SET NX EX = set if not exists, with expiry
            acquired = await redis.set(
                lock_key, "1", nx=True, ex=self.PROCESSING_MARKER_TTL
            )
            if acquired:
                logger.debug("Acquired processing lock for signal %s", signal_id)
                return True
            logger.debug(
                "Processing lock already held for signal %s, skipping", signal_id
            )
            return False
        except Exception as e:
            # INFRA EXCEPTION - fail closed, don't silently skip
            logger.error(
                "Failed to acquire processing lock for %s due to infrastructure error: %s",
                signal_id,
                e,
            )
            raise  # Re-raise to fail the iteration explicitly

    async def _release_processing_lock(self, signal_id: str) -> None:
        """Release the processing lock for a signal.

        Should be called after successful or failed processing to allow
        retry if needed (e.g., if processing failed but signal not marked consumed).

        Args:
            signal_id: The unique signal identifier
        """
        try:
            redis = await self._get_redis()
            lock_key = self.PROCESSING_KEY_PREFIX.format(signal_id=signal_id)
            await redis.delete(lock_key)
            logger.debug("Released processing lock for signal %s", signal_id)
        except Exception as e:
            logger.warning("Failed to release processing lock for %s: %e", signal_id, e)

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

            # Refresh health marker after each poll cycle
            await self._refresh_health_marker()

            # Wait before next poll
            await asyncio.sleep(self.poll_interval)

    async def _poll_once(self) -> int:
        """Perform a single polling cycle.

        Tries XREADGROUP on the stream first (primary path for S4+ signals),
        then falls back to SCAN for legacy paper:signal:* keys (backwards compat).

        Returns:
            Number of signals processed
        """
        processed_count = 0

        try:
            redis = await self._get_redis()

            # Check paper kill switch before processing any signals
            paper_kill_switch = await self._get_paper_kill_switch()
            kill_switch_status = await paper_kill_switch.get_status()
            if kill_switch_status.active:
                logger.warning(
                    f"PAPER KILL SWITCH ACTIVE - skipping signal processing: "
                    f"reason='{kill_switch_status.reason}' "
                    f"activated_by='{kill_switch_status.activated_by}' "
                    f"ttl_remaining={kill_switch_status.ttl_remaining}s"
                )
                return 0

            # --- Primary path: XREADGROUP on stream ---
            stream_messages = await self._read_from_stream()
            if stream_messages:
                logger.debug(
                    "Received %d messages from stream '%s'",
                    len(stream_messages),
                    self.STREAM_KEY,
                )
                for message_id, fields in stream_messages:
                    try:
                        count = await self._process_stream_message(fields, message_id)
                        processed_count += count
                    except Exception as e:
                        logger.error(
                            "Error processing stream message %s: %s",
                            message_id,
                            e,
                        )
                        continue
                return processed_count

            # --- Fallback path: SCAN for legacy paper:signal:* keys ---
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

            logger.debug(f"Found {len(signal_keys)} legacy signal keys in Redis")

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

                    # Atomically acquire processing lock to prevent double-processing
                    if not signal_id or not await self._acquire_processing_lock(
                        signal_id
                    ):
                        continue

                    try:
                        # Convert to Signal object and submit
                        signal = self._convert_to_signal(signal_data)
                        if signal:
                            token = (signal.token or "").upper().strip()
                            if (
                                self.allowed_symbols
                                and token not in self.allowed_symbols
                            ):
                                logger.warning(
                                    "SKIPPED signal %s for non-allowed symbol %s "
                                    "(allowed=%s); signal NOT consumed — will retry "
                                    "if symbol is later added to allowlist",
                                    signal.signal_id,
                                    token,
                                    sorted(self.allowed_symbols),
                                )
                                continue
                            submitted = await self._submit_signal(signal, redis_key=key)
                            if submitted:
                                processed_count += 1
                    finally:
                        # Always release the processing lock
                        await self._release_processing_lock(signal_id)

                except Exception as e:
                    logger.error(f"Error processing signal {key}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error during poll cycle: {e}")

        if processed_count > 0:
            logger.info(f"Processed {processed_count} signals in this cycle")

        return processed_count

    async def _process_stream_message(
        self, fields: dict[str, str], message_id: str
    ) -> int:
        """Process a single stream message.

        Args:
            fields: The message fields from the stream entry.
            message_id: The stream message ID for XACK.

        Returns:
            1 if signal was processed, 0 otherwise.
        """
        import json

        signal_data: dict[str, Any] = {}

        # Stream fields from S4's XADD are stored as a flat hash.
        # The 'data' field contains JSON with the full signal payload.
        data_field = fields.get("data")
        if data_field:
            try:
                signal_data = json.loads(data_field)
            except json.JSONDecodeError:
                logger.warning(
                    "Failed to parse JSON data in stream message %s", message_id
                )
                return 0
        else:
            # Fallback: treat all fields as signal data directly
            signal_data = dict(fields)

        signal_id = signal_data.get("signal_id", "")
        if not signal_id:
            logger.debug("Stream message %s has no signal_id, skipping", message_id)
            return 0

        # Skip if already in processed set
        if signal_id in self._processed_signals:
            await self._ack_stream_message(message_id)
            return 0

        # Only process actionable signals
        status = signal_data.get("status", "")
        if status != "actionable":
            await self._ack_stream_message(message_id)
            return 0

        # Convert to Signal object and submit
        signal = self._convert_to_signal(signal_data)
        if not signal:
            await self._ack_stream_message(message_id)
            return 0

        token = (signal.token or "").upper().strip()
        if self.allowed_symbols and token not in self.allowed_symbols:
            logger.warning(
                "SKIPPED stream signal %s for non-allowed symbol %s "
                "(allowed=%s); signal NOT consumed — will retry "
                "if symbol is later added to allowlist",
                signal.signal_id,
                token,
                sorted(self.allowed_symbols),
            )
            return 0

        submitted = await self._submit_signal(signal, None)
        if submitted:
            # Acknowledge the stream message after successful processing
            await self._ack_stream_message(message_id)
            return 1

        return 0

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

    async def _submit_signal(
        self, signal: Signal, redis_key: str | None = None
    ) -> bool:
        """Submit a signal to the orchestrator.

        Args:
            signal: The Signal object to submit
            redis_key: Redis key for updating status (None for stream-sourced signals)

        Returns:
            True if submitted successfully
        """
        try:
            # NOTE: No consumer-level throttle here. Cadence enforcement is
            # the orchestrator's responsibility via G1_THROTTLE. A duplicate
            # throttle at this layer caused total signal suppression (ST-PIPE-001).

            # Submit to orchestrator
            await self.orchestrator.submit_signal(signal)

            # Mark as consumed in Redis (only for legacy key-based signals)
            if redis_key:
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
            marker = await redis.hgetall(self.HEALTH_MARKER_KEY)
            health["redis_marker"] = marker if marker else None
        except Exception as e:
            health["redis_marker_error"] = str(e)

        return health
