"""Incident Manager with Auto-Remediation.

Main engine that coordinates incident lifecycle management, severity classification,
auto-remediation, notifications, and post-mortem generation.

For ST-NS-041: Incident Manager with Auto-Remediation
"""

from __future__ import annotations

import asyncio
import builtins
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from src.autonomous_control_plane.models.incidents import (
    P0_EVENT_TYPES,
    P1_EVENT_TYPES,
    P2_EVENT_TYPES,
    Incident,
    IncidentEvent,
    IncidentMetrics,
    IncidentStatus,
    IncidentStore,
    Notification,
    NotificationChannel,
    PostMortem,
    RemediationAction,
    Severity,
)

logger = logging.getLogger(__name__)


class AutoRemediationEngine:
    """Engine for auto-remediation of incidents.

    Handles known solution registry, auto-execution for P2/P3,
    and human approval gates for P0/P1.
    """

    # Registry of known remediation patterns
    # pattern_key -> {severities: [Severity], action: callable, auto_execute: bool}
    REMEDIATION_RULES: dict[str, dict[str, Any]] = {
        "redis_connection_failed": {
            "severities": [Severity.P2, Severity.P3],
            "action": "restart_redis_connection_pool",
            "description": "Restart Redis connection pool",
            "auto_execute": True,
        },
        "service_unhealthy": {
            "severities": [Severity.P2, Severity.P3],
            "action": "restart_service",
            "description": "Restart unhealthy service",
            "auto_execute": True,
        },
        "cache_stale": {
            "severities": [Severity.P2, Severity.P3],
            "action": "clear_cache",
            "description": "Clear stale cache entries",
            "auto_execute": True,
        },
        "config_reload_needed": {
            "severities": [Severity.P2, Severity.P3],
            "action": "reload_config",
            "description": "Reload configuration",
            "auto_execute": True,
        },
        "high_memory_usage": {
            "severities": [Severity.P1, Severity.P2],
            "action": "trigger_gc_and_alert",
            "description": "Trigger garbage collection and alert",
            "auto_execute": False,  # Requires approval
        },
        "failover_needed": {
            "severities": [Severity.P1],
            "action": "trigger_failover",
            "description": "Trigger failover to backup",
            "auto_execute": False,  # Requires approval
        },
    }

    def __init__(self, action_handlers: dict[str, Callable] | None = None):
        """Initialize auto-remediation engine.

        Args:
            action_handlers: Custom action handlers to register
        """
        self._action_handlers: dict[str, Callable] = action_handlers or {}
        self._register_default_handlers()

    def _register_default_handlers(self) -> None:
        """Register default remediation action handlers."""
        # These are placeholder handlers - real implementations would be injected
        self._action_handlers.setdefault(
            "restart_redis_connection_pool",
            self._handle_restart_redis,
        )
        self._action_handlers.setdefault(
            "restart_service",
            self._handle_restart_service,
        )
        self._action_handlers.setdefault(
            "clear_cache",
            self._handle_clear_cache,
        )
        self._action_handlers.setdefault(
            "reload_config",
            self._handle_reload_config,
        )
        self._action_handlers.setdefault(
            "trigger_gc_and_alert",
            self._handle_trigger_gc,
        )
        self._action_handlers.setdefault(
            "trigger_failover",
            self._handle_failover,
        )

    def _handle_restart_redis(self, context: dict[str, Any]) -> dict[str, Any]:
        """Handle Redis connection pool restart."""
        logger.info("Auto-remediation: Restarting Redis connection pool")
        # Placeholder - actual implementation would restart connections
        return {"success": True, "message": "Redis connection pool restarted"}

    def _handle_restart_service(self, context: dict[str, Any]) -> dict[str, Any]:
        """Handle service restart."""
        service = context.get("service", "unknown")
        logger.info(f"Auto-remediation: Restarting service {service}")
        # Placeholder - actual implementation would restart service
        return {"success": True, "message": f"Service {service} restarted"}

    def _handle_clear_cache(self, context: dict[str, Any]) -> dict[str, Any]:
        """Handle cache clear."""
        logger.info("Auto-remediation: Clearing cache")
        # Placeholder - actual implementation would clear cache
        return {"success": True, "message": "Cache cleared"}

    def _handle_reload_config(self, context: dict[str, Any]) -> dict[str, Any]:
        """Handle config reload."""
        logger.info("Auto-remediation: Reloading configuration")
        # Placeholder - actual implementation would reload config
        return {"success": True, "message": "Configuration reloaded"}

    def _handle_trigger_gc(self, context: dict[str, Any]) -> dict[str, Any]:
        """Handle garbage collection trigger."""
        logger.info("Auto-remediation: Triggering garbage collection")
        import gc

        gc.collect()
        return {"success": True, "message": "Garbage collection triggered"}

    def _handle_failover(self, context: dict[str, Any]) -> dict[str, Any]:
        """Handle failover."""
        logger.info("Auto-remediation: Triggering failover")
        # Placeholder - actual implementation would trigger failover
        return {"success": True, "message": "Failover triggered"}

    def find_remediation(
        self, event_type: str, severity: Severity
    ) -> dict[str, Any] | None:
        """Find remediation rule for event type and severity.

        Args:
            event_type: Type of event
            severity: Incident severity

        Returns:
            Remediation rule or None if no match
        """
        rule = self.REMEDIATION_RULES.get(event_type)
        if rule and severity in rule["severities"]:
            return rule
        return None

    async def execute_remediation(
        self,
        rule: dict[str, Any],
        incident: Incident,
        auto_execute: bool = False,
    ) -> RemediationAction:
        """Execute a remediation action.

        Args:
            rule: Remediation rule to execute
            incident: Parent incident
            auto_execute: Whether to auto-execute without approval

        Returns:
            Remediation action result
        """
        action_type = rule["action"]
        description = rule["description"]
        should_auto = rule.get("auto_execute", False)

        action = RemediationAction(
            action_type=action_type,
            description=description,
        )

        # Check if auto-execution is allowed
        if not should_auto or not auto_execute:
            logger.info(
                f"Remediation action {action_type} requires manual approval "
                f"for incident {incident.incident_id}"
            )
            action.status = "awaiting_approval"
            return action

        # Execute the action
        handler = self._action_handlers.get(action_type)
        if not handler:
            logger.error(f"No handler for remediation action: {action_type}")
            action.status = "failed"
            action.result = {"success": False, "error": f"No handler for {action_type}"}
            return action

        try:
            context = {
                "incident_id": incident.incident_id,
                "service": incident.source,
                "severity": incident.severity.value,
            }
            result = handler(context)
            action.mark_executed(result, auto=True)
            logger.info(
                f"Auto-remediation {action_type} executed for incident "
                f"{incident.incident_id}: {result.get('message', 'success')}"
            )
        except Exception as e:
            logger.exception(f"Auto-remediation failed: {e}")
            action.status = "failed"
            action.result = {"success": False, "error": str(e)}

        return action

    def register_action_handler(self, action_type: str, handler: Callable) -> None:
        """Register a custom action handler.

        Args:
            action_type: Action type identifier
            handler: Callable that executes the action
        """
        self._action_handlers[action_type] = handler


class NotificationDispatcher:
    """Dispatcher for incident notifications.

    Handles immediate P0/P1 notifications and batched P2/P3 digests.
    """

    def __init__(
        self,
        discord_webhook_url: str | None = None,
        grafana_oncall_url: str | None = None,
        grafana_oncall_token: str | None = None,
    ):
        """Initialize notification dispatcher.

        Args:
            discord_webhook_url: Discord webhook URL for notifications
            grafana_oncall_url: Grafana On-Call API URL
            grafana_oncall_token: Grafana On-Call API token
        """
        self._discord_webhook = discord_webhook_url
        self._grafana_oncall_url = grafana_oncall_url
        self._grafana_oncall_token = grafana_oncall_token
        self._pending_digest: list[Incident] = []
        self._digest_interval_minutes = 15

    def get_notification_template(self, incident: Incident) -> str:
        """Get notification message template for incident severity.

        Args:
            incident: Incident to generate notification for

        Returns:
            Formatted notification message
        """
        templates = {
            Severity.P0: "🚨 CRITICAL: {title} - Immediate action required",
            Severity.P1: "⚠️ HIGH: {title} - Respond within 15 minutes",
            Severity.P2: "📋 MEDIUM: {title}",
            Severity.P3: "📝 LOW: {title}",
        }

        template = templates.get(incident.severity, "📋 {title}")
        return template.format(title=incident.title)

    async def dispatch(self, incident: Incident) -> list[Notification]:
        """Dispatch notifications for an incident.

        Args:
            incident: Incident to notify about

        Returns:
            List of sent notifications
        """
        notifications: list[Notification] = []

        # P0/P1: Immediate notification via Discord and Grafana On-Call
        if incident.severity in [Severity.P0, Severity.P1]:
            if self._discord_webhook:
                notification = await self._send_discord(incident)
                if notification:
                    notifications.append(notification)

            if self._grafana_oncall_url and self._grafana_oncall_token:
                notification = await self._send_grafana_oncall(incident)
                if notification:
                    notifications.append(notification)
        else:
            # P2/P3: Add to digest
            self._pending_digest.append(incident)
            logger.debug(
                f"Incident {incident.incident_id} added to notification digest"
            )

        return notifications

    async def _send_discord(self, incident: Incident) -> Notification | None:
        """Send Discord notification.

        Args:
            incident: Incident to notify about

        Returns:
            Notification record or None if failed
        """
        import aiohttp

        content = self.get_notification_template(incident)
        embed = {
            "title": f"[{incident.severity.value}] {incident.title}",
            "description": incident.description,
            "color": self._get_severity_color(incident.severity),
            "fields": [
                {"name": "Source", "value": incident.source, "inline": True},
                {"name": "Incident ID", "value": incident.incident_id, "inline": True},
                {"name": "Status", "value": incident.status.value, "inline": True},
            ],
            "timestamp": incident.created_at.isoformat(),
        }

        payload = {
            "content": content,
            "embeds": [embed],
        }

        if not self._discord_webhook:
            return None

        try:
            async with (
                aiohttp.ClientSession() as session,
                session.post(
                    self._discord_webhook,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response,
            ):
                if response.status in (200, 204):
                    logger.info(
                        f"Discord notification sent for incident {incident.incident_id}"
                    )
                    return Notification(
                        channel=NotificationChannel.DISCORD,
                        content=content,
                    )
                else:
                    logger.warning(f"Discord notification failed: {response.status}")
        except Exception as e:
            logger.exception(f"Failed to send Discord notification: {e}")

        return None

    async def _send_grafana_oncall(self, incident: Incident) -> Notification | None:
        """Send Grafana On-Call alert.

        Args:
            incident: Incident to alert about

        Returns:
            Notification record or None if failed
        """
        import aiohttp

        if not self._grafana_oncall_url or not self._grafana_oncall_token:
            return None

        content = self.get_notification_template(incident)

        # Build Grafana On-Call alert payload
        payload = {
            "alert_uid": incident.incident_id,
            "title": f"[{incident.severity.value}] {incident.title}",
            "message": incident.description,
            "image_url": None,
            "state": (
                "alerting" if incident.severity in [Severity.P0, Severity.P1] else "ok"
            ),
            "link_to_upstream_details": None,
        }

        headers = {"Authorization": f"Bearer {self._grafana_oncall_token}"}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self._grafana_oncall_url}/api/v1/webhooks/",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status in (200, 201):
                        logger.info(
                            f"Grafana On-Call alert sent for incident {incident.incident_id}"
                        )
                        return Notification(
                            channel=NotificationChannel.GRAFANA_ONCALL,
                            content=content,
                        )
                    else:
                        logger.warning(
                            f"Grafana On-Call alert failed: {response.status}"
                        )
        except Exception as e:
            logger.exception(f"Failed to send Grafana On-Call alert: {e}")

        return None

    def _get_severity_color(self, severity: Severity) -> int:
        """Get Discord embed color for severity.

        Args:
            severity: Incident severity

        Returns:
            Integer color code
        """
        colors = {
            Severity.P0: 0xFF0000,  # Red
            Severity.P1: 0xFF8800,  # Orange
            Severity.P2: 0xFFFF00,  # Yellow
            Severity.P3: 0x00FF00,  # Green
        }
        return colors.get(severity, 0x808080)  # Gray default

    async def send_digest(self) -> list[Notification]:
        """Send batched digest of P2/P3 incidents.

        Returns:
            List of sent notifications
        """
        if not self._pending_digest:
            return []

        notifications: list[Notification] = []

        if self._discord_webhook:
            content = "📊 **Incident Digest**\n\n"
            for incident in self._pending_digest[-10:]:  # Last 10
                content += f"• [{incident.severity.value}] {incident.title}\n"

            try:
                import aiohttp

                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        self._discord_webhook,
                        json={"content": content},
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as response:
                        if response.status in (200, 204):
                            notifications.append(
                                Notification(
                                    channel=NotificationChannel.DISCORD,
                                    content=content,
                                )
                            )
            except Exception as e:
                logger.exception(f"Failed to send digest: {e}")

        self._pending_digest = []
        return notifications


class InMemoryIncidentStore(IncidentStore):
    """In-memory implementation of incident storage."""

    def __init__(self) -> None:
        """Initialize in-memory store."""
        self._incidents: dict[str, Incident] = {}
        self._lock = asyncio.Lock()

    async def save(self, incident: Incident) -> None:
        """Save or update an incident."""
        async with self._lock:
            self._incidents[incident.incident_id] = incident

    async def get(self, incident_id: str) -> Incident | None:
        """Get incident by ID."""
        return self._incidents.get(incident_id)

    async def list(
        self,
        status: IncidentStatus | None = None,
        severity: Severity | None = None,
        source: str | None = None,
        limit: int = 100,
    ) -> builtins.list[Incident]:
        """List incidents with optional filtering."""
        incidents = list(self._incidents.values())

        if status:
            incidents = [i for i in incidents if i.status == status]
        if severity:
            incidents = [i for i in incidents if i.severity == severity]
        if source:
            incidents = [i for i in incidents if i.source == source]

        # Sort by created_at descending
        incidents.sort(key=lambda i: i.created_at, reverse=True)
        return incidents[:limit]

    async def delete(self, incident_id: str) -> bool:
        """Delete an incident."""
        async with self._lock:
            if incident_id in self._incidents:
                del self._incidents[incident_id]
                return True
            return False

    async def get_all(self) -> builtins.list[Incident]:
        """Get all incidents."""
        return list(self._incidents.values())


class IncidentManager:
    """Central incident manager with auto-remediation.

    Features:
    - Auto incident creation from system events
    - P0-P3 severity classification
    - Auto-remediation for P2/P3 with known solutions
    - P0/P1 immediate notifications (Discord + Grafana On-Call)
    - Incident state transitions (open→investigating→resolved)
    - Auto-generated post-mortems on resolution
    - Incident metrics export

    Example:
        >>> manager = IncidentManager()
        >>> event = IncidentEvent(
        ...     event_type="service_down",
        ...     source="api-gateway",
        ...     message="API gateway is not responding"
        ... )
        >>> incident = await manager.create_incident(event)
        >>> await manager.resolve_incident(incident.incident_id, "Service restarted")
    """

    # Valid state transitions
    VALID_TRANSITIONS: dict[IncidentStatus, set[IncidentStatus]] = {
        IncidentStatus.OPEN: {IncidentStatus.INVESTIGATING, IncidentStatus.RESOLVED},
        IncidentStatus.INVESTIGATING: {
            IncidentStatus.MITIGATED,
            IncidentStatus.RESOLVED,
            IncidentStatus.OPEN,
        },
        IncidentStatus.MITIGATED: {
            IncidentStatus.RESOLVED,
            IncidentStatus.INVESTIGATING,
        },
        IncidentStatus.RESOLVED: {IncidentStatus.CLOSED, IncidentStatus.OPEN},
        IncidentStatus.CLOSED: {IncidentStatus.OPEN},
    }

    def __init__(
        self,
        store: IncidentStore | None = None,
        discord_webhook_url: str | None = None,
        grafana_oncall_url: str | None = None,
        grafana_oncall_token: str | None = None,
    ):
        """Initialize incident manager.

        Args:
            store: Incident storage backend (defaults to in-memory)
            discord_webhook_url: Discord webhook for notifications
            grafana_oncall_url: Grafana On-Call API URL
            grafana_oncall_token: Grafana On-Call API token
        """
        self._store = store or InMemoryIncidentStore()
        self._remediation_engine = AutoRemediationEngine()
        self._notification_dispatcher = NotificationDispatcher(
            discord_webhook_url=discord_webhook_url,
            grafana_oncall_url=grafana_oncall_url,
            grafana_oncall_token=grafana_oncall_token,
        )
        self._metrics = IncidentMetrics()

        # Event callbacks for integration
        self._on_incident_created: list[Callable] = []
        self._on_incident_resolved: list[Callable] = []
        self._on_incident_escalated: list[Callable] = []

        logger.info("IncidentManager initialized")

    def classify_severity(self, event: IncidentEvent) -> Severity:
        """Classify incident severity from event.

        Classification rules:
        - P0: service_down, data_loss, security_breach, trading_failure
        - P1: performance_degraded, high_error_rate, api_failure
        - P2: service_unhealthy, cache_miss_high, queue_backlog
        - P3: deprecated_api_usage, minor_error, cleanup_needed

        Args:
            event: Event to classify

        Returns:
            Severity level (P0-P3)
        """
        # Check explicit severity hint first
        if event.severity_hint:
            return event.severity_hint

        event_type = event.event_type.lower()

        # P0: Critical issues
        if event_type in P0_EVENT_TYPES:
            return Severity.P0

        # Check for keywords in event type and message
        p0_keywords = ["critical", "crash", "corruption", "breach", "down"]
        if any(kw in event_type or kw in event.message.lower() for kw in p0_keywords):
            return Severity.P0

        # P1: High impact
        if event_type in P1_EVENT_TYPES:
            return Severity.P1

        p1_keywords = ["degraded", "high", "failure", "slow", "full"]
        if any(kw in event_type or kw in event.message.lower() for kw in p1_keywords):
            return Severity.P1

        # P2: Medium impact
        if event_type in P2_EVENT_TYPES:
            return Severity.P2

        p2_keywords = ["unhealthy", "backlog", "exhausted", "increased", "miss"]
        if any(kw in event_type or kw in event.message.lower() for kw in p2_keywords):
            return Severity.P2

        # Default to P3 (lowest)
        return Severity.P3

    async def create_incident(self, event: IncidentEvent) -> Incident:
        """Create incident from event.

        Args:
            event: Event that triggered the incident

        Returns:
            Created incident
        """
        severity = self.classify_severity(event)

        incident = Incident(
            title=f"{event.event_type}: {event.source}",
            description=event.message,
            severity=severity,
            source=event.source,
            triggered_by_event=event.event_id,
            metadata=event.metadata,
        )

        # Save incident
        await self._store.save(incident)
        self._metrics.record_incident(incident)

        # Dispatch notifications
        notifications = await self._notification_dispatcher.dispatch(incident)
        for notification in notifications:
            incident.add_notification(notification)

        # Attempt auto-remediation for P2/P3
        if severity in [Severity.P2, Severity.P3]:
            await self._attempt_auto_remediation(incident)

        # Trigger callbacks
        for callback in self._on_incident_created:
            try:
                await callback(incident)
            except Exception as e:
                logger.exception(f"Incident created callback failed: {e}")

        logger.info(
            f"Incident created: {incident.incident_id} "
            f"(severity={severity.value}, source={event.source})"
        )

        return incident

    async def _attempt_auto_remediation(self, incident: Incident) -> None:
        """Attempt auto-remediation for an incident.

        Args:
            incident: Incident to remediate
        """
        if not incident.triggered_by_event:
            return

        # Find remediation rule
        rule = self._remediation_engine.find_remediation(
            incident.metadata.get("event_type", ""),
            incident.severity,
        )

        if not rule:
            return

        # Execute remediation
        action = await self._remediation_engine.execute_remediation(
            rule, incident, auto_execute=True
        )

        incident.add_remediation_action(action)
        await self._store.save(incident)

        if action.status == "executed":
            logger.info(
                f"Auto-remediation executed for incident {incident.incident_id}"
            )
        elif action.status == "awaiting_approval":
            logger.info(
                f"Auto-remediation awaiting approval for incident {incident.incident_id}"
            )

    async def transition_status(
        self, incident_id: str, new_status: IncidentStatus
    ) -> Incident | None:
        """Transition incident to new status.

        Args:
            incident_id: ID of incident to transition
            new_status: New status to transition to

        Returns:
            Updated incident or None if not found
        """
        incident = await self._store.get(incident_id)
        if not incident:
            return None

        # Validate transition
        if new_status not in self.VALID_TRANSITIONS.get(incident.status, set()):
            logger.warning(
                f"Invalid status transition: {incident.status.value} -> {new_status.value}"
            )
            return incident

        incident.update_status(new_status)
        await self._store.save(incident)

        logger.info(
            f"Incident {incident_id} transitioned: "
            f"{incident.status.value} -> {new_status.value}"
        )

        return incident

    async def assign_incident(self, incident_id: str, assignee: str) -> Incident | None:
        """Assign incident to someone.

        Args:
            incident_id: ID of incident to assign
            assignee: Person to assign to

        Returns:
            Updated incident or None if not found
        """
        incident = await self._store.get(incident_id)
        if not incident:
            return None

        incident.assign(assignee)
        await self._store.save(incident)

        logger.info(f"Incident {incident_id} assigned to {assignee}")
        return incident

    async def resolve_incident(
        self, incident_id: str, resolution_notes: str
    ) -> Incident | None:
        """Resolve an incident and generate post-mortem.

        Args:
            incident_id: ID of incident to resolve
            resolution_notes: Notes on resolution

        Returns:
            Updated incident or None if not found
        """
        incident = await self._store.get(incident_id)
        if not incident:
            return None

        incident.resolve(resolution_notes)

        # Generate post-mortem
        _ = incident.generate_post_mortem()
        logger.info(f"Post-mortem generated for incident {incident_id}")

        await self._store.save(incident)

        # Trigger callbacks
        for callback in self._on_incident_resolved:
            try:
                await callback(incident)
            except Exception as e:
                logger.exception(f"Incident resolved callback failed: {e}")

        logger.info(f"Incident {incident_id} resolved")
        return incident

    async def close_incident(self, incident_id: str) -> Incident | None:
        """Close a resolved incident.

        Args:
            incident_id: ID of incident to close

        Returns:
            Updated incident or None if not found
        """
        incident = await self._store.get(incident_id)
        if not incident:
            return None

        incident.close()
        await self._store.save(incident)

        logger.info(f"Incident {incident_id} closed")
        return incident

    async def reopen_incident(self, incident_id: str) -> Incident | None:
        """Reopen a resolved/closed incident.

        Args:
            incident_id: ID of incident to reopen

        Returns:
            Updated incident or None if not found
        """
        incident = await self._store.get(incident_id)
        if not incident:
            return None

        incident.reopen()
        await self._store.save(incident)

        logger.info(f"Incident {incident_id} reopened")
        return incident

    async def get_incident(self, incident_id: str) -> Incident | None:
        """Get incident by ID.

        Args:
            incident_id: ID of incident to retrieve

        Returns:
            Incident or None if not found
        """
        return await self._store.get(incident_id)

    async def list_incidents(
        self,
        status: IncidentStatus | None = None,
        severity: Severity | None = None,
        source: str | None = None,
        limit: int = 100,
    ) -> list[Incident]:
        """List incidents with optional filtering.

        Args:
            status: Filter by status
            severity: Filter by severity
            source: Filter by source
            limit: Maximum results

        Returns:
            List of incidents
        """
        return await self._store.list(status, severity, source, limit)

    async def get_post_mortem(self, incident_id: str) -> PostMortem | None:
        """Get post-mortem for an incident.

        Args:
            incident_id: ID of incident

        Returns:
            Post-mortem or None if not found/not generated
        """
        incident = await self._store.get(incident_id)
        if incident and incident.post_mortem:
            return incident.post_mortem
        return None

    async def get_metrics(self) -> IncidentMetrics:
        """Get current incident metrics.

        Returns:
            Incident metrics
        """
        incidents = (
            await self._store.get_all() if hasattr(self._store, "get_all") else []
        )
        self._metrics.update_status_counts(incidents)
        self._metrics.calculate_resolution_stats(incidents)

        # Calculate creation rate (incidents per hour in last 24h)
        now = datetime.now(UTC)
        cutoff = now - timedelta(hours=24)
        recent = [i for i in incidents if i.created_at > cutoff]
        if recent:
            hours = 24
            self._metrics.creation_rate = len(recent) / hours

        # Calculate escalation rate (P0/P1 as percentage)
        if incidents:
            critical = sum(
                1 for i in incidents if i.severity in [Severity.P0, Severity.P1]
            )
            self._metrics.escalation_rate = (critical / len(incidents)) * 100

        return self._metrics

    def on_incident_created(self, callback: Callable) -> None:
        """Register callback for incident creation.

        Args:
            callback: Async function to call when incident is created
        """
        self._on_incident_created.append(callback)

    def on_incident_resolved(self, callback: Callable) -> None:
        """Register callback for incident resolution.

        Args:
            callback: Async function to call when incident is resolved
        """
        self._on_incident_resolved.append(callback)

    def on_incident_escalated(self, callback: Callable) -> None:
        """Register callback for incident escalation.

        Args:
            callback: Async function to call when incident is escalated
        """
        self._on_incident_escalated.append(callback)

    async def approve_remediation(
        self, incident_id: str, action_id: str, approved_by: str
    ) -> RemediationAction | None:
        """Approve and execute a pending remediation action.

        Args:
            incident_id: ID of incident
            action_id: ID of action to approve
            approved_by: Who approved the action

        Returns:
            Updated action or None if not found
        """
        incident = await self._store.get(incident_id)
        if not incident:
            return None

        action = None
        for a in incident.remediation_actions:
            if a.action_id == action_id:
                action = a
                break

        if not action or action.status != "awaiting_approval":
            return None

        # Execute the action
        rule = self._remediation_engine.find_remediation(
            action.action_type.replace("_", "_"),  # Normalize
            incident.severity,
        )

        if rule:
            result = await self._remediation_engine.execute_remediation(
                rule, incident, auto_execute=True
            )
            action.status = result.status
            action.result = result.result
            action.executed_at = datetime.now(UTC)
            action.auto_executed = False
            action.approved_by = approved_by

            await self._store.save(incident)
            logger.info(
                f"Remediation action {action_id} approved by {approved_by} "
                f"for incident {incident_id}"
            )

        return action
