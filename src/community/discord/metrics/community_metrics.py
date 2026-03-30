"""Community metrics tracking for Discord."""

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class MetricType(Enum):
    """Type of metric."""

    ACTIVE_USERS = "active_users"
    MESSAGES_SENT = "messages_sent"
    REACTIONS_ADDED = "reactions_added"
    THREADS_CREATED = "threads_created"
    COMMAND_USAGE = "command_usage"


@dataclass
class MetricSnapshot:
    """A snapshot of community metrics."""

    timestamp: datetime
    metric_type: MetricType
    value: float
    period: str  # 'daily', 'weekly', 'monthly'
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "metric_type": self.metric_type.value,
            "value": self.value,
            "period": self.period,
            "metadata": self.metadata,
        }


@dataclass
class ActiveUserMetrics:
    """Active user metrics breakdown."""

    total: int
    daily: int
    weekly: int
    monthly: int
    new_users: int
    returning_users: int
    peak_online: int


@dataclass
class EngagementMetrics:
    """Engagement metrics breakdown."""

    messages_sent: int
    reactions_added: int
    threads_created: int
    avg_messages_per_user: float
    avg_reactions_per_user: float
    total_engagement_score: float


@dataclass
class CommandUsageMetrics:
    """Command usage statistics."""

    command_name: str
    usage_count: int
    unique_users: int
    avg_response_time_ms: float
    error_count: int
    last_used: datetime | None


class CommunityMetrics:
    """Track community metrics in Redis.

    Tracks active users, engagement, and command usage statistics.
    Stores metrics with TTL for automatic cleanup.
    """

    # TTL constants
    HOURLY_TTL = 3600  # 1 hour
    DAILY_TTL = 86400  # 24 hours
    WEEKLY_TTL = 604800  # 7 days
    MONTHLY_TTL = 2592000  # 30 days

    def __init__(
        self,
        redis_client: Any = None,
        metrics_ttl_days: int = 30,
    ):
        """Initialize CommunityMetrics.

        Args:
            redis_client: Redis client for storing metrics
            metrics_ttl_days: Days to retain detailed metrics
        """
        self._redis = redis_client
        self._metrics_ttl_days = metrics_ttl_days
        self._local_cache: dict[str, Any] = {}

    def _get_metric_key(
        self,
        metric_type: MetricType,
        period: str,
        timestamp: datetime | None = None,
    ) -> str:
        """Get Redis key for a metric."""
        ts = timestamp or datetime.now(UTC)
        date_str = ts.strftime("%Y%m%d")
        return f"community:discord:metrics:{metric_type.value}:{period}:{date_str}"

    def _get_user_activity_key(self, user_id: str, period: str) -> str:
        """Get Redis key for user's activity."""
        return f"community:discord:user:{user_id}:activity:{period}"

    def _get_command_usage_key(self, command_name: str) -> str:
        """Get Redis key for command usage."""
        return f"community:discord:command:{command_name}:usage"

    async def record_active_user(self, user_id: str) -> None:
        """Record a user as active.

        Args:
            user_id: Discord user ID
        """
        # Record in all periods
        for period in ["daily", "weekly", "monthly"]:
            try:
                from tools.redis_state import redis_state_expire, redis_state_sadd

                key = f"community:discord:active_users:{period}"
                redis_state_sadd(key, user_id)

                # Set TTL for daily (others are approximations)
                if period == "daily":
                    redis_state_expire(key, self.DAILY_TTL)
            except Exception as e:
                logger.warning(f"Failed to record active user in Redis: {e}")

        # Update local cache
        if "active_users" not in self._local_cache:
            self._local_cache["active_users"] = {
                "daily": set(),
                "weekly": set(),
                "monthly": set(),
            }

        self._local_cache["active_users"]["daily"].add(user_id)
        self._local_cache["active_users"]["weekly"].add(user_id)
        self._local_cache["active_users"]["monthly"].add(user_id)

    async def record_message_sent(
        self,
        user_id: str,
        channel_id: str,
        thread_id: str | None = None,
    ) -> None:
        """Record a message sent by a user.

        Args:
            user_id: Discord user ID
            channel_id: Discord channel ID
            thread_id: Discord thread ID if in a thread
        """
        try:
            from tools.redis_state import (
                redis_state_expire,
                redis_state_hincrby,
            )

            # Increment user's message count
            user_key = f"community:discord:user:{user_id}:messages"
            redis_state_hincrby(user_key, "count", 1)
            redis_state_expire(user_key, self.MONTHLY_TTL)

            # Increment channel message count
            channel_key = f"community:discord:channel:{channel_id}:messages"
            redis_state_hincrby(channel_key, "count", 1)
            redis_state_expire(channel_key, self.MONTHLY_TTL)

            # Update daily/weekly/monthly counters
            for period in ["daily", "weekly", "monthly"]:
                counter_key = f"community:discord:messages:{period}"
                redis_state_hincrby(counter_key, "total", 1)
                redis_state_expire(counter_key, self.WEEKLY_TTL)

        except Exception as e:
            logger.warning(f"Failed to record message in Redis: {e}")

    async def record_reaction(
        self,
        user_id: str,
        message_id: str,
        emoji: str,
    ) -> None:
        """Record a reaction added by a user.

        Args:
            user_id: Discord user ID
            message_id: Discord message ID
            emoji: Emoji used
        """
        try:
            from tools.redis_state import redis_state_expire, redis_state_hincrby

            # Increment user's reaction count
            user_key = f"community:discord:user:{user_id}:reactions"
            redis_state_hincrby(user_key, "count", 1)
            redis_state_expire(user_key, self.MONTHLY_TTL)

            # Update daily counter
            counter_key = "community:discord:reactions:daily"
            redis_state_hincrby(counter_key, "total", 1)
            redis_state_expire(counter_key, self.DAILY_TTL)

        except Exception as e:
            logger.warning(f"Failed to record reaction in Redis: {e}")

    async def record_thread_created(
        self,
        user_id: str,
        thread_id: str,
        channel_id: str,
    ) -> None:
        """Record a thread created by a user.

        Args:
            user_id: Discord user ID
            thread_id: Discord thread ID
            channel_id: Discord channel ID
        """
        try:
            from tools.redis_state import redis_state_expire, redis_state_hincrby

            # Increment user's thread count
            user_key = f"community:discord:user:{user_id}:threads"
            redis_state_hincrby(user_key, "count", 1)
            redis_state_expire(user_key, self.MONTHLY_TTL)

            # Update daily counter
            counter_key = "community:discord:threads:daily"
            redis_state_hincrby(counter_key, "total", 1)
            redis_state_expire(counter_key, self.DAILY_TTL)

        except Exception as e:
            logger.warning(f"Failed to record thread creation in Redis: {e}")

    async def record_command_usage(
        self,
        command_name: str,
        user_id: str,
        response_time_ms: float | None = None,
        error: bool = False,
    ) -> None:
        """Record command usage.

        Args:
            command_name: Name of the command
            user_id: Discord user ID who used the command
            response_time_ms: Command response time in milliseconds
            error: Whether the command resulted in an error
        """
        try:
            from tools.redis_state import redis_state_expire, redis_state_hincrby

            key = self._get_command_usage_key(command_name)

            # Increment total usage
            redis_state_hincrby(key, "total", 1)

            # Track unique users
            redis_state_hincrby(key, f"user:{user_id}", 1)

            # Track errors
            if error:
                redis_state_hincrby(key, "errors", 1)

            # Track response time
            if response_time_ms is not None:
                redis_state_hincrby(key, "response_time_sum", response_time_ms)
                redis_state_hincrby(key, "response_time_count", 1)

            redis_state_expire(key, self.MONTHLY_TTL)

        except Exception as e:
            logger.warning(f"Failed to record command usage in Redis: {e}")

    async def get_active_users(self, period: str = "daily") -> ActiveUserMetrics:
        """Get active user metrics.

        Args:
            period: Time period ('daily', 'weekly', 'monthly')

        Returns:
            ActiveUserMetrics
        """
        try:
            from tools.redis_state import redis_state_smembers

            daily_key = "community:discord:active_users:daily"
            weekly_key = "community:discord:active_users:weekly"
            monthly_key = "community:discord:active_users:monthly"

            daily_users = set(redis_state_smembers(daily_key) or [])
            weekly_users = set(redis_state_smembers(weekly_key) or [])
            monthly_users = set(redis_state_smembers(monthly_key) or [])

            return ActiveUserMetrics(
                total=len(monthly_users),
                daily=len(daily_users),
                weekly=len(weekly_users),
                monthly=len(monthly_users),
                new_users=0,  # Would need user join tracking
                returning_users=len(daily_users & weekly_users),
                peak_online=len(daily_users),
            )

        except Exception as e:
            logger.warning(f"Failed to get active users from Redis: {e}")

            # Return from local cache
            if "active_users" in self._local_cache:
                cache = self._local_cache["active_users"]
                return ActiveUserMetrics(
                    total=len(cache.get("monthly", set())),
                    daily=len(cache.get("daily", set())),
                    weekly=len(cache.get("weekly", set())),
                    new_users=0,
                    returning_users=0,
                    peak_online=len(cache.get("daily", set())),
                )

            return ActiveUserMetrics(0, 0, 0, 0, 0, 0, 0)

    async def get_engagement_metrics(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> EngagementMetrics:
        """Get engagement metrics.

        Args:
            start_date: Start of date range
            end_date: End of date range

        Returns:
            EngagementMetrics
        """
        try:
            from tools.redis_state import redis_state_get

            messages_key = "community:discord:messages:daily"
            reactions_key = "community:discord:reactions:daily"
            threads_key = "community:discord:threads:daily"

            messages_data = redis_state_get(messages_key)
            reactions_data = redis_state_get(reactions_key)
            threads_data = redis_state_get(threads_key)

            messages = int(messages_data.get("total", 0)) if messages_data else 0
            reactions = int(reactions_data.get("total", 0)) if reactions_data else 0
            threads = int(threads_data.get("total", 0)) if threads_data else 0

            # Get active users for calculations
            active_users = await self.get_active_users("daily")
            user_count = max(active_users.daily, 1)

            return EngagementMetrics(
                messages_sent=messages,
                reactions_added=reactions,
                threads_created=threads,
                avg_messages_per_user=messages / user_count,
                avg_reactions_per_user=reactions / user_count,
                total_engagement_score=messages + (reactions * 0.5) + (threads * 2),
            )

        except Exception as e:
            logger.warning(f"Failed to get engagement metrics: {e}")
            return EngagementMetrics(0, 0, 0, 0.0, 0.0, 0.0)

    async def get_command_usage(
        self,
        command_name: str | None = None,
        limit: int = 10,
    ) -> list[CommandUsageMetrics]:
        """Get command usage statistics.

        Args:
            command_name: Specific command to get stats for (None for all)
            limit: Maximum number of commands to return

        Returns:
            List of CommandUsageMetrics
        """
        results: list[CommandUsageMetrics] = []

        try:
            from tools.redis_state import redis_state_get, redis_state_scan_keys

            if command_name:
                # Get specific command
                keys = [self._get_command_usage_key(command_name)]
            else:
                # Get all commands
                pattern = "community:discord:command:*:usage"
                keys = redis_state_scan_keys(pattern, count=limit)

            for key in keys:
                data = redis_state_get(key)
                if not data:
                    continue

                # Extract command name from key
                parts = key.split(":")
                if len(parts) >= 3:
                    cmd_name = parts[2]
                else:
                    continue

                total = int(data.get("total", 0))
                errors = int(data.get("errors", 0))
                resp_time_sum = float(data.get("response_time_sum", 0))
                resp_time_count = int(data.get("response_time_count", 0))

                # Count unique users
                unique_users = sum(1 for k, v in data.items() if k.startswith("user:"))

                results.append(
                    CommandUsageMetrics(
                        command_name=cmd_name,
                        usage_count=total,
                        unique_users=unique_users,
                        avg_response_time_ms=(
                            resp_time_sum / resp_time_count
                            if resp_time_count > 0
                            else 0.0
                        ),
                        error_count=errors,
                        last_used=None,
                    )
                )

            # Sort by usage count
            results.sort(key=lambda x: x.usage_count, reverse=True)

            return results[:limit]

        except Exception as e:
            logger.warning(f"Failed to get command usage: {e}")
            return []

    async def get_metric_snapshot(
        self,
        metric_type: MetricType,
        period: str = "daily",
    ) -> MetricSnapshot:
        """Get a snapshot of current metrics.

        Args:
            metric_type: Type of metric to snapshot
            period: Time period

        Returns:
            MetricSnapshot
        """
        value = 0.0
        metadata: dict[str, Any] = {}

        if metric_type == MetricType.ACTIVE_USERS:
            metrics = await self.get_active_users(period)
            value = metrics.daily
            metadata = {
                "weekly": metrics.weekly,
                "monthly": metrics.monthly,
            }
        elif metric_type == MetricType.MESSAGES_SENT:
            eng = await self.get_engagement_metrics()
            value = float(eng.messages_sent)
        elif metric_type == MetricType.REACTIONS_ADDED:
            eng = await self.get_engagement_metrics()
            value = float(eng.reactions_added)
        elif metric_type == MetricType.THREADS_CREATED:
            eng = await self.get_engagement_metrics()
            value = float(eng.threads_created)
        elif metric_type == MetricType.COMMAND_USAGE:
            commands = await self.get_command_usage(limit=1)
            if commands:
                value = float(commands[0].usage_count)

        return MetricSnapshot(
            timestamp=datetime.now(UTC),
            metric_type=metric_type,
            value=value,
            period=period,
            metadata=metadata,
        )

    async def store_snapshot(self, snapshot: MetricSnapshot) -> None:
        """Store a metric snapshot.

        Args:
            snapshot: MetricSnapshot to store
        """
        try:
            from tools.redis_state import redis_state_set

            key = self._get_metric_key(
                snapshot.metric_type,
                snapshot.period,
                snapshot.timestamp,
            )

            redis_state_set(key, json.dumps(snapshot.to_dict()))
            redis_state_set(
                f"{key}:ttl",
                str(self._metrics_ttl_days * 86400),
            )

        except Exception as e:
            logger.warning(f"Failed to store metric snapshot: {e}")
