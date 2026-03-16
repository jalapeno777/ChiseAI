"""Action guards for autonomous cognition auto-action enforcement.

This module provides the ActionGuards class which enforces safety constraints
and automatically blocks or approves actions based on policy rules.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from autonomous_cognition.policy_engine import (
    ApprovalRequirement,
    AutonomousPolicyEngine,
    PolicyResult,
)

logger = logging.getLogger(__name__)


@dataclass
class ActionResult:
    """Result of action guard validation.

    Attributes:
        allowed: Whether the action is allowed to proceed
        reason: Explanation for the decision
        risk_level: The risk level assessed for this action
        requires_approval: Whether human approval is required
        blocked: Whether the action was blocked (vs just requiring approval)
        audit_log_id: ID of the audit log entry for this action
    """

    allowed: bool
    reason: str = ""
    risk_level: str = "unknown"
    requires_approval: bool = False
    blocked: bool = False
    audit_log_id: str = ""


@dataclass
class BlockedAction:
    """Record of a blocked action for audit trail.

    Attributes:
        action_id: Unique identifier for this blocked action
        timestamp: When the action was blocked
        decision: The decision that was blocked
        reason: Why the action was blocked
        risk_level: The risk level of the blocked action
        files: List of files affected (if any)
    """

    action_id: str
    timestamp: str
    decision: dict[str, Any]
    reason: str
    risk_level: str
    files: list[str] = field(default_factory=list)


class ActionGuards:
    """Enforces safety constraints and auto-action guardrails.

    This class provides automatic enforcement of:
    - Risk level limits (blocks actions exceeding max_risk_level)
    - Protected file restrictions (blocks modifications to protected files)
    - Full validation pipeline using PolicyEngine
    - Comprehensive audit trail for all actions

    The ActionGuards integrate with the PolicyEngine to provide
    a fail-closed safety layer that blocks actions by default
    when validation cannot be completed.
    """

    REDIS_BLOCKED_ACTIONS_KEY = "bmad:chiseai:autocog:blocked_actions"
    REDIS_AUDIT_LOG_KEY = "bmad:chiseai:autocog:action_audit_log"

    def __init__(
        self,
        policy_engine: AutonomousPolicyEngine | None = None,
        max_risk_level: str = "medium",
        redis_client: Any | None = None,
    ):
        """Initialize the action guards.

        Args:
            policy_engine: PolicyEngine instance for validation.
                          If None, creates a new instance.
            max_risk_level: Maximum allowed risk level (low, medium, high, critical)
            redis_client: Redis client for audit logging.
                         If None, uses in-memory storage.
        """
        self._policy_engine = policy_engine or AutonomousPolicyEngine()
        self._max_risk_level = max_risk_level
        self._redis = redis_client
        self._blocked_actions: list[BlockedAction] = []
        self._audit_log: list[dict[str, Any]] = []
        self._action_counter: int = 0

        # Risk level ordering for comparison
        self._risk_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}

        logger.info("ActionGuards initialized with max_risk_level=%s", max_risk_level)

    def enforce_risk_limit(self, decision: dict[str, Any]) -> bool:
        """Enforce maximum risk level limit.

        Blocks actions where the risk level exceeds the configured maximum.

        Args:
            decision: Dictionary containing decision details:
                - risk_level: str (low, medium, high, critical)
                - action: str - action being taken
                - description: str - human-readable description

        Returns:
            True if risk level is within limits, False if blocked
        """
        risk_level = decision.get("risk_level", "unknown")
        action = decision.get("action", "unknown")

        logger.debug(
            "Enforcing risk limit: action=%s risk_level=%s max=%s",
            action,
            risk_level,
            self._max_risk_level,
        )

        # Check if risk level is valid
        if risk_level not in self._risk_order:
            logger.warning(
                "Invalid risk level '%s' for action '%s', blocking",
                risk_level,
                action,
            )
            self.log_blocked_action(
                decision,
                f"Invalid risk level: {risk_level}",
            )
            return False

        # Check against max risk level
        decision_risk = self._risk_order.get(risk_level, 0)
        max_risk = self._risk_order.get(self._max_risk_level, 1)

        if decision_risk > max_risk:
            reason = (
                f"Risk level {risk_level} exceeds maximum allowed "
                f"{self._max_risk_level}"
            )
            logger.warning("Risk limit exceeded: %s (action: %s)", reason, action)
            self.log_blocked_action(decision, reason)
            return False

        logger.debug(
            "Risk level %s within limits (max: %s)",
            risk_level,
            self._max_risk_level,
        )
        return True

    def check_protected_files(self, files: list[str]) -> bool:
        """Check if any files are protected and should block the action.

        Args:
            files: List of file paths to check

        Returns:
            True if no protected files are found, False if any are blocked
        """
        if not files:
            return True

        logger.debug("Checking %d files for protected status", len(files))

        # Use policy engine to check protected files
        has_protected = self._policy_engine.check_protected_files(files)

        if has_protected:
            # Get the specific blocked files
            blocked = self._policy_engine._check_protected_files(files)
            logger.warning(
                "Protected files detected: %s",
                ", ".join(blocked),
            )
            return False

        logger.debug("No protected files found")
        return True

    def validate_auto_action(self, decision: dict[str, Any]) -> ActionResult:
        """Perform full validation of an auto-action.

        This is the main entry point for action validation. It performs:
        1. Risk limit enforcement
        2. Protected file checking
        3. Policy engine validation
        4. Audit logging

        Args:
            decision: Dictionary containing decision details:
                - risk_level: str (low, medium, high, critical)
                - files: list[str] - files affected by decision
                - action: str - action being taken
                - description: str - human-readable description
                - evidence: dict - supporting evidence

        Returns:
            ActionResult with validation outcome
        """
        action = decision.get("action", "unknown")
        self._action_counter += 1
        audit_log_id = f"action-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{self._action_counter}"

        logger.info(
            "Validating auto-action: id=%s action=%s",
            audit_log_id,
            action,
        )

        try:
            # Step 1: Check risk limits
            if not self.enforce_risk_limit(decision):
                result = ActionResult(
                    allowed=False,
                    reason=f"Risk limit exceeded (max: {self._max_risk_level})",
                    risk_level=decision.get("risk_level", "unknown"),
                    requires_approval=False,
                    blocked=True,
                    audit_log_id=audit_log_id,
                )
                self._log_audit_entry(audit_log_id, decision, result)
                return result

            # Step 2: Check protected files
            files = decision.get("files", [])
            if not self.check_protected_files(files):
                blocked_files = self._policy_engine._check_protected_files(files)
                result = ActionResult(
                    allowed=False,
                    reason=f"Protected files: {', '.join(blocked_files)}",
                    risk_level=decision.get("risk_level", "unknown"),
                    requires_approval=False,
                    blocked=True,
                    audit_log_id=audit_log_id,
                )
                self._log_audit_entry(audit_log_id, decision, result)
                return result

            # Step 3: Full policy validation
            policy_result = self._policy_engine.validate_decision(decision)

            # Step 4: Determine final result
            if policy_result.approved:
                result = ActionResult(
                    allowed=True,
                    reason=policy_result.reason,
                    risk_level=policy_result.risk_level,
                    requires_approval=False,
                    blocked=False,
                    audit_log_id=audit_log_id,
                )
            elif policy_result.requires_approval:
                result = ActionResult(
                    allowed=False,
                    reason=policy_result.reason,
                    risk_level=policy_result.risk_level,
                    requires_approval=True,
                    blocked=False,
                    audit_log_id=audit_log_id,
                )
            else:
                result = ActionResult(
                    allowed=False,
                    reason=policy_result.reason,
                    risk_level=policy_result.risk_level,
                    requires_approval=False,
                    blocked=True,
                    audit_log_id=audit_log_id,
                )

            self._log_audit_entry(audit_log_id, decision, result)
            return result

        except Exception as e:
            # Fail closed: block action on any error
            logger.exception("Validation error for action %s: %s", action, e)
            result = ActionResult(
                allowed=False,
                reason=f"Validation error: {str(e)}",
                risk_level=decision.get("risk_level", "unknown"),
                requires_approval=False,
                blocked=True,
                audit_log_id=audit_log_id,
            )
            self._log_audit_entry(audit_log_id, decision, result)
            return result

    def log_blocked_action(self, decision: dict[str, Any], reason: str) -> str:
        """Log a blocked action to the audit trail.

        Args:
            decision: The decision that was blocked
            reason: Why the action was blocked

        Returns:
            ID of the blocked action record
        """
        action_id = f"blocked-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{len(self._blocked_actions)}"

        blocked_action = BlockedAction(
            action_id=action_id,
            timestamp=datetime.now(UTC).isoformat(),
            decision=decision.copy(),
            reason=reason,
            risk_level=decision.get("risk_level", "unknown"),
            files=decision.get("files", []),
        )

        self._blocked_actions.append(blocked_action)

        # Persist to Redis if available
        if self._redis:
            try:
                self._redis.lpush(
                    self.REDIS_BLOCKED_ACTIONS_KEY,
                    json.dumps(
                        {
                            "action_id": action_id,
                            "timestamp": blocked_action.timestamp,
                            "action": decision.get("action"),
                            "reason": reason,
                            "risk_level": blocked_action.risk_level,
                        }
                    ),
                )
            except Exception as e:
                logger.warning("Failed to log blocked action to Redis: %s", e)

        logger.info(
            "Blocked action logged: id=%s action=%s reason=%s",
            action_id,
            decision.get("action"),
            reason,
        )

        return action_id

    def get_blocked_actions_summary(self) -> dict[str, Any]:
        """Get summary statistics of blocked actions.

        Returns:
            Dictionary with blocked action statistics
        """
        total_blocked = len(self._blocked_actions)

        # Count by risk level
        by_risk_level: dict[str, int] = {}
        for action in self._blocked_actions:
            risk = action.risk_level
            by_risk_level[risk] = by_risk_level.get(risk, 0) + 1

        # Count by reason category
        by_reason: dict[str, int] = {}
        for action in self._blocked_actions:
            reason = action.reason
            if "risk" in reason.lower():
                category = "risk_limit"
            elif "protected" in reason.lower() or "file" in reason.lower():
                category = "protected_file"
            elif "error" in reason.lower():
                category = "validation_error"
            else:
                category = "other"
            by_reason[category] = by_reason.get(category, 0) + 1

        # Get recent blocked actions (last 10)
        recent = [
            {
                "action_id": a.action_id,
                "timestamp": a.timestamp,
                "action": a.decision.get("action"),
                "reason": a.reason,
                "risk_level": a.risk_level,
            }
            for a in self._blocked_actions[-10:]
        ]

        return {
            "total_blocked": total_blocked,
            "by_risk_level": by_risk_level,
            "by_reason_category": by_reason,
            "recent_blocked": recent,
        }

    def _log_audit_entry(
        self,
        audit_log_id: str,
        decision: dict[str, Any],
        result: ActionResult,
    ) -> None:
        """Log an entry to the audit trail.

        Args:
            audit_log_id: Unique ID for this audit entry
            decision: The decision that was validated
            result: The validation result
        """
        entry = {
            "audit_log_id": audit_log_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "action": decision.get("action"),
            "risk_level": result.risk_level,
            "allowed": result.allowed,
            "blocked": result.blocked,
            "requires_approval": result.requires_approval,
            "reason": result.reason,
            "files": decision.get("files", []),
        }

        self._audit_log.append(entry)

        # Persist to Redis if available
        if self._redis:
            try:
                self._redis.lpush(
                    self.REDIS_AUDIT_LOG_KEY,
                    json.dumps(entry),
                )
            except Exception as e:
                logger.warning("Failed to log audit entry to Redis: %s", e)

        # Log at appropriate level
        if result.blocked:
            logger.warning(
                "Action blocked: id=%s action=%s reason=%s",
                audit_log_id,
                decision.get("action"),
                result.reason,
            )
        elif result.requires_approval:
            logger.info(
                "Action requires approval: id=%s action=%s",
                audit_log_id,
                decision.get("action"),
            )
        else:
            logger.info(
                "Action allowed: id=%s action=%s",
                audit_log_id,
                decision.get("action"),
            )

    def get_audit_trail(
        self,
        limit: int = 100,
        action_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get the audit trail with optional filtering.

        Args:
            limit: Maximum number of entries to return
            action_type: Filter by action type (optional)

        Returns:
            List of audit log entries
        """
        entries = self._audit_log

        if action_type:
            entries = [e for e in entries if e.get("action") == action_type]

        # Return most recent first
        return entries[-limit:][::-1]

    def clear_audit_trail(self) -> None:
        """Clear the in-memory audit trail."""
        self._audit_log.clear()
        self._blocked_actions.clear()
        logger.info("Audit trail cleared")

    def get_policy_engine(self) -> AutonomousPolicyEngine:
        """Get the underlying policy engine.

        Returns:
            The AutonomousPolicyEngine instance
        """
        return self._policy_engine

    def reload_policies(self) -> None:
        """Reload policy configuration from files."""
        self._policy_engine.reload_config()
        logger.info("Policy configuration reloaded")
