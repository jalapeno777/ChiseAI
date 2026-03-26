"""Test incremental caching functionality.

Tests the local_ci_incremental_cache module.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

# Add scripts to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from local_ci_incremental_cache import (
    CACHE_EXT,
    CacheEntry,
    CacheResult,
    IncrementalCache,
)


class TestIncrementalCache:
    """Test cases for IncrementalCache."""

    @pytest.fixture
    def temp_cache_dir(self, tmp_path):
        """Create a temporary cache directory."""
        cache_dir = tmp_path / "test_cache"
        cache_dir.mkdir()
        return cache_dir

    @pytest.fixture
    def temp_source_dir(self, tmp_path):
        """Create a temporary source directory with test files."""
        source_dir = tmp_path / "src"
        source_dir.mkdir()

        # Create some Python files
        (source_dir / "module1.py").write_text("""def func1():
    return 1
""")
        (source_dir / "module2.py").write_text("""def func2():
    return 2
""")

        return source_dir

    def test_cache_initialization(self, temp_cache_dir):
        """Test cache initializes correctly."""
        cache = IncrementalCache(cache_dir=temp_cache_dir)
        assert cache.cache_dir == temp_cache_dir
        assert temp_cache_dir.exists()

    def test_compute_file_hash(self, temp_source_dir, temp_cache_dir):
        """Test file hash computation."""
        cache = IncrementalCache(cache_dir=temp_cache_dir)
        file_path = temp_source_dir / "module1.py"
        hash1 = cache._compute_file_hash(file_path)
        hash2 = cache._compute_file_hash(file_path)

        # Same file should produce same hash
        assert hash1 == hash2
        # Hash should be 16 characters (truncated SHA256)
        assert len(hash1) == 16

    def test_compute_file_hash_nonexistent(self, temp_cache_dir):
        """Test hash computation for nonexistent file."""
        cache = IncrementalCache(cache_dir=temp_cache_dir)
        hash_val = cache._compute_file_hash("/nonexistent/path.py")
        assert hash_val == ""

    def test_compute_dir_hash(self, temp_source_dir, temp_cache_dir):
        """Test directory hash computation."""
        cache = IncrementalCache(cache_dir=temp_cache_dir)
        hashes = cache._compute_dir_hash(temp_source_dir)

        # Hashes use absolute paths
        assert any("module1.py" in k for k in hashes)
        assert any("module2.py" in k for k in hashes)
        # All values should be 16 char hashes
        for v in hashes.values():
            assert len(v) == 16

    def test_compute_dir_hash_excludes_cache_dirs(
        self, temp_source_dir, temp_cache_dir
    ):
        """Test that cache dirs are excluded from hashing."""
        cache = IncrementalCache(cache_dir=temp_cache_dir)

        # Create cache-like directories
        (temp_source_dir / "__pycache__").mkdir()
        (temp_source_dir / ".cache").mkdir()
        (temp_source_dir / ".git").mkdir()

        hashes = cache._compute_dir_hash(temp_source_dir)

        # Cache directories should not be included
        assert "__pycache__" not in hashes
        assert ".cache" not in hashes
        assert ".git" not in hashes

    def test_get_cache_key(self, temp_cache_dir):
        """Test cache key generation."""
        cache = IncrementalCache(cache_dir=temp_cache_dir)
        key1 = cache._get_cache_key("test_file.py", {"src/a.py": "hash1"})
        key2 = cache._get_cache_key("test_file.py", {"src/a.py": "hash1"})
        key3 = cache._get_cache_key("test_file.py", {"src/b.py": "hash2"})

        # Same inputs should produce same key
        assert key1 == key2
        # Different inputs should produce different key
        assert key1 != key3
        # Key should be 24 characters
        assert len(key1) == 24

    def test_cache_key_deterministic(self, temp_cache_dir):
        """Test cache key is deterministic regardless of dict order."""
        cache = IncrementalCache(cache_dir=temp_cache_dir)

        key1 = cache._get_cache_key(
            "test.py",
            {"z.py": "hash_z", "a.py": "hash_a", "m.py": "hash_m"},
        )
        key2 = cache._get_cache_key(
            "test.py",
            {"a.py": "hash_a", "m.py": "hash_m", "z.py": "hash_z"},
        )

        assert key1 == key2

    def test_check_cache_miss(self, temp_source_dir, temp_cache_dir):
        """Test cache miss when no cache exists."""
        cache = IncrementalCache(cache_dir=temp_cache_dir)
        test_file = temp_source_dir / "module1.py"

        result = cache.check_cache(str(test_file), str(temp_source_dir))

        assert result.found is False
        assert (
            "not found" in result.reason.lower() or "not exist" in result.reason.lower()
        )

    def test_store_and_check_cache(self, temp_source_dir, temp_cache_dir):
        """Test storing and retrieving cached results."""
        cache = IncrementalCache(cache_dir=temp_cache_dir)
        test_file = temp_source_dir / "module1.py"

        # Store a result
        success = cache.store_result(
            test_file=str(test_file),
            source_dir=str(temp_source_dir),
            passed=5,
            failed=1,
            skipped=2,
            duration=1.5,
        )
        assert success is True

        # Check cache
        result = cache.check_cache(str(test_file), str(temp_source_dir))

        assert result.found is True
        assert result.entry is not None
        assert result.entry.passed == 5
        assert result.entry.failed == 1
        assert result.entry.skipped == 2
        assert result.entry.duration == 1.5

    def test_cache_invalidation_on_source_change(self, temp_source_dir, temp_cache_dir):
        """Test cache invalidates when source files change."""
        cache = IncrementalCache(cache_dir=temp_cache_dir)
        test_file = temp_source_dir / "module1.py"

        # Store initial result
        cache.store_result(
            test_file=str(test_file),
            source_dir=str(temp_source_dir),
            passed=5,
            failed=0,
            skipped=0,
            duration=1.0,
        )

        # Modify source file
        time.sleep(0.1)  # Ensure different mtime
        (temp_source_dir / "module2.py").write_text("""def func2():
    return 42  # changed
""")

        # Check cache - should miss because modifying ANY source file
        # changes the cache key (since all source file hashes are combined)
        result = cache.check_cache(str(test_file), str(temp_source_dir))

        # The cache should miss - either because source changed or cache key changed
        assert result.found is False
        assert result.reason is not None

    def test_cache_expiry(self, temp_source_dir, temp_cache_dir):
        """Test cache expires after max age."""
        cache = IncrementalCache(cache_dir=temp_cache_dir)
        test_file = temp_source_dir / "module1.py"

        # Store a result
        cache.store_result(
            test_file=str(test_file),
            source_dir=str(temp_source_dir),
            passed=5,
            failed=0,
            skipped=0,
            duration=1.0,
        )

        # Simulate old cache by modifying mtime
        cache_path = list(cache.cache_dir.glob(f"*{CACHE_EXT}"))[0]
        old_time = time.time() - 7200  # 2 hours ago
        os.utime(cache_path, (old_time, old_time))

        # Check cache - should miss due to expiry
        result = cache.check_cache(str(test_file), str(temp_source_dir))

        assert result.found is False
        assert "expired" in result.reason.lower()

    def test_clear_cache(self, temp_source_dir, temp_cache_dir):
        """Test clearing cache files."""
        cache = IncrementalCache(cache_dir=temp_cache_dir)
        test_file = temp_source_dir / "module1.py"

        # Store multiple results
        cache.store_result(
            test_file=str(test_file),
            source_dir=str(temp_source_dir),
            passed=5,
            failed=0,
            skipped=0,
            duration=1.0,
        )
        cache.store_result(
            test_file=str(test_file),
            source_dir=str(temp_source_dir),
            passed=10,
            failed=0,
            skipped=0,
            duration=2.0,
        )

        # Verify files exist
        assert len(list(cache.cache_dir.glob(f"*{CACHE_EXT}"))) >= 1

        # Clear cache
        count = cache.clear_cache()

        assert count >= 1
        assert len(list(cache.cache_dir.glob(f"*{CACHE_EXT}"))) == 0

    def test_get_stats(self, temp_source_dir, temp_cache_dir):
        """Test cache statistics tracking."""
        cache = IncrementalCache(cache_dir=temp_cache_dir)
        test_file = temp_source_dir / "module1.py"

        # Generate some cache hits and misses
        cache.check_cache(str(test_file), str(temp_source_dir))  # miss
        cache.check_cache(str(test_file), str(temp_source_dir))  # miss

        cache.store_result(
            test_file=str(test_file),
            source_dir=str(temp_source_dir),
            passed=5,
            failed=0,
            skipped=0,
            duration=1.0,
        )

        cache.check_cache(str(test_file), str(temp_source_dir))  # hit

        stats = cache.get_stats()

        assert stats.hits == 1
        assert stats.misses == 2
        assert stats.stored >= 1
        assert 0 <= stats.hit_rate <= 100

    def test_cache_result_dataclass(self):
        """Test CacheResult dataclass."""
        entry = CacheEntry(
            test_file="test.py",
            file_hashes={"src/a.py": "hash1"},
            result_hash="result_hash",
            passed=5,
            failed=1,
            skipped=2,
            duration=1.5,
            timestamp=1234567890.0,
            output="test output",
        )

        result = CacheResult(found=True, entry=entry, reason="Cache hit")

        assert result.found is True
        assert result.entry is not None
        assert result.entry.passed == 5
        assert result.reason == "Cache hit"

    def test_cache_result_not_found(self):
        """Test CacheResult when cache not found."""
        result = CacheResult(found=False, reason="Cache not found")

        assert result.found is False
        assert result.entry is None
        assert result.reason == "Cache not found"

    def test_run_cached_tests_mixed(self, temp_source_dir, temp_cache_dir):
        """Test running cached tests with mixed hit/miss."""
        cache = IncrementalCache(cache_dir=temp_cache_dir)
        test_file1 = temp_source_dir / "module1.py"
        test_file2 = temp_source_dir / "module2.py"

        # Store result for only one test
        cache.store_result(
            test_file=str(test_file1),
            source_dir=str(temp_source_dir),
            passed=5,
            failed=0,
            skipped=0,
            duration=1.0,
        )

        # Run cached tests
        tests = [str(test_file1), str(test_file2)]
        to_run, cached, all_cached = cache.run_cached_tests(tests, str(temp_source_dir))

        assert len(to_run) == 1
        assert str(test_file2) in to_run
        assert len(cached) == 1
        assert all_cached is False

    def test_run_cached_tests_all_cached(self, temp_source_dir, temp_cache_dir):
        """Test running when all tests are cached."""
        cache = IncrementalCache(cache_dir=temp_cache_dir)
        test_file = temp_source_dir / "module1.py"

        # Store result
        cache.store_result(
            test_file=str(test_file),
            source_dir=str(temp_source_dir),
            passed=5,
            failed=0,
            skipped=0,
            duration=1.0,
        )

        # Run cached tests
        tests = [str(test_file)]
        to_run, cached, all_cached = cache.run_cached_tests(tests, str(temp_source_dir))

        assert len(to_run) == 0
        assert len(cached) == 1
        assert all_cached is True


class TestCacheIntegration:
    """Integration tests for cache with pytest execution."""

    def test_store_result_with_output(self, tmp_path):
        """Test storing result with output."""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()

        source_dir = tmp_path / "src"
        source_dir.mkdir()
        (source_dir / "test.py").write_text("def foo(): pass")

        cache = IncrementalCache(cache_dir=cache_dir)

        success = cache.store_result(
            test_file="test_file.py",
            source_dir=str(source_dir),
            passed=3,
            failed=0,
            skipped=1,
            duration=0.5,
            output="some test output",
        )

        assert success is True

        # Verify stored data
        cache_files = list(cache_dir.glob(f"*{CACHE_EXT}"))
        assert len(cache_files) == 1

        with open(cache_files[0]) as f:
            data = json.load(f)

        assert data["passed"] == 3
        assert data["skipped"] == 1
        assert data["output"] == "some test output"
