#!/usr/bin/env python3
"""Test Discord webhook connectivity."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request


def get_webhook_url(explicit: str | None) -> str | None:
    return (
        explicit
        or os.getenv("DISCORD_STANDUP_WEBHOOK")
        or os.getenv("DISCORD_WEBHOOK_URL")
        or os.getenv("CHISE_DISCORD_WEBHOOK_URL")
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Test Discord webhook")
    parser.add_argument("--webhook-url", help="Override webhook URL")
    parser.add_argument(
        "--message",
        default="ChiseAI webhook connectivity test",
        help="Test message to send",
    )
    parser.add_argument("--dry-run", action="store_true", help="Only validate config")
    args = parser.parse_args()

    webhook = get_webhook_url(args.webhook_url)
    if not webhook:
        print("ERROR: Discord webhook URL not configured", file=sys.stderr)
        return 1

    if args.dry_run:
        print("Webhook configured")
        return 0

    payload = json.dumps({"content": args.message[:2000]}).encode("utf-8")
    req = urllib.request.Request(
        webhook,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "ChiseAI-Discord-TestWebhook/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status not in (200, 204):
                print(f"ERROR: Discord returned HTTP {resp.status}", file=sys.stderr)
                return 1
    except Exception as exc:
        print(f"ERROR: Webhook test failed: {exc}", file=sys.stderr)
        return 1

    print("Webhook test succeeded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
