#!/usr/bin/env python3
"""Post daily Full Pilot executive summary to Discord webhook."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]

import sys

sys.path.insert(0, str(PROJECT_ROOT / "src"))
from config.bootstrap import bootstrap

bootstrap(load_env=True)

FULL_PILOT_DIR = PROJECT_ROOT / "_bmad-output" / "full-pilot"
SCORECARD_PATH = FULL_PILOT_DIR / "scorecard.json"
GO_NO_GO_PATH = FULL_PILOT_DIR / "go-no-go-packet.json"


def now_iso() -> str:
    return (
        datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )


def webhook_url() -> str | None:
    return (
        os.getenv("DISCORD_AUTONOMY_WEBHOOK_URL")
        or os.getenv("DISCORD_DEV_WEBHOOK_URL")
        or os.getenv("DISCORD_WEBHOOK_URL")
        or os.getenv("CHISE_DISCORD_WEBHOOK_URL")
    )


def run_cmd(cmd: list[str]) -> int:
    proc = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=1200,
        check=False,
    )
    return proc.returncode


def ensure_artifacts() -> None:
    FULL_PILOT_DIR.mkdir(parents=True, exist_ok=True)
    if not SCORECARD_PATH.exists():
        rc = run_cmd(["python3", "scripts/ops/autonomy_scorecard.py", "--lookback-days", "30"])
        if rc != 0:
            raise RuntimeError("Failed generating scorecard")
    if not GO_NO_GO_PATH.exists():
        rc = run_cmd(["python3", "scripts/ops/generate_go_no_go_packet.py"])
        if rc != 0:
            raise RuntimeError("Failed generating go/no-go packet")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_message(scorecard: dict[str, Any], packet: dict[str, Any]) -> str:
    cadence = scorecard.get("cadence", {})
    alerts = scorecard.get("alerts", {})
    decision = packet.get("decision", "UNKNOWN")
    rationale = packet.get("rationale", "")

    return "\n".join(
        [
            "Full Pilot Daily Executive Summary",
            f"Generated: {now_iso()}",
            "",
            f"Decision: {decision}",
            f"Rationale: {rationale}",
            "",
            f"Cadence Success Rate: {cadence.get('success_rate_percent', 0)}%",
            f"Successful Runs: {cadence.get('success_runs', 0)}",
            f"Failed Runs: {cadence.get('failed_runs', 0)}",
            f"Dry Runs: {cadence.get('dry_runs', 0)}",
            f"Total Alerts (30d): {alerts.get('total_alerts', 0)}",
            "",
            "Top Required Actions:",
            *[f"- {x}" for x in packet.get("required_actions", [])[:3]],
        ]
    )[:1900]


def post_discord(content: str) -> None:
    webhook = webhook_url()
    if not webhook:
        raise RuntimeError("Discord webhook URL not configured")
    payload = json.dumps({"content": content}).encode("utf-8")
    req = urllib.request.Request(
        webhook,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "ChiseAI-FullPilot-DailySummary/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        if resp.status not in (200, 204):
            raise RuntimeError(f"Discord HTTP status={resp.status}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Post daily full-pilot executive summary")
    ap.add_argument("--dry-run", action="store_true", help="Do not post to Discord")
    ap.add_argument(
        "--regenerate", action="store_true", help="Regenerate scorecard and go/no-go first"
    )
    args = ap.parse_args()

    enabled_raw = os.getenv("CHISE_FULL_PILOT_DAILY_SUMMARY_ENABLED", "true").strip().lower()
    if enabled_raw not in {"1", "true", "yes", "on"}:
        print("Daily full-pilot summary is disabled by CHISE_FULL_PILOT_DAILY_SUMMARY_ENABLED")
        return 0

    if args.regenerate:
        if run_cmd(["python3", "scripts/ops/autonomy_scorecard.py", "--lookback-days", "30"]) != 0:
            return 1
        if run_cmd(["python3", "scripts/ops/generate_go_no_go_packet.py"]) != 0:
            return 1
    else:
        ensure_artifacts()

    scorecard = load_json(SCORECARD_PATH)
    packet = load_json(GO_NO_GO_PATH)
    message = build_message(scorecard, packet)

    if args.dry_run:
        print(message)
        return 0

    post_discord(message)
    print("Daily full-pilot summary posted to Discord")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
