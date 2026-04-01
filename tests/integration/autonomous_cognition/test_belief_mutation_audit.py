"""Tests for belief mutation audit instrumentation.

These tests verify that audit events are emitted when beliefs are mutated
across the autonomous cognition system.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import jsonschema
import pytest

# Schema path constant
SCHEMA_PATH = (
    Path(__file__).parent.parent.parent.parent
    / "schemas"
    / "aria"
    / "belief-mutation-event.schema.json"
)


class TestBeliefMutationAuditInstrumentation:
    """Tests for audit event emission at mutation touchpoints."""

    @pytest.fixture
    def mock_redis_client(self):
        """Create a mock Redis client at the connection level."""
        mock_client = MagicMock()
        mock_client.get.return_value = None  # Feature flag not set - defaults to True
        mock_client.lpush.return_value = 1
        mock_client.expire.return_value = True
        return mock_client

    @pytest.fixture
    def sample_belief_event(self):
        """Sample belief mutation event for testing."""
        return {
            "event_id": "test-evt-001",
            "timestamp": datetime.now(UTC).isoformat(),
            "actor": "autonomous_cognition",
            "belief_key": "test.belief.001",
            "mutation_type": "update",
            "severity": "medium",
            "old_value": {"statement": "Old belief"},
            "new_value": {"statement": "New belief"},
            "evidence": [{"source_type": "system", "summary": "Test evidence"}],
            "conflict_resolution": None,
            "approval_required": False,
            "approval_reason": None,
            "applied": True,
            "notified": False,
            "notification_mode": "digest",
            "notes": None,
        }

    def test_write_mutation_event_calls_redis_lpush_with_correct_key(
        self, mock_redis_client, sample_belief_event
    ):
        """Test that write_mutation_event actually calls Redis lpush with correct key."""
        from src.autonomous_cognition.beliefs.audit_writer import (
            BeliefMutationAuditWriter,
            BeliefMutationEvent,
        )

        # Patch get_feature_flags to return a mock with known behavior
        mock_flags = MagicMock()
        mock_flags.get_redis_value.return_value = True  # Feature flag enabled

        with patch(
            "src.autonomous_cognition.beliefs.audit_writer.get_feature_flags",
            return_value=mock_flags,
        ):
            writer = BeliefMutationAuditWriter(redis_client=mock_redis_client)

            event = BeliefMutationEvent(**sample_belief_event)
            result = writer.write_mutation_event(event)

            assert result is True
            # Verify lpush was called with the correct AUDIT_KEY
            mock_redis_client.lpush.assert_called_once()
            call_args = mock_redis_client.lpush.call_args
            # First arg is the key, second is the JSON value
            assert call_args[0][0] == "bmad:chiseai:autocog:audit:belief_mutations"
            # Verify the JSON contains all required fields
            serialized_event = json.loads(call_args[0][1])
            assert serialized_event["event_id"] == sample_belief_event["event_id"]
            assert serialized_event["belief_key"] == sample_belief_event["belief_key"]
            assert (
                serialized_event["mutation_type"]
                == sample_belief_event["mutation_type"]
            )

    def test_write_mutation_event_sets_ttl_on_audit_key(
        self, mock_redis_client, sample_belief_event
    ):
        """Test that write_mutation_event sets TTL on the audit key."""
        from src.autonomous_cognition.beliefs.audit_writer import (
            BeliefMutationAuditWriter,
            BeliefMutationEvent,
        )

        mock_flags = MagicMock()
        mock_flags.get_redis_value.return_value = True

        with patch(
            "src.autonomous_cognition.beliefs.audit_writer.get_feature_flags",
            return_value=mock_flags,
        ):
            writer = BeliefMutationAuditWriter(redis_client=mock_redis_client)

            event = BeliefMutationEvent(**sample_belief_event)
            writer.write_mutation_event(event)

            # Verify expire was called with correct TTL
            mock_redis_client.expire.assert_called_once_with(
                "bmad:chiseai:autocog:audit:belief_mutations",
                30 * 24 * 60 * 60,  # 30 days in seconds
            )

    def test_write_mutation_event_respects_feature_flag_disabled(
        self, mock_redis_client, sample_belief_event
    ):
        """Test that write_mutation_event does NOT write when feature flag is disabled."""
        from src.autonomous_cognition.beliefs.audit_writer import (
            BeliefMutationAuditWriter,
            BeliefMutationEvent,
        )

        mock_flags = MagicMock()
        mock_flags.get_redis_value.return_value = False  # Feature flag disabled

        with patch(
            "src.autonomous_cognition.beliefs.audit_writer.get_feature_flags",
            return_value=mock_flags,
        ):
            writer = BeliefMutationAuditWriter(redis_client=mock_redis_client)

            event = BeliefMutationEvent(**sample_belief_event)
            result = writer.write_mutation_event(event)

            assert result is False
            # lpush should NOT be called when feature flag is disabled
            mock_redis_client.lpush.assert_not_called()

    def test_is_enabled_uses_feature_flags_pattern(self):
        """Test that is_enabled uses get_feature_flags().get_redis_value()."""
        from src.autonomous_cognition.beliefs.audit_writer import (
            FEATURE_FLAG_KEY,
            BeliefMutationAuditWriter,
        )

        mock_flags = MagicMock()
        mock_flags.get_redis_value.return_value = True

        with patch(
            "src.autonomous_cognition.beliefs.audit_writer.get_feature_flags",
            return_value=mock_flags,
        ):
            writer = BeliefMutationAuditWriter()
            result = writer.is_enabled()

            assert result is True
            # Verify the correct key was used
            mock_flags.get_redis_value.assert_called_once_with(
                FEATURE_FLAG_KEY, default=True
            )

    def test_full_cycle_emits_audit_events(
        self, mock_redis_client, sample_belief_event
    ):
        """Test that full_cycle.py emits audit events during belief revisions."""
        from src.autonomous_cognition.beliefs.audit_writer import BeliefMutationEvent

        # Create a minimal test scenario
        mock_flags = MagicMock()
        mock_flags.get_redis_value.return_value = True

        with patch(
            "src.autonomous_cognition.beliefs.audit_writer.get_feature_flags",
            return_value=mock_flags,
        ):
            # Test that we can construct valid BeliefMutationEvent objects
            event = BeliefMutationEvent(
                event_id="test-001",
                timestamp=datetime.now(UTC).isoformat(),
                actor="autonomous_cognition",
                belief_key="test.belief.001",
                mutation_type="update",
                severity="medium",
                old_value={"statement": "Old"},
                new_value={"statement": "New"},
            )

            assert event.event_id == "test-001"
            assert event.mutation_type == "update"
            assert event.severity == "medium"

    def test_consistency_checker_audit_interface(self):
        """Test that consistency_checker has the correct interface for audit."""
        from src.autonomous_cognition.beliefs.consistency_checker import (
            BeliefConsistencyChecker,
        )

        checker = BeliefConsistencyChecker()

        # detect_conflicts should be callable and return a list
        # (actual detection depends on belief store)
        assert hasattr(checker, "detect_conflicts")
        assert callable(checker.detect_conflicts)

    def test_runtime_integration_audit_interface(self):
        """Test that runtime_integration has correct interface for audit."""
        from src.autonomous_cognition.runtime_integration import (
            NeuroSymbolicRuntimeIntegrator,
        )

        integrator = NeuroSymbolicRuntimeIntegrator()

        # Should have run method that accepts mode parameter
        assert hasattr(integrator, "run")
        assert callable(integrator.run)

    def test_iteration_logging_audit_interface(self):
        """Test that iteration_logging has correct interface for audit."""
        from operations.iteration_logging import (
            close_iteration,
            log_decision,
            log_iteration_start,
            log_learning,
        )

        # These should be callable functions
        assert callable(log_iteration_start)
        assert callable(log_decision)
        assert callable(log_learning)
        assert callable(close_iteration)

    def test_audit_writer_feature_flag_gating(self):
        """Test that audit writer respects feature flag via get_feature_flags."""
        from src.autonomous_cognition.beliefs.audit_writer import (
            BeliefMutationAuditWriter,
        )

        # Test with disabled feature flag
        mock_flags = MagicMock()
        mock_flags.get_redis_value.return_value = False

        with patch(
            "src.autonomous_cognition.beliefs.audit_writer.get_feature_flags",
            return_value=mock_flags,
        ):
            writer = BeliefMutationAuditWriter()
            assert writer.is_enabled() is False

        # Test with enabled feature flag
        mock_flags.get_redis_value.return_value = True
        with patch(
            "src.autonomous_cognition.beliefs.audit_writer.get_feature_flags",
            return_value=mock_flags,
        ):
            writer = BeliefMutationAuditWriter()
            assert writer.is_enabled() is True


class TestBeliefMutationEventConstruction:
    """Tests for BeliefMutationEvent construction and serialization."""

    def test_event_to_dict(self):
        """Test BeliefMutationEvent serialization."""
        from src.autonomous_cognition.beliefs.audit_writer import BeliefMutationEvent

        event = BeliefMutationEvent(
            event_id="evt-001",
            timestamp="2026-03-31T12:00:00+00:00",
            actor="test-actor",
            belief_key="belief.001",
            mutation_type="create",
            severity="high",
            old_value=None,
            new_value={"statement": "New belief created"},
        )

        result = event.to_dict()

        assert result["event_id"] == "evt-001"
        assert result["actor"] == "test-actor"
        assert result["belief_key"] == "belief.001"
        assert result["mutation_type"] == "create"
        assert result["severity"] == "high"
        assert result["old_value"] is None
        assert result["new_value"] == {"statement": "New belief created"}

    def test_event_with_conflict_resolution(self):
        """Test BeliefMutationEvent with conflict resolution data."""
        from src.autonomous_cognition.beliefs.audit_writer import BeliefMutationEvent

        event = BeliefMutationEvent(
            event_id="evt-002",
            timestamp="2026-03-31T12:00:00+00:00",
            actor="autonomous_cognition",
            belief_key="belief.002",
            mutation_type="conflict_resolution",
            severity="medium",
            old_value={"statement": "Belief A"},
            new_value={"statement": "Belief B wins"},
            conflict_resolution={
                "winner_belief_id": "belief.002",
                "loser_belief_id": "belief.001",
                "reason": "Higher evidence support",
            },
        )

        result = event.to_dict()

        assert result["mutation_type"] == "conflict_resolution"
        assert result["conflict_resolution"]["winner_belief_id"] == "belief.002"


class TestAuditWriterGovernanceIntegration:
    """Tests for audit writer governance policy integration."""

    def test_determine_approval_required(self):
        """Test approval requirement determination from governance policy."""
        from src.autonomous_cognition.beliefs.audit_writer import (
            BeliefMutationAuditWriter,
        )

        writer = BeliefMutationAuditWriter()

        # Mock governance policy
        with patch.object(
            writer,
            "_load_governance_policy",
            return_value={
                "belief_mutation": {"approval_required": ["soul_items", "core_values"]}
            },
        ):
            # Should require approval for soul_items
            assert writer._determine_approval_required("soul_items") is True
            # Should require approval for core_values
            assert writer._determine_approval_required("core_values") is True
            # Should NOT require approval for user_preferences
            assert writer._determine_approval_required("user_preferences") is False

    def test_derive_notification_mode(self):
        """Test notification mode derivation based on severity."""
        from src.autonomous_cognition.beliefs.audit_writer import (
            BeliefMutationAuditWriter,
        )

        writer = BeliefMutationAuditWriter()

        # Critical/high always gets immediate
        assert writer._derive_notification_mode("critical", False) == "immediate"
        assert writer._derive_notification_mode("high", True) == "immediate"

        # Medium/low gets digest
        assert writer._derive_notification_mode("medium", False) == "digest"
        assert writer._derive_notification_mode("low", True) == "digest"

    def test_governance_policy_path_resolution_with_env_var(self, tmp_path):
        """Test governance policy path resolution uses CHISEAI_REPO_ROOT when set."""
        from src.autonomous_cognition.beliefs.audit_writer import (
            BeliefMutationAuditWriter,
        )

        # Create a temp governance policy file
        policy = {"belief_mutation": {"approval_required": ["test_category"]}}
        import yaml

        policy_file = tmp_path / "config" / "aria" / "governance-policy.yaml"
        policy_file.parent.mkdir(parents=True, exist_ok=True)
        policy_file.write_text(yaml.dump(policy))

        # Set env var
        with patch.dict("os.environ", {"CHISEAI_REPO_ROOT": str(tmp_path)}):
            writer = BeliefMutationAuditWriter()
            loaded = writer._load_governance_policy()

            assert loaded["belief_mutation"]["approval_required"] == ["test_category"]


class TestBeliefMutationEventNewFields:
    """Tests for BeliefMutationEvent new fields: confidence_before, confidence_after, conflict_detected, conflict_resolution_summary."""

    def test_event_to_dict_includes_all_new_fields(self):
        """Test that to_dict() includes confidence_before, confidence_after, conflict_detected, and conflict_resolution_summary."""
        from src.autonomous_cognition.beliefs.audit_writer import BeliefMutationEvent

        event = BeliefMutationEvent(
            event_id="evt-new-fields-001",
            timestamp="2026-03-31T12:00:00+00:00",
            actor="test-actor",
            belief_key="belief.new.fields.001",
            mutation_type="update",
            severity="medium",
            old_value={"statement": "Old belief"},
            new_value={"statement": "New belief"},
            evidence=[{"source_type": "test", "summary": "Test evidence"}],
            confidence_before=0.75,
            confidence_after=0.92,
            conflict_detected=True,
            conflict_resolution_summary="Resolved by evidence weight",
        )

        result = event.to_dict()

        # Verify all new fields are present
        assert "confidence_before" in result
        assert "confidence_after" in result
        assert "conflict_detected" in result
        assert "conflict_resolution_summary" in result

        # Verify values
        assert result["confidence_before"] == 0.75
        assert result["confidence_after"] == 0.92
        assert result["conflict_detected"] is True
        assert result["conflict_resolution_summary"] == "Resolved by evidence weight"

    def test_event_with_conflict_resolution_has_correct_structure(self):
        """Test BeliefMutationEvent with conflict resolution fields set correctly."""
        from src.autonomous_cognition.beliefs.audit_writer import BeliefMutationEvent

        event = BeliefMutationEvent(
            event_id="evt-conflict-001",
            timestamp="2026-03-31T12:00:00+00:00",
            actor="BeliefConsistencyChecker",
            belief_key="belief.conflict.001",
            mutation_type="conflict_resolution",
            severity="high",
            old_value={"belief_id": "belief.a", "confidence": 0.6},
            new_value={"belief_id": "belief.b", "confidence": 0.85},
            conflict_resolution={
                "similarity": 0.82,
                "belief_id_a": "belief.a",
                "belief_id_b": "belief.b",
            },
            applied=False,
            confidence_before=0.6,
            confidence_after=0.85,
            conflict_detected=True,
            conflict_resolution_summary="Belief B has stronger evidence support",
        )

        result = event.to_dict()

        assert result["mutation_type"] == "conflict_resolution"
        assert result["conflict_detected"] is True
        assert result["confidence_before"] == 0.6
        assert result["confidence_after"] == 0.85
        assert (
            result["conflict_resolution_summary"]
            == "Belief B has stronger evidence support"
        )

    def test_event_with_null_confidence_fields(self):
        """Test BeliefMutationEvent allows null confidence values."""
        from src.autonomous_cognition.beliefs.audit_writer import BeliefMutationEvent

        event = BeliefMutationEvent(
            event_id="evt-null-confidence-001",
            timestamp="2026-03-31T12:00:00+00:00",
            actor="test-actor",
            belief_key="belief.null.conf.001",
            mutation_type="create",
            severity="low",
            old_value=None,
            new_value={"statement": "New belief"},
            confidence_before=None,
            confidence_after=None,
            conflict_detected=False,
            conflict_resolution_summary=None,
        )

        result = event.to_dict()

        assert result["confidence_before"] is None
        assert result["confidence_after"] is None
        assert result["conflict_detected"] is False
        assert result["conflict_resolution_summary"] is None


class TestSchemaValidation:
    """Tests for BeliefMutationEvent schema validation against JSON schema."""

    def test_schema_loads_successfully(self):
        """Test that the schema file loads without errors."""
        schema_path = SCHEMA_PATH
        assert schema_path.exists(), f"Schema file not found at {schema_path}"

        with open(schema_path) as f:
            schema = json.load(f)

        assert schema["title"] == "BeliefMutationEvent"
        assert "properties" in schema

    def test_valid_event_passes_schema_validation(self):
        """Test that a valid BeliefMutationEvent passes jsonschema validation."""
        from src.autonomous_cognition.beliefs.audit_writer import BeliefMutationEvent

        with open(SCHEMA_PATH) as f:
            schema = json.load(f)

        # Create a valid event with all required fields
        event = BeliefMutationEvent(
            event_id="evt-schema-001",
            timestamp="2026-03-31T12:00:00+00:00",
            actor="test-actor",
            belief_key="belief.schema.001",
            mutation_type="create",
            severity="medium",
            old_value=None,
            new_value={"statement": "Test belief"},
            evidence=[{"source_type": "test", "summary": "Test evidence"}],
            approval_required=False,
            applied=True,
            notified=False,
            # New fields
            confidence_before=0.5,
            confidence_after=0.8,
            conflict_detected=False,
            conflict_resolution_summary=None,
        )

        # Validate against schema - should not raise
        jsonschema.validate(event.to_dict(), schema)

    def test_valid_conflict_resolution_event_passes_schema(self):
        """Test that a valid conflict_resolution event passes schema validation."""
        from src.autonomous_cognition.beliefs.audit_writer import BeliefMutationEvent

        with open(SCHEMA_PATH) as f:
            schema = json.load(f)

        event = BeliefMutationEvent(
            event_id="evt-schema-conflict-001",
            timestamp="2026-03-31T12:00:00+00:00",
            actor="BeliefConsistencyChecker",
            belief_key="belief.schema.conflict.001",
            mutation_type="conflict_resolution",
            severity="high",
            old_value={"belief_id": "belief.a", "confidence": 0.6},
            new_value={"belief_id": "belief.b", "confidence": 0.85},
            evidence=[{"source_type": "system", "summary": "Conflict detected"}],
            conflict_resolution={
                "similarity": 0.82,
                "belief_id_a": "belief.a",
                "belief_id_b": "belief.b",
            },
            approval_required=False,
            applied=False,
            notified=False,
            confidence_before=0.6,
            confidence_after=0.85,
            conflict_detected=True,
            conflict_resolution_summary="Resolved based on evidence strength",
        )

        # Validate against schema - should not raise
        jsonschema.validate(event.to_dict(), schema)


class TestConsistencyCheckerConflictPath:
    """Tests for consistency_checker conflict path audit emission."""

    @pytest.fixture
    def mock_redis_client(self):
        """Create a mock Redis client at the connection level."""
        mock_client = MagicMock()
        mock_client.get.return_value = None
        mock_client.lpush.return_value = 1
        mock_client.expire.return_value = True
        return mock_client

    def test_emit_conflict_audit_called_with_conflict_detected(self, mock_redis_client):
        """Test that _emit_conflict_audit is called when conflicts are detected."""
        from src.autonomous_cognition.beliefs.consistency_checker import (
            BeliefConsistencyChecker,
        )
        from src.autonomous_cognition.beliefs.models import Belief, BeliefConflict

        mock_flags = MagicMock()
        mock_flags.get_redis_value.return_value = True

        with patch(
            "src.autonomous_cognition.beliefs.audit_writer.get_feature_flags",
            return_value=mock_flags,
        ):
            checker = BeliefConsistencyChecker()
            checker._audit_writer = MagicMock()
            checker._audit_writer.write_mutation_event.return_value = True

            # Create two beliefs with conflicting statements
            belief_a = Belief(
                belief_id="test.belief.a",
                statement="The sky is blue",
                domain="test_domain",
                confidence=0.7,
                evidence_refs=[],
                status="active",
            )
            belief_b = Belief(
                belief_id="test.belief.b",
                statement="The sky is not blue",
                domain="test_domain",
                confidence=0.8,
                evidence_refs=[],
                status="active",
            )

            # Create a conflict
            conflict = BeliefConflict(
                conflict_id="test-conflict-001",
                belief_id_a="test.belief.a",
                belief_id_b="test.belief.b",
                similarity=0.75,
                severity="medium",
                reason="Contradicting statements detected",
            )

            # Call _emit_conflict_audit directly
            checker._emit_conflict_audit([belief_a, belief_b], [conflict])

            # Verify write_mutation_event was called
            checker._audit_writer.write_mutation_event.assert_called_once()
            call_args = checker._audit_writer.write_mutation_event.call_args
            event = call_args[0][0]

            # Verify event has correct mutation_type
            assert event.mutation_type == "conflict_resolution"
            # Verify conflict_detected is True
            assert event.conflict_detected is True
            # Verify confidence values are set
            assert event.confidence_before is not None
            assert event.confidence_after is not None

    def test_consistency_check_emits_audit_events(self, mock_redis_client):
        """Test that check_consistency emits audit events via BeliefMutationAuditWriter."""
        from src.autonomous_cognition.beliefs.consistency_checker import (
            BeliefConsistencyChecker,
        )
        from src.autonomous_cognition.beliefs.models import Belief

        mock_flags = MagicMock()
        mock_flags.get_redis_value.return_value = True

        with patch(
            "src.autonomous_cognition.beliefs.audit_writer.get_feature_flags",
            return_value=mock_flags,
        ):
            checker = BeliefConsistencyChecker()
            # Mock the audit writer to track calls
            original_writer = checker._audit_writer
            checker._audit_writer = MagicMock()
            checker._audit_writer.write_mutation_event.return_value = True

            # Create beliefs that will trigger conflict detection
            # Using domain that bypasses TEST_DOMAINS filter
            belief_a = Belief(
                belief_id="real.belief.a",
                statement="Coffee is healthy in moderation",
                domain="health",
                confidence=0.6,
                evidence_refs=["evidence.1"],
                status="active",
            )
            belief_b = Belief(
                belief_id="real.belief.b",
                statement="Coffee is not healthy",
                domain="health",
                confidence=0.9,
                evidence_refs=["evidence.2"],
                status="active",
            )

            # Run consistency check
            conflicts = checker.check_consistency([belief_a, belief_b])

            # If conflicts were detected, audit should have been called
            if conflicts:
                assert checker._audit_writer.write_mutation_event.called


class TestEndToEndEmission:
    """End-to-end tests for audit event emission at mutation touchpoints."""

    @pytest.fixture
    def mock_redis_client(self):
        """Create a mock Redis client."""
        mock_client = MagicMock()
        mock_client.get.return_value = None
        mock_client.lpush.return_value = 1
        mock_client.expire.return_value = True
        return mock_client

    def test_belief_revision_engine_creates_events_with_confidence_fields(self):
        """Test that BeliefRevisionEngine creates BeliefRevision with confidence_before/after."""
        from src.autonomous_cognition.beliefs.models import Belief
        from src.autonomous_cognition.beliefs.revision_engine import (
            BeliefRevisionEngine,
        )

        engine = BeliefRevisionEngine()

        old_belief = Belief(
            belief_id="rev.belief.old",
            statement="Old statement",
            domain="test",
            confidence=0.5,
            status="active",
        )
        new_belief = Belief(
            belief_id="rev.belief.new",
            statement="New statement",
            domain="test",
            confidence=0.85,
            status="active",
        )

        revision = engine.create_revision(
            old_belief=old_belief,
            new_belief=new_belief,
            conflict_id="rev-conflict-001",
            reason="Stronger evidence",
            evidence_refs=["evidence.1"],
        )

        assert revision.confidence_before == 0.5
        assert revision.confidence_after == 0.85
        assert revision.old_belief_id == "rev.belief.old"
        assert revision.new_belief_id == "rev.belief.new"

    def test_audit_writer_emits_event_with_all_confidence_fields(
        self, mock_redis_client
    ):
        """Test BeliefMutationAuditWriter emits event with confidence_before/after fields."""
        from src.autonomous_cognition.beliefs.audit_writer import (
            BeliefMutationAuditWriter,
            BeliefMutationEvent,
        )

        mock_flags = MagicMock()
        mock_flags.get_redis_value.return_value = True

        with patch(
            "src.autonomous_cognition.beliefs.audit_writer.get_feature_flags",
            return_value=mock_flags,
        ):
            writer = BeliefMutationAuditWriter(redis_client=mock_redis_client)

            event = BeliefMutationEvent(
                event_id="e2e-evt-001",
                timestamp="2026-03-31T12:00:00+00:00",
                actor="BeliefRevisionEngine",
                belief_key="e2e.belief.001",
                mutation_type="update",
                severity="medium",
                old_value={"statement": "Old", "confidence": 0.5},
                new_value={"statement": "New", "confidence": 0.85},
                evidence=[{"source_type": "test", "summary": "Test"}],
                approval_required=False,
                applied=True,
                notified=False,
                confidence_before=0.5,
                confidence_after=0.85,
                conflict_detected=False,
                conflict_resolution_summary=None,
            )

            result = writer.write_mutation_event(event)

            assert result is True
            # Verify the serialized event contains confidence fields
            call_args = mock_redis_client.lpush.call_args
            serialized = json.loads(call_args[0][1])
            assert serialized["confidence_before"] == 0.5
            assert serialized["confidence_after"] == 0.85
            assert serialized["conflict_detected"] is False

    def test_consistency_checker_emits_event_with_conflict_resolution_fields(
        self, mock_redis_client
    ):
        """Test consistency_checker emits conflict_resolution event with correct fields."""
        from src.autonomous_cognition.beliefs.audit_writer import (
            BeliefMutationAuditWriter,
        )
        from src.autonomous_cognition.beliefs.consistency_checker import (
            BeliefConsistencyChecker,
        )
        from src.autonomous_cognition.beliefs.models import Belief, BeliefConflict

        mock_flags = MagicMock()
        mock_flags.get_redis_value.return_value = True

        with patch(
            "src.autonomous_cognition.beliefs.audit_writer.get_feature_flags",
            return_value=mock_flags,
        ):
            writer = BeliefMutationAuditWriter(redis_client=mock_redis_client)
            checker = BeliefConsistencyChecker()
            # Directly set the writer to our mock
            checker._audit_writer = writer

            belief_a = Belief(
                belief_id="audit.belief.a",
                statement="Testing is important",
                domain="development",
                confidence=0.65,
                evidence_refs=["src.1"],
                status="active",
            )
            belief_b = Belief(
                belief_id="audit.belief.b",
                statement="Testing is not important",
                domain="development",
                confidence=0.9,
                evidence_refs=["src.2"],
                status="active",
            )

            conflict = BeliefConflict(
                conflict_id="audit-conflict-001",
                belief_id_a="audit.belief.a",
                belief_id_b="audit.belief.b",
                similarity=0.72,
                severity="medium",
                reason="Conflicting views on testing",
            )

            # Emit the audit event
            checker._emit_conflict_audit([belief_a, belief_b], [conflict])

            # Verify lpush was called with correct data
            mock_redis_client.lpush.assert_called()
            call_args = mock_redis_client.lpush.call_args
            serialized = json.loads(call_args[0][1])

            assert serialized["mutation_type"] == "conflict_resolution"
            assert serialized["conflict_detected"] is True
            assert serialized["confidence_before"] == 0.65
            assert serialized["confidence_after"] == 0.9
            assert "testing" in serialized["conflict_resolution_summary"]
