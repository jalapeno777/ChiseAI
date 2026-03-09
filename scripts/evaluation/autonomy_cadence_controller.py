#!/usr/bin/env python3
"""Unified autonomy cadence controller (Phase 1 pilot).

Registry-driven scheduler that executes cadence jobs, persists durable state, and
emits alerts for missed cadence and potentially stuck jobs.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
# Load .env before reading runtime env vars (cron-safe).
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from config.bootstrap import bootstrap

bootstrap(load_env=True)

DEFAULT_REGISTRY = PROJECT_ROOT / "config" / "autonomy_job_registry.yaml"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "_bmad-output" / "autonomy-cadence"
STATE_PATH = DEFAULT_OUTPUT_DIR / "state.json"
RUN_LOG_PATH = DEFAULT_OUTPUT_DIR / "runs.jsonl"
ALERT_LOG_PATH = DEFAULT_OUTPUT_DIR / "alerts.jsonl"

logger = logging.getLogger("autonomy_cadence_controller")


def now_utc() -> datetime:
    return datetime.now(UTC)


def iso(dt: datetime | None = None) -> str:
    return (dt or now_utc()).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except Exception:
        return None


def cadence_seconds(cadence: str) -> int | None:
    normalized = cadence.strip().lower()
    table = {
        "6h": 6 * 3600,
        "daily": 24 * 3600,
        "weekly": 7 * 24 * 3600,
        "monthly": 30 * 24 * 3600,
        "event": None,
    }
    if normalized in table:
        return table[normalized]
    if normalized.endswith("h") and normalized[:-1].isdigit():
        return int(normalized[:-1]) * 3600
    return None


@dataclass
class Job:
    job_id: str
    enabled: bool
    cadence: str
    timeout_seconds: int
    risk_level: str
    command: list[str]
    required_flags: list[str]
    preconditions: list[str]
    required_approvals: list[str]
    idempotency_key: str | None
    retry_policy: dict[str, Any]


def load_registry(path: Path) -> tuple[dict[str, Any], list[Job]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid registry format in {path}")
    rows = raw.get("jobs", [])
    if not isinstance(rows, list):
        raise ValueError(f"Registry jobs must be a list in {path}")
    jobs: list[Job] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        cmd = row.get("command", [])
        if not isinstance(cmd, list) or not all(isinstance(x, str) for x in cmd):
            continue
        job_id = str(row.get("job_id", "")).strip()
        if not job_id:
            continue
        jobs.append(
            Job(
                job_id=job_id,
                enabled=bool(row.get("enabled", True)),
                cadence=str(row.get("cadence", "event")),
                timeout_seconds=int(row.get("timeout_seconds", 300)),
                risk_level=str(row.get("risk_level", "low")),
                command=cmd,
                required_flags=[
                    str(v).strip()
                    for v in row.get("required_flags", [])
                    if str(v).strip()
                ],
                preconditions=[
                    str(v).strip()
                    for v in row.get("preconditions", [])
                    if str(v).strip()
                ],
                required_approvals=[
                    str(v).strip()
                    for v in row.get("required_approvals", [])
                    if str(v).strip()
                ],
                idempotency_key=(
                    str(row.get("idempotency_key", "")).strip() or None
                ),
                retry_policy=(
                    row.get("retry_policy", {})
                    if isinstance(row.get("retry_policy", {}), dict)
                    else {}
                ),
            )
        )
    return raw, jobs


def ensure_output_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"jobs": {}, "version": 1}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("jobs", {})
            return data
    except Exception:
        pass
    return {"jobs": {}, "version": 1}


def save_state(path: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = iso()
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def discord_webhook_url() -> str | None:
    return (
        os.getenv("DISCORD_AUTONOMY_WEBHOOK_URL")
        or os.getenv("DISCORD_DEV_WEBHOOK_URL")
        or os.getenv("DISCORD_STANDUP_WEBHOOK")
        or os.getenv("DISCORD_WEBHOOK_URL")
        or os.getenv("CHISE_DISCORD_WEBHOOK_URL")
    )


def discord_enabled() -> bool:
    raw = os.getenv("CHISE_AUTONOMY_NOTIFY_DISCORD", "true").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def send_discord(content: str) -> bool:
    webhook = discord_webhook_url()
    if not webhook or not discord_enabled():
        return False
    payload = json.dumps({"content": content[:2000]}).encode("utf-8")
    req = urllib.request.Request(
        webhook,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "ChiseAI-Autonomy-Cadence/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status in (200, 204)
    except Exception as exc:
        logger.warning(f"Discord notification failed: {exc}")
        return False


def is_flag_enabled(flag_name: str) -> bool:
    env_name = f"CHISE_FLAG_{flag_name.upper().replace('-', '_')}"
    raw = (os.getenv(env_name) or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def evaluate_preconditions(job: Job) -> tuple[bool, str | None]:
    for cond in job.preconditions:
        if cond.startswith("env:"):
            expr = cond.replace("env:", "", 1)
            if "=" in expr:
                key, expected = expr.split("=", 1)
                if (os.getenv(key, "") or "").strip().lower() != expected.strip().lower():
                    return False, f"precondition failed: {cond}"
            else:
                if not os.getenv(expr.strip()):
                    return False, f"precondition failed: {cond}"
        elif cond.startswith("file_exists:"):
            p = Path(cond.replace("file_exists:", "", 1).strip())
            if not p.exists():
                return False, f"precondition failed: {cond}"
    return True, None


def approvals_granted(job: Job) -> tuple[bool, str | None]:
    for approval in job.required_approvals:
        env_name = f"CHISE_APPROVAL_{approval.upper().replace('-', '_')}"
        raw = (os.getenv(env_name, "") or "").strip().lower()
        if raw not in {"1", "true", "yes", "approved"}:
            return False, f"missing approval: {approval} ({env_name})"
    return True, None


def resolved_idempotency_key(template: str | None) -> str | None:
    if not template:
        return None
    now = now_utc()
    value = template
    value = value.replace("{date}", now.strftime("%Y-%m-%d"))
    value = value.replace("{week}", now.strftime("%G-W%V"))
    value = value.replace("{month}", now.strftime("%Y-%m"))
    return value


def should_run(job: Job, job_state: dict[str, Any], force: bool) -> bool:
    if not job.enabled:
        return False
    if force:
        return True
    interval = cadence_seconds(job.cadence)
    if interval is None:
        # event jobs run only when forced
        return False
    last_started = parse_iso(job_state.get("last_started_at"))
    if last_started is None:
        return True
    return (now_utc() - last_started).total_seconds() >= interval


def emit_alert(
    *,
    output_dir: Path,
    alert_type: str,
    job_id: str,
    severity: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> None:
    payload = {
        "timestamp_utc": iso(),
        "alert_type": alert_type,
        "job_id": job_id,
        "severity": severity,
        "message": message,
        "details": details or {},
    }
    append_jsonl(output_dir / "alerts.jsonl", payload)
    logger.warning(
        f"ALERT [{severity}] {alert_type} job={job_id} message={message} details={payload['details']}"
    )
    send_discord(
        "\n".join(
            [
                f"[AUTONOMY ALERT] {severity.upper()}",
                f"job={job_id}",
                f"type={alert_type}",
                f"message={message}",
            ]
        )
    )


def evaluate_alerts(
    *,
    jobs: list[Job],
    state: dict[str, Any],
    output_dir: Path,
    missed_factor: float,
) -> None:
    jobs_state = state.get("jobs", {})
    for job in jobs:
        js = jobs_state.get(job.job_id, {})
        interval = cadence_seconds(job.cadence)

        running_since = parse_iso(js.get("running_since"))
        if running_since is not None:
            age = (now_utc() - running_since).total_seconds()
            if age > job.timeout_seconds:
                emit_alert(
                    output_dir=output_dir,
                    alert_type="job_stuck",
                    job_id=job.job_id,
                    severity="critical",
                    message="Job appears stuck (running_since exceeds timeout_seconds)",
                    details={
                        "running_for_seconds": int(age),
                        "timeout_seconds": job.timeout_seconds,
                    },
                )

        if interval is None:
            continue
        last_success = parse_iso(js.get("last_success_at"))
        if last_success is None:
            continue
        age = (now_utc() - last_success).total_seconds()
        limit = interval * missed_factor
        if age > limit:
            emit_alert(
                output_dir=output_dir,
                alert_type="missed_cadence",
                job_id=job.job_id,
                severity="high",
                message="Job has exceeded expected cadence window",
                details={"age_seconds": int(age), "allowed_seconds": int(limit)},
            )


def run_job(job: Job, *, dry_run: bool, output_dir: Path, job_state: dict[str, Any]) -> int:
    for flag in job.required_flags:
        if not is_flag_enabled(flag):
            logger.info(f"Skipping {job.job_id}: required flag disabled ({flag})")
            return 0
    ok, reason = evaluate_preconditions(job)
    if not ok:
        logger.info(f"Skipping {job.job_id}: {reason}")
        return 0
    ok, reason = approvals_granted(job)
    if not ok:
        logger.info(f"Skipping {job.job_id}: {reason}")
        job_state["last_status"] = "awaiting_approval"
        job_state["last_error"] = reason
        approval_alert_key = f"{reason}|{resolved_idempotency_key(job.idempotency_key) or now_utc().strftime('%Y-%m-%d')}"
        if job_state.get("last_approval_alert_key") != approval_alert_key:
            emit_alert(
                output_dir=output_dir,
                alert_type="approval_required",
                job_id=job.job_id,
                severity="medium",
                message=reason or "Approval required",
                details={"required_approvals": job.required_approvals},
            )
            job_state["last_approval_alert_key"] = approval_alert_key
        return 0
    idem = resolved_idempotency_key(job.idempotency_key)
    if idem and job_state.get("last_idempotency_key") == idem and job_state.get("last_status") == "success":
        logger.info(f"Skipping {job.job_id}: idempotency key already succeeded ({idem})")
        return 0

    started_at = iso()
    job_state["last_started_at"] = started_at
    job_state["running_since"] = started_at

    if dry_run:
        logger.info(f"[DRY RUN] {job.job_id} -> {' '.join(job.command)}")
        append_jsonl(
            output_dir / "runs.jsonl",
            {
                "timestamp_utc": iso(),
                "job_id": job.job_id,
                "status": "dry_run",
                "command": job.command,
            },
        )
        job_state["last_status"] = "dry_run"
        if idem:
            job_state["last_idempotency_key"] = idem
        job_state.pop("running_since", None)
        return 0

    logger.info(f"Running {job.job_id}: {' '.join(job.command)}")
    started_ts = time.time()
    attempts = max(int(job.retry_policy.get("max_retries", 0)), 0) + 1
    backoff = max(int(job.retry_policy.get("backoff_seconds", 0)), 0)
    try:
        proc: subprocess.CompletedProcess[str] | None = None
        for attempt in range(1, attempts + 1):
            proc = subprocess.run(
                job.command,
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                timeout=job.timeout_seconds,
                check=False,
            )
            if proc.returncode == 0:
                break
            if attempt < attempts and backoff > 0:
                time.sleep(backoff)
        assert proc is not None
        duration = time.time() - started_ts
        ok = proc.returncode == 0
        status = "success" if ok else "failed"
        payload = {
            "timestamp_utc": iso(),
            "job_id": job.job_id,
            "status": status,
            "exit_code": proc.returncode,
            "duration_seconds": round(duration, 3),
            "stdout_tail": proc.stdout[-2000:],
            "stderr_tail": proc.stderr[-2000:],
            "command": job.command,
        }
        append_jsonl(output_dir / "runs.jsonl", payload)
        job_state["last_status"] = status
        job_state["last_duration_seconds"] = round(duration, 3)
        job_state["last_exit_code"] = proc.returncode
        job_state["last_error"] = proc.stderr[-500:] if not ok else None
        if ok:
            job_state["last_success_at"] = iso()
            if idem:
                job_state["last_idempotency_key"] = idem
        return 0 if ok else 1
    except subprocess.TimeoutExpired:
        duration = time.time() - started_ts
        append_jsonl(
            output_dir / "runs.jsonl",
            {
                "timestamp_utc": iso(),
                "job_id": job.job_id,
                "status": "timeout",
                "duration_seconds": round(duration, 3),
                "command": job.command,
                "timeout_seconds": job.timeout_seconds,
            },
        )
        emit_alert(
            output_dir=output_dir,
            alert_type="job_timeout",
            job_id=job.job_id,
            severity="critical",
            message="Job execution timed out",
            details={"timeout_seconds": job.timeout_seconds},
        )
        job_state["last_status"] = "timeout"
        job_state["last_error"] = "timeout"
        return 1
    finally:
        job_state.pop("running_since", None)
        job_state["updated_at"] = iso()


def tick(
    *,
    jobs: list[Job],
    state: dict[str, Any],
    output_dir: Path,
    dry_run: bool,
    force: bool,
    job_filter: set[str] | None,
    max_jobs: int,
) -> int:
    jobs_state = state.setdefault("jobs", {})
    eligible = [j for j in jobs if job_filter is None or j.job_id in job_filter]

    ran = 0
    failures = 0
    for job in eligible:
        js = jobs_state.setdefault(job.job_id, {})
        if not should_run(job, js, force=force):
            continue
        rc = run_job(job, dry_run=dry_run, output_dir=output_dir, job_state=js)
        ran += 1
        if rc != 0:
            failures += 1
        if max_jobs > 0 and ran >= max_jobs:
            break

    logger.info(f"Tick complete: ran={ran}, failures={failures}, eligible={len(eligible)}")
    if ran > 0 or failures > 0:
        send_discord(
            "\n".join(
                [
                    "[AUTONOMY TICK]",
                    f"ran={ran}",
                    f"failures={failures}",
                    f"eligible={len(eligible)}",
                    f"dry_run={str(dry_run).lower()}",
                    f"time={iso()}",
                ]
            )
        )
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Unified autonomy cadence controller")
    parser.add_argument(
        "--registry",
        type=Path,
        default=DEFAULT_REGISTRY,
        help="Path to registry yaml (default: config/autonomy_job_registry.yaml)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Output dir for state/run/alert logs",
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not execute jobs")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force eligible jobs regardless of cadence interval",
    )
    parser.add_argument(
        "--job-id",
        action="append",
        help="Limit execution to one or more specific job_ids",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run continuous scheduler loop",
    )
    parser.add_argument(
        "--tick-seconds",
        type=int,
        help="Override scheduler tick interval in daemon mode",
    )
    parser.add_argument(
        "--max-jobs-per-tick",
        type=int,
        default=0,
        help="Optional cap per tick (0 means unlimited)",
    )
    parser.add_argument(
        "--missed-cadence-factor",
        type=float,
        default=1.5,
        help="Alert when job last success age exceeds cadence*factor",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate registry and exit",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    if not args.registry.exists():
        logger.error(f"Registry not found: {args.registry}")
        return 1

    registry_raw, jobs = load_registry(args.registry)
    if not jobs:
        logger.error("No valid jobs in registry")
        return 1

    if args.validate_only:
        print(
            json.dumps(
                {
                    "registry": str(args.registry),
                    "job_count": len(jobs),
                    "jobs": [j.job_id for j in jobs],
                },
                indent=2,
            )
        )
        return 0

    ensure_output_dir(args.output_dir)
    state_path = args.output_dir / STATE_PATH.name
    state = load_state(state_path)
    job_filter = set(args.job_id) if args.job_id else None
    missed_factor = args.missed_cadence_factor
    tick_seconds = args.tick_seconds or int(registry_raw.get("default_tick_seconds", 60))

    if not args.daemon:
        rc = tick(
            jobs=jobs,
            state=state,
            output_dir=args.output_dir,
            dry_run=args.dry_run,
            force=args.force,
            job_filter=job_filter,
            max_jobs=args.max_jobs_per_tick,
        )
        evaluate_alerts(
            jobs=jobs,
            state=state,
            output_dir=args.output_dir,
            missed_factor=missed_factor,
        )
        save_state(state_path, state)
        return rc

    logger.info("Starting autonomy cadence controller daemon")
    while True:
        rc = tick(
            jobs=jobs,
            state=state,
            output_dir=args.output_dir,
            dry_run=args.dry_run,
            force=False,
            job_filter=job_filter,
            max_jobs=args.max_jobs_per_tick,
        )
        evaluate_alerts(
            jobs=jobs,
            state=state,
            output_dir=args.output_dir,
            missed_factor=missed_factor,
        )
        save_state(state_path, state)
        if rc != 0:
            logger.warning("Tick completed with job failures")
        time.sleep(max(tick_seconds, 1))


if __name__ == "__main__":
    raise SystemExit(main())
