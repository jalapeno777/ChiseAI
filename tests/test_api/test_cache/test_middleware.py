"""Integration tests for cache middleware."""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi import FastAPI
from starlette.testclient import TestClient

from api.cache.cache_manager import QueryCacheManager
from api.cache.middleware import CacheMiddleware, CachedInfluxClient


class TestCacheMiddleware:
    """Test FastAPI cache middleware."""

    def test_middleware_caches_get_requests(self):
        """Test that GET requests are cached."""
        app = FastAPI()
        cache_manager = QueryCacheManager(enable_memory_fallback=True)

        @app.get("/test")
        def test_endpoint():
            return {"data": "test_value", "timestamp": 12345}

        app.add_middleware(CacheMiddleware, cache_manager=cache_manager)

        client = TestClient(app)

        # First request - cache miss
        response1 = client.get("/test")
        assert response1.status_code == 200

        # Second request - should be cached
        response2 = client.get("/test")
        assert response2.status_code == 200

        # Verify cache was used
        metrics = cache_manager.get_metrics()
        assert metrics.hits >= 1

    def test_middleware_respects_cache_control(self):
        """Test that Cache-Control headers are respected."""
        app = FastAPI()
        cache_manager = QueryCacheManager(enable_memory_fallback=True)

        @app.get("/test")
        def test_endpoint():
            return {"data": "test_value"}

        app.add_middleware(CacheMiddleware, cache_manager=cache_manager)

        client = TestClient(app)

        # Request with no-cache header
        response = client.get("/test", headers={"Cache-Control": "no-cache"})
        assert response.status_code == 200

    def test_middleware_excludes_paths(self):
        """Test that excluded paths are not cached."""
        app = FastAPI()
        cache_manager = QueryCacheManager(enable_memory_fallback=True)

        @app.get("/health")
        def health_endpoint():
            return {"status": "ok"}

        app.add_middleware(
            CacheMiddleware,
            cache_manager=cache_manager,
            exclude_paths=["/health"],
        )

        client = TestClient(app)

        # Multiple requests to excluded path
        for _ in range(3):
            response = client.get("/health")
            assert response.status_code == 200

        # Should not be cached
        metrics = cache_manager.get_metrics()
        assert metrics.total_requests == 0

    def test_middleware_only_caches_cacheable_methods(self):
        """Test that only cacheable methods are cached."""
        app = FastAPI()
        cache_manager = QueryCacheManager(enable_memory_fallback=True)

        @app.post("/test")
        def test_post():
            return {"data": "posted"}

        @app.get("/test")
        def test_get():
            return {"data": "got"}

        app.add_middleware(CacheMiddleware, cache_manager=cache_manager)

        client = TestClient(app)

        # POST should not be cached
        response_post = client.post("/test")
        assert response_post.status_code == 200

        # GET should be cached
        response_get = client.get("/test")
        assert response_get.status_code == 200

        metrics = cache_manager.get_metrics()
        # Only GET should be counted
        assert metrics.total_requests >= 1


class TestCachedInfluxClient:
    """Test cached InfluxDB client wrapper."""

    def test_query_with_cache_hit(self):
        """Test InfluxDB query with cache hit."""
        mock_influx = MagicMock()
        mock_query_api = MagicMock()
        mock_influx.query_api.return_value = mock_query_api

        cache_manager = QueryCacheManager(enable_memory_fallback=True)
        cached_client = CachedInfluxClient(mock_influx, cache_manager)

        # Pre-populate cache
        query = 'from(bucket: "test") |> range(start: -1h)'
        cache_key = cache_manager.get_cache_key(query)
        cache_manager.set(cache_key, "cached_result", ttl=300)

        # Query should return cached result
        result = cached_client.query(query)

        assert result == "cached_result"
        mock_query_api.query.assert_not_called()

    def test_query_with_cache_miss(self):
        """Test InfluxDB query with cache miss."""
        mock_influx = MagicMock()
        mock_query_api = MagicMock()
        mock_query_api.query.return_value = "fresh_result"
        mock_influx.query_api.return_value = mock_query_api

        cache_manager = QueryCacheManager(enable_memory_fallback=True)
        cached_client = CachedInfluxClient(mock_influx, cache_manager)

        query = 'from(bucket: "test") |> range(start: -1h)'
        result = cached_client.query(query)

        assert result == "fresh_result"
        mock_query_api.query.assert_called_once()

    def test_query_with_cache_disabled(self):
        """Test InfluxDB query with caching disabled."""
        mock_influx = MagicMock()
        mock_query_api = MagicMock()
        mock_query_api.query.return_value = "fresh_result"
        mock_influx.query_api.return_value = mock_query_api

        cache_manager = QueryCacheManager(enable_memory_fallback=True)
        cached_client = CachedInfluxClient(mock_influx, cache_manager)

        query = 'from(bucket: "test") |> range(start: -1h)'
        result = cached_client.query(query, use_cache=False)

        assert result == "fresh_result"
        mock_query_api.query.assert_called_once()

    def test_invalidate_cache(self):
        """Test cache invalidation."""
        mock_influx = MagicMock()
        cache_manager = QueryCacheManager(enable_memory_fallback=True)
        cached_client = CachedInfluxClient(mock_influx, cache_manager)

        # Pre-populate cache
        query = 'from(bucket: "test") |> range(start: -1h)'
        cache_key = cache_manager.get_cache_key(query)
        cache_manager.set(cache_key, "cached_result", ttl=300)

        # Invalidate cache
        count = cached_client.invalidate_cache()

        assert count >= 1
        assert cache_manager.get(cache_key) is None

    def test_get_metrics(self):
        """Test metrics retrieval."""
        mock_influx = MagicMock()
        cache_manager = QueryCacheManager(enable_memory_fallback=True)
        cached_client = CachedInfluxClient(mock_influx, cache_manager)

        # Generate some activity
        query = 'from(bucket: "test") |> range(start: -1h)'
        cache_key = cache_manager.get_cache_key(query)
        cache_manager.set(cache_key, "result", ttl=300)
        cache_manager.get(cache_key)

        metrics = cached_client.get_metrics()

        assert "metrics" in metrics
        assert "memory_cache_size" in metrics
