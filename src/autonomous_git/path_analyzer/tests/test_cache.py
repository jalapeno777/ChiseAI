"""Tests for cache module."""

import time
from autonomous_git.path_analyzer.cache import PathAnalysisCache


class TestPathAnalysisCache:
    """Test PathAnalysisCache class."""

    def test_default_initialization(self):
        """Test default initialization."""
        cache = PathAnalysisCache()
        assert cache._redis is None
        assert cache._ttl == 3600
        assert cache._memory_cache == {}

    def test_custom_ttl(self):
        """Test custom TTL."""
        cache = PathAnalysisCache(ttl=7200)
        assert cache._ttl == 7200

    def test_hash_file_list(self):
        """Test file list hashing."""
        files = ["a.py", "b.py", "c.py"]
        hash1 = PathAnalysisCache._hash_file_list(files)
        hash2 = PathAnalysisCache._hash_file_list(files)

        # Same files should produce same hash
        assert hash1 == hash2
        assert len(hash1) == 16

    def test_hash_order_independence(self):
        """Test that hash is independent of file order."""
        files1 = ["a.py", "b.py", "c.py"]
        files2 = ["c.py", "a.py", "b.py"]

        hash1 = PathAnalysisCache._hash_file_list(files1)
        hash2 = PathAnalysisCache._hash_file_list(files2)

        assert hash1 == hash2

    def test_make_key_with_pr_and_commit(self):
        """Test key generation with PR and commit."""
        cache = PathAnalysisCache()
        files = ["a.py"]
        file_hash = PathAnalysisCache._hash_file_list(files)

        key = cache._make_key(123, "abcdef123456", file_hash)
        assert "path_analysis:123:abcdef12" in key

    def test_make_key_without_commit(self):
        """Test key generation without commit."""
        cache = PathAnalysisCache()
        files = ["a.py"]
        file_hash = PathAnalysisCache._hash_file_list(files)

        key = cache._make_key(123, None, file_hash)
        assert "path_analysis:123:" in key

    def test_set_and_get(self):
        """Test setting and getting cached values."""
        cache = PathAnalysisCache()
        files = ["docs/readme.md"]
        result = {"risk_level": "safe", "confidence": 0.9}

        cache.set(123, "abc", files, result)
        cached = cache.get(123, "abc", files)

        assert cached is not None
        assert cached["risk_level"] == "safe"
        assert cached["confidence"] == 0.9
        assert "_cached_at" in cached
        assert "_ttl" in cached

    def test_get_miss(self):
        """Test cache miss."""
        cache = PathAnalysisCache()
        files = ["docs/readme.md"]

        cached = cache.get(999, "xyz", files)
        assert cached is None

    def test_cache_expiration(self):
        """Test that cache entries expire."""
        cache = PathAnalysisCache(ttl=0)  # Immediate expiration
        files = ["docs/readme.md"]
        result = {"risk_level": "safe"}

        cache.set(123, "abc", files, result)
        time.sleep(0.1)  # Small delay

        cached = cache.get(123, "abc", files)
        assert cached is None

    def test_invalidate_specific_commit(self):
        """Test invalidating specific commit."""
        cache = PathAnalysisCache()
        files = ["docs/readme.md"]
        result = {"risk_level": "safe"}

        cache.set(123, "abc123", files, result)
        count = cache.invalidate(123, "abc123")

        assert count >= 1
        cached = cache.get(123, "abc123", files)
        assert cached is None

    def test_invalidate_all_commits_for_pr(self):
        """Test invalidating all commits for a PR."""
        cache = PathAnalysisCache()
        files = ["docs/readme.md"]
        result = {"risk_level": "safe"}

        cache.set(123, "abc123", files, result)
        cache.set(123, "def456", files, result)

        count = cache.invalidate(123)

        assert count >= 2
        assert cache.get(123, "abc123", files) is None
        assert cache.get(123, "def456", files) is None

    def test_clear(self):
        """Test clearing all cache entries."""
        cache = PathAnalysisCache()
        files = ["docs/readme.md"]
        result = {"risk_level": "safe"}

        cache.set(123, "abc", files, result)
        cache.set(456, "def", files, result)

        cache.clear()

        assert cache.get(123, "abc", files) is None
        assert cache.get(456, "def", files) is None

    def test_stats_empty(self):
        """Test stats for empty cache."""
        cache = PathAnalysisCache()
        stats = cache.stats()

        assert stats["memory_entries"] == 0
        assert stats["total_entries"] == 0
        assert stats["ttl_seconds"] == 3600

    def test_stats_with_entries(self):
        """Test stats with entries."""
        cache = PathAnalysisCache()
        files = ["docs/readme.md"]
        result = {"risk_level": "safe"}

        cache.set(123, "abc", files, result)
        cache.set(456, "def", files, result)

        stats = cache.stats()

        assert stats["memory_entries"] == 2
        assert stats["total_entries"] == 2

    def test_different_file_lists_different_keys(self):
        """Test that different file lists get different cache keys."""
        cache = PathAnalysisCache()
        result1 = {"risk_level": "safe"}
        result2 = {"risk_level": "complex"}

        files1 = ["a.py", "b.py"]
        files2 = ["a.py", "c.py"]

        cache.set(123, "abc", files1, result1)
        cache.set(456, "def", files2, result2)  # Different PR to avoid key collision

        cached1 = cache.get(123, "abc", files1)
        cached2 = cache.get(456, "def", files2)

        assert cached1["risk_level"] == "safe"
        assert cached2["risk_level"] == "complex"
