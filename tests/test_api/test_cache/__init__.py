"""Test cache initialization and imports."""

from __future__ import annotations


def test_cache_module_imports():
    """Test that all cache module components can be imported."""
    from api.cache import (
        CacheMetrics,
        CacheMetricsCollector,
        CacheMiddleware,
        CacheStrategy,
        QueryCacheManager,
        QueryType,
        TTLStrategy,
    )

    # Verify all imports are available
    assert CacheMetrics is not None
    assert CacheMetricsCollector is not None
    assert CacheMiddleware is not None
    assert CacheStrategy is not None
    assert QueryCacheManager is not None
    assert QueryType is not None
    assert TTLStrategy is not None


def test_cache_manager_creation():
    """Test cache manager can be created."""
    from api.cache import QueryCacheManager

    manager = QueryCacheManager(enable_memory_fallback=True)
    assert manager is not None
    assert manager.default_ttl == 300


def test_cache_strategy_creation():
    """Test cache strategy can be created."""
    from api.cache import CacheStrategy, TTLStrategy

    ttl_strategy = TTLStrategy()
    strategy = CacheStrategy(ttl_strategy)

    assert strategy is not None
    assert strategy.ttl_strategy == ttl_strategy


def test_metrics_collector_creation():
    """Test metrics collector can be created."""
    from api.cache import CacheMetricsCollector

    collector = CacheMetricsCollector()
    assert collector is not None
    assert collector.window_size == 1000
