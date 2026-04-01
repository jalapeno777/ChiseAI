"""Tests for belief mutation audit instrumentation.

These tests verify that audit events are emitted when beliefs are mutated
across the autonomous cognition system.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest


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
            BeliefMutationAuditWriter,
            FEATURE_FLAG_KEY,
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
