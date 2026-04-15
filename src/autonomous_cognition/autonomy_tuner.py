"""Configurable autonomy boundaries for autonomous cognition.

This module provides the AutonomyTuner class which manages configurable
autonomy level boundaries based on calibration metrics, incident trends,
and constitution compliance.

References:
    - Constitution v1.0.0: Decision Boundaries (Section 3)
    - Escalation Criteria (Section 5)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class AutonomyLevel(str, Enum):
    """Autonomy levels from most restricted to most autonomous.

    Ordered from supervised (human approval for all actions) to
    autonomous (agent operates with broad discretion within constraints).
    """

    SUPERVISED = "supervised"  # Human approval required for all actions
    BOUNDED = "bounded"  # Agent can act within strict constraints
    ASSISTED = "assisted"  # Agent proposes, human approves significant decisions
    AUTONOMOUS = "autonomous"  # Agent acts within constitution bounds


# Default escalation thresholds from constitution
DEFAULT_ECE_UPPER = 0.15  # ECE > 15% triggers regression guardrail
DEFAULT_ECE_LOWER = 0.08  # ECE < 8% sustained enables progression
DEFAULT_INCIDENT_THRESHOLD = (
    1  # >1 incident triggers regression (allows single transient incident)
)
DEFAULT_HEALTH_SCORE_THRESHOLD = 50  # Health score < 50 triggers escalation


@dataclass
class AutonomyTuningDecision:
    """Decision record for autonomy level tuning.

    Attributes:
        previous_level: The autonomy level before tuning
        new_level: The autonomy level after tuning
        reason: Human-readable reason for the decision
        ece: Expected Calibration Error at time of decision
        incident_count: Number of incidents at time of decision
        constitution_compliant: Whether agent was constitution-compliant
    """

    previous_level: str
    new_level: str
    reason: str
    ece: float = 0.0
    incident_count: int = 0
    constitution_compliant: bool = True


@dataclass
class AutonomyBoundary:
    """Defines boundaries for a specific autonomy level.

    Attributes:
        level: The autonomy level this boundary applies to
        max_risk_level: Maximum risk level permitted (low/medium/high/critical)
        requires_approval_for_blocked: Whether blocked path access requires approval
        max_files_per_action: Maximum files agent may modify in single action
        max_lines_per_file: Maximum lines changed per file
        allowed_paths: List of path prefixes agent may modify
        blocked_paths: List of path prefixes agent may never modify
        escalation_threshold: Incident count that triggers escalation
    """

    level: AutonomyLevel
    max_risk_level: str = "medium"
    requires_approval_for_blocked: bool = True
    max_files_per_action: int = 10
    max_lines_per_file: int = 500
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
    escalation_threshold: int = 0


# Default boundaries for each autonomy level
DEFAULT_BOUNDARIES: dict[AutonomyLevel, AutonomyBoundary] = {
    AutonomyLevel.SUPERVISED: AutonomyBoundary(
        level=AutonomyLevel.SUPERVISED,
        max_risk_level="low",
        requires_approval_for_blocked=True,
        max_files_per_action=1,
        max_lines_per_file=50,
        allowed_paths=["src/autonomous_cognition/"],
        blocked_paths=[
            ".woodpecker.yml",
            "docs/bmm-workflow-status.yaml",
            "infrastructure/terraform/",
            "AGENTS.md",
            "pyproject.toml",
            "src/autonomous_cognition/constitution_audit.py",
            "src/autonomous_cognition/autonomy_tuner.py",
        ],
        escalation_threshold=0,
    ),
    AutonomyLevel.BOUNDED: AutonomyBoundary(
        level=AutonomyLevel.BOUNDED,
        max_risk_level="medium",
        requires_approval_for_blocked=True,
        max_files_per_action=5,
        max_lines_per_file=200,
        allowed_paths=["src/autonomous_cognition/"],
        blocked_paths=[
            ".woodpecker.yml",
            "docs/bmm-workflow-status.yaml",
            "infrastructure/terraform/",
            "AGENTS.md",
            "pyproject.toml",
        ],
        escalation_threshold=0,
    ),
    AutonomyLevel.ASSISTED: AutonomyBoundary(
        level=AutonomyLevel.ASSISTED,
        max_risk_level="high",
        requires_approval_for_blocked=False,
        max_files_per_action=10,
        max_lines_per_file=500,
        allowed_paths=["src/"],
        blocked_paths=[
            ".woodpecker.yml",
            "docs/bmm-workflow-status.yaml",
            "infrastructure/terraform/",
            "AGENTS.md",
            "pyproject.toml",
        ],
        escalation_threshold=2,
    ),
    AutonomyLevel.AUTONOMOUS: AutonomyBoundary(
        level=AutonomyLevel.AUTONOMOUS,
        max_risk_level="critical",
        requires_approval_for_blocked=False,
        max_files_per_action=20,
        max_lines_per_file=1000,
        allowed_paths=["src/"],
        blocked_paths=[
            ".woodpecker.yml",
            "docs/bmm-workflow-status.yaml",
            "infrastructure/terraform/",
            "AGENTS.md",
            "pyproject.toml",
        ],
        escalation_threshold=5,
    ),
}


@dataclass
class AutonomyConfig:
    """Configuration for autonomy tuning.

    Attributes:
        ece_upper_threshold: ECE > this triggers regression
        ece_lower_threshold: ECE < this sustained enables progression
        incident_threshold: Incidents > this triggers regression
        health_score_threshold: Health score < this triggers P2 escalation
        min_stability_window: Minimum consecutive cycles at low ECE before progression
        max_level: Maximum autonomy level allowed
    """

    ece_upper_threshold: float = DEFAULT_ECE_UPPER
    ece_lower_threshold: float = DEFAULT_ECE_LOWER
    incident_threshold: int = DEFAULT_INCIDENT_THRESHOLD
    health_score_threshold: float = DEFAULT_HEALTH_SCORE_THRESHOLD
    min_stability_window: int = 5
    max_level: AutonomyLevel = AutonomyLevel.AUTONOMOUS


class AutonomyTuner:
    """Tunes autonomy level with conservative safety-first logic.

    The tuner implements a conservative approach:
    - Regresses quickly on any incident or calibration degradation
    - Progresses slowly after sustained stability
    - Always respects constitution boundaries

    Example:
        >>> config = AutonomyConfig()
        >>> tuner = AutonomyTuner(config)
        >>> decision = tuner.tune(
        ...     current_level="bounded",
        ...     ece=0.10,
        ...     incident_count=0,
        ...     constitution_compliant=True,
        ... )
        >>> print(f"New level: {decision.new_level}")
    """

    _LEVELS = [
        AutonomyLevel.SUPERVISED,
        AutonomyLevel.BOUNDED,
        AutonomyLevel.ASSISTED,
        AutonomyLevel.AUTONOMOUS,
    ]

    def __init__(
        self,
        config: AutonomyConfig | None = None,
        boundaries: dict[AutonomyLevel, AutonomyBoundary] | None = None,
    ):
        """Initialize the autonomy tuner.

        Args:
            config: Tuning configuration (uses defaults if not provided)
            boundaries: Custom boundaries per level (uses constitution defaults)
        """
        self._config = config or AutonomyConfig()
        self._boundaries = boundaries or DEFAULT_BOUNDARIES.copy()
        self._stability_counter: int = 0
        self._decision_history: list[AutonomyTuningDecision] = []

    @property
    def config(self) -> AutonomyConfig:
        """Current tuning configuration."""
        return self._config

    @property
    def boundaries(self) -> dict[AutonomyLevel, AutonomyBoundary]:
        """Current boundaries per level."""
        return self._boundaries

    @property
    def stability_counter(self) -> int:
        """Number of consecutive cycles with stable, compliant operation."""
        return self._stability_counter

    def get_boundary(self, level: AutonomyLevel | str) -> AutonomyBoundary:
        """Get boundary configuration for a level.

        Args:
            level: Autonomy level (string or enum)

        Returns:
            AutonomyBoundary for the level
        """
        if isinstance(level, str):
            level = AutonomyLevel(level)
        return self._boundaries.get(level, DEFAULT_BOUNDARIES[AutonomyLevel.BOUNDED])

    def tune(
        self,
        current_level: str,
        ece: float,
        incident_count: int,
        constitution_compliant: bool = True,
        health_score: float | None = None,
    ) -> AutonomyTuningDecision:
        """Tune autonomy level from current metrics.

        Implements conservative safety-first logic:
        - Any incident or ECE > upper_threshold → regress one level
        - Sustained low ECE (>= min_stability_window) + no incidents → progress
        - Constitution non-compliance → immediate regression
        - Health score below threshold → trigger escalation

        Args:
            current_level: Current autonomy level (string)
            ece: Expected Calibration Error (0.0 to 1.0)
            incident_count: Number of incidents since last tuning
            constitution_compliant: Whether agent maintained compliance
            health_score: Optional health score (0-100)

        Returns:
            AutonomyTuningDecision with new level and reasoning
        """
        # Parse and validate current level
        if current_level not in [lvl.value for lvl in self._LEVELS]:
            logger.warning("Invalid level %s, defaulting to supervised", current_level)
            current_level = AutonomyLevel.SUPERVISED.value

        current = AutonomyLevel(current_level)
        idx = self._LEVELS.index(current)

        # Check constitution compliance first (immediate regression if violated)
        if not constitution_compliant:
            new_idx = max(0, idx - 2)  # Regress two levels for compliance violation
            reason = "constitution_violation"
            self._stability_counter = 0
        # Check for regression triggers
        elif (
            incident_count > self._config.incident_threshold
            or ece > self._config.ece_upper_threshold
        ):
            new_idx = max(0, idx - 1)
            reason = "regression_guardrail_triggered"
            self._stability_counter = 0
        # Check for health score escalation
        elif (
            health_score is not None
            and health_score < self._config.health_score_threshold
        ):
            new_idx = max(0, idx - 1)
            reason = "health_score_escalation"
            self._stability_counter = 0
        # Check for progression (sustained stability)
        elif (
            ece < self._config.ece_lower_threshold
            and incident_count == 0
            and constitution_compliant
        ):
            self._stability_counter += 1
            if self._stability_counter >= self._config.min_stability_window:
                new_idx = min(len(self._LEVELS) - 1, idx + 1)
                reason = "sustained_calibration_stability"
                self._stability_counter = 0  # Reset after progression
            else:
                new_idx = idx
                reason = "building_stability"
        # Hold level - ECE is in the "middle band" (between lower and upper)
        # Do NOT reset stability counter here: the agent is stable, just not
        # yet below the lower threshold. Resetting would punish agents that
        # hover near the lower threshold and create oscillation.
        else:
            new_idx = idx
            reason = "hold_level"

        # Enforce max level cap
        max_idx = self._LEVELS.index(self._config.max_level)
        if new_idx > max_idx:
            new_idx = max_idx
            reason = "max_level_cap"

        decision = AutonomyTuningDecision(
            previous_level=current.value,
            new_level=self._LEVELS[new_idx].value,
            reason=reason,
            ece=ece,
            incident_count=incident_count,
            constitution_compliant=constitution_compliant,
        )

        self._decision_history.append(decision)
        logger.info(
            "Autonomy tuning: %s → %s (reason: %s, ece=%.3f, incidents=%d)",
            decision.previous_level,
            decision.new_level,
            reason,
            ece,
            incident_count,
        )

        return decision

    def get_boundary_for_action(
        self,
        level: str,
        action_type: str,
        files: list[str],
        risk_level: str,
    ) -> tuple[bool, str]:
        """Check if an action is permitted under the current boundary.

        Args:
            level: Current autonomy level
            action_type: Type of action being attempted
            files: List of files the action would modify
            risk_level: Risk level of the action (low/medium/high/critical)

        Returns:
            Tuple of (is_permitted, reason)
        """
        boundary = self.get_boundary(level)

        # Check risk level
        risk_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        max_risk_order = risk_order.get(boundary.max_risk_level, 1)
        action_risk_order = risk_order.get(risk_level, 3)

        if action_risk_order > max_risk_order:
            return (
                False,
                f"Risk level '{risk_level}' exceeds maximum '{boundary.max_risk_level}'",
            )

        # Check blocked paths
        for file_path in files:
            for blocked in boundary.blocked_paths:
                if file_path.startswith(blocked) or file_path == blocked:
                    if boundary.requires_approval_for_blocked:
                        return (
                            False,
                            f"File '{file_path}' matches blocked path '{blocked}'",
                        )
                    else:
                        return (
                            False,
                            f"Action requires approval for blocked path '{blocked}'",
                        )

        # Check allowed paths (if specified)
        if boundary.allowed_paths:
            for file_path in files:
                allowed = any(file_path.startswith(p) for p in boundary.allowed_paths)
                if not allowed:
                    return False, f"File '{file_path}' outside allowed paths"

        # Check file count
        if len(files) > boundary.max_files_per_action:
            return (
                False,
                f"Too many files: {len(files)} > {boundary.max_files_per_action}",
            )

        return True, "Action permitted"

    def check_escalation_needed(
        self,
        incident_count: int,
        ece: float,
        constitution_violations: int,
        health_score: float | None = None,
    ) -> tuple[bool, str, str]:
        """Check if escalation is needed per constitution Section 5.

        Args:
            incident_count: Number of active incidents
            ece: Current Expected Calibration Error
            constitution_violations: Number of constitution violations
            health_score: Optional health score (0-100)

        Returns:
            Tuple of (escalation_needed, severity, reason)
        """
        # P0: Immediate threat
        if constitution_violations > 0:
            return True, "P0", "constitution_violation_detected"

        # P0: Unauthorized access
        # (Would be detected by constitution_violations > 0)

        # P1: Invariant violation detected
        if incident_count >= 3:
            return True, "P1", "multiple_incidents"

        # P2: Health score degradation
        if health_score is not None and health_score < 50:
            return True, "P2", "health_score_degraded"

        # P2: ECE regression
        if ece > self._config.ece_upper_threshold:
            return True, "P2", "calibration_regression"

        return False, "", ""

    def get_decision_history(self) -> list[AutonomyTuningDecision]:
        """Get history of tuning decisions.

        Returns:
            List of AutonomyTuningDecision objects (most recent last)
        """
        return list(self._decision_history)

    def clear_history(self) -> None:
        """Clear decision history."""
        self._decision_history.clear()
        self._stability_counter = 0

    def update_boundary(
        self,
        level: AutonomyLevel,
        **kwargs: Any,
    ) -> None:
        """Update boundary configuration for a level.

        Args:
            level: The autonomy level to update
            **kwargs: Boundary fields to update
        """
        if level not in self._boundaries:
            self._boundaries[level] = AutonomyBoundary(level=level)

        boundary = self._boundaries[level]
        for key, value in kwargs.items():
            if hasattr(boundary, key):
                setattr(boundary, key, value)
            else:
                logger.warning("Unknown boundary attribute: %s", key)

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of current tuner state.

        Returns:
            Dictionary with tuner summary
        """
        return {
            "stability_counter": self._stability_counter,
            "min_stability_required": self._config.min_stability_window,
            "ece_thresholds": {
                "upper": self._config.ece_upper_threshold,
                "lower": self._config.ece_lower_threshold,
            },
            "incident_threshold": self._config.incident_threshold,
            "max_level": self._config.max_level.value,
            "available_levels": [lvl.value for lvl in self._LEVELS],
            "decision_count": len(self._decision_history),
        }
