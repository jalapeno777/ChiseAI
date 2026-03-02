"""
Tests for Complex Path Gate and Human Approval Workflow.

This module tests:
- COMPLEX classification detection
- Approval workflow
- Discord notification
- Emergency override
"""

from __future__ import annotations

import os

# Add paths for imports
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(
    0, str(Path(__file__).parent.parent.parent / "scripts" / "pr_lifecycle")
)
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from complex_path_gate import (
    ApprovalRecord,
    ApprovalStatus,
    ComplexPathCheckResult,
    ComplexPathGate,
)
from human_approval_workflow import (
    HumanApprovalWorkflow,
    WorkflowConfig,
    WorkflowResult,
)

from autonomous_git.path_analyzer import RiskLevel


class TestComplexPathGate:
    """Tests for ComplexPathGate class."""

    @pytest.fixture
    def temp_audit_log(self):
        """Create a temporary audit log file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            path = f.name
        yield path
        os.unlink(path)

    @pytest.fixture
    def gate(self, temp_audit_log):
        """Create a ComplexPathGate with temp audit log."""
        return ComplexPathGate(
            audit_log_path=temp_audit_log,
            emergency_approvers=["admin1", "admin2"],
            approval_timeout_hours=48,
        )

    def test_is_complex_classification_safe_files(self, gate):
        """Test that safe files are not classified as COMPLEX."""
        safe_files = [
            "docs/README.md",
            "tests/test_foo.py",
            "src/utils/helpers.py",
        ]

        is_complex, risk_level, confidence = gate.is_complex_classification(safe_files)

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

        is_complex, risk_level, confidence = gate.is_complex_classification(
            complex_files
        )

        # These files should be COMPLEX
        assert is_complex or risk_level == RiskLevel.COMPLEX
        assert confidence > 0

    def test_is_complex_classification_empty_list(self, gate):
        """Test classification with empty file list."""
        is_complex, risk_level, confidence = gate.is_complex_classification([])

        # Empty list should default to SAFE
        assert risk_level == RiskLevel.SAFE

    @pytest.mark.asyncio
    async def test_check_human_approval_pending(self, gate):
        """Test checking approval when none exists."""
        status, record = await gate._check_human_approval(999)

        assert status == ApprovalStatus.PENDING
        assert record is None

    @pytest.mark.asyncio
    async def test_record_human_approval(self, gate):
        """Test recording a human approval."""
        record = await gate.record_human_approval(
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
    async def test_record_human_rejection(self, gate):
        """Test recording a human rejection."""
        record = await gate.record_human_rejection(
            pr_number=123,
            approver="reviewer1",
            reason="Needs more tests",
        )

        assert record.pr_number == 123
        assert record.status == ApprovalStatus.REJECTED
        assert record.approver == "reviewer1"
        assert record.reason == "Needs more tests"

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

    def test_can_merge_non_complex(self, gate):
        """Test that non-COMPLEX PRs can merge."""
        can_merge = gate._can_merge(
            is_complex=False,
            approval_status=ApprovalStatus.PENDING,
            gitreviewbot_completed=True,
        )

        assert can_merge is True

    def test_can_merge_complex_pending(self, gate):
        """Test that COMPLEX PRs with pending approval cannot merge."""
        can_merge = gate._can_merge(
            is_complex=True,
            approval_status=ApprovalStatus.PENDING,
            gitreviewbot_completed=True,
        )

        assert can_merge is False

    def test_can_merge_complex_approved(self, gate):
        """Test that COMPLEX PRs with approval can merge."""
        can_merge = gate._can_merge(
            is_complex=True,
            approval_status=ApprovalStatus.APPROVED,
            gitreviewbot_completed=True,
        )

        assert can_merge is True

    def test_can_merge_complex_emergency(self, gate):
        """Test that COMPLEX PRs with emergency override can merge."""
        can_merge = gate._can_merge(
            is_complex=True,
            approval_status=ApprovalStatus.EMERGENCY_OVERRIDE,
            gitreviewbot_completed=True,
        )

        assert can_merge is True

    def test_is_approval_expired(self, gate):
        """Test approval expiration check."""
        # Recent approval - not expired
        recent_record = ApprovalRecord(
            pr_number=123,
            status=ApprovalStatus.APPROVED,
            approver="reviewer1",
            timestamp=datetime.now(UTC),
        )
        assert not gate._is_approval_expired(recent_record)

        # Old approval - expired
        old_record = ApprovalRecord(
            pr_number=123,
            status=ApprovalStatus.APPROVED,
            approver="reviewer1",
            timestamp=datetime.now(UTC) - timedelta(hours=49),
        )
        assert gate._is_approval_expired(old_record)

    def test_audit_log_persistence(self, gate):
        """Test that approvals are persisted to audit log."""
        # Create a record
        record = ApprovalRecord(
            pr_number=456,
            status=ApprovalStatus.APPROVED,
            approver="reviewer2",
            timestamp=datetime.now(UTC),
            reason="Approved after review",
        )

        # Write to log
        gate._append_to_audit_log(record)

        # Read back from log
        loaded_record = gate._load_approval_from_log(456)

        assert loaded_record is not None
        assert loaded_record.pr_number == 456
        assert loaded_record.status == ApprovalStatus.APPROVED
        assert loaded_record.approver == "reviewer2"

    def test_get_audit_trail(self, gate):
        """Test retrieving audit trail."""
        # Add multiple records
        for i in range(3):
            record = ApprovalRecord(
                pr_number=100 + i,
                status=ApprovalStatus.APPROVED,
                approver=f"reviewer{i}",
                timestamp=datetime.now(UTC),
            )
            gate._append_to_audit_log(record)

        # Get all records
        all_records = gate.get_audit_trail()
        assert len(all_records) >= 3

        # Get records for specific PR
        pr_records = gate.get_audit_trail(pr_number=100)
        assert len(pr_records) >= 1
        assert pr_records[0].pr_number == 100

    def test_approval_record_serialization(self):
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

    def test_build_reasoning(self, gate):
        """Test reasoning message generation."""
        reasoning = gate._build_reasoning(
            is_complex=True,
            risk_level=RiskLevel.COMPLEX,
            approval_status=ApprovalStatus.PENDING,
            gitreviewbot_completed=True,
        )

        assert "COMPLEX" in reasoning
        assert "human approval" in reasoning
        assert "PENDING" in reasoning.upper()


class TestHumanApprovalWorkflow:
    """Tests for HumanApprovalWorkflow class."""

    @pytest.fixture
    def mock_gate(self):
        """Create a mock ComplexPathGate."""
        gate = MagicMock(spec=ComplexPathGate)
        gate.emergency_approvers = {"admin1", "admin2"}
        return gate

    @pytest.fixture
    def mock_gitea(self):
        """Create a mock GiteaClient."""
        return AsyncMock()

    @pytest.fixture
    def mock_discord(self):
        """Create a mock DiscordClient."""
        return AsyncMock()

    @pytest.fixture
    def workflow(self, mock_gate, mock_gitea, mock_discord):
        """Create a HumanApprovalWorkflow with mocked dependencies."""
        config = WorkflowConfig(
            poll_interval_seconds=1,  # Fast for testing
            max_poll_attempts=2,
            approval_timeout_hours=48,
        )

        return HumanApprovalWorkflow(
            gate=mock_gate,
            gitea_client=mock_gitea,
            discord_client=mock_discord,
            config=config,
        )

    @pytest.mark.asyncio
    async def test_process_non_complex_pr(self, workflow, mock_gate):
        """Test processing a non-COMPLEX PR."""
        # Setup mock
        mock_result = MagicMock()
        mock_result.is_complex = False
        mock_result.risk_level = RiskLevel.SAFE
        mock_gate.check_pr_status = AsyncMock(return_value=mock_result)

        result = await workflow.process_complex_pr(pr_number=123)

        assert result.success is True
        assert result.final_status == ApprovalStatus.PENDING
        assert result.gitreviewbot_completed is False
        assert result.discord_notified is False

    @pytest.mark.asyncio
    async def test_process_complex_pr_success(self, workflow, mock_gate):
        """Test processing a COMPLEX PR that gets approved."""
        # Setup mocks
        mock_check_result = MagicMock()
        mock_check_result.is_complex = True
        mock_check_result.risk_level = RiskLevel.COMPLEX
        mock_check_result.files_analyzed = ["src/critical.py"]
        mock_check_result.gitreviewbot_completed = True
        mock_check_result.approval_status = ApprovalStatus.APPROVED

        mock_approval_record = MagicMock()
        mock_approval_record.status = ApprovalStatus.APPROVED
        mock_check_result.approval_record = mock_approval_record

        mock_gate.check_pr_status = AsyncMock(return_value=mock_check_result)

        result = await workflow.process_complex_pr(pr_number=123)

        assert result.success is True
        assert result.final_status == ApprovalStatus.APPROVED

    @pytest.mark.asyncio
    async def test_send_approval_notification(self, workflow, mock_gitea, mock_discord):
        """Test Discord notification for approval request."""
        # Setup mock PR
        mock_pr = MagicMock()
        mock_pr.title = "Test PR"
        mock_pr.author = "developer1"
        mock_pr.branch = "feature/test"
        mock_gitea.get_pr = AsyncMock(return_value=mock_pr)

        # Setup mock check result
        mock_check_result = MagicMock()
        mock_check_result.risk_level = RiskLevel.COMPLEX
        mock_check_result.confidence = 0.95
        mock_check_result.files_analyzed = ["src/file1.py", "src/file2.py"]
        mock_check_result.gitreviewbot_completed = True

        result = await workflow._send_approval_notification(123, mock_check_result)

        assert result is True
        assert 123 in workflow._notified_prs

    @pytest.mark.asyncio
    async def test_emergency_override_success(self, workflow, mock_gate):
        """Test successful emergency override."""
        # Setup mock
        mock_record = MagicMock()
        mock_record.status = ApprovalStatus.EMERGENCY_OVERRIDE
        mock_gate.emergency_override = AsyncMock(return_value=mock_record)

        result = await workflow.process_emergency_override(
            pr_number=123,
            approver="admin1",
            justification="Critical security fix",
        )

        assert result.success is True
        assert result.final_status == ApprovalStatus.EMERGENCY_OVERRIDE
        mock_gate.emergency_override.assert_called_once_with(
            pr_number=123,
            approver="admin1",
            justification="Critical security fix",
        )

    @pytest.mark.asyncio
    async def test_emergency_override_failure(self, workflow, mock_gate):
        """Test failed emergency override."""
        # Setup mock to raise exception
        mock_gate.emergency_override = AsyncMock(
            side_effect=ValueError("Not authorized")
        )

        result = await workflow.process_emergency_override(
            pr_number=123,
            approver="unauthorized",
            justification="Critical fix",
        )

        assert result.success is False
        assert result.error_message is not None

    def test_build_approval_message(self, workflow):
        """Test Discord message building."""
        mock_pr = MagicMock()
        mock_pr.title = "Critical Infrastructure Change"
        mock_pr.author = "developer1"
        mock_pr.branch = "feature/infra"

        mock_check_result = MagicMock()
        mock_check_result.risk_level = RiskLevel.COMPLEX
        mock_check_result.confidence = 0.95
        mock_check_result.files_analyzed = [
            "infrastructure/terraform/main.tf",
            "infrastructure/terraform/network.tf",
        ]
        mock_check_result.gitreviewbot_completed = True

        message = workflow._build_approval_message(123, mock_pr, mock_check_result)

        assert "COMPLEX PR" in message
        assert "123" in message
        assert "Critical Infrastructure Change" in message
        assert "developer1" in message
        assert "terraform" in message

    @pytest.mark.asyncio
    async def test_poll_for_approval_timeout(self, workflow, mock_gate):
        """Test polling that times out without approval."""
        # Setup mock to always return pending
        mock_result = MagicMock()
        mock_result.approval_status = ApprovalStatus.PENDING
        mock_gate.check_pr_status = AsyncMock(return_value=mock_result)

        status, record = await workflow._poll_for_approval(123)

        # Should return pending after max polls
        assert status == ApprovalStatus.PENDING

    def test_workflow_config_defaults(self):
        """Test WorkflowConfig default values."""
        config = WorkflowConfig()

        assert config.poll_interval_seconds == 60
        assert config.max_poll_attempts == 100
        assert config.approval_timeout_hours == 48
        assert config.run_gitreviewbot_first is True
        assert config.gitreviewbot_min_confidence == 0.7


class TestIntegration:
    """Integration tests for the complete workflow."""

    @pytest.mark.asyncio
    async def test_full_workflow_simulation(self):
        """Simulate a complete workflow from detection to approval."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            audit_log = f.name

        try:
            # Create gate
            gate = ComplexPathGate(
                audit_log_path=audit_log,
                emergency_approvers=["admin"],
            )

            # Test classification
            complex_files = [
                "infrastructure/terraform/main.tf",
                "src/execution/critical.py",
            ]

            is_complex, risk_level, confidence = gate.is_complex_classification(
                complex_files
            )

            # COMPLEX files should be detected
            assert is_complex or risk_level == RiskLevel.COMPLEX

            # Record approval
            record = await gate.record_human_approval(
                pr_number=999,
                approver="reviewer1",
                reason="Integration test approval",
            )

            assert record.status == ApprovalStatus.APPROVED

            # Verify audit log
            audit_trail = gate.get_audit_trail(pr_number=999)
            assert len(audit_trail) >= 1

        finally:
            os.unlink(audit_log)

    def test_complex_path_check_result_serialization(self):
        """Test ComplexPathCheckResult serialization."""
        record = ApprovalRecord(
            pr_number=123,
            status=ApprovalStatus.APPROVED,
            approver="reviewer1",
            timestamp=datetime.now(UTC),
        )

        result = ComplexPathCheckResult(
            pr_number=123,
            is_complex=True,
            risk_level=RiskLevel.COMPLEX,
            confidence=0.95,
            files_analyzed=["file1.py", "file2.py"],
            approval_status=ApprovalStatus.APPROVED,
            approval_record=record,
            gitreviewbot_completed=True,
            gitreviewbot_decision="APPROVE",
            requires_human_approval=True,
            can_merge=True,
            reasoning="Test reasoning",
        )

        # Serialize
        data = result.to_dict()

        # Verify structure
        assert data["pr_number"] == 123
        assert data["is_complex"] is True
        assert data["risk_level"] == "complex"
        assert data["can_merge"] is True
        assert data["approval_record"] is not None

    def test_workflow_result_serialization(self):
        """Test WorkflowResult serialization."""
        record = ApprovalRecord(
            pr_number=123,
            status=ApprovalStatus.APPROVED,
            approver="reviewer1",
            timestamp=datetime.now(UTC),
        )

        result = WorkflowResult(
            pr_number=123,
            success=True,
            final_status=ApprovalStatus.APPROVED,
            gitreviewbot_completed=True,
            discord_notified=True,
            approval_record=record,
            processing_time_seconds=120.5,
        )

        # Serialize
        data = result.to_dict()

        # Verify
        assert data["pr_number"] == 123
        assert data["success"] is True
        assert data["final_status"] == "approved"
        assert data["processing_time_seconds"] == 120.5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
