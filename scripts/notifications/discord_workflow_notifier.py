#!/usr/bin/env python3
"""
Discord Workflow Notifier
Story: ST-WORKFLOW-ARCHIVAL-001

Sends Discord notifications for workflow archival events.
Supports notification levels: INFO, WARNING, ERROR, CRITICAL

Usage:
    python scripts/notifications/discord_workflow_notifier.py --level INFO --title "Test" --message "Hello"
    python scripts/notifications/discord_workflow_notifier.py --level ERROR --title "Archival Failed" --message "Details..."
    echo '{"level": "WARNING", "title": "Alert", "message": "Something happened"}' | python scripts/notifications/discord_workflow_notifier.py --stdin

Environment Variables:
    DISCORD_WEBHOOK_URL - Discord webhook URL for notifications
    DISCORD_CHANNEL_ID - Discord channel ID (optional, for direct posting)

Exit Codes:
    0 - Notification sent successfully (or suppressed)
    1 - Failed to send notification
    2 - Invalid arguments
"""

import argparse
import json
import os
import sys
from datetime import datetime
from enum import Enum
from typing import Optional

import urllib.request
import urllib.error


class NotificationLevel(Enum):
    """Notification priority levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

    @property
    def color(self) -> int:
        """Discord embed color for this level."""
        colors = {
            NotificationLevel.INFO: 0x3498DB,  # Blue
            NotificationLevel.WARNING: 0xF39C12,  # Orange
            NotificationLevel.ERROR: 0xE74C3C,  # Red
            NotificationLevel.CRITICAL: 0x9B59B6,  # Purple
        }
        return colors[self]

    @property
    def emoji(self) -> str:
        """Emoji prefix for this level."""
        emojis = {
            NotificationLevel.INFO: "ℹ️",
            NotificationLevel.WARNING: "⚠️",
            NotificationLevel.ERROR: "❌",
            NotificationLevel.CRITICAL: "🚨",
        }
        return emojis[self]


# Discord channel IDs (for direct posting if webhook not available)
DEFAULT_CHANNELS = {
    "development": "1448414506412806347",
    "trading": "1444447985378398459",
    "alerts": "1480675962785107968",
}

NOTIFIER_VERSION = "1.0.0"


def send_discord_webhook(
    webhook_url: str,
    title: str,
    message: str,
    level: NotificationLevel,
    fields: Optional[list] = None,
    footer: Optional[str] = None,
) -> bool:
    """
    Send notification via Discord webhook.

    Args:
        webhook_url: Discord webhook URL
        title: Notification title
        message: Main message content
        level: Notification level
        fields: Optional list of field dicts ({name, value, inline})
        footer: Optional footer text

    Returns:
        True if sent successfully, False otherwise
    """
    embed = {
        "title": f"{level.emoji} {title}",
        "description": message,
        "color": level.color,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    if fields:
        embed["fields"] = fields

    if footer:
        embed["footer"] = {"text": footer}

    payload = {
        "embeds": [embed],
    }

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "ChiseAI-Workflow-Notifier/1.0",
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers=headers,
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status == 204  # Discord returns 204 on success

    except urllib.error.HTTPError as e:
        print(f"HTTP Error {e.code}: {e.reason}", file=sys.stderr)
        return False
    except urllib.error.URLError as e:
        print(f"URL Error: {e.reason}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"Error sending notification: {e}", file=sys.stderr)
        return False


def send_discord_channel_message(
    channel_id: str,
    message: str,
    bot_token: Optional[str] = None,
) -> bool:
    """
    Send message directly to Discord channel (requires bot token).

    Args:
        channel_id: Discord channel ID
        message: Message content
        bot_token: Discord bot token

    Returns:
        True if sent successfully, False otherwise
    """
    if not bot_token:
        print("Bot token required for direct channel posting", file=sys.stderr)
        return False

    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"

    headers = {
        "Authorization": f"Bot {bot_token}",
        "Content-Type": "application/json",
    }

    payload = {
        "content": message,
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers=headers,
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status == 200

    except Exception as e:
        print(f"Error sending channel message: {e}", file=sys.stderr)
        return False


def create_archival_summary_fields(
    stories_archived: int,
    duration_seconds: float,
    verification_status: str,
) -> list:
    """Create embed fields for archival summary notification."""
    return [
        {
            "name": "Stories Archived",
            "value": str(stories_archived),
            "inline": True,
        },
        {
            "name": "Duration",
            "value": f"{duration_seconds:.1f}s",
            "inline": True,
        },
        {
            "name": "Verification",
            "value": verification_status,
            "inline": True,
        },
    ]


def create_health_report_fields(
    total_stories: int,
    archived_stories: int,
    active_stories: int,
    orphaned_archives: int,
    integrity_failures: int,
) -> list:
    """Create embed fields for health report notification."""
    fields = [
        {
            "name": "Total Stories",
            "value": str(total_stories),
            "inline": True,
        },
        {
            "name": "Archived",
            "value": str(archived_stories),
            "inline": True,
        },
        {
            "name": "Active",
            "value": str(active_stories),
            "inline": True,
        },
    ]

    if orphaned_archives > 0:
        fields.append(
            {
                "name": "⚠️ Orphaned Archives",
                "value": str(orphaned_archives),
                "inline": True,
            }
        )

    if integrity_failures > 0:
        fields.append(
            {
                "name": "🚨 Integrity Failures",
                "value": str(integrity_failures),
                "inline": True,
            }
        )

    return fields


def main():
    parser = argparse.ArgumentParser(
        description="Send Discord notifications for workflow archival events"
    )
    parser.add_argument(
        "--level",
        type=str,
        choices=["INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Notification level",
    )
    parser.add_argument(
        "--title",
        type=str,
        required=True,
        help="Notification title",
    )
    parser.add_argument(
        "--message",
        type=str,
        required=True,
        help="Notification message",
    )
    parser.add_argument(
        "--webhook-url",
        type=str,
        default=os.environ.get("DISCORD_WEBHOOK_URL"),
        help="Discord webhook URL (or set DISCORD_WEBHOOK_URL env var)",
    )
    parser.add_argument(
        "--channel",
        type=str,
        choices=list(DEFAULT_CHANNELS.keys()),
        default="development",
        help="Target channel (for reference, webhook determines actual destination)",
    )
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="Read notification data from stdin as JSON",
    )
    parser.add_argument(
        "--suppress-if-healthy",
        action="store_true",
        help="Suppress notification if level is INFO and no issues",
    )
    parser.add_argument(
        "--field",
        type=str,
        action="append",
        help="Add embed field as 'name=value' (can be used multiple times)",
    )
    parser.add_argument(
        "--footer",
        type=str,
        default=f"ChiseAI Workflow Notifier v{NOTIFIER_VERSION}",
        help="Footer text",
    )

    args = parser.parse_args()

    # Handle stdin input
    if args.stdin:
        try:
            stdin_data = sys.stdin.read()
            data = json.loads(stdin_data)
            args.level = data.get("level", args.level)
            args.title = data.get("title", args.title)
            args.message = data.get("message", args.message)
        except json.JSONDecodeError as e:
            print(f"Invalid JSON from stdin: {e}", file=sys.stderr)
            return 2
        except Exception as e:
            print(f"Error reading stdin: {e}", file=sys.stderr)
            return 2

    # Check suppression
    if args.suppress_if_healthy and args.level == "INFO":
        print("Notification suppressed (healthy status)")
        return 0

    # Parse level
    try:
        level = NotificationLevel[args.level.upper()]
    except KeyError:
        print(f"Invalid notification level: {args.level}", file=sys.stderr)
        return 2

    # Check webhook URL
    if not args.webhook_url:
        # Try to construct from environment or use channel-based fallback
        print("No webhook URL provided, attempting fallback...", file=sys.stderr)

        # If we have a bot token, we could use direct channel posting
        bot_token = os.environ.get("DISCORD_BOT_TOKEN")
        if bot_token and args.channel in DEFAULT_CHANNELS:
            channel_id = DEFAULT_CHANNELS[args.channel]
            success = send_discord_channel_message(
                channel_id=channel_id,
                message=f"**{args.title}**\n{args.message}",
                bot_token=bot_token,
            )
            return 0 if success else 1

        print(
            "No notification method available (no webhook URL or bot token)",
            file=sys.stderr,
        )
        print(
            "Set DISCORD_WEBHOOK_URL environment variable or provide --webhook-url",
            file=sys.stderr,
        )
        # Return success to avoid blocking CI, but log the issue
        return 0

    # Parse fields
    fields = []
    if args.field:
        for field_str in args.field:
            if "=" in field_str:
                name, value = field_str.split("=", 1)
                fields.append(
                    {
                        "name": name,
                        "value": value,
                        "inline": True,
                    }
                )

    # Send notification
    success = send_discord_webhook(
        webhook_url=args.webhook_url,
        title=args.title,
        message=args.message,
        level=level,
        fields=fields if fields else None,
        footer=args.footer,
    )

    if success:
        print(f"Notification sent: {args.title}")
        return 0
    else:
        print("Failed to send notification", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
