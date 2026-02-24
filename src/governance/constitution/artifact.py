"""Constitution artifact loader and validator.

Provides versioned loading of constitution documents with JSON schema validation.

For ST-GOV-002: Agent Constitution Artifact
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
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
class ViolationRule:
    """Represents a violation detection rule."""

    id: str
    name: str
    pattern: str
    severity: str
    auto_detect: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "pattern": self.pattern,
            "severity": self.severity,
            "auto_detect": self.auto_detect,
        }


@dataclass
class EscalationStep:
    """Represents an escalation step in an escalation path."""

    level: int
    target: str
    channel: str
    auto: bool = False
    delay_minutes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "target": self.target,
            "channel": self.channel,
            "auto": self.auto,
            "delay_minutes": self.delay_minutes,
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
class ConstitutionArtifact:
    """Represents a loaded constitution document with all its components."""

    version: ConstitutionVersion
    status: ConstitutionStatus
    effective_date: datetime
    governed_by: str | None = None
    principles: dict[str, Any] = field(default_factory=dict)
    decision_boundaries: dict[str, list[DecisionBoundary]] = field(default_factory=dict)
    safety_invariants: dict[str, list[Invariant]] = field(default_factory=dict)
    escalation_criteria: dict[str, Any] = field(default_factory=dict)
    violation_categories: dict[str, Any] = field(default_factory=dict)
    override_protocol: dict[str, Any] = field(default_factory=dict)
    compliance_metrics: dict[str, Any] = field(default_factory=dict)
    raw_content: str | None = None
    loaded_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert artifact to dictionary for API responses."""
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
                k: [i.to_dict() for i in v] for k, v in self.safety_invariants.items()
            },
            "escalation_criteria": self.escalation_criteria,
            "violation_categories": self.violation_categories,
            "override_protocol": self.override_protocol,
            "compliance_metrics": self.compliance_metrics,
            "loaded_at": self.loaded_at.isoformat(),
        }

    def get_health_status(self) -> dict[str, Any]:
        """Get health status of the constitution."""
        return {
            "status": "healthy",
            "version": str(self.version),
            "loaded_at": self.loaded_at.isoformat(),
            "invariant_count": sum(len(v) for v in self.safety_invariants.values()),
            "violation_rule_count": len(
                self.violation_categories.get("detection_rules", [])
            ),
        }

    def get_invariant(self, invariant_id: str) -> Invariant | None:
        """Get a specific invariant by ID.

        Args:
            invariant_id: The invariant ID (e.g., INV-001)

        Returns:
            Invariant if found, None otherwise
        """
        for invariants in self.safety_invariants.values():
            for inv in invariants:
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
        rules = self.violation_categories.get("detection_rules", [])
        for rule_data in rules:
            if isinstance(rule_data, dict) and rule_data.get("id") == rule_id:
                return ViolationRule(
                    id=rule_data.get("id", ""),
                    name=rule_data.get("name", ""),
                    pattern=rule_data.get("pattern", ""),
                    severity=rule_data.get("severity", "P2"),
                    auto_detect=rule_data.get("auto_detect", True),
                )
        return None


class ConstitutionLoader:
    """Loads and validates constitution documents from the filesystem."""

    DEFAULT_DOCS_PATH = Path("docs/constitution")
    DEFAULT_SCHEMA_PATH = Path("schemas/constitution.json")

    def __init__(
        self,
        docs_path: Path | str | None = None,
        schema_path: Path | str | None = None,
    ):
        """Initialize the constitution loader.

        Args:
            docs_path: Path to constitution documents directory
            schema_path: Path to JSON schema file
        """
        self.docs_path = Path(docs_path) if docs_path else self.DEFAULT_DOCS_PATH
        self.schema_path = (
            Path(schema_path) if schema_path else self.DEFAULT_SCHEMA_PATH
        )
        self._schema_cache: dict[str, Any] | None = None
        self._artifact_cache: dict[str, ConstitutionArtifact] = {}

    def _load_schema(self) -> dict[str, Any]:
        """Load the JSON schema for validation.

        Returns:
            Schema dictionary

        Raises:
            FileNotFoundError: If schema file not found
            json.JSONDecodeError: If schema is invalid JSON
        """
        if self._schema_cache is not None:
            return self._schema_cache

        if not self.schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {self.schema_path}")

        with open(self.schema_path) as f:
            self._schema_cache = json.load(f)

        return self._schema_cache

    def _parse_markdown_frontmatter(self, content: str) -> dict[str, Any]:
        """Parse frontmatter from markdown content.

        Args:
            content: Raw markdown content

        Returns:
            Parsed frontmatter as dictionary
        """
        # Simple frontmatter extraction - look for key: value patterns at start
        frontmatter: dict[str, Any] = {}
        lines = content.split("\n")

        for line in lines[:20]:  # Check first 20 lines for metadata
            line = line.strip()
            if line.startswith("> **"):
                # Parse metadata like: > **Version:** 1.0.0 or > **Governed By:** ST-GOV-002
                match = re.match(r"> \*\*([\w\s]+?):\*\*\s*(.+)", line)
                if match:
                    key = match.group(1).lower().replace(" ", "_")
                    value = match.group(2).strip()
                    frontmatter[key] = value

        return frontmatter

    def _parse_decision_boundaries(
        self, content: str
    ) -> dict[str, list[DecisionBoundary]]:
        """Parse decision boundaries from markdown content.

        Args:
            content: Raw markdown content

        Returns:
            Dictionary of decision boundary lists by category
        """
        boundaries: dict[str, list[DecisionBoundary]] = {
            "autonomous": [],
            "conditional": [],
            "restricted": [],
        }

        # Find sections by header
        sections = {
            "autonomous": self._extract_table_rows(content, "Autonomous Actions"),
            "conditional": self._extract_table_rows(content, "Conditional Actions"),
            "restricted": self._extract_table_rows(content, "Restricted Actions"),
        }

        for category, rows in sections.items():
            for row in rows:
                if len(row) >= 2:
                    boundaries[category].append(
                        DecisionBoundary(
                            category=row[0] if len(row) > 0 else "",
                            action=row[1] if len(row) > 1 else "",
                            constraints=row[2:] if len(row) > 2 else [],
                            approval_required=(
                                row[2]
                                if len(row) > 2 and category != "autonomous"
                                else None
                            ),
                        )
                    )

        return boundaries

    def _extract_table_rows(self, content: str, section_title: str) -> list[list[str]]:
        """Extract table rows from a markdown section.

        Args:
            content: Markdown content
            section_title: Title of the section to find

        Returns:
            List of row data lists
        """
        rows: list[list[str]] = []
        lines = content.split("\n")
        in_section = False

        for line in lines:
            # Check for section header
            if section_title.lower() in line.lower() and line.startswith("###"):
                in_section = True
                continue

            # Check for next section (stop condition)
            if in_section and line.startswith("###"):
                break

            # Parse table rows
            if in_section and "|" in line:
                cells = [c.strip() for c in line.split("|") if c.strip()]
                # Skip header separator rows
                if cells and not all(set(c) <= {"-", ":"} for c in cells):
                    rows.append(cells)

        return rows

    def _parse_safety_invariants(self, content: str) -> dict[str, list[Invariant]]:
        """Parse safety invariants from markdown content.

        Args:
            content: Raw markdown content

        Returns:
            Dictionary of invariant lists by type
        """
        invariants: dict[str, list[Invariant]] = {
            "hard_constraints": [],
            "conditional": [],
        }

        # Parse YAML blocks for invariants
        yaml_pattern = r"```yaml\ninvariants:(.*?)```"
        matches = re.findall(yaml_pattern, content, re.DOTALL)

        for match in matches:
            # Simple YAML parsing for invariants
            inv_pattern = r"-\s+id:\s*(\S+)\s+name:\s*([^\n]+)\s+description:\s*([^\n]+)\s+enforcement:\s*(\S+)(?:\s+exception:\s*([^\n]+))?"
            for inv_match in re.finditer(inv_pattern, match):
                invariants["hard_constraints"].append(
                    Invariant(
                        id=inv_match.group(1),
                        name=inv_match.group(2).strip(),
                        description=inv_match.group(3).strip(),
                        enforcement=EnforcementAction(inv_match.group(4)),
                        exception=(
                            inv_match.group(5).strip() if inv_match.group(5) else None
                        ),
                    )
                )

        # Parse conditional invariants
        yaml_pattern = r"```yaml\nconditional_invariants:(.*?)```"
        matches = re.findall(yaml_pattern, content, re.DOTALL)

        for match in matches:
            inv_pattern = r"-\s+id:\s*(\S+)\s+name:\s*([^\n]+)\s+description:\s*([^\n]+)\s+trigger:\s*([^\n]+)\s+enforcement:\s*(\S+)(?:\s+resolution:\s*([^\n]+))?"
            for inv_match in re.finditer(inv_pattern, match):
                invariants["conditional"].append(
                    Invariant(
                        id=inv_match.group(1),
                        name=inv_match.group(2).strip(),
                        description=inv_match.group(3).strip(),
                        enforcement=EnforcementAction(inv_match.group(5)),
                        exception=(
                            inv_match.group(6).strip() if inv_match.group(6) else None
                        ),
                    )
                )

        return invariants

    def _parse_violation_categories(self, content: str) -> dict[str, Any]:
        """Parse violation categories from markdown content.

        Args:
            content: Raw markdown content

        Returns:
            Dictionary with severity levels and detection rules
        """
        categories: dict[str, Any] = {
            "severity_levels": [],
            "detection_rules": [],
        }

        # Parse severity levels from table
        rows = self._extract_table_rows(content, "Severity Levels")
        for row in rows:
            if len(row) >= 2:
                categories["severity_levels"].append(
                    {
                        "level": row[0] if len(row) > 0 else "",
                        "name": row[1] if len(row) > 1 else "",
                        "description": row[2] if len(row) > 2 else "",
                    }
                )

        # Parse violation rules from YAML blocks
        yaml_pattern = r"```yaml\nviolation_rules:(.*?)```"
        matches = re.findall(yaml_pattern, content, re.DOTALL)

        for match in matches:
            rule_pattern = r"-\s+id:\s*(\S+)\s+name:\s*([^\n]+)\s+pattern:\s*\"([^\"]+)\"\s+severity:\s*(\S+)\s+auto_detect:\s*(\w+)"
            for rule_match in re.finditer(rule_pattern, match):
                categories["detection_rules"].append(
                    {
                        "id": rule_match.group(1),
                        "name": rule_match.group(2).strip(),
                        "pattern": rule_match.group(3),
                        "severity": rule_match.group(4),
                        "auto_detect": rule_match.group(5).lower() == "true",
                    }
                )

        return categories

    def _parse_escalation_criteria(self, content: str) -> dict[str, Any]:
        """Parse escalation criteria from markdown content.

        Args:
            content: Raw markdown content

        Returns:
            Dictionary with triggers and paths
        """
        criteria: dict[str, Any] = {
            "triggers": [],
            "paths": [],
        }

        # Parse triggers from table
        rows = self._extract_table_rows(content, "Automatic Escalation Triggers")
        for row in rows:
            if len(row) >= 2:
                criteria["triggers"].append(
                    {
                        "trigger": row[0] if len(row) > 0 else "",
                        "severity": row[1] if len(row) > 1 else "",
                        "escalation_path": row[2] if len(row) > 2 else "",
                        "response_sla": row[3] if len(row) > 3 else "",
                    }
                )

        # Parse escalation paths from YAML
        yaml_pattern = r"```yaml\nescalation_paths:(.*?)```"
        matches = re.findall(yaml_pattern, content, re.DOTALL)

        for match in matches:
            path_pattern = r"-\s+path:\s*(\S+)(.*?)(?=-\s+path:|$)"
            for path_match in re.finditer(path_pattern, match, re.DOTALL):
                path_name = path_match.group(1)
                steps_text = path_match.group(2)

                steps = []
                step_pattern = r"-\s+level:\s*(\d+)\s+target:\s*(\S+)\s+channel:\s*(\S+)(?:\s+auto:\s*(\w+))?(?:\s+delay_minutes:\s*(\d+))?"
                for step_match in re.finditer(step_pattern, steps_text):
                    steps.append(
                        {
                            "level": int(step_match.group(1)),
                            "target": step_match.group(2),
                            "channel": step_match.group(3),
                            "auto": (
                                step_match.group(4).lower() == "true"
                                if step_match.group(4)
                                else False
                            ),
                            "delay_minutes": (
                                int(step_match.group(5)) if step_match.group(5) else 0
                            ),
                        }
                    )

                criteria["paths"].append(
                    {
                        "path": path_name,
                        "steps": steps,
                    }
                )

        return criteria

    def _parse_override_protocol(self, content: str) -> dict[str, Any]:
        """Parse override protocol from markdown content.

        Args:
            content: Raw markdown content

        Returns:
            Dictionary with override protocol configuration
        """
        protocol: dict[str, Any] = {
            "requirements": {},
            "approval_flow": [],
            "rollback": {},
        }

        # Parse requirements from YAML
        yaml_pattern = r"```yaml\noverride_requirements:(.*?)```"
        matches = re.findall(yaml_pattern, content, re.DOTALL)

        for match in matches:
            # Parse required fields
            fields_pattern = r"required_fields:\s*\n((?:\s+-.*\n)+)"
            fields_match = re.search(fields_pattern, match)
            if fields_match:
                fields = re.findall(r"-\s+(\w+)", fields_match.group(1))
                protocol["requirements"]["required_fields"] = fields

            # Parse approval flow
            flow_pattern = r"approval_flow:\s*\n((?:\s+-.*\n)+)"
            flow_match = re.search(flow_pattern, match)
            if flow_match:
                step_pattern = (
                    r"- step:\s*(\d+)\s+action:\s*([^\n]+)\s+endpoint:\s*(\S+)"
                )
                for step_match in re.finditer(step_pattern, flow_match.group(1)):
                    protocol["approval_flow"].append(
                        {
                            "step": int(step_match.group(1)),
                            "action": step_match.group(2).strip(),
                            "endpoint": step_match.group(3),
                        }
                    )

            # Parse rollback config
            rollback_pattern = r"rollback_capability:\s*\n\s+window_hours:\s*(\d+)\s+automatic_rollback:\s*(\w+)\s+requires_confirmation:\s*(\w+)"
            rollback_match = re.search(rollback_pattern, match)
            if rollback_match:
                protocol["rollback"] = {
                    "window_hours": int(rollback_match.group(1)),
                    "automatic_rollback": rollback_match.group(2).lower() == "true",
                    "requires_confirmation": rollback_match.group(3).lower() == "true",
                }

        return protocol

    def load(
        self,
        version: str | ConstitutionVersion | None = None,
        validate: bool = True,
    ) -> ConstitutionArtifact:
        """Load a constitution document.

        Args:
            version: Version to load (e.g., "1.0.0"). If None, loads latest.
            validate: Whether to validate against JSON schema

        Returns:
            Loaded ConstitutionArtifact

        Raises:
            FileNotFoundError: If constitution document not found
            ValueError: If version is invalid
        """
        if version is None:
            # Find latest version
            version = self.get_latest_version()
            if version is None:
                raise FileNotFoundError(
                    f"No constitution documents found in {self.docs_path}"
                )

        if isinstance(version, str):
            version = ConstitutionVersion.parse(version)

        version_str = str(version)
        cache_key = f"{version_str}:{validate}"

        if cache_key in self._artifact_cache:
            logger.debug(f"Returning cached constitution artifact: {version_str}")
            return self._artifact_cache[cache_key]

        # Find the document file
        doc_path = self.docs_path / f"v{version_str}.md"
        if not doc_path.exists():
            raise FileNotFoundError(f"Constitution document not found: {doc_path}")

        # Load content
        with open(doc_path) as f:
            content = f.read()

        # Parse frontmatter
        frontmatter = self._parse_markdown_frontmatter(content)

        # Create artifact
        artifact = ConstitutionArtifact(
            version=version,
            status=ConstitutionStatus(frontmatter.get("status", "active").lower()),
            effective_date=self._parse_date(frontmatter.get("effective_date")),
            governed_by=frontmatter.get("governed_by"),
            raw_content=content,
        )

        # Parse components
        artifact.principles = {"core_values": []}  # Simplified for now
        artifact.decision_boundaries = self._parse_decision_boundaries(content)
        artifact.safety_invariants = self._parse_safety_invariants(content)
        artifact.violation_categories = self._parse_violation_categories(content)
        artifact.escalation_criteria = self._parse_escalation_criteria(content)
        artifact.override_protocol = self._parse_override_protocol(content)

        # Validate if requested
        if validate and HAS_JSONSCHEMA:
            self._validate_artifact(artifact)

        # Cache the artifact
        self._artifact_cache[cache_key] = artifact
        logger.info(f"Loaded constitution artifact: {version_str}")

        return artifact

    def _parse_date(self, date_str: str | None) -> datetime:
        """Parse a date string.

        Args:
            date_str: Date string in various formats

        Returns:
            Parsed datetime
        """
        if not date_str:
            return datetime.utcnow()

        # Try common formats
        formats = ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"]
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        # Fall back to current date
        logger.warning(f"Could not parse date: {date_str}, using current time")
        return datetime.utcnow()

    def _validate_artifact(self, artifact: ConstitutionArtifact) -> None:
        """Validate artifact against JSON schema.

        Args:
            artifact: Artifact to validate

        Raises:
            ValidationError: If validation fails
        """
        schema = self._load_schema()

        # Convert artifact to dict for validation
        artifact_dict = artifact.to_dict()

        try:
            jsonschema.validate(instance=artifact_dict, schema=schema)
            logger.debug(
                f"Constitution artifact validated successfully: {artifact.version}"
            )
        except JsonSchemaValidationError as e:
            logger.error(f"Constitution validation failed: {e.message}")
            raise

    def get_latest_version(self) -> ConstitutionVersion | None:
        """Get the latest constitution version.

        Returns:
            Latest version or None if no versions found
        """
        if not self.docs_path.exists():
            return None

        versions: list[ConstitutionVersion] = []
        for path in self.docs_path.glob("v*.md"):
            match = re.match(r"v(\d+\.\d+\.\d+)\.md", path.name)
            if match:
                try:
                    versions.append(ConstitutionVersion.parse(match.group(1)))
                except ValueError:
                    continue

        if not versions:
            return None

        return max(versions)

    def list_versions(self) -> list[ConstitutionVersion]:
        """List all available constitution versions.

        Returns:
            List of versions sorted newest first
        """
        if not self.docs_path.exists():
            return []

        versions: list[ConstitutionVersion] = []
        for path in self.docs_path.glob("v*.md"):
            match = re.match(r"v(\d+\.\d+\.\d+)\.md", path.name)
            if match:
                try:
                    versions.append(ConstitutionVersion.parse(match.group(1)))
                except ValueError:
                    continue

        return sorted(versions, reverse=True)

    def clear_cache(self) -> None:
        """Clear the artifact cache."""
        self._artifact_cache.clear()
        logger.debug("Constitution artifact cache cleared")
