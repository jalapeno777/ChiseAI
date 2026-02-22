"""Performance benchmarks for query result caching."""

from __future__ import annotations

import time

from api.cache.cache_manager import QueryCacheManager
from api.cache.strategies import CacheStrategy, QueryType


class TestCachePerformance:
    """Performance benchmarks for cache operations."""

    def test_cache_hit_performance(self):
        """Benchmark cache hit performance."""
        manager = QueryCacheManager(enable_memory_fallback=True)

        # Pre-populate cache
        test_data = {"result": "test" * 1000}  # 4KB of data
        manager.set("test_key", test_data, ttl=300)

        # Benchmark cache hits
        iterations = 1000
        start = time.time()

        for _ in range(iterations):
            result = manager.get("test_key")
            assert result == test_data

        elapsed = time.time() - start
        avg_time_ms = (elapsed / iterations) * 1000

        # Cache hits should be very fast (< 1ms)
        assert avg_time_ms < 1.0, f"Cache hit too slow: {avg_time_ms:.3f}ms"

    def test_cache_miss_performance(self):
        """Benchmark cache miss performance."""
        manager = QueryCacheManager(enable_memory_fallback=True)

        # Benchmark cache misses
        iterations = 1000
        start = time.time()

        for i in range(iterations):
            result = manager.get(f"missing_key_{i}")
            assert result is None

        elapsed = time.time() - start
        avg_time_ms = (elapsed / iterations) * 1000

        # Cache misses should be fast (< 1ms)
        assert avg_time_ms < 1.0, f"Cache miss too slow: {avg_time_ms:.3f}ms"

    def test_cache_key_generation_performance(self):
        """Benchmark cache key generation."""
        strategy = CacheStrategy()
        query = "SELECT * FROM trades WHERE time > now() - 1h AND symbol = 'BTCUSDT'"

        iterations = 10000
        start = time.time()

        for _ in range(iterations):
            key = strategy.generate_cache_key(query)
            assert key.startswith("query:")

        elapsed = time.time() - start
        avg_time_ms = (elapsed / iterations) * 1000

        # Key generation should be very fast (< 0.1ms)
        assert avg_time_ms < 0.1, f"Key generation too slow: {avg_time_ms:.3f}ms"

    def test_query_classification_performance(self):
        """Benchmark query classification."""
        strategy = CacheStrategy()
        queries = [
            "SELECT * FROM trades WHERE time > now() - 1h",
            "SELECT * FROM trades WHERE time > now() - 1d",
            "SELECT * FROM trading_signals",
            "SELECT * FROM config",
        ]

        iterations = 1000
        start = time.time()

        for _ in range(iterations):
            for query in queries:
                query_type = strategy.classify_query(query)
                assert isinstance(query_type, QueryType)

        elapsed = time.time() - start
        avg_time_ms = (elapsed / (iterations * len(queries))) * 1000

        # Classification should be fast (< 0.1ms)
        assert avg_time_ms < 0.1, f"Classification too slow: {avg_time_ms:.3f}ms"

    def test_get_or_execute_performance(self):
        """Benchmark get_or_execute with cache hit vs miss."""
        manager = QueryCacheManager(enable_memory_fallback=True)

        test_data = {"result": "test"}

        # Pre-populate cache
        manager.set("cached_key", test_data, ttl=300)

        # Benchmark cache hit
        iterations = 1000
        start = time.time()

        for _ in range(iterations):
            result = manager.get_or_execute(
                "cached_key",
                lambda: {"result": "fresh"},
            )
            assert result == test_data

        hit_time = time.time() - start
        hit_avg_ms = (hit_time / iterations) * 1000

        # Benchmark cache miss
        start = time.time()

        for i in range(iterations):
            result = manager.get_or_execute(
                f"miss_key_{i}",
                lambda: {"result": "fresh"},
            )
            assert result == {"result": "fresh"}

        miss_time = time.time() - start
        miss_avg_ms = (miss_time / iterations) * 1000

        # Cache hit should be much faster than miss
        speedup = miss_avg_ms / hit_avg_ms
        assert speedup > 2.0, f"Cache hit not significantly faster: {speedup:.1f}x"

    def test_memory_cache_size_impact(self):
        """Test performance with large memory cache."""
        manager = QueryCacheManager(enable_memory_fallback=True)

        # Populate cache with many entries
        num_entries = 10000
        for i in range(num_entries):
            manager.set(f"key_{i}", {"data": f"value_{i}"}, ttl=3600)

        # Benchmark random access
        import random

        iterations = 1000
        start = time.time()

        for _ in range(iterations):
            key = f"key_{random.randint(0, num_entries - 1)}"
            result = manager.get(key)
            assert result is not None

        elapsed = time.time() - start
        avg_time_ms = (elapsed / iterations) * 1000

        # Large cache should still be fast (< 1ms)
        assert avg_time_ms < 1.0, f"Large cache access too slow: {avg_time_ms:.3f}ms"

    def test_concurrent_access_performance(self):
        """Test concurrent cache access performance."""
        import concurrent.futures

        manager = QueryCacheManager(enable_memory_fallback=True)

        # Pre-populate cache
        for i in range(100):
            manager.set(f"key_{i}", {"data": f"value_{i}"}, ttl=300)

        def read_cache(key_id):
            return manager.get(f"key_{key_id % 100}")

        # Concurrent reads
        start = time.time()

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(read_cache, i) for i in range(1000)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        elapsed = time.time() - start
        avg_time_ms = (elapsed / len(results)) * 1000

        # Concurrent access should still be fast
        assert avg_time_ms < 5.0, f"Concurrent access too slow: {avg_time_ms:.3f}ms"


class TestCacheHitRate:
    """Test cache hit rate targets."""

    def test_repeated_query_hit_rate(self):
        """Test hit rate for repeated queries."""
        manager = QueryCacheManager(enable_memory_fallback=True)

        query = "SELECT * FROM trades WHERE time > now() - 1h"
        cache_key = manager.get_cache_key(query)

        # First access - cache miss
        manager.get_or_execute(cache_key, lambda: {"data": "result"}, ttl=300)

        # Repeated accesses - should be cache hits
        num_accesses = 100
        for _ in range(num_accesses):
            manager.get(cache_key)

        metrics = manager.get_metrics()
        hit_rate = metrics.hit_rate

        # Should have 100% hit rate after first miss
        assert hit_rate >= 99.0, f"Hit rate too low: {hit_rate:.1f}%"

    def test_mixed_query_hit_rate(self):
        """Test hit rate with mixed query patterns."""
        manager = QueryCacheManager(enable_memory_fallback=True)

        # Simulate dashboard load with multiple queries
        queries = [
            ("realtime_1", "SELECT * FROM trades WHERE time > now() - 1h"),
            ("realtime_2", "SELECT mean(price) FROM trades WHERE time > now() - 1h"),
            ("historical_1", "SELECT * FROM trades WHERE time > now() - 1d"),
            ("signal_1", "SELECT * FROM trading_signals"),
        ]

        # First pass - populate cache
        for name, query in queries:
            cache_key = manager.get_cache_key(query)
            manager.get_or_execute(cache_key, lambda n=name: {"data": n}, ttl=300)

        # Second pass - should be cache hits
        for name, query in queries:
            cache_key = manager.get_cache_key(query)
            manager.get(cache_key)

        metrics = manager.get_metrics()
        hit_rate = metrics.hit_rate

        # Should achieve > 50% hit rate
        assert hit_rate >= 50.0, f"Hit rate too low: {hit_rate:.1f}%"
