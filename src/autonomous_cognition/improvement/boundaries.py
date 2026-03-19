"""Boundary enforcement for autonomous improvement cycles.

This module provides the BoundaryEnforcer class which enforces safety boundaries
including file access, scope limits, risk levels, and emergency stop.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class RiskLevel(str, Enum):
    """Risk levels for improvement proposals."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class BoundaryConfig:
    """Configuration for boundary enforcement.

    Attributes:
        allowed_paths: File paths that may be modified
        blocked_paths: File paths that must never be modified
        max_files_per_cycle: Maximum number of files in a single improvement
        max_lines_per_file: Maximum lines changed per file
        max_risk_level: Maximum allowed risk level
        emergency_stop: Whether emergency stop is active
    """

    allowed_paths: list[str] = field(
        default_factory=lambda: ["src/autonomous_cognition/"]
    )
    blocked_paths: list[str] = field(
        default_factory=lambda: [
            ".woodpecker.yml",
            "docs/bmm-workflow-status.yaml",
            "infrastructure/terraform/",
            "AGENTS.md",
            "pyproject.toml",
        ]
    )
    max_files_per_cycle: int = 10
    max_lines_per_file: int = 500
    max_risk_level: RiskLevel = RiskLevel.MEDIUM
    emergency_stop: bool = False


@dataclass
class BoundaryViolation:
    """Records a boundary violation.

    Attributes:
        violation_type: Type of boundary violated
        description: Human-readable description
        severity: Severity level (low/medium/high/critical)
        file_path: File that triggered the violation (if applicable)
        blocked: Whether this violation blocks the proposal
    """

    violation_type: str
    description: str
    severity: str
    file_path: str = ""
    blocked: bool = True


class BoundaryEnforcer:
    """Enforces safety boundaries for autonomous improvement cycles.

    This enforcer checks:
    - File access (allowed/blocked paths)
    - Scope limits (max files, max lines)
    - Risk level limits
    - Emergency stop status

    Example:
        >>> config = BoundaryConfig(max_risk_level=RiskLevel.HIGH)
        >>> enforcer = BoundaryEnforcer(config)
        >>> violations = enforcer.check_proposal(proposal)
        >>> if not violations:
        ...     # Safe to proceed
        ...     pass
    """

    def __init__(self, config: BoundaryConfig | None = None) -> None:
        """Initialize with optional config (uses defaults if not provided)."""
        self._config = config or BoundaryConfig()
        self._violations: list[BoundaryViolation] = []
        self._emergency_stop_active: bool = self._config.emergency_stop

    @property
    def config(self) -> BoundaryConfig:
        """Current boundary configuration."""
        return self._config

    @property
    def emergency_stop_active(self) -> bool:
        """Whether emergency stop is currently active."""
        return self._emergency_stop_active

    def check_proposal(self, proposal: dict[str, Any]) -> list[BoundaryViolation]:
        """Check a proposal against all boundaries.

        Args:
            proposal: Dict with keys:
                - files: list[str] of files to modify
                - risk_level: str risk level
                - changes: dict mapping file -> line_count

        Returns:
            List of BoundaryViolation objects (empty = safe)
        """
        violations: list[BoundaryViolation] = []

        # Check emergency stop first
        if self._emergency_stop_active:
            violations.append(
                BoundaryViolation(
                    violation_type="emergency_stop",
                    description="Emergency stop is active — all proposals blocked",
                    severity="critical",
                    blocked=True,
                )
            )
            return violations

        # Block everything immediately
        files = proposal.get("files", [])
        risk_level = proposal.get("risk_level", "low")
        changes = proposal.get("changes", {})

        # Check file access
        violations.extend(self._check_file_access(files))

        # Check scope limits
        violations.extend(self._check_scope(files, changes))

        # Check risk level
        violations.extend(self._check_risk_level(risk_level))

        self._violations.extend(violations)
        return violations

    def _check_file_access(self, files: list[str]) -> list[BoundaryViolation]:
        """Check if files are within allowed paths and not blocked."""
        violations: list[BoundaryViolation] = []

        for file_path in files:
            # Check blocked paths first
            blocked_match = False
            for blocked in self._config.blocked_paths:
                if file_path.startswith(blocked) or file_path == blocked:
                    violations.append(
                        BoundaryViolation(
                            violation_type="blocked_path",
                            description=f"File '{file_path}' matches blocked path '{blocked}'",
                            severity="critical",
                            file_path=file_path,
                            blocked=True,
                        )
                    )
                    blocked_match = True
                    break

            if not blocked_match:
                # Check allowed paths
                allowed = any(
                    file_path.startswith(p) for p in self._config.allowed_paths
                )
                if not allowed:
                    violations.append(
                        BoundaryViolation(
                            violation_type="outside_scope",
                            description=f"File '{file_path}' is outside allowed paths",
                            severity="high",
                            file_path=file_path,
                            blocked=True,
                        )
                    )

        return violations

    def _check_scope(
        self, files: list[str], changes: dict[str, int]
    ) -> list[BoundaryViolation]:
        """Check scope limits (max files, max lines)."""
        violations: list[BoundaryViolation] = []

        if len(files) > self._config.max_files_per_cycle:
            violations.append(
                BoundaryViolation(
                    violation_type="scope_exceeded",
                    description=f"Too many files: {len(files)} > {self._config.max_files_per_cycle}",
                    severity="high",
                    blocked=True,
                )
            )

        for file_path, line_count in changes.items():
            if line_count > self._config.max_lines_per_file:
                violations.append(
                    BoundaryViolation(
                        violation_type="lines_exceeded",
                        description=f"File '{file_path}' has {line_count} lines > {self._config.max_lines_per_file}",
                        severity="medium",
                        file_path=file_path,
                        blocked=True,
                    )
                )

        return violations

    def _check_risk_level(self, risk_level: str) -> list[BoundaryViolation]:
        """Check if risk level is within allowed bounds."""
        violations: list[BoundaryViolation] = []

        risk_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        proposal_risk = risk_order.get(risk_level, 3)
        max_risk = risk_order.get(self._config.max_risk_level.value, 1)

        if proposal_risk > max_risk:
            violations.append(
                BoundaryViolation(
                    violation_type="risk_exceeded",
                    description=f"Risk level '{risk_level}' exceeds max '{self._config.max_risk_level.value}'",
                    severity="critical",
                    blocked=True,
                )
            )

        return violations

    def activate_emergency_stop(self, reason: str = "") -> None:
        """Activate emergency stop — blocks all proposals immediately."""
        self._emergency_stop_active = True
        logger.warning("Emergency stop activated: %s", reason)

    def deactivate_emergency_stop(self) -> None:
        """Deactivate emergency stop."""
        self._emergency_stop_active = False
        logger.info("Emergency stop deactivated")

    def get_violations(self) -> list[BoundaryViolation]:
        """Get all recorded violations."""
        return list(self._violations)

    def clear_violations(self) -> None:
        """Clear violation history."""
        self._violations.clear()

    def is_safe(self, proposal: dict[str, Any]) -> bool:
        """Quick check if a proposal is safe (no violations)."""
        return len(self.check_proposal(proposal)) == 0
