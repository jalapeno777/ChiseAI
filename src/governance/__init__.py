"""
Governance module for ChiseAI.

This module provides governance capabilities including:
- Memory deduplication engine
- Audit and compliance utilities
- Retrieval baseline metrics
- Feature flag management
- Task sentinel enforcement utilities
- Swarm health monitoring and predictive alerting (ST-GOV-008)
- Parallel execution optimization (ST-GOV-010)
"""

from src.governance.audit import AuditSnapshot, RetrievalBaseline
from src.governance.memory import MemoryDeduplicationEngine
from src.governance.sentinel import SentinelConfig, TaskSentinel
from src.governance.health import (
    HealthSentinel,
    HealthSentinelConfig,
    HealthScorer,
    AgentHealthScore,
    SwarmHealthScore,
    HealthStatus,
)
from src.governance.parallel_optimizer import (
    ParallelOptimizer,
    OptimizerConfig,
    OptimizableTask,
    ExecutionPlan,
    TaskPriority,
)

__all__ = [
    "AuditSnapshot",
    "RetrievalBaseline",
    "MemoryDeduplicationEngine",
    "TaskSentinel",
    "SentinelConfig",
    # Health Sentinel (ST-GOV-008)
    "HealthSentinel",
    "HealthSentinelConfig",
    "HealthScorer",
    "AgentHealthScore",
    "SwarmHealthScore",
    "HealthStatus",
    # Parallel Optimizer (ST-GOV-010)
    "ParallelOptimizer",
    "OptimizerConfig",
    "OptimizableTask",
    "ExecutionPlan",
    "TaskPriority",
]
