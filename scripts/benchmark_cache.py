#!/usr/bin/env python3
"""Performance benchmark for query result caching.

Demonstrates the performance improvement achieved by the caching layer.
Run this script to verify cache hit rates and response times.
"""

from __future__ import annotations

import time
from api.cache import QueryCacheManager, CacheStrategy


def benchmark_cache_performance():
    """Run performance benchmarks."""
    print("=" * 60)
    print("ChiseAI Query Cache Performance Benchmark")
    print("=" * 60)
    print()

    # Initialize cache manager
    cache_manager = QueryCacheManager(enable_memory_fallback=True)
    strategy = CacheStrategy()

    # Test queries simulating dashboard load
    queries = [
        ("realtime_price", "SELECT mean(price) FROM trades WHERE time > now() - 1h"),
        ("realtime_volume", "SELECT sum(volume) FROM trades WHERE time > now() - 1h"),
        ("historical_daily", "SELECT mean(price) FROM trades WHERE time > now() - 1d"),
        ("signals_recent", "SELECT * FROM trading_signals WHERE time > now() - 1h"),
        ("config_static", "SELECT * FROM config"),
    ]

    print("Query Classification:")
    print("-" * 60)
    for name, query in queries:
        query_type = strategy.classify_query(query)
        ttl = strategy.get_ttl(query)
        print(f"  {name:20} -> {query_type.name:12} (TTL: {ttl}s)")
    print()

    # Simulate first load (all cache misses)
    print("First Load (Cache Misses):")
    print("-" * 60)
    start_time = time.time()

    for name, query in queries:
        cache_key = cache_manager.get_cache_key(query)

        # Simulate slow InfluxDB query (100ms)
        def slow_query():
            time.sleep(0.1)
            return {"data": f"result_for_{name}"}

        result = cache_manager.get_or_execute(cache_key, slow_query, ttl=300)

    first_load_time = time.time() - start_time
    print(f"  Total time: {first_load_time:.3f}s")
    print(f"  Average per query: {first_load_time / len(queries) * 1000:.1f}ms")
    print()

    # Simulate second load (all cache hits)
    print("Second Load (Cache Hits):")
    print("-" * 60)
    start_time = time.time()

    for name, query in queries:
        cache_key = cache_manager.get_cache_key(query)
        result = cache_manager.get(cache_key)

    second_load_time = time.time() - start_time
    print(f"  Total time: {second_load_time:.3f}s")
    print(f"  Average per query: {second_load_time / len(queries) * 1000:.3f}ms")
    print()

    # Calculate speedup
    speedup = first_load_time / second_load_time if second_load_time > 0 else 0
    print(f"Speedup: {speedup:.1f}x faster with caching")
    print()

    # Simulate sustained load (repeated queries)
    print("Sustained Load (10x repeated queries):")
    print("-" * 60)
    start_time = time.time()
    for _ in range(10):
        for name, query in queries:
            cache_key = cache_manager.get_cache_key(query)
            result = cache_manager.get(cache_key)
            if result is None:
                # Shouldn't happen, but just in case
                def slow_query():
                    time.sleep(0.1)
                    return {"data": f"result_for_{name}"}

                result = cache_manager.get_or_execute(cache_key, slow_query, ttl=300)

    sustained_time = time.time() - start_time
    print(f"  Total time for 50 queries: {sustained_time:.3f}s")
    print(f"  Average per query: {sustained_time / 50 * 1000:.3f}ms")
    print()

    # Display metrics
    metrics = cache_manager.get_metrics()
    print("Cache Metrics:")
    print("-" * 60)
    print(f"  Hits: {metrics.hits}")
    print(f"  Misses: {metrics.misses}")
    print(f"  Hit Rate: {metrics.hit_rate:.1f}%")
    print(f"  Avg Response Time: {metrics.avg_response_time_ms:.3f}ms")
    print()

    # Display stats
    stats = cache_manager.get_stats()
    print("Cache Stats:")
    print("-" * 60)
    print(f"  Memory Cache Size: {stats['memory_cache_size']} entries")
    print(f"  Using Redis: {stats['using_redis']}")
    print(f"  Using Memory Fallback: {stats['using_memory_fallback']}")
    print()

    # Performance targets
    print("Performance Targets:")
    print("-" * 60)
    print(f"  Target hit rate: >70%")
    print(f"  Achieved hit rate: {metrics.hit_rate:.1f}%")
    print(f"  Status: {'PASS ✓' if metrics.hit_rate >= 70 else 'FAIL ✗'}")
    print()

    print("=" * 60)


if __name__ == "__main__":
    benchmark_cache_performance()
