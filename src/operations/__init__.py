"""Operations module for ChiseAI.

This module provides operational utilities including:
- Iteration logging for BMAD workflow compliance
- Data quality monitoring
- Continuous backtest runner
"""

from __future__ import annotations

from operations.backtest_runner import (
    BacktestKPIs,
    BacktestRunner,
    BacktestStatus,
    CircuitBreaker,
    CircuitBreakerState,
    InfluxDBKPIStorage,
    QueueMetrics,
    Trade,
    generate_kpis,
    persist_kpis,
    run_backtest,
)
from operations.data_quality_monitoring import (
    DataQualityMonitor,
    GapAlert,
)
from operations.iteration_logging import (
    IterationLogEntry,
    check_ttl_validity,
    close_iteration,
    get_iteration_log,
    log_completion,
    log_decision,
    log_iteration_start,
    log_learning,
    promote_to_qdrant,
    query_by_story_pattern,
    validate_iteration_schema,
    validate_story_completeness,
)

__all__ = [
    # Backtest runner
    "BacktestRunner",
    "BacktestKPIs",
    "BacktestStatus",
    "CircuitBreaker",
    "CircuitBreakerState",
    "InfluxDBKPIStorage",
    "QueueMetrics",
    "Trade",
    "run_backtest",
    "generate_kpis",
    "persist_kpis",
    # Data quality
    "DataQualityMonitor",
    "GapAlert",
    # Iteration logging
    "IterationLogEntry",
    "log_iteration_start",
    "log_decision",
    "log_learning",
    "log_completion",
    "close_iteration",
    "get_iteration_log",
    "query_by_story_pattern",
    "validate_iteration_schema",
    "check_ttl_validity",
    "validate_story_completeness",
    "promote_to_qdrant",
]
