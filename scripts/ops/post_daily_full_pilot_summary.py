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
SCORECARD_7D_PATH = FULL_PILOT_DIR / "scorecard-7d.json"
GO_NO_GO_PATH = FULL_PILOT_DIR / "go-no-go-packet.json"
CADENCE_STATE_PATH = PROJECT_ROOT / "_bmad-output" / "autonomy-cadence" / "state.json"
CADENCE_RUNS_PATH = PROJECT_ROOT / "_bmad-output" / "autonomy-cadence" / "runs.jsonl"
AUTODISPATCH_TASKS_PATH = (
    PROJECT_ROOT / "_bmad-output" / "autonomy-dispatch" / "tasks.jsonl"
)


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
        rc = run_cmd(
            ["python3", "scripts/ops/autonomy_scorecard.py", "--lookback-days", "30"]
        )
        if rc != 0:
            raise RuntimeError("Failed generating scorecard")
    if not SCORECARD_7D_PATH.exists():
        rc = run_cmd(
            [
                "python3",
                "scripts/ops/autonomy_scorecard.py",
                "--lookback-days",
                "7",
                "--output-json",
                str(SCORECARD_7D_PATH),
                "--output-md",
                str(FULL_PILOT_DIR / "scorecard-7d.md"),
            ]
        )
        if rc != 0:
            raise RuntimeError("Failed generating 7d scorecard")
    if not GO_NO_GO_PATH.exists():
        rc = run_cmd(["python3", "scripts/ops/generate_go_no_go_packet.py"])
        if rc != 0:
            raise RuntimeError("Failed generating go/no-go packet")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def pending_approvals_from_state() -> list[dict[str, Any]]:
    if not CADENCE_STATE_PATH.exists():
        return []
    try:
        state = load_json(CADENCE_STATE_PATH)
    except Exception:
        return []
    jobs = state.get("jobs", {})
    if not isinstance(jobs, dict):
        return []
    pending: list[dict[str, Any]] = []
    for job_id, payload in jobs.items():
        if not isinstance(payload, dict):
            continue
        msg = str(payload.get("last_error") or "")
        if "missing approval:" in msg:
            pending.append(
                {
                    "job_id": job_id,
                    "reason": msg,
                }
            )
    return pending


def operational_score_7d(
    scorecard_7d: dict[str, Any], pending_approvals: list[dict[str, Any]]
) -> int:
    cadence = scorecard_7d.get("cadence", {})
    alerts = scorecard_7d.get("alerts", {})
    success_rate = float(cadence.get("success_rate_percent", 0.0))
    total_alerts = int(alerts.get("total_alerts", 0))
    failed_runs = int(cadence.get("failed_runs", 0))
    score = (
        success_rate
        - (failed_runs * 5)
        - (total_alerts * 2)
        - (len(pending_approvals) * 3)
    )
    return max(0, min(100, int(round(score))))


def failure_trend(score_7d: dict[str, Any], score_30d: dict[str, Any]) -> str:
    fail_7 = int(score_7d.get("cadence", {}).get("failed_runs", 0))
    fail_30 = int(score_30d.get("cadence", {}).get("failed_runs", 0))
    if fail_7 < fail_30:
        return "improving"
    if fail_7 > fail_30:
        return "worsening"
    return "stable"


def parse_runs_24h() -> list[dict[str, Any]]:
    if not CADENCE_RUNS_PATH.exists():
        return []
    cutoff = datetime.now(UTC).timestamp() - 86400
    rows: list[dict[str, Any]] = []
    for line in CADENCE_RUNS_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        ts = item.get("timestamp_utc")
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00")).astimezone(UTC)
        except Exception:
            continue
        if dt.timestamp() >= cutoff:
            rows.append(item)
    return rows


def recovery_snapshot() -> dict[str, Any]:
    rows = parse_runs_24h()
    by_job: dict[str, list[str]] = {}
    for item in rows:
        jid = str(item.get("job_id", "")).strip()
        status = str(item.get("status", "")).strip().lower()
        if not jid:
            continue
        by_job.setdefault(jid, []).append(status)

    recovered: list[str] = []
    unresolved: list[str] = []
    for job_id, statuses in by_job.items():
        has_fail = any(s in {"failed", "timeout"} for s in statuses)
        has_success_after = False
        seen_fail = False
        for s in statuses:
            if s in {"failed", "timeout"}:
                seen_fail = True
            if s == "success" and seen_fail:
                has_success_after = True
        if has_fail and has_success_after:
            recovered.append(job_id)
        elif statuses and statuses[-1] in {"failed", "timeout"}:
            unresolved.append(job_id)

    return {
        "recovered_jobs_24h": sorted(set(recovered)),
        "unresolved_failed_jobs_24h": sorted(set(unresolved)),
    }


def autodispatch_snapshot() -> dict[str, int]:
    if not AUTODISPATCH_TASKS_PATH.exists():
        return {
            "queued_24h": 0,
            "dispatched_24h": 0,
            "dispatch_failed_24h": 0,
        }
    cutoff = datetime.now(UTC).timestamp() - 86400
    stats = {"queued_24h": 0, "dispatched_24h": 0, "dispatch_failed_24h": 0}
    for line in AUTODISPATCH_TASKS_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
            dt = datetime.fromisoformat(
                str(item.get("timestamp_utc", "")).replace("Z", "+00:00")
            ).astimezone(UTC)
        except Exception:
            continue
        if dt.timestamp() < cutoff:
            continue
        status = str(item.get("status", "")).lower()
        if status in {"queued"}:
            stats["queued_24h"] += 1
        elif status in {"dispatched"}:
            stats["dispatched_24h"] += 1
        elif status in {"dispatch_failed"}:
            stats["dispatch_failed_24h"] += 1
    return stats


def build_message(
    scorecard_30d: dict[str, Any], scorecard_7d: dict[str, Any], packet: dict[str, Any]
) -> str:
    cadence = scorecard_30d.get("cadence", {})
    alerts = scorecard_30d.get("alerts", {})
    cadence_7 = scorecard_7d.get("cadence", {})
    decision = packet.get("decision", "UNKNOWN")
    rationale = packet.get("rationale", "")
    pending_approvals = pending_approvals_from_state()
    op_score = operational_score_7d(scorecard_7d, pending_approvals)
    trend = failure_trend(scorecard_7d, scorecard_30d)
    recovery = recovery_snapshot()
    autod = autodispatch_snapshot()

    approval_lines = ["None"]
    if pending_approvals:
        approval_lines = [f"{p['job_id']}" for p in pending_approvals[:3]]

    return "\n".join(
        [
            "Full Pilot Daily Executive Summary",
            f"Generated: {now_iso()}",
            "",
            f"Decision: {decision}",
            f"Rationale: {rationale}",
            "",
            f"7-Day Operational Score: {op_score}/100",
            f"7-Day Success Rate: {cadence_7.get('success_rate_percent', 0)}%",
            f"Failure Trend (7d vs 30d): {trend}",
            "",
            f"Cadence Success Rate: {cadence.get('success_rate_percent', 0)}%",
            f"Successful Runs: {cadence.get('success_runs', 0)}",
            f"Failed Runs: {cadence.get('failed_runs', 0)}",
            f"Dry Runs: {cadence.get('dry_runs', 0)}",
            f"Total Alerts (30d): {alerts.get('total_alerts', 0)}",
            "",
            f"Auto-Dispatch (24h): queued={autod['queued_24h']} dispatched={autod['dispatched_24h']} failed={autod['dispatch_failed_24h']}",
            "",
            f"Fixes Applied (Recovered Jobs, 24h): {len(recovery['recovered_jobs_24h'])}",
            *(
                [f"- {x}" for x in recovery["recovered_jobs_24h"][:3]]
                if recovery["recovered_jobs_24h"]
                else ["- None"]
            ),
            f"Unresolved Failed Jobs (24h): {len(recovery['unresolved_failed_jobs_24h'])}",
            *(
                [f"- {x}" for x in recovery["unresolved_failed_jobs_24h"][:3]]
                if recovery["unresolved_failed_jobs_24h"]
                else ["- None"]
            ),
            "",
            "Pending Approvals:",
            *[f"- {line}" for line in approval_lines],
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
        "--regenerate",
        action="store_true",
        help="Regenerate scorecard and go/no-go first",
    )
    args = ap.parse_args()

    enabled_raw = (
        os.getenv("CHISE_FULL_PILOT_DAILY_SUMMARY_ENABLED", "true").strip().lower()
    )
    if enabled_raw not in {"1", "true", "yes", "on"}:
        print(
            "Daily full-pilot summary is disabled by CHISE_FULL_PILOT_DAILY_SUMMARY_ENABLED"
        )
        return 0

    if args.regenerate:
        if (
            run_cmd(
                [
                    "python3",
                    "scripts/ops/autonomy_scorecard.py",
                    "--lookback-days",
                    "30",
                ]
            )
            != 0
        ):
            return 1
        if (
            run_cmd(
                [
                    "python3",
                    "scripts/ops/autonomy_scorecard.py",
                    "--lookback-days",
                    "7",
                    "--output-json",
                    str(SCORECARD_7D_PATH),
                    "--output-md",
                    str(FULL_PILOT_DIR / "scorecard-7d.md"),
                ]
            )
            != 0
        ):
            return 1
        if run_cmd(["python3", "scripts/ops/generate_go_no_go_packet.py"]) != 0:
            return 1
    else:
        ensure_artifacts()

    scorecard = load_json(SCORECARD_PATH)
    scorecard_7d = load_json(SCORECARD_7D_PATH)
    packet = load_json(GO_NO_GO_PATH)
    message = build_message(scorecard, scorecard_7d, packet)

    if args.dry_run:
        print(message)
        return 0

    post_discord(message)
    print("Daily full-pilot summary posted to Discord")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
