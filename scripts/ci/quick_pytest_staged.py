#!/usr/bin/env python3
"""Quick pytest runner for staged .py files (ST-GIT-REMEDIATION-001).

Finds staged Python files, maps them to their corresponding test files,
and runs pytest on those tests. Designed to be fast (<60s) and stop on first failure.

Exit codes:
    0 = pass (or no test files found)
    1 = test failure
    2 = error (e.g., git/subprocess error)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def get_staged_python_files() -> list[Path]:
    """Return list of staged .py files from git diff --cached."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--", "*.py"],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as exc:
        print(f"Error running git diff: {exc}", file=sys.stderr)
        sys.exit(2)

    if result.returncode != 0:
        print(f"git diff failed: {result.stderr}", file=sys.stderr)
        sys.exit(2)

    files = []
    for line in result.stdout.strip().split("\n"):
        line = line.strip()
        if line and line.endswith(".py"):
            files.append(Path(line))
    return files


def find_test_file(source_file: Path, repo_root: Path) -> Path | None:
    """Find test file corresponding to source file using path conventions.

    Conventions:
    - src/foo/bar.py -> tests/test_foo/test_bar.py or tests/test_bar.py
    - scripts/ci/foo.py -> tests/test_scripts/test_ci/test_foo.py
    """
    source_str = str(source_file)

    if source_str.startswith("src/"):
        # src/foo/bar.py -> tests/test_foo/test_bar.py
        parts = source_file.parts[1:]  # Remove 'src' prefix
        if len(parts) >= 2:
            # tests/test_foo/test_bar.py
            module_dir = parts[0]
            module_name = Path(parts[-1]).stem
            test_path = (
                repo_root / "tests" / f"test_{module_dir}" / f"test_{module_name}.py"
            )
            if test_path.exists():
                return test_path

        # Also try tests/test_bar.py for single-level
        module_name = Path(parts[-1]).stem if parts else source_file.stem
        test_path = repo_root / "tests" / f"test_{module_name}.py"
        if test_path.exists():
            return test_path

    elif source_str.startswith("scripts/"):
        # scripts/ci/foo.py -> tests/test_scripts/test_ci/test_foo.py
        parts = source_file.parts[1:]  # Remove 'scripts' prefix
        if len(parts) >= 2:
            module_parts = [f"test_{p}" for p in parts[:-1]]
            module_name = Path(parts[-1]).stem
            test_path = (
                repo_root / "tests" / "/".join(module_parts) / f"test_{module_name}.py"
            )
            if test_path.exists():
                return test_path
        elif len(parts) == 1:
            # scripts/foo.py -> tests/test_scripts/test_foo.py
            module_name = source_file.stem
            test_path = repo_root / "tests" / "test_scripts" / f"test_{module_name}.py"
            if test_path.exists():
                return test_path

    # Generic fallback: tests/test_<stem>.py
    module_name = source_file.stem
    test_path = repo_root / "tests" / f"test_{module_name}.py"
    if test_path.exists():
        return test_path

    return None


def run_pytest(test_files: list[Path], repo_root: Path) -> int:
    """Run pytest on given test files. Returns exit code."""
    if not test_files:
        print("No test files found for staged changes")
        return 0

    print(f"Running pytest on {len(test_files)} test file(s)...")
    for tf in test_files:
        print(f"  - {tf}")

    try:
        result = subprocess.run(
            ["pytest", *test_files, "-x", "-q", "--tb=short"],
            cwd=repo_root,
            capture_output=False,  # Let output flow to terminal for pre-commit
            text=False,
        )
        return result.returncode
    except Exception as exc:
        print(f"Error running pytest: {exc}", file=sys.stderr)
        return 2


def main() -> int:
    # Find repo root
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        repo_root = Path(result.stdout.strip())
    except Exception as exc:
        print(f"Error finding repo root: {exc}", file=sys.stderr)
        return 2

    # Get staged Python files
    staged_files = get_staged_python_files()
    if not staged_files:
        print("No staged .py files found")
        return 0

    print(f"Found {len(staged_files)} staged .py file(s):")
    for f in staged_files:
        print(f"  - {f}")

    # Find test files
    test_files: list[Path] = []
    for source_file in staged_files:
        test_file = find_test_file(source_file, repo_root)
        if test_file:
            test_files.append(test_file)

    return run_pytest(test_files, repo_root)


if __name__ == "__main__":
    raise SystemExit(main())
