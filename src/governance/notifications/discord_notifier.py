"""Discord notifier for governance events."""

import asyncio
import logging
import re
from datetime import UTC, datetime
from typing import Any

from discord_alerts.config import DiscordConfig
from discord_alerts.discord_client import DiscordClient

logger = logging.getLogger(__name__)

# Required severity levels for routing configuration
REQUIRED_SEVERITY_LEVELS = {"high", "medium", "low", "critical"}

# Discord channel ID validation pattern (17-20 digit numeric)
CHANNEL_ID_PATTERN = re.compile(r"^\d{17,20}$")

# Discord webhook URL validation pattern
WEBHOOK_URL_PATTERN = re.compile(
    r"^https://discord\.com/api/webhooks/\d{17,20}/[A-Za-z0-9_-]+$"
)


def validate_routing_config(routing_config: dict[str, Any]) -> dict[str, Any]:
    """Validate Discord routing configuration.

    Validates that the routing configuration contains all required severity levels
    with valid channel IDs and optional webhook URLs.

    Args:
        routing_config: Dictionary mapping severity levels to channel configurations.
            Expected format:
            {
                "high": {"channel_id": "123...", "webhook_url": "..."},
                "medium": {"channel_id": "456..."},
                "low": {"channel_id": "789..."},
                "critical": {"channel_id": "012...", "webhook_url": "..."}
            }

    Returns:
        Dictionary with validation results:
        {
            "valid": bool,
            "errors": [list of error messages],
            "missing": [list of missing required severity levels]
        }

    Example:
        >>> config = {
        ...     "high": {"channel_id": "1234567890123456789"},
        ...     "medium": {"channel_id": "9876543210987654321"},
        ...     "low": {"channel_id": "1111111111111111111"},
        ...     "critical": {"channel_id": "2222222222222222222"}
        ... }
        >>> result = validate_routing_config(config)
        >>> result["valid"]
        True
    """
    errors: list[str] = []
    missing: list[str] = []

    # Check if routing_config is a dictionary
    if not isinstance(routing_config, dict):
        return {
            "valid": False,
            "errors": ["Routing configuration must be a dictionary"],
            "missing": list(REQUIRED_SEVERITY_LEVELS),
        }

    # Check for missing required severity levels
    configured_levels = set(routing_config.keys())
    missing = list(REQUIRED_SEVERITY_LEVELS - configured_levels)

    if missing:
        errors.append(f"Missing required severity levels: {', '.join(sorted(missing))}")

    # Check for channel name conflicts (same channel_id used for multiple severities)
    channel_id_to_severities: dict[str, list[str]] = {}
    for severity, config in routing_config.items():
        if not isinstance(config, dict):
            errors.append(f"Configuration for '{severity}' must be a dictionary")
            continue

        channel_id = config.get("channel_id")
        if channel_id:
            if channel_id not in channel_id_to_severities:
                channel_id_to_severities[channel_id] = []
            channel_id_to_severities[channel_id].append(severity)

    # Report channel conflicts
    for channel_id, severities in channel_id_to_severities.items():
        if len(severities) > 1:
            errors.append(
                f"Channel ID '{channel_id}' is used for multiple severity levels: "
                f"{', '.join(sorted(severities))}"
            )

    # Validate each configured severity level
    for severity, config in routing_config.items():
        if not isinstance(config, dict):
            continue  # Already reported above

        # Check if channel_id exists
        channel_id = config.get("channel_id")
        if channel_id is None:
            errors.append(f"'{severity}' is missing required 'channel_id'")
        elif not isinstance(channel_id, str):
            errors.append(
                f"'{severity}' channel_id must be a string, got {type(channel_id).__name__}"
            )
        elif not CHANNEL_ID_PATTERN.match(channel_id):
            errors.append(
                f"'{severity}' has invalid channel_id '{channel_id}'. "
                f"Expected 17-20 digit numeric Discord channel ID"
            )

        # Validate webhook URL if present
        webhook_url = config.get("webhook_url")
        if webhook_url is not None:
            if not isinstance(webhook_url, str):
                errors.append(
                    f"'{severity}' webhook_url must be a string, "
                    f"got {type(webhook_url).__name__}"
                )
            elif not WEBHOOK_URL_PATTERN.match(webhook_url):
                errors.append(
                    f"'{severity}' has invalid webhook_url format. "
                    f"Expected: https://discord.com/api/webhooks/<id>/<token>"
                )

        # Check for unknown configuration keys
        known_keys = {"channel_id", "webhook_url"}
        unknown_keys = set(config.keys()) - known_keys
        if unknown_keys:
            errors.append(
                f"'{severity}' has unknown configuration keys: {', '.join(sorted(unknown_keys))}"
            )

    return {
        "valid": len(errors) == 0 and len(missing) == 0,
        "errors": errors,
        "missing": missing,
    }


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
        self,
        client: DiscordClient | None = None,
        channel_id: str | None = None,
        config: DiscordConfig | None = None,
    ):
        """Initialize Discord notifier.

        Supports three initialization patterns:
        1. Injected client: notifier = DiscordNotifier(client=my_client)
        2. Injected config: notifier = DiscordNotifier(config=my_config)
        3. Environment-based: notifier = DiscordNotifier()  # loads from env

        Args:
            client: DiscordClient instance (created if None)
            channel_id: Target channel ID for development events
            config: DiscordConfig instance (loaded from env if None and needed)
        """
        self._config = config
        self._webhook_url: str | None = None
        self._owns_client = False

        # Case 1: Client is injected - use it directly
        if client is not None:
            self.client = client
            self._owns_client = False
            # Try to extract channel_id from injected config or use provided
            resolved_channel = channel_id
            if resolved_channel is None and self._config is not None:
                resolved_channel = self._config.development_channel_id
            self.channel_id = self._validate_channel_id(
                resolved_channel,
                fallback=None,
            )
            return

        # Case 2 & 3: Need to create client - ensure we have config
        if self._config is None:
            try:
                self._config = DiscordConfig.from_env()
            except Exception as e:
                logger.warning("Failed to load DiscordConfig from env: %s", e)
                self.client = None
                self.channel_id = None
                return

        # Create client from config, with webhook fallback
        self.channel_id = self._validate_channel_id(
            channel_id or self._config.development_channel_id,
            fallback=self._config.development_channel_id,
        )
        self._webhook_url = self._config.webhook_url

        # Try to create DiscordClient, fall back to webhook-only mode
        try:
            self.client = DiscordClient(self._config)
            self._owns_client = True
        except Exception as e:
            logger.warning(
                "Failed to create DiscordClient, will use webhook fallback: %s", e
            )
            self.client = None
            self._owns_client = False

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
        """Send message with exponential backoff retry.

        Falls back to webhook if Discord client is unavailable.
        """
        # Try Discord client first if available
        if self.client is not None:
            for attempt in range(max_retries):
                try:
                    result = await self.client.send_message(
                        content=content, channel_id=self.channel_id
                    )
                    if result.success:
                        return True
                    logger.warning(
                        "Discord send failed (attempt %d): %s",
                        attempt + 1,
                        result.error,
                    )
                except Exception as e:
                    logger.warning(
                        "Discord send exception (attempt %d): %s", attempt + 1, e
                    )

                if attempt < max_retries - 1:
                    delay = min(2**attempt, 30)  # Exponential backoff, max 30s
                    await asyncio.sleep(delay)

        # Fallback to webhook if configured
        if self._webhook_url:
            return await self._send_via_webhook(content, max_retries)

        logger.error("No Discord client or webhook available for notification")
        return False

    async def _send_via_webhook(self, content: str, max_retries: int = 3) -> bool:
        """Send message via Discord webhook.

        Args:
            content: Message content to send
            max_retries: Maximum number of retry attempts

        Returns:
            True if sent successfully, False otherwise
        """
        try:
            import aiohttp
        except ImportError:
            logger.error("aiohttp required for webhook fallback")
            return False

        payload = {"content": content}
        if len(content) > 2000:
            # Discord webhook content limit is 2000 chars
            payload["content"] = content[:1997] + "..."

        if not self._webhook_url:
            return False

        webhook_url = self._webhook_url  # type: ignore[assignment]
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        webhook_url,
                        json=payload,
                        headers={"Content-Type": "application/json"},
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as response:
                        if response.status in (200, 204):
                            logger.debug("Webhook send successful")
                            return True
                        logger.warning(
                            "Webhook send failed (attempt %d): HTTP %d",
                            attempt + 1,
                            response.status,
                        )
            except Exception as e:
                logger.warning(
                    "Webhook send exception (attempt %d): %s", attempt + 1, e
                )

            if attempt < max_retries - 1:
                delay = min(2**attempt, 30)
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

    async def notify_self_assessment(
        self,
        artifact: Any,
        artifact_path: str | None = None,
    ) -> bool:
        """Send self-assessment completion event to Discord.

        Event type: self_assessment_completed
        """
        if not self._is_enabled():
            logger.info("Discord notifications disabled by feature flag")
            return False

        event_date = getattr(artifact, "assessment_date", "")
        event_id = f"self_assessment_completed:{event_date}"

        if self._is_duplicate(event_id):
            logger.info(f"Skipping duplicate self-assessment notification: {event_id}")
            return False

        try:
            from .formatters import SelfAssessmentNotificationFormatter

            formatter = SelfAssessmentNotificationFormatter()
            content = formatter.format_self_assessment(
                artifact=artifact,
                artifact_path=artifact_path,
            )
            success = await self._send_with_retry(content)
            if success:
                self._mark_sent(event_id)
                logger.info("Sent self-assessment completion to Discord")
            return success
        except Exception as e:
            logger.error(f"Failed to send self-assessment notification: {e}")
            return False

    async def notify_autocog_event(
        self,
        event_type: str,
        severity: str,
        summary: str,
        impact: str,
        top_metrics: dict[str, Any] | None,
        artifact_path: str | None,
        run_id: str,
        title: str | None = None,
        issue: str | None = None,
        intended_resolution: str | None = None,
        expected_improvement: str | None = None,
        outcome_status: str | None = None,
        evidence_reasoning: list[str] | None = None,
        decision_packet: dict[str, Any] | None = None,
    ) -> bool:
        """Send autonomous cognition event notification to Discord."""
        if not self._is_enabled():
            logger.info("Discord notifications disabled by feature flag")
            return False

        event_id = f"autocog:{event_type}:{run_id}"
        if self._is_duplicate(event_id):
            logger.info(f"Skipping duplicate autocog notification: {event_id}")
            return False

        try:
            from .formatters import AutocogEventFormatter

            formatter = AutocogEventFormatter()
            content = formatter.format_event(
                event_type=event_type,
                severity=severity,
                summary=summary,
                impact=impact,
                top_metrics=top_metrics or {},
                artifact_path=artifact_path,
                run_id=run_id,
                title=title,
                issue=issue,
                intended_resolution=intended_resolution,
                expected_improvement=expected_improvement,
                outcome_status=outcome_status,
                evidence_reasoning=evidence_reasoning or [],
                decision_packet=decision_packet or {},
            )
            success = await self._send_with_retry(content)
            if success:
                self._mark_sent(event_id)
                logger.info("Sent autonomous cognition event: %s", event_type)
            return success
        except Exception as e:
            logger.error(
                "Failed to send autonomous cognition event %s: %s", event_type, e
            )
            return False

    async def close(self) -> None:
        """Close owned Discord client resources."""
        if not self._owns_client or self.client is None:
            return
        try:
            await self.client.disconnect()
        except Exception as e:
            logger.debug("Discord client close skipped: %s", e)
