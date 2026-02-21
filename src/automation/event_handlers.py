"""Event handlers for self-healing automation.

Provides handlers for health events:
- OnHealthCritical: immediate recovery
- OnHealthWarning: scheduled recovery
- OnRecoverySuccess: health score restoration
- OnRecoveryFailure: escalation

Integrates with health monitoring from PAPER-003-001.

For PAPER-003-004: Event-Driven Self-Healing Automation
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from .recovery_orchestrator import (
    HealthLevel,
    RecoveryContext,
    RecoveryOrchestrator,
    RecoveryResult,
    RecoveryType,
)
from .self_healing_engine import (
    HealingAction,
    SelfHealingEngine,
    SelfHealingResult,
)

logger = logging.getLogger(__name__)


class EventType(StrEnum):
    """Types of health events."""

    HEALTH_CRITICAL = "health_critical"
    HEALTH_WARNING = "health_warning"
    HEALTH_INFO = "health_info"
    RECOVERY_SUCCESS = "recovery_success"
    RECOVERY_FAILURE = "recovery_failure"
    DATA_GAP_DETECTED = "data_gap_detected"
    DEPLOYMENT_HEALTH_LOW = "deployment_health_low"


@dataclass
class HealthEvent:
    """A health event from monitoring systems.

    Attributes:
        event_type: Type of health event
        source: Component that generated the event
        severity: Event severity level
        message: Human-readable message
        timestamp: When event occurred
        metadata: Additional event data
    """

    event_type: EventType
    source: str
    severity: HealthLevel
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "event_type": self.event_type.value,
            "source": self.source,
            "severity": self.severity.value,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


class EventHandler(ABC):
    """Abstract base class for event handlers."""

    def __init__(
        self,
        orchestrator: RecoveryOrchestrator,
        healing_engine: SelfHealingEngine,
    ):
        """Initialize event handler.

        Args:
            orchestrator: Recovery orchestrator
            healing_engine: Self-healing engine
        """
        self._orchestrator = orchestrator
        self._healing_engine = healing_engine

    @abstractmethod
    async def handle(
        self, event: HealthEvent
    ) -> RecoveryResult | SelfHealingResult | None:
        """Handle a health event.

        Args:
            event: Health event to handle

        Returns:
            Recovery/healing result or None
        """
        pass


class OnHealthCritical(EventHandler):
    """Handler for critical health events.

    Triggers immediate recovery for critical issues.
    """

    RECOVERY_MAPPING: dict[str, RecoveryType] = {
        "redis": RecoveryType.REDIS_RECONNECT,
        "datasource": RecoveryType.REDIS_RECONNECT,
        "exchange": RecoveryType.EXCHANGE_FAILOVER,
        "bybit": RecoveryType.EXCHANGE_FAILOVER,
        "bitget": RecoveryType.EXCHANGE_FAILOVER,
        "service": RecoveryType.SERVICE_RESTART,
        "api": RecoveryType.SERVICE_RESTART,
        "circuit_breaker": RecoveryType.CIRCUIT_BREAKER_RESET,
    }

    async def handle(self, event: HealthEvent) -> RecoveryResult | None:
        """Handle critical health event with immediate recovery.

        Args:
            event: Critical health event

        Returns:
            Recovery result
        """
        logger.critical(f"CRITICAL health event from {event.source}: {event.message}")

        # Determine recovery type from source
        recovery_type = self._determine_recovery_type(event)

        # Create recovery context
        context = RecoveryContext(
            source=event.source,
            recovery_type=recovery_type,
            trigger_event=event.event_type.value,
            metadata={
                "event_message": event.message,
                **event.metadata,
            },
        )

        # Trigger immediate recovery
        result = await self._orchestrator.trigger_recovery(
            context,
            priority=HealthLevel.CRITICAL,
        )

        if result.success:
            logger.info(
                f"Critical recovery succeeded for {event.source}: "
                f"{result.attempt.attempt_id}"
            )
        else:
            if result.escalation_required:
                logger.error(
                    f"Critical recovery failed for {event.source}, escalation required"
                )
            else:
                logger.warning(
                    f"Critical recovery failed for {event.source}, will retry"
                )

        return result

    def _determine_recovery_type(self, event: HealthEvent) -> RecoveryType:
        """Determine recovery type from event source."""
        source_lower = event.source.lower()

        # Check for exact matches
        for key, recovery_type in self.RECOVERY_MAPPING.items():
            if key in source_lower:
                return recovery_type

        # Default to service restart
        logger.warning(
            f"No specific recovery type for {event.source}, using SERVICE_RESTART"
        )
        return RecoveryType.SERVICE_RESTART


class OnHealthWarning(EventHandler):
    """Handler for warning health events.

        Schedules recovery during low-traffic periods or
    triggers immediate recovery based on severity trend.
    """

    def __init__(
        self,
        orchestrator: RecoveryOrchestrator,
        healing_engine: SelfHealingEngine,
        low_traffic_hours: tuple[int, int] = (2, 5),  # 2 AM - 5 AM UTC
    ):
        """Initialize warning handler.

        Args:
            orchestrator: Recovery orchestrator
            healing_engine: Self-healing engine
            low_traffic_hours: Hours considered low traffic (start, end)
        """
        super().__init__(orchestrator, healing_engine)
        self._low_traffic_hours = low_traffic_hours
        self._scheduled_recoveries: dict[str, asyncio.Task] = {}

    async def handle(self, event: HealthEvent) -> RecoveryResult | None:
        """Handle warning health event.

        Args:
            event: Warning health event

        Returns:
            Recovery result if immediate, None if scheduled
        """
        logger.warning(f"WARNING health event from {event.source}: {event.message}")

        # Check if we should recover immediately or schedule
        if self._should_recover_immediately(event):
            return await self._recover_immediately(event)
        else:
            return await self._schedule_recovery(event)

    def _should_recover_immediately(self, event: HealthEvent) -> bool:
        """Check if warning requires immediate recovery.

        Immediate recovery if:
        - Trend is worsening rapidly
        - Component is in degraded state
        - Low traffic period (safe to restart)
        """
        # Check if already in low-traffic period
        current_hour = datetime.now(UTC).hour
        start_hour, end_hour = self._low_traffic_hours

        is_low_traffic = start_hour <= current_hour <= end_hour

        # Check for worsening trend in metadata
        trend = event.metadata.get("trend", "stable")
        is_worsening = trend == "worsening"

        # Check degraded state
        health_score = event.metadata.get("health_score", 100)
        is_degraded = health_score < 40

        return is_low_traffic or is_worsening or is_degraded

    async def _recover_immediately(
        self,
        event: HealthEvent,
    ) -> RecoveryResult:
        """Trigger immediate recovery."""
        recovery_type = self._determine_recovery_type(event)

        context = RecoveryContext(
            source=event.source,
            recovery_type=recovery_type,
            trigger_event=event.event_type.value,
            metadata={
                "event_message": event.message,
                "immediate": True,
                **event.metadata,
            },
        )

        result = await self._orchestrator.trigger_recovery(
            context,
            priority=HealthLevel.WARNING,
        )

        logger.info(
            f"Immediate recovery for warning {event.source}: success={result.success}"
        )

        return result

    async def _schedule_recovery(
        self,
        event: HealthEvent,
    ) -> None:
        """Schedule recovery for low-traffic period."""
        # Cancel any existing scheduled recovery for this source
        if event.source in self._scheduled_recoveries:
            existing_task = self._scheduled_recoveries[event.source]
            if not existing_task.done():
                existing_task.cancel()
            del self._scheduled_recoveries[event.source]

        # Calculate time until low-traffic period
        current_hour = datetime.now(UTC).hour
        start_hour, end_hour = self._low_traffic_hours

        if current_hour < start_hour:
            # Before low-traffic period
            hours_until = start_hour - current_hour
        elif current_hour > end_hour:
            # After low-traffic period, schedule for next day
            hours_until = (24 - current_hour) + start_hour
        else:
            # Already in low-traffic period
            hours_until = 0

        delay_seconds = hours_until * 3600

        logger.info(
            f"Scheduled recovery for {event.source} in {hours_until} hours "
            f"(low-traffic window: {start_hour}:00-{end_hour}:00 UTC)"
        )

        # Schedule the recovery
        task = asyncio.create_task(
            self._execute_scheduled_recovery(event, delay_seconds)
        )
        self._scheduled_recoveries[event.source] = task

        return None

    async def _execute_scheduled_recovery(
        self,
        event: HealthEvent,
        delay_seconds: float,
    ) -> None:
        """Execute scheduled recovery after delay."""
        try:
            await asyncio.sleep(delay_seconds)

            recovery_type = self._determine_recovery_type(event)

            context = RecoveryContext(
                source=event.source,
                recovery_type=recovery_type,
                trigger_event=event.event_type.value,
                metadata={
                    "event_message": event.message,
                    "scheduled": True,
                    **event.metadata,
                },
            )

            result = await self._orchestrator.trigger_recovery(
                context,
                priority=HealthLevel.WARNING,
            )

            logger.info(
                f"Scheduled recovery for {event.source} completed: "
                f"success={result.success}"
            )

        except asyncio.CancelledError:
            logger.info(f"Scheduled recovery for {event.source} cancelled")
        except Exception as e:
            logger.error(f"Scheduled recovery for {event.source} failed: {e}")
        finally:
            # Clean up
            if event.source in self._scheduled_recoveries:
                del self._scheduled_recoveries[event.source]

    def _determine_recovery_type(self, event: HealthEvent) -> RecoveryType:
        """Determine recovery type from event."""
        source_lower = event.source.lower()

        mappings = {
            "redis": RecoveryType.REDIS_RECONNECT,
            "datasource": RecoveryType.REDIS_RECONNECT,
            "exchange": RecoveryType.EXCHANGE_FAILOVER,
            "bybit": RecoveryType.EXCHANGE_FAILOVER,
            "bitget": RecoveryType.EXCHANGE_FAILOVER,
            "service": RecoveryType.SERVICE_RESTART,
            "api": RecoveryType.SERVICE_RESTART,
            "circuit_breaker": RecoveryType.CIRCUIT_BREAKER_RESET,
        }

        for key, recovery_type in mappings.items():
            if key in source_lower:
                return recovery_type

        return RecoveryType.SERVICE_RESTART

    def cancel_scheduled(self, source: str) -> bool:
        """Cancel a scheduled recovery.

        Args:
            source: Source to cancel recovery for

        Returns:
            True if cancelled
        """
        if source in self._scheduled_recoveries:
            task = self._scheduled_recoveries[source]
            if not task.done():
                task.cancel()
            del self._scheduled_recoveries[source]
            logger.info(f"Cancelled scheduled recovery for {source}")
            return True
        return False


class OnRecoverySuccess(EventHandler):
    """Handler for successful recoveries.

    Restores health scores and notifies monitoring.
    """

    def __init__(
        self,
        orchestrator: RecoveryOrchestrator,
        healing_engine: SelfHealingEngine,
        health_score_restorer: Callable[[str, float], Awaitable[None]] | None = None,
    ):
        """Initialize success handler.

        Args:
            orchestrator: Recovery orchestrator
            healing_engine: Self-healing engine
            health_score_restorer: Optional callback to restore health scores
        """
        super().__init__(orchestrator, healing_engine)
        self._health_score_restorer = health_score_restorer

    async def handle(self, event: HealthEvent) -> SelfHealingResult | None:
        """Handle recovery success event.

        Args:
            event: Recovery success event

        Returns:
            Healing result or None
        """
        source = event.source

        logger.info(f"Recovery succeeded for {source}: {event.message}")

        # Restore health score if restorer available
        if self._health_score_restorer:
            try:
                # Restore to 80 (good health) or metadata specified value
                health_score = event.metadata.get("health_score", 80.0)
                await self._health_score_restorer(source, health_score)

                logger.info(f"Restored health score for {source} to {health_score}")

                return SelfHealingResult(
                    action=HealingAction.CIRCUIT_BREAKER_RESET,
                    status="succeeded",
                    source=source,
                    details={
                        "health_score_restored": health_score,
                        "message": event.message,
                    },
                )
            except Exception as e:
                logger.error(f"Failed to restore health score for {source}: {e}")

        return None


class OnRecoveryFailure(EventHandler):
    """Handler for failed recoveries.

    Escalates to human operators when recovery fails.
    """

    def __init__(
        self,
        orchestrator: RecoveryOrchestrator,
        healing_engine: SelfHealingEngine,
        escalation_handlers: (
            list[Callable[[HealthEvent], Awaitable[None]]] | None
        ) = None,
    ):
        """Initialize failure handler.

        Args:
            orchestrator: Recovery orchestrator
            healing_engine: Self-healing engine
            escalation_handlers: Handlers for escalations
        """
        super().__init__(orchestrator, healing_engine)
        self._escalation_handlers = escalation_handlers or []

    async def handle(self, event: HealthEvent) -> None:
        """Handle recovery failure event.

        Args:
            event: Recovery failure event
        """
        source = event.source
        attempt_count = event.metadata.get("attempt_count", 1)

        logger.critical(
            f"RECOVERY FAILED for {source} after {attempt_count} attempts: "
            f"{event.message}"
        )

        # Add escalation metadata
        escalation_event = HealthEvent(
            event_type=EventType.RECOVERY_FAILURE,
            source=source,
            severity=HealthLevel.CRITICAL,
            message=f"Recovery failed after {attempt_count} attempts: {event.message}",
            metadata={
                "original_event": event.to_dict(),
                "escalation_required": True,
                "human_intervention_needed": True,
                **event.metadata,
            },
        )

        # Call escalation handlers
        for handler in self._escalation_handlers:
            try:
                await handler(escalation_event)
            except Exception as e:
                logger.error(f"Escalation handler failed: {e}")

        return None

    def add_escalation_handler(
        self,
        handler: Callable[[HealthEvent], Awaitable[None]],
    ) -> None:
        """Add an escalation handler."""
        self._escalation_handlers.append(handler)
        logger.debug(f"Added escalation handler: {handler.__name__}")


class EventRouter:
    """Routes health events to appropriate handlers.

    Integrates with health monitoring systems to receive events
    and dispatch to the correct handler.
    """

    def __init__(
        self,
        orchestrator: RecoveryOrchestrator,
        healing_engine: SelfHealingEngine,
        low_traffic_hours: tuple[int, int] = (2, 5),
    ):
        """Initialize event router.

        Args:
            orchestrator: Recovery orchestrator
            healing_engine: Self-healing engine
            low_traffic_hours: Low traffic window hours
        """
        self._orchestrator = orchestrator
        self._healing_engine = healing_engine

        # Initialize handlers
        self._critical_handler = OnHealthCritical(orchestrator, healing_engine)
        self._warning_handler = OnHealthWarning(
            orchestrator, healing_engine, low_traffic_hours
        )
        self._success_handler = OnRecoverySuccess(orchestrator, healing_engine)
        self._failure_handler = OnRecoveryFailure(orchestrator, healing_engine)

        # Event handlers mapping
        self._handlers: dict[EventType, EventHandler] = {
            EventType.HEALTH_CRITICAL: self._critical_handler,
            EventType.HEALTH_WARNING: self._warning_handler,
            EventType.RECOVERY_SUCCESS: self._success_handler,
            EventType.RECOVERY_FAILURE: self._failure_handler,
        }

        logger.info("EventRouter initialized")

    async def route(self, event: HealthEvent) -> Any:
        """Route an event to the appropriate handler.

        Args:
            event: Health event to route

        Returns:
            Handler result
        """
        handler = self._handlers.get(event.event_type)

        if not handler:
            logger.warning(f"No handler for event type: {event.event_type}")
            return None

        logger.debug(f"Routing {event.event_type} to {handler.__class__.__name__}")

        return await handler.handle(event)

    async def route_from_monitoring_alert(
        self,
        source: str,
        severity: str,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        """Route from a monitoring alert.

        Args:
            source: Alert source
            severity: Alert severity (critical/warning/info)
            message: Alert message
            metadata: Additional metadata

        Returns:
            Handler result
        """
        # Map severity to event type
        severity_lower = severity.lower()

        if severity_lower == "critical":
            event_type = EventType.HEALTH_CRITICAL
            health_level = HealthLevel.CRITICAL
        elif severity_lower == "warning":
            event_type = EventType.HEALTH_WARNING
            health_level = HealthLevel.WARNING
        else:
            event_type = EventType.HEALTH_INFO
            health_level = HealthLevel.INFO

        event = HealthEvent(
            event_type=event_type,
            source=source,
            severity=health_level,
            message=message,
            metadata=metadata or {},
        )

        return await self.route(event)

    def get_critical_handler(self) -> OnHealthCritical:
        """Get the critical health handler."""
        return self._critical_handler

    def get_warning_handler(self) -> OnHealthWarning:
        """Get the warning health handler."""
        return self._warning_handler

    def get_success_handler(self) -> OnRecoverySuccess:
        """Get the recovery success handler."""
        return self._success_handler

    def get_failure_handler(self) -> OnRecoveryFailure:
        """Get the recovery failure handler."""
        return self._failure_handler


# Integration helpers for existing monitoring systems


def create_health_event_from_datasource_alert(
    alert: Any,
) -> HealthEvent:
    """Create a health event from a datasource health alert.

    Args:
        alert: DatasourceHealthAlert from monitoring.datasource_health

    Returns:
        HealthEvent for automation system
    """
    # Map alert severity to health level
    severity_map = {
        "critical": HealthLevel.CRITICAL,
        "warning": HealthLevel.WARNING,
        "info": HealthLevel.INFO,
    }

    # Determine event type
    if alert.alert_type in ["disconnected", "reconnect_failed"]:
        event_type = EventType.HEALTH_CRITICAL
    elif alert.alert_type == "extended_downtime":
        event_type = EventType.HEALTH_CRITICAL
    else:
        event_type = EventType.HEALTH_WARNING

    return HealthEvent(
        event_type=event_type,
        source=f"{alert.source_type}_{alert.source_name}",
        severity=severity_map.get(alert.severity.value, HealthLevel.WARNING),
        message=alert.message,
        metadata={
            "alert_type": alert.alert_type,
            "source_type": alert.source_type,
            **(alert.metrics if hasattr(alert, "metrics") else {}),
        },
    )


def create_health_event_from_execution_alert(
    alert: Any,
) -> HealthEvent:
    """Create a health event from an execution health alert.

    Args:
        alert: DataGapAlert from execution.health_monitor

    Returns:
        HealthEvent for automation system
    """
    # Data gaps are critical for execution
    event_type = EventType.DATA_GAP_DETECTED

    # Severity based on duration
    severity = (
        HealthLevel.CRITICAL if alert.duration_seconds > 60 else HealthLevel.WARNING
    )

    return HealthEvent(
        event_type=event_type,
        source=f"{alert.source}_{alert.symbol}",
        severity=severity,
        message=f"Data gap detected: {alert.duration_seconds:.1f}s",
        metadata={
            "gap_start": alert.gap_start,
            "gap_end": alert.gap_end,
            "duration_seconds": alert.duration_seconds,
            "symbol": alert.symbol,
        },
    )
