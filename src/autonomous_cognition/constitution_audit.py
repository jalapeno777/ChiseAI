"""Automated constitution audit and violation escalation.

This module provides the ConstitutionAuditEngine class which runs automated
constitution compliance checks against the ChiseAI Agent Constitution v1.0.0.

References:
    - Constitution v1.0.0: Violation Categories (Section 6)
    - Safety Invariants (Section 4)
    - Escalation Criteria (Section 5)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ViolationSeverity(str, Enum):
    """Severity levels per constitution Section 6.1."""

    P0 = "P0"  # Critical - immediate threat
    P1 = "P1"  # High - significant impact
    P2 = "P2"  # Medium - degraded performance
    P3 = "P3"  # Low - minor issues


class ViolationEnforcement(str, Enum):
    """Enforcement actions per constitution Section 4."""

    BLOCK = "BLOCK"  # Immediately block action
    ALERT = "ALERT"  # Log and alert
    COORDINATE = "COORDINATE"  # Coordinate with other agents
    VALIDATE = "VALIDATE"  # Run validation


@dataclass
class ConstitutionViolation:
    """Represents a detected constitution violation.

    Attributes:
        rule_id: Unique identifier (e.g., 'VR-001', 'INV-001')
        name: Human-readable violation name
        severity: P0/P1/P2/P3 severity level
        enforcement: BLOCK/ALERT/COORDINATE/VALIDATE
        description: Detailed description of the violation
        evidence: Evidence capturing the violation context
        auto_detect: Whether this was auto-detected
        detection_sla_seconds: SLA for detection in seconds
    """

    rule_id: str
    name: str
    severity: ViolationSeverity
    enforcement: ViolationEnforcement
    description: str
    evidence: dict[str, Any] = field(default_factory=dict)
    auto_detect: bool = True
    detection_sla_seconds: int = 300


@dataclass
class AuditMetrics:
    """Metrics from an audit run.

    Attributes:
        total_actions: Total number of actions audited
        violations_found: Number of violations detected
        critical_count: Number of P0 violations
        high_count: Number of P1 violations
        medium_count: Number of P2 violations
        low_count: Number of P3 violations
        constitution_compliant: Whether any violations were found
        audit_duration_ms: Time taken for audit in milliseconds
    """

    total_actions: int
    violations_found: int
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    constitution_compliant: bool = True
    audit_duration_ms: float = 0.0

    @property
    def severity_breakdown(self) -> dict[str, int]:
        """Get breakdown by severity."""
        return {
            "P0": self.critical_count,
            "P1": self.high_count,
            "P2": self.medium_count,
            "P3": self.low_count,
        }


@dataclass
class ConstitutionAuditResult:
    """Result of constitution audit pass.

    Attributes:
        violations: List of detected violations
        metrics: Audit metrics summary
        recommendations: List of recommended actions
        requires_escalation: Whether escalation is required
        escalation_severity: Severity level requiring escalation (if any)
    """

    violations: list[ConstitutionViolation]
    metrics: AuditMetrics
    recommendations: list[str] = field(default_factory=list)
    requires_escalation: bool = False
    escalation_severity: str = ""

    @property
    def critical_count(self) -> int:
        return self.metrics.critical_count

    @property
    def is_compliant(self) -> bool:
        return self.metrics.constitution_compliant


# Constitution violation rules from Section 6.2
CONSTITUTION_VIOLATION_RULES: list[dict[str, Any]] = [
    {
        "id": "VR-001",
        "name": "Unauthorized Scope Access",
        "pattern": r"Agent accessed path outside SCOPE_GLOBS",
        "severity": ViolationSeverity.P1,
        "enforcement": ViolationEnforcement.BLOCK,
        "auto_detect": True,
    },
    {
        "id": "VR-002",
        "name": "Branch Safety Violation",
        "pattern": r"Direct commit to protected branch",
        "severity": ViolationSeverity.P1,
        "enforcement": ViolationEnforcement.BLOCK,
        "auto_detect": True,
    },
    {
        "id": "VR-003",
        "name": "Missing Audit Trail",
        "pattern": r"State change without audit log entry",
        "severity": ViolationSeverity.P2,
        "enforcement": ViolationEnforcement.ALERT,
        "auto_detect": True,
    },
    {
        "id": "VR-004",
        "name": "Rate Limit Exceeded",
        "pattern": r"API call rate exceeded threshold",
        "severity": ViolationSeverity.P2,
        "enforcement": ViolationEnforcement.BLOCK,
        "auto_detect": True,
    },
    {
        "id": "VR-005",
        "name": "Feature Flag Bypass",
        "pattern": r"Feature used without flag check",
        "severity": ViolationSeverity.P1,
        "enforcement": ViolationEnforcement.BLOCK,
        "auto_detect": True,
    },
]

# Hard invariants from Section 4.1
CONSTITUTION_INVARIANTS: list[dict[str, Any]] = [
    {
        "id": "INV-001",
        "name": "No Direct Main Branch Commits",
        "description": "Agents must never commit directly to main branch",
        "enforcement": ViolationEnforcement.BLOCK,
        "exception": "Emergency override with Captain Craig approval",
        "severity": ViolationSeverity.P0,
    },
    {
        "id": "INV-002",
        "name": "No Unvalidated Trading Execution",
        "description": "Trading strategies must pass backtest and paper trading gates",
        "enforcement": ViolationEnforcement.BLOCK,
        "exception": None,
        "severity": ViolationSeverity.P0,
    },
    {
        "id": "INV-003",
        "name": "Protected Container Integrity",
        "description": "Cannot modify tradedev, intelligent_ride, or MCP containers",
        "enforcement": ViolationEnforcement.BLOCK,
        "exception": "Captain Craig explicit approval",
        "severity": ViolationSeverity.P0,
    },
    {
        "id": "INV-004",
        "name": "Data Retention Compliance",
        "description": "Audit logs must be retained for minimum 90 days",
        "enforcement": ViolationEnforcement.ALERT,
        "exception": None,
        "severity": ViolationSeverity.P1,
    },
    {
        "id": "INV-005",
        "name": "Rate Limit Respect",
        "description": "Must honor external API rate limits and circuit breakers",
        "enforcement": ViolationEnforcement.BLOCK,
        "exception": None,
        "severity": ViolationSeverity.P1,
    },
]


class ConstitutionAuditEngine:
    """Runs automated constitution compliance checks.

    The engine validates actions against:
    - Hard invariants (Section 4.1)
    - Violation detection rules (Section 6.2)
    - Escalation criteria (Section 5)

    Example:
        >>> engine = ConstitutionAuditEngine()
        >>> result = engine.run(
        ...     actions=[{"type": "git_commit", "branch": "main"}],
        ...     context={"agent_id": "test-agent"},
        ... )
        >>> if not result.is_compliant:
        ...     print(f"Violations: {result.critical_count}")
    """

    def __init__(
        self,
        violation_rules: list[dict[str, Any]] | None = None,
        invariants: list[dict[str, Any]] | None = None,
        constitution_path: Path | None = None,
    ):
        """Initialize the audit engine.

        Args:
            violation_rules: Custom violation rules (uses constitution defaults)
            invariants: Custom invariants (uses constitution defaults)
            constitution_path: Path to constitution document (for reference)
        """
        self._violation_rules = violation_rules or CONSTITUTION_VIOLATION_RULES
        self._invariants = invariants or CONSTITUTION_INVARIANTS
        self._constitution_path = constitution_path
        self._compiled_patterns: list[tuple[str, re.Pattern]] = []
        self._compile_patterns()
        self._audit_history: list[ConstitutionAuditResult] = []

    def _compile_patterns(self) -> None:
        """Pre-compile regex patterns for efficiency."""
        self._compiled_patterns = []
        for rule in self._violation_rules:
            pattern = rule.get("pattern", "")
            if pattern:
                try:
                    compiled = re.compile(pattern)
                    self._compiled_patterns.append((rule["id"], compiled))
                except re.error as e:
                    logger.warning("Invalid pattern %s: %s", rule["id"], e)

    def run(
        self,
        actions: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
    ) -> ConstitutionAuditResult:
        """Run audit over action log stream.

        Args:
            actions: List of action dictionaries, each containing:
                - type: Action type (e.g., 'git_commit', 'api_call')
                - details: Action-specific details
                - timestamp: Optional ISO timestamp
            context: Optional context dictionary with:
                - agent_id: Agent identifier
                - session_id: Session identifier
                - scope_globs: Allowed paths

        Returns:
            ConstitutionAuditResult with violations and metrics
        """
        import time

        start_time = time.time()
        context = context or {}
        violations: list[ConstitutionViolation] = []

        # Check each action against violation rules
        for action in actions:
            action_violations = self._check_action(action, context)
            violations.extend(action_violations)

        # Check invariants
        invariant_violations = self._check_invariants(actions, context)
        violations.extend(invariant_violations)

        # Check scope compliance
        scope_violations = self._check_scope_compliance(actions, context)
        violations.extend(scope_violations)

        # Calculate metrics
        metrics = self._calculate_metrics(actions, violations, start_time)

        # Determine escalation needs
        requires_escalation, escalation_severity = self._determine_escalation(
            violations, metrics
        )

        # Generate recommendations
        recommendations = self._generate_recommendations(violations, metrics)

        result = ConstitutionAuditResult(
            violations=violations,
            metrics=metrics,
            recommendations=recommendations,
            requires_escalation=requires_escalation,
            escalation_severity=escalation_severity,
        )

        self._audit_history.append(result)
        logger.info(
            "Audit complete: %d violations (%d critical) in %d actions",
            len(violations),
            metrics.critical_count,
            len(actions),
        )

        return result

    def _check_action(
        self,
        action: dict[str, Any],
        context: dict[str, Any],
    ) -> list[ConstitutionViolation]:
        """Check a single action against violation rules."""
        violations: list[ConstitutionViolation] = []
        action_str = str(action)

        for rule_id, pattern in self._compiled_patterns:
            rule = next((r for r in self._violation_rules if r["id"] == rule_id), None)
            if not rule:
                continue

            if pattern.search(action_str):
                violation = ConstitutionViolation(
                    rule_id=rule["id"],
                    name=rule["name"],
                    severity=ViolationSeverity(rule["severity"].value),
                    enforcement=ViolationEnforcement(rule["enforcement"].value),
                    description=f"Action matched violation pattern: {rule['name']}",
                    evidence={
                        "action": action,
                        "matched_pattern": rule["pattern"],
                    },
                    auto_detect=rule.get("auto_detect", True),
                    detection_sla_seconds=self._get_detection_sla(rule["severity"]),
                )
                violations.append(violation)
                logger.warning(
                    "Violation detected: %s (rule %s)",
                    violation.name,
                    violation.rule_id,
                )

        return violations

    def _check_invariants(
        self,
        actions: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> list[ConstitutionViolation]:
        """Check actions against hard invariants."""
        violations: list[ConstitutionViolation] = []

        for invariant in self._invariants:
            # Check if invariant applies
            if not self._invariant_applies(invariant, actions, context):
                continue

            violation = ConstitutionViolation(
                rule_id=invariant["id"],
                name=invariant["name"],
                severity=ViolationSeverity(invariant["severity"].value),
                enforcement=ViolationEnforcement(invariant["enforcement"].value),
                description=invariant["description"],
                evidence={"context": context},
                auto_detect=True,
                detection_sla_seconds=self._get_detection_sla(invariant["severity"]),
            )
            violations.append(violation)
            logger.error(
                "Invariant violated: %s (%s)",
                violation.name,
                violation.rule_id,
            )

        return violations

    def _invariant_applies(
        self,
        invariant: dict[str, Any],
        actions: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> bool:
        """Check if an invariant applies to the current context."""
        inv_id = invariant["id"]

        # INV-001: No direct main branch commits
        if inv_id == "INV-001":
            for action in actions:
                if isinstance(action, dict) and action.get("type") == "git_commit":
                    branch = action.get("details", {}).get("branch", "")
                    if branch == "main":
                        # Check for emergency override in context
                        override = context.get("override", {})
                        return override.get("approved_by") != "captain_craig"

        # INV-002: No unvalidated trading execution
        if inv_id == "INV-002":
            for action in actions:
                if isinstance(action, dict) and action.get("type") == "trading_execute":
                    backtest_passed = action.get("details", {}).get(
                        "backtest_passed", False
                    )
                    paper_passed = action.get("details", {}).get("paper_passed", False)
                    if not (backtest_passed and paper_passed):
                        return True

        # INV-003: Protected container integrity
        if inv_id == "INV-003":
            protected = [
                "tradedev",
                "intelligent_ride",
                "aisetup-mcp-discord-1",
                "duckduckgo-mcp-server",
            ]
            for action in actions:
                if (
                    isinstance(action, dict)
                    and action.get("type") == "container_modify"
                ):
                    container = action.get("details", {}).get("container", "")
                    if container in protected:
                        override = context.get("override", {})
                        return override.get("approved_by") != "captain_craig"

        # INV-005: Rate limit respect
        if inv_id == "INV-005":
            for action in actions:
                if isinstance(action, dict) and action.get("type") == "api_call":
                    rate_exceeded = action.get("details", {}).get(
                        "rate_limit_exceeded", False
                    )
                    if rate_exceeded:
                        return True

        return False

    def _check_scope_compliance(
        self,
        actions: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> list[ConstitutionViolation]:
        """Check if actions stay within scope globs."""
        violations: list[ConstitutionViolation] = []
        scope_globs = context.get("scope_globs", [])

        if not scope_globs:
            return violations

        for action in actions:
            files = action.get("details", {}).get("files", [])
            for file_path in files:
                if not self._is_within_scope(file_path, scope_globs):
                    violation = ConstitutionViolation(
                        rule_id="VR-001",
                        name="Unauthorized Scope Access",
                        severity=ViolationSeverity.P1,
                        enforcement=ViolationEnforcement.BLOCK,
                        description=f"File '{file_path}' outside SCOPE_GLOBS",
                        evidence={
                            "file": file_path,
                            "scope_globs": scope_globs,
                            "action": action,
                        },
                        auto_detect=True,
                        detection_sla_seconds=300,
                    )
                    violations.append(violation)

        return violations

    def _is_within_scope(self, file_path: str, scope_globs: list[str]) -> bool:
        """Check if file is within any of the scope globs."""
        import fnmatch

        for glob_pattern in scope_globs:
            # Normalize glob for matching
            pattern = glob_pattern.rstrip("/")
            if not pattern:
                continue

            # Direct prefix match
            if file_path.startswith(pattern):
                return True

            # Glob match
            if fnmatch.fnmatch(file_path, pattern):
                return True

            # Directory recursive match
            if pattern.endswith("/**"):
                dir_path = pattern[:-3]
                if file_path.startswith(dir_path):
                    return True

        return False

    def _calculate_metrics(
        self,
        actions: list[dict[str, Any]],
        violations: list[ConstitutionViolation],
        start_time: float,
    ) -> AuditMetrics:
        """Calculate audit metrics."""
        import time

        metrics = AuditMetrics(
            total_actions=len(actions),
            violations_found=len(violations),
            audit_duration_ms=(time.time() - start_time) * 1000,
        )

        for v in violations:
            if v.severity == ViolationSeverity.P0:
                metrics.critical_count += 1
            elif v.severity == ViolationSeverity.P1:
                metrics.high_count += 1
            elif v.severity == ViolationSeverity.P2:
                metrics.medium_count += 1
            elif v.severity == ViolationSeverity.P3:
                metrics.low_count += 1

        metrics.constitution_compliant = len(violations) == 0

        return metrics

    def _determine_escalation(
        self,
        violations: list[ConstitutionViolation],
        metrics: AuditMetrics,
    ) -> tuple[bool, str]:
        """Determine if escalation is required per Section 5."""
        # P0: Any critical violation
        if metrics.critical_count > 0:
            return True, "P0"

        # P1: Invariant violations or unauthorized access
        if metrics.high_count > 0:
            return True, "P1"

        # P2: Multiple medium violations
        if metrics.medium_count >= 3:
            return True, "P2"

        return False, ""

    def _generate_recommendations(
        self,
        violations: list[ConstitutionViolation],
        metrics: AuditMetrics,
    ) -> list[str]:
        """Generate actionable recommendations from violations."""
        recommendations: list[str] = []

        if not violations:
            recommendations.append("Continue monitoring - no violations detected")
            return recommendations

        # Group by severity
        by_severity: dict[str, list[ConstitutionViolation]] = {}
        for v in violations:
            by_severity.setdefault(v.severity.value, []).append(v)

        # P0 recommendations
        if "P0" in by_severity:
            recommendations.append(
                "CRITICAL: Immediate intervention required for P0 violations"
            )
            recommendations.append("Escalate to #security-alerts and Captain Craig")

        # P1 recommendations
        if "P1" in by_severity:
            recommendations.append(
                "HIGH: Review violation patterns and implement corrective actions"
            )
            recommendations.append("Audit agent scope boundaries and approval gates")

        # P2 recommendations
        if "P2" in by_severity:
            recommendations.append(
                "MEDIUM: Monitor violation trends and address root causes"
            )
            recommendations.append("Review rate limiting and logging configurations")

        # Specific recommendations based on violation types
        violation_ids = {v.rule_id for v in violations}
        if "INV-001" in violation_ids:
            recommendations.append(
                "BLOCK: Implement pre-commit hooks to prevent direct main commits"
            )
        if "INV-002" in violation_ids:
            recommendations.append(
                "BLOCK: Require backtest/paper validation before trading execution"
            )
        if "INV-003" in violation_ids:
            recommendations.append(
                "BLOCK: Add protected container checks to action guards"
            )
        if "VR-001" in violation_ids:
            recommendations.append(
                "Review SCOPE_GLOBS configuration and agent scope enforcement"
            )

        return recommendations

    def _get_detection_sla(self, severity: ViolationSeverity) -> int:
        """Get detection SLA in seconds per constitution Section 6.1."""
        slas = {
            ViolationSeverity.P0: 60,
            ViolationSeverity.P1: 300,
            ViolationSeverity.P2: 900,
            ViolationSeverity.P3: 3600,
        }
        return slas.get(severity, 300)

    def get_audit_history(self) -> list[ConstitutionAuditResult]:
        """Get history of audit results."""
        return list(self._audit_history)

    def clear_history(self) -> None:
        """Clear audit history."""
        self._audit_history.clear()

    def validate_constitution_doc(self) -> tuple[bool, list[str]]:
        """Validate constitution document structure.

        Returns:
            Tuple of (is_valid, list of error messages)
        """
        errors: list[str] = []

        if not self._violation_rules:
            errors.append("No violation rules defined")

        if not self._invariants:
            errors.append("No invariants defined")

        # Check rule structure
        for rule in self._violation_rules:
            if "id" not in rule:
                errors.append("Violation rule missing 'id' field")
            if "pattern" in rule:
                try:
                    re.compile(rule["pattern"])
                except re.error as e:
                    errors.append(
                        f"Invalid regex pattern in rule {rule.get('id')}: {e}"
                    )

        # Check invariant structure
        for inv in self._invariants:
            if "id" not in inv:
                errors.append("Invariant missing 'id' field")
            if "enforcement" not in inv:
                errors.append(f"Invariant {inv.get('id')} missing 'enforcement' field")

        return len(errors) == 0, errors

    def get_violation_summary(self) -> dict[str, Any]:
        """Get summary of violation rules and their status.

        Returns:
            Dictionary with violation rule summary
        """
        return {
            "violation_rules_count": len(self._violation_rules),
            "invariants_count": len(self._invariants),
            "audit_history_count": len(self._audit_history),
            "violation_rules": [
                {"id": r["id"], "name": r["name"], "severity": r["severity"].value}
                for r in self._violation_rules
            ],
            "invariants": [
                {
                    "id": i["id"],
                    "name": i["name"],
                    "severity": i["severity"].value,
                    "enforcement": i["enforcement"].value,
                }
                for i in self._invariants
            ],
        }
