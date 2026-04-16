"""Connection pooling module for exchange APIs.

Provides connection pool management, rate limiting, and health monitoring
for Bybit and Bitget exchange APIs.

For ST-NS-026: Connection Pooling for Exchange APIs
"""

from data.exchange.pooling.connection_pool import (
    ConnectionContextManager,
    ExchangeConnectionPool,
    PooledConnection,
    PoolMetrics,
)
from data.exchange.pooling.health_monitor import (
    ConnectionLifecycleEvent,
    HealthCheckResult,
    HealthReporter,
    PoolHealthMonitor,
)
from data.exchange.pooling.pooled_client import (
    OrderBook,
    OrderResult,
    PooledBitgetClient,
    PooledBybitClient,
    PooledExchangeClient,
)
from data.exchange.pooling.rate_limiter import (
    AdaptiveRateLimiter,
    CompositeRateLimiter,
    RateLimitConfig,
    RateLimitState,
    SlidingWindowRateLimiter,
    TokenBucketRateLimiter,
)

__all__ = [
    # Connection Pool
    "ExchangeConnectionPool",
    "PooledConnection",
    "ConnectionContextManager",
    "PoolMetrics",
    # Pooled Clients
    "PooledExchangeClient",
    "PooledBybitClient",
    "PooledBitgetClient",
    "OrderResult",
    "OrderBook",
    # Rate Limiting
    "TokenBucketRateLimiter",
    "SlidingWindowRateLimiter",
    "AdaptiveRateLimiter",
    "CompositeRateLimiter",
    "RateLimitConfig",
    "RateLimitState",
    # Health Monitoring
    "PoolHealthMonitor",
    "HealthCheckResult",
    "HealthReporter",
    "ConnectionLifecycleEvent",
]
