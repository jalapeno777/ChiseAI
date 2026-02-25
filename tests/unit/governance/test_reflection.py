"""
Unit tests for reflection module.

Tests cover:
- Artifact creation and validation
- Reflection loop execution
- Storage operations
- Schema validation
"""

from __future__ import annotations

import json
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

# Import directly from reflection submodule to avoid governance package circular imports
from governance.reflection.artifacts import (
    AutomationTarget,
    FailureObservation,
    FailureType,
    KPISnapshot,
    Priority,
    PromotionCandidate,
    ReflectionArtifact,
    ReflectionType,
    ReflectionValidator,
    RootCause,
    RootCauseCategory,
    Severity,
    create_reflection_artifact,
)
from governance.reflection.loops import ReflectionLoops, ReflectionStorage


class TestReflectionType:
    """Test reflection type enum."""

    def test_reflection_type_values(self):
        """Test that reflection types have correct values."""
        assert ReflectionType.MICRO.value == "micro"
        assert ReflectionType.MESO.value == "meso"
        assert ReflectionType.MACRO.value == "macro"

    def test_reflection_type_from_string(self):
        """Test creating reflection type from string."""
        assert ReflectionType("micro") == ReflectionType.MICRO
        assert ReflectionType("meso") == ReflectionType.MESO
        assert ReflectionType("macro") == ReflectionType.MACRO


class TestKPISnapshot:
    """Test KPI snapshot dataclass."""

    def test_kpi_snapshot_creation(self):
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
        assert kpi.cycle_time_hours == 4.5
        assert kpi.test_count == 50
        assert kpi.lines_changed == 120

    def test_kpi_snapshot_to_dict(self):
        """Test converting KPI snapshot to dictionary."""
        kpi = KPISnapshot(ci_pass_rate=0.95, coverage=0.82)
        d = kpi.to_dict()

        assert d == {"ci_pass_rate": 0.95, "coverage": 0.82}
        assert "cycle_time_hours" not in d

    def test_kpi_snapshot_from_dict(self):
        """Test creating KPI snapshot from dictionary."""
        d = {"ci_pass_rate": 0.95, "coverage": 0.82, "test_count": 50}
        kpi = KPISnapshot.from_dict(d)

        assert kpi.ci_pass_rate == 0.95
        assert kpi.coverage == 0.82
        assert kpi.test_count == 50
        assert kpi.cycle_time_hours is None


class TestFailureObservation:
    """Test failure observation dataclass."""

    def test_failure_observation_creation(self):
        """Test creating failure observation."""
        failure = FailureObservation(
            type=FailureType.TEST_FAILURE,
            timestamp="2026-02-25T18:00:00Z",
            description="Test failed with assertion error",
            severity=Severity.HIGH,
        )

        assert failure.type == FailureType.TEST_FAILURE
        assert failure.timestamp == "2026-02-25T18:00:00Z"
        assert failure.description == "Test failed with assertion error"
        assert failure.severity == Severity.HIGH

    def test_failure_observation_to_dict(self):
        """Test converting failure observation to dictionary."""
        failure = FailureObservation(
            type=FailureType.CI_FAILURE,
            timestamp="2026-02-25T18:00:00Z",
            description="CI pipeline failed",
            severity=Severity.MEDIUM,
        )
        d = failure.to_dict()

        assert d["type"] == "ci_failure"
        assert d["severity"] == "medium"

    def test_failure_observation_from_dict(self):
        """Test creating failure observation from dictionary."""
        d = {
            "type": "test_failure",
            "timestamp": "2026-02-25T18:00:00Z",
            "description": "Test failed",
            "severity": "low",
        }
        failure = FailureObservation.from_dict(d)

        assert failure.type == FailureType.TEST_FAILURE
        assert failure.severity == Severity.LOW


class TestRootCause:
    """Test root cause dataclass."""

    def test_root_cause_creation(self):
        """Test creating root cause."""
        rc = RootCause(
            category=RootCauseCategory.CODE_QUALITY,
            description="Missing null check",
            contributing_factors=["incomplete review", "no static analysis"],
        )

        assert rc.category == RootCauseCategory.CODE_QUALITY
        assert rc.description == "Missing null check"
        assert len(rc.contributing_factors) == 2

    def test_root_cause_to_dict(self):
        """Test converting root cause to dictionary."""
        rc = RootCause(
            category=RootCauseCategory.TEST_COVERAGE,
            description="Insufficient test coverage",
        )
        d = rc.to_dict()

        assert d["category"] == "test_coverage"
        assert d["contributing_factors"] == []


class TestAutomationTarget:
    """Test automation target dataclass."""

    def test_automation_target_creation(self):
        """Test creating automation target."""
        target = AutomationTarget(
            target="Auto-fix lint errors",
            priority=Priority.HIGH,
            estimated_impact="Reduce CI failures by 20%",
        )

        assert target.target == "Auto-fix lint errors"
        assert target.priority == Priority.HIGH
        assert target.estimated_impact == "Reduce CI failures by 20%"


class TestPromotionCandidate:
    """Test promotion candidate dataclass."""

    def test_promotion_candidate_creation(self):
        """Test creating promotion candidate."""
        candidate = PromotionCandidate(
            story_id="ST-TEST-001",
            reason="High coverage and CI pass rate",
            confidence=0.92,
        )

        assert candidate.story_id == "ST-TEST-001"
        assert candidate.confidence == 0.92


class TestReflectionArtifact:
    """Test reflection artifact dataclass."""

    def test_artifact_creation(self):
        """Test creating reflection artifact."""
        artifact = ReflectionArtifact(
            story_id="ST-TEST-001",
            reflection_type=ReflectionType.MICRO,
            timestamp="2026-02-25T18:00:00Z",
            what_changed="Implemented feature X",
        )

        assert artifact.story_id == "ST-TEST-001"
        assert artifact.reflection_type == ReflectionType.MICRO
        assert artifact.what_changed == "Implemented feature X"

    def test_artifact_with_kpi(self):
        """Test artifact with KPI snapshot."""
        kpi = KPISnapshot(coverage=0.85, ci_pass_rate=0.95)
        artifact = ReflectionArtifact(
            story_id="ST-TEST-001",
            reflection_type=ReflectionType.MESO,
            timestamp="2026-02-25T18:00:00Z",
            what_changed="Story completed",
            kpi_snapshot=kpi,
        )

        assert artifact.kpi_snapshot.coverage == 0.85

    def test_artifact_to_dict(self):
        """Test converting artifact to dictionary."""
        artifact = ReflectionArtifact(
            story_id="ST-TEST-001",
            reflection_type=ReflectionType.MICRO,
            timestamp="2026-02-25T18:00:00Z",
            what_changed="Test",
        )
        d = artifact.to_dict()

        assert d["story_id"] == "ST-TEST-001"
        assert d["reflection_type"] == "micro"
        assert "kpi_snapshot" not in d

    def test_artifact_to_json(self):
        """Test converting artifact to JSON."""
        artifact = ReflectionArtifact(
            story_id="ST-TEST-001",
            reflection_type=ReflectionType.MICRO,
            timestamp="2026-02-25T18:00:00Z",
            what_changed="Test",
        )
        json_str = artifact.to_json()

        assert "ST-TEST-001" in json_str
        assert "micro" in json_str

        # Verify it's valid JSON
        data = json.loads(json_str)
        assert data["story_id"] == "ST-TEST-001"

    def test_artifact_from_dict(self):
        """Test creating artifact from dictionary."""
        d = {
            "story_id": "ST-TEST-001",
            "reflection_type": "meso",
            "timestamp": "2026-02-25T18:00:00Z",
            "what_changed": "Story completed",
            "kpi_snapshot": {"coverage": 0.85},
        }
        artifact = ReflectionArtifact.from_dict(d)

        assert artifact.story_id == "ST-TEST-001"
        assert artifact.reflection_type == ReflectionType.MESO
        assert artifact.kpi_snapshot.coverage == 0.85

    def test_artifact_from_json(self):
        """Test creating artifact from JSON."""
        json_str = json.dumps(
            {
                "story_id": "ST-TEST-001",
                "reflection_type": "micro",
                "timestamp": "2026-02-25T18:00:00Z",
                "what_changed": "Test action",
            }
        )
        artifact = ReflectionArtifact.from_json(json_str)

        assert artifact.story_id == "ST-TEST-001"
        assert artifact.what_changed == "Test action"

    def test_artifact_round_trip(self):
        """Test round-trip serialization."""
        original = ReflectionArtifact(
            story_id="ST-TEST-001",
            reflection_type=ReflectionType.MESO,
            timestamp="2026-02-25T18:00:00Z",
            what_changed="Test",
            kpi_snapshot=KPISnapshot(coverage=0.85),
            failures_observed=[
                FailureObservation(
                    type=FailureType.TEST_FAILURE,
                    timestamp="2026-02-25T18:00:00Z",
                    description="Test failed",
                    severity=Severity.MEDIUM,
                )
            ],
        )

        json_str = original.to_json()
        restored = ReflectionArtifact.from_json(json_str)

        assert restored.story_id == original.story_id
        assert restored.reflection_type == original.reflection_type
        assert restored.kpi_snapshot.coverage == original.kpi_snapshot.coverage
        assert len(restored.failures_observed) == 1


class TestReflectionValidator:
    """Test reflection validator."""

    def test_validate_valid_story_id(self):
        """Test validating valid story IDs."""
        assert ReflectionValidator.validate_story_id("ST-TEST-001") is True
        assert ReflectionValidator.validate_story_id("ST-REFLECT-042") is True
        assert ReflectionValidator.validate_story_id("ST-A-1") is True

    def test_validate_invalid_story_id(self):
        """Test validating invalid story IDs."""
        assert ReflectionValidator.validate_story_id("test-001") is False
        assert ReflectionValidator.validate_story_id("ST-001") is False
        assert ReflectionValidator.validate_story_id("ST-TEST") is False
        assert ReflectionValidator.validate_story_id("") is False

    def test_validate_valid_reflection_type(self):
        """Test validating valid reflection types."""
        assert ReflectionValidator.validate_reflection_type("micro") is True
        assert ReflectionValidator.validate_reflection_type("meso") is True
        assert ReflectionValidator.validate_reflection_type("macro") is True

    def test_validate_invalid_reflection_type(self):
        """Test validating invalid reflection types."""
        assert ReflectionValidator.validate_reflection_type("invalid") is False
        assert ReflectionValidator.validate_reflection_type("") is False

    def test_validate_valid_timestamp(self):
        """Test validating valid timestamps."""
        assert ReflectionValidator.validate_timestamp("2026-02-25T18:00:00Z") is True
        assert (
            ReflectionValidator.validate_timestamp("2026-02-25T18:00:00+00:00") is True
        )

    def test_validate_invalid_timestamp(self):
        """Test validating invalid timestamps."""
        assert ReflectionValidator.validate_timestamp("invalid") is False
        assert ReflectionValidator.validate_timestamp("2026-02-25") is False

    def test_validate_valid_kpi_snapshot(self):
        """Test validating valid KPI snapshot."""
        kpi = {"ci_pass_rate": 0.95, "coverage": 0.82}
        errors = ReflectionValidator.validate_kpi_snapshot(kpi)
        assert len(errors) == 0

    def test_validate_kpi_out_of_range(self):
        """Test validating KPI with out-of-range values."""
        kpi = {"ci_pass_rate": 1.5, "coverage": -0.1}
        errors = ReflectionValidator.validate_kpi_snapshot(kpi)
        assert len(errors) == 2
        assert any("ci_pass_rate" in e for e in errors)
        assert any("coverage" in e for e in errors)

    def test_validate_valid_artifact(self):
        """Test validating a valid artifact."""
        artifact = ReflectionArtifact(
            story_id="ST-TEST-001",
            reflection_type=ReflectionType.MICRO,
            timestamp="2026-02-25T18:00:00Z",
            what_changed="Test",
        )
        is_valid, errors = ReflectionValidator.validate_artifact(artifact)

        assert is_valid is True
        assert len(errors) == 0

    def test_validate_invalid_artifact_missing_fields(self):
        """Test validating artifact with missing fields."""
        artifact = {"story_id": "ST-TEST-001"}  # Missing required fields
        is_valid, errors = ReflectionValidator.validate_artifact(artifact)

        assert is_valid is False
        assert any("Missing required field" in e for e in errors)

    def test_validate_invalid_artifact_bad_story_id(self):
        """Test validating artifact with invalid story ID."""
        artifact = {
            "story_id": "invalid",
            "reflection_type": "micro",
            "timestamp": "2026-02-25T18:00:00Z",
            "what_changed": "Test",
        }
        is_valid, errors = ReflectionValidator.validate_artifact(artifact)

        assert is_valid is False
        assert any("Invalid story_id" in e for e in errors)


class TestCreateReflectionArtifact:
    """Test artifact factory function."""

    def test_create_basic_artifact(self):
        """Test creating basic artifact."""
        artifact = create_reflection_artifact(
            story_id="ST-TEST-001",
            reflection_type=ReflectionType.MICRO,
            what_changed="Test action performed",
        )

        assert artifact.story_id == "ST-TEST-001"
        assert artifact.reflection_type == ReflectionType.MICRO
        assert artifact.what_changed == "Test action performed"
        assert artifact.timestamp is not None

    def test_create_artifact_with_kpi(self):
        """Test creating artifact with KPI."""
        kpi = KPISnapshot(coverage=0.85, ci_pass_rate=0.95)
        artifact = create_reflection_artifact(
            story_id="ST-TEST-001",
            reflection_type=ReflectionType.MESO,
            what_changed="Story completed",
            kpi_snapshot=kpi,
        )

        assert artifact.kpi_snapshot.coverage == 0.85

    def test_create_artifact_timestamp_format(self):
        """Test that timestamp is in correct format."""
        artifact = create_reflection_artifact(
            story_id="ST-TEST-001",
            reflection_type=ReflectionType.MICRO,
            what_changed="Test",
        )

        # Should be ISO 8601 format ending in Z
        assert artifact.timestamp.endswith("Z")
        assert "T" in artifact.timestamp


class TestReflectionStorage:
    """Test reflection storage."""

    def test_storage_initialization(self):
        """Test storage initialization."""
        storage = ReflectionStorage()
        assert storage.redis is None
        assert storage.qdrant is None

    def test_storage_with_mock_redis(self):
        """Test storage with mock Redis client."""
        mock_redis = MagicMock()
        storage = ReflectionStorage(redis_client=mock_redis)

        artifact = ReflectionArtifact(
            story_id="ST-TEST-001",
            reflection_type=ReflectionType.MICRO,
            timestamp="2026-02-25T18:00:00Z",
            what_changed="Test",
        )

        # Mock the lpush and expire methods
        mock_redis.lpush.return_value = 1
        mock_redis.expire.return_value = True

        # Store should use Redis
        storage.redis = mock_redis
        key = storage.MICRO_KEY.format(story_id="ST-TEST-001")
        storage.redis.lpush(key, artifact.to_json())

        mock_redis.lpush.assert_called_once()

    def test_store_micro_reflection(self):
        """Test storing micro-reflection."""
        mock_redis = MagicMock()
        storage = ReflectionStorage(redis_client=mock_redis)

        artifact = storage.store_micro_reflection(
            story_id="ST-TEST-001",
            action="tool_call",
            result="success",
            duration_ms=150,
        )

        assert artifact.story_id == "ST-TEST-001"
        assert artifact.reflection_type == ReflectionType.MICRO
        assert "tool_call" in artifact.what_changed

        mock_redis.lpush.assert_called_once()
        mock_redis.expire.assert_called_once()

    def test_store_meso_reflection(self):
        """Test storing meso-reflection."""
        mock_redis = MagicMock()
        storage = ReflectionStorage(redis_client=mock_redis)

        kpi = KPISnapshot(coverage=0.85, ci_pass_rate=0.95)
        artifact = storage.store_meso_reflection(
            story_id="ST-TEST-001",
            what_changed="Story completed successfully",
            kpi_snapshot=kpi,
        )

        assert artifact.story_id == "ST-TEST-001"
        assert artifact.reflection_type == ReflectionType.MESO
        assert artifact.kpi_snapshot.coverage == 0.85

        mock_redis.set.assert_called_once()
        mock_redis.expire.assert_called_once()

    def test_store_macro_reflection(self):
        """Test storing macro-reflection."""
        mock_redis = MagicMock()
        mock_qdrant = MagicMock()
        storage = ReflectionStorage(
            redis_client=mock_redis,
            qdrant_client=mock_qdrant,
        )

        kpi = KPISnapshot(coverage=0.80, ci_pass_rate=0.90)
        artifact = storage.store_macro_reflection(
            period="daily",
            what_changed="Daily retro summary",
            kpi_snapshot=kpi,
            failures_observed=[],
            root_causes=[],
            next_automation_targets=[],
            promotion_candidates=[],
        )

        assert artifact.reflection_type == ReflectionType.MACRO
        assert "MACRO-DAILY" in artifact.story_id

        mock_redis.set.assert_called_once()
        mock_qdrant.upsert.assert_called_once()

    def test_should_promote_high_coverage(self):
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

    def test_should_promote_with_failures(self):
        """Test promotion criteria with failures and root causes."""
        storage = ReflectionStorage()

        artifact = ReflectionArtifact(
            story_id="ST-TEST-001",
            reflection_type=ReflectionType.MESO,
            timestamp="2026-02-25T18:00:00Z",
            what_changed="Test",
            failures_observed=[
                FailureObservation(
                    type=FailureType.TEST_FAILURE,
                    timestamp="2026-02-25T18:00:00Z",
                    description="Test failed",
                    severity=Severity.MEDIUM,
                )
            ],
            root_causes=[
                RootCause(
                    category=RootCauseCategory.CODE_QUALITY,
                    description="Missing test",
                )
            ],
        )

        assert storage._should_promote_to_qdrant(artifact) is True

    def test_should_not_promote_low_coverage(self):
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

    def test_get_micro_reflections(self):
        """Test retrieving micro-reflections."""
        mock_redis = MagicMock()
        storage = ReflectionStorage(redis_client=mock_redis)

        artifact = ReflectionArtifact(
            story_id="ST-TEST-001",
            reflection_type=ReflectionType.MICRO,
            timestamp="2026-02-25T18:00:00Z",
            what_changed="Test",
        )

        mock_redis.lrange.return_value = [artifact.to_json()]

        reflections = storage.get_micro_reflections("ST-TEST-001")

        assert len(reflections) == 1
        assert reflections[0].story_id == "ST-TEST-001"

    def test_get_meso_reflection(self):
        """Test retrieving meso-reflection."""
        mock_redis = MagicMock()
        storage = ReflectionStorage(redis_client=mock_redis)

        artifact = ReflectionArtifact(
            story_id="ST-TEST-001",
            reflection_type=ReflectionType.MESO,
            timestamp="2026-02-25T18:00:00Z",
            what_changed="Test",
        )

        mock_redis.get.return_value = artifact.to_json()

        reflection = storage.get_meso_reflection("ST-TEST-001")

        assert reflection is not None
        assert reflection.story_id == "ST-TEST-001"

    def test_get_meso_reflection_not_found(self):
        """Test retrieving non-existent meso-reflection."""
        mock_redis = MagicMock()
        storage = ReflectionStorage(redis_client=mock_redis)

        mock_redis.get.return_value = None

        reflection = storage.get_meso_reflection("ST-NOTFOUND-001")

        assert reflection is None


class TestReflectionLoops:
    """Test reflection loops."""

    def test_loops_initialization(self):
        """Test loops initialization."""
        loops = ReflectionLoops()
        assert loops.storage is not None

    def test_micro_loop(self):
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
        assert "file_edit" in artifact.what_changed

    def test_micro_loop_with_error(self):
        """Test micro loop with error."""
        mock_redis = MagicMock()
        loops = ReflectionLoops(redis_client=mock_redis)

        artifact = loops.micro_loop(
            story_id="ST-TEST-001",
            action="test_run",
            result="failure",
            error="Assertion failed",
        )

        assert len(artifact.failures_observed) == 1
        assert artifact.failures_observed[0].description == "Assertion failed"

    def test_meso_loop(self):
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

    def test_macro_loop(self):
        """Test macro loop execution."""
        mock_redis = MagicMock()
        loops = ReflectionLoops(redis_client=mock_redis)

        # Set up mock to return meso reflections
        meso_artifact = ReflectionArtifact(
            story_id="ST-TEST-001",
            reflection_type=ReflectionType.MESO,
            timestamp="2026-02-25T18:00:00Z",
            what_changed="Story completed",
            kpi_snapshot=KPISnapshot(coverage=0.85, ci_pass_rate=0.95),
            failures_observed=[],
            root_causes=[],
            next_automation_targets=[],
            promotion_candidates=[],
        )
        mock_redis.get.return_value = meso_artifact.to_json()

        artifact = loops.macro_loop(
            period="daily",
            stories_completed=["ST-TEST-001"],
        )

        assert artifact.reflection_type == ReflectionType.MACRO
        assert "daily" in artifact.what_changed.lower()

    def test_compute_aggregate_kpis(self):
        """Test KPI aggregation."""
        mock_redis = MagicMock()
        loops = ReflectionLoops(redis_client=mock_redis)

        # Set up mock to return meso reflections
        meso_artifacts = [
            ReflectionArtifact(
                story_id="ST-TEST-001",
                reflection_type=ReflectionType.MESO,
                timestamp="2026-02-25T18:00:00Z",
                what_changed="Story 1",
                kpi_snapshot=KPISnapshot(
                    coverage=0.80, ci_pass_rate=0.90, cycle_time_hours=4.0
                ),
            ),
            ReflectionArtifact(
                story_id="ST-TEST-002",
                reflection_type=ReflectionType.MESO,
                timestamp="2026-02-25T18:00:00Z",
                what_changed="Story 2",
                kpi_snapshot=KPISnapshot(
                    coverage=0.90, ci_pass_rate=0.95, cycle_time_hours=6.0
                ),
            ),
        ]

        mock_redis.get.side_effect = [a.to_json() for a in meso_artifacts]

        kpis = loops._compute_aggregate_kpis(["ST-TEST-001", "ST-TEST-002"])

        assert abs(kpis.coverage - 0.85) < 0.001  # Average of 0.80 and 0.90
        assert kpis.ci_pass_rate == 0.925  # Average of 0.90 and 0.95
        assert kpis.cycle_time_hours == 5.0  # Average of 4.0 and 6.0

    def test_generate_macro_summary(self):
        """Test macro summary generation."""
        loops = ReflectionLoops()

        root_causes = [
            RootCause(category=RootCauseCategory.CODE_QUALITY, description="Issue 1"),
            RootCause(category=RootCauseCategory.CODE_QUALITY, description="Issue 2"),
            RootCause(category=RootCauseCategory.TEST_COVERAGE, description="Issue 3"),
        ]

        summary = loops._generate_macro_summary(
            period="daily",
            stories_completed=["ST-001", "ST-002"],
            failures=[],
            root_causes=root_causes,
        )

        assert "daily" in summary
        assert "2" in summary  # Number of stories
        assert "code_quality" in summary


class TestIntegration:
    """Integration tests for the reflection system."""

    def test_full_micro_to_meso_flow(self):
        """Test complete flow from micro to meso reflection."""
        mock_redis = MagicMock()
        loops = ReflectionLoops(redis_client=mock_redis)

        # Execute micro reflections
        for i in range(3):
            loops.micro_loop(
                story_id="ST-TEST-001",
                action=f"action_{i}",
                result="success",
            )

        # Execute meso reflection
        kpi = KPISnapshot(coverage=0.90, ci_pass_rate=0.95)
        meso = loops.meso_loop(
            story_id="ST-TEST-001",
            what_changed="Story completed with 3 actions",
            kpi_snapshot=kpi,
        )

        assert meso.story_id == "ST-TEST-001"
        assert meso.kpi_snapshot.coverage == 0.90

    def test_promotion_to_qdrant(self):
        """Test that high-quality reflections are promoted to Qdrant."""
        mock_redis = MagicMock()
        mock_qdrant = MagicMock()
        loops = ReflectionLoops(
            redis_client=mock_redis,
            qdrant_client=mock_qdrant,
        )

        # High coverage should trigger promotion
        kpi = KPISnapshot(coverage=0.90, ci_pass_rate=0.96)
        loops.meso_loop(
            story_id="ST-TEST-001",
            what_changed="High quality story",
            kpi_snapshot=kpi,
        )

        # Qdrant upsert should have been called
        mock_qdrant.upsert.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
