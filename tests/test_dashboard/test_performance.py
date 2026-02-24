"""Tests for dashboard performance optimization.

Tests cover caching, query optimization, and performance monitoring
to ensure dashboard load times under 3 seconds.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dashboard.performance import (
    CacheKeyBuilder,
    CacheStats,
    DashboardCache,
    LoadTimeMetric,
    PerformanceAlert,
    PerformanceMonitor,
    PerformanceThresholds,
    QueryMetrics,
    QueryOptimizer,
    QueryPlan,
    QueryType,
    cached_query,
    optimize_panel_query,
)


class TestCacheStats:
    """Tests for CacheStats."""

    def test_initial_stats(self) -> None:
        """Test initial state."""
        stats = CacheStats()
        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.hit_rate == 0.0

    def test_record_hit(self) -> None:
        """Test recording a hit."""
        stats = CacheStats()
        stats.record_hit(10.0)
        assert stats.hits == 1
        assert stats.total_requests == 1
        assert stats.hit_rate == 100.0

    def test_record_miss(self) -> None:
        """Test recording a miss."""
        stats = CacheStats()
        stats.record_miss(50.0)
        assert stats.misses == 1
        assert stats.total_requests == 1
        assert stats.hit_rate == 0.0

    def test_hit_rate_calculation(self) -> None:
        """Test hit rate calculation."""
        stats = CacheStats()
        stats.record_hit(10.0)
        stats.record_hit(10.0)
        stats.record_miss(50.0)
        assert stats.hit_rate == pytest.approx(66.67, rel=0.01)

    def test_to_dict(self) -> None:
        """Test serialization."""
        stats = CacheStats(hits=10, misses=5, total_requests=15)
        result = stats.to_dict()
        assert result["hits"] == 10
        assert result["misses"] == 5
        assert result["hit_rate"] == pytest.approx(66.67, rel=0.01)


class TestCacheKeyBuilder:
    """Tests for CacheKeyBuilder."""

    def test_build_key_basic(self) -> None:
        """Test basic key building."""
        key = CacheKeyBuilder.build_key("signal_list", "BTC")
        assert key == "chiseai:dashboard:cache:signal_list:BTC"

    def test_build_key_with_params(self) -> None:
        """Test key building with params."""
        key = CacheKeyBuilder.build_key(
            "signal_list",
            "ETH",
            params={"limit": 10, "offset": 0},
        )
        assert "chiseai:dashboard:cache:signal_list:ETH:" in key
        # Params are hashed, so we should have an 8-char hash
        parts = key.split(":")
        assert len(parts[-1]) == 8

    def test_build_key_consistent(self) -> None:
        """Test that same params produce same key."""
        params = {"limit": 10, "offset": 0}
        key1 = CacheKeyBuilder.build_key("signal_list", "BTC", params)
        key2 = CacheKeyBuilder.build_key("signal_list", "BTC", params)
        assert key1 == key2

    def test_build_key_param_order_independent(self) -> None:
        """Test that param order doesn't affect key."""
        key1 = CacheKeyBuilder.build_key("signal_list", "BTC", {"a": 1, "b": 2})
        key2 = CacheKeyBuilder.build_key("signal_list", "BTC", {"b": 2, "a": 1})
        assert key1 == key2

    def test_build_pattern(self) -> None:
        """Test pattern building."""
        pattern = CacheKeyBuilder.build_pattern("signal_list")
        assert pattern == "chiseai:dashboard:cache:signal_list:*"


class TestDashboardCache:
    """Tests for DashboardCache."""

    @pytest.fixture
    def mock_redis(self) -> AsyncMock:
        """Create mock Redis client."""
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock(return_value=True)
        redis.delete = AsyncMock(return_value=1)
        redis.scan = AsyncMock(return_value=(0, []))
        redis.ping = AsyncMock(return_value=True)
        return redis

    @pytest.fixture
    def cache(self, mock_redis: AsyncMock) -> DashboardCache:
        """Create cache instance."""
        return DashboardCache(mock_redis)

    @pytest.mark.asyncio
    async def test_get_miss(self, cache: DashboardCache, mock_redis: AsyncMock) -> None:
        """Test cache miss."""
        mock_redis.get = AsyncMock(return_value=None)
        result = await cache.get("test_key")
        assert result is None
        assert cache.stats.misses == 1

    @pytest.mark.asyncio
    async def test_get_hit(self, cache: DashboardCache, mock_redis: AsyncMock) -> None:
        """Test cache hit."""
        import json

        mock_redis.get = AsyncMock(return_value=json.dumps({"data": "test"}))
        result = await cache.get("test_key")
        assert result == {"data": "test"}
        assert cache.stats.hits == 1

    @pytest.mark.asyncio
    async def test_set(self, cache: DashboardCache, mock_redis: AsyncMock) -> None:
        """Test setting cache value."""
        result = await cache.set("test_key", {"data": "test"}, ttl_seconds=60)
        assert result is True
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_with_data_type(
        self, cache: DashboardCache, mock_redis: AsyncMock
    ) -> None:
        """Test setting cache with data type for TTL lookup."""
        result = await cache.set(
            "test_key",
            {"data": "test"},
            data_type="market_summary",
        )
        assert result is True
        # Should use 60 second TTL for market_summary
        call_args = mock_redis.setex.call_args
        assert call_args[0][1] == 60

    @pytest.mark.asyncio
    async def test_delete(self, cache: DashboardCache, mock_redis: AsyncMock) -> None:
        """Test deleting cache key."""
        result = await cache.delete("test_key")
        assert result is True
        assert cache.stats.evictions == 1

    @pytest.mark.asyncio
    async def test_get_or_compute_cache_hit(
        self, cache: DashboardCache, mock_redis: AsyncMock
    ) -> None:
        """Test get_or_compute with cache hit."""
        import json

        mock_redis.get = AsyncMock(return_value=json.dumps({"cached": True}))

        compute_fn = MagicMock(return_value={"computed": True})
        result = await cache.get_or_compute("test_key", compute_fn)

        assert result == {"cached": True}
        compute_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_or_compute_cache_miss(
        self, cache: DashboardCache, mock_redis: AsyncMock
    ) -> None:
        """Test get_or_compute with cache miss."""
        mock_redis.get = AsyncMock(return_value=None)

        async def compute_fn() -> dict:
            return {"computed": True}

        result = await cache.get_or_compute("test_key", compute_fn)

        assert result == {"computed": True}
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_healthy(
        self, cache: DashboardCache, mock_redis: AsyncMock
    ) -> None:
        """Test health check when healthy."""
        result = await cache.health_check()
        assert result["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_health_check_unhealthy(
        self, cache: DashboardCache, mock_redis: AsyncMock
    ) -> None:
        """Test health check when unhealthy."""
        mock_redis.ping = AsyncMock(side_effect=Exception("Connection failed"))
        result = await cache.health_check()
        assert result["status"] == "unhealthy"


class TestQueryOptimizer:
    """Tests for QueryOptimizer."""

    def test_analyze_query_select_star(self) -> None:
        """Test detection of SELECT * queries."""
        optimizer = QueryOptimizer()
        plan = optimizer.analyze_query(
            "SELECT * FROM signals",
            QueryType.SIGNAL_LIST,
        )
        assert any("SELECT *" in opt for opt in plan.optimizations)

    def test_analyze_query_missing_where(self) -> None:
        """Test detection of missing WHERE clause."""
        optimizer = QueryOptimizer()
        plan = optimizer.analyze_query(
            "SELECT id, token FROM signals;",
            QueryType.SIGNAL_LIST,
        )
        assert any("WHERE" in opt for opt in plan.optimizations)

    def test_optimization_improves_query(self) -> None:
        """Test that optimization improves query."""
        optimizer = QueryOptimizer()
        plan = optimizer.analyze_query(
            "SELECT * FROM signals;",
            QueryType.SIGNAL_LIST,
        )
        assert len(plan.optimizations) > 0
        assert plan.estimated_improvement > 0

    def test_record_metrics(self) -> None:
        """Test recording query metrics."""
        optimizer = QueryOptimizer()

        metrics = QueryMetrics(
            query_type=QueryType.SIGNAL_LIST,
            execution_time_ms=500,
            rows_returned=100,
        )
        optimizer.record_metrics(metrics)

        assert len(optimizer._metrics_history) == 1

    def test_get_slow_queries(self) -> None:
        """Test getting slow queries."""
        optimizer = QueryOptimizer()

        # Record a fast query
        optimizer.record_metrics(
            QueryMetrics(
                query_type=QueryType.SIGNAL_LIST,
                execution_time_ms=100,
                rows_returned=10,
            )
        )

        # Record a slow query
        optimizer.record_metrics(
            QueryMetrics(
                query_type=QueryType.SIGNAL_LIST,
                execution_time_ms=1500,
                rows_returned=1000,
            )
        )

        slow = optimizer.get_slow_queries()
        assert len(slow) == 1
        assert slow[0].execution_time_ms == 1500

    def test_get_index_recommendations(self) -> None:
        """Test getting index recommendations."""
        optimizer = QueryOptimizer()
        indexes = optimizer.get_index_recommendations()

        assert len(indexes) > 0
        assert all("CREATE INDEX" in idx for idx in indexes)


class TestQueryMetrics:
    """Tests for QueryMetrics."""

    def test_efficiency_ratio(self) -> None:
        """Test efficiency ratio calculation."""
        metrics = QueryMetrics(
            query_type=QueryType.SIGNAL_LIST,
            execution_time_ms=500,
            rows_returned=10,
            rows_scanned=100,
        )
        assert metrics.efficiency_ratio == 0.1

    def test_efficiency_ratio_no_scans(self) -> None:
        """Test efficiency ratio with no scans."""
        metrics = QueryMetrics(
            query_type=QueryType.SIGNAL_LIST,
            execution_time_ms=500,
            rows_returned=10,
            rows_scanned=0,
        )
        assert metrics.efficiency_ratio == 1.0

    def test_is_slow_by_time(self) -> None:
        """Test is_slow detection by time."""
        metrics = QueryMetrics(
            query_type=QueryType.SIGNAL_LIST,
            execution_time_ms=1500,
            rows_returned=10,
        )
        assert metrics.is_slow is True

    def test_is_slow_by_efficiency(self) -> None:
        """Test is_slow detection by low efficiency."""
        metrics = QueryMetrics(
            query_type=QueryType.SIGNAL_LIST,
            execution_time_ms=500,
            rows_returned=10,
            rows_scanned=1000,  # Only 1% efficient
        )
        assert metrics.is_slow is True


class TestPerformanceMonitor:
    """Tests for PerformanceMonitor."""

    @pytest.fixture
    def monitor(self) -> PerformanceMonitor:
        """Create monitor instance."""
        return PerformanceMonitor()

    def test_record_load_time(self, monitor: PerformanceMonitor) -> None:
        """Test recording load time."""
        metric = monitor.record_load_time("signal_list", 1500, cached=True)
        assert metric.load_time_ms == 1500
        assert metric.cached is True

    def test_get_component_metrics(self, monitor: PerformanceMonitor) -> None:
        """Test getting component metrics."""
        monitor.record_load_time("signal_list", 1500)
        monitor.record_load_time("signal_list", 2000)
        monitor.record_load_time("market_summary", 500)

        metrics = monitor.get_component_metrics("signal_list")
        assert len(metrics) == 2

    def test_check_alerts_load_time(self, monitor: PerformanceMonitor) -> None:
        """Test load time alerts."""
        # Record several slow loads
        for _ in range(5):
            monitor.record_load_time("signal_list", 2500)

        alerts = monitor.check_alerts()
        assert len(alerts) > 0
        assert any(a.component == "signal_list" for a in alerts)

    def test_check_alerts_cache_hit_rate(self, monitor: PerformanceMonitor) -> None:
        """Test cache hit rate alerts."""
        # Create mock cache stats with low hit rate
        cache_stats = CacheStats(hits=30, misses=70, total_requests=100)

        alerts = monitor.check_alerts(cache_stats=cache_stats)
        assert any(a.component == "cache" for a in alerts)

    def test_get_summary(self, monitor: PerformanceMonitor) -> None:
        """Test getting performance summary."""
        monitor.record_load_time("signal_list", 1000, cached=True)
        monitor.record_load_time("signal_list", 1500, cached=False)
        monitor.record_load_time("market_summary", 500)

        summary = monitor.get_summary()
        assert "signal_list" in summary["components"]
        assert "market_summary" in summary["components"]

    def test_resolve_alert(self, monitor: PerformanceMonitor) -> None:
        """Test resolving alerts."""
        # Create an alert
        for _ in range(5):
            monitor.record_load_time("signal_list", 3000)
        alerts = monitor.check_alerts()

        assert len(alerts) > 0
        alert_id = alerts[0].alert_id

        result = monitor.resolve_alert(alert_id)
        assert result is True
        assert alerts[0].resolved is True


class TestLoadTimeMetric:
    """Tests for LoadTimeMetric."""

    def test_is_slow(self) -> None:
        """Test is_slow detection."""
        metric = LoadTimeMetric(
            component="signal_list",
            load_time_ms=2500,
        )
        assert metric.is_slow() is True

    def test_is_fast(self) -> None:
        """Test fast load detection."""
        metric = LoadTimeMetric(
            component="signal_list",
            load_time_ms=500,
        )
        assert metric.is_slow() is False

    def test_to_dict(self) -> None:
        """Test serialization."""
        metric = LoadTimeMetric(
            component="signal_list",
            load_time_ms=1500,
            cached=True,
            query_count=3,
        )
        result = metric.to_dict()
        assert result["component"] == "signal_list"
        assert result["load_time_ms"] == 1500
        assert result["cached"] is True


class TestPerformanceThresholds:
    """Tests for PerformanceThresholds."""

    def test_default_thresholds(self) -> None:
        """Test default thresholds."""
        thresholds = PerformanceThresholds.default()
        assert thresholds.load_time_warning_ms == 2000.0
        assert thresholds.load_time_critical_ms == 3000.0

    def test_strict_thresholds(self) -> None:
        """Test strict thresholds."""
        thresholds = PerformanceThresholds.strict()
        assert (
            thresholds.load_time_warning_ms
            < PerformanceThresholds.default().load_time_warning_ms
        )


class TestOptimizePanelQuery:
    """Tests for optimize_panel_query function."""

    def test_optimize_signal_list_query(self) -> None:
        """Test optimizing signal list query."""
        plan = optimize_panel_query(
            "SELECT * FROM signals WHERE token = ?",
            QueryType.SIGNAL_LIST,
        )
        assert plan is not None
        assert isinstance(plan.optimizations, list)


class TestCachedQueryDecorator:
    """Tests for cached_query decorator."""

    @pytest.mark.asyncio
    async def test_decorator_with_cache(self) -> None:
        """Test decorator caches results."""
        # Create a mock cache
        mock_cache = AsyncMock(spec=DashboardCache)
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock(return_value=True)
        mock_cache.get_or_compute = AsyncMock(return_value={"result": "data"})

        class TestService:
            def __init__(self, cache: DashboardCache):
                self._cache = cache

            @cached_query("test", ttl_seconds=60)
            async def get_data(self, token: str) -> dict:
                return {"token": token, "computed": True}

        service = TestService(mock_cache)
        result = await service.get_data("BTC")

        assert result is not None
