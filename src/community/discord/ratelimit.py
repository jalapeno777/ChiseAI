"""Rate limiting for Discord bot commands.

Implements per-user and per-channel rate limiting to prevent Discord API bans.
Rate Limits:
- 5 commands per user per minute
- 20 messages per channel per minute
- 1 identify per 5 seconds (bot startup)
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting.

    Attributes:
        commands_per_user_per_minute: Max commands a single user can issue per minute.
        messages_per_channel_per_minute: Max messages per channel per minute.
        identify_per_second: Min seconds between identify calls (bot startup).
        warning_threshold: Percentage at which to start sending warnings.
    """

    commands_per_user_per_minute: int = 5
    messages_per_channel_per_minute: int = 20
    identify_per_second: float = 5.0
    warning_threshold: float = 0.8

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RateLimitConfig:
        """Create config from dictionary."""
        return cls(
            commands_per_user_per_minute=data.get("commands_per_user_per_minute", 5),
            messages_per_channel_per_minute=data.get(
                "messages_per_channel_per_minute", 20
            ),
            identify_per_second=data.get("identify_per_second", 5.0),
            warning_threshold=data.get("warning_threshold", 0.8),
        )


@dataclass
class RateLimitStatus:
    """Status of rate limiting for a user or channel.

    Attributes:
        current_count: Current usage count in the window.
        max_count: Maximum allowed in the window.
        reset_at: When the rate limit window resets.
        is_limited: Whether the user/channel is currently rate limited.
        warning_sent: Whether a warning has been sent this window.
    """

    current_count: int = 0
    max_count: int = 0
    reset_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    is_limited: bool = False
    warning_sent: bool = False

    @property
    def remaining(self) -> int:
        """Remaining requests in current window."""
        return max(0, self.max_count - self.current_count)

    @property
    def usage_percentage(self) -> float:
        """Percentage of rate limit used."""
        if self.max_count == 0:
            return 0.0
        return self.current_count / self.max_count


class RateLimiter:
    """Rate limiter for Discord bot commands and messages.

    Implements token bucket style rate limiting with sliding window tracking.

    Thread-safe for async usage with asyncio.Lock.
    """

    def __init__(self, config: RateLimitConfig | None = None):
        """Initialize rate limiter.

        Args:
            config: Rate limit configuration. Uses defaults if None.
        """
        self._config = config or RateLimitConfig()
        self._lock = asyncio.Lock()

        # Per-user command tracking: user_id -> list of timestamps
        self._user_commands: dict[str, list[float]] = defaultdict(list)

        # Per-channel message tracking: channel_id -> list of timestamps
        self._channel_messages: dict[str, list[float]] = defaultdict(list)

        # Per-user rate limit status cache
        self._user_status: dict[str, RateLimitStatus] = {}

        # Per-channel rate limit status cache
        self._channel_status: dict[str, RateLimitStatus] = {}

        # Identify rate limiting
        self._last_identify: float = 0.0

        # Warning messages sent tracking
        self._user_warned: set[str] = set()
        self._channel_warned: set[str] = set()

    @property
    def config(self) -> RateLimitConfig:
        """Get rate limit configuration."""
        return self._config

    def _clean_old_timestamps(
        self, timestamps: list[float], window_seconds: float
    ) -> list[float]:
        """Remove timestamps outside the current window.

        Args:
            timestamps: List of Unix timestamps.
            window_seconds: Window size in seconds.

        Returns:
            Filtered list of timestamps within the window.
        """
        cutoff = time.time() - window_seconds
        return [ts for ts in timestamps if ts > cutoff]

    async def check_user_command(self, user_id: str) -> tuple[bool, RateLimitStatus]:
        """Check if a user is allowed to issue a command.

        Args:
            user_id: Discord user ID.

        Returns:
            Tuple of (is_allowed, status).
            is_allowed is True if the command is within rate limits.
            status contains current rate limit state.
        """
        async with self._lock:
            now = time.time()
            window = 60.0  # 1 minute window

            # Clean old timestamps
            self._user_commands[user_id] = self._clean_old_timestamps(
                self._user_commands[user_id], window
            )

            current_count = len(self._user_commands[user_id])
            max_count = self._config.commands_per_user_per_minute

            # Check if rate limited
            if current_count >= max_count:
                # Find when the oldest command will expire
                oldest = (
                    self._user_commands[user_id][0]
                    if self._user_commands[user_id]
                    else now
                )
                reset_at = datetime.fromtimestamp(oldest + window, tz=UTC)

                status = RateLimitStatus(
                    current_count=current_count,
                    max_count=max_count,
                    reset_at=reset_at,
                    is_limited=True,
                    warning_sent=user_id in self._user_warned,
                )
                self._user_status[user_id] = status
                return False, status

            # Not rate limited, but check if approaching limit
            warning_threshold = self._config.warning_threshold
            approaching = current_count >= (max_count * warning_threshold)

            if approaching and user_id not in self._user_warned:
                self._user_warned.add(user_id)

            # Record this command
            self._user_commands[user_id].append(now)

            reset_at = datetime.fromtimestamp(now + window, tz=UTC)
            status = RateLimitStatus(
                current_count=current_count + 1,
                max_count=max_count,
                reset_at=reset_at,
                is_limited=False,
                warning_sent=user_id in self._user_warned,
            )
            self._user_status[user_id] = status
            return True, status

    async def check_channel_message(
        self, channel_id: str
    ) -> tuple[bool, RateLimitStatus]:
        """Check if a channel is allowed to receive a message.

        Args:
            channel_id: Discord channel ID.

        Returns:
            Tuple of (is_allowed, status).
            is_allowed is True if the message is within rate limits.
            status contains current rate limit state.
        """
        async with self._lock:
            now = time.time()
            window = 60.0  # 1 minute window

            # Clean old timestamps
            self._channel_messages[channel_id] = self._clean_old_timestamps(
                self._channel_messages[channel_id], window
            )

            current_count = len(self._channel_messages[channel_id])
            max_count = self._config.messages_per_channel_per_minute

            # Check if rate limited
            if current_count >= max_count:
                oldest = (
                    self._channel_messages[channel_id][0]
                    if self._channel_messages[channel_id]
                    else now
                )
                reset_at = datetime.fromtimestamp(oldest + window, tz=UTC)

                status = RateLimitStatus(
                    current_count=current_count,
                    max_count=max_count,
                    reset_at=reset_at,
                    is_limited=True,
                    warning_sent=channel_id in self._channel_warned,
                )
                self._channel_status[channel_id] = status
                return False, status

            # Not rate limited
            warning_threshold = self._config.warning_threshold
            approaching = current_count >= (max_count * warning_threshold)

            if approaching and channel_id not in self._channel_warned:
                self._channel_warned.add(channel_id)

            # Record this message
            self._channel_messages[channel_id].append(now)

            reset_at = datetime.fromtimestamp(now + window, tz=UTC)
            status = RateLimitStatus(
                current_count=current_count + 1,
                max_count=max_count,
                reset_at=reset_at,
                is_limited=False,
                warning_sent=channel_id in self._channel_warned,
            )
            self._channel_status[channel_id] = status
            return True, status

    async def check_identify(self) -> bool:
        """Check if bot can perform an identify (connect to Discord).

        Implements 1 identify per 5 seconds rate limit.

        Returns:
            True if identify is allowed.
        """
        async with self._lock:
            now = time.time()
            min_interval = self._config.identify_per_second

            if now - self._last_identify < min_interval:
                wait_time = min_interval - (now - self._last_identify)
                logger.warning(
                    "Identify rate limited, need to wait %.2f seconds", wait_time
                )
                return False

            self._last_identify = now
            return True

    def get_user_status(self, user_id: str) -> RateLimitStatus:
        """Get cached rate limit status for a user.

        Args:
            user_id: Discord user ID.

        Returns:
            Rate limit status for the user.
        """
        return self._user_status.get(
            user_id,
            RateLimitStatus(
                current_count=len(self._user_commands.get(user_id, [])),
                max_count=self._config.commands_per_user_per_minute,
                reset_at=datetime.now(UTC) + timedelta(minutes=1),
                is_limited=False,
                warning_sent=False,
            ),
        )

    def get_channel_status(self, channel_id: str) -> RateLimitStatus:
        """Get cached rate limit status for a channel.

        Args:
            channel_id: Discord channel ID.

        Returns:
            Rate limit status for the channel.
        """
        return self._channel_status.get(
            channel_id,
            RateLimitStatus(
                current_count=len(self._channel_messages.get(channel_id, [])),
                max_count=self._config.messages_per_channel_per_minute,
                reset_at=datetime.now(UTC) + timedelta(minutes=1),
                is_limited=False,
                warning_sent=False,
            ),
        )

    async def clear_user_warnings(self, user_id: str) -> None:
        """Clear warning flag for a user (called when they slow down).

        Args:
            user_id: Discord user ID.
        """
        async with self._lock:
            self._user_warned.discard(user_id)

    async def clear_channel_warnings(self, channel_id: str) -> None:
        """Clear warning flag for a channel.

        Args:
            channel_id: Discord channel ID.
        """
        async with self._lock:
            self._channel_warned.discard(channel_id)

    def get_warning_message(self, status: RateLimitStatus) -> str | None:
        """Generate a warning message if approaching rate limit.

        Args:
            status: Current rate limit status.

        Returns:
            Warning message or None if not approaching limit.
        """
        if status.is_limited:
            return (
                f"⚠️ Rate limit reached! Please wait until {status.reset_at.strftime('%H:%M:%S')} UTC. "
                f"({status.remaining}/{status.max_count} remaining)"
            )

        if status.warning_sent and status.usage_percentage >= 0.8:
            return (
                f"⚠️ Approaching rate limit ({status.usage_percentage * 100:.0f}% used). "
                f"Slow down to avoid being rate limited."
            )

        return None
