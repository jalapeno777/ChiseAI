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


def run_checks() -> int:
    """Run all pre-push checks. Returns exit code (0=pass, 1=fail)."""
    print("Pre-push CI gate")
    print("=" * 40)

    # Docs-only check — skip all checks if only docs changed
    if _is_docs_only():
        print("  [docs-only] SKIP (only documentation changed)")
        print("\nAll checks passed (docs-only change).")
        return 0

    checks: list[tuple[str, list[str], int]] = [
        ("lint: black", [sys.executable, "-m", "black", "--check", "."], 120),
        ("lint: ruff", [sys.executable, "-m", "ruff", "check", "."], 120),
        ("security-scan", [sys.executable, "-m", "bandit", "r", "-q", "."], 120),
        ("secret-scan", ["detect-secrets", "scan", "."], 120),
        (
            "dependency-audit",
            [sys.executable, "scripts/ci/dependency_audit.py"],
            360,
        ),
    ]

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
