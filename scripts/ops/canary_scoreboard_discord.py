#!/usr/bin/env python3
"""Canary scoreboard Discord notification script - hybrid scheduler edition.

Architecture:
  - RUNTIME (primary): Run from host/runtime environment. Reads .env secrets.
    Emits local status artifact for audit. Falls back to DRY-RUN if webhook
    missing or test mode requested.
  - WOODPECKER (fallback): Daily heartbeat in cron-eval.yaml. Always exits 0.
    Emits DRY-RUN if webhook not available in CI context.

Usage:
  python3 scripts/ops/canary_scoreboard_discord.py          # normal run
  python3 scripts/ops/canary_scoreboard_discord.py --dry-run # safe test, no webhook
  python3 scripts/ops/canary_scoreboard_discord.py --test    # uses DISCORD_TEST_WEBHOOK_URL
"""

import argparse
import glob
import json
import os
import sys
from datetime import datetime

import requests


def main():
    parser = argparse.ArgumentParser(description="Canary scoreboard Discord sender")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Emit DRY-RUN status and skip webhook call",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Use DISCORD_TEST_WEBHOOK_URL instead of DISCORD_WEBHOOK_URL",
    )
    args = parser.parse_args()

    # Determine webhook URL
    if args.test:
        webhook_url = os.environ.get("DISCORD_TEST_WEBHOOK_URL")
        status_file = "_bmad-output/ci/canary-scoreboard-discord.test.status"
    else:
        webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
        status_file = "_bmad-output/ci/canary-scoreboard-discord.status"

    # Emit local audit artifact (always, even DRY-RUN)
    audit_dir = "_bmad-output/ci"
    os.makedirs(audit_dir, exist_ok=True)
    audit_file = os.path.join(audit_dir, "canary-scoreboard-discord.audit.json")
    audit_entry = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "mode": "test" if args.test else ("dry-run" if args.dry_run else "live"),
        "webhook_configured": bool(webhook_url),
        "webhook_prefix": webhook_url[:40] + "..." if webhook_url else None,
    }

    if not webhook_url or args.dry_run:
        print("DRY-RUN mode: skipping scoreboard webhook")
        with open(status_file, "w") as f:
            f.write("DRY-RUN")
        audit_entry["result"] = "skipped"
        with open(audit_file, "w") as f:
            json.dump(audit_entry, f, indent=2)
        return

    canary_files = sorted(glob.glob("data/canary/*.json"))
    active_canaries = []
    for f in canary_files:
        try:
            with open(f) as fh:
                data = json.load(fh)
                if data.get("status") in ("active", "running", "canary"):
                    active_canaries.append(data)
        except Exception:
            pass

    if not active_canaries:
        embed = {
            "title": "R2a Canary Scoreboard - DRY-RUN",
            "description": "No active canaries found. This is a test message.",
            "color": 0x808080,
            "fields": [
                {"name": "Total Trades", "value": "-", "inline": True},
                {"name": "Net PnL", "value": "-", "inline": True},
                {"name": "Win Rate", "value": "-", "inline": True},
                {"name": "Max Drawdown", "value": "-", "inline": True},
            ],
            "footer": {
                "text": "ChiseAI | " + datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
            },
        }
    else:
        for c in active_canaries:
            trades = c.get("total_trades", c.get("trades", 0))
            pnl = c.get("net_profit", c.get("pnl", 0.0))
            win_rate = c.get("win_rate", 0.0)
            dd = c.get("max_drawdown", c.get("drawdown", 0.0))
            name = c.get("name", c.get("strategy", "unknown"))
            embed = {
                "title": name + " Canary Scoreboard",
                "description": c.get("description", "Active canary period"),
                "color": 0x00FF00 if pnl > 0 else 0xFF0000,
                "fields": [
                    {"name": "Total Trades", "value": str(trades), "inline": True},
                    {"name": "Net PnL", "value": f"${pnl:.2f}", "inline": True},
                    {
                        "name": "Win Rate",
                        "value": f"{win_rate:.1%}",
                        "inline": True,
                    },
                    {
                        "name": "Max Drawdown",
                        "value": f"{dd:.2%}",
                        "inline": True,
                    },
                ],
                "footer": {
                    "text": "ChiseAI | "
                    + datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
                },
            }

    payload = {"embeds": [embed]}
    resp = requests.post(webhook_url, json=payload)
    audit_entry["http_status"] = resp.status_code
    audit_entry["http_response"] = resp.text[:200]

    if resp.status_code not in (200, 204):
        print("DISCORD error: " + str(resp.status_code) + " " + resp.text[:200])
        with open(status_file, "w") as f:
            f.write("ERROR")
        audit_entry["result"] = "error"
        with open(audit_file, "w") as f:
            json.dump(audit_entry, f, indent=2)
        return

    with open(status_file, "w") as f:
        f.write("PASS")
    audit_entry["result"] = "pass"
    with open(audit_file, "w") as f:
        json.dump(audit_entry, f, indent=2)


if __name__ == "__main__":
    main()
