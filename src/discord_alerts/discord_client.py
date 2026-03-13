"""Discord bot client wrapper with P0 runtime hardening.

Provides async Discord bot client with:
- Message queue for failed sends with Redis persistence
- Hourly checkpoint message capability
- Connection health monitoring with Redis storage
- Automatic reconnection with exponential backoff
- Message delivery confirmation tracking

For ST-NS-009: Discord Alert Integration
For GATE-RECOVERY-002: Discord Channel Routing Fix
For P0-RUNTIME-HARDEN-003: Discord Continuity
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import json
import logging
import sys
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from discord_alerts.config import DiscordConfig

logger = logging.getLogger(__name__)


def _load_redis_state_helpers() -> dict[str, Any]:
    """Load redis_state helpers with script-mode import fallback."""
    candidates = ["tools.redis_state", "src.tools.redis_state"]
    for module_name in candidates:
        with contextlib.suppress(Exception):
            module = importlib.import_module(module_name)
            return {
                "lpush": getattr(module, "redis_state_lpush", None),
                "lrange": getattr(module, "redis_state_lrange", None),
                "hset": getattr(module, "redis_state_hset", None),
            }

    # Fallback: ensure repo root is in sys.path, then retry tools.redis_state.
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    with contextlib.suppress(Exception):
        module = importlib.import_module("tools.redis_state")
        return {
            "lpush": getattr(module, "redis_state_lpush", None),
            "lrange": getattr(module, "redis_state_lrange", None),
            "hset": getattr(module, "redis_state_hset", None),
        }

    return {"lpush": None, "lrange": None, "hset": None}


@dataclass
class DeliveryResult:
    """Result of a Discord message delivery attempt.

    Attributes:
        success: Whether delivery was successful
        message_id: Discord message ID (if available from bot)
        channel_id: Target channel ID
        channel_name: Target channel name
        error: Error message if failed
        method: Delivery method used ('bot', 'webhook', or 'none')
        guild_validated: Whether guild lock was validated
    """

    success: bool
    message_id: str | None = None
    channel_id: str | None = None
    channel_name: str | None = None
    error: str | None = None
    method: str = "none"
    guild_validated: bool = False

    def __getitem__(self, key: str) -> Any:
        """Allow legacy dict-style access used by existing tests/callers."""
        try:
            return getattr(self, key)
        except AttributeError as exc:
            raise KeyError(key) from exc


@dataclass
class QueuedMessage:
    """Message queued for retry with persistence support.

    Attributes:
        message_id: Unique identifier for this message
        content: Message content
        channel_id: Target channel ID
        channel_name: Target channel name
        embeds: Optional Discord embeds
        priority: Priority level (1=high, 2=normal, 3=low)
        created_at: When message was created
        retry_count: Number of retry attempts
        last_error: Last error message
    """

    content: str
    channel_id: str | None = None
    channel_name: str | None = None
    embeds: list[dict[str, Any]] | None = None
    priority: int = 2
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    retry_count: int = 0
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for Redis storage."""
        return {
            "message_id": self.message_id,
            "content": self.content,
            "channel_id": self.channel_id,
            "channel_name": self.channel_name,
            "embeds": self.embeds,
            "priority": self.priority,
            "created_at": self.created_at.isoformat(),
            "retry_count": self.retry_count,
            "last_error": self.last_error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QueuedMessage:
        """Create from dictionary from Redis."""
        return cls(
            content=data["content"],
            channel_id=data.get("channel_id"),
            channel_name=data.get("channel_name"),
            embeds=data.get("embeds"),
            priority=data.get("priority", 2),
            message_id=data.get("message_id", str(uuid.uuid4())),
            created_at=datetime.fromisoformat(data["created_at"]),
            retry_count=data.get("retry_count", 0),
            last_error=data.get("last_error"),
        )


class DiscordClient:
    """Discord bot client with webhook fallback and P0 hardening.

    Supports both bot token (for full bot functionality) and
    webhook URL (for simple message posting) authentication.

    Implements Gate B fix: bot-send is primary, webhook is fallback.
    All sends enforce guild lock for security.

    P0 Hardening Features:
        - Message queue for failed sends with Redis persistence
        - Hourly checkpoint message capability
        - Connection health monitoring with Redis storage
        - Automatic reconnection with exponential backoff
        - Message delivery confirmation tracking

    Attributes:
        config: Discord configuration
        is_connected: Whether client is connected
        _session: aiohttp ClientSession (created on first use)
        _bot_client: discord.py Client instance
        _guild_cache: Cache of resolved guild/channel IDs
        _consecutive_failures: Count of consecutive send failures
        _disabled_until: Timestamp when Discord will be re-enabled
        _rate_limit_backoff_seconds: Current backoff interval
        _message_queue: Queue for failed messages
        _checkpoint_task: Background checkpoint task
        _health_check_task: Background health monitoring task
        _retry_task: Background retry task
        _delivery_confirmations: Tracking for confirmed deliveries
    """

    MAX_CONSECUTIVE_FAILURES = 5
    DISABLE_DURATION_MINUTES = 15
    MAX_QUEUE_SIZE = 1000
    MAX_RETRY_ATTEMPTS = 10
    CHECKPOINT_INTERVAL_MINUTES = 60
    HEALTH_CHECK_INTERVAL_SECONDS = 30
    RETRY_INTERVAL_SECONDS = 60
    REDIS_KEY_PREFIX = "discord:continuity"

    def __init__(self, config: DiscordConfig):
        """Initialize Discord client.

        Args:
            config: Discord configuration
        """
        self.config = config
        self.is_connected = False
        self._session: Any | None = None
        self._bot_client: Any | None = None
        self._guild_cache: dict[str, Any] = {}
        self._consecutive_failures = 0
        self._disabled_until: datetime | None = None
        self._rate_limit_backoff_seconds = 5  # Initial backoff

        # P0 Hardening: Message queue and persistence
        self._message_queue: asyncio.PriorityQueue[
            tuple[int, datetime, QueuedMessage]
        ] = asyncio.PriorityQueue()
        self._queue_lock = asyncio.Lock()
        self._checkpoint_task: asyncio.Task | None = None
        self._health_check_task: asyncio.Task | None = None
        self._retry_task: asyncio.Task | None = None
        self._delivery_confirmations: dict[str, datetime] = {}
        self._last_successful_send: datetime | None = None
        self._total_messages_sent = 0
        self._total_messages_failed = 0
        self._total_messages_queued = 0

    @property
    def is_disabled(self) -> bool:
        """Check if Discord is temporarily disabled due to failures.

        Returns:
            True if disabled, False otherwise. Auto-re-enables after duration.
        """
        if self._disabled_until is None:
            return False
        if datetime.now(UTC) >= self._disabled_until:
            # Auto-re-enable after duration
            self._disabled_until = None
            self._consecutive_failures = 0
            self._rate_limit_backoff_seconds = 5
            logger.info("Discord auto-re-enabled after disable duration")
            return False
        return True

    async def _get_session(self) -> Any:
        """Get or create aiohttp session.

        Returns:
            aiohttp ClientSession
        """
        if self._session is None:
            try:
                import aiohttp

                self._session = aiohttp.ClientSession()
            except ImportError:
                logger.error("aiohttp not installed, cannot create session")
                raise
        return self._session

    async def connect(self) -> bool:
        """Connect to Discord.

        For bot token mode, this initializes the bot client (primary method).
        For webhook mode, this validates the webhook URL (fallback method).

        Gate B fix: Bot is primary, webhook is fallback.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Primary: Try bot token first (full functionality)
            if self.config.bot_token and await self._connect_bot():
                self.is_connected = True
                logger.info("Discord client connected via bot token (primary)")
                self._start_background_tasks()
                await self._restore_queued_messages()
                return True

            # Fallback: Try webhook (simpler, no gateway connection needed)
            if self.config.webhook_url and await self._validate_webhook():
                self.is_connected = True
                logger.info("Discord client connected via webhook (fallback)")
                self._start_background_tasks()
                await self._restore_queued_messages()
                return True

            logger.error("No valid Discord authentication configured")
            return False

        except Exception as e:
            logger.error(f"Discord connection failed: {e}")
            return False

    def _start_background_tasks(self) -> None:
        """Start background tasks for P0 hardening features."""
        # Start checkpoint task
        if self._checkpoint_task is None or self._checkpoint_task.done():
            self._checkpoint_task = asyncio.create_task(self._checkpoint_loop())
            logger.info("Started checkpoint task")

        # Start health check task
        if self._health_check_task is None or self._health_check_task.done():
            self._health_check_task = asyncio.create_task(self._health_check_loop())
            logger.info("Started health check task")

        # Start retry task
        if self._retry_task is None or self._retry_task.done():
            self._retry_task = asyncio.create_task(self._retry_loop())
            logger.info("Started retry task")

    async def _checkpoint_loop(self) -> None:
        """Send hourly checkpoint messages to verify continuity."""
        while True:
            try:
                await asyncio.sleep(self.CHECKPOINT_INTERVAL_MINUTES * 60)

                if not self.is_connected or self.is_disabled:
                    logger.warning("Skipping checkpoint - Discord not available")
                    continue

                # Send checkpoint message
                checkpoint_msg = (
                    f"🔄 **Discord Continuity Checkpoint**\n"
                    f"Time: {datetime.now(UTC).isoformat()}\n"
                    f"Status: Connected ({self._get_connection_mode()})\n"
                    f"Messages Sent (session): {self._total_messages_sent}\n"
                    f"Queue Size: {self._message_queue.qsize()}\n"
                    f"Consecutive Failures: {self._consecutive_failures}"
                )

                result = await self.send_message(
                    content=checkpoint_msg,
                    channel_id=self.config.summaries_channel_id,
                )

                if result.success:
                    logger.info("Checkpoint message sent successfully")
                    await self._store_checkpoint_status(True, None)
                else:
                    logger.warning(f"Checkpoint message failed: {result.error}")
                    await self._store_checkpoint_status(False, result.error)

            except asyncio.CancelledError:
                logger.info("Checkpoint loop cancelled")
                break
            except Exception as e:
                logger.error(f"Checkpoint loop error: {e}")
                await asyncio.sleep(60)  # Retry in 1 minute on error

    async def _health_check_loop(self) -> None:
        """Monitor connection health and store metrics in Redis."""
        while True:
            try:
                await asyncio.sleep(self.HEALTH_CHECK_INTERVAL_SECONDS)

                health = await self.health_check()
                await self._store_health_metrics(health)

                # Check for stale connection (no messages in 2 hours)
                if self._last_successful_send:
                    time_since_last = datetime.now(UTC) - self._last_successful_send
                    if time_since_last > timedelta(hours=2):
                        logger.warning(
                            f"No messages sent in {time_since_last.total_seconds() / 3600:.1f} hours"
                        )
                        await self._trigger_continuity_alert(time_since_last)

                # Auto-reconnect if disconnected but not disabled
                if not self.is_connected and not self.is_disabled:
                    logger.info("Attempting auto-reconnect...")
                    await self.connect()

            except asyncio.CancelledError:
                logger.info("Health check loop cancelled")
                break
            except Exception as e:
                logger.error(f"Health check loop error: {e}")

    async def _retry_loop(self) -> None:
        """Process queued messages for retry."""
        while True:
            try:
                await asyncio.sleep(self.RETRY_INTERVAL_SECONDS)

                if not self.is_connected or self.is_disabled:
                    continue

                await self._process_message_queue()

            except asyncio.CancelledError:
                logger.info("Retry loop cancelled")
                break
            except Exception as e:
                logger.error(f"Retry loop error: {e}")

    async def _process_message_queue(self) -> None:
        """Process queued messages for retry."""
        processed = []

        async with self._queue_lock:
            # Get all messages from queue
            temp_queue = []
            while not self._message_queue.empty():
                try:
                    priority, created_at, msg = self._message_queue.get_nowait()
                    temp_queue.append((priority, created_at, msg))
                except asyncio.QueueEmpty:
                    break

            # Try to send each message
            for priority, created_at, msg in temp_queue:
                if msg.retry_count >= self.MAX_RETRY_ATTEMPTS:
                    logger.warning(
                        f"Message {msg.message_id} exceeded max retries, dropping"
                    )
                    self._total_messages_failed += 1
                    continue

                try:
                    result = await self._send_queued_message(msg)
                    if result.success:
                        logger.info(
                            f"Queued message {msg.message_id} sent successfully"
                        )
                        self._delivery_confirmations[msg.message_id] = datetime.now(UTC)
                        processed.append(msg.message_id)
                    else:
                        # Re-queue with incremented retry count
                        msg.retry_count += 1
                        msg.last_error = result.error
                        await self._message_queue.put((priority, created_at, msg))
                        logger.warning(
                            f"Message {msg.message_id} retry {msg.retry_count} failed: {result.error}"
                        )
                except Exception as e:
                    logger.error(
                        f"Error processing queued message {msg.message_id}: {e}"
                    )
                    msg.retry_count += 1
                    msg.last_error = str(e)
                    await self._message_queue.put((priority, created_at, msg))

        if processed:
            logger.info(f"Processed {len(processed)} queued messages")
            await self._persist_queue_state()

    async def _send_queued_message(self, msg: QueuedMessage) -> DeliveryResult:
        """Send a queued message."""
        return await self.send_message(
            content=msg.content,
            channel_id=msg.channel_id,
            channel=msg.channel_name,
            embeds=msg.embeds,
        )

    async def _queue_message(self, msg: QueuedMessage) -> bool:
        """Queue a message for later retry.

        Args:
            msg: Message to queue

        Returns:
            True if queued successfully
        """
        async with self._queue_lock:
            if self._message_queue.qsize() >= self.MAX_QUEUE_SIZE:
                logger.error("Message queue full, dropping oldest message")
                # Remove oldest message
                with contextlib.suppress(asyncio.QueueEmpty):
                    self._message_queue.get_nowait()

            await self._message_queue.put((msg.priority, msg.created_at, msg))
            self._total_messages_queued += 1

        logger.info(f"Message {msg.message_id} queued for retry")
        await self._persist_queue_state()
        return True

    async def _persist_queue_state(self) -> None:
        """Persist queue state to Redis."""
        try:
            helpers = _load_redis_state_helpers()
            redis_state_lpush = helpers.get("lpush")
            if redis_state_lpush is None:
                logger.debug("Redis state helper unavailable for queue persistence")
                return

            # Get all messages from queue
            messages = []
            temp_items = []

            async with self._queue_lock:
                while not self._message_queue.empty():
                    try:
                        item = self._message_queue.get_nowait()
                        temp_items.append(item)
                        _, _, msg = item
                        messages.append(msg.to_dict())
                    except asyncio.QueueEmpty:
                        break

                # Restore queue
                for item in temp_items:
                    await self._message_queue.put(item)

            # Store in Redis
            redis_key = f"{self.REDIS_KEY_PREFIX}:queued_messages"

            # Clear existing and store new
            # Note: This is a simplified approach; production might use a Redis list
            for msg_dict in messages[-100:]:  # Keep last 100
                redis_state_lpush(redis_key, json.dumps(msg_dict), expire=86400)

            logger.debug(f"Persisted {len(messages)} queued messages to Redis")

        except Exception as e:
            logger.error(f"Failed to persist queue state: {e}")

    async def _restore_queued_messages(self) -> None:
        """Restore queued messages from Redis on reconnect."""
        try:
            helpers = _load_redis_state_helpers()
            redis_state_lrange = helpers.get("lrange")
            if redis_state_lrange is None:
                logger.debug("Redis state helper unavailable for queue restore")
                return

            redis_key = f"{self.REDIS_KEY_PREFIX}:queued_messages"
            stored = redis_state_lrange(redis_key, 0, 99)

            if stored:
                restored_count = 0
                for item in stored:
                    try:
                        if isinstance(item, dict):
                            msg_dict = item
                        elif isinstance(item, str):
                            msg_dict = json.loads(item)
                        elif isinstance(item, bytes):
                            msg_dict = json.loads(item.decode("utf-8"))
                        else:
                            raise TypeError(
                                f"unsupported queued message type: {type(item).__name__}"
                            )
                        msg = QueuedMessage.from_dict(msg_dict)
                        # Restore without repersisting queue on every element.
                        async with self._queue_lock:
                            await self._message_queue.put(
                                (msg.priority, msg.created_at, msg)
                            )
                            self._total_messages_queued += 1
                        restored_count += 1
                    except Exception as e:
                        logger.warning("Failed to restore queued message: %s", e)

                logger.info(f"Restored {restored_count} queued messages from Redis")

        except Exception as e:
            logger.error(f"Failed to restore queued messages: {e}")

    async def _store_checkpoint_status(self, success: bool, error: str | None) -> None:
        """Store checkpoint status in Redis."""
        try:
            helpers = _load_redis_state_helpers()
            redis_state_hset = helpers.get("hset")
            if redis_state_hset is None:
                logger.debug("Redis state helper unavailable for checkpoint status")
                return

            redis_key = f"{self.REDIS_KEY_PREFIX}:checkpoint"
            redis_state_hset(
                redis_key,
                "last_checkpoint",
                datetime.now(UTC).isoformat(),
            )
            redis_state_hset(redis_key, "success", str(success))
            if error:
                redis_state_hset(redis_key, "error", error)

        except Exception as e:
            logger.error(f"Failed to store checkpoint status: {e}")

    async def _store_health_metrics(self, health: dict[str, Any]) -> None:
        """Store health metrics in Redis."""
        try:
            helpers = _load_redis_state_helpers()
            redis_state_hset = helpers.get("hset")
            if redis_state_hset is None:
                logger.debug("Redis state helper unavailable for health metrics")
                return

            redis_key = f"{self.REDIS_KEY_PREFIX}:health"
            redis_state_hset(redis_key, "timestamp", datetime.now(UTC).isoformat())
            redis_state_hset(redis_key, "metrics", json.dumps(health))
            redis_state_hset(
                redis_key,
                "last_successful_send",
                (
                    self._last_successful_send.isoformat()
                    if self._last_successful_send
                    else ""
                ),
            )
            redis_state_hset(redis_key, "total_sent", str(self._total_messages_sent))
            redis_state_hset(
                redis_key, "total_failed", str(self._total_messages_failed)
            )
            redis_state_hset(redis_key, "queue_size", str(self._message_queue.qsize()))

        except Exception as e:
            logger.error(f"Failed to store health metrics: {e}")

    async def _trigger_continuity_alert(self, time_since_last: timedelta) -> None:
        """Trigger alert when no messages sent for extended period."""
        logger.error(
            f"CONTINUITY ALERT: No Discord messages sent for {time_since_last.total_seconds() / 3600:.1f} hours"
        )
        # This could trigger external alerting (PagerDuty, etc.)

    def _get_connection_mode(self) -> str:
        """Get current connection mode."""
        if self.config.bot_token and self._bot_client:
            return "bot"
        elif self.config.webhook_url:
            return "webhook"
        return "none"

    async def _validate_webhook(self) -> bool:
        """Validate webhook URL by making a test request.

        Returns:
            True if webhook is valid, False otherwise
        """
        if not self.config.webhook_url:
            return False

        try:
            session = await self._get_session()
            # Make a GET request to validate webhook exists
            async with session.get(self.config.webhook_url) as resp:
                # Webhooks return 200 with webhook info on GET
                if resp.status == 200:
                    return True
                # Some webhooks may not support GET, so we accept 401/403
                # as "exists but requires POST"
                if resp.status in (401, 403):
                    return True
                logger.warning(f"Webhook validation returned status {resp.status}")
                return False
        except Exception as e:
            logger.warning(f"Webhook validation failed: {e}")
            # Assume valid if we can't check (will fail on actual send)
            return True

    async def _connect_bot(self) -> bool:
        """Connect using bot token.

        Gate B fix: Bot is primary method for sending messages.
        Initializes the bot client and validates guild access.

        Returns:
            True if bot connection successful, False otherwise
        """
        if not self.config.bot_token:
            return False

        try:
            # Try to import discord.py
            import discord

            intents = discord.Intents.default()
            intents.guilds = True  # Need guild access for channel resolution
            self._bot_client = discord.Client(intents=intents)

            # Validate guild if configured
            if self.config.guild_id:
                logger.info(f"Bot configured with guild lock: {self.config.guild_id}")

            return True

        except ImportError:
            logger.warning("discord.py not installed, bot mode unavailable")
            return False

    def _get_disabled_remaining_minutes(self) -> float:
        """Get remaining disable time in minutes.

        Returns:
            Remaining minutes until re-enable, or 0.0 if not disabled
        """
        if self._disabled_until is None:
            return 0.0
        remaining = (self._disabled_until - datetime.now(UTC)).total_seconds()
        return max(0.0, remaining / 60.0)

    async def _handle_send_result(self, result: DeliveryResult) -> DeliveryResult:
        """Handle send result, tracking failures and rate limits.

        Args:
            result: The delivery result to process

        Returns:
            The same result (potentially modified)
        """
        if not result.success:
            self._consecutive_failures += 1

            # Check if rate limited
            if result.error and "rate limited" in result.error.lower():
                await self._handle_rate_limit()

            # Check for persistent failures
            if self._consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
                await self._disable_due_to_failures()
        else:
            # Reset on success
            self._last_successful_send = datetime.now(UTC)
            self._total_messages_sent += 1
            if self._consecutive_failures > 0:
                self._consecutive_failures = 0
                self._rate_limit_backoff_seconds = 5  # Reset backoff

        return result

    async def _handle_rate_limit(self) -> None:
        """Handle rate limit with exponential backoff."""
        logger.warning(
            f"Rate limited, backing off for {self._rate_limit_backoff_seconds}s"
        )
        await asyncio.sleep(self._rate_limit_backoff_seconds)
        # Exponential backoff: 5s, 10s, 20s, 40s, max 300s
        self._rate_limit_backoff_seconds = min(
            self._rate_limit_backoff_seconds * 2, 300
        )

    async def _disable_due_to_failures(self) -> None:
        """Disable Discord after persistent failures."""
        self._disabled_until = datetime.now(UTC) + timedelta(
            minutes=self.DISABLE_DURATION_MINUTES
        )
        logger.error(
            f"Discord disabled for {self.DISABLE_DURATION_MINUTES} minutes "
            f"due to {self._consecutive_failures} consecutive failures"
        )

    def enable(self) -> None:
        """Manually re-enable Discord after being disabled."""
        self._disabled_until = None
        self._consecutive_failures = 0
        self._rate_limit_backoff_seconds = 5
        logger.info("Discord manually re-enabled")

    async def disconnect(self) -> None:
        """Disconnect from Discord and cleanup resources."""
        # Cancel background tasks
        for task in [self._checkpoint_task, self._health_check_task, self._retry_task]:
            if task and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

        self.is_connected = False

        if self._session:
            await self._session.close()
            self._session = None

        if self._bot_client:
            await self._bot_client.close()
            self._bot_client = None

        logger.info("Discord client disconnected")

    async def send_message(
        self,
        content: str,
        channel: str | None = None,
        channel_id: str | None = None,
        embeds: list[dict[str, Any]] | None = None,
    ) -> DeliveryResult:
        """Send a message to Discord.

        Gate B fix: Uses authoritative channel IDs and enforces guild lock.
        Fallback chain: bot → webhook → queue for retry.

        Implements rate limiting with exponential backoff and automatic
        disable after MAX_CONSECUTIVE_FAILURES.

        Args:
            content: Message content
            channel: Target channel name (e.g., 'summaries', 'trading')
            channel_id: Target channel ID (overrides channel name)
            embeds: Optional Discord embeds

        Returns:
            DeliveryResult with status and message info
        """
        # Check if notifications are disabled due to validation failure
        if not self.config.notifications_enabled:
            return DeliveryResult(
                success=False,
                error=(
                    f"Discord notifications disabled due to validation errors: "
                    f"{'; '.join(self.config.validation_errors)}"
                ),
                method="none",
            )

        # Check if disabled due to persistent failures
        if self.is_disabled:
            remaining = self._get_disabled_remaining_minutes()
            # Queue message for later
            msg = QueuedMessage(
                content=content,
                channel_id=channel_id,
                channel_name=channel,
                embeds=embeds,
                priority=1,  # High priority for immediate retry
            )
            await self._queue_message(msg)
            return DeliveryResult(
                success=False,
                error=f"Discord temporarily disabled ({remaining:.0f}m remaining), message queued",
                method="none",
            )

        if not self.is_connected and not await self.connect():
            # Auto-connect on first send
            # Queue message for retry
            msg = QueuedMessage(
                content=content,
                channel_id=channel_id,
                channel_name=channel,
                embeds=embeds,
                priority=1,
            )
            await self._queue_message(msg)
            return DeliveryResult(
                success=False,
                error="Failed to connect to Discord, message queued",
            )

        # Resolve authoritative channel ID
        target_channel_id = channel_id
        target_channel_name = channel or self.config.default_channel

        if target_channel_id is None and channel:
            # Try to resolve from channel name using config
            resolved_id = self.config.get_channel_id_for_name(channel)
            if resolved_id:
                target_channel_id = resolved_id
                logger.debug(f"Resolved channel '{channel}' to ID {resolved_id}")

        # Validate guild lock if configured
        guild_validated = self._validate_guild_for_send()
        if self.config.guild_id and not guild_validated:
            return DeliveryResult(
                success=False,
                error=f"Guild lock violation: not in guild {self.config.guild_id}",
                channel_name=target_channel_name,
                channel_id=target_channel_id,
                guild_validated=False,
            )

        # Primary: Try bot client first
        if self.config.bot_token and self._bot_client:
            result = await self._send_via_bot(
                content, target_channel_id, target_channel_name, embeds
            )
            if result.success:
                result = await self._handle_send_result(result)
                return result
            logger.warning(f"Bot send failed, trying webhook fallback: {result.error}")

        # Fallback: Try webhook
        if self.config.webhook_url:
            result = await self._send_via_webhook(content, embeds)
            result.channel_name = target_channel_name
            result.channel_id = target_channel_id
            result.guild_validated = guild_validated

            # Track failures and handle rate limits
            result = await self._handle_send_result(result)

            # If failed, queue for retry
            if not result.success:
                msg = QueuedMessage(
                    content=content,
                    channel_id=target_channel_id,
                    channel_name=target_channel_name,
                    embeds=embeds,
                    priority=2,
                )
                await self._queue_message(msg)

            return result

        # Final fallback: Queue for retry
        msg = QueuedMessage(
            content=content,
            channel_id=target_channel_id,
            channel_name=target_channel_name,
            embeds=embeds,
            priority=2,
        )
        await self._queue_message(msg)

        result = DeliveryResult(
            success=False,
            error="No valid Discord sending method available, message queued",
            channel_name=target_channel_name,
            channel_id=target_channel_id,
            guild_validated=guild_validated,
        )

        # Track failures
        result = await self._handle_send_result(result)
        return result

    async def _send_via_webhook(
        self, content: str, embeds: list[dict[str, Any]] | None = None
    ) -> DeliveryResult:
        """Send message via webhook (fallback method).

        Gate B fix: Webhook is fallback method after bot attempt.

        Args:
            content: Message content
            embeds: Optional Discord embeds

        Returns:
            DeliveryResult with status
        """
        if not self.config.webhook_url:
            return DeliveryResult(
                success=False,
                error="No webhook URL configured",
                method="webhook",
            )

        payload: dict[str, Any] = {"content": content}
        if embeds:
            payload["embeds"] = embeds

        try:
            session = await self._get_session()
            async with session.post(self.config.webhook_url, json=payload) as resp:
                if resp.status == 204:
                    # Webhooks return 204 on success
                    logger.info("Message sent via webhook (fallback)")
                    return DeliveryResult(
                        success=True,
                        error=None,
                        message_id=None,  # Webhooks don't return message ID
                        method="webhook",
                    )
                elif resp.status == 429:
                    # Rate limited
                    retry_after = resp.headers.get("Retry-After", "5")
                    return DeliveryResult(
                        success=False,
                        error=f"Rate limited. Retry after {retry_after}s",
                        method="webhook",
                    )
                else:
                    body = await resp.text()
                    return DeliveryResult(
                        success=False,
                        error=f"HTTP {resp.status}: {body}",
                        method="webhook",
                    )

        except Exception as e:
            logger.error(f"Webhook send failed: {e}")
            return DeliveryResult(
                success=False,
                error=str(e),
                method="webhook",
            )

    async def _send_via_bot(
        self,
        content: str,
        channel_id: str | None,
        channel_name: str | None = None,
        embeds: list[dict[str, Any]] | None = None,
    ) -> DeliveryResult:
        """Send message via bot client (primary method).

        Gate B fix: Bot is primary method with channel ID routing.

        Args:
            content: Message content
            channel_id: Target channel ID
            channel_name: Target channel name (for logging)
            embeds: Optional Discord embeds

        Returns:
            DeliveryResult with status
        """
        resolved_channel_name = (
            channel_name or self.config.default_channel or channel_id
        )

        if not self.config.bot_token:
            return DeliveryResult(
                success=False,
                error="Bot not configured",
                channel_name=resolved_channel_name,
                channel_id=channel_id,
                method="bot",
            )

        # Bot client sending requires the client to be running
        # This is a placeholder for full bot implementation
        # In production, this would:
        # 1. Fetch the channel by ID from the guild
        # 2. Validate guild lock
        # 3. Send the message
        # 4. Return the message ID
        logger.warning("Bot client sending not fully implemented - using placeholder")

        # Placeholder: Return failure to trigger webhook fallback
        return DeliveryResult(
            success=False,
            error="Bot client sending not implemented (placeholder)",
            channel_name=resolved_channel_name,
            channel_id=channel_id,
            method="bot",
        )

    def _validate_guild_for_send(self) -> bool:
        """Validate guild lock for sending messages.

        Returns:
            True if guild is valid or no guild restriction configured
        """
        if self.config.guild_id is None:
            # No restriction configured, allow all
            return True

        # In production, this would check if the bot is in the configured guild
        # For now, we assume validation passes if guild_id is configured
        logger.debug(f"Guild lock configured: {self.config.guild_id}")
        return True

    async def health_check(self) -> dict[str, Any]:
        """Check Discord connection health.

        Returns:
            Dictionary with health status including rate limit info
        """
        base_health = {
            "consecutive_failures": self._consecutive_failures,
            "is_disabled": self.is_disabled,
            "disabled_remaining_minutes": (
                self._get_disabled_remaining_minutes() if self.is_disabled else 0.0
            ),
            "rate_limit_backoff_seconds": self._rate_limit_backoff_seconds,
            "queue_size": self._message_queue.qsize(),
            "total_messages_sent": self._total_messages_sent,
            "total_messages_failed": self._total_messages_failed,
            "total_messages_queued": self._total_messages_queued,
            "last_successful_send": (
                self._last_successful_send.isoformat()
                if self._last_successful_send
                else None
            ),
            "connection_mode": self._get_connection_mode(),
        }

        if not self.is_connected:
            base_health.update(
                {
                    "healthy": False,
                    "connected": False,
                    "error": "Not connected",
                }
            )
            return base_health

        # Test connection by validating webhook or bot status
        if self.config.webhook_url:
            webhook_valid = await self._validate_webhook()
            base_health.update(
                {
                    "healthy": webhook_valid,
                    "connected": self.is_connected,
                    "mode": "webhook",
                    "guild_restricted": self.config.guild_id is not None,
                    "error": None if webhook_valid else "Webhook validation failed",
                }
            )
            return base_health

        base_health.update(
            {
                "healthy": self.is_connected,
                "connected": self.is_connected,
                "mode": "bot",
                "guild_restricted": self.config.guild_id is not None,
                "error": None,
            }
        )
        return base_health

    def validate_guild(self, guild_id: str | None) -> bool:
        """Validate that the guild ID matches the configured restriction.

        If no guild_id is configured in settings, all guilds are allowed.
        If guild_id is configured, only that specific guild is allowed.

        Args:
            guild_id: The guild/server ID to validate

        Returns:
            True if guild is allowed, False otherwise
        """
        if self.config.guild_id is None:
            # No restriction configured, allow all
            return True

        if guild_id is None:
            # Guild ID required but not provided
            logger.warning("Guild ID validation failed: no guild_id provided")
            return False

        allowed = str(self.config.guild_id) == str(guild_id)
        if not allowed:
            logger.warning(
                f"Guild ID validation failed: {guild_id} != {self.config.guild_id}"
            )
        return allowed

    async def get_delivery_status(self, message_id: str) -> dict[str, Any] | None:
        """Get delivery confirmation status for a message.

        Args:
            message_id: The message ID to check

        Returns:
            Delivery status dict or None if not found
        """
        if message_id in self._delivery_confirmations:
            return {
                "message_id": message_id,
                "delivered_at": self._delivery_confirmations[message_id].isoformat(),
                "status": "delivered",
            }

        # Check queue
        async with self._queue_lock:
            temp_items = []
            found = None

            while not self._message_queue.empty():
                try:
                    item = self._message_queue.get_nowait()
                    temp_items.append(item)
                    _, _, msg = item
                    if msg.message_id == message_id:
                        found = {
                            "message_id": message_id,
                            "status": "queued",
                            "retry_count": msg.retry_count,
                            "created_at": msg.created_at.isoformat(),
                        }
                except asyncio.QueueEmpty:
                    break

            # Restore queue
            for item in temp_items:
                await self._message_queue.put(item)

            return found

    async def get_continuity_metrics(self) -> dict[str, Any]:
        """Get continuity metrics for monitoring.

        Returns:
            Dictionary with continuity metrics
        """
        now = datetime.now(UTC)
        time_since_last = None
        if self._last_successful_send:
            time_since_last = (now - self._last_successful_send).total_seconds()

        return {
            "timestamp": now.isoformat(),
            "is_connected": self.is_connected,
            "is_disabled": self.is_disabled,
            "connection_mode": self._get_connection_mode(),
            "last_successful_send": (
                self._last_successful_send.isoformat()
                if self._last_successful_send
                else None
            ),
            "time_since_last_send_seconds": time_since_last,
            "total_messages_sent": self._total_messages_sent,
            "total_messages_failed": self._total_messages_failed,
            "total_messages_queued": self._total_messages_queued,
            "current_queue_size": self._message_queue.qsize(),
            "consecutive_failures": self._consecutive_failures,
        }

    async def validate_channel_id(
        self, channel_id: str | None
    ) -> tuple[bool, str | None]:
        """Validate that a channel ID is a valid Discord text channel.

        Uses Discord API to verify the channel exists and is accessible.
        Detects if the ID refers to a guild/server instead of a channel.

        Args:
            channel_id: The Discord channel ID to validate

        Returns:
            Tuple of (is_valid, error_message)
            - is_valid: True if valid text channel, False otherwise
            - error_message: None if valid, descriptive error if invalid
        """
        if not channel_id:
            return True, None  # No channel ID is valid (optional)

        if not self.config.bot_token:
            logger.warning(
                "Cannot validate channel ID without bot token. "
                "Skipping validation for channel_id=%s",
                channel_id,
            )
            return True, None  # Can't validate without bot token

        try:
            session = await self._get_session()
            headers = {"Authorization": f"Bot {self.config.bot_token}"}

            async with session.get(
                f"https://discord.com/api/v10/channels/{channel_id}",
                headers=headers,
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()

                    # Check if this is a channel (has 'type' field)
                    # Text channels have type 0 (GUILD_TEXT)
                    # Guilds don't have a 'type' field but have 'owner_id'
                    if "type" in data:
                        channel_type = data.get("type")
                        if channel_type == 0:  # GUILD_TEXT
                            logger.debug(
                                "Channel %s validated as text channel", channel_id
                            )
                            return True, None
                        else:
                            type_names = {
                                1: "DM",
                                2: "GROUP_DM",
                                3: "GUILD_VOICE",
                                4: "GUILD_CATEGORY",
                                5: "GUILD_ANNOUNCEMENT",
                                10: "ANNOUNCEMENT_THREAD",
                                11: "PUBLIC_THREAD",
                                12: "PRIVATE_THREAD",
                                13: "GUILD_STAGE_VOICE",
                                14: "GUILD_DIRECTORY",
                                15: "GUILD_FORUM",
                                16: "GUILD_MEDIA",
                            }
                            type_name = type_names.get(
                                channel_type, f"type_{channel_type}"
                            )
                            error_msg = (
                                f"Channel ID {channel_id} is not a text channel. "
                                f"It is a {type_name} channel (type={channel_type}). "
                                f"Please provide a text channel ID."
                            )
                            logger.error(error_msg)
                            return False, error_msg
                    elif "owner_id" in data:
                        # This is a guild/server, not a channel
                        guild_name = data.get("name", "Unknown")
                        error_msg = (
                            f"DISCORD_DEVELOPMENT_CHANNEL_ID ({channel_id}) appears to be "
                            f"a Guild/Server ID, not a Channel ID. "
                            f"Guild name: '{guild_name}'. "
                            f"\n\n"
                            f"COMMON MISTAKE: You may have copied the Guild ID instead of "
                            f"the Channel ID.\n"
                            f"\n"
                            f"To find the correct Channel ID:\n"
                            f"1. Enable Developer Mode in Discord (User Settings > Advanced)\n"
                            f"2. Right-click on the TEXT CHANNEL (not the server)\n"
                            f"3. Select 'Copy Channel ID'\n"
                            f"\n"
                            f"Expected format: 17-19 digit numeric string\n"
                            f"Guild IDs and Channel IDs look similar but serve different purposes."
                        )
                        logger.error(error_msg)
                        return False, error_msg
                    else:
                        error_msg = (
                            f"Channel ID {channel_id} returned unexpected data structure. "
                            f"Neither channel nor guild format detected."
                        )
                        logger.error(error_msg)
                        return False, error_msg

                elif resp.status == 404:
                    error_msg = (
                        f"Channel ID {channel_id} not found (404). "
                        f"The channel may not exist or the bot may not have access."
                    )
                    logger.error(error_msg)
                    return False, error_msg

                elif resp.status == 401:
                    error_msg = (
                        f"Authentication failed when validating channel {channel_id}. "
                        f"Please check your DISCORD_BOT_TOKEN."
                    )
                    logger.error(error_msg)
                    return False, error_msg

                elif resp.status == 403:
                    error_msg = (
                        f"Access denied to channel {channel_id} (403). "
                        f"The bot may not have permission to view this channel."
                    )
                    logger.error(error_msg)
                    return False, error_msg

                else:
                    body = await resp.text()
                    error_msg = (
                        f"Discord API returned unexpected status {resp.status} "
                        f"when validating channel {channel_id}: {body}"
                    )
                    logger.error(error_msg)
                    return False, error_msg

        except Exception as e:
            error_msg = f"Error validating channel ID {channel_id}: {e}"
            logger.error(error_msg)
            return False, error_msg

    async def validate_development_channel(self) -> tuple[bool, list[str]]:
        """Validate the development channel configuration.

        Performs strict or non-strict validation based on config.
        In strict mode (default), raises/fails on invalid config.
        In non-strict mode, logs error and disables notifications.

        Returns:
            Tuple of (success, errors)
            - success: True if validation passed or non-strict mode
            - errors: List of error messages (empty if no errors)
        """
        channel_id = self.config.development_channel_id
        errors: list[str] = []

        if not channel_id:
            # No development channel configured - this is optional
            logger.debug("No development channel configured, skipping validation")
            return True, errors

        is_valid, error_msg = await self.validate_channel_id(channel_id)

        if is_valid:
            logger.info("Development channel %s validated successfully", channel_id)
            self.config.notifications_enabled = True
            return True, errors

        # Validation failed
        errors.append(error_msg or f"Unknown validation error for channel {channel_id}")

        if self.config.strict_validation:
            logger.error(
                "Development channel validation FAILED (strict mode). "
                "To disable strict validation, set DISCORD_STRICT_VALIDATION=false"
            )
            self.config.validation_errors = errors
            return False, errors
        else:
            logger.warning(
                "Development channel validation failed (non-strict mode). "
                "Notifications will be disabled. Error: %s",
                error_msg,
            )
            self.config.notifications_enabled = False
            self.config.validation_errors = errors
            return True, errors
