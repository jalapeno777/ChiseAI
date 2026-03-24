#!/usr/bin/env python3
"""Monitor skill autonomy backlog queue depth and emit alerts.

Non-blocking by design:
- exits 0 on threshold breaches (alerts are operational signals, not hard failures)
- exits non-zero only for unrecoverable runtime/config errors
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso(dt: datetime | None = None) -> str:
    return (dt or utc_now()).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def redis_client():
    try:
        import redis

        host = os.getenv("REDIS_HOST", "host.docker.internal")
        port = int(os.getenv("REDIS_PORT", "6380"))
        db = int(os.getenv("REDIS_DB", "0"))
        client = redis.Redis(
            host=host,
            port=port,
            db=db,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
        )
        client.ping()
        return client
    except Exception:
        return None


def send_discord(webhook: str, message: str) -> None:
    try:
        import requests

        payload = {
            "embeds": [
                {
                    "title": "Skill Autonomy Queue Alert",
                    "description": message,
                    "color": 15158332,
                    "timestamp": iso(),
                }
            ]
        }
        requests.post(webhook, json=payload, timeout=8)
    except Exception:
        # Non-blocking alert path
        pass


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Monitor skill autonomy backlog queue depth"
    )
    ap.add_argument(
        "--queue-key",
        default="bmad:chiseai:skills:backlog:candidates",
        help="Redis queue key to monitor",
    )
    ap.add_argument("--warn-threshold", type=int, default=25)
    ap.add_argument("--crit-threshold", type=int, default=100)
    ap.add_argument(
        "--min-alert-interval-minutes",
        type=int,
        default=180,
        help="Suppress duplicate alerts within this interval",
    )
    ap.add_argument(
        "--alert-state-key",
        default="bmad:chiseai:monitoring:skill_autonomy_queue:last_alert",
        help="Redis key to track last alert timestamp",
    )
    ap.add_argument(
        "--log-file",
        default="logs/skill-autonomy/queue-monitor.log",
        help="Local log sink",
    )
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    Path(args.log_file).parent.mkdir(parents=True, exist_ok=True)

    client = redis_client()
    if client is None:
        msg = f"{iso()} ERROR redis_unavailable queue_key={args.queue_key}\n"
        with open(args.log_file, "a", encoding="utf-8") as f:
            f.write(msg)
        # runtime issue should surface
        print("SKILL_AUTONOMY_QUEUE_MONITOR")
        print(json.dumps({"ok": False, "error": "redis_unavailable"}))
        return 1

    depth = int(client.llen(args.queue_key) or 0)
    level = "ok"
    if depth >= args.crit_threshold:
        level = "critical"
    elif depth >= args.warn_threshold:
        level = "warning"

    alert_sent = False
    webhook = os.getenv("DISCORD_DEV_WEBHOOK_URL", os.getenv("DISCORD_WEBHOOK_URL", ""))

    if level in {"warning", "critical"} and webhook:
        last = client.get(args.alert_state_key)
        should_alert = True
        if last:
            try:
                last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
                if utc_now() - last_dt < timedelta(
                    minutes=args.min_alert_interval_minutes
                ):
                    should_alert = False
            except Exception:
                should_alert = True
        if should_alert:
            message = (
                f"Queue depth {depth} for `{args.queue_key}` (level={level}). "
                f"warn={args.warn_threshold}, crit={args.crit_threshold}."
            )
            send_discord(webhook, message)
            client.set(args.alert_state_key, iso())
            client.expire(args.alert_state_key, 60 * 60 * 24 * 14)
            alert_sent = True

    line = (
        f"{iso()} level={level} depth={depth} queue_key={args.queue_key} "
        f"warn={args.warn_threshold} crit={args.crit_threshold} alert_sent={str(alert_sent).lower()}\n"
    )
    with open(args.log_file, "a", encoding="utf-8") as f:
        f.write(line)

    print("SKILL_AUTONOMY_QUEUE_MONITOR")
    print(
        json.dumps(
            {
                "ok": True,
                "level": level,
                "depth": depth,
                "queue_key": args.queue_key,
                "warn_threshold": args.warn_threshold,
                "crit_threshold": args.crit_threshold,
                "alert_sent": alert_sent,
            }
        )
    )

    # Queue depth alert is non-blocking for workflows.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
