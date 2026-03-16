"""Policy engine for autonomous cognition decision validation.

This module provides the AutonomousPolicyEngine class which validates
all autonomous cognition decisions against configurable policies and
safety guardrails.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class PolicyResult:
    """Result of policy validation for a decision.

    Attributes:
        approved: Whether the decision is approved
        reason: Explanation for the decision outcome
        risk_level: The risk level assessed for this decision
        requires_approval: Whether human approval is required
        approval_timeout: Timeout in seconds for approval (if required)
        notify_immediately: Whether to notify immediately for critical decisions
        blocked_files: List of files that were blocked
    """

    approved: bool
    reason: str = ""
    risk_level: str = "unknown"
    requires_approval: bool = False
    approval_timeout: int | None = None
    notify_immediately: bool = False
    blocked_files: list[str] = field(default_factory=list)


@dataclass
class ApprovalRequirement:
    """Approval requirements for a decision.

    Attributes:
        required: Whether approval is required
        roles: List of roles that can approve
        timeout_seconds: Timeout for approval
        notify_immediately: Whether to notify immediately
    """

    required: bool
    roles: list[str] = field(default_factory=list)
    timeout_seconds: int = 3600
    notify_immediately: bool = False


class AutonomousPolicyEngine:
    """Validates autonomous cognition decisions against policies.

    This engine checks decisions against:
    - Risk level policies (low, medium, high, critical)
    - Protected file/path policies
    - Approval gate requirements
    - Concurrent operation limits

    Configuration is loaded from config/autocog_policies.yaml and
    integrates with config/autocog.yaml safety settings.
    """

    DEFAULT_CONFIG_PATH = Path("config/autocog_policies.yaml")
    AUTOCOG_CONFIG_PATH = Path("config/autocog.yaml")

    def __init__(self, config_path: Path | None = None):
        """Initialize the policy engine.

        Args:
            config_path: Path to policy configuration file.
                        Defaults to config/autocog_policies.yaml
        """
        self._config_path = config_path or self.DEFAULT_CONFIG_PATH
        self._config: dict[str, Any] = {}
        self._autocog_config: dict[str, Any] = {}
        self._risk_policies: dict[str, dict[str, Any]] = {}
        self._protected_paths: list[dict[str, str]] = []
        self._approval_gates: dict[str, list[dict[str, str]]] = {}
        self._concurrent_counts: dict[str, int] = {}

        self._load_configs()

    def _load_configs(self) -> None:
        """Load policy configuration from YAML files."""
        # Load autocog.yaml for safety settings
        if self.AUTOCOG_CONFIG_PATH.exists():
            try:
                with open(self.AUTOCOG_CONFIG_PATH, "r", encoding="utf-8") as f:
                    self._autocog_config = yaml.safe_load(f) or {}
                logger.info("Loaded autocog config from %s", self.AUTOCOG_CONFIG_PATH)
            except Exception as e:
                logger.warning("Failed to load autocog config: %s", e)
                self._autocog_config = {}
        else:
            logger.warning("autocog.yaml not found, using defaults")
            self._autocog_config = {}

        # Load autocog_policies.yaml
        if self._config_path.exists():
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    self._config = yaml.safe_load(f) or {}
                logger.info("Loaded policy config from %s", self._config_path)
            except Exception as e:
                logger.warning("Failed to load policy config: %s", e)
                self._config = self._default_config()
        else:
            logger.warning("Policy config not found, using defaults")
            self._config = self._default_config()

        # Parse policy sections
        policies = self._config.get("policies", {})
        self._risk_policies = policies.get("risk_levels", {})
        self._protected_paths = policies.get("protected_paths", [])
        self._approval_gates = policies.get("approval_gates", {})

    def _default_config(self) -> dict[str, Any]:
        """Return default policy configuration."""
        return {
            "policies": {
                "risk_levels": {
                    "low": {
                        "auto_approve": True,
                        "max_concurrent": 10,
                    },
                    "medium": {
                        "auto_approve": True,
                        "max_concurrent": 5,
                    },
                    "high": {
                        "auto_approve": False,
                        "requires_approval": True,
                        "approval_timeout": 3600,
                    },
                    "critical": {
                        "auto_approve": False,
                        "requires_approval": True,
                        "approval_timeout": 7200,
                        "notify_immediately": True,
                    },
                },
                "protected_paths": [
                    {"pattern": "src/core/risk_caps.py", "action": "block"},
                    {"pattern": "src/core/governance_bypasses.py", "action": "block"},
                    {
                        "pattern": "docs/bmm-workflow-status.yaml",
                        "action": "require_approval",
                    },
                ],
                "approval_gates": {
                    "high": [{"role": "senior-dev"}, {"role": "jarvis"}],
                    "critical": [{"role": "craig"}],
                },
            }
        }

    def validate_decision(self, decision: dict[str, Any]) -> PolicyResult:
        """Validate a decision against all policies.

        Args:
            decision: Dictionary containing decision details:
                - risk_level: str (low, medium, high, critical)
                - files: list[str] - files affected by decision
                - action: str - action being taken
                - description: str - human-readable description

        Returns:
            PolicyResult with approval status and requirements
        """
        risk_level = decision.get("risk_level", "unknown")
        files = decision.get("files", [])
        action = decision.get("action", "unknown")
        description = decision.get("description", "")

        logger.info(
            "Validating decision: action=%s risk_level=%s files=%d",
            action,
            risk_level,
            len(files),
        )

        # Check risk level
        risk_ok, risk_reason = self._check_risk_level_policy(risk_level)
        if not risk_ok:
            logger.warning("Risk level policy violation: %s", risk_reason)
            return PolicyResult(
                approved=False,
                reason=risk_reason,
                risk_level=risk_level,
                requires_approval=True,
            )

        # Check protected files
        blocked_files = self._check_protected_files(files)
        if blocked_files:
            block_reason = f"Blocked files: {', '.join(blocked_files)}"
            logger.warning("Protected file violation: %s", block_reason)
            return PolicyResult(
                approved=False,
                reason=block_reason,
                risk_level=risk_level,
                requires_approval=True,
                blocked_files=blocked_files,
            )

        # Check approval requirements
        approval_req = self.check_approval_requirements(decision)

        # Check concurrent limits
        concurrent_ok, concurrent_reason = self._check_concurrent_limit(risk_level)
        if not concurrent_ok:
            logger.warning("Concurrent limit violation: %s", concurrent_reason)
            return PolicyResult(
                approved=False,
                reason=concurrent_reason,
                risk_level=risk_level,
                requires_approval=True,
            )

        # Determine final approval status
        if approval_req.required:
            result = PolicyResult(
                approved=False,
                reason=f"Approval required from: {', '.join(approval_req.roles)}",
                risk_level=risk_level,
                requires_approval=True,
                approval_timeout=approval_req.timeout_seconds,
                notify_immediately=approval_req.notify_immediately,
            )
        else:
            result = PolicyResult(
                approved=True,
                reason=f"Auto-approved: {description}",
                risk_level=risk_level,
                requires_approval=False,
            )

        # Log the decision
        self._log_decision(decision, result)

        return result

    def _check_risk_level_policy(self, risk_level: str) -> tuple[bool, str]:
        """Check if risk level is valid and within policy.

        Args:
            risk_level: The risk level to check

        Returns:
            Tuple of (is_valid, reason)
        """
        valid_levels = ["low", "medium", "high", "critical"]

        if risk_level not in valid_levels:
            return False, f"Invalid risk level: {risk_level}"

        # Check against autocog safety settings
        max_risk = self._autocog_config.get("safety", {}).get(
            "max_risk_level", "medium"
        )

        risk_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}

        if risk_order.get(risk_level, 0) > risk_order.get(max_risk, 1):
            return False, f"Risk level {risk_level} exceeds max allowed {max_risk}"

        return True, ""

    def check_risk_level(self, risk_level: str) -> bool:
        """Check if a risk level is valid and within policy.

        Args:
            risk_level: The risk level to check (low, medium, high, critical)

        Returns:
            True if risk level is valid and within policy
        """
        is_valid, _ = self._check_risk_level_policy(risk_level)
        return is_valid

    def _check_protected_files(self, files: list[str]) -> list[str]:
        """Check if any files are protected and should be blocked.

        Args:
            files: List of file paths to check

        Returns:
            List of blocked file paths (includes both 'block' and 'require_approval' actions)
        """
        blocked: list[str] = []

        for file_path in files:
            for protected in self._protected_paths:
                pattern = protected.get("pattern", "")
                action = protected.get("action", "block")

                # Simple pattern matching (can be enhanced with glob/regex)
                if self._match_pattern(file_path, pattern):
                    if action in ("block", "require_approval"):
                        blocked.append(file_path)
                        logger.debug(
                            "Protected file %s matching pattern %s (action: %s)",
                            file_path,
                            pattern,
                            action,
                        )
                    break  # Stop checking other patterns for this file

        return blocked

    def check_protected_files(self, files: list[str]) -> bool:
        """Check if any files in the list are protected.

        Args:
            files: List of file paths to check

        Returns:
            True if any files are protected (blocked or require approval)
        """
        blocked = self._check_protected_files(files)
        return len(blocked) > 0

    def _match_pattern(self, file_path: str, pattern: str) -> bool:
        """Match a file path against a pattern.

        Supports:
        - Exact match
        - Wildcard * for any characters
        - Directory prefix matching

        Args:
            file_path: The file path to check
            pattern: The pattern to match against

        Returns:
            True if file_path matches pattern
        """
        import fnmatch

        # Normalize paths
        file_path = file_path.lstrip("/")
        pattern = pattern.lstrip("/")

        # Direct match
        if file_path == pattern:
            return True

        # Glob pattern match
        if fnmatch.fnmatch(file_path, pattern):
            return True

        # Directory prefix match
        if pattern.endswith("/") and file_path.startswith(pattern):
            return True

        return False

    def check_approval_requirements(
        self, decision: dict[str, Any]
    ) -> ApprovalRequirement:
        """Determine approval requirements for a decision.

        Args:
            decision: Dictionary containing decision details

        Returns:
            ApprovalRequirement with approval details
        """
        risk_level = decision.get("risk_level", "unknown")

        # Get risk policy
        risk_policy = self._risk_policies.get(risk_level, {})

        # Check if auto-approve is enabled
        auto_approve = risk_policy.get("auto_approve", False)

        if auto_approve:
            return ApprovalRequirement(required=False)

        # Get approval gate for this risk level
        approval_gate = self._approval_gates.get(risk_level, [])
        roles = [item.get("role", "") for item in approval_gate if item.get("role")]

        # Get timeout and notification settings
        timeout = risk_policy.get("approval_timeout", 3600)
        notify = risk_policy.get("notify_immediately", False)

        return ApprovalRequirement(
            required=True,
            roles=roles,
            timeout_seconds=timeout,
            notify_immediately=notify,
        )

    def _check_concurrent_limit(self, risk_level: str) -> tuple[bool, str]:
        """Check if concurrent operation limit is exceeded.

        Args:
            risk_level: The risk level of the operation

        Returns:
            Tuple of (within_limit, reason)
        """
        risk_policy = self._risk_policies.get(risk_level, {})
        max_concurrent = risk_policy.get("max_concurrent")

        if max_concurrent is None:
            # No limit specified
            return True, ""

        current = self._concurrent_counts.get(risk_level, 0)

        if current >= max_concurrent:
            return (
                False,
                f"Concurrent limit exceeded: {current}/{max_concurrent} for {risk_level}",
            )

        return True, ""

    def increment_concurrent(self, risk_level: str) -> bool:
        """Increment concurrent operation count for a risk level.

        Args:
            risk_level: The risk level to increment

        Returns:
            True if increment was successful (within limit)
        """
        within_limit, _ = self._check_concurrent_limit(risk_level)

        if within_limit:
            self._concurrent_counts[risk_level] = (
                self._concurrent_counts.get(risk_level, 0) + 1
            )
            logger.debug(
                "Incremented concurrent count for %s: %d",
                risk_level,
                self._concurrent_counts[risk_level],
            )
            return True

        return False

    def decrement_concurrent(self, risk_level: str) -> None:
        """Decrement concurrent operation count for a risk level.

        Args:
            risk_level: The risk level to decrement
        """
        current = self._concurrent_counts.get(risk_level, 0)
        if current > 0:
            self._concurrent_counts[risk_level] = current - 1
            logger.debug(
                "Decremented concurrent count for %s: %d",
                risk_level,
                self._concurrent_counts[risk_level],
            )

    def _log_decision(self, decision: dict[str, Any], result: PolicyResult) -> None:
        """Log a policy decision.

        Args:
            decision: The decision that was validated
            result: The policy result
        """
        log_entry = {
            "action": decision.get("action"),
            "risk_level": result.risk_level,
            "approved": result.approved,
            "requires_approval": result.requires_approval,
            "reason": result.reason,
            "files": decision.get("files", []),
        }

        if result.approved:
            logger.info("Policy decision: approved - %s", log_entry)
        else:
            if result.requires_approval:
                logger.warning("Policy decision: approval required - %s", log_entry)
            else:
                logger.error("Policy decision: blocked - %s", log_entry)

    def get_policy_summary(self) -> dict[str, Any]:
        """Get a summary of current policies.

        Returns:
            Dictionary with policy summary
        """
        return {
            "risk_levels": list(self._risk_policies.keys()),
            "protected_paths_count": len(self._protected_paths),
            "protected_paths": [p.get("pattern") for p in self._protected_paths],
            "approval_gates": {
                level: [item.get("role") for item in gates]
                for level, gates in self._approval_gates.items()
            },
            "max_risk_level": self._autocog_config.get("safety", {}).get(
                "max_risk_level", "medium"
            ),
            "concurrent_counts": self._concurrent_counts.copy(),
        }

    def reload_config(self) -> None:
        """Reload configuration from files."""
        logger.info("Reloading policy configuration")
        self._load_configs()

    # Legacy method for backward compatibility
    def evaluate_promotion_gates(self, metrics: dict[str, float]) -> "GateDecision":
        """Evaluate core gates for candidate promotion (legacy method).

        Args:
            metrics: Dictionary with metrics including sharpe, ece, drawdown, constitution_violations

        Returns:
            GateDecision with pass/fail status
        """
        failures: list[str] = []
        if metrics.get("sharpe", 0.0) < 1.1:
            failures.append("statistical_improvement_gate")
        if metrics.get("ece", 1.0) > 0.15:
            failures.append("calibration_gate")
        if metrics.get("drawdown", 1.0) > 0.20:
            failures.append("risk_regression_gate")
        if metrics.get("constitution_violations", 0.0) > 0:
            failures.append("constitution_gate")
        return GateDecision(passed=not failures, failed_gates=failures)


@dataclass
class GateDecision:
    """Result of gate evaluation (legacy compatibility)."""

    passed: bool
    failed_gates: list[str] = field(default_factory=list)
