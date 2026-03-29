#!/usr/bin/env python3
"""Run pip-audit against project dependencies when the audit is relevant."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]


DEPENDENCY_AUDIT_PATHS = (
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "requirements-lock.txt",
    "poetry.lock",
    "uv.lock",
    "Pipfile",
    "Pipfile.lock",
    "setup.py",
    "setup.cfg",
    ".woodpecker/ci.yaml",
    "scripts/ci/dependency_audit.py",
    "scripts/ci/pre_push_gate.py",
    "infrastructure/docker/Dockerfile.ci-dependency-audit",
)


def _event_name() -> str:
    return (
        (
            os.environ.get("CI_BUILD_EVENT")
            or os.environ.get("WOODPECKER_BUILD_EVENT")
            or os.environ.get("WOODPECKER_EVENT")
            or os.environ.get("CI_PIPELINE_EVENT")
            or ""
        )
        .strip()
        .lower()
    )


def _branch_name() -> str:
    return (
        os.environ.get("CI_COMMIT_BRANCH")
        or os.environ.get("WOODPECKER_COMMIT_BRANCH")
        or ""
    ).strip()


def _parse_env_changed_files() -> list[str]:
    raw = os.environ.get("CI_PIPELINE_FILES", "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item).strip() for item in parsed if str(item).strip()]


def _git_changed_files() -> list[str]:
    candidates = (
        ["git", "diff", "--name-only", "--cached"],
        ["git", "diff", "--name-only", "origin/main...HEAD"],
        ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
    )
    for cmd in candidates:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode == 0 and proc.stdout.strip():
            return [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    return []


def _changed_files() -> list[str]:
    return _parse_env_changed_files() or _git_changed_files()


def _is_dependency_audit_relevant(changed_files: list[str]) -> bool:
    for path in changed_files:
        if path in DEPENDENCY_AUDIT_PATHS:
            return True
        if path.startswith("requirements/"):
            return True
        if path.startswith("constraints/"):
            return True
    return False


def should_run_dependency_audit() -> tuple[bool, str]:
    for env_var in ("FORCE_DEPENDENCY_AUDIT", "FORCE_FULL_GATE", "CI_FORCE_FULL"):
        raw = os.environ.get(env_var, "").strip()
        if raw == "1":
            try:
                from audit.override_audit import log_override_if_active

                log_override_if_active(env_var, reason="force dependency audit gate")
            except Exception:
                pass  # audit is best-effort
            return True, f"{env_var}=1"

    event = _event_name()
    branch = _branch_name()
    if event == "cron" and branch == "main":
        return True, "cron main audit"
    if event == "manual" and branch == "main":
        return True, "manual main audit"

    changed_files = _changed_files()
    if _is_dependency_audit_relevant(changed_files):
        return True, "dependency inputs changed"

    if changed_files:
        return False, "no dependency or audit files changed"
    return False, "no changed-file metadata available and no dependency diff detected"


def main() -> int:
    should_run, reason = should_run_dependency_audit()
    if not should_run:
        print(f"dependency-audit: skipping ({reason})")
        return 0

    print(f"dependency-audit: running ({reason})")
    baked_req = Path("/opt/chiseai/dependency-audit-requirements.txt")
    if baked_req.exists():
        cmd = [
            sys.executable,
            "-m",
            "pip_audit",
            "-r",
            str(baked_req),
            "--ignore",
            "GHSA-5239-wwwm-4pmq",
            "--progress-spinner",
            "off",
            "--desc",
            "off",
        ]
    else:
        pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
        deps = pyproject.get("project", {}).get("dependencies", [])
        if not isinstance(deps, list) or not deps:
            print("dependency-audit: no dependencies found; skipping")
            return 0

        cleaned: list[str] = []
        for dep in deps:
            d = str(dep).strip()
            if not d or d.startswith("-e "):
                continue
            cleaned.append(d)

        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as tmp:
            for dep in cleaned:
                tmp.write(dep + "\n")
            req_path = tmp.name
        cmd = [
            sys.executable,
            "-m",
            "pip_audit",
            "-r",
            req_path,
            "--ignore",
            "GHSA-5239-wwwm-4pmq",
            "--progress-spinner",
            "off",
            "--desc",
            "off",
        ]
    proc = subprocess.run(cmd, check=False, timeout=300)
    if proc.returncode == 0:
        print("dependency-audit: OK")
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
