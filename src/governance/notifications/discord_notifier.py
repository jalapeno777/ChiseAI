"""Discord notifier for governance events."""

import asyncio
import logging
import re
from datetime import UTC, datetime
from typing import Any

from discord_alerts.config import DiscordConfig
from discord_alerts.discord_client import DiscordClient

logger = logging.getLogger(__name__)


def get_redis_client():
    """Get Redis client with graceful fallback."""
    try:
        from tools.redis_state import redis_state_get, redis_state_set

        return {"get": redis_state_get, "set": redis_state_set}
    except ImportError:
        return None


class DiscordNotifier:
    """Sends Discord notifications for governance events."""

    def __init__(
        self, client: DiscordClient | None = None, channel_id: str | None = None
    ):
        """Initialize Discord notifier.

        Args:
            client: DiscordClient instance (created if None)
            channel_id: Target channel ID for development events
        """
        config: DiscordConfig | None = None
        if client is None or channel_id is None:
            try:
                config = DiscordConfig.from_env()
            except Exception as e:
                logger.warning("Failed to load DiscordConfig from env: %s", e)
        if client is None:
            if config is None:
                config = DiscordConfig.from_env()
            client = DiscordClient(config)
            self._owns_client = True
        else:
            self._owns_client = False
        self.client = client
        default_channel = config.development_channel_id if config else None
        resolved_channel = channel_id or default_channel
        self.channel_id = self._validate_channel_id(
            resolved_channel,
            fallback=default_channel,
        )

    @staticmethod
    def _validate_channel_id(
        channel_id: str | None,
        fallback: str | None = None,
    ) -> str | None:
        """Validate Discord channel identifier with safe fallback."""
        if not channel_id:
            return fallback

        value = str(channel_id).strip()

        # Allow numeric snowflake IDs and channel names in local/dev tests.
        if re.fullmatch(r"\d{3,22}", value) or value.startswith("#"):
            return value

        logger.warning("Invalid Discord channel_id '%s', using fallback", value)
        return fallback

    def _is_enabled(self) -> bool:
        """Check if Discord notifications are enabled via feature flag."""
        redis = get_redis_client()
        if redis is None:
            return True  # Default to enabled
        try:
            from tools.redis_state import redis_state_hget

            flag = redis_state_hget(
                "chise:feature_flags:governance", "discord_notifications_enabled"
            )
            if flag is None:
                return True
            return flag.lower() in ("true", "1", "yes", "on")
        except Exception as e:
            logger.warning(f"Failed to read feature flag: {e}")
            return True

    def _is_duplicate(self, event_id: str) -> bool:
        """Check if event was already sent (deduplication)."""
        redis = get_redis_client()
        if redis is None:
            return False
        try:
            from tools.redis_state import redis_state_get

            key = f"bmad:chiseai:notifications:sent:{event_id}"
            return redis_state_get(key) is not None
        except Exception as e:
            logger.warning(f"Deduplication check failed: {e}")
            return False

    def _mark_sent(self, event_id: str) -> None:
        """Mark event as sent in Redis with 24h TTL."""
        redis = get_redis_client()
        if redis is None:
            return
        try:
            from tools.redis_state import redis_state_expire, redis_state_set

            key = f"bmad:chiseai:notifications:sent:{event_id}"
            redis_state_set(key, "1")
            redis_state_expire(key, 86400)  # 24h TTL
            logger.debug(f"Marked {event_id} as sent with 24h TTL")
        except Exception as e:
            logger.warning(f"Failed to mark event as sent: {e}")

    async def _send_with_retry(self, content: str, max_retries: int = 3) -> bool:
        """Send message with exponential backoff retry."""

        for attempt in range(max_retries):
            try:
                result = await self.client.send_message(
                    content=content, channel_id=self.channel_id
                )
                if result.success:
                    return True
                logger.warning(
                    f"Discord send failed (attempt {attempt + 1}): {result.error}"
                )
            except Exception as e:
                logger.warning(f"Discord send exception (attempt {attempt + 1}): {e}")

            if attempt < max_retries - 1:
                delay = min(2**attempt, 30)  # Exponential backoff, max 30s
                await asyncio.sleep(delay)

        return False

    async def notify_reflection(
        self,
        artifact: Any,
        artifact_type: str,  # "daily" or "weekly"
        artifact_path: str | None = None,
    ) -> bool:
        """Send reflection notification to Discord.

        Args:
            artifact: DailyReflectionArtifact or WeeklyReflectionArtifact
            artifact_type: "daily" or "weekly"
            artifact_path: Optional path to the artifact file

        Returns:
            True if sent successfully, False otherwise
        """
        if not self._is_enabled():
            logger.info("Discord notifications disabled by feature flag")
            return False

        # Generate event ID for deduplication
        event_id = f"reflection:{artifact_type}:{getattr(artifact, 'date', getattr(artifact, 'week_start', ''))}"

        if self._is_duplicate(event_id):
            logger.info(f"Skipping duplicate reflection notification: {event_id}")
            return False

        try:
            from .formatters import ReflectionNotificationFormatter

            formatter = ReflectionNotificationFormatter()

            if artifact_type == "daily":
                content = formatter.format_daily(artifact, artifact_path)
            else:
                content = formatter.format_weekly(artifact, artifact_path)

            success = await self._send_with_retry(content)
            if success:
                self._mark_sent(event_id)
                logger.info(f"Sent {artifact_type} reflection notification to Discord")
            return success

        except Exception as e:
            logger.error(f"Failed to send reflection notification: {e}")
            return False  # Non-blocking: return False on error

    async def notify_decision(self, decision_data: dict[str, Any]) -> bool:
        """Send decision notification to Discord.

        Args:
            decision_data: Dictionary with decision information

        Returns:
            True if sent successfully, False otherwise
        """
        if not self._is_enabled():
            logger.info("Discord notifications disabled by feature flag")
            return False

        # Generate event ID for deduplication
        story_id = decision_data.get("story_id", "unknown")
        timestamp = decision_data.get("timestamp", datetime.now(UTC).isoformat())
        event_id = f"decision:{story_id}:{timestamp}"

        if self._is_duplicate(event_id):
            logger.info(f"Skipping duplicate decision notification: {event_id}")
            return False

        try:
            from .formatters import DecisionNotificationFormatter

            formatter = DecisionNotificationFormatter()
            content = formatter.format_decision(decision_data)

            success = await self._send_with_retry(content)
            if success:
                self._mark_sent(event_id)
                logger.info("Sent decision notification to Discord")
            return success

        except Exception as e:
            logger.error(f"Failed to send decision notification: {e}")
            return False  # Non-blocking: return False on error
