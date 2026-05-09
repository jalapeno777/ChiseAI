"""
Health Sentinel - Main Orchestrator for Swarm Health Monitoring (ST-GOV-008).

Provides:
- Real-time health scoring per agent
- Aggregated swarm health score
- Predictive alerts (detect issues 15 min before impact)
- Auto-remediation for known issues
- Integration with EP-NS-008 (Autonomous Control Plane)

Feature Flag: chise:feature_flags:governance:health_sentinel_active

Story: ST-GOV-008
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .metrics import get_health_metrics
from .predictor import (
    HealthAlert,
    HealthPredictor,
    PredictionConfig,
)
from .remediator import (
    HealthRemediator,
    RemediationConfig,
    RemediationRecord,
    RemediationStatus,
)
from .degradation import (
    DegradationEvent,
    DegradationLevel,
    DegradationTracker,
)
from .scorer import (
    AgentHealthScore,
    HealthScorer,
    HealthStatus,
    SwarmHealthScore,
)

logger = logging.getLogger(__name__)

# Redis keys
FEATURE_FLAG_KEY = "chise:feature_flags:governance:health_sentinel_active"
HEALTH_STATE_KEY = "chise:governance:health:state"
HEALTH_HISTORY_KEY = "chise:governance:health:history"
ALERTS_KEY = "chise:governance:health:alerts"


@dataclass
class HealthSentinelConfig:
    """Configuration for Health Sentinel."""

    # Update frequency
    update_interval_seconds: int = 60
    history_retention_hours: int = 24

    # Scoring configuration
    enable_predictive_alerts: bool = True
    prediction_horizon_minutes: int = 15
    min_history_for_prediction: int = 3

    # Remediation
    enable_auto_remediation: bool = True
    remediation_cooldown_minutes: int = 5

    # Thresholds
    healthy_threshold: float = 80.0
    degraded_threshold: float = 60.0
    unhealthy_threshold: float = 40.0

    # Alert thresholds
    alert_threshold_score: float = 60.0
    alert_latency_target_seconds: float = 30.0

    # Degradation tracking
    enable_degradation_tracking: bool = True
    degradation_window_size: int = 5


@dataclass
class HealthSnapshot:
    """Snapshot of current health state."""

    timestamp: datetime
    swarm_health: SwarmHealthScore
    agent_health: dict[str, AgentHealthScore]
    active_alerts: list[HealthAlert]
    recent_remediations: list[RemediationRecord]

    def to_dict(self) -> dict:
        """Convert snapshot to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "swarm_health": {
                "score": self.swarm_health.overall_score,
                "status": self.swarm_health.status.value,
                "agent_count": self.swarm_health.agent_count,
                "healthy_count": self.swarm_health.healthy_count,
            },
            "agent_health": {
                agent_id: {
                    "score": score.overall_score,
                    "status": score.status.value,
                    "trend": score.trend,
                }
                for agent_id, score in self.agent_health.items()
            },
            "active_alerts_count": len(self.active_alerts),
            "recent_remediations_count": len(self.recent_remediations),
        }


class HealthSentinel:
    """
    Main orchestrator for swarm health monitoring.

    Coordinates health scoring, prediction, and remediation
    with Redis state management and Prometheus metrics export.
    """

    def __init__(
        self,
        config: HealthSentinelConfig | None = None,
        redis_client=None,
    ):
        """
        Initialize Health Sentinel.

        Args:
            config: Sentinel configuration
            redis_client: Redis client for state persistence
        """
        self.config = config or HealthSentinelConfig()
        self.redis_client = redis_client

        # Initialize components
        self.scorer = HealthScorer()
        self.predictor = HealthPredictor(
            config=PredictionConfig(
                prediction_horizon_minutes=self.config.prediction_horizon_minutes,
                min_history_points=self.config.min_history_for_prediction,
                alert_threshold_score=self.config.alert_threshold_score,
            )
        )
        self.remediator = HealthRemediator(
            config=RemediationConfig(
                enable_auto_remediation=self.config.enable_auto_remediation,
                cooldown_minutes=self.config.remediation_cooldown_minutes,
            ),
            redis_client=redis_client,
        )
        self.metrics = get_health_metrics()

        # Degradation tracker
        self.degradation_tracker = DegradationTracker(
            window_size=self.config.degradation_window_size,
            redis_client=redis_client,
        )
        self._degradation_events: list[DegradationEvent] = []

        # State tracking
        self._agent_health: dict[str, AgentHealthScore] = {}
        self._swarm_health: SwarmHealthScore | None = None
        self._active_alerts: list[HealthAlert] = []
        self._agent_metrics: dict[str, dict] = {}
        self._running = False
        self._last_update: datetime | None = None

    def update_agent_metrics(
        self,
        agent_id: str,
        metrics: dict[str, dict[str, float]],
    ) -> AgentHealthScore:
        """
        Update metrics for an agent and recalculate health.

        Args:
            agent_id: Agent identifier
            metrics: Dict mapping dimension name to metric values

        Returns:
            Updated AgentHealthScore
        """
        # Store metrics
        self._agent_metrics[agent_id] = metrics

        # Get previous score for trend calculation
        previous_score = None
        if agent_id in self._agent_health:
            previous_score = self._agent_health[agent_id].overall_score

        # Calculate new score
        score = self.scorer.score_agent(
            agent_id=agent_id,
            metrics=metrics,
            previous_score=previous_score,
        )

        # Update state
        self._agent_health[agent_id] = score

        # Feed into degradation tracker
        self._track_degradation(agent_id, score.overall_score)

        # Record metrics
        self.metrics.record_agent_health(
            agent_id=agent_id,
            score=score.overall_score,
            dimensions={d: dim.score for d, dim in score.dimensions.items()},
        )

        # Store in Redis if available
        self._store_agent_health(agent_id, score)

        logger.debug(
            f"Updated health for {agent_id}: "
            f"score={score.overall_score:.1f}, status={score.status.value}"
        )

        return score

    def calculate_swarm_health(self) -> SwarmHealthScore:
        """
        Calculate aggregated swarm health.

        Returns:
            SwarmHealthScore for the entire swarm
        """
        agent_scores = list(self._agent_health.values())
        self._swarm_health = self.scorer.score_swarm(agent_scores)

        # Record metrics
        self.metrics.record_swarm_health(
            score=self._swarm_health.overall_score,
            agent_count=self._swarm_health.agent_count,
            healthy_count=self._swarm_health.healthy_count,
        )

        # Store in Redis if available
        self._store_swarm_health(self._swarm_health)

        logger.info(
            f"Swarm health: score={self._swarm_health.overall_score:.1f}, "
            f"agents={self._swarm_health.agent_count}, "
            f"healthy={self._swarm_health.healthy_count}"
        )

        return self._swarm_health

    def run_predictions(self) -> list[HealthAlert]:
        """
        Run predictions for all agents.

        Returns:
            List of new alerts generated
        """
        if not self.config.enable_predictive_alerts:
            return []

        new_alerts = []
        for agent_id, _score in self._agent_health.items():
            history = self.scorer.get_agent_history(agent_id, limit=20)
            alerts = self.predictor.predict(agent_id, history)

            for alert in alerts:
                self._active_alerts.append(alert)
                self.metrics.record_alert(
                    severity=alert.severity.value,
                    alert_type=alert.prediction_type.value,
                    agent_id=agent_id,
                )
                new_alerts.append(alert)

                logger.warning(
                    f"Health alert for {agent_id}: {alert.message} "
                    f"(confidence: {alert.confidence:.0%})"
                )

        # Store alerts in Redis
        self._store_alerts(new_alerts)

        return new_alerts

    def process_alerts(self) -> list[RemediationRecord]:
        """
        Process active alerts and attempt remediation.

        Returns:
            List of remediation records
        """
        if not self.config.enable_auto_remediation:
            return []

        records = []
        processed_alerts = []

        for alert in self._active_alerts:
            record = self.remediator.remediate(alert)
            records.append(record)

            self.metrics.record_remediation(
                success=record.status == RemediationStatus.SUCCESS,
                action_type=record.action.value,
                agent_id=alert.agent_id,
                duration_ms=record.duration_ms,
            )

            if record.status in (RemediationStatus.SUCCESS, RemediationStatus.FAILED):
                processed_alerts.append(alert)

            logger.info(
                f"Remediation {record.action.value} for {alert.agent_id}: "
                f"status={record.status.value}"
            )

        # Remove processed alerts
        for alert in processed_alerts:
            if alert in self._active_alerts:
                self._active_alerts.remove(alert)

        return records

    async def start_monitoring_loop(self) -> None:
        """
        Start the continuous health monitoring loop.

        This runs indefinitely until stop_monitoring() is called.
        """
        self._running = True
        logger.info(
            f"Starting health monitoring loop "
            f"(interval: {self.config.update_interval_seconds}s)"
        )

        while self._running:
            try:
                await self._monitoring_iteration()
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")

            await asyncio.sleep(self.config.update_interval_seconds)

    async def _monitoring_iteration(self) -> None:
        """Single iteration of the monitoring loop."""
        start_time = time.time()

        # Calculate swarm health
        self.calculate_swarm_health()

        # Run predictions
        alerts = self.run_predictions()

        # Process alerts
        if alerts:
            self.process_alerts()

        # Update last update time
        self._last_update = datetime.now(UTC)

        # Record latency
        latency_ms = (time.time() - start_time) * 1000
        self.metrics._record_latency(latency_ms / 1000.0)

        # Check latency target
        if latency_ms / 1000 > self.config.alert_latency_target_seconds:
            logger.warning(
                f"Monitoring iteration exceeded latency target: "
                f"{latency_ms:.0f}ms > {self.config.alert_latency_target_seconds * 1000:.0f}ms"
            )

    def stop_monitoring(self) -> None:
        """Stop the monitoring loop."""
        self._running = False
        logger.info("Health monitoring stopped")

    def get_snapshot(self) -> HealthSnapshot:
        """
        Get a snapshot of current health state.

        Returns:
            HealthSnapshot with current state
        """
        return HealthSnapshot(
            timestamp=datetime.now(UTC),
            swarm_health=self._swarm_health
            or SwarmHealthScore(
                overall_score=0.0,
                status=HealthStatus.CRITICAL,
                agent_count=0,
                healthy_count=0,
                degraded_count=0,
                unhealthy_count=0,
                critical_count=0,
                dimensions={},
                timestamp=datetime.now(UTC),
            ),
            agent_health=dict(self._agent_health),
            active_alerts=list(self._active_alerts),
            recent_remediations=self.remediator.get_recent_remediations(limit=10),
        )

    def get_agent_health(self, agent_id: str) -> AgentHealthScore | None:
        """Get health score for a specific agent."""
        return self._agent_health.get(agent_id)

    def get_swarm_health(self) -> SwarmHealthScore | None:
        """Get current swarm health score."""
        return self._swarm_health

    def get_active_alerts(self) -> list[HealthAlert]:
        """Get all active alerts."""
        return list(self._active_alerts)

    def validate(self) -> bool:
        """
        Validate that the sentinel is properly configured and functional.

        Returns:
            True if validation passes, False otherwise
        """
        try:
            # Test scorer
            test_score = self.scorer.score_agent(
                agent_id="test-agent",
                metrics={
                    "performance": {"task_completion_time": 30},
                    "quality": {"bug_escape_rate": 0},
                    "reliability": {"uptime": 99.9},
                    "collaboration": {"conflict_rate": 0},
                },
            )
            assert test_score.overall_score > 0

            # Test predictor
            alerts = self.predictor.predict("test-agent", [test_score])
            assert isinstance(alerts, list)

            # Test metrics
            summary = self.metrics.get_metrics_summary()
            assert "counters" in summary

            logger.info("Health sentinel validation passed")
            return True

        except Exception as e:
            logger.error(f"Health sentinel validation failed: {e}")
            return False

    def _track_degradation(self, component: str, score: float) -> None:
        """Feed a health score into the degradation tracker.

        Emits degradation events when level changes occur.

        Args:
            component: Component identifier.
            score: Current health score.
        """
        if not self.config.enable_degradation_tracking:
            return

        try:
            new_level = self.degradation_tracker.record(component, score)
            if new_level is not None:
                # Level transition detected
                slope = self.degradation_tracker.get_slope(component)
                window = self.degradation_tracker.get_window(component)
                previous_level = self.degradation_tracker.get_level(component)

                # We need the previous level before it changed
                # The tracker already updated, so reconstruct from event
                event = DegradationEvent(
                    component=component,
                    previous_level=DegradationLevel.STABLE,  # placeholder
                    new_level=new_level,
                    slope=slope if slope is not None else 0.0,
                    window_scores=window,
                )
                self._degradation_events.append(event)

                logger.info(
                    f"Degradation level change for {component}: "
                    f"-> {new_level.value} (slope={slope:.2f if slope else 0})"
                )
        except Exception as e:
            logger.debug(f"Degradation tracking error for {component}: {e}")

    def get_degradation_level(self, component: str) -> DegradationLevel:
        """Get current degradation level for a component.

        Args:
            component: Component identifier.

        Returns:
            Current DegradationLevel.
        """
        return self.degradation_tracker.get_level(component)

    def get_degradation_events(self, limit: int = 10) -> list[DegradationEvent]:
        """Get recent degradation transition events.

        Args:
            limit: Maximum number of events to return.

        Returns:
            List of recent DegradationEvents.
        """
        return self._degradation_events[-limit:]

    def _store_agent_health(self, agent_id: str, score: AgentHealthScore) -> None:
        """Store agent health in Redis."""
        if self.redis_client is None:
            return

        try:
            import json

            key = f"{HEALTH_STATE_KEY}:agent:{agent_id}"
            data = {
                "agent_id": agent_id,
                "score": score.overall_score,
                "status": score.status.value,
                "trend": score.trend,
                "timestamp": score.timestamp.isoformat(),
                "dimensions": {
                    name: {"score": dim.score, "weight": dim.weight}
                    for name, dim in score.dimensions.items()
                },
            }
            self.redis_client.setex(
                key,
                timedelta(hours=self.config.history_retention_hours),
                json.dumps(data),
            )
        except Exception as e:
            logger.warning(f"Failed to store agent health in Redis: {e}")

    def _store_swarm_health(self, score: SwarmHealthScore) -> None:
        """Store swarm health in Redis."""
        if self.redis_client is None:
            return

        try:
            import json

            key = f"{HEALTH_STATE_KEY}:swarm"
            data = {
                "score": score.overall_score,
                "status": score.status.value,
                "agent_count": score.agent_count,
                "healthy_count": score.healthy_count,
                "degraded_count": score.degraded_count,
                "unhealthy_count": score.unhealthy_count,
                "critical_count": score.critical_count,
                "timestamp": score.timestamp.isoformat(),
            }
            self.redis_client.setex(
                key,
                timedelta(hours=self.config.history_retention_hours),
                json.dumps(data),
            )
        except Exception as e:
            logger.warning(f"Failed to store swarm health in Redis: {e}")

    def _store_alerts(self, alerts: list[HealthAlert]) -> None:
        """Store alerts in Redis."""
        if self.redis_client is None or not alerts:
            return

        try:
            import json

            for alert in alerts:
                key = f"{ALERTS_KEY}:{alert.alert_id}"
                self.redis_client.setex(
                    key,
                    timedelta(hours=1),
                    json.dumps(alert.to_dict()),
                )
        except Exception as e:
            logger.warning(f"Failed to store alerts in Redis: {e}")

    def get_prediction_accuracy(self) -> float:
        """Calculate current prediction accuracy."""
        actual_scores = {
            agent_id: self.scorer.get_agent_history(agent_id, limit=20)
            for agent_id in self._agent_health
        }
        return self.predictor.calculate_prediction_accuracy(actual_scores)

    def get_metrics_export(self) -> str:
        """Get Prometheus-formatted metrics export."""
        return self.metrics.export_prometheus()
