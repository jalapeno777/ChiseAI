"""Belief Mutation Audit Writer for autonomous cognition audit trail."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from src.config.feature_flags import get_feature_flags

if TYPE_CHECKING:
    import redis

logger = logging.getLogger(__name__)

# Redis key constants
GOVERNANCE_PREFIX = "chise:feature_flags:governance"
AUDIT_KEY = "bmad:chiseai:autocog:audit:belief_mutations"
FEATURE_FLAG_KEY = f"{GOVERNANCE_PREFIX}:belief_mutation_audit_enabled"

# TTL for Redis entries (30 days in seconds)
AUDIT_TTL_SECONDS = 30 * 24 * 60 * 60


@dataclass
class BeliefMutationEvent:
    """BeliefMutationEvent matching schemas/aria/belief-mutation-event.schema.json.

    Attributes:
        event_id: Unique identifier for the event
        timestamp: ISO format timestamp
        actor: Entity that initiated the mutation
        belief_key: Key/path of the belief being mutated
        mutation_type: Type of mutation (create, update, deprecate, promote, merge, conflict_resolution)
        severity: Severity level (low, medium, high, critical)
        old_value: Previous value before mutation
        new_value: New value after mutation
        evidence: List of evidence records supporting the mutation
        conflict_resolution: Details if this was a conflict resolution
        approval_required: Whether approval was required
        approval_reason: Reason for approval requirement
        applied: Whether the mutation was applied
        notified: Whether notification was sent
        notification_mode: Notification mode (immediate, digest, None)
        notes: Optional notes
    """

    event_id: str
    timestamp: str
    actor: str
    belief_key: str
    mutation_type: str
    severity: str
    old_value: Any
    new_value: Any
    evidence: list[dict] = field(default_factory=list)
    conflict_resolution: dict | None = None
    approval_required: bool = False
    approval_reason: str | None = None
    applied: bool = False
    notified: bool = False
    notification_mode: str | None = None
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert event to dictionary for serialization."""
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "actor": self.actor,
            "belief_key": self.belief_key,
            "mutation_type": self.mutation_type,
            "severity": self.severity,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "evidence": self.evidence,
            "conflict_resolution": self.conflict_resolution,
            "approval_required": self.approval_required,
            "approval_reason": self.approval_reason,
            "applied": self.applied,
            "notified": self.notified,
            "notification_mode": self.notification_mode,
            "notes": self.notes,
        }


class BeliefMutationAuditWriter:
    """Canonical writer for belief mutation audit events.

    Writes belief mutation events to Redis using LPUSH for append-only semantics.
    Respects feature flag gating and governance policy for approval requirements.

    Usage:
        writer = BeliefMutationAuditWriter()
        event = BeliefMutationEvent(
            event_id="evt-001",
            timestamp=datetime.now(UTC).isoformat(),
            actor="agent-1",
            belief_key="soul_items.core.value.honesty",
            mutation_type="create",
            severity="high",
            old_value=None,
            new_value={"statement": "Honesty is the best policy"},
        )
        writer.write_mutation_event(event)
    """

    def __init__(
        self,
        redis_client: redis.Redis | None = None,
        governance_policy_path: str | None = None,
    ) -> None:
        """Initialize the BeliefMutationAuditWriter.

        Args:
            redis_client: Optional Redis client instance. If not provided,
                will attempt to connect using environment variables.
            governance_policy_path: Optional path to governance policy YAML file.
                Defaults to config/aria/governance-policy.yaml in repo root.
        """
        self._redis_client = redis_client
        self._governance_policy_path = governance_policy_path
        self._governance_policy: dict[str, Any] | None = None

    @property
    def redis_client(self) -> redis.Redis | None:
        """Get Redis client, lazily initialized if needed."""
        if self._redis_client is None:
            self._redis_client = self._get_redis_client()
        return self._redis_client

    @staticmethod
    def _get_redis_client() -> redis.Redis | None:
        """Get Redis client from environment or return None.

        Returns:
            Redis client instance or None if connection fails.
        """
        try:
            import redis

            redis_host = os.getenv("REDIS_HOST", "host.docker.internal")
            redis_port = int(os.getenv("REDIS_PORT", "6380"))
            redis_db = int(os.getenv("REDIS_DB", "0"))
            redis_password = os.getenv("REDIS_PASSWORD", None)

            return redis.Redis(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                password=redis_password,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
        except Exception as e:
            logger.debug(f"Could not connect to Redis: {e}")
            return None

    def is_enabled(self) -> bool:
        """Check if belief mutation audit is enabled via feature flag.

        Returns:
            True if feature flag is enabled, False otherwise.
        """
        try:
            flags = get_feature_flags()
            # Use the existing FeatureFlags pattern - defaults to True for safety
            return flags.get_redis_value(FEATURE_FLAG_KEY, default=True)
        except Exception as e:
            logger.warning(f"Error checking feature flag {FEATURE_FLAG_KEY}: {e}")
            return True  # Default to enabled for safety

    def write_mutation_event(self, event: BeliefMutationEvent) -> bool:
        """Write a belief mutation event to the audit log.

        Uses LPUSH to append events to the Redis list with TTL.

        Args:
            event: The BeliefMutationEvent to write.

        Returns:
            True if event was written successfully, False otherwise.
        """
        # Check if audit is enabled
        if not self.is_enabled():
            logger.debug("Belief mutation audit is disabled, skipping write")
            return False

        client = self.redis_client
        if client is None:
            logger.warning("Redis unavailable, cannot write belief mutation event")
            return False

        try:
            # Serialize event to JSON
            event_data = event.to_dict()
            event_json = json.dumps(event_data)

            # Use LPUSH for append-only semantics (newest first)
            # Set TTL separately (not perfectly atomic but sufficient for audit log)
            client.lpush(AUDIT_KEY, event_json)
            client.expire(AUDIT_KEY, AUDIT_TTL_SECONDS)

            logger.info(
                f"Wrote belief mutation event {event.event_id} for {event.belief_key}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to write belief mutation event: {e}")
            return False

    def _load_governance_policy(self) -> dict[str, Any]:
        """Load governance policy from YAML file.

        Returns:
            Governance policy dictionary.

        Raises:
            FileNotFoundError: If governance policy file doesn't exist.
            yaml.YAMLError: If YAML parsing fails.
        """
        if self._governance_policy is not None:
            return self._governance_policy

        if self._governance_policy_path is None:
            # Use CHISEAI_REPO_ROOT env var if set, else walk up from file location
            env_root = os.environ.get("CHISEAI_REPO_ROOT")
            if env_root:
                repo_root = Path(env_root).resolve()
                if repo_root.exists():
                    self._governance_policy_path = str(
                        repo_root / "config" / "aria" / "governance-policy.yaml"
                    )
            else:
                # Walk up from audit_writer.py:
                # beliefs -> autonomous_cognition -> src -> <repo_root>
                current = Path(__file__).resolve()
                for _ in range(6):
                    current = current.parent
                    if (current / "pyproject.toml").exists():
                        self._governance_policy_path = str(
                            current / "config" / "aria" / "governance-policy.yaml"
                        )
                        break
                else:
                    # Fallback: use original relative path calculation
                    repo_root = Path(__file__).parent.parent.parent.parent
                    self._governance_policy_path = str(
                        repo_root / "config" / "aria" / "governance-policy.yaml"
                    )

        with open(self._governance_policy_path) as f:
            self._governance_policy = yaml.safe_load(f)

        return self._governance_policy

    def _determine_approval_required(self, belief_category: str) -> bool:
        """Determine if a belief category requires approval based on governance policy.

        Args:
            belief_category: The category of the belief (e.g., 'soul_items',
                'core_values', 'user_preference_updates').

        Returns:
            True if the category requires approval, False otherwise.
        """
        try:
            policy = self._load_governance_policy()
            approval_required_categories = policy.get("belief_mutation", {}).get(
                "approval_required", []
            )
            return belief_category in approval_required_categories
        except Exception as e:
            logger.warning(f"Failed to load governance policy for approval check: {e}")
            # Fail safe: require approval if we can't determine
            return True

    def _derive_notification_mode(self, severity: str, approval_required: bool) -> str:
        """Derive the notification mode based on severity and approval requirement.

        Args:
            severity: Event severity (low, medium, high, critical).
            approval_required: Whether approval was required for this mutation.

        Returns:
            Notification mode: 'immediate' or 'digest'.
        """
        # critical/high severity always gets immediate notification
        if severity in ("critical", "high"):
            return "immediate"

        # medium/low severity depends on approval requirement
        # If approval was required, use digest; otherwise also digest
        # per the requirement: medium/low + approval_required => digest
        # medium/low + approval_required=false => digest
        return "digest"
