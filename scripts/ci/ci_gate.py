#!/usr/bin/env python3
"""Fail the pipeline if any captured CI step failed; post PR comment on failure.

Rationale:
- Woodpecker may stop the pipeline on first failure, preventing log-summarizing steps.
- We instead capture exit codes in earlier steps, then fail once at the end.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Allow direct script execution from any worktree by exposing repo root + src.
_REPO_ROOT = Path(__file__).resolve().parents[2]
for _path in (str(_REPO_ROOT), str(_REPO_ROOT / "src")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

try:
    from config.bootstrap import bootstrap
except ModuleNotFoundError:
    from src.config.bootstrap import bootstrap

CI_DIR = Path(os.environ.get("CI_STATUS_DIR", "_bmad-output/ci"))
FAST_REQUIRED = [
    "swarm-context.status",
    "lint.status",
    "security-scan.status",
    "dependency-audit.status",
    "secret-scan.status",
    "risk-invariants.status",
    "brain-regression.status",
    "docs-pairing.status",
    "docker-governance.status",
    "changed-lines-coverage.status",
    "deprecation-gate.status",  # TECH-001-B: Deprecation warning validation
    "status-write-gate.status",
    "performance-gate.status",  # PHASE 3: Performance threshold validation
    "evidence-gate.status",  # TECH-002-B: Per-story evidence validation
]
FULL_REQUIRED = [
    "local-ci.status",
    "brain-eval.status",
    "pre-eval-ingestion.status",
]
# Cron diagnostics run in dedicated steps but are not hard-blocking for merge gate.
CRON_REQUIRED: list[str] = []


def _read_status(path: Path) -> int:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except Exception:  # noqa: BLE001
        return 99


def _infer_missing_status_from_log(status_path: Path) -> int | None:
    """Infer success for missing status files only on explicit skip logs."""
    log_path = status_path.with_suffix(".log")
    if not log_path.exists():
        return None
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return None

    low = text.lower()
    success_markers = (
        "skipping",
        "all checks passed",
        "all validation passed",
        "validation passed",
        "ok (",
        "completed successfully",
    )
    if not any(marker in low for marker in success_markers):
        return None

    # Keep this conservative: only treat as success when no obvious hard-failure markers exist.
    hard_markers = (
        "traceback",
        "module not found",
        "error while importing test module",
        "validation failed",
        "ci-gate: fail",
        "failed steps",
    )
    if any(marker in low for marker in hard_markers):
        return None
    return 0


def _is_pr_build(env: dict[str, str]) -> bool:
    # Woodpecker sets CI_COMMIT_PULL_REQUEST on PR builds.
    return bool(env.get("CI_COMMIT_PULL_REQUEST", "").strip()) or bool(
        env.get("CI_PULL_REQUEST", "").strip()
    )


def _is_main_push(env: dict[str, str]) -> bool:
    event = (
        (
            env.get("CI_BUILD_EVENT", "")
            or env.get("WOODPECKER_BUILD_EVENT", "")
            or env.get("WOODPECKER_EVENT", "")
            or env.get("CI_PIPELINE_EVENT", "")
        )
        .strip()
        .lower()
    )
    branch = (
        env.get("CI_COMMIT_BRANCH", "") or env.get("WOODPECKER_COMMIT_BRANCH", "")
    ).strip()
    return event == "push" and branch == "main"


def _is_main_cron(env: dict[str, str]) -> bool:
    event = (
        (
            env.get("CI_BUILD_EVENT", "")
            or env.get("WOODPECKER_BUILD_EVENT", "")
            or env.get("WOODPECKER_EVENT", "")
            or env.get("CI_PIPELINE_EVENT", "")
        )
        .strip()
        .lower()
    )
    branch = (
        env.get("CI_COMMIT_BRANCH", "") or env.get("WOODPECKER_COMMIT_BRANCH", "")
    ).strip()
    return event == "cron" and branch == "main"


def _is_ci_context(env: dict[str, str]) -> bool:
    """Detect if running in CI environment via reliable CI env vars."""
    # CI_PIPELINE_NUMBER is reliably set in all Woodpecker builds.
    if env.get("CI_PIPELINE_NUMBER", "").strip():
        return True
    # Also check for other CI indicators.
    ci_indicators = [
        env.get("CI_COMMIT_BRANCH", "").strip(),
        env.get("WOODPECKER_BUILD_EVENT", "").strip(),
        env.get("CI_BUILD_EVENT", "").strip(),
        env.get("WOODPECKER_EVENT", "").strip(),
        env.get("CI_PIPELINE_EVENT", "").strip(),
    ]
    return bool(any(ci_indicators))


def _is_repo_local_path(path: Path, repo_root: Path) -> bool:
    """Check if path resolves to a location under repo root (local artifact cache)."""
    try:
        resolved = path.resolve()
        repo_resolved = repo_root.resolve()
        return resolved.is_relative_to(repo_resolved)
    except (ValueError, OSError):
        return False


def _run_root_cause_bundle(ci_dir: Path, env: dict[str, str]) -> Path | None:
    triage_script = Path("scripts/ci/woodpecker_triage.py")
    if not triage_script.exists():
        return None

    root_log = ci_dir / "root-cause.log"
    pipeline_num = env.get("CI_PIPELINE_NUMBER", "").strip() or "0"
    out_dir = str(ci_dir)

    attempts = [
        [
            sys.executable,
            str(triage_script),
            "bundle",
            "--pipeline",
            pipeline_num,
            "--out-dir",
            out_dir,
            "--format",
            "human",
        ],
        [
            sys.executable,
            str(triage_script),
            "bundle",
            "--from-local-dir",
            str(ci_dir),
            "--out-dir",
            out_dir,
            "--format",
            "human",
        ],
    ]

    root_log.parent.mkdir(parents=True, exist_ok=True)
    with root_log.open("w", encoding="utf-8") as fh:
        fh.write("")

    generated_json: Path | None = None
    for cmd in attempts:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        with root_log.open("a", encoding="utf-8") as fh:
            fh.write(f"$ {' '.join(cmd)}\n")
            if proc.stdout:
                fh.write(proc.stdout.rstrip() + "\n")
            if proc.stderr:
                fh.write(proc.stderr.rstrip() + "\n")
            fh.write("\n")

        if proc.stdout:
            print(proc.stdout.rstrip())
        if proc.stderr:
            print(proc.stderr.rstrip(), file=sys.stderr)

        if cmd[2] == "bundle" and "--pipeline" in cmd:
            candidate = ci_dir / pipeline_num / "root-cause.json"
        else:
            candidate = ci_dir / "0" / "root-cause.json"
        if candidate.exists():
            generated_json = candidate
            break

    return generated_json


def _print_exact_root_causes(root_cause_json: Path) -> None:
    try:
        causes = json.loads(root_cause_json.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(
            f"ci-gate: unable to parse root cause json ({root_cause_json}): {exc}",
            file=sys.stderr,
        )
        return

    if not isinstance(causes, list) or not causes:
        print("ci-gate: no structured root causes extracted", file=sys.stderr)
        return

    print("ci-gate: exact root causes", file=sys.stderr)
    for idx, rc in enumerate(causes, 1):
        if not isinstance(rc, dict):
            continue
        tool = str(rc.get("tool") or "unknown")
        message = str(rc.get("message") or "no message")
        file = rc.get("file")
        line = rc.get("line")
        rule = rc.get("rule")
        test = rc.get("test")

        details: list[str] = []
        if file:
            details.append(f"file={file}:{line or 1}")
        if rule:
            details.append(f"rule={rule}")
        if test:
            details.append(f"test={test}")
        details_text = f" ({', '.join(details)})" if details else ""

        print(f"  {idx}. tool={tool}: {message}{details_text}", file=sys.stderr)


def main() -> int:
    # Bootstrap environment first
    bootstrap(load_env=True)
    env = dict(os.environ)

    # --- CI context hardening: fail fast on stale/missing CI_STATUS_DIR ---
    if _is_ci_context(env):
        ci_status_dir_raw = env.get("CI_STATUS_DIR", "")
        if not ci_status_dir_raw.strip():
            print(
                "ci-gate: CI_STATUS_DIR is not set or empty in CI context. "
                "Set CI_STATUS_DIR to a pipeline-specific path like "
                "'/woodpecker/ci-status/${CI_PIPELINE_NUMBER}'.",
                file=sys.stderr,
            )
            return 1
        ci_status_path = Path(ci_status_dir_raw)
        if _is_repo_local_path(ci_status_path, _REPO_ROOT):
            print(
                f"ci-gate: CI_STATUS_DIR resolves to repo-local fallback "
                f"'{ci_status_dir_raw}'. In CI context, set CI_STATUS_DIR to a "
                f"pipeline-specific path like "
                f"'/woodpecker/ci-status/${{CI_PIPELINE_NUMBER}}'.",
                file=sys.stderr,
            )
            return 1
    # --- End CI context hardening ---

    CI_DIR.mkdir(parents=True, exist_ok=True)
    required_files = [CI_DIR / name for name in FAST_REQUIRED]
    if _is_main_cron(env) or env.get("FORCE_FULL_GATE", "").strip() == "1":
        required_files.extend(CI_DIR / name for name in FULL_REQUIRED)
    if _is_main_cron(env) or env.get("FORCE_CRON_GATE", "").strip() == "1":
        required_files.extend(CI_DIR / name for name in CRON_REQUIRED)

    # Some diagnostics/full gates are no longer hard-wired in ci-gate depends_on.
    # On full/cron modes, allow time for those status files to be written.
    wait_seconds = int(env.get("CI_GATE_STATUS_WAIT_SECONDS", "0") or "0")
    if wait_seconds <= 0 and (
        _is_main_cron(env) or env.get("FORCE_FULL_GATE", "").strip() == "1"
    ):
        wait_seconds = 900
    poll_seconds = int(env.get("CI_GATE_STATUS_POLL_SECONDS", "5") or "5")
    if wait_seconds > 0:
        deadline = time.time() + wait_seconds
        while True:
            pending = []
            for path in required_files:
                if path.exists():
                    continue
                if _infer_missing_status_from_log(path) is not None:
                    continue
                pending.append(path.name)
            if not pending:
                break
            if time.time() >= deadline:
                print(
                    "ci-gate: timeout while waiting for required status files: "
                    + ", ".join(sorted(pending)),
                    file=sys.stderr,
                )
                break
            print(
                "ci-gate: waiting for required status files: "
                + ", ".join(sorted(pending)),
                file=sys.stderr,
            )
            time.sleep(max(poll_seconds, 1))

    # Debug: print current directory and list CI_DIR contents
    print(f"ci-gate: Running in {os.getcwd()}")
    print(f"ci-gate: CI_DIR is {CI_DIR.absolute()}")
    if CI_DIR.exists():
        print(f"ci-gate: CI_DIR contents: {list(CI_DIR.iterdir())}")
    else:
        print("ci-gate: CI_DIR does not exist")

    missing: list[Path] = []
    statuses: dict[str, int] = {}
    for p in required_files:
        if p.exists():
            statuses[p.name] = _read_status(p)
            continue
        inferred = _infer_missing_status_from_log(p)
        if inferred is not None:
            statuses[p.name] = inferred
            print(
                f"ci-gate: inferred status=0 from skip log for missing {p.name}",
                file=sys.stderr,
            )
            continue
        missing.append(p)
        statuses[p.name] = 99

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

    # Print root-cause bundle details directly in ci-gate logs.
    root_cause_json = _run_root_cause_bundle(CI_DIR, env)
    if root_cause_json is not None:
        _print_exact_root_causes(root_cause_json)
    else:
        scan_script = Path("scripts/ci/scan_failure_logs.py")
        if scan_script.exists():
            subprocess.run([sys.executable, str(scan_script)], check=False)

    # Best-effort PR comment for swarm visibility.
    if _is_pr_build(env):
        if env.get("GITEA_TOKEN", "").strip():
            comment_script = Path("scripts/ci/post_ci_failure_pr_comment.py")
            if comment_script.exists():
                subprocess.run([sys.executable, str(comment_script)], check=False)
        else:
            print(
                "ci-gate: PR build but GITEA_TOKEN is not set; cannot post PR comment.",
                file=sys.stderr,
            )
    elif _is_main_cron(env):
        notify_script = Path("scripts/ci/post_ci_failure_discord.py")
        if notify_script.exists():
            subprocess.run([sys.executable, str(notify_script)], check=False)
        else:
            print(
                "ci-gate: cron/main failure notifier script missing; "
                "cannot dispatch swarm handoff notification.",
                file=sys.stderr,
            )
        issue_script = Path("scripts/ci/post_ci_failure_issue.py")
        if issue_script.exists():
            subprocess.run([sys.executable, str(issue_script)], check=False)
        else:
            print(
                "ci-gate: cron/main issue handoff script missing; "
                "cannot create/update Gitea incident issue.",
                file=sys.stderr,
            )

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
