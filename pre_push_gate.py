#!/usr/bin/env python3
"""
Pre-Push Gate: Fast CI validation before git push.

Runs quality checks and targeted tests on changed files.
Designed to complete in <30 seconds for typical changes.

Usage:
    python scripts/pre_push_gate.py [--files file1.py file2.py ...]
    python scripts/pre_push_gate.py  # Auto-detect changed files

Exit codes:
    0 - All checks passed
    1 - One or more checks failed
    2 - Setup/error
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import NamedTuple


class CheckResult(NamedTuple):
    name: str
    passed: bool
    duration_ms: int
    output: str


def run_command(
    cmd: list[str],
    cwd: str | None = None,
    timeout: int = 60,
    check: bool = False,
) -> tuple[int, str]:
    """Run a command and return (returncode, stdout+stderr)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd or os.getcwd(),
            timeout=timeout,
            check=check,
        )
        return result.returncode, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return 124, f"Command timed out after {timeout}s: {' '.join(cmd)}"
    except FileNotFoundError as e:
        return 127, f"Command not found: {cmd[0]}\n{e}"
    except Exception as e:
        return 1, f"Error running command: {' '.join(cmd)}\n{e}"


def get_changed_python_files() -> list[str]:
    """Get list of changed .py files compared to origin/main."""
    if not Path(".git").exists():
        return []

    rc, diff_output = run_command(
        ["git", "diff", "--name-only", "--diff-filter=ACM", "origin/main...HEAD"],
        timeout=10,
    )

    if rc != 0:
        rc, diff_output = run_command(
            ["git", "diff", "--name-only", "--cached"],
            timeout=10,
        )
        if rc != 0:
            return []

    files = []
    for line in diff_output.strip().split("\n"):
        line = line.strip()
        if line.endswith(".py") and not line.startswith("tests/"):
            files.append(line)

    return files


def get_related_test_files(source_files: list[str]) -> list[str]:
    """Find test files related to changed source files."""
    if not source_files:
        return []

    test_files = []
    for src_file in source_files:
        if src_path_parts := src_file.split(os.sep):
            if len(src_path_parts) >= 2 and src_path_parts[0] == "src":
                module_parts = src_path_parts[1:]
                module_path = "/".join(module_parts)
                stem = Path(module_path).stem

                test_patterns = [
                    f"tests/{'/'.join(module_parts[:-1])}/test_{stem}.py",
                    f"tests/{'/'.join(module_parts[:-1])}/{stem}_test.py",
                    f"tests/{module_path.replace('/', '_')}_test.py",
                ]

                for pattern in test_patterns:
                    if Path(pattern).exists():
                        test_files.append(pattern)
                        break

    return list(set(test_files))


def check_black(files: list[str], project_root: str) -> CheckResult:
    """Run black --check on files or entire project if no files specified."""
    start = time.monotonic()
    cmd = ["python3", "-m", "black", "--check"]
    if files:
        cmd.extend(files)
    else:
        cmd.append("src/")

    returncode, output = run_command(cmd, cwd=project_root, timeout=120)
    duration_ms = int((time.monotonic() - start) * 1000)

    return CheckResult(
        name="black",
        passed=returncode == 0,
        duration_ms=duration_ms,
        output=output,
    )


def check_ruff(files: list[str], project_root: str) -> CheckResult:
    """Run ruff check on files or entire project if no files specified."""
    start = time.monotonic()
    cmd = ["python3", "-m", "ruff", "check"]
    if files:
        cmd.extend(files)
    else:
        cmd.append("src/")

    returncode, output = run_command(cmd, cwd=project_root, timeout=60)
    duration_ms = int((time.monotonic() - start) * 1000)

    return CheckResult(
        name="ruff",
        passed=returncode == 0,
        duration_ms=duration_ms,
        output=output,
    )


def check_mypy(files: list[str], project_root: str) -> CheckResult:
    """Run mypy on files if configured and available."""
    start = time.monotonic()

    returncode, _ = run_command(["python3", "-m", "mypy", "--version"], timeout=5)
    if returncode != 0:
        return CheckResult(
            name="mypy",
            passed=True,
            duration_ms=0,
            output="mypy not available, skipping",
        )

    pyproject = Path(project_root) / "pyproject.toml"
    if not pyproject.exists() or "[tool.mypy]" not in pyproject.read_text():
        return CheckResult(
            name="mypy",
            passed=True,
            duration_ms=0,
            output="mypy not configured, skipping",
        )

    cmd = ["python3", "-m", "mypy"]
    if files:
        cmd.extend(files)
    else:
        cmd.append("src/")

    returncode, output = run_command(cmd, cwd=project_root, timeout=120)
    duration_ms = int((time.monotonic() - start) * 1000)

    return CheckResult(
        name="mypy",
        passed=returncode == 0,
        duration_ms=duration_ms,
        output=output,
    )


def check_pytest(test_files: list[str], project_root: str) -> CheckResult:
    """Run pytest on specified test files."""
    start = time.monotonic()

    if not test_files:
        return CheckResult(
            name="pytest",
            passed=True,
            duration_ms=0,
            output="No test files to run",
        )

    cmd = ["python3", "-m", "pytest", "-v", "--tb=short", "--no-header", "-q"]
    cmd.extend(test_files)

    returncode, output = run_command(cmd, cwd=project_root, timeout=300)
    duration_ms = int((time.monotonic() - start) * 1000)

    return CheckResult(
        name="pytest",
        passed=returncode == 0,
        duration_ms=duration_ms,
        output=output,
    )


def syntax_check(files: list[str], project_root: str) -> CheckResult:
    """Run python compile check on files."""
    start = time.monotonic()

    if not files:
        return CheckResult(
            name="syntax",
            passed=True,
            duration_ms=0,
            output="No files to check",
        )

    returncode = 0
    output_lines = []
    for f in files:
        result = subprocess.run(
            ["python3", "-m", "py_compile", f],
            capture_output=True,
            text=True,
            cwd=project_root,
        )
        if result.returncode != 0:
            returncode = 1
            output_lines.append(result.stderr)

    duration_ms = int((time.monotonic() - start) * 1000)

    return CheckResult(
        name="syntax",
        passed=returncode == 0,
        duration_ms=duration_ms,
        output=(
            "\n".join(output_lines)
            if output_lines
            else "All files compiled successfully"
        ),
    )


def print_result(result: CheckResult, verbose: bool = False) -> None:
    """Print a check result with formatting."""
    status = "✓ PASS" if result.passed else "✗ FAIL"
    duration = f"{result.duration_ms}ms"

    print(f"  [{status}] {result.name}: {duration}")

    if verbose or not result.passed:
        if result.output.strip():
            for line in result.output.strip().split("\n")[:20]:
                print(f"    {line}")
            if len(result.output.strip().split("\n")) > 20:
                print(
                    f"    ... ({len(result.output.strip().split(chr(10))) - 20} more lines)"
                )


def print_summary(results: list[CheckResult], total_duration_ms: int) -> None:
    """Print summary of all check results."""
    print("\n" + "=" * 60)
    print("PRE-PUSH GATE SUMMARY")
    print("=" * 60)

    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)

    for result in results:
        print_result(result, verbose=False)

    print("-" * 60)
    print(f"Total duration: {total_duration_ms}ms")
    print(f"Checks: {passed} passed, {failed} failed")

    if failed == 0:
        print("\n✓ All checks passed! Ready to push.")
    else:
        print(f"\n✗ {failed} check(s) failed. Fix issues before pushing.")

    print("=" * 60)


def main() -> int:
    parser = argparse.ArgumentParser(description="Pre-push validation gate for ChiseAI")
    parser.add_argument(
        "--files",
        nargs="+",
        metavar="FILE",
        help="Python files to check (auto-detected if not specified)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed output for all checks",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip pytest (for when tests are run separately)",
    )

    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    project_root = str(script_dir.parent)

    os.environ["PYTHONPATH"] = f"{project_root}/src"

    print("ChiseAI Pre-Push Gate")
    print("=" * 60)

    if args.files:
        source_files = [f for f in args.files if f.endswith(".py")]
    else:
        source_files = get_changed_python_files()

    test_files = [] if args.skip_tests else get_related_test_files(source_files)

    print(f"\nChanged source files: {len(source_files)}")
    if source_files:
        for f in source_files[:10]:
            print(f"  - {f}")
        if len(source_files) > 10:
            print(f"  ... and {len(source_files) - 10} more")

    print(f"\nRelated test files: {len(test_files)}")
    if test_files:
        for f in test_files[:5]:
            print(f"  - {f}")
        if len(test_files) > 5:
            print(f"  ... and {len(test_files) - 5} more")

    print()

    results: list[CheckResult] = []
    start_time = time.monotonic()

    results.append(syntax_check(source_files, project_root))
    results.append(check_black(source_files, project_root))
    results.append(check_ruff(source_files, project_root))
    results.append(check_mypy(source_files, project_root))

    if not args.skip_tests and test_files:
        results.append(check_pytest(test_files, project_root))
    elif args.skip_tests:
        print("  [SKIP] pytest (--skip-tests specified)")
    else:
        print("  [SKIP] pytest (no related tests found)")

    total_duration_ms = int((time.monotonic() - start_time) * 1000)

    print_summary(results, total_duration_ms)

    all_passed = all(r.passed for r in results)
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
