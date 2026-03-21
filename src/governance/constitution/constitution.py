"""Core Constitution class for loading, validation, and rule checking.

Provides:
- Constitution loading and validation against JSON schema
- Rule checking methods for decision boundaries and invariants
- Violation detection logic
- Version management

For ST-GOV-002: Agent Constitution Artifact
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

# Try to import jsonschema for validation, fall back to basic validation
try:
    import jsonschema
    from jsonschema import ValidationError as JsonSchemaValidationError

    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False
    JsonSchemaValidationError = Exception  # type: ignore

logger = logging.getLogger(__name__)


class ConstitutionStatus(str, Enum):
    """Status of a constitution version."""

    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    RETIRED = "retired"


class EnforcementAction(str, Enum):
    """Enforcement action for invariants."""

    BLOCK = "BLOCK"
    ALERT = "ALERT"
    LOG = "LOG"
    COORDINATE = "COORDINATE"
    VALIDATE = "VALIDATE"


class ViolationSeverity(str, Enum):
    """Severity level of a violation."""

    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


@dataclass
class ConstitutionVersion:
    """Represents a constitution version identifier."""

    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, version_str: str) -> ConstitutionVersion:
        """Parse a semantic version string.

        Args:
            version_str: Version string like "1.0.0"

        Returns:
            ConstitutionVersion instance

        Raises:
            ValueError: If version string is invalid
        """
        pattern = r"^(\d+)\.(\d+)\.(\d+)$"
        match = re.match(pattern, version_str)
        if not match:
            raise ValueError(f"Invalid version string: {version_str}")
        return cls(
            major=int(match.group(1)),
            minor=int(match.group(2)),
            patch=int(match.group(3)),
        )

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    def __lt__(self, other: ConstitutionVersion) -> bool:
        return (self.major, self.minor, self.patch) < (
            other.major,
            other.minor,
            other.patch,
        )

    def __le__(self, other: ConstitutionVersion) -> bool:
        return self == other or self < other


@dataclass
class Invariant:
    """Represents a safety invariant rule."""

    id: str
    name: str
    description: str
    enforcement: EnforcementAction
    exception: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "enforcement": self.enforcement.value,
            "exception": self.exception,
        }


@dataclass
class ConditionalInvariant:
    """Represents a conditional safety invariant."""

    id: str
    name: str
    description: str
    trigger: str
    enforcement: EnforcementAction
    resolution: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "trigger": self.trigger,
            "enforcement": self.enforcement.value,
            "resolution": self.resolution,
        }


@dataclass
class ViolationRule:
    """Represents a violation detection rule."""

    id: str
    name: str
    pattern: str
    severity: ViolationSeverity
    auto_detect: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "pattern": self.pattern,
            "severity": self.severity.value,
            "auto_detect": self.auto_detect,
        }


@dataclass
class DecisionBoundary:
    """Represents a decision boundary for agent actions."""

    category: str
    action: str
    constraints: list[str]
    approval_required: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {
            "category": self.category,
            "action": self.action,
            "constraints": self.constraints,
        }
        if self.approval_required:
            result["approval_required"] = self.approval_required
        return result


@dataclass
class SeverityLevel:
    """Represents a violation severity level."""

    level: str
    name: str
    description: str
    detection_sla_seconds: int
    response_sla_minutes: int
    requires_human_intervention: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "name": self.name,
            "description": self.description,
            "detection_sla_seconds": self.detection_sla_seconds,
            "response_sla_minutes": self.response_sla_minutes,
            "requires_human_intervention": self.requires_human_intervention,
        }


@dataclass
class EscalationStep:
    """Represents an escalation step."""

    level: int
    target: str
    channel: str
    auto: bool = False
    delay_minutes: int = 0
    delay_seconds: int | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {
            "level": self.level,
            "target": self.target,
            "channel": self.channel,
            "auto": self.auto,
            "delay_minutes": self.delay_minutes,
        }
        if self.delay_seconds is not None:
            result["delay_seconds"] = self.delay_seconds
        return result


@dataclass
class EscalationPath:
    """Represents an escalation path."""

    path: str
    steps: list[EscalationStep]

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "steps": [s.to_dict() for s in self.steps],
        }


@dataclass
class EscalationTrigger:
    """Represents an escalation trigger."""

    trigger: str
    severity: ViolationSeverity
    escalation_path: str
    response_sla: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "trigger": self.trigger,
            "severity": self.severity.value,
            "escalation_path": self.escalation_path,
            "response_sla": self.response_sla,
        }


@dataclass
class Constitution:
    """Core Constitution class for loading and validation.

    Provides methods for:
    - Loading constitution from JSON files
    - Validating against JSON schema
    - Checking decision boundaries
    - Detecting violations
    - Managing versions
    """

    version: ConstitutionVersion
    status: ConstitutionStatus
    effective_date: datetime
    governed_by: str
    principles: dict[str, Any] = field(default_factory=dict)
    decision_boundaries: dict[str, list[DecisionBoundary]] = field(default_factory=dict)
    safety_invariants: dict[str, list[Invariant]] = field(default_factory=dict)
    conditional_invariants: list[ConditionalInvariant] = field(default_factory=list)
    escalation_criteria: dict[str, Any] = field(default_factory=dict)
    violation_categories: dict[str, Any] = field(default_factory=dict)
    override_protocol: dict[str, Any] = field(default_factory=dict)
    compliance_metrics: dict[str, Any] = field(default_factory=dict)
    version_history: list[dict[str, Any]] = field(default_factory=list)
    loaded_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    # Schema path
    DEFAULT_SCHEMA_PATH = Path("docs/constitution/constitution-schema.json")
    DEFAULT_VERSIONS_PATH = Path("docs/constitution/versions")

    @classmethod
    def load(
        cls,
        version: str | ConstitutionVersion | None = None,
        validate: bool = True,
    ) -> Constitution:
        """Load a constitution from JSON file.

        Args:
            version: Version to load (e.g., "1.0.0"). If None, loads latest.
            validate: Whether to validate against JSON schema

        Returns:
            Loaded Constitution instance

        Raises:
            FileNotFoundError: If constitution file not found
            ValueError: If version is invalid or validation fails
        """
        if version is None:
            version = cls.get_latest_version()
            if version is None:
                raise FileNotFoundError(
                    f"No constitution versions found in {cls.DEFAULT_VERSIONS_PATH}"
                )

        if isinstance(version, str):
            version = ConstitutionVersion.parse(version)

        # Load the JSON file
        file_path = cls.DEFAULT_VERSIONS_PATH / f"v{version}.json"
        if not file_path.exists():
            raise FileNotFoundError(f"Constitution file not found: {file_path}")

        with open(file_path) as f:
            data = json.load(f)

        # Validate if requested
        if validate:
            cls._validate_against_schema(data)

        # Parse the data
        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> Constitution:
        """Create Constitution from dictionary."""
        # Parse decision boundaries
        decision_boundaries = {}
        for category in ["autonomous", "conditional", "restricted"]:
            boundaries = data.get("decision_boundaries", {}).get(category, [])
            decision_boundaries[category] = [
                DecisionBoundary(
                    category=b.get("category", ""),
                    action=b.get("action", ""),
                    constraints=b.get("constraints", []),
                    approval_required=b.get("approval_required"),
                )
                for b in boundaries
            ]

        # Parse safety invariants
        safety_invariants = {}
        invariants_data = data.get("safety_invariants", {})
        safety_invariants["hard_constraints"] = [
            Invariant(
                id=inv["id"],
                name=inv["name"],
                description=inv["description"],
                enforcement=EnforcementAction(inv["enforcement"]),
                exception=inv.get("exception"),
            )
            for inv in invariants_data.get("hard_constraints", [])
        ]

        # Parse conditional invariants
        conditional_invariants = [
            ConditionalInvariant(
                id=inv["id"],
                name=inv["name"],
                description=inv["description"],
                trigger=inv["trigger"],
                enforcement=EnforcementAction(inv["enforcement"]),
                resolution=inv["resolution"],
            )
            for inv in invariants_data.get("conditional", [])
        ]

        # Parse escalation criteria
        escalation_data = data.get("escalation_criteria", {})
        escalation_criteria = {
            "triggers": [
                EscalationTrigger(
                    trigger=t["trigger"],
                    severity=ViolationSeverity(t["severity"]),
                    escalation_path=t["escalation_path"],
                    response_sla=t["response_sla"],
                )
                for t in escalation_data.get("triggers", [])
            ],
            "paths": [
                EscalationPath(
                    path=p["path"],
                    steps=[
                        EscalationStep(
                            level=s["level"],
                            target=s["target"],
                            channel=s["channel"],
                            auto=s.get("auto", False),
                            delay_minutes=s.get("delay_minutes", 0),
                            delay_seconds=s.get("delay_seconds"),
                        )
                        for s in p.get("steps", [])
                    ],
                )
                for p in escalation_data.get("paths", [])
            ],
        }

        # Parse violation categories
        violation_data = data.get("violation_categories", {})
        violation_categories = {
            "severity_levels": [
                SeverityLevel(
                    level=sl["level"],
                    name=sl["name"],
                    description=sl["description"],
                    detection_sla_seconds=sl["detection_sla_seconds"],
                    response_sla_minutes=sl["response_sla_minutes"],
                    requires_human_intervention=sl["requires_human_intervention"],
                )
                for sl in violation_data.get("severity_levels", [])
            ],
            "detection_rules": [
                ViolationRule(
                    id=vr["id"],
                    name=vr["name"],
                    pattern=vr["pattern"],
                    severity=ViolationSeverity(vr["severity"]),
                    auto_detect=vr.get("auto_detect", True),
                )
                for vr in violation_data.get("detection_rules", [])
            ],
        }

        return cls(
            version=ConstitutionVersion.parse(data["version"]),
            status=ConstitutionStatus(data["status"]),
            effective_date=datetime.fromisoformat(
                data["effective_date"].replace("Z", "+00:00")
            ),
            governed_by=data["governed_by"],
            principles=data.get("principles", {}),
            decision_boundaries=decision_boundaries,
            safety_invariants=safety_invariants,
            conditional_invariants=conditional_invariants,
            escalation_criteria=escalation_criteria,
            violation_categories=violation_categories,
            override_protocol=data.get("override_protocol", {}),
            compliance_metrics=data.get("compliance_metrics", {}),
            version_history=data.get("version_history", []),
        )

    @classmethod
    def _validate_against_schema(cls, data: dict[str, Any]) -> None:
        """Validate constitution data against JSON schema.

        Args:
            data: Constitution data to validate

        Raises:
            ValueError: If validation fails
        """
        if not HAS_JSONSCHEMA:
            logger.warning("jsonschema not available, skipping schema validation")
            return

        schema_path = cls.DEFAULT_SCHEMA_PATH
        if not schema_path.exists():
            logger.warning(f"Schema file not found: {schema_path}")
            return

        with open(schema_path) as f:
            schema = json.load(f)

        try:
            jsonschema.validate(instance=data, schema=schema)
            logger.debug("Constitution validated successfully against schema")
        except JsonSchemaValidationError as e:
            raise ValueError(f"Constitution validation failed: {e.message}")

    @classmethod
    def get_latest_version(cls) -> ConstitutionVersion | None:
        """Get the latest constitution version.

        Returns:
            Latest version or None if no versions found
        """
        if not cls.DEFAULT_VERSIONS_PATH.exists():
            return None

        versions: list[ConstitutionVersion] = []
        for path in cls.DEFAULT_VERSIONS_PATH.glob("v*.json"):
            match = re.match(r"v(\d+\.\d+\.\d+)\.json", path.name)
            if match:
                try:
                    versions.append(ConstitutionVersion.parse(match.group(1)))
                except ValueError:
                    continue

        if not versions:
            return None

        return max(versions)

    @classmethod
    def list_versions(cls) -> list[ConstitutionVersion]:
        """List all available constitution versions.

        Returns:
            List of versions sorted newest first
        """
        if not cls.DEFAULT_VERSIONS_PATH.exists():
            return []

        versions: list[ConstitutionVersion] = []
        for path in cls.DEFAULT_VERSIONS_PATH.glob("v*.json"):
            match = re.match(r"v(\d+\.\d+\.\d+)\.json", path.name)
            if match:
                try:
                    versions.append(ConstitutionVersion.parse(match.group(1)))
                except ValueError:
                    continue

        return sorted(versions, reverse=True)

    def to_dict(self) -> dict[str, Any]:
        """Convert constitution to dictionary."""
        return {
            "version": str(self.version),
            "status": self.status.value,
            "effective_date": self.effective_date.isoformat(),
            "governed_by": self.governed_by,
            "principles": self.principles,
            "decision_boundaries": {
                k: [b.to_dict() for b in v] for k, v in self.decision_boundaries.items()
            },
            "safety_invariants": {
                "hard_constraints": [
                    inv.to_dict()
                    for inv in self.safety_invariants.get("hard_constraints", [])
                ],
                "conditional": [inv.to_dict() for inv in self.conditional_invariants],
            },
            "escalation_criteria": {
                "triggers": [
                    t.to_dict() for t in self.escalation_criteria.get("triggers", [])
                ],
                "paths": [
                    p.to_dict() for p in self.escalation_criteria.get("paths", [])
                ],
            },
            "violation_categories": {
                "severity_levels": [
                    sl.to_dict()
                    for sl in self.violation_categories.get("severity_levels", [])
                ],
                "detection_rules": [
                    vr.to_dict()
                    for vr in self.violation_categories.get("detection_rules", [])
                ],
            },
            "override_protocol": self.override_protocol,
            "compliance_metrics": self.compliance_metrics,
            "version_history": self.version_history,
            "loaded_at": self.loaded_at.isoformat(),
        }

    def check_decision_boundary(
        self, category: str, action: str
    ) -> DecisionBoundary | None:
        """Check if an action is within a decision boundary category.

        Args:
            category: Decision boundary category (autonomous, conditional, restricted)
            action: Action to check

        Returns:
            DecisionBoundary if found, None otherwise
        """
        boundaries = self.decision_boundaries.get(category, [])
        for boundary in boundaries:
            if boundary.action.lower() in action.lower():
                return boundary
        return None

    def get_invariant(self, invariant_id: str) -> Invariant | None:
        """Get a specific invariant by ID.

        Args:
            invariant_id: The invariant ID (e.g., INV-001)

        Returns:
            Invariant if found, None otherwise
        """
        for inv in self.safety_invariants.get("hard_constraints", []):
            if inv.id == invariant_id:
                return inv
        return None

    def get_conditional_invariant(
        self, invariant_id: str
    ) -> ConditionalInvariant | None:
        """Get a specific conditional invariant by ID.

        Args:
            invariant_id: The invariant ID (e.g., CINV-001)

        Returns:
            ConditionalInvariant if found, None otherwise
        """
        for inv in self.conditional_invariants:
            if inv.id == invariant_id:
                return inv
        return None

    def get_violation_rule(self, rule_id: str) -> ViolationRule | None:
        """Get a specific violation rule by ID.

        Args:
            rule_id: The rule ID (e.g., VR-001)

        Returns:
            ViolationRule if found, None otherwise
        """
        for rule in self.violation_categories.get("detection_rules", []):
            if rule.id == rule_id:
                return rule
        return None

    def check_violation(
        self, action: str, context: dict[str, Any] | None = None
    ) -> list[ViolationRule]:
        """Check if an action violates any rules.

        Args:
            action: Action text to check
            context: Additional context

        Returns:
            List of violated rules
        """
        violations = []
        context = context or {}

        for rule in self.violation_categories.get("detection_rules", []):
            if not rule.auto_detect:
                continue

            # Check if pattern matches
            if re.search(rule.pattern, action, re.IGNORECASE):
                violations.append(rule)

        return violations

    def get_escalation_path(self, path_name: str) -> EscalationPath | None:
        """Get an escalation path by name.

        Args:
            path_name: Name of the escalation path

        Returns:
            EscalationPath if found, None otherwise
        """
        for path in self.escalation_criteria.get("paths", []):
            if path.path == path_name:
                return path
        return None

    def get_escalation_triggers(
        self, severity: ViolationSeverity | None = None
    ) -> list[EscalationTrigger]:
        """Get escalation triggers, optionally filtered by severity.

        Args:
            severity: Optional severity filter

        Returns:
            List of matching escalation triggers
        """
        triggers = self.escalation_criteria.get("triggers", [])
        if severity:
            triggers = [t for t in triggers if t.severity == severity]
        return triggers

    def get_severity_level(self, level: str) -> SeverityLevel | None:
        """Get a severity level by code.

        Args:
            level: Severity level code (P0, P1, P2, P3)

        Returns:
            SeverityLevel if found, None otherwise
        """
        for sl in self.violation_categories.get("severity_levels", []):
            if sl.level == level:
                return sl
        return None

    def validate_action(
        self, action: str, category: str | None = None
    ) -> dict[str, Any]:
        """Validate an action against the constitution.

        Args:
            action: Action to validate
            category: Optional category hint

        Returns:
            Validation result with status and any violations
        """
        result = {
            "valid": True,
            "violations": [],
            "requires_approval": False,
            "approval_level": None,
        }

        # Check for violations
        violations = self.check_violation(action)
        if violations:
            result["valid"] = False
            result["violations"] = [v.to_dict() for v in violations]

        # Check decision boundaries
        for cat in ["autonomous", "conditional", "restricted"]:
            boundary = self.check_decision_boundary(cat, action)
            if boundary:
                if cat == "restricted":
                    result["requires_approval"] = True
                    result["approval_level"] = boundary.approval_required
                elif cat == "conditional":
                    result["requires_approval"] = True
                    result["approval_level"] = boundary.approval_required
                break

        return result

    def get_health_status(self) -> dict[str, Any]:
        """Get health status of the constitution."""
        return {
            "status": "healthy"
            if self.status == ConstitutionStatus.ACTIVE
            else self.status.value,
            "version": str(self.version),
            "loaded_at": self.loaded_at.isoformat(),
            "invariant_count": len(self.safety_invariants.get("hard_constraints", [])),
            "conditional_invariant_count": len(self.conditional_invariants),
            "violation_rule_count": len(
                self.violation_categories.get("detection_rules", [])
            ),
            "decision_boundary_count": sum(
                len(v) for v in self.decision_boundaries.values()
            ),
        }

    def get_compliance_summary(self) -> dict[str, Any]:
        """Get compliance metrics summary."""
        kpis = self.compliance_metrics.get("kpis", [])
        return {
            "total_kpis": len(kpis),
            "kpis": [
                {"metric": k.get("metric"), "target": k.get("target")} for k in kpis
            ],
            "reporting_schedules": len(self.compliance_metrics.get("reporting", [])),
        }
