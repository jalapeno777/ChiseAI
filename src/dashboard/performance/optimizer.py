"""Query optimization for dashboard panels.

Provides query optimization strategies, plan analysis, and
performance tuning for slow dashboard queries.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class QueryType(Enum):
    """Types of dashboard queries."""

    SIGNAL_LIST = "signal_list"
    SIGNAL_DETAIL = "signal_detail"
    MARKET_SUMMARY = "market_summary"
    KEY_LEVELS = "key_levels"
    REGIME_DETECTION = "regime_detection"
    HISTORICAL_CONTEXT = "historical_context"
    RISK_EXPOSURE = "risk_exposure"


@dataclass
class QueryMetrics:
    """Metrics for a single query execution.

    Attributes:
        query_type: Type of query
        execution_time_ms: Execution time in milliseconds
        rows_returned: Number of rows returned
        rows_scanned: Number of rows scanned (if available)
        cache_hit: Whether result was cached
        timestamp: Query execution timestamp
        optimization_applied: Whether optimization was applied
    """

    query_type: QueryType
    execution_time_ms: float
    rows_returned: int
    rows_scanned: int = 0
    cache_hit: bool = False
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    optimization_applied: bool = False

    @property
    def efficiency_ratio(self) -> float:
        """Calculate query efficiency (rows returned / rows scanned)."""
        if self.rows_scanned == 0:
            return 1.0
        return self.rows_returned / self.rows_scanned

    @property
    def is_slow(self) -> bool:
        """Check if query is slow (>1000ms or low efficiency)."""
        return self.execution_time_ms > 1000 or (
            self.rows_scanned > 0 and self.efficiency_ratio < 0.1
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "query_type": self.query_type.value,
            "execution_time_ms": round(self.execution_time_ms, 2),
            "rows_returned": self.rows_returned,
            "rows_scanned": self.rows_scanned,
            "efficiency_ratio": round(self.efficiency_ratio, 4),
            "cache_hit": self.cache_hit,
            "is_slow": self.is_slow,
            "optimization_applied": self.optimization_applied,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class QueryPlan:
    """Optimized query execution plan.

    Attributes:
        original_query: Original query string
        optimized_query: Optimized query string
        optimizations: List of applied optimizations
        estimated_improvement: Estimated improvement percentage
        indexes_used: Indexes recommended for this query
    """

    original_query: str
    optimized_query: str
    optimizations: list[str] = field(default_factory=list)
    estimated_improvement: float = 0.0
    indexes_used: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "original_query": (
                self.original_query[:200] + "..."
                if len(self.original_query) > 200
                else self.original_query
            ),
            "optimized_query": (
                self.optimized_query[:200] + "..."
                if len(self.optimized_query) > 200
                else self.optimized_query
            ),
            "optimizations": self.optimizations,
            "estimated_improvement": round(self.estimated_improvement, 2),
            "indexes_used": self.indexes_used,
        }


class QueryOptimizer:
    """Optimizer for dashboard database queries.

    Analyzes queries and applies optimizations to improve performance.
    Supports various optimization strategies including:
    - SELECT column limiting
    - JOIN optimization
    - WHERE clause optimization
    - Index recommendations
    """

    # Slow query patterns and their optimizations
    OPTIMIZATION_PATTERNS = {
        "select_star": {
            "pattern": r"SELECT\s+\*\s+FROM",
            "fix": "Replace SELECT * with specific columns",
            "improvement": 20,
        },
        "missing_where": {
            "pattern": r"FROM\s+\w+\s*;",
            "fix": "Add WHERE clause to limit rows",
            "improvement": 50,
        },
        "unindexed_order": {
            "pattern": r"ORDER\s+BY\s+\w+\s+(?:DESC|ASC)\s+LIMIT",
            "fix": "Consider adding index for ORDER BY column",
            "improvement": 30,
        },
        "subquery_in_where": {
            "pattern": r"WHERE\s+\w+\s+IN\s*\(",
            "fix": "Consider JOIN instead of subquery",
            "improvement": 40,
        },
        "like_prefix": {
            "pattern": r"LIKE\s+['\"]%",
            "fix": "Avoid leading wildcard in LIKE (prevents index use)",
            "improvement": 60,
        },
    }

    # Recommended indexes by query type
    RECOMMENDED_INDEXES = {
        QueryType.SIGNAL_LIST: [
            "CREATE INDEX IF NOT EXISTS idx_signals_token ON signals(token)",
            "CREATE INDEX IF NOT EXISTS idx_signals_confidence ON signals(confidence DESC)",
            "CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON signals(timestamp DESC)",
        ],
        QueryType.SIGNAL_DETAIL: [
            "CREATE INDEX IF NOT EXISTS idx_signal_detail_id ON signal_details(signal_id)",
            "CREATE INDEX IF NOT EXISTS idx_signal_factors ON signal_factors(signal_id)",
        ],
        QueryType.MARKET_SUMMARY: [
            "CREATE INDEX IF NOT EXISTS idx_market_token ON market_data(token)",
            "CREATE INDEX IF NOT EXISTS idx_market_timestamp ON market_data(timestamp DESC)",
        ],
        QueryType.KEY_LEVELS: [
            "CREATE INDEX IF NOT EXISTS idx_key_levels_token ON key_levels(token)",
            "CREATE INDEX IF NOT EXISTS idx_key_levels_type ON key_levels(level_type)",
        ],
        QueryType.HISTORICAL_CONTEXT: [
            "CREATE INDEX IF NOT EXISTS idx_historical_signal ON historical_signals(signal_id)",
            "CREATE INDEX IF NOT EXISTS idx_historical_outcome ON historical_signals(outcome)",
        ],
    }

    def __init__(self, slow_threshold_ms: float = 1000.0):
        """Initialize query optimizer.

        Args:
            slow_threshold_ms: Threshold for slow queries in milliseconds
        """
        self.slow_threshold_ms = slow_threshold_ms
        self._metrics_history: list[QueryMetrics] = []

    def analyze_query(self, query: str, query_type: QueryType) -> QueryPlan:
        """Analyze a query and generate optimization plan.

        Args:
            query: SQL query to analyze
            query_type: Type of dashboard query

        Returns:
            QueryPlan with optimizations
        """
        optimizations: list[str] = []
        estimated_improvement = 0.0
        optimized_query = query

        # Check for optimization patterns
        for _name, config in self.OPTIMIZATION_PATTERNS.items():
            if re.search(config["pattern"], query, re.IGNORECASE):
                optimizations.append(config["fix"])
                estimated_improvement += config["improvement"]

        # Apply basic optimizations
        optimized_query = self._apply_optimizations(query, optimizations)

        # Get recommended indexes
        indexes = self.RECOMMENDED_INDEXES.get(query_type, [])

        return QueryPlan(
            original_query=query,
            optimized_query=optimized_query,
            optimizations=optimizations,
            estimated_improvement=min(estimated_improvement, 80),  # Cap at 80%
            indexes_used=indexes,
        )

    def _apply_optimizations(self, query: str, optimizations: list[str]) -> str:
        """Apply optimizations to query.

        Args:
            query: Original query
            optimizations: List of optimizations to apply

        Returns:
            Optimized query string
        """
        optimized = query

        # Apply SELECT * optimization
        if "Replace SELECT * with specific columns" in optimizations:
            # This is a hint - actual implementation depends on context
            optimized = re.sub(
                r"SELECT\s+\*\s+FROM",
                "SELECT id, token, direction, confidence, timestamp FROM",
                optimized,
                flags=re.IGNORECASE,
            )

        # Add LIMIT if missing
        if "Add WHERE clause to limit rows" in optimizations:
            if "LIMIT" not in optimized.upper():
                optimized = optimized.rstrip(";") + " LIMIT 1000"

        return optimized

    def record_metrics(self, metrics: QueryMetrics) -> None:
        """Record query metrics for analysis.

        Args:
            metrics: Query execution metrics
        """
        self._metrics_history.append(metrics)

        # Keep last 1000 metrics
        if len(self._metrics_history) > 1000:
            self._metrics_history = self._metrics_history[-1000:]

    def get_slow_queries(self) -> list[QueryMetrics]:
        """Get list of slow queries.

        Returns:
            List of QueryMetrics for slow queries
        """
        return [m for m in self._metrics_history if m.is_slow]

    def get_metrics_summary(self) -> dict[str, Any]:
        """Get summary of recorded metrics.

        Returns:
            Dictionary with metrics summary
        """
        if not self._metrics_history:
            return {
                "total_queries": 0,
                "slow_queries": 0,
                "avg_time_ms": 0,
                "by_type": {},
            }

        by_type: dict[str, list[float]] = {}
        for m in self._metrics_history:
            if m.query_type.value not in by_type:
                by_type[m.query_type.value] = []
            by_type[m.query_type.value].append(m.execution_time_ms)

        type_stats = {}
        for qtype, times in by_type.items():
            type_stats[qtype] = {
                "count": len(times),
                "avg_ms": round(sum(times) / len(times), 2),
                "max_ms": round(max(times), 2),
            }

        slow_count = len(self.get_slow_queries())

        return {
            "total_queries": len(self._metrics_history),
            "slow_queries": slow_count,
            "avg_time_ms": round(
                sum(m.execution_time_ms for m in self._metrics_history)
                / len(self._metrics_history),
                2,
            ),
            "by_type": type_stats,
        }

    def get_index_recommendations(self) -> list[str]:
        """Get all recommended indexes.

        Returns:
            List of CREATE INDEX statements
        """
        all_indexes: set[str] = set()
        for indexes in self.RECOMMENDED_INDEXES.values():
            all_indexes.update(indexes)
        return sorted(all_indexes)


def optimize_panel_query(
    query: str,
    query_type: QueryType,
    params: dict[str, Any] | None = None,
) -> QueryPlan:
    """Optimize a dashboard panel query.

    Args:
        query: SQL query to optimize
        query_type: Type of dashboard query
        params: Optional query parameters

    Returns:
        QueryPlan with optimization recommendations

    Example:
        plan = optimize_panel_query(
            "SELECT * FROM signals WHERE token = ?",
            QueryType.SIGNAL_LIST
        )
        print(plan.optimizations)
    """
    optimizer = QueryOptimizer()
    return optimizer.analyze_query(query, query_type)
