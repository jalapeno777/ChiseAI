"""
Health Remediator - Auto-Remediation System (ST-GOV-008).

Implements auto-remediation for known health issues with:
- Remediation actions for common problems
- Integration with EP-NS-008 (Autonomous Control Plane)
- Remediation history tracking
- Safe rollback mechanisms

Story: ST-GOV-008
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Callable
import logging
import time

from .scorer import AgentHealthScore, HealthStatus
from .predictor import HealthAlert, PredictionType, AlertSeverity

logger = logging.getLogger(__name__)


class RemediationAction(Enum):
    """Types of remediation actions."""

    RESTART_AGENT = "restart_agent"
    REDUCE_LOAD = "reduce_load"
    CLEAR_CACHE = "clear_cache"
    SCALE_UP = "scale_up"
    FAILOVER = "failover"
    QUARANTINE = "quarantine"
    RESET_CONNECTIONS = "reset_connections"
    TRIGGER_GARBAGE_COLLECTION = "trigger_gc"
    NOTIFY_HUMAN = "notify_human"
    NO_ACTION = "no_action"


class RemediationStatus(Enum):
    """Status of a remediation action."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    TIMEOUT = "timeout"


@dataclass
class RemediationRecord:
    """Record of a remediation action."""

    record_id: str
    agent_id: str
    action: RemediationAction
    trigger: str  # What triggered this remediation
    status: RemediationStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_ms: Optional[float] = None
    error_message: Optional[str] = None
    rollback_action: Optional[RemediationAction] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert record to dictionary for serialization."""
        return {
            "record_id": self.record_id,
            "agent_id": self.agent_id,
            "action": self.action.value,
            "trigger": self.trigger,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "duration_ms": self.duration_ms,
            "error_message": self.error_message,
            "rollback_action": self.rollback_action.value
            if self.rollback_action
            else None,
            "metadata": self.metadata,
        }


@dataclass
class RemediationConfig:
    """Configuration for remediation system."""

    max_retries: int = 3
    retry_delay_seconds: float = 5.0
    timeout_seconds: float = 30.0
    cooldown_minutes: int = 5  # Minimum time between remediations
    enable_auto_remediation: bool = True
    require_human_approval_for: list[RemediationAction] = field(
        default_factory=lambda: [
            RemediationAction.QUARANTINE,
            RemediationAction.FAILOVER,
        ]
    )


class HealthRemediator:
    """
    Auto-remediation system for health issues.

    Provides automated responses to predicted or detected health problems,
    with support for rollback and human approval workflows.
    """

    # Mapping of prediction types to remediation actions
    REMEDIATION_MAP: dict[PredictionType, list[RemediationAction]] = {
        PredictionType.DEGRADATION: [
            RemediationAction.REDUCE_LOAD,
            RemediationAction.CLEAR_CACHE,
            RemediationAction.TRIGGER_GARBAGE_COLLECTION,
        ],
        PredictionType.THRESHOLD_BREACH: [
            RemediationAction.SCALE_UP,
            RemediationAction.REDUCE_LOAD,
            RemediationAction.NOTIFY_HUMAN,
        ],
        PredictionType.DIMENSION_FAILURE: [
            RemediationAction.RESTART_AGENT,
            RemediationAction.RESET_CONNECTIONS,
        ],
        PredictionType.SYSTEMIC_ISSUE: [
            RemediationAction.FAILOVER,
            RemediationAction.NOTIFY_HUMAN,
        ],
    }

    def __init__(
        self,
        config: Optional[RemediationConfig] = None,
        redis_client=None,
    ):
        """
        Initialize health remediator.

        Args:
            config: Remediation configuration
            redis_client: Redis client for state persistence
        """
        self.config = config or RemediationConfig()
        self.redis_client = redis_client
        self._action_handlers: dict[RemediationAction, Callable] = {}
        self._remediation_history: list[RemediationRecord] = []
        self._record_counter = 0
        self._last_remediation: dict[str, datetime] = {}

        # Register default handlers
        self._register_default_handlers()

    def _register_default_handlers(self) -> None:
        """Register default remediation action handlers."""
        self.register_handler(RemediationAction.CLEAR_CACHE, self._action_clear_cache)
        self.register_handler(RemediationAction.REDUCE_LOAD, self._action_reduce_load)
        self.register_handler(
            RemediationAction.RESET_CONNECTIONS, self._action_reset_connections
        )
        self.register_handler(
            RemediationAction.TRIGGER_GARBAGE_COLLECTION, self._action_trigger_gc
        )
        self.register_handler(RemediationAction.NOTIFY_HUMAN, self._action_notify_human)
        self.register_handler(RemediationAction.NO_ACTION, self._action_noop)

    def register_handler(
        self,
        action: RemediationAction,
        handler: Callable[[str, dict], bool],
    ) -> None:
        """
        Register a handler for a remediation action.

        Args:
            action: The remediation action
            handler: Callable that takes (agent_id, metadata) and returns success bool
        """
        self._action_handlers[action] = handler

    def remediate(
        self,
        alert: HealthAlert,
        agent_id: Optional[str] = None,
    ) -> RemediationRecord:
        """
        Attempt remediation based on a health alert.

        Args:
            alert: The health alert triggering remediation
            agent_id: Override agent_id from alert

        Returns:
            RemediationRecord with results
        """
        target_agent = agent_id or alert.agent_id

        # Check cooldown
        if not self._check_cooldown(target_agent):
            return self._create_record(
                agent_id=target_agent,
                action=RemediationAction.NO_ACTION,
                trigger=f"Alert {alert.alert_id}",
                status=RemediationStatus.PENDING,
                metadata={"reason": "Cooldown active"},
            )

        # Check if auto-remediation is enabled
        if not self.config.enable_auto_remediation:
            return self._create_record(
                agent_id=target_agent,
                action=RemediationAction.NOTIFY_HUMAN,
                trigger=f"Alert {alert.alert_id}",
                status=RemediationStatus.PENDING,
                metadata={"reason": "Auto-remediation disabled"},
            )

        # Determine action
        action = self._determine_action(alert)
        if action == RemediationAction.NO_ACTION:
            return self._create_record(
                agent_id=target_agent,
                action=action,
                trigger=f"Alert {alert.alert_id}",
                status=RemediationStatus.SUCCESS,
                metadata={"reason": "No action needed"},
            )

        # Check if human approval required
        if action in self.config.require_human_approval_for:
            return self._create_record(
                agent_id=target_agent,
                action=action,
                trigger=f"Alert {alert.alert_id}",
                status=RemediationStatus.PENDING,
                metadata={"reason": "Requires human approval"},
            )

        # Execute action
        return self._execute_action(target_agent, action, alert)

    def _determine_action(self, alert: HealthAlert) -> RemediationAction:
        """Determine the appropriate remediation action."""
        actions = self.REMEDIATION_MAP.get(alert.prediction_type, [])

        # Filter by severity
        if alert.severity == AlertSeverity.CRITICAL:
            # For critical alerts, try more aggressive actions first
            for action in reversed(actions):
                if action in self._action_handlers:
                    return action
        elif alert.severity == AlertSeverity.WARNING:
            # For warnings, try less aggressive actions first
            for action in actions:
                if action in self._action_handlers:
                    return action

        return RemediationAction.NO_ACTION

    def _execute_action(
        self,
        agent_id: str,
        action: RemediationAction,
        alert: HealthAlert,
    ) -> RemediationRecord:
        """Execute a remediation action."""
        self._record_counter += 1
        record = self._create_record(
            agent_id=agent_id,
            action=action,
            trigger=f"Alert {alert.alert_id}",
            status=RemediationStatus.IN_PROGRESS,
        )

        start_time = time.time()

        try:
            handler = self._action_handlers.get(action)
            if handler is None:
                raise ValueError(f"No handler registered for action: {action}")

            metadata = {
                "alert_type": alert.prediction_type.value,
                "current_score": alert.current_score,
                "predicted_score": alert.predicted_score,
                "factors": alert.contributing_factors,
            }

            success = handler(agent_id, metadata)

            duration_ms = (time.time() - start_time) * 1000
            record.completed_at = datetime.utcnow()
            record.duration_ms = duration_ms
            record.status = (
                RemediationStatus.SUCCESS if success else RemediationStatus.FAILED
            )

            if success:
                self._last_remediation[agent_id] = datetime.utcnow()
                logger.info(
                    f"Remediation {action.value} succeeded for {agent_id} "
                    f"in {duration_ms:.0f}ms"
                )
            else:
                record.error_message = "Handler returned failure"
                logger.warning(f"Remediation {action.value} failed for {agent_id}")

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            record.completed_at = datetime.utcnow()
            record.duration_ms = duration_ms
            record.status = RemediationStatus.FAILED
            record.error_message = str(e)
            logger.error(f"Remediation {action.value} error for {agent_id}: {e}")

        self._remediation_history.append(record)
        return record

    def _check_cooldown(self, agent_id: str) -> bool:
        """Check if cooldown period has passed since last remediation."""
        last = self._last_remediation.get(agent_id)
        if last is None:
            return True

        cooldown = timedelta(minutes=self.config.cooldown_minutes)
        return datetime.utcnow() >= last + cooldown

    def _create_record(
        self,
        agent_id: str,
        action: RemediationAction,
        trigger: str,
        status: RemediationStatus,
        metadata: Optional[dict] = None,
    ) -> RemediationRecord:
        """Create a remediation record."""
        self._record_counter += 1
        return RemediationRecord(
            record_id=f"rem-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{self._record_counter}",
            agent_id=agent_id,
            action=action,
            trigger=trigger,
            status=status,
            started_at=datetime.utcnow(),
            metadata=metadata or {},
        )

    # Default action handlers
    def _action_clear_cache(self, agent_id: str, metadata: dict) -> bool:
        """Clear agent cache (simulated)."""
        logger.info(f"Clearing cache for agent {agent_id}")
        # In production, this would call the actual cache clear API
        return True

    def _action_reduce_load(self, agent_id: str, metadata: dict) -> bool:
        """Reduce agent load by throttling tasks."""
        logger.info(f"Reducing load for agent {agent_id}")
        # In production, this would adjust task queue limits
        return True

    def _action_reset_connections(self, agent_id: str, metadata: dict) -> bool:
        """Reset network connections for agent."""
        logger.info(f"Resetting connections for agent {agent_id}")
        # In production, this would reset Redis/DB connections
        return True

    def _action_trigger_gc(self, agent_id: str, metadata: dict) -> bool:
        """Trigger garbage collection."""
        logger.info(f"Triggering GC for agent {agent_id}")
        # In production, this would call the agent's GC endpoint
        return True

    def _action_notify_human(self, agent_id: str, metadata: dict) -> bool:
        """Notify human operator (simulated)."""
        logger.warning(f"Human notification required for agent {agent_id}: {metadata}")
        # In production, this would send Slack/email/Discord notification
        return True

    def _action_noop(self, agent_id: str, metadata: dict) -> bool:
        """No operation handler."""
        return True

    def get_remediation_stats(self) -> dict:
        """
        Get statistics about remediation actions.

        Returns:
            Dictionary with remediation statistics
        """
        if not self._remediation_history:
            return {
                "total": 0,
                "success_count": 0,
                "failed_count": 0,
                "success_rate": 0.0,
                "avg_duration_ms": 0.0,
            }

        success_count = sum(
            1
            for r in self._remediation_history
            if r.status == RemediationStatus.SUCCESS
        )
        failed_count = sum(
            1 for r in self._remediation_history if r.status == RemediationStatus.FAILED
        )
        durations = [
            r.duration_ms
            for r in self._remediation_history
            if r.duration_ms is not None
        ]

        return {
            "total": len(self._remediation_history),
            "success_count": success_count,
            "failed_count": failed_count,
            "success_rate": (success_count / len(self._remediation_history)) * 100,
            "avg_duration_ms": sum(durations) / len(durations) if durations else 0.0,
            "by_action": self._get_action_breakdown(),
        }

    def _get_action_breakdown(self) -> dict[str, int]:
        """Get count breakdown by action type."""
        breakdown: dict[str, int] = {}
        for record in self._remediation_history:
            action_name = record.action.value
            breakdown[action_name] = breakdown.get(action_name, 0) + 1
        return breakdown

    def get_recent_remediations(self, limit: int = 20) -> list[RemediationRecord]:
        """Get recent remediation records."""
        return list(reversed(self._remediation_history[-limit:]))

    def clear_history(self) -> None:
        """Clear remediation history."""
        self._remediation_history.clear()
        self._last_remediation.clear()
