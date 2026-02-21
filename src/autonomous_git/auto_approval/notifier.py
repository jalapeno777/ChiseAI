"""Discord notifications for auto-approval."""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import json

logger = logging.getLogger(__name__)


@dataclass
class Notification:
    """Auto-approval notification."""

    pr_number: int
    pr_title: str
    author: str
    file_count: int
    classification_confidence: float
    timestamp: str
    success: bool
    error_message: Optional[str] = None


class DiscordNotifier:
    """Sends Discord notifications for auto-approval events."""

    def __init__(
        self,
        webhook_url: Optional[str] = None,
        channel: str = "#git-activity",
        alert_channel: str = "#alerts",
        rate_limit: str = "1 per 5 minutes",
        redis_client=None,
    ):
        """Initialize Discord notifier.

        Args:
            webhook_url: Discord webhook URL
            channel: Default channel for notifications
            alert_channel: Channel for alerts
            rate_limit: Rate limit string (e.g., "1 per 5 minutes")
            redis_client: Optional Redis client for rate limiting
        """
        self.webhook_url = webhook_url
        self.channel = channel
        self.alert_channel = alert_channel
        self.rate_limit = rate_limit
        self.redis = redis_client

        # Parse rate limit
        self._rate_limit_count = 1
        self._rate_limit_seconds = 300  # 5 minutes
        self._parse_rate_limit(rate_limit)

        # In-memory rate limiting fallback
        self._last_notification_time: Optional[datetime] = None

    def _parse_rate_limit(self, rate_limit: str):
        """Parse rate limit string."""
        try:
            # Format: "N per X minutes/hours/seconds"
            parts = rate_limit.lower().split()
            if len(parts) >= 4 and parts[1] == "per":
                self._rate_limit_count = int(parts[0])
                value = int(parts[2])
                unit = parts[3]

                if unit.startswith("minute"):
                    self._rate_limit_seconds = value * 60
                elif unit.startswith("hour"):
                    self._rate_limit_seconds = value * 3600
                elif unit.startswith("second"):
                    self._rate_limit_seconds = value
        except (ValueError, IndexError):
            logger.warning(f"Could not parse rate limit: {rate_limit}")

    async def _check_rate_limit(self) -> bool:
        """Check if we can send a notification based on rate limit.

        Returns:
            True if notification is allowed
        """
        if self.redis:
            try:
                key = "bmad:chiseai:auto_approval:notification_rate_limit"
                current = await self.redis.incr(key)
                if current == 1:
                    await self.redis.expire(key, self._rate_limit_seconds)

                if current > self._rate_limit_count:
                    logger.debug("Discord notification rate limit exceeded")
                    return False
                return True
            except Exception as e:
                logger.warning(f"Redis rate limit check failed: {e}")

        # In-memory rate limiting
        now = datetime.now(timezone.utc)
        if self._last_notification_time:
            elapsed = (now - self._last_notification_time).total_seconds()
            if elapsed < self._rate_limit_seconds:
                return False

        # Update last notification time when allowing
        self._last_notification_time = now
        return True

    async def notify_auto_merge(
        self,
        pr_number: int,
        pr_title: str,
        author: str,
        file_count: int,
        classification_confidence: float,
    ):
        """Send notification for successful auto-merge.

        Args:
            pr_number: PR number
            pr_title: PR title
            author: PR author
            file_count: Number of files changed
            classification_confidence: Classification confidence score
        """
        if not await self._check_rate_limit():
            logger.debug("Skipping Discord notification due to rate limit")
            return

        message = self._format_success_message(
            pr_number, pr_title, author, file_count, classification_confidence
        )

        await self._send_webhook(message, self.channel)
        self._last_notification_time = datetime.now(timezone.utc)

    async def notify_failure(
        self,
        pr_number: int,
        pr_title: str,
        author: str,
        error_message: str,
    ):
        """Send alert for failed auto-approval.

        Args:
            pr_number: PR number
            pr_title: PR title
            author: PR author
            error_message: Error message
        """
        # Always send failure notifications (no rate limit)
        message = self._format_failure_message(
            pr_number, pr_title, author, error_message
        )

        await self._send_webhook(message, self.alert_channel)

    def _format_success_message(
        self,
        pr_number: int,
        pr_title: str,
        author: str,
        file_count: int,
        classification_confidence: float,
    ) -> Dict[str, Any]:
        """Format success notification message."""
        confidence_pct = int(classification_confidence * 100)

        return {
            "content": None,
            "embeds": [
                {
                    "title": f"✅ Auto-Merged PR #{pr_number}",
                    "description": pr_title,
                    "color": 0x00FF00,  # Green
                    "fields": [
                        {
                            "name": "Author",
                            "value": author,
                            "inline": True,
                        },
                        {
                            "name": "Files Changed",
                            "value": str(file_count),
                            "inline": True,
                        },
                        {
                            "name": "Confidence",
                            "value": f"{confidence_pct}%",
                            "inline": True,
                        },
                    ],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "footer": {
                        "text": "ChiseAI Auto-Approval",
                    },
                }
            ],
        }

    def _format_failure_message(
        self,
        pr_number: int,
        pr_title: str,
        author: str,
        error_message: str,
    ) -> Dict[str, Any]:
        """Format failure notification message."""
        return {
            "content": f"🚨 Auto-approval failed for PR #{pr_number}",
            "embeds": [
                {
                    "title": pr_title,
                    "description": f"**Error:** {error_message}",
                    "color": 0xFF0000,  # Red
                    "fields": [
                        {
                            "name": "Author",
                            "value": author,
                            "inline": True,
                        },
                        {
                            "name": "PR",
                            "value": f"#{pr_number}",
                            "inline": True,
                        },
                    ],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "footer": {
                        "text": "ChiseAI Auto-Approval",
                    },
                }
            ],
        }

    async def _send_webhook(self, payload: Dict[str, Any], channel: str):
        """Send webhook to Discord.

        Args:
            payload: Message payload
            channel: Target channel
        """
        if not self.webhook_url:
            logger.debug(
                f"No webhook URL configured, would send to {channel}: {json.dumps(payload)}"
            )
            return

        try:
            # Import aiohttp here to avoid dependency issues
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                ) as response:
                    if response.status == 204:
                        logger.info(f"Discord notification sent to {channel}")
                    elif response.status == 429:
                        # Rate limited by Discord
                        retry_after = int(response.headers.get("Retry-After", 60))
                        logger.warning(
                            f"Discord rate limited, retry after {retry_after}s"
                        )
                    else:
                        logger.warning(f"Discord webhook returned {response.status}")
        except ImportError:
            logger.warning("aiohttp not installed, cannot send Discord notifications")
        except Exception as e:
            logger.error(f"Failed to send Discord notification: {e}")

    async def send_manual_notification(self, message: str):
        """Send a manual notification message.

        Args:
            message: Message to send
        """
        payload = {"content": message}
        await self._send_webhook(payload, self.channel)
