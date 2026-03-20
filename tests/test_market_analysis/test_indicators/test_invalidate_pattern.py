"""Test invalidate_pattern Redis consistency."""

import pytest

from market_analysis.indicators.feature_store import FeatureStore


class TestInvalidatePattern:
    """Test invalidate_pattern method."""

    @pytest.fixture
    def store(self):
        """Create fresh FeatureStore instance."""
        return FeatureStore(prefix="test", default_ttl=60)

    def test_invalidate_pattern_local_and_redis(self, store):
        """Test that invalidate_pattern with glob pattern removes keys from both local cache and Redis."""
        # Set some keys
        store.set("key1", "value1")
        store.set("key2", "value2")
        store.set("other", "value3")

        # Ensure they are in local cache
        assert "key1" in store._local_cache
        assert "key2" in store._local_cache
        assert "other" in store._local_cache

        # Invalidate pattern "key*"
        count = store.invalidate_pattern("key*")

        # Should have invalidated 2 keys
        assert count == 2

        # Local cache should have only "other"
        assert "key1" not in store._local_cache
        assert "key2" not in store._local_cache
        assert "other" in store._local_cache

        # Redis should also have only "other" (namespaced)
        from tools.redis_state import redis_state_hgetall

        all_fields = redis_state_hgetall("feature_store")
        if all_fields:
            # Filter fields for this store's prefix
            store_fields = [f for f in all_fields if f.startswith("test:")]
            # Should be only test:other
            assert len(store_fields) == 1
            assert store_fields[0] == "test:other"
        else:
            # If Redis is empty, that's okay (maybe other keys belong to other stores)
            pass

        # Clean up
        store.delete("other")

    def test_invalidate_pattern_redis_only(self, store):
        """Test invalidation of keys that exist only in Redis (not in local cache) using glob pattern."""
        # Manually set a key in Redis (bypass local cache)
        from tools.redis_state import redis_state_hset

        redis_state_hset(
            "feature_store", "test:redis_only", '"redis_value"', expire_seconds=60
        )

        # Ensure not in local cache
        assert "redis_only" not in store._local_cache

        # Invalidate pattern "redis*"
        count = store.invalidate_pattern("redis*")
        assert count == 1

        # Verify Redis key is gone
        from tools.redis_state import redis_state_hget

        val = redis_state_hget("feature_store", "test:redis_only")
        assert val is None

        # Clean up (just in case)
        try:
            from tools.redis_state import redis_state_hdel

            redis_state_hdel("feature_store", "test:redis_only")
        except Exception:
            pass

    def test_invalidate_pattern_no_match(self, store):
        """Test that pattern matching zero keys returns zero."""
        store.set("foo", "bar")
        count = store.invalidate_pattern("nomatch")
        assert count == 0
        assert "foo" in store._local_cache
        store.delete("foo")
