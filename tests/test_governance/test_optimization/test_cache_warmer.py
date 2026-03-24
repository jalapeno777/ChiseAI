"""
Tests for the CacheWarmer class.

ST-GOV-MINI-002: Optimization Feedback Loop

Covers initialization, cache warming return structure, and key counting.
"""

from src.governance.optimization.cache_warmer import CacheWarmer


class TestCacheWarmerInit:
    """Verify CacheWarmer initializes correctly."""

    def test_cache_warmer_initialization(self):
        warmer = CacheWarmer()
        assert hasattr(warmer, "warmed_keys"), "CacheWarmer must have 'warmed_keys'"
        assert warmer.warmed_keys == [], "warmed_keys should start as an empty list"


class TestWarmCacheReturn:
    """Verify warm_cache() return structure."""

    def test_warm_cache_returns_dict(self):
        warmer = CacheWarmer()
        result = warmer.warm_cache()

        assert isinstance(result, dict), "warm_cache() must return a dict"
        for key in ("patterns_warmed", "keys_warmed", "duration_ms"):
            assert key in result, f"Result dict missing key: {key}"

        assert isinstance(result["patterns_warmed"], int)
        assert isinstance(result["keys_warmed"], int)
        assert isinstance(result["duration_ms"], (int, float))

        assert result["patterns_warmed"] == len(
            CacheWarmer.TOP_PATTERNS
        ), "patterns_warmed should equal the number of TOP_PATTERNS"


class TestWarmCacheIncrementsKeysWarmed:
    """Verify keys_warmed count increases after warming."""

    def test_warm_cache_increments_keys_warmed(self):
        warmer = CacheWarmer()

        # Before warming
        assert len(warmer.warmed_keys) == 0

        result = warmer.warm_cache()

        # After warming, warmed_keys list should have grown
        assert (
            len(warmer.warmed_keys) > 0
        ), "warmed_keys should be non-empty after warm_cache()"
        assert result["keys_warmed"] == len(
            warmer.warmed_keys
        ), "Result keys_warmed should match len(warmer.warmed_keys)"

    def test_warm_cache_idempotent_accumulates(self):
        """Calling warm_cache() twice should accumulate keys in warmed_keys list."""
        warmer = CacheWarmer()
        warmer.warm_cache()
        first_count = len(warmer.warmed_keys)

        warmer.warm_cache()
        second_count = len(warmer.warmed_keys)

        assert (
            second_count > first_count
        ), "warmed_keys list should grow with each warm_cache() call"
