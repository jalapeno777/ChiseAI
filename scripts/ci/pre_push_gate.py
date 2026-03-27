#!/usr/bin/env python3
"""Pre-push local CI gate.

Runs fast checks mirroring FAST_REQUIRED from ci_gate.py before every git push.
This is a best-effort local gate, not a full CI replacement.

Usage:
    python scripts/ci/pre_push_gate.py
    python scripts/ci/pre_push_gate.py --help

Exit codes:
    0 - All checks passed
    1 - One or more checks failed
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _run(title: str, cmd: list[str], timeout: int = 120) -> bool:
    """Run a check command and report pass/fail. Returns True on success."""
    print(f"  [{title}] ... ", end="", flush=True)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode == 0:
            print("PASS")
            return True
        print("FAIL")
        if result.stderr.strip():
            for line in result.stderr.strip().splitlines()[-5:]:
                print(f"    {line}")
        if result.stdout.strip():
            for line in result.stdout.strip().splitlines()[-5:]:
                print(f"    {line}")
        return False
    except FileNotFoundError:
        print("SKIP (tool not found)")
        return True  # Best-effort: missing tool is not a hard failure
    except subprocess.TimeoutExpired:
        print("FAIL (timeout)")
        return False


def _is_docs_only() -> bool:
    """Check if staged changes are docs-only using ci_change_scope.py."""
    scope_script = Path(__file__).parent / "ci_change_scope.py"
    if not scope_script.exists():
        return False
    try:
        result = subprocess.run(
            [sys.executable, str(scope_script), "--mode", "docs-only"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def _get_changed_python_files() -> list[str]:
    """Get list of changed Python files using ci_change_scope.py.

    Returns list of .py file paths, or empty list on error/no changes.
    """
    scope_script = Path(__file__).parent / "ci_change_scope.py"
    if not scope_script.exists():
        return []
    try:
        result = subprocess.run(
            [sys.executable, str(scope_script), "--mode", "changed-python"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return []
        files = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return files
    except (subprocess.TimeoutExpired, OSError):
        return []


def run_checks() -> int:
    """Run all pre-push checks. Returns exit code (0=pass, 1=fail)."""
    print("Pre-push CI gate")
    print("=" * 40)

    # Docs-only check — skip all checks if only docs changed
    if _is_docs_only():
        print("  [docs-only] SKIP (only documentation changed)")
        print("\nAll checks passed (docs-only change).")
        return 0

    # Determine changed Python files for scope-aware linting
    py_files = _get_changed_python_files()
    py_count = len(py_files)
    scope_suffix = ""
    if py_count == 0:
        scope_suffix = " (no Python changed — skipping lint/security)"
    elif py_count <= 20:
        scope_suffix = f" (scope: {py_count} Python file{'s' if py_count != 1 else ''})"

    checks: list[tuple[str, list[str], int]] = []

    # Black: scope-aware (skip if no Python changed, targeted if ≤20, full otherwise)
    if py_count == 0:
        print(f"  [lint: black]{scope_suffix} — SKIP")
    elif py_count <= 20:
        checks.append(
            (
                f"lint: black{scope_suffix}",
                [sys.executable, "-m", "black", "--check", *py_files],
                120,
            )
        )
    else:
        checks.append(
            (
                "lint: black (>20 files, full scan)",
                [sys.executable, "-m", "black", "--check", "."],
                120,
            )
        )

    # Ruff: scope-aware (same logic as black)
    if py_count == 0:
        print(f"  [lint: ruff]{scope_suffix} — SKIP")
    elif py_count <= 20:
        checks.append(
            (
                f"lint: ruff{scope_suffix}",
                [sys.executable, "-m", "ruff", "check", *py_files],
                120,
            )
        )
    else:
        checks.append(
            (
                "lint: ruff (>20 files, full scan)",
                [sys.executable, "-m", "ruff", "check", "."],
                120,
            )
        )

    # Bandit: scope-aware by parent directory (skip if no Python changed)
    if py_count == 0:
        print(f"  [security-scan: bandit]{scope_suffix} — SKIP")
    else:
        parent_dirs = sorted({str(Path(f).parent) for f in py_files})
        if py_count <= 20:
            checks.append(
                (
                    f"security-scan: bandit{scope_suffix}",
                    [sys.executable, "-m", "bandit", "-r", "-q", *parent_dirs],
                    120,
                )
            )
        else:
            checks.append(
                (
                    "security-scan: bandit (>20 files, full scan)",
                    [sys.executable, "-m", "bandit", "-r", "-q", "."],
                    120,
                )
            )

    # detect-secrets: always full-repo scan (fast, needs full scan for secrets)
    checks.append(("secret-scan: detect-secrets", ["detect-secrets", "scan", "."], 120))

    # dependency-audit: always runs (not scope-dependent)
    checks.append(
        (
            "dependency-audit",
            [sys.executable, "scripts/ci/dependency_audit.py"],
            360,
        ),
    )

    passed = 0
    failed = 0
    for title, cmd, timeout in checks:
        if _run(title, cmd, timeout=timeout):
            passed += 1
        else:
            failed += 1

    print("=" * 40)
    print(f"Results: {passed} passed, {failed} failed")

    if failed == 0:
        print("\nAll checks passed. Safe to push.")
        return 0
    else:
        print("\nSome checks failed. Fix issues before pushing.")
        return 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pre-push local CI gate — fast checks before every git push."
    )
    parser.parse_args()
    sys.exit(run_checks())


if __name__ == "__main__":
    main()
