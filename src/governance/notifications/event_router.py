"""Event router for notification routing based on notification-policy.yaml.

Routes governance events to either immediate alerts or daily digest based on:
- Event type (always_send_for list → immediate)
- Severity level (high/critical → immediate, medium/low → digest)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

from .discord_notifier import DiscordNotifier

logger = logging.getLogger(__name__)

# Timezone for digest scheduling
TORONTO_TZ = ZoneInfo("America/Toronto")

# Redis key for feature flag
REDIS_FLAG_KEY = "chise:feature_flags:governance:notification_routing_enabled"


def _get_redis_client():
    """Get Redis client with graceful fallback."""
    try:
        from tools.redis_state import redis_state_hget

        return {"get": redis_state_hget}
    except ImportError:
        return None


# SeverityMapper is optional - imported lazily if available
# (created by ST-03A severity_mapper story)
try:
    from .severity_mapper import SeverityMapper

    _SEVERITY_MAPPER_AVAILABLE = True
except ImportError:
    SeverityMapper = None
    _SEVERITY_MAPPER_AVAILABLE = False
    logger.debug("SeverityMapper not available, using severity-based routing only")


@dataclass
class RoutingDecision:
    """Result of routing decision."""

    mode: str  # "immediate" or "digest"
    reason: str  # Human-readable reason
    event_id: str | None = None


class NotificationEventRouter:
    """Routes notification events to immediate or digest based on policy.

    Usage:
        router = NotificationEventRouter()
        decision = router.route_event({
            "event_type": "approval_request",
            "severity": "medium",
            "event_id": "evt-001",
            ...
        })
        # decision.mode == "immediate"
    """

    def __init__(
        self,
        notifier: DiscordNotifier | None = None,
        severity_mapper: Any = None,  # Optional, type hint kept generic for compatibility
        policy_path: str | None = None,
    ):
        """Initialize the NotificationEventRouter.

        Args:
            notifier: DiscordNotifier instance. Creates new if None.
            severity_mapper: SeverityMapper instance. Creates new if available.
            policy_path: Optional path to notification-policy.yaml.
        """
        self._notifier = notifier
        self._severity_mapper = severity_mapper
        self._policy_path = policy_path
        self._policy: dict[str, Any] | None = None

    @property
    def notifier(self) -> DiscordNotifier:
        """Get DiscordNotifier instance, lazily initialized."""
        if self._notifier is None:
            self._notifier = DiscordNotifier()
        return self._notifier

    @property
    def severity_mapper(self) -> Any:
        """Get SeverityMapper instance, lazily initialized if available."""
        if self._severity_mapper is None and _SEVERITY_MAPPER_AVAILABLE:
            self._severity_mapper = SeverityMapper(policy_path=self._policy_path)
        return self._severity_mapper

    def _load_policy(self) -> dict[str, Any]:
        """Load notification policy from YAML file."""
        if self._policy is not None:
            return self._policy

        if self._policy_path is None:
            # Navigate from event_router.py to worktree root (4 levels up)
            # event_router.py -> notifications -> governance -> src -> worktree_root
            repo_root = Path(__file__).parent.parent.parent.parent
            self._policy_path = str(
                repo_root / "config" / "aria" / "notification-policy.yaml"
            )

        try:
            policy_file = Path(self._policy_path)
            if policy_file.exists():
                with open(self._policy_path) as f:
                    self._policy = yaml.safe_load(f)
            else:
                logger.warning(
                    f"Notification policy not found at {self._policy_path}, using defaults"
                )
                self._policy = {
                    "immediate_alerts": {
                        "send_for_severity": ["high", "critical"],
                        "always_send_for": [
                            "approval_request",
                            "core_identity_conflict",
                            "proposed_soul_item_change",
                            "proposed_prd_objective_change",
                            "governance_conflict",
                            "safety_conflict",
                        ],
                    }
                }
        except Exception as e:
            logger.warning(f"Failed to load notification policy: {e}")
            self._policy = {
                "immediate_alerts": {
                    "send_for_severity": ["high", "critical"],
                    "always_send_for": [
                        "approval_request",
                        "core_identity_conflict",
                        "proposed_soul_item_change",
                        "proposed_prd_objective_change",
                        "governance_conflict",
                        "safety_conflict",
                    ],
                }
            }

        return self._policy

    def _is_enabled(self) -> bool:
        """Check if notification routing is enabled via feature flag."""
        redis = _get_redis_client()
        if redis is None:
            return True
        try:
            flag = redis["get"](REDIS_FLAG_KEY, "notification_routing_enabled")
            if flag is None:
                return True
            return flag.lower() in ("true", "1", "yes", "on")
        except Exception as e:
            logger.warning(f"Failed to read feature flag: {e}")
            return True

    def get_immediate_alert_severities(self) -> list[str]:
        """Get list of severities that trigger immediate alerts."""
        policy = self._load_policy()
        return policy.get("immediate_alerts", {}).get(
            "send_for_severity", ["high", "critical"]
        )

    def get_always_send_for_types(self) -> list[str]:
        """Get list of event types that always trigger immediate alerts."""
        policy = self._load_policy()
        return policy.get("immediate_alerts", {}).get("always_send_for", [])

    def route_event(self, event: dict[str, Any]) -> RoutingDecision:
        """Determine routing for an event.

        Args:
            event: Event dict with keys:
                - event_type: str (required)
                - severity: str (optional, defaults to low)
                - event_id: str (optional)
                - summary: str (optional)
                - etc.

        Returns:
            RoutingDecision with mode and reason.
        """
        if not self._is_enabled():
            return RoutingDecision(
                mode="digest",  # Disabled = silent (safe default)
                reason="notification routing disabled by feature flag",
                event_id=event.get("event_id"),
            )

        event_type = event.get("event_type", "unknown")
        # If explicit severity provided, use it; otherwise derive via SeverityMapper
        if "severity" in event:
            severity = event["severity"]
        elif self.severity_mapper is not None:
            severity = self.severity_mapper.get_severity(event_type)
        else:
            severity = "low"

        # Check always_send_for list first
        always_send_for = self.get_always_send_for_types()
        if event_type in always_send_for:
            return RoutingDecision(
                mode="immediate",
                reason=f"event_type '{event_type}' is in always_send_for list",
                event_id=event.get("event_id"),
            )

        # Check severity-based routing
        immediate_severities = self.get_immediate_alert_severities()
        if severity in immediate_severities:
            return RoutingDecision(
                mode="immediate",
                reason=f"severity '{severity}' triggers immediate alert",
                event_id=event.get("event_id"),
            )

        # Default to digest
        return RoutingDecision(
            mode="digest",
            reason=f"event_type '{event_type}' with severity '{severity}' routed to digest",
            event_id=event.get("event_id"),
        )

    async def handle_event(self, event: dict[str, Any]) -> bool:
        """Route and handle an event using the DiscordNotifier.

        Args:
            event: Event dict to route and handle.

        Returns:
            True if event was handled successfully.
        """
        decision = self.route_event(event)

        if decision.mode == "immediate":
            return await self._send_immediate(event)
        else:
            return self._add_to_digest(event)

    def _send_immediate(self, event: dict[str, Any]) -> bool:
        """Send event immediately via DiscordNotifier.notify_autocog_event.

        Note: This is a sync wrapper. The actual DiscordNotifier methods are async.
        For true async handling, use handle_event() instead.
        """
        try:
            import asyncio

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # No running event loop, create new one
                loop = asyncio.new_event_loop()
                close_loop = True
            else:
                close_loop = False
            try:
                return loop.run_until_complete(
                    self.notifier.notify_autocog_event(
                        event_type=event.get("event_type", "unknown"),
                        severity=event.get("severity", "low"),
                        summary=event.get("summary", ""),
                        impact=event.get("impact", ""),
                        top_metrics=event.get("top_metrics"),
                        artifact_path=event.get("artifact_path"),
                        run_id=event.get("run_id", event.get("event_id", "unknown")),
                        title=event.get("title"),
                        issue=event.get("issue"),
                        intended_resolution=event.get("intended_resolution"),
                        expected_improvement=event.get("expected_improvement"),
                        outcome_status=event.get("outcome_status"),
                        evidence_reasoning=event.get("evidence_reasoning"),
                        decision_packet=event.get("decision_packet"),
                    )
                )
            finally:
                if close_loop:
                    loop.close()
        except Exception as e:
            logger.error(f"Failed to send immediate notification: {e}")
            return False

    def _add_to_digest(self, event: dict[str, Any]) -> bool:
        """Add event to digest buffer."""
        try:
            return self.notifier.add_to_digest(event)
        except Exception as e:
            logger.error(f"Failed to add event to digest: {e}")
            return False


class DigestBuilder:
    """Skeleton for building digest notifications.

    This is the digest builder factory. The actual scheduler integration
    (8PM America/Toronto) will be implemented separately.

    Usage:
        builder = DigestBuilder(router.notifier)
        digest_content = builder.build_digest()
    """

    def __init__(self, notifier: DiscordNotifier | None = None):
        """Initialize DigestBuilder.

        Args:
            notifier: DiscordNotifier instance to build digest from.
        """
        self._notifier = notifier

    @property
    def notifier(self) -> DiscordNotifier:
        """Get DiscordNotifier instance, lazily initialized."""
        if self._notifier is None:
            self._notifier = DiscordNotifier()
        return self._notifier

    def build_digest(self) -> str | None:
        """Build digest content from buffered events.

        Returns:
            Formatted digest string, or None if no events buffered.
        """
        from .formatters import LowSeverityDigestFormatter

        if not self.notifier._low_severity_buffer:
            return None

        formatter = LowSeverityDigestFormatter()
        return formatter.format_digest(self.notifier._low_severity_buffer)

    def get_buffered_count(self) -> int:
        """Get number of events in digest buffer."""
        return len(self.notifier._low_severity_buffer)

    def should_flush(self) -> bool:
        """Check if digest should be flushed."""
        return self.notifier.should_flush_digest()

    def get_next_digest_time(self) -> datetime:
        """Get next digest time in America/Toronto timezone.

        Returns:
            datetime in America/Toronto timezone.
        """
        now = datetime.now(TORONTO_TZ)
        # Next 8PM
        from datetime import time as dt_time

        target_time = dt_time(hour=20, minute=0, second=0)

        next_digest = now.replace(
            hour=target_time.hour,
            minute=target_time.minute,
            second=target_time.second,
            microsecond=0,
        )

        # If we're past 8PM today, schedule for tomorrow
        if now.hour >= 20:
            from datetime import timedelta

            next_digest += timedelta(days=1)

        return next_digest

    async def send_digest(self) -> bool:
        """Flush and send digest via DiscordNotifier.

        Returns:
            True if digest was sent successfully.
        """
        return await self.notifier.send_digest()
