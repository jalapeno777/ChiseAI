"""Cache strategies for query result caching.

Provides TTL strategies and query type classification for cache management.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum, auto


class QueryType(Enum):
    """Classification of query types for caching purposes."""

    REALTIME = auto()  # Last 1 hour data - high frequency updates
    HISTORICAL = auto()  # 1 day+ data - relatively static
    SIGNAL = auto()  # Signal data - medium frequency
    STATIC = auto()  # Config/metadata - rarely changes
    UNKNOWN = auto()  # Unclassified


@dataclass(frozen=True)
class TTLStrategy:
    """TTL configuration for different query types."""

    realtime_ttl: int = 300  # 5 minutes
    historical_ttl: int = 3600  # 1 hour
    signal_ttl: int = 60  # 1 minute
    static_ttl: int = 86400  # 24 hours
    default_ttl: int = 300  # 5 minutes

    def get_ttl(self, query_type: QueryType) -> int:
        """Get TTL in seconds for a query type.

        Args:
            query_type: Type of query

        Returns:
            TTL in seconds
        """
        ttl_map = {
            QueryType.REALTIME: self.realtime_ttl,
            QueryType.HISTORICAL: self.historical_ttl,
            QueryType.SIGNAL: self.signal_ttl,
            QueryType.STATIC: self.static_ttl,
            QueryType.UNKNOWN: self.default_ttl,
        }
        return ttl_map.get(query_type, self.default_ttl)


class CacheStrategy:
    """Strategy for cache key generation and query classification.

    Determines how queries are classified and how cache keys are generated
    based on query content and time bucketing.
    """

    # Time bucket sizes in seconds
    REALTIME_BUCKET_SIZE = 300  # 5 minutes
    HISTORICAL_BUCKET_SIZE = 3600  # 1 hour
    SIGNAL_BUCKET_SIZE = 60  # 1 minute
    STATIC_BUCKET_SIZE = 86400  # 24 hours

    # Patterns for query classification
    REALTIME_PATTERNS = [
        r"now\(\)\s*-\s*1h",
        r"now\s*-\s*1h",
        r"now\(\)\s*-\s*60m",
        r"now\s*-\s*60m",
        r"time\s*>\s*now\(\)\s*-\s*1h",
        r"time\s*>\s*now\s*-\s*1h",
        r"range\(start:\s*-1h",
        r"range\(start:\s*-60m",
    ]

    HISTORICAL_PATTERNS = [
        r"now\(\)\s*-\s*1d",
        r"now\s*-\s*1d",
        r"now\(\)\s*-\s*7d",
        r"now\s*-\s*7d",
        r"now\(\)\s*-\s*30d",
        r"now\s*-\s*30d",
        r"range\(start:\s*-1d",
        r"range\(start:\s*-7d",
        r"range\(start:\s*-30d",
        r"range\(start:\s*-90d",
    ]

    SIGNAL_PATTERNS = [
        r"trading_signals",
        r"signal_",
        r"outcome",
    ]

    STATIC_PATTERNS = [
        r"config",
        r"metadata",
        r"schema",
        r"version",
    ]

    def __init__(self, ttl_strategy: TTLStrategy | None = None) -> None:
        """Initialize cache strategy.

        Args:
            ttl_strategy: TTL configuration (uses defaults if None)
        """
        self.ttl_strategy = ttl_strategy or TTLStrategy()
        self._realtime_regex = re.compile(
            "|".join(self.REALTIME_PATTERNS), re.IGNORECASE
        )
        self._historical_regex = re.compile(
            "|".join(self.HISTORICAL_PATTERNS), re.IGNORECASE
        )
        self._signal_regex = re.compile("|".join(self.SIGNAL_PATTERNS), re.IGNORECASE)
        self._static_regex = re.compile("|".join(self.STATIC_PATTERNS), re.IGNORECASE)

    def classify_query(self, query: str) -> QueryType:
        """Classify a query based on its content.

        Args:
            query: Query string (SQL, Flux, etc.)

        Returns:
            QueryType classification
        """
        query_lower = query.lower()

        # Check patterns in order of specificity
        if self._static_regex.search(query_lower):
            return QueryType.STATIC

        if self._historical_regex.search(query_lower):
            return QueryType.HISTORICAL

        if self._realtime_regex.search(query_lower):
            return QueryType.REALTIME

        if self._signal_regex.search(query_lower):
            return QueryType.SIGNAL

        return QueryType.UNKNOWN

    def get_time_bucket(self, query_type: QueryType) -> str:
        """Get current time bucket for a query type.

        Args:
            query_type: Type of query

        Returns:
            Time bucket string (ISO format truncated to bucket size)
        """
        now = datetime.now(UTC)

        bucket_sizes = {
            QueryType.REALTIME: self.REALTIME_BUCKET_SIZE,
            QueryType.HISTORICAL: self.HISTORICAL_BUCKET_SIZE,
            QueryType.SIGNAL: self.SIGNAL_BUCKET_SIZE,
            QueryType.STATIC: self.STATIC_BUCKET_SIZE,
            QueryType.UNKNOWN: self.REALTIME_BUCKET_SIZE,
        }

        bucket_size = bucket_sizes.get(query_type, self.REALTIME_BUCKET_SIZE)

        # Truncate to bucket boundary
        epoch_seconds = int(now.timestamp())
        bucket_start = (epoch_seconds // bucket_size) * bucket_size
        bucket_dt = datetime.fromtimestamp(bucket_start, tz=UTC)

        return bucket_dt.isoformat()

    def normalize_query(self, query: str) -> str:
        """Normalize query string for consistent hashing.

        Removes extra whitespace, converts to lowercase, and normalizes
        common variations.

        Args:
            query: Raw query string

        Returns:
            Normalized query string
        """
        # Convert to lowercase
        normalized = query.lower()

        # Remove extra whitespace
        normalized = " ".join(normalized.split())

        # Remove comments (SQL style)
        normalized = re.sub(r"--[^\n]*", "", normalized)
        normalized = re.sub(r"/\*.*?\*/", "", normalized, flags=re.DOTALL)

        return normalized.strip()

    def generate_cache_key(
        self, query: str, query_type: QueryType | None = None
    ) -> str:
        """Generate a cache key for a query.

        Format: query:{hash}:{time_bucket}

        Args:
            query: Query string
            query_type: Optional pre-computed query type

        Returns:
            Cache key string
        """
        if query_type is None:
            query_type = self.classify_query(query)

        normalized = self.normalize_query(query)
        query_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
        time_bucket = self.get_time_bucket(query_type)

        return f"query:{query_hash}:{time_bucket}"

    def get_ttl(self, query: str | QueryType) -> int:
        """Get TTL for a query or query type.

        Args:
            query: Query string or QueryType

        Returns:
            TTL in seconds
        """
        query_type = self.classify_query(query) if isinstance(query, str) else query
        return self.ttl_strategy.get_ttl(query_type)

    def should_cache(self, query: str) -> bool:
        """Determine if a query should be cached.

        Args:
            query: Query string

        Returns:
            True if query should be cached
        """
        # Don't cache very short queries (likely errors)
        if len(query.strip()) < 10:
            return False

        query_lower = query.lower()

        # Check for explicit no-cache hints
        return not ("/* no-cache */" in query_lower or "-- no-cache" in query_lower)

    def get_invalidation_pattern(self, query_type: QueryType) -> str:
        """Get Redis key pattern for invalidating a query type.

        Args:
            query_type: Type of query to invalidate

        Returns:
            Redis key pattern for SCAN/DEL
        """
        return "query:*"
