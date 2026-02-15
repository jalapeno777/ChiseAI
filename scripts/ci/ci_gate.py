#!/usr/bin/env python3
"""Fail the pipeline if any captured CI step failed; post PR comment on failure.

Rationale:
- Woodpecker may stop the pipeline on first failure, preventing log-summarizing steps.
- We instead capture exit codes in earlier steps, then fail once at the end.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

CI_DIR = Path("_bmad-output/ci")
FAST_REQUIRED = [
    "swarm-context.status",
    "lint.status",
    "security-scan.status",
]
FULL_REQUIRED = [
    "local-ci.status",
    "brain-eval.status",
]


def _read_status(path: Path) -> int:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except Exception:  # noqa: BLE001
        return 99


def _is_pr_build(env: dict[str, str]) -> bool:
    # Woodpecker sets CI_COMMIT_PULL_REQUEST on PR builds.
    return bool(env.get("CI_COMMIT_PULL_REQUEST", "").strip()) or bool(
        env.get("CI_PULL_REQUEST", "").strip()
    )


def _is_main_push(env: dict[str, str]) -> bool:
    event = (
        env.get("CI_BUILD_EVENT", "")
        or env.get("WOODPECKER_BUILD_EVENT", "")
        or env.get("WOODPECKER_EVENT", "")
        or env.get("CI_PIPELINE_EVENT", "")
    ).strip().lower()
    branch = (
        env.get("CI_COMMIT_BRANCH", "") or env.get("WOODPECKER_COMMIT_BRANCH", "")
    ).strip()
    return event == "push" and branch == "main"


def main() -> int:
    env = dict(os.environ)
    CI_DIR.mkdir(parents=True, exist_ok=True)
    required_files = [CI_DIR / name for name in FAST_REQUIRED]
    if _is_main_push(env) or env.get("FORCE_FULL_GATE", "").strip() == "1":
        required_files.extend(CI_DIR / name for name in FULL_REQUIRED)

    # Debug: print current directory and list CI_DIR contents
    print(f"ci-gate: Running in {os.getcwd()}")
    print(f"ci-gate: CI_DIR is {CI_DIR.absolute()}")
    if CI_DIR.exists():
        print(f"ci-gate: CI_DIR contents: {list(CI_DIR.iterdir())}")
    else:
        print("ci-gate: CI_DIR does not exist")

    missing = [p for p in required_files if not p.exists()]
    statuses = {p.name: (_read_status(p) if p.exists() else 99) for p in required_files}

    print(f"ci-gate: Statuses read: {statuses}")

    failing = {k: v for k, v in statuses.items() if v != 0}
    if missing:
        print("ci-gate: missing status files:", file=sys.stderr)
        for p in missing:
            print(f"  - {p}", file=sys.stderr)
        failing.update({p.name: 99 for p in missing})

    if not failing:
        print("ci-gate: OK (all captured steps passed)")
        return 0

    print("ci-gate: FAIL (captured step failures detected)", file=sys.stderr)
    for k, v in failing.items():
        print(f"  - {k}: {v}", file=sys.stderr)

    # Print a concise summary to the build logs (root-cause-first, then fallback).
    triage_script = Path("scripts/ci/woodpecker_triage.py")
    if triage_script.exists():
        subprocess.run(
            [
                sys.executable,
                str(triage_script),
                "diagnose",
                "--from-local-dir",
                str(CI_DIR),
                "--write-artifacts",
            ],
            check=False,
        )
    else:
        scan_script = Path("scripts/ci/scan_failure_logs.py")
        if scan_script.exists():
            subprocess.run([sys.executable, str(scan_script)], check=False)

    # Best-effort PR comment for swarm visibility.
    if _is_pr_build(env) and env.get("GITEA_TOKEN", "").strip():
        comment_script = Path("scripts/ci/post_ci_failure_pr_comment.py")
        if comment_script.exists():
            subprocess.run([sys.executable, str(comment_script)], check=False)
    else:
        if _is_pr_build(env):
            print(
                "ci-gate: PR build but GITEA_TOKEN is not set; cannot post PR comment.",
                file=sys.stderr,
            )

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
