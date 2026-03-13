"""Violation detection for constitution compliance.

Detects when agent behavior violates constitution rules and sends alerts.

For ST-GOV-002: Agent Constitution Artifact
"""

from __future__ import annotations

import json
import logging
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ViolationSeverity(str, Enum):
    """Severity level of a violation."""

    P0 = "P0"  # Critical
    P1 = "P1"  # High
    P2 = "P2"  # Medium
    P3 = "P3"  # Low


@dataclass
class Violation:
    """Represents a detected constitution violation."""

    id: str
    rule_id: str
    severity: ViolationSeverity
    description: str
    pattern_matched: str
    context: dict[str, Any]
    detected_at: datetime = field(default_factory=datetime.utcnow)
    resolved: bool = False
    resolved_at: datetime | None = None
    resolved_by: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert violation to dictionary."""
        return {
            "id": self.id,
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "description": self.description,
            "pattern_matched": self.pattern_matched,
            "context": self.context,
            "detected_at": self.detected_at.isoformat(),
            "resolved": self.resolved,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolved_by": self.resolved_by,
        }

    def resolve(self, resolved_by: str) -> None:
        """Mark the violation as resolved."""
        self.resolved = True
        self.resolved_at = datetime.utcnow()
        self.resolved_by = resolved_by


class AlertChannel:
    """Base class for alert channels."""

    def send(self, violation: Violation) -> bool:
        """Send an alert for a violation.

        Args:
            violation: The violation to alert about

        Returns:
            True if alert was sent successfully
        """
        raise NotImplementedError


class DiscordAlertChannel(AlertChannel):
    """Sends violation alerts to Discord."""

    def __init__(self, webhook_url: str | None = None, channel_id: str = "#alerts"):
        """Initialize Discord alert channel.

        Args:
            webhook_url: Discord webhook URL (optional, uses MCP if not provided)
            channel_id: Discord channel ID or name
        """
        self.webhook_url = webhook_url
        self.channel_id = channel_id
        self._mcp_available = False

    def _format_message(self, violation: Violation) -> str:
        """Format violation as Discord message."""
        severity_emoji = {
            ViolationSeverity.P0: "🚨",
            ViolationSeverity.P1: "⚠️",
            ViolationSeverity.P2: "⚡",
            ViolationSeverity.P3: "📋",
        }

        emoji = severity_emoji.get(violation.severity, "⚠️")

        return (
            f"{emoji} **Constitution Violation Detected**\n"
            f"**Severity:** {violation.severity.value}\n"
            f"**Rule:** {violation.rule_id}\n"
            f"**Description:** {violation.description}\n"
            f"**Pattern:** {violation.pattern_matched}\n"
            f"**Time:** {violation.detected_at.isoformat()}\n"
            f"**Context:** ```json\n{json.dumps(violation.context, indent=2)}```"
        )

    def send(self, violation: Violation) -> bool:
        """Send alert to Discord.

        Args:
            violation: The violation to alert about

        Returns:
            True if alert was sent successfully
        """
        message = self._format_message(violation)

        # Try webhook first
        if self.webhook_url:
            try:
                payload = json.dumps({"content": message}).encode("utf-8")
                request = Request(
                    self.webhook_url,
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(request, timeout=10) as response:
                    if 200 <= response.status < 300:
                        logger.info(
                            "Discord violation alert sent: channel=%s status=%s",
                            self.channel_id,
                            response.status,
                        )
                        return True
                    logger.error(
                        "Discord webhook failed: status=%s channel=%s",
                        response.status,
                        self.channel_id,
                    )
                    return False
            except (HTTPError, URLError, TimeoutError, ValueError) as e:
                logger.error(f"Failed to send Discord webhook: {e}")
                return False
            except Exception as e:
                logger.error(f"Unexpected Discord webhook failure: {e}")
                return False

        # Fall back to logging (MCP integration would be added here)
        logger.warning(f"Discord alert (channel={self.channel_id}): {message[:200]}...")
        return True


class ViolationDetector:
    """Detects constitution violations in agent behavior."""

    def __init__(
        self,
        alert_channels: list[AlertChannel] | None = None,
        detection_accuracy_target: float = 0.99,
    ):
        """Initialize the violation detector.

        Args:
            alert_channels: List of alert channels to notify
            detection_accuracy_target: Target detection accuracy (default 99%)
        """
        self.alert_channels = alert_channels or []
        self.detection_accuracy_target = detection_accuracy_target
        self._violation_rules: dict[str, dict[str, Any]] = {}
        self._violations: list[Violation] = []
        self._detection_stats = {
            "total_checked": 0,
            "violations_detected": 0,
            "true_positives": 0,
            "false_positives": 0,
        }

    def register_rule(
        self,
        rule_id: str,
        pattern: str,
        severity: ViolationSeverity,
        description: str,
        auto_detect: bool = True,
    ) -> None:
        """Register a violation detection rule.

        Args:
            rule_id: Unique rule identifier (e.g., VR-001)
            pattern: Regex pattern to match
            severity: Severity level
            description: Human-readable description
            auto_detect: Whether to auto-detect this violation
        """
        self._violation_rules[rule_id] = {
            "pattern": re.compile(pattern, re.IGNORECASE),
            "severity": severity,
            "description": description,
            "auto_detect": auto_detect,
        }
        logger.debug(f"Registered violation rule: {rule_id}")

    def register_default_rules(self) -> None:
        """Register default violation detection rules."""
        default_rules = [
            (
                "VR-001",
                r"(accessed|modified|touched).*(outside|beyond).*(scope|globs)",
                ViolationSeverity.P1,
                "Unauthorized Scope Access",
            ),
            (
                "VR-002",
                r"(direct|straight).*(commit|push).*(to|on).*(main|master)",
                ViolationSeverity.P1,
                "Branch Safety Violation",
            ),
            (
                "VR-003",
                r"(state|data).*(change|modify|update).*(without|missing).*(audit|log)",
                ViolationSeverity.P2,
                "Missing Audit Trail",
            ),
            (
                "VR-004",
                r"(rate|limit).*(exceeded|surpassed|violated)",
                ViolationSeverity.P2,
                "Rate Limit Exceeded",
            ),
            (
                "VR-005",
                r"(feature|capability).*(used|accessed).*(without|missing).*(flag|check)",
                ViolationSeverity.P1,
                "Feature Flag Bypass",
            ),
        ]

        for rule_id, pattern, severity, description in default_rules:
            self.register_rule(rule_id, pattern, severity, description)

    def detect(
        self,
        action: str,
        context: dict[str, Any] | None = None,
    ) -> list[Violation]:
        """Detect violations in an action.

        Args:
            action: The action text to check
            context: Additional context for the action

        Returns:
            List of detected violations
        """
        self._detection_stats["total_checked"] += 1
        violations: list[Violation] = []
        context = context or {}

        for rule_id, rule in self._violation_rules.items():
            if not rule["auto_detect"]:
                continue

            match = rule["pattern"].search(action)
            if match:
                violation = Violation(
                    id=f"viol-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{rule_id}",
                    rule_id=rule_id,
                    severity=rule["severity"],
                    description=rule["description"],
                    pattern_matched=match.group(0),
                    context=context,
                )
                violations.append(violation)
                self._violations.append(violation)
                self._detection_stats["violations_detected"] += 1

                # Send alerts
                for channel in self.alert_channels:
                    try:
                        channel.send(violation)
                    except Exception as e:
                        logger.error(f"Failed to send alert: {e}")

        return violations

    def check_scope_violation(
        self,
        accessed_path: str,
        allowed_globs: list[str],
        context: dict[str, Any] | None = None,
    ) -> Violation | None:
        """Check if a path access violates scope boundaries.

        Args:
            accessed_path: Path that was accessed
            allowed_globs: List of allowed glob patterns
            context: Additional context

        Returns:
            Violation if detected, None otherwise
        """
        import fnmatch

        is_allowed = any(fnmatch.fnmatch(accessed_path, glob) for glob in allowed_globs)

        if not is_allowed:
            violation = Violation(
                id=f"viol-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-scope",
                rule_id="VR-001",
                severity=ViolationSeverity.P1,
                description="Unauthorized Scope Access",
                pattern_matched=accessed_path,
                context={
                    "accessed_path": accessed_path,
                    "allowed_globs": allowed_globs,
                    **(context or {}),
                },
            )
            self._violations.append(violation)
            self._detection_stats["violations_detected"] += 1

            for channel in self.alert_channels:
                channel.send(violation)

            return violation

        return None

    def check_branch_safety(
        self,
        branch: str,
        action: str,
        context: dict[str, Any] | None = None,
    ) -> Violation | None:
        """Check for branch safety violations.

        Args:
            branch: Current branch name
            action: Action being performed
            context: Additional context

        Returns:
            Violation if detected, None otherwise
        """
        protected_branches = {"main", "master"}

        if branch in protected_branches and "commit" in action.lower():
            violation = Violation(
                id=f"viol-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-branch",
                rule_id="VR-002",
                severity=ViolationSeverity.P1,
                description="Branch Safety Violation",
                pattern_matched=f"Direct commit to {branch}",
                context={
                    "branch": branch,
                    "action": action,
                    **(context or {}),
                },
            )
            self._violations.append(violation)
            self._detection_stats["violations_detected"] += 1

            for channel in self.alert_channels:
                channel.send(violation)

            return violation

        return None

    def get_accuracy(self) -> float:
        """Calculate current detection accuracy.

        Returns:
            Detection accuracy as a float between 0 and 1
        """
        if self._detection_stats["total_checked"] == 0:
            return 1.0

        total = (
            self._detection_stats["true_positives"]
            + self._detection_stats["false_positives"]
        )
        if total == 0:
            return 1.0

        return self._detection_stats["true_positives"] / total

    def record_validation_result(
        self,
        violation_id: str,
        is_true_positive: bool,
    ) -> None:
        """Record whether a detected violation was a true positive.

        Args:
            violation_id: ID of the violation
            is_true_positive: Whether it was a true positive
        """
        self._detection_stats["total_checked"] += 1
        if is_true_positive:
            self._detection_stats["true_positives"] += 1
        else:
            self._detection_stats["false_positives"] += 1

    def get_stats(self) -> dict[str, Any]:
        """Get detection statistics.

        Returns:
            Dictionary with detection statistics
        """
        return {
            **self._detection_stats,
            "accuracy": self.get_accuracy(),
            "accuracy_target": self.detection_accuracy_target,
            "meets_target": self.get_accuracy() >= self.detection_accuracy_target,
            "total_rules": len(self._violation_rules),
            "recent_violations": len([v for v in self._violations if not v.resolved]),
        }

    def get_violations(
        self,
        severity: ViolationSeverity | None = None,
        resolved: bool | None = None,
        limit: int = 100,
    ) -> list[Violation]:
        """Get violations with optional filters.

        Args:
            severity: Filter by severity
            resolved: Filter by resolved status
            limit: Maximum number to return

        Returns:
            List of matching violations
        """
        violations = self._violations

        if severity is not None:
            violations = [v for v in violations if v.severity == severity]

        if resolved is not None:
            violations = [v for v in violations if v.resolved == resolved]

        return violations[-limit:]

    def clear_violations(self) -> None:
        """Clear all stored violations."""
        self._violations.clear()
