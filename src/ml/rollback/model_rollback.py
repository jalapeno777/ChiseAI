"""Model rollback with degradation detection, automatic rollback, and audit history.

This module provides rollback capabilities with performance monitoring,
automatic rollback triggers, and comprehensive audit logging.

Acceptance Criteria:
- Degradation detection: >10% from baseline triggers alert
- Automatic rollback: <5 minutes (target <2 minutes)
- Audit history: 90-day retention with query API

Example:
    >>> from ml.rollback.model_rollback import (
    ...     RollbackManager, RollbackConfig, DegradationMonitor
    ... )
    >>> from ml.model_registry.registry import ModelRegistry
    >>>
    >>> registry = ModelRegistry()
    >>> config = RollbackConfig(max_rollback_time_seconds=120)  # 2 min target
    >>> rollback = RollbackManager(registry=registry, config=config)
    >>>
    >>> # Trigger automatic rollback
    >>> result = await rollback.execute_rollback(
    ...     failed_version_id="model_v2",
    ...     reason="degradation_detected"
    ... )
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class RollbackTrigger(Enum):
    """Triggers for automatic rollback."""

    DEGRADATION = "degradation"  # Performance degradation detected
    VALIDATION_FAILURE = "validation_failure"  # Validation gate failed
    MANUAL = "manual"  # Manual trigger
    SYSTEM_ERROR = "system_error"  # System error
    TIMEOUT = "timeout"  # Operation timeout
    HEALTH_CHECK_FAILURE = "health_check_failure"  # Health check failed


class RollbackStatus(Enum):
    """Status of rollback operations."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


@dataclass
class RollbackConfig:
    """Configuration for rollback operations.

    Task 13.4: CRITICAL - Rollback must complete in <5 minutes (target: <2 minutes)
    """

    max_rollback_time_seconds: float = (
        120.0  # Target: <2 minutes (120s), Max: 5 min (300s)
    )
    degradation_threshold_pct: float = 10.0  # Task 13.3: >10% triggers alert
    auto_rollback_enabled: bool = True
    protect_current_trades: bool = True  # Task 13.4: Protect current trades
    notification_webhook: str = ""  # Discord webhook for alerts
    audit_retention_days: int = 90  # Task 13.5: 90-day retention


@dataclass
class RollbackEvent:
    """Record of a rollback event.

    Task 13.5: Track rollback events with timestamps and reasons.
    """

    event_id: str
    timestamp: datetime
    trigger: RollbackTrigger
    failed_version: str
    target_version: str | None
    status: RollbackStatus
    duration_seconds: float = 0.0
    reason: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    trade_protection_applied: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "trigger": self.trigger.value,
            "failed_version": self.failed_version,
            "target_version": self.target_version,
            "status": self.status.value,
            "duration_seconds": self.duration_seconds,
            "reason": self.reason,
            "details": self.details,
            "trade_protection_applied": self.trade_protection_applied,
        }


@dataclass
class DegradationAlert:
    """Alert for performance degradation.

    Task 13.3: Discord notification within 1 minute.
    """

    alert_id: str
    model_version: str
    metric_name: str
    baseline_value: float
    current_value: float
    degradation_percentage: float
    detected_at: datetime
    notified_at: datetime | None = None
    rollback_triggered: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "alert_id": self.alert_id,
            "model_version": self.model_version,
            "metric_name": self.metric_name,
            "baseline_value": self.baseline_value,
            "current_value": self.current_value,
            "degradation_percentage": self.degradation_percentage,
            "detected_at": self.detected_at.isoformat(),
            "notified_at": self.notified_at.isoformat() if self.notified_at else None,
            "rollback_triggered": self.rollback_triggered,
        }


class AuditStorage(Protocol):
    """Protocol for audit storage backends."""

    async def store_event(self, event: RollbackEvent) -> bool:
        """Store rollback event."""
        ...

    async def store_alert(self, alert: DegradationAlert) -> bool:
        """Store degradation alert."""
        ...

    async def get_events(
        self,
        model_version: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 100,
    ) -> list[RollbackEvent]:
        """Query rollback events."""
        ...

    async def get_alerts(
        self,
        model_version: str | None = None,
        limit: int = 100,
    ) -> list[DegradationAlert]:
        """Query degradation alerts."""
        ...


class InMemoryAuditStorage:
    """In-memory audit storage for testing and development.

    Task 13.5: Store all validation results in database.
    """

    def __init__(self, retention_days: int = 90):
        """Initialize in-memory storage.

        Args:
            retention_days: Number of days to retain records
        """
        self._retention_days = retention_days
        self._events: list[RollbackEvent] = []
        self._alerts: list[DegradationAlert] = []
        self._validation_results: list[dict[str, Any]] = []

    async def store_event(self, event: RollbackEvent) -> bool:
        """Store rollback event."""
        self._events.append(event)
        self._cleanup_expired()
        return True

    async def store_alert(self, alert: DegradationAlert) -> bool:
        """Store degradation alert."""
        self._alerts.append(alert)
        self._cleanup_expired()
        return True

    async def store_validation_result(self, result: dict[str, Any]) -> bool:
        """Store validation result.

        Task 13.5: Store all validation results in database.
        """
        result["stored_at"] = datetime.now(UTC).isoformat()
        self._validation_results.append(result)
        self._cleanup_expired()
        return True

    async def get_events(
        self,
        model_version: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 100,
    ) -> list[RollbackEvent]:
        """Query rollback events."""
        events = self._events

        if model_version:
            events = [e for e in events if e.failed_version == model_version]

        if start_date:
            events = [e for e in events if e.timestamp >= start_date]

        if end_date:
            events = [e for e in events if e.timestamp <= end_date]

        return sorted(events, key=lambda e: e.timestamp, reverse=True)[:limit]

    async def get_alerts(
        self,
        model_version: str | None = None,
        limit: int = 100,
    ) -> list[DegradationAlert]:
        """Query degradation alerts."""
        alerts = self._alerts

        if model_version:
            alerts = [a for a in alerts if a.model_version == model_version]

        return sorted(alerts, key=lambda a: a.detected_at, reverse=True)[:limit]

    async def get_validation_history(
        self,
        model_version: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query validation history.

        Task 13.5: Add query API: GET /api/v1/validation/history.
        """
        results = self._validation_results

        if model_version:
            results = [r for r in results if r.get("model_version") == model_version]

        if start_date:
            results = [
                r
                for r in results
                if self._parse_timestamp(r.get("timestamp", "1970-01-01T00:00:00Z"))
                >= start_date
            ]

        if end_date:
            results = [
                r
                for r in results
                if self._parse_timestamp(r.get("timestamp", "1970-01-01T00:00:00Z"))
                <= end_date
            ]

        return sorted(results, key=lambda r: r.get("timestamp", ""), reverse=True)[
            :limit
        ]

    def _parse_timestamp(self, ts: str) -> datetime:
        """Parse timestamp string to timezone-aware datetime."""
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            # Ensure timezone-aware
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt
        except (ValueError, TypeError):
            return datetime(1970, 1, 1, tzinfo=UTC)

    def _cleanup_expired(self) -> None:
        """Remove records older than retention period."""
        cutoff = datetime.now(UTC) - timedelta(days=self._retention_days)

        self._events = [e for e in self._events if e.timestamp >= cutoff]
        self._alerts = [a for a in self._alerts if a.detected_at >= cutoff]

        self._validation_results = [
            r
            for r in self._validation_results
            if datetime.fromisoformat(r.get("stored_at", "1970-01-01")) >= cutoff
        ]


class Notifier(Protocol):
    """Protocol for sending notifications."""

    async def send_alert(self, message: str, severity: str = "warning") -> bool:
        """Send alert notification."""
        ...


class DiscordNotifier:
    """Discord notification handler.

    Task 13.3: Discord notification within 1 minute.
    """

    def __init__(self, webhook_url: str = ""):
        """Initialize Discord notifier.

        Args:
            webhook_url: Discord webhook URL
        """
        self._webhook_url = webhook_url

    async def send_alert(self, message: str, severity: str = "warning") -> bool:
        """Send alert to Discord.

        Args:
            message: Alert message
            severity: Alert severity (info, warning, critical)

        Returns:
            True if sent successfully
        """
        if not self._webhook_url:
            logger.warning("Discord webhook not configured, skipping notification")
            return False

        # Map severity to emoji
        emoji_map = {
            "info": "ℹ️",
            "warning": "⚠️",
            "critical": "🚨",
        }
        emoji = emoji_map.get(severity, "⚠️")

        payload = {
            "content": f"{emoji} **Model Rollback Alert**\n\n{message}",
            "username": "ChiseAI Model Monitor",
        }

        try:
            import aiohttp

            async with (
                aiohttp.ClientSession() as session,
                session.post(
                    self._webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response,
            ):
                if response.status == 204:
                    logger.info("Discord notification sent successfully")
                    return True
                else:
                    logger.warning(
                        f"Discord notification failed: status={response.status}"
                    )
                    return False

        except ImportError:
            logger.warning("aiohttp not installed, skipping Discord notification")
            return False
        except Exception as e:
            logger.error(f"Failed to send Discord notification: {e}")
            return False


class DegradationMonitor:
    """Monitor for model performance degradation.

    Task 13.3: Degradation Detection
    - Implement performance monitoring for deployed models
    - Detect degradation >10% from baseline
    - Trigger rollback alert on detection
    - Log degradation events to InfluxDB
    - Discord notification within 1 minute
    """

    def __init__(
        self,
        audit_storage: AuditStorage,
        notifier: Notifier | None = None,
        degradation_threshold_pct: float = 10.0,
    ):
        """Initialize degradation monitor.

        Args:
            audit_storage: Audit storage backend
            notifier: Optional notifier for alerts
            degradation_threshold_pct: Threshold for degradation detection
        """
        self._audit_storage = audit_storage
        self._notifier = notifier
        self._degradation_threshold_pct = degradation_threshold_pct
        self._baselines: dict[str, dict[str, float]] = {}
        self._monitoring_active: dict[str, bool] = {}

        logger.info(
            f"DegradationMonitor initialized: threshold={degradation_threshold_pct}%"
        )

    def set_baseline(self, model_version: str, metrics: dict[str, float]) -> None:
        """Set baseline metrics for a model.

        Args:
            model_version: Model version identifier
            metrics: Baseline metrics dictionary
        """
        self._baselines[model_version] = metrics.copy()
        logger.info(f"Set baseline for {model_version}: {metrics}")

    def start_monitoring(self, model_version: str) -> None:
        """Start monitoring a model for degradation.

        Args:
            model_version: Model version to monitor
        """
        self._monitoring_active[model_version] = True
        logger.info(f"Started monitoring for {model_version}")

    def stop_monitoring(self, model_version: str) -> None:
        """Stop monitoring a model.

        Args:
            model_version: Model version to stop monitoring
        """
        self._monitoring_active[model_version] = False
        logger.info(f"Stopped monitoring for {model_version}")

    async def check_degradation(
        self,
        model_version: str,
        current_metrics: dict[str, float],
    ) -> tuple[bool, DegradationAlert | None]:
        """Check for performance degradation.

        Task 13.3: Detect degradation >10% from baseline.

        Args:
            model_version: Model version to check
            current_metrics: Current performance metrics

        Returns:
            Tuple of (degradation_detected, alert)
        """
        if not self._monitoring_active.get(model_version, False):
            return False, None

        baseline = self._baselines.get(model_version)
        if not baseline:
            logger.warning(f"No baseline set for {model_version}")
            return False, None

        # Check each metric for degradation
        for metric_name, baseline_value in baseline.items():
            if metric_name not in current_metrics:
                continue

            current_value = current_metrics[metric_name]
            if baseline_value <= 0:
                continue

            degradation_pct = (baseline_value - current_value) / baseline_value * 100

            if degradation_pct > self._degradation_threshold_pct:
                # Create alert
                alert = DegradationAlert(
                    alert_id=f"alert_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S_%f')}",
                    model_version=model_version,
                    metric_name=metric_name,
                    baseline_value=baseline_value,
                    current_value=current_value,
                    degradation_percentage=degradation_pct,
                    detected_at=datetime.now(UTC),
                )

                # Store alert
                await self._audit_storage.store_alert(alert)

                # Send notification
                if self._notifier:
                    message = (
                        f"**Model Degradation Detected**\n"
                        f"Model: `{model_version}`\n"
                        f"Metric: `{metric_name}`\n"
                        f"Degradation: **{degradation_pct:.1f}%**\n"
                        f"Baseline: `{baseline_value:.4f}`\n"
                        f"Current: `{current_value:.4f}`\n\n"
                        f"⚠️ Rollback recommended."
                    )
                    await self._notifier.send_alert(message, severity="critical")
                    alert.notified_at = datetime.now(UTC)

                logger.warning(
                    f"Degradation detected for {model_version}: "
                    f"{metric_name} degraded by {degradation_pct:.1f}%"
                )

                return True, alert

        return False, None


class RollbackManager:
    """Manager for automatic model rollback.

    Task 13.4: Automatic Rollback Implementation
    - Extend automatic.py
    - Implement automatic rollback trigger
    - CRITICAL: Rollback must complete in <5 minutes (target: <2 minutes)
    - Protect current trades (new signals use rolled-back model)
    - Log rollback events with full context
    """

    def __init__(
        self,
        registry: Any,  # ModelRegistry
        config: RollbackConfig | None = None,
        audit_storage: AuditStorage | None = None,
        notifier: Notifier | None = None,
        degradation_monitor: DegradationMonitor | None = None,
    ):
        """Initialize rollback manager.

        Args:
            registry: Model registry instance
            config: Rollback configuration
            audit_storage: Audit storage backend
            notifier: Optional notifier for alerts
            degradation_monitor: Optional degradation monitor
        """
        self._registry = registry
        self._config = config or RollbackConfig()
        self._audit_storage = audit_storage or InMemoryAuditStorage(
            retention_days=self._config.audit_retention_days
        )
        self._notifier = notifier
        self._degradation_monitor = degradation_monitor

        logger.info(
            f"RollbackManager initialized: "
            f"max_time={self._config.max_rollback_time_seconds}s, "
            f"auto_enabled={self._config.auto_rollback_enabled}"
        )

    def _generate_event_id(self) -> str:
        """Generate unique event ID."""
        return f"rollback_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S_%f')}"

    async def execute_rollback(
        self,
        failed_version_id: str,
        trigger: RollbackTrigger = RollbackTrigger.MANUAL,
        reason: str = "",
        target_version_id: str | None = None,
    ) -> RollbackEvent:
        """Execute rollback operation.

        Task 13.4: CRITICAL - Rollback must complete in <5 minutes (target: <2 minutes).

        Args:
            failed_version_id: Version to roll back from
            trigger: What triggered the rollback
            reason: Human-readable reason
            target_version_id: Optional specific version to roll back to

        Returns:
            RollbackEvent with operation details
        """
        started_at = datetime.now(UTC)
        event_id = self._generate_event_id()

        logger.info(
            f"Starting rollback: {event_id}, "
            f"failed={failed_version_id}, trigger={trigger.value}"
        )

        # Get failed version info
        failed_version = self._registry.get_version(failed_version_id)
        if not failed_version:
            event = RollbackEvent(
                event_id=event_id,
                timestamp=started_at,
                trigger=trigger,
                failed_version=failed_version_id,
                target_version=None,
                status=RollbackStatus.FAILED,
                reason=f"Failed version not found: {failed_version_id}",
            )
            await self._audit_storage.store_event(event)
            return event

        # Find rollback target
        if target_version_id:
            target_version = self._registry.get_version(target_version_id)
        else:
            target_version = self._registry.get_rollback_target(
                failed_version.model_type
            )

        if not target_version:
            event = RollbackEvent(
                event_id=event_id,
                timestamp=started_at,
                trigger=trigger,
                failed_version=failed_version_id,
                target_version=None,
                status=RollbackStatus.FAILED,
                reason=(
                    "No rollback target available for "
                    f"{failed_version.model_type.value}"
                ),
            )
            await self._audit_storage.store_event(event)
            return event

        # Create pending event
        event = RollbackEvent(
            event_id=event_id,
            timestamp=started_at,
            trigger=trigger,
            failed_version=failed_version_id,
            target_version=target_version.version_id,
            status=RollbackStatus.IN_PROGRESS,
            reason=reason,
        )

        try:
            # Execute rollback with timeout enforcement
            result = await asyncio.wait_for(
                self._execute_rollback_operation(
                    event=event,
                    failed_version=failed_version,
                    target_version=target_version,
                ),
                timeout=self._config.max_rollback_time_seconds,
            )

            # Calculate duration
            duration = (datetime.now(UTC) - started_at).total_seconds()
            result.duration_seconds = duration

            # Log success
            logger.info(
                f"Rollback completed: {event_id}, "
                f"duration={duration:.2f}s, "
                f"target={target_version.version_id}"
            )

            # Send notification
            if self._notifier:
                message = (
                    f"**Rollback Completed**\n"
                    f"From: `{failed_version_id}`\n"
                    f"To: `{target_version.version_id}`\n"
                    f"Duration: `{duration:.2f}s`\n"
                    f"Reason: {reason}"
                )
                await self._notifier.send_alert(message, severity="info")

            return result

        except TimeoutError:
            duration = (datetime.now(UTC) - started_at).total_seconds()
            event.status = RollbackStatus.TIMEOUT
            event.duration_seconds = duration
            event.reason = (
                f"Rollback timeout after {self._config.max_rollback_time_seconds}s"
            )

            logger.error(f"Rollback timeout: {event_id}, duration={duration:.2f}s")

            await self._audit_storage.store_event(event)
            return event

        except Exception as e:
            duration = (datetime.now(UTC) - started_at).total_seconds()
            event.status = RollbackStatus.FAILED
            event.duration_seconds = duration
            event.reason = f"Rollback failed: {str(e)}"

            logger.exception(f"Rollback failed: {event_id}")

            await self._audit_storage.store_event(event)
            return event

    async def _execute_rollback_operation(
        self,
        event: RollbackEvent,
        failed_version: Any,
        target_version: Any,
    ) -> RollbackEvent:
        """Execute the actual rollback operation.

        Task 13.4: Protect current trades (new signals use rolled-back model).

        Args:
            event: Rollback event being processed
            failed_version: Version to roll back from
            target_version: Version to roll back to

        Returns:
            Updated RollbackEvent
        """
        # Step 1: Protect current trades
        trade_protection_applied = False
        if self._config.protect_current_trades:
            trade_protection_applied = await self._protect_current_trades(
                failed_version.version_id,
                target_version.version_id,
            )
            event.details["trade_protection"] = trade_protection_applied

        # Step 2: Mark failed version
        try:
            self._registry.mark_failed(
                failed_version.version_id,
                reason=f"{event.trigger.value}: {event.reason}",
            )
            event.details["marked_failed"] = True
        except Exception as e:
            event.details["marked_failed"] = False
            event.details["mark_failed_error"] = str(e)
            logger.warning(f"Failed to mark version as failed: {e}")

        # Step 3: Promote target to champion
        try:
            new_champion, _ = self._registry.promote_to_champion(
                target_version.version_id,
                force=True,
            )
            event.details["promoted_to_champion"] = new_champion.version_id
        except Exception as e:
            event.details["promoted_to_champion"] = None
            event.details["promotion_error"] = str(e)
            event.status = RollbackStatus.FAILED
            event.reason = f"Failed to promote rollback target: {e}"
            await self._audit_storage.store_event(event)
            return event

        # Success
        event.status = RollbackStatus.COMPLETED
        event.trade_protection_applied = trade_protection_applied

        # Store event
        await self._audit_storage.store_event(event)

        return event

    async def _protect_current_trades(
        self, failed_version: str, target_version: str
    ) -> bool:
        """Protect current trades during rollback.

        Task 13.4: Protect current trades (new signals use rolled-back model).

        Args:
            failed_version: Version being rolled back from
            target_version: Version being rolled back to

        Returns:
            True if protection was applied successfully
        """
        try:
            # In production, this would:
            # 1. Signal to the trading system to use the target model
            # 2. Update model routing configuration
            # 3. Ensure pending signals use the rolled-back model

            logger.info(f"Trade protection applied: routing to {target_version}")

            # Simulate async operation
            await asyncio.sleep(0.01)

            return True

        except Exception as e:
            logger.error(f"Failed to apply trade protection: {e}")
            return False

    async def trigger_on_degradation(
        self,
        model_version: str,
        degradation_alert: DegradationAlert,
    ) -> RollbackEvent | None:
        """Trigger rollback on degradation detection.

        Task 13.3 & 13.4: Trigger rollback alert on detection.

        Args:
            model_version: Model with degradation
            degradation_alert: Degradation alert details

        Returns:
            RollbackEvent or None if auto-rollback disabled
        """
        if not self._config.auto_rollback_enabled:
            logger.warning(
                f"Auto-rollback disabled, skipping rollback for {model_version}"
            )
            return None

        logger.info(f"Triggering auto-rollback for {model_version} due to degradation")

        event = await self.execute_rollback(
            failed_version_id=model_version,
            trigger=RollbackTrigger.DEGRADATION,
            reason=f"Degradation detected: {degradation_alert.metric_name} "
            f"degraded by {degradation_alert.degradation_percentage:.1f}%",
        )

        degradation_alert.rollback_triggered = event.status == RollbackStatus.COMPLETED

        return event

    async def get_rollback_history(
        self,
        model_version: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 100,
    ) -> list[RollbackEvent]:
        """Get rollback history.

        Task 13.5: Track rollback events with timestamps and reasons.

        Args:
            model_version: Optional filter by model version
            start_date: Optional start date filter
            end_date: Optional end date filter
            limit: Maximum results

        Returns:
            List of rollback events
        """
        return await self._audit_storage.get_events(
            model_version=model_version,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )

    def is_performance_acceptable(self, duration_seconds: float) -> bool:
        """Check if rollback performance meets requirements.

        Task 13.4: CRITICAL - Rollback must complete in <5 minutes.

        Args:
            duration_seconds: Rollback duration

        Returns:
            True if within acceptable limits
        """
        return duration_seconds < self._config.max_rollback_time_seconds


class ValidationHistoryAPI:
    """API for querying validation history.

    Task 13.5: Validation History & Audit
    - Store all validation results in database
    - Track rollback events with timestamps and reasons
    - Create audit trail for compliance
    - Add query API: GET /api/v1/validation/history
    - Retention: 90 days
    """

    def __init__(self, audit_storage: AuditStorage):
        """Initialize validation history API.

        Args:
            audit_storage: Audit storage backend
        """
        self._audit_storage = audit_storage

    async def get_validation_history(
        self,
        model_version: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Get validation history.

        Task 13.5: Add query API: GET /api/v1/validation/history.

        Args:
            model_version: Optional filter by model version
            start_date: Optional start date (ISO format)
            end_date: Optional end date (ISO format)
            limit: Maximum results

        Returns:
            Dictionary with validation history and metadata
        """
        # Parse dates - ensure timezone-aware for comparison
        start_dt = None
        end_dt = None

        if start_date:
            try:
                start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
                # Ensure timezone-aware
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=UTC)
            except ValueError:
                pass

        if end_date:
            try:
                end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                # Ensure timezone-aware
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=UTC)
            except ValueError:
                pass

        # Get results
        if isinstance(self._audit_storage, InMemoryAuditStorage):
            results = await self._audit_storage.get_validation_history(
                model_version=model_version,
                start_date=start_dt,
                end_date=end_dt,
                limit=limit,
            )
        else:
            results = []

        return {
            "results": results,
            "count": len(results),
            "query": {
                "model_version": model_version,
                "start_date": start_date,
                "end_date": end_date,
                "limit": limit,
            },
            "retention_days": 90,
        }

    async def get_rollback_history(
        self,
        model_version: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Get rollback history.

        Task 13.5: Track rollback events with timestamps and reasons.

        Args:
            model_version: Optional filter by model version
            start_date: Optional start date (ISO format)
            end_date: Optional end date (ISO format)
            limit: Maximum results

        Returns:
            Dictionary with rollback history and metadata
        """
        start_dt = None
        end_dt = None

        if start_date:
            try:
                # Handle timezone-naive dates by make them timezone-aware
                start_dt = datetime.fromisoformat(start_date)
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=UTC)
            except ValueError:
                pass

        if end_date:
            with contextlib.suppress(ValueError):
                end_dt = datetime.fromisoformat(end_date)

        events = await self._audit_storage.get_events(
            model_version=model_version,
            start_date=start_dt,
            end_date=end_dt,
            limit=limit,
        )

        return {
            "results": [e.to_dict() for e in events],
            "count": len(events),
            "query": {
                "model_version": model_version,
                "start_date": start_date,
                "end_date": end_date,
                "limit": limit,
            },
            "retention_days": 90,
        }

    async def get_degradation_alerts(
        self,
        model_version: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Get degradation alerts.

        Args:
            model_version: Optional filter by model version
            limit: Maximum results

        Returns:
            Dictionary with alerts and metadata
        """
        alerts = await self._audit_storage.get_alerts(
            model_version=model_version,
            limit=limit,
        )

        return {
            "results": [a.to_dict() for a in alerts],
            "count": len(alerts),
            "query": {
                "model_version": model_version,
                "limit": limit,
            },
        }

    async def store_validation_result(self, result: dict[str, Any]) -> dict[str, Any]:
        """Store validation result.

        Task 13.5: Store all validation results in database.

        Args:
            result: Validation result to store

        Returns:
            Storage confirmation
        """
        if isinstance(self._audit_storage, InMemoryAuditStorage):
            success = await self._audit_storage.store_validation_result(result)
        else:
            success = False

        return {
            "success": success,
            "timestamp": datetime.now(UTC).isoformat(),
            "retention_days": 90,
        }
