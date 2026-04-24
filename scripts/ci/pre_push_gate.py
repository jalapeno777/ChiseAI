#!/usr/bin/env python3
"""Fast pre-push gate aligned with feature-branch remote CI.

This gate intentionally mirrors the lightweight blocking checks from
`.woodpecker/push.yaml`:
- docs-only short circuit
- changed-file black --check
- changed-file ruff check
- changed-file secret scan

It is designed to be enforced via the repo-managed `.githooks/pre-push` hook.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _scope_script() -> Path:
    return Path(__file__).resolve().with_name("ci_change_scope.py")


def _secret_scan_script() -> Path:
    return Path(__file__).resolve().with_name("secret_scan_changed.py")


def _run(
    title: str,
    cmd: list[str],
    *,
    cwd: Path = REPO_ROOT,
    timeout: int = 120,
) -> tuple[bool, str, int]:
    start = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        return (
            False,
            f"{cmd[0]} not found: {exc}",
            int((time.monotonic() - start) * 1000),
        )
    except subprocess.TimeoutExpired:
        return (
            False,
            f"{title} timed out after {timeout}s",
            int((time.monotonic() - start) * 1000),
        )

    output = "\n".join(
        part.strip() for part in (result.stdout, result.stderr) if part.strip()
    )
    return (
        result.returncode == 0,
        output,
        int((time.monotonic() - start) * 1000),
    )


def _changed_python_files() -> list[str]:
    scope = _scope_script()
    result = subprocess.run(
        [sys.executable, str(scope), "--mode", "changed-python"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _is_docs_only() -> bool:
    scope = _scope_script()
    result = subprocess.run(
        [sys.executable, str(scope), "--mode", "docs-only"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return result.returncode == 0


def _print_result(title: str, ok: bool, duration_ms: int, output: str) -> None:
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {title}: {duration_ms}ms")
    if not ok and output:
        for line in output.splitlines()[:20]:
            print(f"    {line}")
        extra = len(output.splitlines()) - 20
        if extra > 0:
            print(f"    ... ({extra} more lines)")


def _current_branch() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _is_feature_branch(branch: str) -> bool:
    return branch.startswith("feature/")


def _branch_is_up_to_date_with_main() -> tuple[bool, str]:
    fetch = subprocess.run(
        ["git", "fetch", "origin", "main"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if fetch.returncode != 0:
        out = "\n".join(x for x in (fetch.stdout, fetch.stderr) if x.strip())
        return False, out or "git fetch origin main failed"

    check = subprocess.run(
        ["git", "merge-base", "--is-ancestor", "origin/main", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if check.returncode == 0:
        return True, "branch includes latest origin/main"

    msg = (
        "branch is behind origin/main. Run "
        "`git fetch origin --prune && git rebase origin/main` (or merge origin/main) "
        "before pushing."
    )
    return False, msg


def run_gate(*, skip_secret_scan: bool) -> int:
    print("ChiseAI pre-push gate")
    print("=" * 48)

    branch = _current_branch()
    if _is_feature_branch(branch):
        ok, freshness_output = _branch_is_up_to_date_with_main()
        _print_result("branch-freshness", ok, 0, freshness_output)
        if not ok:
            print("\nPre-push gate failed. Fix issues before pushing.")
            return 1

    if _is_docs_only():
        print("  [PASS] docs-only: changed files are documentation/opencode only")
        print("\nAll checks passed.")
        return 0

    py_files = _changed_python_files()
    if py_files:
        print(f"Changed Python files: {len(py_files)}")
        for path in py_files[:10]:
            print(f"  - {path}")
        if len(py_files) > 10:
            print(f"  ... and {len(py_files) - 10} more")
    else:
        print("Changed Python files: 0")

    checks: list[tuple[str, list[str], int]] = []
    if py_files:
        checks.append(
            ("black", [sys.executable, "-m", "black", "--check", *py_files], 120)
        )
        checks.append(("ruff", [sys.executable, "-m", "ruff", "check", *py_files], 120))
    else:
        print("  [PASS] black: skipped (no changed Python files)")
        print("  [PASS] ruff: skipped (no changed Python files)")

    if skip_secret_scan:
        print("  [PASS] secret-scan: skipped (--skip-secret-scan)")
    else:
        checks.append(
            (
                "secret-scan",
                [sys.executable, str(_secret_scan_script())],
                120,
            )
        )

    # CI base tag drift check
    drift_detector = Path(__file__).resolve().with_name("ci_base_tag_drift_detector.py")
    checks.append(
        (
            "ci-base-tag-drift",
            [sys.executable, str(drift_detector)],
            60,
        )
    )

    failures = 0
    total_duration = 0
    for title, cmd, timeout in checks:
        ok, output, duration_ms = _run(title, cmd, timeout=timeout)
        total_duration += duration_ms
        _print_result(title, ok, duration_ms, output)
        if not ok:
            failures += 1

    print("-" * 48)
    print(f"Total duration: {total_duration}ms")
    if failures:
        print(f"Checks failed: {failures}")
        print("\nPre-push gate failed. Fix issues before pushing.")
        return 1

    print("Checks failed: 0")
    print("\nAll checks passed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fast pre-push checks aligned with remote feature-branch CI."
    )
    parser.add_argument(
        "--skip-secret-scan",
        action="store_true",
        help="Skip changed-file secret scan.",
    )
    args = parser.parse_args()
    return run_gate(skip_secret_scan=args.skip_secret_scan)


if __name__ == "__main__":
    raise SystemExit(main())
