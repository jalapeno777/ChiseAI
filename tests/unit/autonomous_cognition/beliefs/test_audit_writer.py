"""Tests for BeliefMutationAuditWriter."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml
from src.autonomous_cognition.beliefs.audit_writer import BeliefMutationAuditWriter


# Dataclass matching schema for testing
@dataclass
class BeliefMutationEvent:
    """BeliefMutationEvent matching schemas/aria/belief-mutation-event.schema.json."""

    event_id: str
    timestamp: str  # ISO format
    actor: str
    belief_key: str
    mutation_type: str  # create, update, deprecate, promote, merge, conflict_resolution
    severity: str  # low, medium, high, critical
    old_value: Any
    new_value: Any
    evidence: list[dict] = field(default_factory=list)
    conflict_resolution: dict | None = None
    approval_required: bool = False
    approval_reason: str | None = None
    applied: bool = False
    notified: bool = False
    notification_mode: str | None = None
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "actor": self.actor,
            "belief_key": self.belief_key,
            "mutation_type": self.mutation_type,
            "severity": self.severity,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "evidence": self.evidence,
            "conflict_resolution": self.conflict_resolution,
            "approval_required": self.approval_required,
            "approval_reason": self.approval_reason,
            "applied": self.applied,
            "notified": self.notified,
            "notification_mode": self.notification_mode,
            "notes": self.notes,
        }


class TestBeliefMutationAuditWriter:
    """Test suite for BeliefMutationAuditWriter."""

    @pytest.fixture
    def mock_redis_client(self):
        """Create a mock Redis client."""
        mock_client = MagicMock()
        mock_client.lpush.return_value = 1
        mock_client.expire.return_value = True
        return mock_client

    @pytest.fixture
    def mock_feature_flags(self):
        """Create a mock FeatureFlags instance."""
        mock_flags = MagicMock()
        mock_flags.get_redis_value.return_value = True  # Default: enabled
        return mock_flags

    @pytest.fixture
    def governance_policy_yaml(self):
        """Create a temporary governance policy YAML file."""
        policy = {
            "version": 1,
            "policy_id": "aria-governance-policy-v1",
            "belief_mutation": {
                "audit_required": True,
                "approval_required": [
                    "soul_items",
                    "core_values",
                    "prd_objectives",
                    "approval_gated_rules",
                ],
            },
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(policy, f)
            yield f.name
        os.unlink(f.name)

    @pytest.fixture
    def sample_event(self) -> BeliefMutationEvent:
        """Create a sample BeliefMutationEvent."""
        return BeliefMutationEvent(
            event_id="evt-001",
            timestamp=datetime.now(UTC).isoformat(),
            actor="test-agent",
            belief_key="soul_items.core.value.honesty",
            mutation_type="create",
            severity="high",
            old_value=None,
            new_value={"statement": "Honesty is the best policy"},
            evidence=[
                {
                    "source_type": "user_input",
                    "summary": "User stated honesty is important",
                }
            ],
            approval_required=False,
            applied=True,
            notified=False,
        )

    def test_audit_writer_is_enabled_returns_bool(self, mock_feature_flags):
        """Test is_enabled returns a boolean."""
        with patch(
            "src.autonomous_cognition.beliefs.audit_writer.get_feature_flags",
            return_value=mock_feature_flags,
        ):
            writer = BeliefMutationAuditWriter()
            result = writer.is_enabled()
            assert isinstance(result, bool)

    def test_audit_writer_is_enabled_respects_feature_flag(self, mock_redis_client):
        """Test is_enabled returns False when feature flag is disabled."""
        mock_flags = MagicMock()
        mock_flags.get_redis_value.return_value = False  # Feature flag disabled

        with patch(
            "src.autonomous_cognition.beliefs.audit_writer.get_feature_flags",
            return_value=mock_flags,
        ):
            writer = BeliefMutationAuditWriter(redis_client=mock_redis_client)
            result = writer.is_enabled()
            assert result is False

    def test_audit_writer_is_enabled_true_when_flag_set(self, mock_redis_client):
        """Test is_enabled returns True when feature flag is enabled."""
        mock_flags = MagicMock()
        mock_flags.get_redis_value.return_value = True  # Feature flag enabled

        with patch(
            "src.autonomous_cognition.beliefs.audit_writer.get_feature_flags",
            return_value=mock_flags,
        ):
            writer = BeliefMutationAuditWriter(redis_client=mock_redis_client)
            result = writer.is_enabled()
            assert result is True

    def test_audit_writer_write_mutation_event_success(
        self,
        mock_redis_client,
        mock_feature_flags,
        governance_policy_yaml,
        sample_event,
    ):
        """Test write_mutation_event successfully writes to Redis."""
        with patch(
            "src.autonomous_cognition.beliefs.audit_writer.get_feature_flags",
            return_value=mock_feature_flags,
        ):
            writer = BeliefMutationAuditWriter(
                redis_client=mock_redis_client,
                governance_policy_path=governance_policy_yaml,
            )
            result = writer.write_mutation_event(sample_event)
            assert result is True
            # Verify LPUSH was called
            mock_redis_client.lpush.assert_called_once()

    def test_audit_writer_write_mutation_event_when_disabled(
        self, mock_redis_client, governance_policy_yaml, sample_event
    ):
        """Test write_mutation_event returns False when disabled."""
        mock_flags = MagicMock()
        mock_flags.get_redis_value.return_value = False  # Feature flag disabled

        with patch(
            "src.autonomous_cognition.beliefs.audit_writer.get_feature_flags",
            return_value=mock_flags,
        ):
            writer = BeliefMutationAuditWriter(
                redis_client=mock_redis_client,
                governance_policy_path=governance_policy_yaml,
            )
            result = writer.write_mutation_event(sample_event)
            assert result is False
            # LPUSH should not be called when disabled
            mock_redis_client.lpush.assert_not_called()

    def test_audit_writer_derives_notification_mode_immediate(self):
        """Test notification_mode derivation for immediate (critical/high + approval)."""
        writer = BeliefMutationAuditWriter()

        # critical/high + approval_required=True => immediate
        mode = writer._derive_notification_mode("critical", True)
        assert mode == "immediate"

        mode = writer._derive_notification_mode("high", True)
        assert mode == "immediate"

    def test_audit_writer_derives_notification_mode_digest(self):
        """Test notification_mode derivation for digest (medium/low or no approval)."""
        writer = BeliefMutationAuditWriter()

        # medium/low + approval_required=True => digest
        mode = writer._derive_notification_mode("medium", True)
        assert mode == "digest"

        mode = writer._derive_notification_mode("low", True)
        assert mode == "digest"

        # medium/low + approval_required=False => digest
        mode = writer._derive_notification_mode("medium", False)
        assert mode == "digest"

        mode = writer._derive_notification_mode("low", False)
        assert mode == "digest"

    def test_audit_writer_derives_notification_mode_immediate_no_approval(
        self,
    ):
        """Test notification_mode derivation for critical/high without approval."""
        writer = BeliefMutationAuditWriter()

        # critical/high + approval_required=False => immediate
        mode = writer._derive_notification_mode("critical", False)
        assert mode == "immediate"

        mode = writer._derive_notification_mode("high", False)
        assert mode == "immediate"

    def test_audit_writer_approval_required_from_governance(
        self, governance_policy_yaml
    ):
        """Test _determine_approval_required reads from governance policy."""
        writer = BeliefMutationAuditWriter(
            governance_policy_path=governance_policy_yaml
        )

        # Categories requiring approval per governance policy
        assert writer._determine_approval_required("soul_items") is True
        assert writer._determine_approval_required("core_values") is True
        assert writer._determine_approval_required("prd_objectives") is True
        assert writer._determine_approval_required("approval_gated_rules") is True

        # Categories NOT requiring approval
        assert writer._determine_approval_required("user_preference_updates") is False
        assert writer._determine_approval_required("tool_preference_updates") is False

    def test_audit_writer_graceful_fallback_when_feature_flag_raises(self):
        """Test graceful fallback when get_feature_flags raises an exception."""
        mock_redis_client = MagicMock()
        mock_redis_client.lpush.return_value = 1
        mock_redis_client.expire.return_value = True

        with patch(
            "src.autonomous_cognition.beliefs.audit_writer.get_feature_flags",
            side_effect=Exception("Redis connection failed"),
        ):
            writer = BeliefMutationAuditWriter(redis_client=mock_redis_client)
            # Should return True (fail-safe) when get_feature_flags fails
            result = writer.is_enabled()
            assert result is True

    def test_audit_writer_sets_ttl_on_lpush(
        self, mock_redis_client, mock_feature_flags, governance_policy_yaml
    ):
        """Test that LPUSH uses TTL for Redis entries."""
        with patch(
            "src.autonomous_cognition.beliefs.audit_writer.get_feature_flags",
            return_value=mock_feature_flags,
        ):
            writer = BeliefMutationAuditWriter(
                redis_client=mock_redis_client,
                governance_policy_path=governance_policy_yaml,
            )

            event = BeliefMutationEvent(
                event_id="evt-003",
                timestamp=datetime.now(UTC).isoformat(),
                actor="test",
                belief_key="test.key",
                mutation_type="create",
                severity="medium",
                old_value=None,
                new_value={"test": "data"},
            )
            writer.write_mutation_event(event)

            # Verify lpush was called with correct key
            call_args = mock_redis_client.lpush.call_args
            assert "bmad:chiseai:autocog:audit:belief_mutations" in str(call_args)
            # Verify TTL was set
            mock_redis_client.expire.assert_called_once_with(
                "bmad:chiseai:autocog:audit:belief_mutations",
                30 * 24 * 60 * 60,
            )

    def test_audit_writer_loads_governance_policy(self, governance_policy_yaml):
        """Test _load_governance_policy loads YAML correctly."""
        writer = BeliefMutationAuditWriter(
            governance_policy_path=governance_policy_yaml
        )
        policy = writer._load_governance_policy()

        assert policy is not None
        assert policy["version"] == 1
        assert policy["policy_id"] == "aria-governance-policy-v1"
        assert "belief_mutation" in policy
        assert "approval_required" in policy["belief_mutation"]

    def test_governance_prefix_is_correct(self):
        """Test that GOVERNANCE_PREFIX is used for feature flag key."""
        from src.autonomous_cognition.beliefs.audit_writer import (
            FEATURE_FLAG_KEY,
            GOVERNANCE_PREFIX,
        )

        # Verify the key pattern matches the required pattern
        assert GOVERNANCE_PREFIX == "chise:feature_flags:governance"
        assert (
            FEATURE_FLAG_KEY
            == "chise:feature_flags:governance:belief_mutation_audit_enabled"
        )

    def test_write_mutation_event_serializes_event_correctly(
        self, mock_redis_client, mock_feature_flags, governance_policy_yaml
    ):
        """Test that write_mutation_event serializes the event to JSON correctly."""
        with patch(
            "src.autonomous_cognition.beliefs.audit_writer.get_feature_flags",
            return_value=mock_feature_flags,
        ):
            writer = BeliefMutationAuditWriter(
                redis_client=mock_redis_client,
                governance_policy_path=governance_policy_yaml,
            )

            event = BeliefMutationEvent(
                event_id="evt-004",
                timestamp="2026-03-31T12:00:00+00:00",
                actor="test-actor",
                belief_key="test.belief.004",
                mutation_type="update",
                severity="high",
                old_value={"statement": "Old"},
                new_value={"statement": "New"},
                evidence=[{"source_type": "test", "summary": "Test evidence"}],
            )
            writer.write_mutation_event(event)

            # Verify the JSON that was passed to lpush
            call_args = mock_redis_client.lpush.call_args
            json_event = json.loads(call_args[0][1])
            assert json_event["event_id"] == "evt-004"
            assert json_event["belief_key"] == "test.belief.004"
            assert json_event["mutation_type"] == "update"
            assert json_event["severity"] == "high"
            assert json_event["old_value"] == {"statement": "Old"}
            assert json_event["new_value"] == {"statement": "New"}
            assert len(json_event["evidence"]) == 1
