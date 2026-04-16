"""
Tests for Human Gate module.

This module tests:
- COMPLEX PR detection and classification
- Discord notification sending
- Redis approval recording
- Reminder scheduling
- Emergency override flow
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add paths for imports
sys.path.insert(
    0, str(Path(__file__).parent.parent.parent / "scripts" / "pr_lifecycle")
)
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from human_gate import (
    ApprovalRecord,
    ApprovalStatus,
    HumanGate,
    HumanGateResult,
)

from autonomous_git.path_analyzer import RiskLevel


class TestApprovalStatus:
    """Tests for ApprovalStatus enum."""

    def test_status_values(self):
        """Test that all status values are correct."""
        assert ApprovalStatus.PENDING.value == "pending"
        assert ApprovalStatus.APPROVED.value == "approved"
        assert ApprovalStatus.REJECTED.value == "rejected"
        assert ApprovalStatus.CHANGES_REQUESTED.value == "changes_requested"
        assert ApprovalStatus.EMERGENCY_OVERRIDE.value == "emergency_override"
        assert ApprovalStatus.EXPIRED.value == "expired"


class TestApprovalRecord:
    """Tests for ApprovalRecord dataclass."""

    def test_record_creation(self):
        """Test creating an approval record."""
        record = ApprovalRecord(
            pr_number=123,
            status=ApprovalStatus.APPROVED,
            approver="reviewer1",
            reason="Looks good",
        )

        assert record.pr_number == 123
        assert record.status == ApprovalStatus.APPROVED
        assert record.approver == "reviewer1"
        assert record.reason == "Looks good"
        assert record.timestamp is not None
        assert record.emergency_justification is None
        assert record.post_hoc_review_required is False

    def test_record_serialization(self):
        """Test ApprovalRecord serialization."""
        original = ApprovalRecord(
            pr_number=123,
            status=ApprovalStatus.APPROVED,
            approver="reviewer1",
            timestamp=datetime.now(UTC),
            reason="Looks good",
            emergency_justification=None,
            post_hoc_review_required=False,
        )

        # Serialize
        data = original.to_dict()

        # Deserialize
        restored = ApprovalRecord.from_dict(data)

        assert restored.pr_number == original.pr_number
        assert restored.status == original.status
        assert restored.approver == original.approver
        assert restored.reason == original.reason
        assert restored.post_hoc_review_required == original.post_hoc_review_required

    def test_record_serialization_with_emergency(self):
        """Test ApprovalRecord serialization with emergency override."""
        original = ApprovalRecord(
            pr_number=456,
            status=ApprovalStatus.EMERGENCY_OVERRIDE,
            approver="admin1",
            timestamp=datetime.now(UTC),
            reason="Emergency fix",
            emergency_justification="Critical security vulnerability",
            post_hoc_review_required=True,
        )

        # Serialize
        data = original.to_dict()

        # Verify emergency fields
        assert data["emergency_justification"] == "Critical security vulnerability"
        assert data["post_hoc_review_required"] is True

        # Deserialize
        restored = ApprovalRecord.from_dict(data)

        assert restored.emergency_justification == "Critical security vulnerability"
        assert restored.post_hoc_review_required is True


class TestHumanGateResult:
    """Tests for HumanGateResult dataclass."""

    def test_result_creation(self):
        """Test creating a result."""
        result = HumanGateResult(
            pr_number=123,
            is_complex=True,
            risk_level=RiskLevel.COMPLEX,
            confidence=0.95,
            files_analyzed=["file1.py", "file2.py"],
            approval_status=ApprovalStatus.PENDING,
            requires_human_approval=True,
            can_merge=False,
            reasoning="COMPLEX classification requires human approval",
        )

        assert result.pr_number == 123
        assert result.is_complex is True
        assert result.confidence == 0.95
        assert result.requires_human_approval is True
        assert result.can_merge is False

    def test_result_serialization(self):
        """Test HumanGateResult serialization."""
        record = ApprovalRecord(
            pr_number=123,
            status=ApprovalStatus.APPROVED,
            approver="reviewer1",
            timestamp=datetime.now(UTC),
        )

        result = HumanGateResult(
            pr_number=123,
            is_complex=True,
            risk_level=RiskLevel.COMPLEX,
            confidence=0.95,
            files_analyzed=["file1.py"],
            approval_status=ApprovalStatus.APPROVED,
            approval_record=record,
            requires_human_approval=True,
            can_merge=True,
            reasoning="Approved by human",
            discord_notified=True,
            reminder_count=2,
        )

        # Serialize
        data = result.to_dict()

        # Verify structure
        assert data["pr_number"] == 123
        assert data["is_complex"] is True
        assert data["can_merge"] is True
        assert data["discord_notified"] is True
        assert data["reminder_count"] == 2
        assert data["approval_record"] is not None


class TestHumanGateInitialization:
    """Tests for HumanGate initialization."""

    def test_default_initialization(self):
        """Test initialization with default parameters."""
        with patch.dict(os.environ, {}, clear=True):
            gate = HumanGate()

            assert gate.redis is None
            assert gate.discord_webhook_url is None
            assert gate.emergency_approvers == set()
            assert gate.approval_timeout_hours == 48
            assert gate.reminder_interval_hours == 4
            assert gate.dry_run is False

    def test_custom_initialization(self):
        """Test initialization with custom parameters."""
        mock_redis = MagicMock()
        gate = HumanGate(
            redis_client=mock_redis,
            discord_webhook_url="https://discord.com/webhook",
            emergency_approvers=["admin1", "admin2"],
            approval_timeout_hours=24,
            reminder_interval_hours=2,
            dry_run=True,
        )

        assert gate.redis == mock_redis
        assert gate.discord_webhook_url == "https://discord.com/webhook"
        assert gate.emergency_approvers == {"admin1", "admin2"}
        assert gate.approval_timeout_hours == 24
        assert gate.reminder_interval_hours == 2
        assert gate.dry_run is True

    def test_env_webhook_url(self):
        """Test that webhook URL can be set from environment."""
        with patch.dict(
            os.environ, {"DISCORD_PR_REVIEWS_WEBHOOK": "https://env.webhook.url"}
        ):
            gate = HumanGate()
            assert gate.discord_webhook_url == "https://env.webhook.url"


class TestComplexClassification:
    """Tests for COMPLEX PR classification."""

    @pytest.fixture
    def gate(self):
        """Create a HumanGate instance."""
        return HumanGate(dry_run=True)

    def test_is_complex_classification_safe_files(self, gate):
        """Test that safe files are not classified as COMPLEX."""
        safe_files = [
            "docs/README.md",
            "tests/test_foo.py",
            "src/utils/helpers.py",
        ]

        is_complex, risk_level, confidence = gate._is_complex_classification(safe_files)

        # These files should not be COMPLEX
        assert not is_complex or risk_level != RiskLevel.COMPLEX
        assert confidence > 0

    def test_is_complex_classification_complex_files(self, gate):
        """Test that complex files are classified as COMPLEX."""
        complex_files = [
            "infrastructure/terraform/main.tf",
            ".woodpecker.yml",
            "src/execution/trade_executor.py",
        ]

        is_complex, risk_level, confidence = gate._is_complex_classification(
            complex_files
        )

        # These files should be COMPLEX
        assert is_complex or risk_level == RiskLevel.COMPLEX
        assert confidence > 0

    def test_is_complex_classification_empty_list(self, gate):
        """Test classification with empty file list."""
        is_complex, risk_level, confidence = gate._is_complex_classification([])

        # Empty list should default to SAFE
        assert risk_level == RiskLevel.SAFE


class TestApprovalStatusChecking:
    """Tests for approval status checking."""

    @pytest.fixture
    def gate(self):
        """Create a HumanGate instance."""
        return HumanGate(dry_run=True)

    @pytest.mark.asyncio
    async def test_get_approval_status_pending_no_redis(self, gate):
        """Test getting approval status when no Redis and no cache."""
        status, record = await gate._get_approval_status(999)

        assert status == ApprovalStatus.PENDING
        assert record is None

    @pytest.mark.asyncio
    async def test_get_approval_status_from_cache(self, gate):
        """Test getting approval status from cache."""
        # Pre-populate cache
        record = ApprovalRecord(
            pr_number=123,
            status=ApprovalStatus.APPROVED,
            approver="reviewer1",
            timestamp=datetime.now(UTC),
        )
        gate._approval_cache[123] = record

        status, retrieved_record = await gate._get_approval_status(123)

        assert status == ApprovalStatus.APPROVED
        assert retrieved_record == record

    @pytest.mark.asyncio
    async def test_get_approval_status_expired(self, gate):
        """Test that expired approvals are detected."""
        # Pre-populate cache with old approval
        old_record = ApprovalRecord(
            pr_number=123,
            status=ApprovalStatus.APPROVED,
            approver="reviewer1",
            timestamp=datetime.now(UTC) - timedelta(hours=49),
        )
        gate._approval_cache[123] = old_record

        status, record = await gate._get_approval_status(123)

        assert status == ApprovalStatus.EXPIRED
        assert record == old_record


class TestCanMerge:
    """Tests for merge eligibility."""

    @pytest.fixture
    def gate(self):
        """Create a HumanGate instance."""
        return HumanGate(dry_run=True)

    def test_can_merge_non_complex(self, gate):
        """Test that non-COMPLEX PRs can merge."""
        can_merge = gate._can_merge(
            is_complex=False,
            approval_status=ApprovalStatus.PENDING,
        )

        assert can_merge is True

    def test_can_merge_complex_pending(self, gate):
        """Test that COMPLEX PRs with pending approval cannot merge."""
        can_merge = gate._can_merge(
            is_complex=True,
            approval_status=ApprovalStatus.PENDING,
        )

        assert can_merge is False

    def test_can_merge_complex_approved(self, gate):
        """Test that COMPLEX PRs with approval can merge."""
        can_merge = gate._can_merge(
            is_complex=True,
            approval_status=ApprovalStatus.APPROVED,
        )

        assert can_merge is True

    def test_can_merge_complex_emergency(self, gate):
        """Test that COMPLEX PRs with emergency override can merge."""
        can_merge = gate._can_merge(
            is_complex=True,
            approval_status=ApprovalStatus.EMERGENCY_OVERRIDE,
        )

        assert can_merge is True

    def test_can_merge_complex_rejected(self, gate):
        """Test that COMPLEX PRs with rejection cannot merge."""
        can_merge = gate._can_merge(
            is_complex=True,
            approval_status=ApprovalStatus.REJECTED,
        )

        assert can_merge is False


class TestApprovalExpiration:
    """Tests for approval expiration."""

    @pytest.fixture
    def gate(self):
        """Create a HumanGate instance."""
        return HumanGate(dry_run=True, approval_timeout_hours=48)

    def test_approval_not_expired(self, gate):
        """Test that recent approvals are not expired."""
        recent_record = ApprovalRecord(
            pr_number=123,
            status=ApprovalStatus.APPROVED,
            approver="reviewer1",
            timestamp=datetime.now(UTC),
        )
        assert not gate._is_approval_expired(recent_record)

    def test_approval_expired(self, gate):
        """Test that old approvals are expired."""
        old_record = ApprovalRecord(
            pr_number=123,
            status=ApprovalStatus.APPROVED,
            approver="reviewer1",
            timestamp=datetime.now(UTC) - timedelta(hours=49),
        )
        assert gate._is_approval_expired(old_record)

    def test_emergency_not_expired(self, gate):
        """Test that emergency overrides can also expire."""
        old_emergency = ApprovalRecord(
            pr_number=123,
            status=ApprovalStatus.EMERGENCY_OVERRIDE,
            approver="admin1",
            timestamp=datetime.now(UTC) - timedelta(hours=49),
        )
        assert gate._is_approval_expired(old_emergency)

    def test_pending_not_expired(self, gate):
        """Test that pending status doesn't expire."""
        pending_record = ApprovalRecord(
            pr_number=123,
            status=ApprovalStatus.PENDING,
            approver=None,
            timestamp=datetime.now(UTC) - timedelta(hours=100),
        )
        assert not gate._is_approval_expired(pending_record)


class TestRecordingApprovals:
    """Tests for recording approvals."""

    @pytest.fixture
    def gate(self):
        """Create a HumanGate instance."""
        return HumanGate(dry_run=True)

    @pytest.mark.asyncio
    async def test_record_approval(self, gate):
        """Test recording a human approval."""
        record = await gate.record_approval(
            pr_number=123,
            approver="reviewer1",
            reason="Looks good",
        )

        assert record.pr_number == 123
        assert record.status == ApprovalStatus.APPROVED
        assert record.approver == "reviewer1"
        assert record.reason == "Looks good"
        assert record.timestamp is not None

    @pytest.mark.asyncio
    async def test_record_rejection(self, gate):
        """Test recording a human rejection."""
        record = await gate.record_rejection(
            pr_number=123,
            reviewer="reviewer1",
            reason="Needs more tests",
        )

        assert record.pr_number == 123
        assert record.status == ApprovalStatus.REJECTED
        assert record.approver == "reviewer1"
        assert record.reason == "Needs more tests"

    @pytest.mark.asyncio
    async def test_record_changes_requested(self, gate):
        """Test recording changes requested."""
        record = await gate.record_changes_requested(
            pr_number=123,
            reviewer="reviewer1",
            comments="Please fix the security issue",
        )

        assert record.pr_number == 123
        assert record.status == ApprovalStatus.CHANGES_REQUESTED
        assert record.approver == "reviewer1"
        assert record.reason == "Please fix the security issue"


class TestEmergencyOverride:
    """Tests for emergency override functionality."""

    @pytest.fixture
    def gate(self):
        """Create a HumanGate instance with emergency approvers."""
        return HumanGate(
            dry_run=True,
            emergency_approvers=["admin1", "admin2"],
        )

    @pytest.mark.asyncio
    async def test_emergency_override_authorized(self, gate):
        """Test emergency override with authorized user."""
        record = await gate.emergency_override(
            pr_number=123,
            approver="admin1",
            justification="Critical security fix",
        )

        assert record.pr_number == 123
        assert record.status == ApprovalStatus.EMERGENCY_OVERRIDE
        assert record.approver == "admin1"
        assert record.emergency_justification == "Critical security fix"
        assert record.post_hoc_review_required is True

    @pytest.mark.asyncio
    async def test_emergency_override_unauthorized(self, gate):
        """Test emergency override with unauthorized user."""
        with pytest.raises(ValueError) as exc_info:
            await gate.emergency_override(
                pr_number=123,
                approver="unauthorized_user",
                justification="Critical fix",
            )

        assert "not authorized" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_emergency_override_no_approvers_configured(self):
        """Test emergency override when no approvers configured.

        When no emergency approvers are configured, the check is bypassed
        (empty set means no restriction).
        """
        gate = HumanGate(dry_run=True, emergency_approvers=[])

        # When no approvers configured, any user can perform emergency override
        record = await gate.emergency_override(
            pr_number=123,
            approver="any_user",
            justification="Critical fix",
        )

        assert record.status == ApprovalStatus.EMERGENCY_OVERRIDE
        assert record.approver == "any_user"


class TestRedisIntegration:
    """Tests for Redis integration."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        redis = MagicMock()
        redis.get.return_value = None
        return redis

    @pytest.fixture
    def gate_with_redis(self, mock_redis):
        """Create a HumanGate instance with mock Redis."""
        return HumanGate(redis_client=mock_redis, dry_run=True)

    @pytest.mark.asyncio
    async def test_store_approval_state_in_redis(self, gate_with_redis, mock_redis):
        """Test storing approval state in Redis."""
        await gate_with_redis._store_approval_state(
            pr_number=123,
            status=ApprovalStatus.APPROVED,
            approver="reviewer1",
            reason="Looks good",
        )

        # Verify Redis calls
        assert mock_redis.set.called
        calls = mock_redis.set.call_args_list

        # Should set status, timestamp, and reviewer
        keys_set = [call[0][0] for call in calls]
        assert any("status" in k for k in keys_set)
        assert any("timestamp" in k for k in keys_set)
        assert any("reviewer" in k for k in keys_set)

    @pytest.mark.asyncio
    async def test_store_emergency_override_in_redis(self, gate_with_redis, mock_redis):
        """Test storing emergency override in Redis."""
        await gate_with_redis._store_approval_state(
            pr_number=123,
            status=ApprovalStatus.EMERGENCY_OVERRIDE,
            approver="admin1",
            reason="Emergency fix",
            emergency_justification="Critical security issue",
        )

        # Verify emergency key is set
        keys_set = [call[0][0] for call in mock_redis.set.call_args_list]
        assert any("emergency_override" in k for k in keys_set)

    @pytest.mark.asyncio
    async def test_get_reminder_count_from_redis(self, gate_with_redis, mock_redis):
        """Test getting reminder count from Redis."""
        mock_redis.get.return_value = b"3"

        count = await gate_with_redis._get_reminder_count(123)

        assert count == 3
        mock_redis.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_reminder_count_no_redis(self):
        """Test getting reminder count when no Redis."""
        gate = HumanGate(redis_client=None, dry_run=True)

        count = await gate._get_reminder_count(123)

        assert count == 0

    @pytest.mark.asyncio
    async def test_clear_approval_state(self, gate_with_redis, mock_redis):
        """Test clearing approval state."""
        # Pre-populate cache
        gate_with_redis._approval_cache[123] = MagicMock()

        result = await gate_with_redis.clear_approval_state(123)

        assert result is True
        assert 123 not in gate_with_redis._approval_cache
        assert mock_redis.delete.called


class TestDiscordNotifications:
    """Tests for Discord notification functionality."""

    @pytest.fixture
    def gate(self):
        """Create a HumanGate instance."""
        return HumanGate(
            dry_run=True,
            discord_webhook_url="https://discord.com/webhook",
        )

    @pytest.mark.asyncio
    async def test_send_discord_notification_dry_run(self, gate):
        """Test that dry run mode returns True without sending."""
        result = await gate._send_discord_notification(
            pr_number=123,
            pr_title="Test PR",
            pr_author="developer1",
            pr_url="https://example.com/pr/123",
            files=["file1.py", "file2.py"],
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_send_discord_notification_no_webhook(self):
        """Test that missing webhook returns False."""
        with patch.dict(os.environ, {}, clear=True):
            gate = HumanGate(dry_run=False, discord_webhook_url=None)

            result = await gate._send_discord_notification(
                pr_number=123,
                pr_title="Test PR",
                pr_author="developer1",
                pr_url="https://example.com/pr/123",
                files=["file1.py"],
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_send_reminder(self, gate):
        """Test sending a reminder."""
        # Pre-populate cache with pending status
        gate._approval_cache[123] = ApprovalRecord(
            pr_number=123,
            status=ApprovalStatus.PENDING,
            timestamp=datetime.now(UTC),
        )

        result = await gate.send_reminder(123)

        # Should return True in dry run mode
        assert result is True


class TestRequestApproval:
    """Tests for request_approval method."""

    @pytest.fixture
    def gate(self):
        """Create a HumanGate instance."""
        return HumanGate(dry_run=True)

    @pytest.mark.asyncio
    async def test_request_approval_success(self, gate):
        """Test successful approval request."""
        result = await gate.request_approval(
            pr_number=123,
            pr_title="Test PR",
            pr_author="developer1",
            pr_url="https://example.com/pr/123",
            files=["file1.py", "file2.py"],
            gitreviewbot_summary="Summary here",
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_request_approval_stores_pending_state(self, gate):
        """Test that request_approval stores pending state."""
        await gate.request_approval(
            pr_number=123,
            pr_title="Test PR",
            pr_author="developer1",
            pr_url="https://example.com/pr/123",
            files=["file1.py"],
        )

        # Check that pending status was stored in cache
        assert 123 in gate._approval_cache
        assert gate._approval_cache[123].status == ApprovalStatus.PENDING


class TestRedisKeyPatterns:
    """Tests for Redis key patterns."""

    def test_redis_key_patterns(self):
        """Test that Redis key patterns are correct."""
        gate = HumanGate()

        pr_number = 123

        status_key = gate._get_redis_key(gate.REDIS_STATUS_KEY, pr_number)
        assert status_key == "bmad:chiseai:pr:human_gate:123:status"

        reviewer_key = gate._get_redis_key(gate.REDIS_REVIEWER_KEY, pr_number)
        assert reviewer_key == "bmad:chiseai:pr:human_gate:123:reviewer"

        timestamp_key = gate._get_redis_key(gate.REDIS_TIMESTAMP_KEY, pr_number)
        assert timestamp_key == "bmad:chiseai:pr:human_gate:123:timestamp"

        emergency_key = gate._get_redis_key(gate.REDIS_EMERGENCY_KEY, pr_number)
        assert emergency_key == "bmad:chiseai:pr:human_gate:123:emergency_override"


class TestBuildReasoning:
    """Tests for reasoning message generation."""

    @pytest.fixture
    def gate(self):
        """Create a HumanGate instance."""
        return HumanGate(dry_run=True)

    def test_build_reasoning_complex_pending(self, gate):
        """Test reasoning for complex pending PR."""
        reasoning = gate._build_reasoning(
            is_complex=True,
            risk_level=RiskLevel.COMPLEX,
            approval_status=ApprovalStatus.PENDING,
        )

        assert "COMPLEX" in reasoning
        assert "human approval" in reasoning
        assert "pending" in reasoning.lower()

    def test_build_reasoning_complex_approved(self, gate):
        """Test reasoning for complex approved PR."""
        reasoning = gate._build_reasoning(
            is_complex=True,
            risk_level=RiskLevel.COMPLEX,
            approval_status=ApprovalStatus.APPROVED,
        )

        assert "COMPLEX" in reasoning
        assert "approved" in reasoning.lower()

    def test_build_reasoning_non_complex(self, gate):
        """Test reasoning for non-complex PR."""
        reasoning = gate._build_reasoning(
            is_complex=False,
            risk_level=RiskLevel.SAFE,
            approval_status=ApprovalStatus.PENDING,
        )

        assert "Not classified as COMPLEX" in reasoning
        assert "no human approval required" in reasoning

    def test_build_reasoning_expired(self, gate):
        """Test reasoning for expired approval."""
        reasoning = gate._build_reasoning(
            is_complex=True,
            risk_level=RiskLevel.COMPLEX,
            approval_status=ApprovalStatus.EXPIRED,
        )

        assert "expired" in reasoning.lower()
        assert "48h" in reasoning  # Default timeout


class TestIntegration:
    """Integration tests for the complete workflow."""

    @pytest.mark.asyncio
    async def test_full_workflow_simulation(self):
        """Simulate a complete workflow from detection to approval."""
        gate = HumanGate(
            dry_run=True,
            emergency_approvers=["admin"],
        )

        # Test classification
        complex_files = [
            "infrastructure/terraform/main.tf",
            "src/execution/critical.py",
        ]

        is_complex, risk_level, confidence = gate._is_complex_classification(
            complex_files
        )

        # COMPLEX files should be detected
        assert is_complex or risk_level == RiskLevel.COMPLEX

        # Record approval
        record = await gate.record_approval(
            pr_number=999,
            approver="reviewer1",
            reason="Integration test approval",
        )

        assert record.status == ApprovalStatus.APPROVED

        # Verify cache
        assert 999 in gate._approval_cache

    @pytest.mark.asyncio
    async def test_emergency_override_workflow(self):
        """Test emergency override workflow."""
        gate = HumanGate(
            dry_run=True,
            emergency_approvers=["admin1"],
        )

        # Apply emergency override
        record = await gate.emergency_override(
            pr_number=123,
            approver="admin1",
            justification="Critical security vulnerability",
        )

        assert record.status == ApprovalStatus.EMERGENCY_OVERRIDE
        assert record.post_hoc_review_required is True

        # Verify merge eligibility
        can_merge = gate._can_merge(
            is_complex=True,
            approval_status=ApprovalStatus.EMERGENCY_OVERRIDE,
        )
        assert can_merge is True

    @pytest.mark.asyncio
    async def test_rejection_workflow(self):
        """Test rejection workflow."""
        gate = HumanGate(dry_run=True)

        # Record rejection
        record = await gate.record_rejection(
            pr_number=123,
            reviewer="reviewer1",
            reason="Security concerns",
        )

        assert record.status == ApprovalStatus.REJECTED

        # Verify merge eligibility
        can_merge = gate._can_merge(
            is_complex=True,
            approval_status=ApprovalStatus.REJECTED,
        )
        assert can_merge is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
