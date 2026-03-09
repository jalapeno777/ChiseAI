#!/usr/bin/env python3
"""Auto-dispatch policy-safe cadence issues to Opencode Aria tasks."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = PROJECT_ROOT / "_bmad-output" / "autonomy-dispatch"
ALERTS_PATH = PROJECT_ROOT / "_bmad-output" / "autonomy-cadence" / "alerts.jsonl"
STATE_PATH = STATE_DIR / "state.json"
TASKS_PATH = STATE_DIR / "tasks.jsonl"
PROMPTS_DIR = STATE_DIR / "prompts"


def now() -> datetime:
    return datetime.now(UTC)


def iso(dt: datetime | None = None) -> str:
    return (dt or now()).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso(v: str | None) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00")).astimezone(UTC)
    except Exception:
        return None


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, sort_keys=True) + "\n")


def read_alerts() -> list[dict[str, Any]]:
    if not ALERTS_PATH.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in ALERTS_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict):
            out.append(item)
    return out


def is_approval_granted_for_job(job_id: str) -> bool:
    # Current guarded job in registry
    if job_id == "pilot.phase3_weekly":
        raw = os.getenv("CHISE_APPROVAL_STRATEGY_AUTOPILOT", "").strip().lower()
        return raw in {"1", "true", "yes", "approved"}
    return True


def severity_rank(sev: str) -> int:
    return {"info": 1, "low": 2, "medium": 3, "high": 4, "critical": 5}.get(
        sev.lower(), 3
    )


def eligible(alert: dict[str, Any]) -> tuple[bool, str]:
    typ = str(alert.get("alert_type", "")).strip().lower()
    sev = str(alert.get("severity", "medium")).strip().lower()
    job = str(alert.get("job_id", "")).strip()

    if typ in {"job_recovered"}:
        return False, "recovered-no-action"
    if typ == "approval_required":
        return False, "awaiting-human-approval"
    if severity_rank(sev) >= 5:
        return False, "critical-requires-human"
    if job and not is_approval_granted_for_job(job):
        return False, "approval-not-granted"
    return True, "auto-dispatch-eligible"


def dispatch_key(alert: dict[str, Any]) -> str:
    basis = json.dumps(
        {
            "alert_type": alert.get("alert_type"),
            "job_id": alert.get("job_id"),
            "message": alert.get("message"),
            "details": alert.get("details"),
        },
        sort_keys=True,
    )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def render_prompt(alert: dict[str, Any], task_id: str) -> str:
    return "\n".join(
        [
            "You are Aria. Handle this autonomy alert with safe remediation.",
            f"Task ID: {task_id}",
            f"Timestamp: {iso()}",
            "",
            "Alert Context:",
            json.dumps(alert, indent=2, sort_keys=True),
            "",
            "Required behavior:",
            "1. Diagnose root cause using repository evidence only.",
            "2. Apply low-risk fix if safe and testable.",
            "3. If fix is risky or unclear, produce an explicit remediation plan and stop.",
            "4. Emit concise outcome notes and commands run.",
            "",
            "Safety:",
            "- Do not touch trading risk caps or promotion gates without explicit approval.",
            "- Respect existing governance/validation commands.",
        ]
    )


def run_opencode(prompt_file: Path, task_id: str) -> tuple[str, str]:
    enabled = os.getenv("CHISE_OPENCODE_AUTODISPATCH_ENABLED", "false").strip().lower()
    if enabled not in {"1", "true", "yes", "on"}:
        return "queued", "autodispatch-disabled"

    template = os.getenv(
        "CHISE_OPENCODE_AUTODISPATCH_CMD",
        "opencode run --agent Aria --prompt-file {prompt_file}",
    )
    cmd_str = template.format(prompt_file=str(prompt_file), task_id=task_id)
    cmd = shlex.split(cmd_str)
    try:
        proc = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=1800,
            check=False,
        )
        if proc.returncode == 0:
            return "dispatched", "ok"
        return "dispatch_failed", f"rc={proc.returncode} stderr={proc.stderr[-300:]}"
    except Exception as exc:
        return "dispatch_failed", f"exception={exc}"


@dataclass
class Settings:
    max_concurrent: int
    retry_budget: int
    dedupe_hours: int


def load_settings() -> Settings:
    return Settings(
        max_concurrent=int(os.getenv("CHISE_AUTODISPATCH_MAX_CONCURRENT", "2")),
        retry_budget=int(os.getenv("CHISE_AUTODISPATCH_RETRY_BUDGET", "2")),
        dedupe_hours=int(os.getenv("CHISE_AUTODISPATCH_DEDUPE_HOURS", "24")),
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Auto-dispatch cadence alerts to Opencode")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-items", type=int, default=20)
    args = ap.parse_args()

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    PROMPTS_DIR.mkdir(parents=True, exist_ok=True)

    settings = load_settings()
    state = load_json(
        STATE_PATH,
        {"tasks": {}, "active": []},
    )
    if not isinstance(state, dict):
        state = {"tasks": {}, "active": []}
    if not isinstance(state.get("tasks"), dict):
        state["tasks"] = {}
    if not isinstance(state.get("active"), list):
        state["active"] = []

    # Trim stale active entries.
    state["active"] = [
        x
        for x in state["active"]
        if isinstance(x, str) and state["tasks"].get(x, {}).get("status") in {"queued", "dispatched"}
    ][: settings.max_concurrent]

    alerts = read_alerts()[-500:]
    dispatched = 0
    skipped = 0
    for alert in alerts:
        if dispatched >= args.max_items:
            break
        if len(state["active"]) >= settings.max_concurrent:
            break

        ok, reason = eligible(alert)
        if not ok:
            skipped += 1
            continue

        key = dispatch_key(alert)
        existing = state["tasks"].get(key, {})
        last_at = parse_iso(existing.get("last_seen_at"))
        if last_at and (now() - last_at) < timedelta(hours=settings.dedupe_hours):
            skipped += 1
            continue
        attempts = int(existing.get("attempts", 0))
        if attempts >= settings.retry_budget:
            skipped += 1
            continue

        task_id = f"autod-{key[:10]}"
        prompt_path = PROMPTS_DIR / f"{task_id}.md"
        prompt_path.write_text(render_prompt(alert, task_id), encoding="utf-8")

        status, detail = ("queued", "dry-run")
        if not args.dry_run:
            status, detail = run_opencode(prompt_path, task_id)

        record = {
            "task_id": task_id,
            "dispatch_key": key,
            "status": status,
            "detail": detail,
            "attempts": attempts + 1,
            "last_seen_at": iso(),
            "job_id": alert.get("job_id"),
            "alert_type": alert.get("alert_type"),
            "severity": alert.get("severity"),
            "prompt_file": str(prompt_path),
        }
        state["tasks"][key] = record
        if status in {"queued", "dispatched"} and task_id not in state["active"]:
            state["active"].append(task_id)

        append_jsonl(
            TASKS_PATH,
            {
                "timestamp_utc": iso(),
                **record,
            },
        )
        dispatched += 1

    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "dispatched_or_queued": dispatched,
                "skipped": skipped,
                "active_count": len(state["active"]),
                "settings": settings.__dict__,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
