"""
Swarm Health Sentinel Module (ST-GOV-008).

This module provides comprehensive health monitoring for the ChiseAI
agent swarm with predictive alerting and auto-remediation.

Features:
- Real-time health scoring per agent
- Aggregated swarm health score
- Predictive alerts (detect issues 15 min before impact)
- Auto-remediation for known issues
- Integration with EP-NS-008 (Autonomous Control Plane)

Health Dimensions (weighted):
- Performance (25%): task_completion_time, pr_merge_time, ci_duration
- Quality (25%): bug_escape_rate, review_rejection_rate, rollback_frequency
- Reliability (25%): uptime, error_rate, recovery_time
- Collaboration (25%): conflict_rate, handoff_success, knowledge_sharing

Feature Flag: chise:feature_flags:governance:health_sentinel_active

Story: ST-GOV-008
Epic: EP-GOV-001
"""

from .metrics import (
    HealthMetricPoint,
    HealthMetrics,
    get_health_metrics,
)
from .predictor import (
    AlertSeverity,
    HealthAlert,
    HealthPredictor,
    PredictionConfig,
    PredictionType,
)
from .remediator import (
    HealthRemediator,
    RemediationAction,
    RemediationConfig,
    RemediationRecord,
    RemediationStatus,
)
from .scorer import (
    AgentHealthScore,
    DimensionConfig,
    HealthDimension,
    HealthScorer,
    HealthStatus,
    SwarmHealthScore,
)
from .degradation import (
    DegradationEvent,
    DegradationLevel,
    DegradationTracker,
)
from .sentinel import (
    HealthSentinel,
    HealthSentinelConfig,
    HealthSnapshot,
)

__all__ = [
    # Main sentinel
    "HealthSentinel",
    "HealthSentinelConfig",
    "HealthSnapshot",
    # Scoring
    "HealthScorer",
    "AgentHealthScore",
    "SwarmHealthScore",
    "HealthStatus",
    "HealthDimension",
    "DimensionConfig",
    # Prediction
    "HealthPredictor",
    "HealthAlert",
    "PredictionConfig",
    "PredictionType",
    "AlertSeverity",
    # Remediation
    "HealthRemediator",
    "RemediationRecord",
    "RemediationConfig",
    "RemediationAction",
    "RemediationStatus",
    # Metrics
    "HealthMetrics",
    "HealthMetricPoint",
    "get_health_metrics",
    # Degradation tracking
    "DegradationTracker",
    "DegradationLevel",
    "DegradationEvent",
]
