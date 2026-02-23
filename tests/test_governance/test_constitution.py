"""Tests for constitution artifact module.

Tests for constitution document loading, validation, and management.

For ST-GOV-002: Agent Constitution Artifact
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from src.governance.constitution.artifact import (
    ConstitutionArtifact,
    ConstitutionLoader,
    ConstitutionStatus,
    ConstitutionVersion,
    EnforcementAction,
    Invariant,
)


class TestConstitutionVersion:
    """Tests for ConstitutionVersion."""

    def test_parse_valid_version(self) -> None:
        """Test parsing valid version strings."""
        version = ConstitutionVersion.parse("1.0.0")
        assert version.major == 1
        assert version.minor == 0
        assert version.patch == 0

    def test_parse_complex_version(self) -> None:
        """Test parsing complex version strings."""
        version = ConstitutionVersion.parse("2.15.37")
        assert version.major == 2
        assert version.minor == 15
        assert version.patch == 37

    def test_parse_invalid_version(self) -> None:
        """Test that invalid versions raise ValueError."""
        with pytest.raises(ValueError):
            ConstitutionVersion.parse("1.0")

        with pytest.raises(ValueError):
            ConstitutionVersion.parse("v1.0.0")

        with pytest.raises(ValueError):
            ConstitutionVersion.parse("invalid")

    def test_version_string_conversion(self) -> None:
        """Test string conversion."""
        version = ConstitutionVersion(1, 2, 3)
        assert str(version) == "1.2.3"

    def test_version_comparison(self) -> None:
        """Test version comparison."""
        v1 = ConstitutionVersion(1, 0, 0)
        v2 = ConstitutionVersion(1, 1, 0)
        v3 = ConstitutionVersion(2, 0, 0)

        assert v1 < v2
        assert v2 < v3
        assert v1 < v3
        assert v1 <= v1
        assert v1 == ConstitutionVersion(1, 0, 0)


class TestConstitutionLoader:
    """Tests for ConstitutionLoader."""

    @pytest.fixture
    def temp_docs_path(self) -> Path:
        """Create a temporary docs path with constitution."""
        with tempfile.TemporaryDirectory() as tmpdir:
            docs_path = Path(tmpdir) / "docs" / "constitution"
            docs_path.mkdir(parents=True)

            # Create a simple constitution document
            constitution_content = """# ChiseAI Agent Constitution v1.0.0

> **Version:** 1.0.0
> **Effective Date:** 2026-02-22
> **Status:** Active
> **Governed By:** ST-GOV-002

## 1. Purpose

This constitution defines agent behavior rules.

## 3. Decision Boundaries

### 3.1 Autonomous Actions (No Human Approval Required)

| Category | Action | Constraints |
|----------|--------|-------------|
| Monitoring | Health checks | Read-only |

### 3.2 Conditional Actions (Requires Confirmation)

| Category | Action | Approval Required |
|----------|--------|-------------------|
| Configuration | Feature flag changes | Single confirmation |

### 3.3 Restricted Actions (Requires Human Approval)

| Category | Action | Approval Level |
|----------|--------|----------------|
| Security | Credential rotation | Admin approval |

## 4. Safety Invariants

### 4.1 Never Violate (Hard Constraints)

```yaml
invariants:
  - id: INV-001
    name: No Direct Main Commits
    description: Agents must never commit directly to main branch
    enforcement: BLOCK
    exception: Emergency override with approval
```

### 4.2 Conditional Invariants

```yaml
conditional_invariants:
  - id: CINV-001
    name: Parallel Execution Isolation
    description: Parallel agents must not share mutable state
    trigger: Parallel work detected
    enforcement: COORDINATE
    resolution: Use ownership claims
```

## 6. Violation Categories

### 6.1 Severity Levels

| Level | Name | Description |
|-------|------|-------------|
| P0 | Critical | Immediate threat |
| P1 | High | Significant impact |
| P2 | Medium | Degraded performance |
| P3 | Low | Minor issues |

### 6.2 Violation Detection Rules

```yaml
violation_rules:
  - id: VR-001
    name: Unauthorized Scope Access
    pattern: "Agent accessed path outside SCOPE_GLOBS"
    severity: P1
    auto_detect: true
```

## 5. Escalation Criteria

### 5.1 Automatic Escalation Triggers

| Trigger | Severity | Escalation Path | Response SLA |
|---------|----------|-----------------|--------------|
| Invariant violation | P1 | #alerts | 5 minutes |

```yaml
escalation_paths:
  - path: default
    steps:
      - level: 1
        target: "#alerts"
        channel: discord
        auto: true
```

## 7. Human Override Protocol

```yaml
override_requirements:
  required_fields:
    - override_id
    - requester
    - justification
  approval_flow:
    - step: 1
      action: Submit request
      endpoint: POST /api/v1/constitution/override
  rollback_capability:
    window_hours: 24
    automatic_rollback: false
    requires_confirmation: true
```
"""
            (docs_path / "v1.0.0.md").write_text(constitution_content)
            yield docs_path  # Return constitution directory path directly

    @pytest.fixture
    def temp_schema_path(self, tmp_path: Path) -> Path:
        """Create a temporary schema file."""
        schema_content = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "required": ["version", "status"],
            "properties": {
                "version": {"type": "string"},
                "status": {"type": "string"},
            },
        }
        schema_path = tmp_path / "constitution.json"
        schema_path.write_text(json.dumps(schema_content))
        return schema_path

    def test_loader_initialization(self, temp_docs_path: Path) -> None:
        """Test loader initialization."""
        loader = ConstitutionLoader(docs_path=temp_docs_path)
        assert loader.docs_path == temp_docs_path

    def test_get_latest_version(self, temp_docs_path: Path) -> None:
        """Test getting the latest version."""
        loader = ConstitutionLoader(docs_path=temp_docs_path)
        version = loader.get_latest_version()

        assert version is not None
        assert version.major == 1
        assert version.minor == 0
        assert version.patch == 0

    def test_list_versions(self, temp_docs_path: Path) -> None:
        """Test listing all versions."""
        loader = ConstitutionLoader(docs_path=temp_docs_path)
        versions = loader.list_versions()

        assert len(versions) == 1
        assert versions[0] == ConstitutionVersion(1, 0, 0)

    def test_load_constitution(self, temp_docs_path: Path) -> None:
        """Test loading a constitution document."""
        loader = ConstitutionLoader(docs_path=temp_docs_path)
        artifact = loader.load("1.0.0", validate=False)

        assert artifact.version == ConstitutionVersion(1, 0, 0)
        assert artifact.status == ConstitutionStatus.ACTIVE
        assert artifact.governed_by == "ST-GOV-002"

    def test_load_latest_constitution(self, temp_docs_path: Path) -> None:
        """Test loading the latest constitution without specifying version."""
        loader = ConstitutionLoader(docs_path=temp_docs_path)
        artifact = loader.load(validate=False)

        assert artifact.version == ConstitutionVersion(1, 0, 0)

    def test_load_nonexistent_version(self, temp_docs_path: Path) -> None:
        """Test that loading a nonexistent version raises FileNotFoundError."""
        loader = ConstitutionLoader(docs_path=temp_docs_path)

        with pytest.raises(FileNotFoundError):
            loader.load("99.0.0")

    def test_artifact_to_dict(self, temp_docs_path: Path) -> None:
        """Test artifact dictionary conversion."""
        loader = ConstitutionLoader(docs_path=temp_docs_path)
        artifact = loader.load("1.0.0", validate=False)
        data = artifact.to_dict()

        assert data["version"] == "1.0.0"
        assert data["status"] == "active"
        assert "decision_boundaries" in data
        assert "safety_invariants" in data

    def test_artifact_health_status(self, temp_docs_path: Path) -> None:
        """Test artifact health status."""
        loader = ConstitutionLoader(docs_path=temp_docs_path)
        artifact = loader.load("1.0.0", validate=False)
        health = artifact.get_health_status()

        assert health["status"] == "healthy"
        assert health["version"] == "1.0.0"
        assert "invariant_count" in health

    def test_caching(self, temp_docs_path: Path) -> None:
        """Test that artifacts are cached."""
        loader = ConstitutionLoader(docs_path=temp_docs_path)

        artifact1 = loader.load("1.0.0", validate=False)
        artifact2 = loader.load("1.0.0", validate=False)

        # Should be the same object (cached)
        assert artifact1 is artifact2

    def test_clear_cache(self, temp_docs_path: Path) -> None:
        """Test cache clearing."""
        loader = ConstitutionLoader(docs_path=temp_docs_path)

        loader.load("1.0.0", validate=False)
        loader.clear_cache()

        # Cache should be empty
        assert len(loader._artifact_cache) == 0


class TestConstitutionArtifact:
    """Tests for ConstitutionArtifact."""

    def test_get_invariant(self) -> None:
        """Test getting an invariant by ID."""
        artifact = ConstitutionArtifact(
            version=ConstitutionVersion(1, 0, 0),
            status=ConstitutionStatus.ACTIVE,
            effective_date=datetime.utcnow(),
            safety_invariants={
                "hard_constraints": [
                    Invariant(
                        id="INV-001",
                        name="Test Invariant",
                        description="Test description",
                        enforcement=EnforcementAction.BLOCK,
                    )
                ]
            },
        )

        invariant = artifact.get_invariant("INV-001")
        assert invariant is not None
        assert invariant.name == "Test Invariant"

        # Test nonexistent invariant
        assert artifact.get_invariant("INV-999") is None


class TestInvariant:
    """Tests for Invariant."""

    def test_invariant_creation(self) -> None:
        """Test invariant creation."""
        invariant = Invariant(
            id="INV-001",
            name="Test Invariant",
            description="Test description",
            enforcement=EnforcementAction.BLOCK,
            exception="Test exception",
        )

        assert invariant.id == "INV-001"
        assert invariant.enforcement == EnforcementAction.BLOCK

    def test_invariant_to_dict(self) -> None:
        """Test invariant to dict conversion."""
        invariant = Invariant(
            id="INV-001",
            name="Test",
            description="Desc",
            enforcement=EnforcementAction.ALERT,
        )

        data = invariant.to_dict()
        assert data["id"] == "INV-001"
        assert data["enforcement"] == "ALERT"


class TestEnforcementAction:
    """Tests for EnforcementAction."""

    def test_enforcement_actions(self) -> None:
        """Test all enforcement action values."""
        assert EnforcementAction.BLOCK.value == "BLOCK"
        assert EnforcementAction.ALERT.value == "ALERT"
        assert EnforcementAction.LOG.value == "LOG"
        assert EnforcementAction.COORDINATE.value == "COORDINATE"
        assert EnforcementAction.VALIDATE.value == "VALIDATE"
