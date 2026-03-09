#!/usr/bin/env python3
"""Full pilot end-to-end validation script."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def run(cmd: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        timeout=3600,
        check=False,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"Command failed ({proc.returncode}): {' '.join(cmd)}\n{proc.stdout}\n{proc.stderr}"
        )
    return proc


def assert_exists(path: Path) -> None:
    if not path.exists():
        raise RuntimeError(f"Required artifact missing: {path}")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Full pilot E2E validation")
    ap.add_argument("--skip-live-ops", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    checks: list[dict[str, Any]] = []

    def record(name: str, proc: subprocess.CompletedProcess[str]) -> None:
        checks.append(
            {
                "name": name,
                "rc": proc.returncode,
                "stdout_tail": proc.stdout[-1000:],
                "stderr_tail": proc.stderr[-1000:],
            }
        )
        if args.verbose:
            print(f"[{name}] rc={proc.returncode}")
            if proc.stdout.strip():
                print(proc.stdout.strip())
            if proc.stderr.strip():
                print(proc.stderr.strip())

    # 1) Validate cadence registry and do a forced dry-run.
    p = run(
        [
            "python3",
            "scripts/evaluation/autonomy_cadence_controller.py",
            "--validate-only",
        ]
    )
    record("cadence_validate", p)
    if p.returncode != 0:
        return 1

    p = run(
        [
            "python3",
            "scripts/evaluation/autonomy_cadence_controller.py",
            "--dry-run",
            "--force",
        ]
    )
    record("cadence_dry_force", p)
    if p.returncode != 0:
        return 1

    # 2) Full pilot phase runner dry-run and live run.
    p = run(["python3", "scripts/ops/full_pilot_phase_runner.py", "--phase", "all", "--dry-run"])
    record("pilot_all_dry", p)
    if p.returncode != 0:
        return 1

    if args.skip_live_ops:
        p = run(["python3", "scripts/ops/full_pilot_phase_runner.py", "--phase", "phase4"])
        record("pilot_phase4_live", p)
    else:
        p = run(["python3", "scripts/ops/full_pilot_phase_runner.py", "--phase", "all"])
        record("pilot_all_live", p)
    if p.returncode != 0:
        return 1

    # 3) Verify key artifacts.
    assert_exists(PROJECT_ROOT / "_bmad-output" / "autonomy-cadence" / "state.json")
    assert_exists(PROJECT_ROOT / "_bmad-output" / "autonomy-cadence" / "runs.jsonl")
    assert_exists(PROJECT_ROOT / "_bmad-output" / "full-pilot" / "events.jsonl")
    assert_exists(PROJECT_ROOT / "_bmad-output" / "full-pilot" / "scorecard.json")
    assert_exists(PROJECT_ROOT / "_bmad-output" / "full-pilot" / "scorecard.md")

    scorecard = load_json(PROJECT_ROOT / "_bmad-output" / "full-pilot" / "scorecard.json")
    if "cadence" not in scorecard or "events" not in scorecard:
        raise RuntimeError("Scorecard schema missing required sections")

    # 4) Verify command docs exist for operational usage.
    assert_exists(PROJECT_ROOT / ".opencode" / "command" / "chise-autonomy-cadence-tick.md")
    assert_exists(PROJECT_ROOT / ".opencode" / "command" / "chise-full-pilot-run.md")
    assert_exists(PROJECT_ROOT / ".opencode" / "command" / "chise-full-pilot-e2e.md")

    print(
        json.dumps(
            {
                "ok": True,
                "checks": checks,
                "artifacts_verified": True,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
