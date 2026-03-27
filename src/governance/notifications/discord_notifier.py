"""Discord notifier for governance events."""

import asyncio
import logging
import re
from datetime import UTC, datetime, timedelta
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

# --- Noise Reduction Configuration Defaults ---
DEFAULT_NOTIFICATION_SCORE_THRESHOLD = 0.01  # 1% minimum score change to notify
DEFAULT_DIGEST_INTERVAL_MINUTES = 60
DEFAULT_DIGEST_MAX_ITEMS = 10


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
        *,
        notification_score_threshold: float = DEFAULT_NOTIFICATION_SCORE_THRESHOLD,
        digest_interval_minutes: int = DEFAULT_DIGEST_INTERVAL_MINUTES,
        digest_max_items: int = DEFAULT_DIGEST_MAX_ITEMS,
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
            notification_score_threshold: Minimum score delta to trigger
                self-assessment notification (default 0.01 = 1%).
            digest_interval_minutes: How often to flush low-severity digest.
            digest_max_items: Maximum items in digest before auto-flush.
        """
        self._config = config
        self._webhook_url: str | None = None
        self._owns_client = False

        # Noise reduction settings
        self._notification_score_threshold = notification_score_threshold
        self._digest_interval_minutes = digest_interval_minutes
        self._digest_max_items = digest_max_items
        self._low_severity_buffer: list[dict[str, Any]] = []
        self._digest_last_flush: datetime | None = None

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

    # --- Noise Reduction Methods ---

    @staticmethod
    def should_notify_for_assessment(
        current_score: float,
        previous_score: float | None,
        threshold: float = DEFAULT_NOTIFICATION_SCORE_THRESHOLD,
    ) -> bool:
        """Determine whether a self-assessment score change warrants a notification.

        Args:
            current_score: The overall score from the current assessment.
            previous_score: The overall score from the previous assessment,
                or None if this is the first assessment.
            threshold: Minimum absolute delta to consider a meaningful change.

        Returns:
            True if a notification should be sent:
            - Always True when previous_score is None (first assessment).
            - True when abs(current - previous) > threshold.
        """
        if previous_score is None:
            return True
        return abs(current_score - previous_score) > threshold

    def add_to_digest(self, event: dict[str, Any]) -> bool:
        """Buffer a low-severity event for batched digest delivery.

        High/critical events should NOT use this path -- they go through
        ``notify_autocog_event`` directly.

        Args:
            event: Dict with keys ``event_type``, ``severity``, ``summary``,
                ``run_id``, plus optional ``impact``, ``top_metrics``,
                ``artifact_path``.

        Returns:
            True if the event was buffered.  Returns False when the event
            is high/critical severity (caller should send immediately).
        """
        severity = (event.get("severity") or "low").lower()
        if severity in ("high", "critical"):
            return False

        self._low_severity_buffer.append(event)
        logger.debug(
            "Buffered low-severity event (buffer=%d/%d): %s",
            len(self._low_severity_buffer),
            self._digest_max_items,
            event.get("event_type"),
        )
        return True

    def should_flush_digest(self) -> bool:
        """Check if the low-severity digest should be flushed.

        Flush triggers:
        - Buffer reached ``_digest_max_items``.
        - Interval elapsed since last flush.
        """
        if len(self._low_severity_buffer) >= self._digest_max_items:
            return True
        if self._digest_last_flush is not None:
            elapsed = datetime.now(UTC) - self._digest_last_flush
            if elapsed >= timedelta(minutes=self._digest_interval_minutes):
                return True
        return False

    async def send_digest(self) -> bool:
        """Flush buffered low-severity events as a single digest notification.

        Returns:
            True if a digest was sent, False if buffer was empty or send failed.
        """
        if not self._low_severity_buffer:
            return False

        if not self._is_enabled():
            logger.info("Discord notifications disabled by feature flag")
            return False

        items = list(self._low_severity_buffer)
        self._low_severity_buffer.clear()
        self._digest_last_flush = datetime.now(UTC)

        try:
            from .formatters import LowSeverityDigestFormatter

            formatter = LowSeverityDigestFormatter()
            content = formatter.format_digest(items)
            success, message_id = await self._send_with_retry(content)
            if success:
                logger.info(
                    "Sent low-severity digest with %d items (message_id=%s)",
                    len(items),
                    message_id,
                )
            return success
        except Exception as e:
            logger.error("Failed to send low-severity digest: %s", e)
            return False

    async def _validate_channel(self) -> tuple[bool, str | None]:
        """Validate that the configured channel is accessible.

        Uses Discord API to verify the channel exists and the bot has access.
        Gracefully returns (True, None) if validation cannot be performed
        (e.g., no bot token, no channel configured).

        Returns:
            Tuple of (is_valid, error_message).
            - is_valid: True if channel is accessible or validation skipped
            - error_message: None if valid, descriptive error if invalid
        """
        if not self.channel_id:
            logger.debug("No channel_id configured, skipping validation")
            return True, None

        if self.client is None:
            logger.debug("No Discord client available, skipping channel validation")
            return True, None

        # Check if client has validate_channel_id method
        if not hasattr(self.client, "validate_channel_id"):
            logger.debug("Discord client does not support channel validation, skipping")
            return True, None

        try:
            is_valid, error_msg = await self.client.validate_channel_id(self.channel_id)
            if not is_valid:
                logger.error(
                    "Channel validation failed for %s: %s",
                    self.channel_id,
                    error_msg,
                )
            return is_valid, error_msg
        except Exception as e:
            # Graceful degradation: log warning but don't block sending
            logger.warning(
                "Channel validation raised exception for %s: %s. "
                "Proceeding with send attempt.",
                self.channel_id,
                e,
            )
            return True, None

    async def _send_with_retry(
        self, content: str, max_retries: int = 3
    ) -> tuple[bool, str | None]:
        """Send message with exponential backoff retry and delivery confirmation.

        Falls back to webhook if Discord client is unavailable.
        Returns tuple of (success, message_id) for delivery confirmation tracking.

        Returns:
            Tuple of (success, message_id).
            - success: True if message was sent successfully
            - message_id: Discord message ID if delivered via bot, None otherwise
        """
        # Validate channel accessibility before attempting send
        channel_valid, channel_error = await self._validate_channel()
        if not channel_valid:
            logger.error(
                "Cannot send notification - channel validation failed: %s",
                channel_error,
            )
            return False, None

        # Try Discord client first if available
        if self.client is not None:
            for attempt in range(max_retries):
                try:
                    result = await self.client.send_message(
                        content=content, channel_id=self.channel_id
                    )
                    if result.success:
                        logger.info(
                            "Discord notification sent successfully to channel %s "
                            "(method=%s, message_id=%s)",
                            self.channel_id,
                            result.method,
                            result.message_id,
                        )
                        return True, result.message_id
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
            webhook_success = await self._send_via_webhook(content, max_retries)
            return webhook_success, None

        logger.error("No Discord client or webhook available for notification")
        return False, None

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

            success, message_id = await self._send_with_retry(content)
            if success:
                self._mark_sent(event_id)
                logger.info(
                    f"Sent {artifact_type} reflection notification to Discord "
                    f"(message_id=%s)",
                    message_id,
                )
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

            success, message_id = await self._send_with_retry(content)
            if success:
                self._mark_sent(event_id)
                logger.info(
                    "Sent decision notification to Discord (message_id=%s)",
                    message_id,
                )
            return success

        except Exception as e:
            logger.error(f"Failed to send decision notification: {e}")
            return False  # Non-blocking: return False on error

    async def notify_self_assessment(
        self,
        artifact: Any,
        artifact_path: str | None = None,
        previous_score: float | None = None,
    ) -> bool:
        """Send self-assessment completion event to Discord.

        Event type: self_assessment_completed

        Noise reduction: If ``previous_score`` is provided and the delta
        between it and ``artifact.overall_score`` is within
        ``_notification_score_threshold``, the notification is suppressed
        (unless this is the first assessment).

        Args:
            artifact: The self-assessment artifact.
            artifact_path: Optional path to the persisted artifact.
            previous_score: Overall score from the previous assessment,
                or None for first assessment (always notifies).

        Returns:
            True if sent successfully, False if suppressed or failed.
        """
        if not self._is_enabled():
            logger.info("Discord notifications disabled by feature flag")
            return False

        current_score = getattr(artifact, "overall_score", 0.0)

        if not self.should_notify_for_assessment(
            current_score, previous_score, self._notification_score_threshold
        ):
            logger.info(
                "Self-assessment score unchanged (%.4f), suppressing notification",
                current_score,
            )
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
            success, message_id = await self._send_with_retry(content)
            if success:
                self._mark_sent(event_id)
                logger.info(
                    "Sent self-assessment completion to Discord (message_id=%s)",
                    message_id,
                )
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
            success, message_id = await self._send_with_retry(content)
            if success:
                self._mark_sent(event_id)
                logger.info(
                    "Sent autonomous cognition event: %s (message_id=%s)",
                    event_type,
                    message_id,
                )
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
