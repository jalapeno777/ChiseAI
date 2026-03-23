#!/usr/bin/env python3
"""
Merge Conflict Notifier

Posts merge conflict notifications to Discord and Redis.
Should be run after merge_conflict_detector.py detects conflicts.

Story: ST-GIT-006
CI Integration: Run via Woodpecker when conflicts detected.

Usage:
    python scripts/notifications/merge_conflict_notifier.py --pr 123 --files src/a.py src/b.py
    python scripts/notifications/merge_conflict_notifier.py --pr 123 --files src/a.py --branch feature/test

Environment Variables:
    DISCORD_WEBHOOK_URL - Discord webhook URL for #development channel
    DISCORD_DEV_WEBHOOK_URL - Alternative Discord webhook (backward compatibility)
    REDIS_CHANNEL - Redis channel for notifications (default: bmad:chiseai:notifications:merge_conflict)

Exit Codes:
    0 - Notification sent successfully
    1 - Failed to send notification
    2 - Invalid arguments
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any

# Allow direct script execution from any worktree
_REPO_ROOT = Path(__file__).resolve().parents[2]
for _path in (str(_REPO_ROOT), str(_REPO_ROOT / "src")):
    if _path not in sys.path:
        sys.path.insert(0, _path)


DEFAULT_REDIS_CHANNEL = "bmad:chiseai:notifications:merge_conflict"
DEFAULT_DISCORD_CHANNEL = "#development"


def _post_discord_webhook(webhook_url: str, payload: dict[str, Any]) -> bool:
    """Send embed to Discord webhook."""
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:  # nosec B310
            return resp.status == 200
    except Exception as e:
        print(f"Discord webhook error: {e}", file=sys.stderr)
        return False


def _post_redis(
    channel: str, message: dict[str, Any], host: str = "localhost", port: int = 6379
) -> bool:
    """Post message to Redis channel using HTTP API (if available) or redis-cli."""
    import subprocess

    try:
        # Try using redis-cli via subprocess
        import shlex

        msg_json = json.dumps(message)
        cmd = ["redis-cli", "-h", host, "-p", str(port), "PUBLISH", channel, msg_json]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return result.returncode == 0
    except Exception as e:
        print(f"Redis publish warning: {e}", file=sys.stderr)
        return False


def build_discord_embed(
    pr_number: int,
    branch: str,
    title: str | None,
    conflict_files: list[str],
    base_url: str = "http://host.docker.internal:3000",
) -> dict[str, Any]:
    """Build Discord embed for merge conflict notification."""
    repo = os.getenv("GITEA_REPO", "ChiseAI")
    owner = os.getenv("GITEA_OWNER", "craig")
    pr_url = f"{base_url}/{owner}/{repo}/pulls/{pr_number}"

    files_list = "\n".join([f"`{f}`" for f in conflict_files[:10]])
    if len(conflict_files) > 10:
        files_list += f"\n... and {len(conflict_files) - 10} more files"

    embed = {
        "title": f"⚠️ Merge Conflict Detected: PR #{pr_number}",
        "description": (
            f"**Branch:** `{branch}`\n"
            f"**Title:** {title or 'N/A'}\n\n"
            f"**Conflicting Files:**\n{files_list}\n\n"
            f"**Action Required:** Resolve conflicts before merge can proceed."
        ),
        "url": pr_url,
        "color": 0xE74C3C,  # Red
        "fields": [
            {
                "name": "PR Number",
                "value": str(pr_number),
                "inline": True,
            },
            {
                "name": "Branch",
                "value": f"`{branch}`",
                "inline": True,
            },
            {
                "name": "Conflict Count",
                "value": str(len(conflict_files)),
                "inline": True,
            },
        ],
        "footer": {
            "text": f"Merge Conflict Detector | {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')} UTC"
        },
    }
    return embed


def send_notification(
    pr_number: int,
    branch: str,
    conflict_files: list[str],
    title: str | None = None,
    base_url: str = "http://host.docker.internal:3000",
    discord_webhook: str | None = None,
    redis_channel: str = DEFAULT_REDIS_CHANNEL,
) -> tuple[bool, bool]:
    """
    Send conflict notification to Discord and Redis.

    Returns:
        Tuple of (discord_success, redis_success)
    """
    discord_success = False
    redis_success = False

    # Build notification payload
    discord_embed = build_discord_embed(
        pr_number=pr_number,
        branch=branch,
        title=title,
        conflict_files=conflict_files,
        base_url=base_url,
    )

    redis_message = {
        "event": "merge_conflict",
        "pr_number": pr_number,
        "branch": branch,
        "title": title,
        "conflict_files": conflict_files,
        "timestamp": datetime.now(UTC).isoformat(),
        "recommended_action": "resolve_conflicts",
    }

    # Send to Discord
    if discord_webhook:
        discord_payload = {
            "content": f"⚠️ **Merge Conflict Alert** - PR #{pr_number}",
            "embeds": [discord_embed],
        }
        discord_success = _post_discord_webhook(discord_webhook, discord_payload)

    # Send to Redis
    redis_success = _post_redis(redis_channel, redis_message)

    return discord_success, redis_success


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Notify about merge conflicts in a PR",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --pr 123 --files src/a.py src/b.py
  %(prog)s --pr 123 --files src/a.py --branch feature/test --title "My PR"

Exit codes:
  0 - Notification sent (at least one channel)
  1 - Failed to send notification (all channels)
  2 - Invalid arguments
        """,
    )
    parser.add_argument(
        "--pr",
        type=int,
        required=True,
        help="PR number with conflicts",
    )
    parser.add_argument(
        "--files",
        nargs="+",
        required=True,
        help="List of conflicting files",
    )
    parser.add_argument(
        "--branch",
        default="unknown",
        help="Branch name with conflicts",
    )
    parser.add_argument(
        "--title",
        default=None,
        help="PR title",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("GITEA_BASE_URL", "http://host.docker.internal:3000"),
        help="Gitea base URL",
    )
    parser.add_argument(
        "--discord-webhook",
        default=os.getenv("DISCORD_WEBHOOK_URL")
        or os.getenv("DISCORD_DEV_WEBHOOK_URL"),
        help="Discord webhook URL (default: $DISCORD_WEBHOOK_URL or $DISCORD_DEV_WEBHOOK_URL)",
    )
    parser.add_argument(
        "--redis-channel",
        default=DEFAULT_REDIS_CHANNEL,
        help=f"Redis channel (default: {DEFAULT_REDIS_CHANNEL})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print notification without sending",
    )

    args = parser.parse_args()

    if args.dry_run:
        print(f"[DRY RUN] Would notify about conflicts in PR #{args.pr}")
        print(f"  Branch: {args.branch}")
        print(f"  Title: {args.title or 'N/A'}")
        print(f"  Files: {args.files}")
        print(f"  Redis Channel: {args.redis_channel}")
        print(
            f"  Discord: {'configured' if args.discord_webhook else 'not configured'}"
        )
        return 0

    discord_success, redis_success = send_notification(
        pr_number=args.pr,
        branch=args.branch,
        conflict_files=args.files,
        title=args.title,
        base_url=args.base_url,
        discord_webhook=args.discord_webhook,
        redis_channel=args.redis_channel,
    )

    print("Notification sent:")
    print(f"  Discord: {'✓' if discord_success else '✗'}")
    print(f"  Redis: {'✓' if redis_success else '✗'}")

    if not discord_success and not redis_success:
        print("ERROR: Failed to send notification to any channel", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
