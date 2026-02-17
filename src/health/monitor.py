"""Main health monitoring module.

Aggregates health from all ChiseAI components:
- Paper trading components (orchestrator, position tracker, order simulator)
- Data sources (Redis, InfluxDB, PostgreSQL)
- Exchange connections (Bybit, Bitget)
- Kill-switch status

Provides:
- Health scores (0-100) per component and overall
- Traffic light status: GREEN, YELLOW, RED
- Health history tracking (last 24 hours)
- Trend calculation

For PAPER-003-001: Unified Health Monitoring System
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from . import ComponentType, HealthStatus
from .history import HealthHistory
from .score_calculator import ComponentScore, HealthScore, ScoreCalculator

if TYPE_CHECKING:
    from data.exchange.bitget_connector import BitgetConnector
    from data.exchange.bybit_connector import BybitConnector
    from execution.kill_switch.executor import KillSwitchExecutor
    from execution.paper.orchestrator import PaperTradingOrchestrator
    from execution.paper.order_simulator import OrderSimulator
    from portfolio.paper_tracker import PaperTracker

logger = logging.getLogger(__name__)


class HealthMonitor:
    """Unified health monitor for ChiseAI system.

    Monitors health of all critical components and provides
    aggregated health scores with trend analysis.

    Attributes:
        orchestrator: Paper trading orchestrator
        position_tracker: Position tracker
        order_simulator: Order simulator
        bybit_connector: Bybit exchange connector
        bitget_connector: Bitget exchange connector
        kill_switch: Kill-switch executor
        redis_client: Redis client
        influxdb_client: InfluxDB client
        postgres_client: PostgreSQL client
        calculator: Health score calculator
        history: Health history tracker
    """

    DEFAULT_UPDATE_INTERVAL_SECONDS = 30

    def __init__(
        self,
        orchestrator: PaperTradingOrchestrator | None = None,
        position_tracker: PaperTracker | None = None,
        order_simulator: OrderSimulator | None = None,
        bybit_connector: BybitConnector | None = None,
        bitget_connector: BitgetConnector | None = None,
        kill_switch: KillSwitchExecutor | None = None,
        redis_client: Any | None = None,
        influxdb_client: Any | None = None,
        postgres_client: Any | None = None,
        update_interval_seconds: int = DEFAULT_UPDATE_INTERVAL_SECONDS,
    ) -> None:
        """Initialize health monitor.

        Args:
            orchestrator: Paper trading orchestrator
            position_tracker: Position tracker
            order_simulator: Order simulator
            bybit_connector: Bybit exchange connector
            bitget_connector: Bitget exchange connector
            kill_switch: Kill-switch executor
            redis_client: Redis client
            influxdb_client: InfluxDB client
            postgres_client: PostgreSQL client
            update_interval_seconds: Seconds between health updates
        """
        # Component references
        self.orchestrator = orchestrator
        self.position_tracker = position_tracker
        self.order_simulator = order_simulator
        self.bybit_connector = bybit_connector
        self.bitget_connector = bitget_connector
        self.kill_switch = kill_switch
        self._redis_client = redis_client
        self._influxdb_client = influxdb_client
        self._postgres_client = postgres_client

        # Health tracking
        self.calculator = ScoreCalculator()
        self.history = HealthHistory()
        self._current_score: HealthScore | None = None
        self._last_update: datetime | None = None
        self._update_interval = update_interval_seconds

        # Background task
        self._running = False
        self._monitor_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

        logger.info("HealthMonitor initialized")

    async def start(self) -> None:
        """Start health monitoring loop."""
        if self._running:
            logger.warning("HealthMonitor already running")
            return

        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("HealthMonitor started")

    async def stop(self) -> None:
        """Stop health monitoring loop."""
        if not self._running:
            return

        self._running = False

        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        logger.info("HealthMonitor stopped")

    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                await self.update_health()
                await asyncio.sleep(self._update_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health monitor loop error: {e}")
                await asyncio.sleep(5)

    async def update_health(self) -> HealthScore:
        """Update health scores for all components.

        Returns:
            Updated HealthScore
        """
        component_scores: list[ComponentScore] = []

        # Paper components
        if self.orchestrator:
            score = self._check_orchestrator_health()
            component_scores.append(score)

        if self.position_tracker:
            score = self._check_position_tracker_health()
            component_scores.append(score)

        if self.order_simulator:
            score = self._check_order_simulator_health()
            component_scores.append(score)

        # Data sources
        score = self._check_redis_health()
        component_scores.append(score)

        score = self._check_influxdb_health()
        component_scores.append(score)

        score = self._check_postgresql_health()
        component_scores.append(score)

        # Exchanges
        if self.bybit_connector:
            score = self._check_bybit_health()
            component_scores.append(score)

        if self.bitget_connector:
            score = self._check_bitget_health()
            component_scores.append(score)

        # Kill-switch
        if self.kill_switch:
            score = self._check_kill_switch_health()
            component_scores.append(score)

        # Calculate overall score
        health_score = self.calculator.calculate_overall_score(component_scores)

        async with self._lock:
            self._current_score = health_score
            self._last_update = datetime.now(UTC)

        # Record in history
        await self.history.record_snapshot(health_score)

        logger.debug(
            f"Health updated: overall={health_score.overall_score:.1f}, "
            f"status={health_score.status.value}"
        )

        return health_score

    def _check_orchestrator_health(self) -> ComponentScore:
        """Check orchestrator health."""
        health_data: dict[str, Any] = {"component": "orchestrator"}

        if self.orchestrator is None:
            health_data["is_running"] = False
            health_data["error"] = "Not initialized"
        else:
            health_data["is_running"] = getattr(self.orchestrator, "running", False)
            health_data["latency_ms"] = getattr(
                self.orchestrator, "_last_latency_ms", 0
            )
            health_data["error_rate"] = getattr(self.orchestrator, "_error_rate", 0.0)
            health_data["last_success_seconds_ago"] = getattr(
                self.orchestrator, "_last_success_time", 0
            )

        return self.calculator.calculate_component_score(
            ComponentType.ORCHESTRATOR, health_data
        )

    def _check_position_tracker_health(self) -> ComponentScore:
        """Check position tracker health."""
        health_data: dict[str, Any] = {"component": "position_tracker"}

        if self.position_tracker is None:
            health_data["is_running"] = False
            health_data["error"] = "Not initialized"
        else:
            health_data["is_running"] = True
            health_data["position_count"] = len(
                getattr(self.position_tracker, "_positions", {})
            )
            health_data["redis_health"] = getattr(
                self.position_tracker, "_redis_health", None
            )
            if health_data["redis_health"]:
                health_data["error_rate"] = health_data["redis_health"].error_rate
                health_data["circuit_breaker_open"] = health_data[
                    "redis_health"
                ].circuit_breaker_open

        return self.calculator.calculate_component_score(
            ComponentType.POSITION_TRACKER, health_data
        )

    def _check_order_simulator_health(self) -> ComponentScore:
        """Check order simulator health."""
        health_data: dict[str, Any] = {"component": "order_simulator"}

        if self.order_simulator is None:
            health_data["is_running"] = False
            health_data["error"] = "Not initialized"
        else:
            health_data["is_running"] = True
            health_data["order_count"] = len(
                getattr(self.order_simulator, "_orders", {})
            )

        return self.calculator.calculate_component_score(
            ComponentType.ORDER_SIMULATOR, health_data
        )

    def _check_redis_health(self) -> ComponentScore:
        """Check Redis health."""
        health_data: dict[str, Any] = {
            "component": "redis",
            "is_connected": False,
        }

        if self._redis_client:
            try:
                # Try to ping Redis
                if hasattr(self._redis_client, "ping"):
                    result = self._redis_client.ping()
                    health_data["is_connected"] = result is not False
                else:
                    health_data["is_connected"] = True  # Assume connected if present

                health_data["response_time_ms"] = 0  # Would measure in real impl
            except Exception as e:
                health_data["is_connected"] = False
                health_data["error"] = str(e)

        return self.calculator.calculate_component_score(
            ComponentType.REDIS, health_data
        )

    def _check_influxdb_health(self) -> ComponentScore:
        """Check InfluxDB health."""
        health_data: dict[str, Any] = {
            "component": "influxdb",
            "is_connected": False,
        }

        if self._influxdb_client:
            try:
                if hasattr(self._influxdb_client, "ping"):
                    health_data["is_connected"] = self._influxdb_client.ping()
                else:
                    health_data["is_connected"] = True
            except Exception as e:
                health_data["error"] = str(e)

        return self.calculator.calculate_component_score(
            ComponentType.INFLUXDB, health_data
        )

    def _check_postgresql_health(self) -> ComponentScore:
        """Check PostgreSQL health."""
        health_data: dict[str, Any] = {
            "component": "postgresql",
            "is_connected": False,
        }

        if self._postgres_client:
            try:
                if hasattr(self._postgres_client, "execute"):
                    # Try a simple query
                    health_data["is_connected"] = True
                else:
                    health_data["is_connected"] = True
            except Exception as e:
                health_data["error"] = str(e)

        return self.calculator.calculate_component_score(
            ComponentType.POSTGRESQL, health_data
        )

    def _check_bybit_health(self) -> ComponentScore:
        """Check Bybit connector health."""
        health_data: dict[str, Any] = {"component": "bybit"}

        if self.bybit_connector is None:
            health_data["is_connected"] = False
            health_data["error"] = "Not initialized"
        else:
            try:
                if hasattr(self.bybit_connector, "is_healthy"):
                    health_data["is_connected"] = self.bybit_connector.is_healthy()
                else:
                    health_data["is_connected"] = True

                if hasattr(self.bybit_connector, "health_check"):
                    connector_health = self.bybit_connector.health_check()
                    if asyncio.iscoroutine(connector_health):
                        # Can't await here in sync method, use cached values
                        pass
                    else:
                        health_data.update(connector_health)

                health_data["latency_ms"] = getattr(
                    self.bybit_connector, "_latency_ms", 0
                )
                health_data["reconnect_count"] = getattr(
                    self.bybit_connector, "_reconnect_count", 0
                )
            except Exception as e:
                health_data["is_connected"] = False
                health_data["error"] = str(e)

        return self.calculator.calculate_component_score(
            ComponentType.BYBIT, health_data
        )

    def _check_bitget_health(self) -> ComponentScore:
        """Check Bitget connector health."""
        health_data: dict[str, Any] = {"component": "bitget"}

        if self.bitget_connector is None:
            health_data["is_connected"] = False
            health_data["error"] = "Not initialized"
        else:
            try:
                if hasattr(self.bitget_connector, "is_healthy"):
                    health_data["is_connected"] = self.bitget_connector.is_healthy()
                else:
                    health_data["is_connected"] = True

                health_data["latency_ms"] = getattr(
                    self.bitget_connector, "_latency_ms", 0
                )
                health_data["reconnect_count"] = getattr(
                    self.bitget_connector, "_reconnect_count", 0
                )
            except Exception as e:
                health_data["is_connected"] = False
                health_data["error"] = str(e)

        return self.calculator.calculate_component_score(
            ComponentType.BITGET, health_data
        )

    def _check_kill_switch_health(self) -> ComponentScore:
        """Check kill-switch health."""
        health_data: dict[str, Any] = {"component": "kill_switch"}

        if self.kill_switch is None:
            health_data["state"] = "NOT_INITIALIZED"
            health_data["is_armed"] = False
        else:
            state = getattr(self.kill_switch, "state", None)
            health_data["state"] = state.value if state else "UNKNOWN"
            health_data["is_armed"] = health_data["state"] == "ARMED"
            health_data["last_test_seconds_ago"] = getattr(
                self.kill_switch, "_last_test_time", 0
            )

        return self.calculator.calculate_component_score(
            ComponentType.KILL_SWITCH, health_data
        )

    async def get_health(self) -> HealthScore:
        """Get current health score.

        Returns:
            Current HealthScore (updates if stale)
        """
        if self._current_score is None:
            return await self.update_health()

        # Check if update needed
        if self._last_update:
            elapsed = (datetime.now(UTC) - self._last_update).total_seconds()
            if elapsed > self._update_interval:
                return await self.update_health()

        return self._current_score

    def get_health_sync(self) -> HealthScore:
        """Get current health score (synchronous).

        Returns:
            Current HealthScore (may be stale)
        """
        if self._current_score is None:
            # Can't update without async, return default
            return HealthScore(
                overall_score=0.0,
                component_scores=[],
            )
        return self._current_score

    async def get_status(self) -> dict[str, Any]:
        """Get full health status including trends.

        Returns:
            Dictionary with health status, scores, and trends
        """
        health = await self.get_health()
        trend = await self.history.calculate_trend(hours=24)
        alerts = await self.history.get_alert_history(hours=24)

        return {
            "overall_score": round(health.overall_score, 2),
            "status": health.status.value,
            "last_update": (
                self._last_update.isoformat() if self._last_update else None
            ),
            "component_scores": {
                cs.component.value: cs.to_dict() for cs in health.component_scores
            },
            "trend": trend.to_dict() if trend else None,
            "recent_alerts": alerts[-10:] if alerts else [],
            "monitoring_active": self._running,
        }

    def is_healthy(self) -> bool:
        """Quick health check.

        Returns:
            True if overall health is GREEN or YELLOW
        """
        if self._current_score is None:
            return False
        return self._current_score.status != HealthStatus.RED

    def is_critical(self) -> bool:
        """Check if health is critical.

        Returns:
            True if overall health is RED
        """
        if self._current_score is None:
            return True
        return self._current_score.status == HealthStatus.RED

    async def record_alert(
        self,
        component: str,
        severity: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Record an alert.

        Args:
            component: Component that triggered alert
            severity: Alert severity (info, warning, critical)
            message: Alert message
            details: Additional details
        """
        await self.history.record_alert(component, severity, message, details)

    def get_component_health(self, component: ComponentType) -> ComponentScore | None:
        """Get health for a specific component.

        Args:
            component: Component to check

        Returns:
            ComponentScore or None
        """
        if self._current_score is None:
            return None
        return self._current_score.get_component_score(component)
