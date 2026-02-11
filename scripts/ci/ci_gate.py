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
REQUIRED_STATUS_FILES = [
    CI_DIR / "lint.status",
    CI_DIR / "security-scan.status",
    CI_DIR / "local-ci.status",
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


def main() -> int:
    env = dict(os.environ)
    CI_DIR.mkdir(parents=True, exist_ok=True)

    missing = [p for p in REQUIRED_STATUS_FILES if not p.exists()]
    statuses = {
        p.name: (_read_status(p) if p.exists() else 99) for p in REQUIRED_STATUS_FILES
    }

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

    # Print a concise summary to the build logs.
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
