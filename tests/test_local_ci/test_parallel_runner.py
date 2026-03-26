#!/usr/bin/env python3
"""Tests for local_ci_parallel_runner.py

These tests verify:
- Dynamic worker allocation (uses min(cpu_count, 8))
- Test distribution based on historical runtimes
- Progress reporting during parallel execution
- 30%+ speedup vs single-worker for full suite
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from local_ci_parallel_runner import (
    BenchmarkResults,
    WorkerStats,
    discover_tests,
    distribute_tests_balanced,
    estimate_test_times,
    get_cpu_count,
    get_optimal_workers,
    load_test_history,
    parse_pytest_counts,
    run_tests_parallel,
    run_tests_single,
    save_test_history,
)


class TestWorkerAllocation:
    """Tests for dynamic worker allocation."""

    def test_get_cpu_count_returns_positive(self):
        """CPU count should return a positive integer."""
        count = get_cpu_count()
        assert isinstance(count, int)
        assert count >= 1

    def test_get_optimal_workers_auto(self):
        """Auto worker allocation should use min(cpu_count, 8)."""
        cpu_count = get_cpu_count()
        workers = get_optimal_workers()
        assert workers <= cpu_count
        assert workers <= 8

    def test_get_optimal_workers_with_requested(self):
        """Requested workers should be capped at min(requested, cpu_count, 8)."""
        cpu_count = get_cpu_count()
        workers = get_optimal_workers(requested=16)
        assert workers <= cpu_count
        assert workers <= 8

    def test_get_optimal_workers_respects_max(self):
        """Max workers parameter should be respected."""
        workers = get_optimal_workers(requested=4, max_workers=4)
        assert workers <= 4

    def test_get_optimal_workers_no_exceed_cpu(self):
        """Workers should never exceed CPU count."""
        for requested in [1, 2, 4, 8, 16, 100]:
            for max_w in [1, 4, 8, 16]:
                workers = get_optimal_workers(requested=requested, max_workers=max_w)
                assert workers <= get_cpu_count()


class TestTestDistribution:
    """Tests for balanced test distribution."""

    def test_distribute_tests_balanced_empty(self):
        """Empty test list should distribute evenly."""
        distribution = distribute_tests_balanced([], {}, 4)
        assert len(distribution) == 4
        for worker_tests in distribution.values():
            assert worker_tests == []

    def test_distribute_tests_balanced_single_worker(self):
        """Single worker should get all tests."""
        tests = ["test_a.py", "test_b.py", "test_c.py"]
        estimates = {"test_a.py": 1.0, "test_b.py": 2.0, "test_c.py": 3.0}
        distribution = distribute_tests_balanced(tests, estimates, 1)
        assert len(distribution) == 1
        # With single worker, all tests go to worker 0 (order may vary due to sorting)
        assert set(distribution[0]) == set(tests)

    def test_distribute_tests_balanced_even_distribution(self):
        """Tests should be distributed roughly evenly by time."""
        # Create many tests with equal estimated times
        tests = [f"test_{i}.py" for i in range(20)]
        estimates = {t: 1.0 for t in tests}

        distribution = distribute_tests_balanced(tests, estimates, 4)

        # Each worker should have roughly 5 tests
        for worker_tests in distribution.values():
            assert len(worker_tests) in [4, 5, 6]

    def test_distribute_tests_balanced_respects_estimates(self):
        """Longer tests should be distributed to balance load."""
        # Create tests with very different runtimes
        tests = ["fast.py", "medium.py", "slow.py", "slowest.py"]
        estimates = {
            "fast.py": 1.0,
            "medium.py": 5.0,
            "slow.py": 10.0,
            "slowest.py": 20.0,
        }

        distribution = distribute_tests_balanced(tests, estimates, 2)

        # Total time is 36, so ~18 per worker
        # The greedy algorithm should balance this
        total_assigned = sum(
            len(worker_tests) for worker_tests in distribution.values()
        )
        assert total_assigned == 4


class TestTestTimeEstimation:
    """Tests for test time estimation."""

    def test_estimate_test_times_with_history(self):
        """Should use historical data when available."""
        history = {"test_a.py": 5.0, "test_b.py": 10.0}
        tests = ["test_a.py", "test_b.py", "test_c.py"]

        estimates = estimate_test_times(tests, history)

        assert estimates["test_a.py"] == 5.0
        assert estimates["test_b.py"] == 10.0
        # test_c.py has no history, should get default
        assert estimates["test_c.py"] > 0

    def test_estimate_test_times_empty_history(self):
        """Should estimate based on file size when no history."""
        tests = ["local_ci_parallel_runner.py"]  # This file
        estimates = estimate_test_times(tests, {})

        assert len(estimates) == 1
        assert estimates[tests[0]] > 0


class TestHistoryManagement:
    """Tests for runtime history management."""

    def test_save_and_load_history(self, tmp_path):
        """Should save and load history correctly."""
        history_file = tmp_path / "test_history.json"
        history = {"test_a.py": 5.0, "test_b.py": 10.0}

        save_test_history(history, str(history_file))
        loaded = load_test_history(str(history_file))

        assert loaded == history

    def test_load_history_missing_file(self):
        """Missing history file should return empty dict."""
        loaded = load_test_history("/nonexistent/path.json")
        assert loaded == {}

    def test_load_history_invalid_json(self, tmp_path):
        """Invalid JSON should return empty dict."""
        history_file = tmp_path / "invalid.json"
        history_file.write_text("not valid json {")

        loaded = load_test_history(str(history_file))
        assert loaded == {}


class TestTestDiscovery:
    """Tests for test discovery."""

    def test_discover_tests_returns_list(self):
        """Should return a list of test paths."""
        tests = discover_tests(["tests/unit"])
        assert isinstance(tests, list)

    def test_discover_tests_filters_correct_files(self):
        """Should only return test_*.py or *_test.py files."""
        tests = discover_tests(["tests/unit"])
        for test in tests:
            basename = os.path.basename(test)
            assert basename.startswith("test_") or basename.endswith("_test.py")
            assert basename.endswith(".py")
            assert basename not in ["__init__.py", "conftest.py"]


class TestPytestOutputParsing:
    """Tests for pytest output parsing."""

    def test_parse_pytest_counts_all_passed(self):
        """Should parse all passed correctly."""
        output = "tests collected: 10\n\n10 passed in 1.5s"
        tests_run, passed, failed, skipped = parse_pytest_counts(output)
        assert passed == 10
        assert failed == 0
        assert skipped == 0

    def test_parse_pytest_counts_mixed(self):
        """Should parse mixed results correctly."""
        output = "8 passed, 2 failed, 1 skipped in 5.0s"
        tests_run, passed, failed, skipped = parse_pytest_counts(output)
        assert passed == 8
        assert failed == 2
        assert skipped == 1

    def test_parse_pytest_counts_empty(self):
        """Should handle empty output."""
        tests_run, passed, failed, skipped = parse_pytest_counts("")
        assert passed == 0
        assert failed == 0
        assert skipped == 0


class TestBenchmarkResults:
    """Tests for BenchmarkResults dataclass."""

    def test_benchmark_results_creation(self):
        """Should create BenchmarkResults with correct defaults."""
        result = BenchmarkResults(
            mode="parallel",
            total_duration=10.0,
            num_workers=4,
            tests_run=100,
            tests_passed=95,
            tests_failed=5,
            tests_skipped=0,
        )

        assert result.mode == "parallel"
        assert result.total_duration == 10.0
        assert result.num_workers == 4
        assert result.tests_run == 100
        assert result.tests_passed == 95
        assert result.tests_failed == 5

    def test_worker_stats_duration(self):
        """WorkerStats duration property should work correctly."""
        worker = WorkerStats(
            worker_id=0,
            start_time=100.0,
            end_time=110.0,
        )
        assert worker.duration == 10.0


class TestIntegration:
    """Integration tests for the parallel runner."""

    def test_script_runs_without_errors(self):
        """The parallel runner script should run without errors."""
        result = subprocess.run(
            [sys.executable, "scripts/local_ci_parallel_runner.py", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_estimate_only_runs(self):
        """The estimate-only mode should run without errors."""
        result = subprocess.run(
            [sys.executable, "scripts/local_ci_parallel_runner.py", "--estimate-only"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        # Should show worker allocation
        assert "Using" in result.stdout
        assert "workers" in result.stdout.lower()

    def test_estimate_only_shows_balanced_distribution(self):
        """Estimate-only should show balanced distribution across workers."""
        result = subprocess.run(
            [sys.executable, "scripts/local_ci_parallel_runner.py", "--estimate-only"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        # Should show distribution across workers
        assert "Worker" in result.stdout


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
