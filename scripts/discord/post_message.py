#!/usr/bin/env python3
"""Post a message to Discord webhook.

Compatibility utility used by standup/reporting command docs.
"""

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
    parser = argparse.ArgumentParser(description="Post a message to Discord webhook")
    parser.add_argument("--message", required=True, help="Message content")
    parser.add_argument("--channel", help="Channel identifier (informational only)")
    parser.add_argument("--webhook-url", help="Override webhook URL")
    args = parser.parse_args()

    webhook = get_webhook_url(args.webhook_url)
    if not webhook:
        print("ERROR: Discord webhook URL not configured", file=sys.stderr)
        return 1

    content = args.message
    if args.channel:
        content = f"[channel:{args.channel}]\n{content}"

    payload = json.dumps({"content": content[:2000]}).encode("utf-8")
    req = urllib.request.Request(
        webhook,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "ChiseAI-Discord-PostMessage/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status not in (200, 204):
                print(f"ERROR: Discord returned HTTP {resp.status}", file=sys.stderr)
                return 1
    except Exception as exc:
        print(f"ERROR: Failed to post Discord message: {exc}", file=sys.stderr)
        return 1

    print("Message posted to Discord")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
