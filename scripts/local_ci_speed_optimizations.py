#!/usr/bin/env python3
"""Local CI Speed Optimizations - Orchestrates intelligent test selection and parallel execution.

This module provides:
- Intelligent test selection based on git diff
- Parallel execution improvements
- Caching for unchanged dependencies
- Timing benchmarks

Usage:
    python scripts/local_ci_speed_optimizations.py [options]

Options:
    --full              Run complete test suite (no selective testing)
    --parallel          Enable parallel test execution
    --workers N         Number of parallel workers (default: auto)
    --max-workers N     Maximum number of workers (default: 4)
    --cache             Enable dependency caching
    --benchmark         Run benchmark and print timing results
    --output-dir DIR    Output directory for results (default: _bmad-output/ci)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

# Try to import test_selector
try:
    sys.path.insert(0, str(Path(__file__).parent))
    from ci.test_selector import get_changed_files, select_tests
except ImportError:
    # Fallback if test_selector not available
    select_tests = None
    get_changed_files = None


@dataclass
class BenchmarkResult:
    """Stores benchmark timing results."""

    mode: str = "unknown"
    duration_seconds: float = 0.0
    tests_run: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    tests_skipped: int = 0
    parallel: bool = False
    workers: int = 0
    cache_used: bool = False
    selected_tests: list[str] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    timestamp: str = ""


def ensure_output_dir(output_dir: str) -> Path:
    """Create output directory if it doesn't exist."""
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_optimal_workers(max_workers: int = 4) -> int:
    """Determine optimal number of workers based on CPU count."""
    try:
        cpu_count = os.cpu_count() or 1
        return min(cpu_count, max_workers)
    except Exception:
        return min(4, max_workers)


def run_pytest(
    tests: list[str],
    parallel: bool = False,
    workers: int = 4,
    output_dir: str = "_bmad-output/ci",
    junit_suffix: str = "",
) -> tuple[int, str]:
    """Run pytest with given configuration.

    Returns:
        Tuple of (exit_code, output)
    """
    output_path = ensure_output_dir(output_dir)
    junit_file = output_path / f"pytest-junit{junit_suffix}.xml"

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "--junitxml",
        str(junit_file),
    ]

    if parallel:
        cmd.extend(["-n", str(workers)])

    cmd.extend(tests)

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )

    return result.returncode, result.stdout + result.stderr


def parse_pytest_output(output: str) -> dict:
    """Parse pytest output to extract test counts."""
    counts = {"passed": 0, "failed": 0, "skipped": 0, "error": 0}

    for line in output.splitlines():
        if " passed" in line:
            parts = line.split()
            for i, part in enumerate(parts):
                if part == "passed" and i > 0:
                    try:
                        counts["passed"] = int(parts[i - 1])
                    except (ValueError, IndexError):
                        pass
        elif " failed" in line:
            parts = line.split()
            for i, part in enumerate(parts):
                if part == "failed" and i > 0:
                    try:
                        counts["failed"] = int(parts[i - 1])
                    except (ValueError, IndexError):
                        pass
        elif " skipped" in line:
            parts = line.split()
            for i, part in enumerate(parts):
                if part == "skipped" and i > 0:
                    try:
                        counts["skipped"] = int(parts[i - 1])
                    except (ValueError, IndexError):
                        pass

    return counts


def run_syntax_check(files: list[str]) -> tuple[int, str]:
    """Run Python syntax check on files."""
    if not files:
        return 0, "No files to check"

    cmd = [sys.executable, "-m", "py_compile"] + files
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr


def save_benchmark_result(result: BenchmarkResult, output_dir: str) -> None:
    """Save benchmark result to JSON file."""
    output_path = ensure_output_dir(output_dir)
    result_file = output_path / "benchmark.json"

    result_dict = {
        "mode": result.mode,
        "duration_seconds": result.duration_seconds,
        "tests_run": result.tests_run,
        "tests_passed": result.tests_passed,
        "tests_failed": result.tests_failed,
        "tests_skipped": result.tests_skipped,
        "parallel": result.parallel,
        "workers": result.workers,
        "cache_used": result.cache_used,
        "selected_tests_count": len(result.selected_tests),
        "changed_files_count": len(result.changed_files),
        "timestamp": result.timestamp,
    }

    with open(result_file, "w") as f:
        json.dump(result_dict, f, indent=2)


def print_benchmark_summary(result: BenchmarkResult) -> None:
    """Print benchmark summary to console."""
    print("\n" + "=" * 60)
    print("LOCAL CI BENCHMARK SUMMARY")
    print("=" * 60)
    print(f"Mode:              {result.mode}")
    print(f"Duration:          {result.duration_seconds:.2f}s")
    print(f"Tests Run:         {result.tests_run}")
    print(f"  Passed:          {result.tests_passed}")
    print(f"  Failed:          {result.tests_failed}")
    print(f"  Skipped:         {result.tests_skipped}")
    print(f"Parallel:          {result.parallel}")
    print(f"Workers:           {result.workers}")
    print(f"Cache Used:        {result.cache_used}")
    print(f"Changed Files:     {len(result.changed_files)}")
    print(f"Selected Tests:    {len(result.selected_tests)}")
    print("=" * 60)


def run_full_suite(
    parallel: bool = False,
    workers: int = 4,
    output_dir: str = "_bmad-output/ci",
) -> BenchmarkResult:
    """Run the complete test suite."""
    start_time = time.time()

    # Find all test files
    all_tests: list[str] = []
    for root, dirs, files in os.walk("tests"):
        dirs[:] = [d for d in dirs if d not in {"__pycache__", ".git", ".pytest_cache"}]
        for f in files:
            if (f.startswith("test_") or f.endswith("_test.py")) and f.endswith(".py"):
                if f not in {"__init__.py", "conftest.py"}:
                    all_tests.append(os.path.join(root, f))

    result = BenchmarkResult(
        mode="full",
        selected_tests=all_tests,
        parallel=parallel,
        workers=workers if parallel else 0,
        timestamp=datetime.now().isoformat(),
    )

    if not all_tests:
        result.duration_seconds = time.time() - start_time
        return result

    exit_code, output = run_pytest(
        all_tests,
        parallel=parallel,
        workers=workers,
        output_dir=output_dir,
        junit_suffix="-full",
    )

    counts = parse_pytest_output(output)
    result.tests_passed = counts["passed"]
    result.tests_failed = counts["failed"]
    result.tests_skipped = counts["skipped"]
    result.tests_run = result.tests_passed + result.tests_failed
    result.duration_seconds = time.time() - start_time

    return result


def run_selective_suite(
    base_ref: str | None = None,
    parallel: bool = False,
    workers: int = 4,
    cache_file: str = ".bmad-test-cache.json",
    output_dir: str = "_bmad-output/ci",
) -> BenchmarkResult:
    """Run selective tests based on changed files."""
    start_time = time.time()

    result = BenchmarkResult(
        mode="selective",
        parallel=parallel,
        workers=workers if parallel else 0,
        timestamp=datetime.now().isoformat(),
    )

    # Get changed files
    if get_changed_files:
        changed_files = get_changed_files(base_ref)
        result.changed_files = changed_files
    else:
        # Fallback to git diff
        proc = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1..HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        changed_files = [
            line.strip() for line in proc.stdout.splitlines() if line.strip()
        ]
        result.changed_files = changed_files

    # Select tests
    if select_tests:
        selected, metadata = select_tests(
            full=False,
            base_ref=base_ref,
            cache_file=cache_file,
            verbose=False,
        )
        result.selected_tests = selected
        result.cache_used = metadata.get("mapping_cache_used", False)

        if metadata.get("fallback_reason"):
            print(f"Note: Falling back due to: {metadata['fallback_reason']}")
    else:
        # Fallback - find tests matching changed files
        selected = _fallback_test_selection(changed_files)
        result.selected_tests = selected

    if not selected:
        # No tests to run - run syntax check on changed files
        py_files = [f for f in changed_files if f.endswith(".py") and Path(f).exists()]
        if py_files:
            exit_code, output = run_syntax_check(py_files)
            result.duration_seconds = time.time() - start_time
            result.tests_run = len(py_files)
            return result
        result.duration_seconds = time.time() - start_time
        return result

    exit_code, output = run_pytest(
        selected,
        parallel=parallel,
        workers=workers,
        output_dir=output_dir,
        junit_suffix="-selective",
    )

    counts = parse_pytest_output(output)
    result.tests_passed = counts["passed"]
    result.tests_failed = counts["failed"]
    result.tests_skipped = counts["skipped"]
    result.tests_run = result.tests_passed + result.tests_failed
    result.duration_seconds = time.time() - start_time

    return result


def _fallback_test_selection(changed_files: list[str]) -> list[str]:
    """Fallback test selection when test_selector is not available."""
    tests: dict[str, bool] = {}

    for changed in changed_files:
        path = Path(changed)
        if not changed.endswith(".py"):
            continue

        # Skip if not in src
        if not str(path).startswith("src/"):
            continue

        stem = path.stem
        parent = path.parent.name

        # Look for matching tests
        for pattern in [
            f"tests/test_{stem}.py",
            f"tests/{parent}/test_{stem}.py",
            f"tests/unit/{parent}/test_{stem}.py",
        ]:
            if Path(pattern).exists():
                tests[pattern] = True

    return list(tests.keys())


def compare_benchmarks(
    baseline: BenchmarkResult,
    optimized: BenchmarkResult,
) -> dict:
    """Compare two benchmark results and compute speedup."""
    speedup = 0.0
    if baseline.duration_seconds > 0:
        speedup = baseline.duration_seconds / optimized.duration_seconds

    test_reduction = 0
    if baseline.tests_run > 0:
        test_reduction = (
            (baseline.tests_run - optimized.tests_run) / baseline.tests_run
        ) * 100

    return {
        "speedup_factor": speedup,
        "speedup_percent": (speedup - 1) * 100,
        "time_saved_seconds": baseline.duration_seconds - optimized.duration_seconds,
        "test_reduction_percent": test_reduction,
        "baseline_duration": baseline.duration_seconds,
        "optimized_duration": optimized.duration_seconds,
        "baseline_tests": baseline.tests_run,
        "optimized_tests": optimized.tests_run,
    }


def run_benchmark(
    full: bool = False,
    parallel: bool = False,
    workers: int = 4,
    output_dir: str = "_bmad-output/ci",
) -> BenchmarkResult:
    """Run a benchmark comparison."""
    print("Running benchmark...")

    if full:
        return run_full_suite(parallel=parallel, workers=workers, output_dir=output_dir)
    else:
        return run_selective_suite(
            parallel=parallel, workers=workers, output_dir=output_dir
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Local CI Speed Optimizations - Orchestrates intelligent test selection"
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run complete test suite (no selective testing)",
    )
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Enable parallel test execution",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Number of parallel workers (default: auto-detect)",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=4,
        help="Maximum number of workers (default: 4)",
    )
    parser.add_argument(
        "--cache",
        action="store_true",
        default=True,
        help="Enable dependency caching (default: enabled)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_false",
        dest="cache",
        help="Disable dependency caching",
    )
    parser.add_argument(
        "--benchmark",
        action="store_true",
        help="Run benchmark and print timing results",
    )
    parser.add_argument(
        "--output-dir",
        default="_bmad-output/ci",
        help="Output directory for results (default: _bmad-output/ci)",
    )
    parser.add_argument(
        "--base-ref",
        default=None,
        help="Git ref to compare against (default: origin/main)",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Compare selective vs full suite (run both)",
    )

    args = parser.parse_args()

    workers = args.workers or get_optimal_workers(args.max_workers)

    if args.compare:
        # Run both full and selective, then compare
        print("Running comparison: full vs selective suite")
        print("-" * 40)

        full_result = run_full_suite(
            parallel=args.parallel, workers=workers, output_dir=args.output_dir
        )
        selective_result = run_selective_suite(
            base_ref=args.base_ref,
            parallel=args.parallel,
            workers=workers,
            output_dir=args.output_dir,
        )

        print_benchmark_summary(full_result)
        print_benchmark_summary(selective_result)

        comparison = compare_benchmarks(full_result, selective_result)

        print("\n" + "=" * 60)
        print("COMPARISON RESULTS")
        print("=" * 60)
        print(f"Speedup Factor:          {comparison['speedup_factor']:.2f}x")
        print(f"Time Saved:              {comparison['time_saved_seconds']:.2f}s")
        print(f"Test Reduction:          {comparison['test_reduction_percent']:.1f}%")
        print("=" * 60)

        # Save both results
        save_benchmark_result(full_result, args.output_dir)
        save_benchmark_result(selective_result, args.output_dir + "-selective")

        return 0

    if args.benchmark:
        result = run_benchmark(
            full=args.full,
            parallel=args.parallel,
            workers=workers,
            output_dir=args.output_dir,
        )
        print_benchmark_summary(result)
        save_benchmark_result(result, args.output_dir)
        return 0

    # Default: run selective or full suite
    if args.full:
        result = run_full_suite(
            parallel=args.parallel, workers=workers, output_dir=args.output_dir
        )
    else:
        result = run_selective_suite(
            base_ref=args.base_ref,
            parallel=args.parallel,
            workers=workers,
            output_dir=args.output_dir,
        )

    print_benchmark_summary(result)
    save_benchmark_result(result, args.output_dir)

    return 0 if result.tests_failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
