"""Dashboard performance optimization package.

This package provides caching, query optimization, and performance monitoring
for dashboard components to ensure load times under 3 seconds.

Components:
- QueryCache: Redis-backed caching for frequently accessed data
- QueryOptimizer: Optimizes database queries for slow panels
- PerformanceMonitor: Tracks and reports dashboard performance metrics
"""

from dashboard.performance.cache import (
    CacheKeyBuilder,
    CacheStats,
    DashboardCache,
    cached_query,
)
from dashboard.performance.monitor import (
    LoadTimeMetric,
    PerformanceAlert,
    PerformanceMonitor,
    PerformanceThresholds,
)
from dashboard.performance.optimizer import (
    QueryMetrics,
    QueryOptimizer,
    QueryPlan,
    QueryType,
    optimize_panel_query,
)

__all__ = [
    # Cache
    "DashboardCache",
    "CacheKeyBuilder",
    "CacheStats",
    "cached_query",
    # Monitor
    "PerformanceMonitor",
    "LoadTimeMetric",
    "PerformanceAlert",
    "PerformanceThresholds",
    # Optimizer
    "QueryOptimizer",
    "QueryMetrics",
    "QueryPlan",
    "QueryType",
    "optimize_panel_query",
]
