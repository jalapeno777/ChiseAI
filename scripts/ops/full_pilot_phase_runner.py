#!/usr/bin/env python3
"""Run Full Pilot phases 2/3/4 with event emission and guardrails."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from config.bootstrap import bootstrap

bootstrap(load_env=True)

from scripts.ops.autonomy_event_bus import build_event, publish_event

OUTPUT_DIR = Path("_bmad-output/full-pilot")


@dataclass
class StepResult:
    name: str
    command: list[str]
    exit_code: int
    stdout_tail: str
    stderr_tail: str


def run_step(name: str, command: list[str], *, dry_run: bool) -> StepResult:
    if dry_run:
        return StepResult(
            name=name,
            command=command,
            exit_code=0,
            stdout_tail="[dry-run]",
            stderr_tail="",
        )
    proc = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=1800,
        check=False,
    )
    return StepResult(
        name=name,
        command=command,
        exit_code=proc.returncode,
        stdout_tail=proc.stdout[-2000:],
        stderr_tail=proc.stderr[-2000:],
    )


def phase2(*, dry_run: bool) -> list[StepResult]:
    steps = [
        ("reflection_daily", ["python3", "scripts/standup/generate_daily_reflection_report.py"]),
        ("metacog_weekly_check", ["python3", "scripts/validation/validate_metacog_compliance.py", "--require-for-completed-only"]),
        ("skills_weekly_tick", ["python3", "scripts/ops/skill_autonomy_tick.py", "--mode=weekly"]),
        ("skills_backlog_ingest", ["python3", "scripts/ops/ingest_skill_backlog_candidates.py", "--max-items=25"]),
    ]
    results = [run_step(name, cmd, dry_run=dry_run) for name, cmd in steps]
    all_ok = all(r.exit_code == 0 for r in results)
    publish_event(
        build_event(
            event_type="reflection.generated",
            producer="full_pilot_phase_runner",
            severity="info" if all_ok else "high",
            payload={
                "phase": "phase2",
                "ok": all_ok,
                "steps": [r.__dict__ for r in results],
            },
        ),
        output_dir=OUTPUT_DIR,
    )
    if all_ok:
        publish_event(
            build_event(
                event_type="metacog.closed",
                producer="full_pilot_phase_runner",
                severity="info",
                payload={"phase": "phase2", "status": "validated"},
            ),
            output_dir=OUTPUT_DIR,
        )
    return results


def phase3(*, dry_run: bool) -> list[StepResult]:
    autopilot_enabled = (
        os.getenv("CHISE_STRATEGY_AUTOPILOT_ENABLED", "false").strip().lower()
        in {"1", "true", "yes", "on"}
    )
    autopromote_enabled = (
        os.getenv("CHISE_AUTOPROMOTE_LOW_RISK", "false").strip().lower()
        in {"1", "true", "yes", "on"}
    )

    steps: list[tuple[str, list[str]]] = [
        ("canary_status", ["python3", "scripts/canary_auto_eval.py", "status"]),
    ]
    if autopilot_enabled:
        steps.append(("canary_eval_run", ["python3", "scripts/canary_auto_eval.py", "run"]))
    if autopromote_enabled:
        steps.append(("promotion_candidate_triage", ["python3", "scripts/canary_auto_eval.py", "run"]))

    results = [run_step(name, cmd, dry_run=dry_run) for name, cmd in steps]
    all_ok = all(r.exit_code == 0 for r in results)

    publish_event(
        build_event(
            event_type="promotion.candidate.ready",
            producer="full_pilot_phase_runner",
            severity="info" if all_ok else "high",
            payload={
                "phase": "phase3",
                "ok": all_ok,
                "autopilot_enabled": autopilot_enabled,
                "autopromote_low_risk": autopromote_enabled,
                "steps": [r.__dict__ for r in results],
            },
        ),
        output_dir=OUTPUT_DIR,
    )
    if not autopilot_enabled:
        publish_event(
            build_event(
                event_type="promotion.rejected",
                producer="full_pilot_phase_runner",
                severity="info",
                payload={"reason": "autopilot disabled by policy flag"},
            ),
            output_dir=OUTPUT_DIR,
        )
    return results


def phase4(*, dry_run: bool) -> list[StepResult]:
    steps = [
        ("autonomy_scorecard", ["python3", "scripts/ops/autonomy_scorecard.py", "--lookback-days", "30"]),
        ("go_no_go_packet", ["python3", "scripts/ops/generate_go_no_go_packet.py"]),
    ]
    results = [run_step(name, cmd, dry_run=dry_run) for name, cmd in steps]
    ok = all(r.exit_code == 0 for r in results)
    publish_event(
        build_event(
            event_type="experiment.candidate.created",
            producer="full_pilot_phase_runner",
            severity="info" if ok else "high",
            payload={
                "phase": "phase4",
                "ok": ok,
                "steps": [r.__dict__ for r in results],
            },
        ),
        output_dir=OUTPUT_DIR,
    )
    return results


def summarize(label: str, results: list[StepResult]) -> tuple[bool, dict[str, Any]]:
    ok = all(r.exit_code == 0 for r in results)
    return ok, {
        "label": label,
        "ok": ok,
        "steps": [r.__dict__ for r in results],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Run full pilot phase loops")
    ap.add_argument(
        "--phase",
        choices=["phase2", "phase3", "phase4", "all"],
        default="all",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    summaries: list[dict[str, Any]] = []
    if args.phase in {"phase2", "all"}:
        ok, summary = summarize("phase2", phase2(dry_run=args.dry_run))
        summaries.append(summary)
        if not ok and args.phase != "all":
            print(json.dumps({"ok": False, "summary": summaries}, indent=2))
            return 1
    if args.phase in {"phase3", "all"}:
        ok, summary = summarize("phase3", phase3(dry_run=args.dry_run))
        summaries.append(summary)
        if not ok and args.phase != "all":
            print(json.dumps({"ok": False, "summary": summaries}, indent=2))
            return 1
    if args.phase in {"phase4", "all"}:
        ok, summary = summarize("phase4", phase4(dry_run=args.dry_run))
        summaries.append(summary)
        if not ok and args.phase != "all":
            print(json.dumps({"ok": False, "summary": summaries}, indent=2))
            return 1

    overall = all(s["ok"] for s in summaries)
    print(json.dumps({"ok": overall, "summary": summaries}, indent=2))
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
