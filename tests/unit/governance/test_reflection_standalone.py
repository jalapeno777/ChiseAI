#!/usr/bin/env python3
"""
Standalone test for reflection functionality.

This test file can be run independently to verify reflection module functionality
without being affected by circular imports in the governance package.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

# Run pytest programmatically with proper setup
if __name__ == "__main__":
    import types

    # Create mock src module hierarchy BEFORE any imports
    src_module = types.ModuleType("src")
    sys.modules["src"] = src_module

    # Import governance and link to src.governance
    import governance

    src_module.governance = governance
    sys.modules["src.governance"] = governance

    # Link all submodules
    for attr_name in dir(governance):
        if not attr_name.startswith("_"):
            attr = getattr(governance, attr_name)
            if isinstance(attr, types.ModuleType):
                setattr(src_module.governance, attr_name, attr)
                sys.modules[f"src.governance.{attr_name}"] = attr

    # Now run pytest
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))

# Normal imports after setup
from unittest.mock import MagicMock

from governance.reflection.artifacts import (
    KPISnapshot,
    ReflectionArtifact,
    ReflectionType,
    ReflectionValidator,
    create_reflection_artifact,
)
from governance.reflection.loops import ReflectionLoops, ReflectionStorage


def test_reflection_type_values():
    """Test that reflection types have correct values."""
    assert ReflectionType.MICRO.value == "micro"
    assert ReflectionType.MESO.value == "meso"
    assert ReflectionType.MACRO.value == "macro"


def test_kpi_snapshot_creation():
    """Test creating KPI snapshot."""
    kpi = KPISnapshot(
        ci_pass_rate=0.95,
        coverage=0.82,
        cycle_time_hours=4.5,
        test_count=50,
        lines_changed=120,
    )
    assert kpi.ci_pass_rate == 0.95
    assert kpi.coverage == 0.82


def test_artifact_creation():
    """Test creating reflection artifact."""
    artifact = ReflectionArtifact(
        story_id="ST-TEST-001",
        reflection_type=ReflectionType.MICRO,
        timestamp="2026-02-25T18:00:00Z",
        what_changed="Implemented feature X",
    )
    assert artifact.story_id == "ST-TEST-001"
    assert artifact.reflection_type == ReflectionType.MICRO


def test_artifact_round_trip():
    """Test round-trip serialization."""
    original = ReflectionArtifact(
        story_id="ST-TEST-001",
        reflection_type=ReflectionType.MESO,
        timestamp="2026-02-25T18:00:00Z",
        what_changed="Test",
        kpi_snapshot=KPISnapshot(coverage=0.85),
    )

    json_str = original.to_json()
    restored = ReflectionArtifact.from_json(json_str)

    assert restored.story_id == original.story_id
    assert restored.kpi_snapshot.coverage == original.kpi_snapshot.coverage


def test_validate_valid_story_id():
    """Test validating valid story IDs."""
    assert ReflectionValidator.validate_story_id("ST-TEST-001") is True
    assert ReflectionValidator.validate_story_id("ST-REFLECT-042") is True


def test_validate_invalid_story_id():
    """Test validating invalid story IDs."""
    assert ReflectionValidator.validate_story_id("test-001") is False
    assert ReflectionValidator.validate_story_id("") is False


def test_create_reflection_artifact():
    """Test artifact factory function."""
    artifact = create_reflection_artifact(
        story_id="ST-TEST-001",
        reflection_type=ReflectionType.MICRO,
        what_changed="Test action performed",
    )

    assert artifact.story_id == "ST-TEST-001"
    assert artifact.reflection_type == ReflectionType.MICRO
    assert artifact.timestamp is not None


def test_micro_loop():
    """Test micro loop execution."""
    mock_redis = MagicMock()
    loops = ReflectionLoops(redis_client=mock_redis)

    artifact = loops.micro_loop(
        story_id="ST-TEST-001",
        action="file_edit",
        result="success",
        duration_ms=200,
    )

    assert artifact.story_id == "ST-TEST-001"
    assert artifact.reflection_type == ReflectionType.MICRO


def test_meso_loop():
    """Test meso loop execution."""
    mock_redis = MagicMock()
    loops = ReflectionLoops(redis_client=mock_redis)

    kpi = KPISnapshot(coverage=0.85, ci_pass_rate=0.95)
    artifact = loops.meso_loop(
        story_id="ST-TEST-001",
        what_changed="Story completed",
        kpi_snapshot=kpi,
    )

    assert artifact.story_id == "ST-TEST-001"
    assert artifact.reflection_type == ReflectionType.MESO
    assert artifact.kpi_snapshot.coverage == 0.85


def test_should_promote_high_coverage():
    """Test promotion criteria with high coverage."""
    storage = ReflectionStorage()

    artifact = ReflectionArtifact(
        story_id="ST-TEST-001",
        reflection_type=ReflectionType.MESO,
        timestamp="2026-02-25T18:00:00Z",
        what_changed="Test",
        kpi_snapshot=KPISnapshot(coverage=0.90, ci_pass_rate=0.96),
    )

    assert storage._should_promote_to_qdrant(artifact) is True


def test_should_not_promote_low_coverage():
    """Test that low coverage doesn't trigger promotion."""
    storage = ReflectionStorage()

    artifact = ReflectionArtifact(
        story_id="ST-TEST-001",
        reflection_type=ReflectionType.MESO,
        timestamp="2026-02-25T18:00:00Z",
        what_changed="Test",
        kpi_snapshot=KPISnapshot(coverage=0.70, ci_pass_rate=0.90),
    )

    assert storage._should_promote_to_qdrant(artifact) is False


if __name__ == "__main__":
    # Run tests
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
