#!/usr/bin/env python3
"""Local CI Parallel Runner - Dynamic worker allocation and balanced test distribution.

This module provides:
- Dynamic worker allocation based on CPU cores (min(cpu_count, 8))
- Test time estimation for balanced distribution across workers
- Worker pool management
- Progress tracking and reporting
- Historical runtime tracking for better distribution

Usage:
    python scripts/local_ci_parallel_runner.py [options]

Options:
    --benchmark          Run benchmark to compare parallel vs single-worker
    --workers N          Number of workers (default: auto)
    --max-workers N      Maximum workers cap (default: 8)
    --test-dirs DIRS     Colon-separated list of test directories
    --output-dir DIR     Output directory (default: _bmad-output/ci)
    --estimate-only      Only estimate timing, don't run tests
    --history-file FILE  Path to runtime history JSON (default: .bmad-test-times.json)
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

# Default constants
DEFAULT_MAX_WORKERS = 8
HISTORY_FILE = ".bmad-test-times.json"


@dataclass
class TestResult:
    """Stores individual test result."""

    test_id: str
    duration: float
    passed: bool
    worker: int = 0


@dataclass
class WorkerStats:
    """Statistics for a single worker."""

    worker_id: int
    tests_assigned: list[str] = field(default_factory=list)
    total_duration: float = 0.0
    start_time: float = 0.0
    end_time: float = 0.0

    @property
    def duration(self) -> float:
        """Total runtime for this worker."""
        return self.end_time - self.start_time if self.end_time > 0 else 0.0


@dataclass
class BenchmarkResults:
    """Results from a benchmark run."""

    mode: str  # "single" or "parallel"
    total_duration: float
    num_workers: int
    tests_run: int
    tests_passed: int
    tests_failed: int
    tests_skipped: int
    worker_stats: list[WorkerStats] = field(default_factory=list)
    test_results: list[TestResult] = field(default_factory=list)
    timestamp: str = ""


def get_cpu_count() -> int:
    """Get the number of CPU cores available."""
    try:
        return os.cpu_count() or 1
    except Exception:
        return 1


def get_optimal_workers(
    requested: int | None = None, max_workers: int = DEFAULT_MAX_WORKERS
) -> int:
    """Determine optimal number of workers.

    Uses min(cpu_count, max_workers) if requested is None,
    otherwise uses min(requested, cpu_count, max_workers).

    Args:
        requested: Requested number of workers (None for auto-detect)
        max_workers: Maximum worker cap (default: 8)

    Returns:
        Optimal number of workers
    """
    cpu_count = get_cpu_count()
    if requested is None:
        return min(cpu_count, max_workers)
    return min(requested, cpu_count, max_workers)


def load_test_history(history_file: str = HISTORY_FILE) -> dict[str, float]:
    """Load historical test runtimes.

    Args:
        history_file: Path to history JSON file

    Returns:
        Dictionary mapping test_id to average duration in seconds
    """
    path = Path(history_file)
    if not path.exists():
        return {}

    try:
        with open(path) as f:
            data = json.load(f)
            # Convert to float durations
            return {k: float(v) for k, v in data.items()}
    except (json.JSONDecodeError, ValueError):
        return {}


def save_test_history(
    history: dict[str, float], history_file: str = HISTORY_FILE
) -> None:
    """Save test runtimes to history file.

    Args:
        history: Dictionary mapping test_id to duration
        history_file: Path to history JSON file
    """
    path = Path(history_file)
    try:
        with open(path, "w") as f:
            json.dump(history, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not save test history: {e}")


def discover_tests(test_dirs: list[str]) -> list[str]:
    """Discover all test files in given directories.

    Args:
        test_dirs: List of test directory paths

    Returns:
        List of test file paths
    """
    tests = []
    for test_dir in test_dirs:
        dir_path = Path(test_dir)
        if not dir_path.exists():
            continue

        for root, _, files in os.walk(dir_path):
            # Skip hidden and cache directories
            root_path = Path(root)
            if any(part.startswith(".") for part in root_path.parts):
                continue

            for f in files:
                if (f.startswith("test_") or f.endswith("_test.py")) and f.endswith(
                    ".py"
                ):
                    if f not in {"__init__.py", "conftest.py"}:
                        tests.append(str(Path(root) / f))

    return sorted(tests)


def estimate_test_times(
    tests: list[str], history: dict[str, float]
) -> dict[str, float]:
    """Estimate runtime for each test file based on history.

    Uses historical data if available, otherwise uses default estimate.

    Args:
        tests: List of test file paths
        history: Historical runtime data

    Returns:
        Dictionary mapping test_id to estimated duration
    """
    DEFAULT_ESTIMATE = 1.0  # 1 second default

    estimates = {}
    for test in tests:
        # Try to use historical average
        if test in history:
            estimates[test] = history[test]
        else:
            # Estimate based on file size
            try:
                size = Path(test).stat().st_size
                # Rough estimate: 0.1ms per byte, minimum 0.5s
                estimates[test] = max(0.5, size * 0.0001)
            except OSError:
                estimates[test] = DEFAULT_ESTIMATE

    return estimates


def distribute_tests_balanced(
    tests: list[str],
    estimates: dict[str, float],
    num_workers: int,
) -> dict[int, list[str]]:
    """Distribute tests across workers for balanced execution time.

    Uses a greedy bin-packing algorithm to distribute tests
    based on estimated runtimes.

    Args:
        tests: List of test file paths
        estimates: Estimated runtime for each test
        num_workers: Number of workers

    Returns:
        Dictionary mapping worker_id to list of test paths
    """
    if not tests:
        return {i: [] for i in range(num_workers)}

    # Calculate total estimated time
    total_time = sum(estimates.get(t, 1.0) for t in tests)
    total_time / num_workers

    # Initialize worker loads
    worker_loads: dict[int, float] = {i: 0.0 for i in range(num_workers)}
    worker_tests: dict[int, list[str]] = {i: [] for i in range(num_workers)}

    # Sort tests by estimated time (longest first) for better packing
    sorted_tests = sorted(tests, key=lambda t: estimates.get(t, 1.0), reverse=True)

    # Greedy assignment to least loaded worker
    for test in sorted_tests:
        # Find worker with minimum current load
        min_worker = min(worker_loads.keys(), key=lambda w: worker_loads[w])
        worker_tests[min_worker].append(test)
        worker_loads[min_worker] += estimates.get(test, 1.0)

    return worker_tests


def run_tests_parallel(
    tests: list[str],
    num_workers: int,
    output_dir: str = "_bmad-output/ci",
) -> BenchmarkResults:
    """Run tests in parallel using pytest-xdist.

    Args:
        tests: List of test file paths
        num_workers: Number of parallel workers
        output_dir: Output directory for results

    Returns:
        BenchmarkResults with execution statistics
    """
    start_time = time.time()
    results = BenchmarkResults(
        mode="parallel",
        total_duration=0.0,
        num_workers=num_workers,
        tests_run=0,
        tests_passed=0,
        tests_failed=0,
        tests_skipped=0,
        timestamp=datetime.now().isoformat(),
    )

    # Ensure output directory exists
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    junit_file = Path(output_dir) / "pytest-junit-parallel.xml"

    # Build pytest command
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "--junitxml",
        str(junit_file),
        "-n",
        str(num_workers),
        "-v",
    ]
    cmd.extend(tests)

    # Run pytest
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )

    end_time = time.time()
    results.total_duration = end_time - start_time

    # Parse output for counts
    output = proc.stdout + proc.stderr
    (
        results.tests_run,
        results.tests_passed,
        results.tests_failed,
        results.tests_skipped,
    ) = parse_pytest_counts(output)

    # Create worker stats (approximate since xdist manages workers)
    for i in range(num_workers):
        results.worker_stats.append(
            WorkerStats(
                worker_id=i,
                start_time=start_time,
                end_time=end_time,
            )
        )

    return results


def run_tests_single(
    tests: list[str],
    output_dir: str = "_bmad-output/ci",
) -> BenchmarkResults:
    """Run tests sequentially (single worker).

    Args:
        tests: List of test file paths
        output_dir: Output directory for results

    Returns:
        BenchmarkResults with execution statistics
    """
    start_time = time.time()
    results = BenchmarkResults(
        mode="single",
        total_duration=0.0,
        num_workers=1,
        tests_run=0,
        tests_passed=0,
        tests_failed=0,
        tests_skipped=0,
        timestamp=datetime.now().isoformat(),
    )

    # Ensure output directory exists
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    junit_file = Path(output_dir) / "pytest-junit-single.xml"

    # Build pytest command (no -n flag)
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "--junitxml",
        str(junit_file),
        "-v",
    ]
    cmd.extend(tests)

    # Run pytest
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )

    end_time = time.time()
    results.total_duration = end_time - start_time

    # Parse output for counts
    output = proc.stdout + proc.stderr
    (
        results.tests_run,
        results.tests_passed,
        results.tests_failed,
        results.tests_skipped,
    ) = parse_pytest_counts(output)

    # Single worker stat
    results.worker_stats.append(
        WorkerStats(
            worker_id=0,
            start_time=start_time,
            end_time=end_time,
        )
    )

    return results


def parse_pytest_counts(output: str) -> tuple[int, int, int, int]:
    """Parse pytest output to extract test counts.

    Args:
        output: Combined stdout/stderr from pytest

    Returns:
        Tuple of (tests_run, passed, failed, skipped)
    """
    passed = failed = skipped = 0

    for line in output.splitlines():
        line = line.strip()
        # Look for summary lines like "15 passed, 2 failed, 3 skipped"
        if " passed" in line or "failed" in line or "skipped" in line:
            parts = line.replace(",", " ").split()
            for i, part in enumerate(parts):
                try:
                    if part == "passed" and i > 0:
                        passed = int(parts[i - 1])
                    elif part == "failed" and i > 0:
                        failed = int(parts[i - 1])
                    elif part == "skipped" and i > 0:
                        skipped = int(parts[i - 1])
                except (ValueError, IndexError):
                    continue

    return passed + failed, passed, failed, skipped


def run_benchmark(
    test_dirs: list[str],
    num_workers: int,
    output_dir: str = "_bmad-output/ci",
    history_file: str = HISTORY_FILE,
) -> tuple[BenchmarkResults, BenchmarkResults]:
    """Run benchmark comparing single vs parallel execution.

    Args:
        test_dirs: List of test directories to run
        num_workers: Number of workers for parallel run
        output_dir: Output directory for results
        history_file: Path to runtime history

    Returns:
        Tuple of (single_results, parallel_results)
    """
    # Discover tests
    tests = discover_tests(test_dirs)
    if not tests:
        print("No tests found to run")
        sys.exit(1)

    print(f"Discovered {len(tests)} test files")
    print(f"Running with {num_workers} workers...")

    # Load history for estimates
    load_test_history(history_file)

    # Run single-worker baseline
    print("\n--- Running single-worker baseline ---")
    single_results = run_tests_single(tests, output_dir)
    print_single_summary(single_results)

    # Run parallel
    print(f"\n--- Running parallel with {num_workers} workers ---")
    parallel_results = run_tests_parallel(tests, num_workers, output_dir)
    print_parallel_summary(parallel_results)

    return single_results, parallel_results


def print_single_summary(results: BenchmarkResults) -> None:
    """Print single-worker summary."""
    print("\nSingle-worker results:")
    print(f"  Duration:  {results.total_duration:.2f}s")
    print(
        f"  Tests:     {results.tests_run} (passed={results.tests_passed}, failed={results.tests_failed})"
    )


def print_parallel_summary(results: BenchmarkResults) -> None:
    """Print parallel execution summary."""
    print(f"\nParallel results ({results.num_workers} workers):")
    print(f"  Duration:  {results.total_duration:.2f}s")
    print(
        f"  Tests:     {results.tests_run} (passed={results.tests_passed}, failed={results.tests_failed})"
    )


def print_benchmark_comparison(
    single: BenchmarkResults, parallel: BenchmarkResults
) -> None:
    """Print comparison between single and parallel runs."""
    speedup = (
        single.total_duration / parallel.total_duration
        if parallel.total_duration > 0
        else 0
    )
    time_saved = single.total_duration - parallel.total_duration

    print("\n" + "=" * 60)
    print("BENCHMARK COMPARISON")
    print("=" * 60)
    print(f"Single-worker duration:  {single.total_duration:.2f}s")
    print(f"Parallel duration:       {parallel.total_duration:.2f}s")
    print(f"Speedup:                 {speedup:.2f}x")
    print(f"Time saved:              {time_saved:.2f}s ({(speedup - 1) * 100:.1f}%)")
    print("=" * 60)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Local CI Parallel Runner - Dynamic worker allocation and balanced test distribution"
    )
    parser.add_argument(
        "--benchmark",
        action="store_true",
        help="Run benchmark comparing single vs parallel execution",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help=f"Number of workers (default: auto, max {DEFAULT_MAX_WORKERS})",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=DEFAULT_MAX_WORKERS,
        help=f"Maximum number of workers (default: {DEFAULT_MAX_WORKERS})",
    )
    parser.add_argument(
        "--test-dirs",
        default="tests",
        help="Colon-separated list of test directories (default: tests)",
    )
    parser.add_argument(
        "--output-dir",
        default="_bmad-output/ci",
        help="Output directory (default: _bmad-output/ci)",
    )
    parser.add_argument(
        "--estimate-only",
        action="store_true",
        help="Only estimate timing, don't run tests",
    )
    parser.add_argument(
        "--history-file",
        default=HISTORY_FILE,
        help=f"Path to runtime history JSON (default: {HISTORY_FILE})",
    )

    args = parser.parse_args()

    # Parse test directories
    test_dirs = args.test_dirs.split(":")

    # Determine worker count
    num_workers = get_optimal_workers(args.workers, args.max_workers)
    print(
        f"Using {num_workers} workers (requested={args.workers}, max={args.max_workers}, cpus={get_cpu_count()})"
    )

    # Discover tests
    tests = discover_tests(test_dirs)
    if not tests:
        print("No tests found")
        return 1

    print(f"Discovered {len(tests)} test files")

    # Load history for estimates
    history = load_test_history(args.history_file)

    if args.estimate_only:
        # Just show estimate
        estimates = estimate_test_times(tests, history)
        total_estimate = sum(estimates.values())
        distribution = distribute_tests_balanced(tests, estimates, num_workers)

        print(f"\nEstimated total runtime: {total_estimate:.2f}s")
        print(f"\nDistribution across {num_workers} workers:")
        for worker_id, worker_tests in sorted(distribution.items()):
            worker_time = sum(estimates.get(t, 1.0) for t in worker_tests)
            print(
                f"  Worker {worker_id}: {len(worker_tests)} tests, ~{worker_time:.2f}s"
            )
        return 0

    if args.benchmark:
        single, parallel = run_benchmark(
            test_dirs=test_dirs,
            num_workers=num_workers,
            output_dir=args.output_dir,
            history_file=args.history_file,
        )
        print_benchmark_comparison(single, parallel)

        # Save results
        output_path = Path(args.output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        with open(output_path / "benchmark-single.json", "w") as f:
            json.dump(
                {
                    "mode": single.mode,
                    "duration": single.total_duration,
                    "workers": single.num_workers,
                    "tests_run": single.tests_run,
                    "tests_passed": single.tests_passed,
                    "tests_failed": single.tests_failed,
                    "timestamp": single.timestamp,
                },
                f,
                indent=2,
            )

        with open(output_path / "benchmark-parallel.json", "w") as f:
            json.dump(
                {
                    "mode": parallel.mode,
                    "duration": parallel.total_duration,
                    "workers": parallel.num_workers,
                    "tests_run": parallel.tests_run,
                    "tests_passed": parallel.tests_passed,
                    "tests_failed": parallel.tests_failed,
                    "timestamp": parallel.timestamp,
                },
                f,
                indent=2,
            )

        return 0

    # Default: run parallel tests
    results = run_tests_parallel(tests, num_workers, args.output_dir)
    print_parallel_summary(results)

    return 0 if results.tests_failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
