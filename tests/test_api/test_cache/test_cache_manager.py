"""Tests for query result caching layer."""

from __future__ import annotations

import time
from unittest.mock import MagicMock


from api.cache.cache_manager import CacheEntry, QueryCacheManager
from api.cache.metrics import CacheMetricsCollector
from api.cache.strategies import CacheStrategy, QueryType, TTLStrategy


class TestTTLStrategy:
    """Test TTL strategy configuration."""

    def test_default_ttls(self):
        """Test default TTL values."""
        strategy = TTLStrategy()
        assert strategy.realtime_ttl == 300
        assert strategy.historical_ttl == 3600
        assert strategy.signal_ttl == 60
        assert strategy.static_ttl == 86400
        assert strategy.default_ttl == 300

    def test_custom_ttls(self):
        """Test custom TTL configuration."""
        strategy = TTLStrategy(
            realtime_ttl=600,
            historical_ttl=7200,
            default_ttl=60,
        )
        assert strategy.realtime_ttl == 600
        assert strategy.historical_ttl == 7200
        assert strategy.get_ttl(QueryType.REALTIME) == 600

    def test_get_ttl_by_type(self):
        """Test TTL retrieval by query type."""
        strategy = TTLStrategy()
        assert strategy.get_ttl(QueryType.REALTIME) == 300
        assert strategy.get_ttl(QueryType.HISTORICAL) == 3600
        assert strategy.get_ttl(QueryType.SIGNAL) == 60
        assert strategy.get_ttl(QueryType.STATIC) == 86400
        assert strategy.get_ttl(QueryType.UNKNOWN) == 300


class TestCacheStrategy:
    """Test cache strategy for query classification and key generation."""

    def test_classify_realtime_query(self):
        """Test classification of real-time queries."""
        strategy = CacheStrategy()

        queries = [
            "SELECT * FROM trades WHERE time > now() - 1h",
            "from(bucket: 'data') |> range(start: -1h)",
            "SELECT mean(price) WHERE time > now() - 60m",
        ]

        for query in queries:
            assert strategy.classify_query(query) == QueryType.REALTIME

    def test_classify_historical_query(self):
        """Test classification of historical queries."""
        strategy = CacheStrategy()

        queries = [
            "SELECT * FROM trades WHERE time > now() - 1d",
            "from(bucket: 'data') |> range(start: -7d)",
            "SELECT mean(price) WHERE time > now() - 30d",
        ]

        for query in queries:
            assert strategy.classify_query(query) == QueryType.HISTORICAL

    def test_classify_signal_query(self):
        """Test classification of signal queries."""
        strategy = CacheStrategy()

        queries = [
            "SELECT * FROM trading_signals",
            "SELECT * FROM signal_history",
            "SELECT * FROM outcomes",
        ]

        for query in queries:
            assert strategy.classify_query(query) == QueryType.SIGNAL

    def test_classify_static_query(self):
        """Test classification of static/config queries."""
        strategy = CacheStrategy()

        queries = [
            "SELECT * FROM config",
            "SELECT * FROM metadata",
            "SELECT version FROM schema",
        ]

        for query in queries:
            assert strategy.classify_query(query) == QueryType.STATIC

    def test_classify_unknown_query(self):
        """Test classification of unknown queries."""
        strategy = CacheStrategy()

        query = "SELECT * FROM unknown_table"
        assert strategy.classify_query(query) == QueryType.UNKNOWN

    def test_normalize_query(self):
        """Test query normalization."""
        strategy = CacheStrategy()

        # Test whitespace normalization
        query1 = "SELECT   *   FROM   table"
        query2 = "SELECT * FROM table"
        assert strategy.normalize_query(query1) == strategy.normalize_query(query2)

        # Test case normalization
        query3 = "SELECT * FROM table"
        query4 = "select * from table"
        assert strategy.normalize_query(query3) == strategy.normalize_query(query4)

    def test_generate_cache_key(self):
        """Test cache key generation."""
        strategy = CacheStrategy()

        query = "SELECT * FROM trades WHERE time > now() - 1h"
        key = strategy.generate_cache_key(query)

        assert key.startswith("query:")
        # Key format: query:{hash}:{time_bucket} (time_bucket contains colons in ISO format)
        parts = key.split(":")
        assert len(parts) >= 3
        assert parts[0] == "query"
        assert len(parts[1]) == 16  # 16-char hash

        # Same query should generate same key within time bucket
        key2 = strategy.generate_cache_key(query)
        assert key == key2

    def test_should_cache(self):
        """Test cache eligibility."""
        strategy = CacheStrategy()

        # Should cache normal queries
        assert strategy.should_cache("SELECT * FROM table") is True

        # Should not cache very short queries
        assert strategy.should_cache("SELECT") is False

        # Should not cache queries with no-cache hint
        assert strategy.should_cache("SELECT * FROM table /* no-cache */") is False
        assert strategy.should_cache("SELECT * FROM table -- no-cache") is False

    def test_get_ttl(self):
        """Test TTL retrieval from strategy."""
        strategy = CacheStrategy()

        realtime_query = "SELECT * FROM trades WHERE time > now() - 1h"
        historical_query = "SELECT * FROM trades WHERE time > now() - 1d"

        assert strategy.get_ttl(realtime_query) == 300
        assert strategy.get_ttl(historical_query) == 3600
        assert strategy.get_ttl(QueryType.SIGNAL) == 60


class TestCacheMetricsCollector:
    """Test cache metrics collection."""

    def test_record_hit(self):
        """Test recording cache hits."""
        collector = CacheMetricsCollector()

        collector.record_hit(5.0)
        collector.record_hit(3.0)

        snapshot = collector.get_snapshot()
        assert snapshot.hits == 2
        assert snapshot.misses == 0
        assert snapshot.hit_rate == 100.0

    def test_record_miss(self):
        """Test recording cache misses."""
        collector = CacheMetricsCollector()

        collector.record_miss(10.0)
        collector.record_miss(8.0)

        snapshot = collector.get_snapshot()
        assert snapshot.hits == 0
        assert snapshot.misses == 2
        assert snapshot.miss_rate == 100.0

    def test_hit_rate_calculation(self):
        """Test hit rate calculation."""
        collector = CacheMetricsCollector()

        collector.record_hit(5.0)
        collector.record_hit(3.0)
        collector.record_miss(10.0)

        snapshot = collector.get_snapshot()
        assert snapshot.hits == 2
        assert snapshot.misses == 1
        assert abs(snapshot.hit_rate - 66.67) < 0.1  # Allow floating point tolerance

    def test_avg_response_time(self):
        """Test average response time calculation."""
        collector = CacheMetricsCollector()

        collector.record_hit(5.0)
        collector.record_hit(3.0)
        collector.record_miss(10.0)

        snapshot = collector.get_snapshot()
        assert snapshot.avg_response_time_ms == 6.0
        assert snapshot.avg_hit_time_ms == 4.0
        assert snapshot.avg_miss_time_ms == 10.0

    def test_window_stats(self):
        """Test sliding window statistics."""
        collector = CacheMetricsCollector(window_size=5)

        # Add more operations than window size
        for i in range(10):
            collector.record_hit(1.0)

        stats = collector.get_window_stats()
        assert stats["window_size"] == 5
        assert stats["window_hits"] == 5

    def test_reset(self):
        """Test metrics reset."""
        collector = CacheMetricsCollector()

        collector.record_hit(5.0)
        collector.record_miss(10.0)

        collector.reset()

        snapshot = collector.get_snapshot()
        assert snapshot.hits == 0
        assert snapshot.misses == 0

    def test_prometheus_export(self):
        """Test Prometheus format export."""
        collector = CacheMetricsCollector()

        collector.record_hit(5.0)
        collector.record_miss(10.0)

        output = collector.export_prometheus_format()

        assert "chiseai_cache_hits_total 1" in output
        assert "chiseai_cache_misses_total 1" in output
        assert "chiseai_cache_hit_rate" in output


class TestCacheEntry:
    """Test cache entry data structure."""

    def test_cache_entry_creation(self):
        """Test cache entry creation."""
        entry = CacheEntry(
            data={"key": "value"},
            created_at=time.time(),
            ttl=300,
            query_type=QueryType.REALTIME,
        )

        assert entry.data == {"key": "value"}
        assert entry.ttl == 300
        assert entry.query_type == QueryType.REALTIME
        assert entry.access_count == 0

    def test_cache_entry_expiration(self):
        """Test cache entry expiration."""
        entry = CacheEntry(
            data={"key": "value"},
            created_at=time.time() - 400,  # 400 seconds ago
            ttl=300,  # 5 minute TTL
            query_type=QueryType.REALTIME,
        )

        assert entry.is_expired() is True

        fresh_entry = CacheEntry(
            data={"key": "value"},
            created_at=time.time(),
            ttl=300,
            query_type=QueryType.REALTIME,
        )

        assert fresh_entry.is_expired() is False

    def test_cache_entry_serialization(self):
        """Test cache entry serialization."""
        entry = CacheEntry(
            data={"key": "value"},
            created_at=1000.0,
            ttl=300,
            query_type=QueryType.REALTIME,
            access_count=5,
        )

        data = entry.to_dict()
        restored = CacheEntry.from_dict(data)

        assert restored.data == entry.data
        assert restored.created_at == entry.created_at
        assert restored.ttl == entry.ttl
        assert restored.query_type == entry.query_type
        assert restored.access_count == entry.access_count


class TestQueryCacheManager:
    """Test query cache manager."""

    def test_init_with_defaults(self):
        """Test initialization with default values."""
        manager = QueryCacheManager()

        assert manager.default_ttl == 300
        assert manager._enable_memory_fallback is True

    def test_init_with_redis(self):
        """Test initialization with Redis client."""
        mock_redis = MagicMock()
        mock_redis.ping.return_value = True

        manager = QueryCacheManager(redis_client=mock_redis)

        assert manager.redis == mock_redis

    def test_memory_cache_operations(self):
        """Test in-memory cache operations."""
        manager = QueryCacheManager(enable_memory_fallback=True)

        # Test set and get
        manager.set("key1", {"data": "value1"}, ttl=300)
        result = manager.get("key1")

        assert result == {"data": "value1"}

    def test_memory_cache_expiration(self):
        """Test in-memory cache expiration."""
        manager = QueryCacheManager(enable_memory_fallback=True)

        # Set entry with very short TTL
        manager.set("key1", {"data": "value1"}, ttl=1)

        # Should be available immediately
        assert manager.get("key1") == {"data": "value1"}

        # Wait for expiration
        time.sleep(1.1)

        # Should be expired
        assert manager.get("key1") is None

    def test_get_or_execute_cache_hit(self):
        """Test get_or_execute with cache hit."""
        manager = QueryCacheManager(enable_memory_fallback=True)

        # Pre-populate cache
        manager.set("key1", "cached_value", ttl=300)

        # Should return cached value without executing function
        result = manager.get_or_execute("key1", lambda: "fresh_value")

        assert result == "cached_value"

    def test_get_or_execute_cache_miss(self):
        """Test get_or_execute with cache miss."""
        manager = QueryCacheManager(enable_memory_fallback=True)

        # Should execute function and cache result
        result = manager.get_or_execute("key1", lambda: "fresh_value", ttl=300)

        assert result == "fresh_value"
        assert manager.get("key1") == "fresh_value"

    def test_get_or_execute_no_cache(self):
        """Test get_or_execute with caching disabled."""
        manager = QueryCacheManager(enable_memory_fallback=True)

        # Should execute function without caching
        result = manager.get_or_execute("key1", lambda: "fresh_value", use_cache=False)

        assert result == "fresh_value"
        assert manager.get("key1") is None

    def test_invalidate_all(self):
        """Test invalidating all cache entries."""
        manager = QueryCacheManager(enable_memory_fallback=True)

        manager.set("key1", "value1", ttl=300)
        manager.set("key2", "value2", ttl=300)

        count = manager.invalidate()

        assert count >= 2
        assert manager.get("key1") is None
        assert manager.get("key2") is None

    def test_invalidate_pattern(self):
        """Test invalidating cache entries by pattern."""
        manager = QueryCacheManager(enable_memory_fallback=True)

        manager.set("query:abc:123", "value1", ttl=300)
        manager.set("query:def:456", "value2", ttl=300)
        manager.set("other:ghi:789", "value3", ttl=300)

        count = manager.invalidate("query:*")

        assert count == 2
        assert manager.get("query:abc:123") is None
        assert manager.get("query:def:456") is None
        assert manager.get("other:ghi:789") == "value3"

    def test_get_metrics(self):
        """Test metrics retrieval."""
        manager = QueryCacheManager(enable_memory_fallback=True)

        # Generate some cache activity
        manager.set("key1", "value1", ttl=300)
        manager.get("key1")  # Hit
        manager.get("key2")  # Miss

        metrics = manager.get_metrics()

        assert metrics.hits >= 1
        assert metrics.misses >= 1

    def test_get_stats(self):
        """Test comprehensive stats retrieval."""
        manager = QueryCacheManager(enable_memory_fallback=True)

        manager.set("key1", "value1", ttl=300)

        stats = manager.get_stats()

        assert "metrics" in stats
        assert "window" in stats
        assert "memory_cache_size" in stats
        assert stats["memory_cache_size"] >= 1

    def test_should_cache(self):
        """Test cache eligibility check."""
        manager = QueryCacheManager(enable_memory_fallback=True)

        assert manager.should_cache("SELECT * FROM table") is True
        assert manager.should_cache("SELECT") is False

    def test_get_cache_key(self):
        """Test cache key generation."""
        manager = QueryCacheManager(enable_memory_fallback=True)

        query = "SELECT * FROM trades WHERE time > now() - 1h"
        key = manager.get_cache_key(query)

        assert key.startswith("query:")

    def test_get_ttl(self):
        """Test TTL retrieval."""
        manager = QueryCacheManager(enable_memory_fallback=True)

        realtime_query = "SELECT * FROM trades WHERE time > now() - 1h"
        historical_query = "SELECT * FROM trades WHERE time > now() - 1d"

        assert manager.get_ttl(realtime_query) == 300
        assert manager.get_ttl(historical_query) == 3600

    def test_redis_fallback_to_memory(self):
        """Test fallback to memory when Redis fails."""
        mock_redis = MagicMock()
        mock_redis.ping.side_effect = Exception("Redis down")

        manager = QueryCacheManager(
            redis_client=mock_redis,
            enable_memory_fallback=True,
        )

        # Should work with memory fallback
        manager.set("key1", "value1", ttl=300)
        result = manager.get("key1")

        assert result == "value1"

    def test_clear_memory_cache(self):
        """Test clearing memory cache."""
        manager = QueryCacheManager(enable_memory_fallback=True)

        manager.set("key1", "value1", ttl=300)
        manager.set("key2", "value2", ttl=300)

        count = manager.clear_memory_cache()

        assert count == 2
        assert manager.get_memory_cache_size() == 0
