"""FastAPI middleware for query result caching.

Provides middleware that automatically caches API responses based on
request patterns and cache headers.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Callable
from typing import Any, cast

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from api.cache.cache_manager import QueryCacheManager

logger = logging.getLogger(__name__)


class CacheMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for automatic response caching.

    Caches API responses based on request path and query parameters.
    Respects Cache-Control headers for cache invalidation.
    """

    def __init__(
        self,
        app: ASGIApp,
        cache_manager: QueryCacheManager | None = None,
        exclude_paths: list[str] | None = None,
        cacheable_methods: list[str] | None = None,
        default_ttl: int = 300,
    ) -> None:
        """Initialize cache middleware.

        Args:
            app: ASGI application
            cache_manager: Cache manager instance (creates default if None)
            exclude_paths: URL paths to exclude from caching
            cacheable_methods: HTTP methods to cache (default: GET, HEAD)
            default_ttl: Default cache TTL in seconds
        """
        super().__init__(app)
        self.cache_manager = cache_manager or QueryCacheManager(default_ttl=default_ttl)
        self.exclude_paths = exclude_paths or [
            "/health",
            "/metrics",
            "/api/v1/health",
        ]
        self.cacheable_methods = cacheable_methods or ["GET", "HEAD"]
        self.default_ttl = default_ttl

    def _generate_cache_key(self, request: Request) -> str | None:
        """Generate cache key from request.

        Args:
            request: FastAPI request

        Returns:
            Cache key or None if not cacheable
        """
        # Check method
        if request.method not in self.cacheable_methods:
            return None

        # Check excluded paths
        path = request.url.path
        for exclude in self.exclude_paths:
            if path.startswith(exclude):
                return None

        # Generate key from path and query params
        key_parts = [request.method, path]

        # Add sorted query params
        query_params = sorted(request.query_params.items())
        if query_params:
            key_parts.append(json.dumps(query_params, sort_keys=True))

        key_string = "|".join(key_parts)
        key_hash = hashlib.sha256(key_string.encode()).hexdigest()[:16]

        return f"api:{key_hash}"

    def _should_cache_response(self, response: Response) -> bool:
        """Determine if response should be cached.

        Args:
            response: FastAPI response

        Returns:
            True if response should be cached
        """
        # Only cache successful responses
        if response.status_code < 200 or response.status_code >= 300:
            return False

        # Check Cache-Control header
        cache_control = response.headers.get("cache-control", "").lower()
        return not ("no-store" in cache_control or "private" in cache_control)

    def _get_ttl_from_response(self, response: Response) -> int:
        """Extract TTL from response headers.

        Args:
            response: FastAPI response

        Returns:
            TTL in seconds
        """
        cache_control = response.headers.get("cache-control", "").lower()

        # Parse max-age
        if "max-age=" in cache_control:
            try:
                max_age = int(cache_control.split("max-age=")[1].split(",")[0])
                return max_age
            except (ValueError, IndexError):
                return self.default_ttl

        # Check Expires header
        expires = response.headers.get("expires")
        if expires:
            try:
                from email.utils import parsedate_to_datetime

                expires_dt = parsedate_to_datetime(expires)
                ttl = int(expires_dt.timestamp() - time.time())
                if ttl > 0:
                    return ttl
            except (TypeError, ValueError, OverflowError):
                return self.default_ttl

        return self.default_ttl

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with caching.

        Args:
            request: FastAPI request
            call_next: Next middleware/handler

        Returns:
            Response (from cache or fresh)
        """
        # Generate cache key
        cache_key = self._generate_cache_key(request)

        if cache_key is None:
            # Not cacheable, proceed normally
            return cast(Response, await call_next(request))

        # Check for cache-bypass headers
        cache_control = request.headers.get("cache-control", "").lower()
        if "no-cache" in cache_control or "no-store" in cache_control:
            return cast(Response, await call_next(request))

        # Try to get from cache
        cached_response = self.cache_manager.get(cache_key)
        if cached_response is not None and isinstance(cached_response, dict):
            return Response(
                content=cached_response.get("body", b""),
                status_code=cached_response.get("status_code", 200),
                headers=cached_response.get("headers", {}),
                media_type=cached_response.get("media_type"),
            )

        # Execute request
        response = await call_next(request)

        # Cache response if appropriate
        if self._should_cache_response(response):
            ttl = self._get_ttl_from_response(response)

            # Read response body
            body = b""
            async for chunk in response.body_iterator:
                body += chunk

            # Create cacheable response data
            response_data = {
                "body": body,
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "media_type": response.media_type,
            }

            # Cache the response
            self.cache_manager.set(cache_key, response_data, ttl=ttl)

            # Return new response with body
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        return cast(Response, response)


class CachedInfluxClient:
    """Wrapper for InfluxDB client with caching support.

    Automatically caches InfluxDB query results with appropriate TTLs
    based on query type.
    """

    def __init__(
        self,
        influx_client: Any,
        cache_manager: QueryCacheManager | None = None,
        default_use_cache: bool = True,
    ) -> None:
        """Initialize cached InfluxDB client.

        Args:
            influx_client: InfluxDB client instance
            cache_manager: Cache manager (creates default if None)
            default_use_cache: Default caching behavior
        """
        self.influx_client = influx_client
        self.cache_manager = cache_manager or QueryCacheManager()
        self.default_use_cache = default_use_cache

    def query(
        self,
        query: str,
        use_cache: bool | None = None,
        org: str | None = None,
    ) -> Any:
        """Execute InfluxDB query with caching.

        Args:
            query: Flux query string
            use_cache: Whether to use cache (uses default if None)
            org: InfluxDB organization

        Returns:
            Query results
        """
        if use_cache is None:
            use_cache = self.default_use_cache

        if not use_cache or not self.cache_manager.should_cache(query):
            # Execute directly
            query_api = self.influx_client.query_api()
            return query_api.query(query, org=org)

        # Generate cache key
        cache_key = self.cache_manager.get_cache_key(query)
        ttl = self.cache_manager.get_ttl(query)

        # Try cache or execute
        def execute_query():
            query_api = self.influx_client.query_api()
            return query_api.query(query, org=org)

        return self.cache_manager.get_or_execute(
            cache_key,
            execute_query,
            ttl=ttl,
        )

    async def query_async(
        self,
        query: str,
        use_cache: bool | None = None,
        org: str | None = None,
    ) -> Any:
        """Execute InfluxDB query asynchronously with caching.

        Args:
            query: Flux query string
            use_cache: Whether to use cache (uses default if None)
            org: InfluxDB organization

        Returns:
            Query results
        """
        if use_cache is None:
            use_cache = self.default_use_cache

        if not use_cache or not self.cache_manager.should_cache(query):
            # Execute directly
            query_api = self.influx_client.query_api()
            return await query_api.query(query, org=org)

        # Generate cache key
        cache_key = self.cache_manager.get_cache_key(query)
        ttl = self.cache_manager.get_ttl(query)

        # Try cache or execute
        def execute_query():
            query_api = self.influx_client.query_api()
            return query_api.query(query, org=org)

        return self.cache_manager.get_or_execute(
            cache_key,
            execute_query,
            ttl=ttl,
        )

    def invalidate_cache(self, pattern: str | None = None) -> int:
        """Invalidate cached queries.

        Args:
            pattern: Key pattern to match (None = all)

        Returns:
            Number of entries invalidated
        """
        return cast(int, self.cache_manager.invalidate(pattern))

    def get_metrics(self) -> dict[str, Any]:
        """Get cache metrics."""
        return cast(dict[str, Any], self.cache_manager.get_stats())
