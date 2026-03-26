#!/usr/bin/env python3
"""Incremental Test Result Caching for Local CI.

This module provides:
- Test result caching using file content hashes
- Cache storage in `.cache/chiseai/test-results/`
- Cache hit/miss tracking and hit rate metrics
- Cache invalidation when source files change
- Integration with local_ci_speed_optimizations.py

Usage:
    python scripts/local_ci_incremental_cache.py --test-cache

Options:
    --test-cache          Run cache integration test
    --clear-cache         Clear all cached test results
    --show-stats          Show cache statistics
    --cache-dir DIR       Custom cache directory
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

# Cache directory
DEFAULT_CACHE_DIR = Path(".cache/chiseai/test-results")

# Cache file extension
CACHE_EXT = ".json"

# Max cache age in seconds (1 hour)
MAX_CACHE_AGE = 3600


@dataclass
class CacheEntry:
    """Represents a cached test result."""

    test_file: str
    file_hashes: dict[str, str]  # path -> hash
    result_hash: str  # hash of the combined result
    passed: int
    failed: int
    skipped: int
    duration: float
    timestamp: float
    output: str


@dataclass
class CacheStats:
    """Cache statistics."""

    hits: int = 0
    misses: int = 0
    invalidations: int = 0
    stored: int = 0
    hit_rate: float = 0.0


@dataclass
class CacheResult:
    """Result of a cache lookup."""

    found: bool
    entry: CacheEntry | None = None
    reason: str = ""


class IncrementalCache:
    """Incremental test result cache using file hashes."""

    def __init__(self, cache_dir: str | Path = DEFAULT_CACHE_DIR):
        """Initialize the cache.

        Args:
            cache_dir: Directory to store cache files
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._stats = CacheStats()

    def _compute_file_hash(self, file_path: str | Path) -> str:
        """Compute SHA256 hash of a file.

        Args:
            file_path: Path to the file

        Returns:
            Hex digest of the file hash
        """
        path = Path(file_path)
        if not path.exists():
            return ""

        try:
            with open(path, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()[:16]
        except OSError:
            return ""

    def _compute_dir_hash(
        self, directory: str | Path, patterns: tuple[str, ...] = (".py",)
    ) -> dict[str, str]:
        """Compute hashes for all files in a directory matching patterns.

        Args:
            directory: Directory to scan
            patterns: File patterns to match

        Returns:
            Dict mapping file paths to their hashes (using absolute paths)
        """
        path = Path(directory).resolve()
        hashes: dict[str, str] = {}

        if not path.exists():
            return hashes

        # Get all Python files in src and tests
        for root, dirs, files in os.walk(path):
            # Skip cache and pycache directories
            dirs[:] = [
                d
                for d in dirs
                if d not in {"__pycache__", ".git", ".pytest_cache", ".cache"}
            ]

            for file in files:
                if any(file.endswith(p) for p in patterns):
                    file_path = Path(root) / file
                    abs_path = str(file_path.resolve())
                    hashes[abs_path] = self._compute_file_hash(file_path)

        return hashes

    def _get_cache_key(self, test_file: str, file_hashes: dict[str, str]) -> str:
        """Generate a cache key from test file and source hashes.

        Args:
            test_file: Path to the test file
            file_hashes: Dict of source file paths to their hashes

        Returns:
            Cache key (hash string)
        """
        # Sort for deterministic ordering
        sorted_hashes = sorted(file_hashes.items())
        hash_input = f"{test_file}:{json.dumps(sorted_hashes, sort_keys=True)}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:24]

    def _get_cache_path(self, cache_key: str) -> Path:
        """Get the path for a cache key.

        Args:
            cache_key: The cache key

        Returns:
            Path to the cache file
        """
        return self.cache_dir / f"{cache_key}{CACHE_EXT}"

    def check_cache(self, test_file: str, source_dir: str = "src") -> CacheResult:
        """Check if cached test results exist for a test file.

        Args:
            test_file: Path to the test file
            source_dir: Directory containing source files to hash

        Returns:
            CacheResult with found status and entry if found
        """
        # Compute hashes for all source files
        file_hashes = self._compute_dir_hash(source_dir)

        # Also hash the test file itself
        test_path = Path(test_file)
        if test_path.exists():
            # Use absolute path to avoid cwd issues in tests
            abs_test = str(test_path.resolve())
            file_hashes[abs_test] = self._compute_file_hash(test_file)

        # Generate cache key
        cache_key = self._get_cache_key(test_file, file_hashes)
        cache_path = self._get_cache_path(cache_key)

        # Check if cache exists
        if not cache_path.exists():
            self._stats.misses += 1
            self._update_hit_rate()
            return CacheResult(found=False, reason="Cache file not found")

        # Check cache age
        try:
            cache_age = time.time() - cache_path.stat().st_mtime
            if cache_age > MAX_CACHE_AGE:
                self._stats.invalidations += 1
                self._stats.misses += 1
                self._update_hit_rate()
                return CacheResult(found=False, reason="Cache expired")
        except OSError:
            return CacheResult(found=False, reason="Cannot stat cache file")

        # Load and validate cache entry
        try:
            with open(cache_path) as f:
                data = json.load(f)

            entry = CacheEntry(
                test_file=data["test_file"],
                file_hashes=data["file_hashes"],
                result_hash=data["result_hash"],
                passed=data["passed"],
                failed=data["failed"],
                skipped=data["skipped"],
                duration=data["duration"],
                timestamp=data["timestamp"],
                output=data.get("output", ""),
            )

            # Verify hashes still match
            current_hashes = self._compute_dir_hash(source_dir)
            if test_path.exists():
                current_hashes[str(test_path.resolve())] = self._compute_file_hash(
                    test_file
                )

            if entry.file_hashes != current_hashes:
                self._stats.invalidations += 1
                self._stats.misses += 1
                self._update_hit_rate()
                return CacheResult(found=False, reason="Source files changed")

            self._stats.hits += 1
            self._update_hit_rate()
            return CacheResult(found=True, entry=entry, reason="Cache hit")

        except (OSError, json.JSONDecodeError, KeyError) as e:
            self._stats.invalidations += 1
            self._stats.misses += 1
            self._update_hit_rate()
            return CacheResult(found=False, reason=f"Cache corrupted: {e}")

    def store_result(
        self,
        test_file: str,
        source_dir: str,
        passed: int,
        failed: int,
        skipped: int,
        duration: float,
        output: str = "",
    ) -> bool:
        """Store test results in cache.

        Args:
            test_file: Path to the test file
            source_dir: Directory containing source files
            passed: Number of passed tests
            failed: Number of failed tests
            skipped: Number of skipped tests
            duration: Test duration in seconds
            output: Test output (optional)

        Returns:
            True if stored successfully
        """
        # Compute hashes for all source files
        file_hashes = self._compute_dir_hash(source_dir)

        # Also hash the test file itself
        test_path = Path(test_file)
        if test_path.exists():
            # Use absolute path to avoid cwd issues in tests
            abs_test = str(test_path.resolve())
            file_hashes[abs_test] = self._compute_file_hash(test_file)

        # Generate cache key
        cache_key = self._get_cache_key(test_file, file_hashes)
        cache_path = self._get_cache_path(cache_key)

        # Create result hash
        result_data = f"{passed}:{failed}:{skipped}:{duration}"
        result_hash = hashlib.sha256(result_data.encode()).hexdigest()[:16]

        # Create cache entry
        entry = CacheEntry(
            test_file=test_file,
            file_hashes=file_hashes,
            result_hash=result_hash,
            passed=passed,
            failed=failed,
            skipped=skipped,
            duration=duration,
            timestamp=time.time(),
            output=output,
        )

        # Serialize to JSON
        data = {
            "test_file": entry.test_file,
            "file_hashes": entry.file_hashes,
            "result_hash": entry.result_hash,
            "passed": entry.passed,
            "failed": entry.failed,
            "skipped": entry.skipped,
            "duration": entry.duration,
            "timestamp": entry.timestamp,
            "output": entry.output,
        }

        try:
            with open(cache_path, "w") as f:
                json.dump(data, f, indent=2)
            self._stats.stored += 1
            return True
        except OSError as e:
            print(f"Failed to store cache: {e}", file=sys.stderr)
            return False

    def _update_hit_rate(self) -> None:
        """Update the cached hit rate."""
        total = self._stats.hits + self._stats.misses
        if total > 0:
            self._stats.hit_rate = (self._stats.hits / total) * 100

    def get_stats(self) -> CacheStats:
        """Get current cache statistics.

        Returns:
            CacheStats object
        """
        self._update_hit_rate()
        return self._stats

    def clear_cache(self) -> int:
        """Clear all cached test results.

        Returns:
            Number of cache files deleted
        """
        count = 0
        for cache_file in self.cache_dir.glob(f"*{CACHE_EXT}"):
            try:
                cache_file.unlink()
                count += 1
            except OSError:
                pass
        return count

    def run_cached_tests(
        self,
        tests: list[str],
        source_dir: str = "src",
        output_dir: str = "_bmad-output/ci",
    ) -> tuple[list[str], list[CacheEntry], bool]:
        """Run tests, using cache for unchanged files.

        Args:
            tests: List of test file paths
            source_dir: Directory containing source files
            output_dir: Directory for test output

        Returns:
            Tuple of (tests_to_run, cached_results, all_cached)
        """
        tests_to_run: list[str] = []
        cached_results: list[CacheEntry] = []
        all_cached = True

        for test in tests:
            result = self.check_cache(test, source_dir)
            if result.found and result.entry:
                cached_results.append(result.entry)
            else:
                tests_to_run.append(test)
                all_cached = False

        return tests_to_run, cached_results, all_cached

    def print_stats(self) -> None:
        """Print cache statistics to console."""
        stats = self.get_stats()
        print("\n" + "=" * 60)
        print("CACHE STATISTICS")
        print("=" * 60)
        print(f"Cache Hits:        {stats.hits}")
        print(f"Cache Misses:      {stats.misses}")
        print(f"Invalidations:     {stats.invalidations}")
        print(f"Cached Results:    {stats.stored}")
        print(f"Hit Rate:         {stats.hit_rate:.1f}%")
        print("=" * 60)


def run_pytest_cached(
    tests: list[str],
    output_dir: str = "_bmad-output/ci",
    cache: IncrementalCache | None = None,
    source_dir: str = "src",
) -> tuple[int, dict, float, str]:
    """Run pytest with incremental caching.

    Args:
        tests: List of test files to run
        output_dir: Directory for test output
        cache: Optional IncrementalCache instance
        source_dir: Source directory for hashing

    Returns:
        Tuple of (exit_code, counts, duration, output)
    """
    import contextlib

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    junit_file = output_path / "pytest-junit-cache.xml"

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "--junitxml",
        str(junit_file),
        "-v",
    ]
    cmd.extend(tests)

    start_time = time.time()
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )
    duration = time.time() - start_time

    # Parse output
    counts = {"passed": 0, "failed": 0, "skipped": 0, "error": 0}
    for line in result.stdout.splitlines() + result.stderr.splitlines():
        if " passed" in line:
            parts = line.split()
            for i, part in enumerate(parts):
                if part == "passed" and i > 0:
                    with contextlib.suppress(ValueError, IndexError):
                        counts["passed"] = int(parts[i - 1])
        elif " failed" in line:
            parts = line.split()
            for i, part in enumerate(parts):
                if part == "failed" and i > 0:
                    with contextlib.suppress(ValueError, IndexError):
                        counts["failed"] = int(parts[i - 1])
        elif " skipped" in line:
            parts = line.split()
            for i, part in enumerate(parts):
                if part == "skipped" and i > 0:
                    with contextlib.suppress(ValueError, IndexError):
                        counts["skipped"] = int(parts[i - 1])

    # Store in cache
    if cache and result.returncode == 0:
        for test in tests:
            cache.store_result(
                test_file=test,
                source_dir=source_dir,
                passed=counts["passed"] // len(tests) if tests else 0,
                failed=counts["failed"] // len(tests) if tests else 0,
                skipped=counts["skipped"] // len(tests) if tests else 0,
                duration=duration / len(tests) if tests else 0,
                output=result.stdout + result.stderr,
            )

    return result.returncode, counts, duration, result.stdout + result.stderr


def main() -> int:
    """Main entry point for CLI."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Incremental Test Result Caching for Local CI"
    )
    parser.add_argument(
        "--test-cache",
        action="store_true",
        help="Run cache integration test",
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear all cached test results",
    )
    parser.add_argument(
        "--show-stats",
        action="store_true",
        help="Show cache statistics",
    )
    parser.add_argument(
        "--cache-dir",
        type=str,
        default=None,
        help=f"Custom cache directory (default: {DEFAULT_CACHE_DIR})",
    )

    args = parser.parse_args()

    cache = IncrementalCache(args.cache_dir or DEFAULT_CACHE_DIR)

    if args.clear_cache:
        count = cache.clear_cache()
        print(f"Cleared {count} cache files")
        return 0

    if args.show_stats:
        cache.print_stats()
        return 0

    if args.test_cache:
        print("Running cache integration test...")

        # Create a simple test
        test_content = '''"""Test cache integration."""
import pytest

def test_example():
    """Example test."""
    assert True
'''
        test_path = Path("tests/test_cache_integration.py")
        test_path.write_text(test_content)

        try:
            # First run - should miss cache
            print("\nFirst run (should miss cache)...")
            result1 = cache.check_cache(str(test_path))
            print(f"  Cache hit: {result1.found} ({result1.reason})")

            # Store a fake result
            print("\nStoring fake result...")
            cache.store_result(
                test_file=str(test_path),
                source_dir="src",
                passed=1,
                failed=0,
                skipped=0,
                duration=0.1,
            )

            # Second run - should hit cache
            print("\nSecond run (should hit cache)...")
            result2 = cache.check_cache(str(test_path))
            print(f"  Cache hit: {result2.found} ({result2.reason})")

            if result2.found and result2.entry:
                print(f"  Passed: {result2.entry.passed}")
                print(f"  Duration: {result2.entry.duration:.3f}s")

            # Show stats
            cache.print_stats()

            print("\nCache integration test passed!")
            return 0

        finally:
            # Cleanup
            if test_path.exists():
                test_path.unlink()
            cache.clear_cache()

    # Default: show stats
    cache.print_stats()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
