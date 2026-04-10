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

# ── Helpers ────────────────────────────────────────────────────────────────


def load_canary_json(path):
    """Load and parse a single canary JSON file."""
    with open(path) as fh:
        return json.load(fh)


def select_schema(canary):
    """Select schema type based on canary_mode field.

    Returns:
        "memory"  - memory-domain metrics (recall_quality, context_cost, etc.)
        "trading" - trading-domain metrics (total_trades, net_profit, etc.)

    Legacy behavior: if canary_mode is absent, defaults to "trading".
    """
    mode = canary.get("canary_mode")
    if mode == "memory":
        return "memory"
    return "trading"


# ── Memory Schema ──────────────────────────────────────────────────────────


def build_memory_embed(canary):
    """Build Discord embed for memory-domain canary.

    Fields:
      - Recall Quality (0-1 score)
      - Context Cost (token count)
      - Token Efficiency (0-1 ratio)
      - Staleness Quality (0-1 score)
      - Anti-Gaming Status (pass/fail/warn)
      - Operational Reliability (0-1 ratio)

    Missing fields show "MISSING" (not zero).
    If ALL fields missing, adds MEMORY METRICS MISSING notice.
    """
    metrics = canary.get("metrics", {})
    fields = []
    missing_keys = []

    # recall_quality
    val = metrics.get("recall_quality")
    if val is not None:
        fields.append({"name": "Recall Quality", "value": str(val), "inline": True})
    else:
        fields.append({"name": "Recall Quality", "value": "MISSING", "inline": True})
        missing_keys.append("recall_quality")

    # context_cost
    val = metrics.get("context_cost")
    if val is not None:
        fields.append({"name": "Context Cost", "value": str(int(val)), "inline": True})
    else:
        fields.append({"name": "Context Cost", "value": "MISSING", "inline": True})
        missing_keys.append("context_cost")

    # token_efficiency
    val = metrics.get("token_efficiency")
    if val is not None:
        fields.append({"name": "Token Efficiency", "value": str(val), "inline": True})
    else:
        fields.append({"name": "Token Efficiency", "value": "MISSING", "inline": True})
        missing_keys.append("token_efficiency")

    # staleness_quality
    val = metrics.get("staleness_quality")
    if val is not None:
        fields.append({"name": "Staleness Quality", "value": str(val), "inline": True})
    else:
        fields.append({"name": "Staleness Quality", "value": "MISSING", "inline": True})
        missing_keys.append("staleness_quality")

    # anti_gaming_status
    val = metrics.get("anti_gaming_status")
    if val is not None:
        fields.append({"name": "Anti-Gaming Status", "value": str(val), "inline": True})
    else:
        fields.append(
            {"name": "Anti-Gaming Status", "value": "MISSING", "inline": True}
        )
        missing_keys.append("anti_gaming_status")

    # operational_reliability
    val = metrics.get("operational_reliability")
    if val is not None:
        fields.append(
            {"name": "Operational Reliability", "value": str(val), "inline": True}
        )
    else:
        fields.append(
            {"name": "Operational Reliability", "value": "MISSING", "inline": True}
        )
        missing_keys.append("operational_reliability")

    # If ALL fields missing, add full notice
    if len(missing_keys) == 6:
        fields.append(
            {
                "name": "MEMORY METRICS MISSING",
                "value": ", ".join(missing_keys),
                "inline": False,
            }
        )

    return {
        "title": canary.get("name", canary.get("canary_id", "Memory Canary"))
        + " Canary Scoreboard",
        "description": canary.get("description", "Memory domain validation"),
        "color": 0x0088FF,  # Neutral blue - not PnL-based
        "fields": fields,
        "footer": {
            "text": "ChiseAI | " + datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        },
    }


# ── Trading Schema ─────────────────────────────────────────────────────────


def build_trading_embed(canary):
    """Build Discord embed for trading-domain canary (legacy schema).

    Fields:
      - Total Trades (integer)
      - Net PnL (dollar amount with sign)
      - Win Rate (percentage)
      - Max Drawdown (percentage)

    Color: green (0x00FF00) if profit, red (0xFF0000) if loss.
    """
    # Support both flat structure and nested metrics
    if "metrics" in canary:
        m = canary["metrics"]
        trades = m.get("total_trades", 0)
        pnl = m.get("net_profit", 0.0)
        win_rate = m.get("win_rate", 0.0)
        dd = m.get("max_drawdown_pct", m.get("max_drawdown", 0.0))
    else:
        # Legacy flat structure
        trades = canary.get("total_trades", canary.get("trades", 0))
        pnl = canary.get("net_profit", canary.get("pnl", 0.0))
        win_rate = canary.get("win_rate", 0.0)
        dd = canary.get("max_drawdown", canary.get("drawdown", 0.0))

    return {
        "title": canary.get("name", canary.get("strategy", "Trading Canary"))
        + " Canary Scoreboard",
        "description": canary.get("description", "Active canary period"),
        "color": 0x00FF00 if pnl > 0 else 0xFF0000,
        "fields": [
            {"name": "Total Trades", "value": str(trades), "inline": True},
            {"name": "Net PnL", "value": f"${pnl:.2f}", "inline": True},
            {"name": "Win Rate", "value": f"{win_rate:.1%}", "inline": True},
            {"name": "Max Drawdown", "value": f"{dd:.2%}", "inline": True},
        ],
        "footer": {
            "text": "ChiseAI | " + datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        },
    }


# ── Missing Canary ─────────────────────────────────────────────────────────


def build_missing_embed():
    """Build Discord embed when no active canaries found."""
    return {
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


# ── Main ───────────────────────────────────────────────────────────────────


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
            data = load_canary_json(f)
            if data.get("status") in ("active", "running", "canary"):
                active_canaries.append(data)
        except Exception:
            pass

    if not active_canaries:
        embed = build_missing_embed()
    else:
        # Use first active canary for single-embed display
        # TODO: support multi-canary embeds in future
        canary = active_canaries[0]
        schema = select_schema(canary)
        if schema == "memory":
            embed = build_memory_embed(canary)
        else:
            embed = build_trading_embed(canary)

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
