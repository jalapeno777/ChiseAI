"""Severity mapper for notification routing using notification-policy.yaml."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Redis key for feature flag
REDIS_FLAG_KEY = "chise:feature_flags:governance:notification_routing_enabled"

# Default severity for unknown event types (safe default - routes to digest)
DEFAULT_SEVERITY = "low"

# Valid severity levels
VALID_SEVERITIES = {"low", "medium", "high", "critical"}


def _get_redis_client():
    """Get Redis client with graceful fallback."""
    try:
        from tools.redis_state import redis_state_hget

        return {"get": redis_state_hget}
    except ImportError:
        return None


class SeverityMapper:
    """Maps event types to severity levels using notification-policy.yaml.

    Usage:
        mapper = SeverityMapper()
        severity = mapper.get_severity("approval_request")  # Returns "critical"
        severity = mapper.get_severity("unknown_event")     # Returns "low"
    """

    def __init__(self, policy_path: str | None = None):
        """Initialize SeverityMapper.

        Args:
            policy_path: Optional path to notification-policy.yaml.
                Defaults to config/aria/notification-policy.yaml in repo root.
        """
        self._policy_path = policy_path
        self._policy: dict[str, Any] | None = None
        self._severity_map: dict[str, str] | None = None

    def _load_policy(self) -> dict[str, Any]:
        """Load notification policy from YAML file."""
        if self._policy is not None:
            return self._policy

        if self._policy_path is None:
            repo_root = Path(__file__).parent.parent.parent.parent
            self._policy_path = str(
                repo_root / "config" / "aria" / "notification-policy.yaml"
            )

        try:
            with open(self._policy_path) as f:
                self._policy = yaml.safe_load(f)
        except Exception as e:
            logger.warning(f"Failed to load notification policy: {e}")
            self._policy = {"severity_model": {}}

        return self._policy

    def _build_severity_map(self) -> dict[str, str]:
        """Build inverted lookup from event_type -> severity."""
        policy = self._load_policy()
        severity_model = policy.get("severity_model", {})

        result: dict[str, str] = {}
        for severity, event_types in severity_model.items():
            if severity not in VALID_SEVERITIES:
                continue
            for event_type in event_types:
                result[event_type] = severity

        return result

    def _is_enabled(self) -> bool:
        """Check if notification routing is enabled via feature flag."""
        redis = _get_redis_client()
        if redis is None:
            return True  # Default enabled
        try:
            flag = redis["get"](REDIS_FLAG_KEY, "notification_routing_enabled")
            if flag is None:
                return True
            return flag.lower() in ("true", "1", "yes", "on")
        except Exception as e:
            logger.warning(f"Failed to read feature flag: {e}")
            return True

    def get_severity(self, event_type: str) -> str:
        """Map an event type to its severity level.

        Args:
            event_type: The type of event (e.g., "approval_request", "minor_preference_refinement")

        Returns:
            Severity level: "low", "medium", "high", or "critical".
            Returns "low" for unknown event types (safe default).
        """
        if not self._is_enabled():
            return DEFAULT_SEVERITY

        if self._severity_map is None:
            self._severity_map = self._build_severity_map()

        return self._severity_map.get(event_type, DEFAULT_SEVERITY)

    def get_severity_for_belief_mutation(
        self, mutation_type: str, severity: str
    ) -> str:
        """Get severity for a belief mutation event.

        This is a convenience method that handles the special case where
        BeliefMutationEvent already has a severity field.

        Args:
            mutation_type: The mutation type (create, update, deprecate, etc.)
            severity: The severity from BeliefMutationEvent

        Returns:
            The severity (returns the provided severity if valid).
        """
        if severity in VALID_SEVERITIES:
            return severity
        return DEFAULT_SEVERITY
