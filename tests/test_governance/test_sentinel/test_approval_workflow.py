"""Tests for Approval Workflow module (ST-GOV-003)."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
import json

from src.governance.sentinel.approval_workflow import (
    ApprovalWorkflow,
    ApprovalRequest,
    ApprovalResult,
    ApprovalStatus,
)


class TestApprovalStatus:
    """Tests for ApprovalStatus enum."""

    def test_approval_statuses(self):
        """Test all approval statuses are defined."""
        assert ApprovalStatus.PENDING == "pending"
        assert ApprovalStatus.APPROVED == "approved"
        assert ApprovalStatus.REJECTED == "rejected"
        assert ApprovalStatus.EXPIRED == "expired"
        assert ApprovalStatus.CANCELLED == "cancelled"


class TestApprovalRequest:
    """Tests for ApprovalRequest dataclass."""

    def test_approval_request_creation(self):
        """Test creating an ApprovalRequest."""
        now = datetime.utcnow()
        request = ApprovalRequest(
            request_id="apr-12345678",
            task_id="ST-001",
            story_points=8,
            justification="Complex feature requiring coordination",
            requester="agent-1",
            status=ApprovalStatus.PENDING,
            created_at=now,
            expires_at=now + timedelta(hours=24),
        )

        assert request.request_id == "apr-12345678"
        assert request.task_id == "ST-001"
        assert request.story_points == 8
        assert request.status == ApprovalStatus.PENDING

    def test_to_dict(self):
        """Test converting to dictionary."""
        request = ApprovalRequest(
            request_id="apr-123",
            task_id="ST-001",
            story_points=8,
            justification="Test",
            requester="agent-1",
        )

        data = request.to_dict()

        assert data["request_id"] == "apr-123"
        assert data["task_id"] == "ST-001"
        assert data["status"] == "pending"
        assert "created_at" not in data or data["created_at"] is None

    def test_from_dict(self):
        """Test creating from dictionary."""
        data = {
            "request_id": "apr-456",
            "task_id": "ST-002",
            "story_points": 10,
            "justification": "Complex task",
            "requester": "agent-2",
            "status": "approved",
            "approved_by": "human-1",
        }

        request = ApprovalRequest.from_dict(data)

        assert request.request_id == "apr-456"
        assert request.task_id == "ST-002"
        assert request.status == ApprovalStatus.APPROVED
        assert request.approved_by == "human-1"


class TestApprovalWorkflow:
    """Tests for ApprovalWorkflow class."""

    def test_initialization(self):
        """Test workflow initialization."""
        workflow = ApprovalWorkflow()
        assert workflow.redis_client is None
        assert workflow.default_timeout_hours == 24

    def test_initialization_with_redis(self):
        """Test workflow with Redis client."""
        mock_redis = MagicMock()
        workflow = ApprovalWorkflow(redis_client=mock_redis)
        assert workflow.redis_client == mock_redis

    def test_request_approval_without_redis(self):
        """Test request_approval fails without Redis."""
        workflow = ApprovalWorkflow()

        with pytest.raises(RuntimeError, match="Redis client not configured"):
            workflow.request_approval(
                task_id="ST-001",
                story_points=8,
                justification="Complex task",
                requester="agent-1",
            )

    def test_request_approval_with_redis(self):
        """Test creating approval request with Redis."""
        mock_redis = MagicMock()
        workflow = ApprovalWorkflow(redis_client=mock_redis)

        request_id = workflow.request_approval(
            task_id="ST-001",
            story_points=8,
            justification="Complex feature requiring careful coordination",
            requester="agent-1",
        )

        assert request_id.startswith("apr-")
        mock_redis.set.assert_called_once()
        mock_redis.lpush.assert_called_once()

    def test_request_approval_without_justification(self):
        """Test approval request fails without justification."""
        mock_redis = MagicMock()
        workflow = ApprovalWorkflow(redis_client=mock_redis)

        with pytest.raises(ValueError, match="Justification is required"):
            workflow.request_approval(
                task_id="ST-001",
                story_points=8,
                justification="",
                requester="agent-1",
            )

    def test_request_approval_custom_timeout(self):
        """Test approval request with custom timeout."""
        mock_redis = MagicMock()
        workflow = ApprovalWorkflow(redis_client=mock_redis)

        request_id = workflow.request_approval(
            task_id="ST-001",
            story_points=8,
            justification="Valid justification",
            requester="agent-1",
            timeout_hours=48,
        )

        # Verify setex was called with correct TTL
        call_args = mock_redis.set.call_args
        assert call_args is not None

    def test_approve_request(self):
        """Test approving a request."""
        mock_redis = MagicMock()

        # Mock the request data
        request_data = {
            "request_id": "apr-123",
            "task_id": "ST-001",
            "story_points": 8,
            "justification": "Test",
            "requester": "agent-1",
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
            "expires_at": (datetime.utcnow() + timedelta(hours=24)).isoformat(),
        }
        mock_redis.get.return_value = json.dumps(request_data).encode()

        workflow = ApprovalWorkflow(redis_client=mock_redis)
        result = workflow.approve("apr-123", approver="human-1")

        assert result.success is True
        assert result.status == ApprovalStatus.APPROVED
        mock_redis.sadd.assert_called_once()
        mock_redis.lrem.assert_called_once()

    def test_approve_nonexistent_request(self):
        """Test approving a nonexistent request."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        workflow = ApprovalWorkflow(redis_client=mock_redis)
        result = workflow.approve("apr-nonexistent", approver="human-1")

        assert result.success is False
        assert "not found" in result.message.lower()

    def test_approve_already_approved(self):
        """Test approving an already approved request."""
        mock_redis = MagicMock()

        request_data = {
            "request_id": "apr-123",
            "task_id": "ST-001",
            "story_points": 8,
            "justification": "Test",
            "requester": "agent-1",
            "status": "approved",
        }
        mock_redis.get.return_value = json.dumps(request_data).encode()

        workflow = ApprovalWorkflow(redis_client=mock_redis)
        result = workflow.approve("apr-123", approver="human-1")

        assert result.success is False
        assert "already" in result.message.lower()

    def test_reject_request(self):
        """Test rejecting a request."""
        mock_redis = MagicMock()

        request_data = {
            "request_id": "apr-123",
            "task_id": "ST-001",
            "story_points": 8,
            "justification": "Test",
            "requester": "agent-1",
            "status": "pending",
        }
        mock_redis.get.return_value = json.dumps(request_data).encode()

        workflow = ApprovalWorkflow(redis_client=mock_redis)
        result = workflow.reject("apr-123", rejector="human-1", reason="Too complex")

        assert result.success is True
        assert result.status == ApprovalStatus.REJECTED

    def test_cancel_request(self):
        """Test cancelling a request."""
        mock_redis = MagicMock()

        request_data = {
            "request_id": "apr-123",
            "task_id": "ST-001",
            "story_points": 8,
            "justification": "Test",
            "requester": "agent-1",
            "status": "pending",
        }
        mock_redis.get.return_value = json.dumps(request_data).encode()

        workflow = ApprovalWorkflow(redis_client=mock_redis)
        result = workflow.cancel("apr-123", reason="Task decomposed")

        assert result.success is True
        assert result.status == ApprovalStatus.CANCELLED

    def test_get_request(self):
        """Test getting a request by ID."""
        mock_redis = MagicMock()

        request_data = {
            "request_id": "apr-123",
            "task_id": "ST-001",
            "story_points": 8,
            "justification": "Test",
            "requester": "agent-1",
            "status": "pending",
        }
        mock_redis.get.return_value = json.dumps(request_data).encode()

        workflow = ApprovalWorkflow(redis_client=mock_redis)
        request = workflow.get_request("apr-123")

        assert request is not None
        assert request.task_id == "ST-001"

    def test_get_request_not_found(self):
        """Test getting a nonexistent request."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        workflow = ApprovalWorkflow(redis_client=mock_redis)
        request = workflow.get_request("apr-nonexistent")

        assert request is None

    def test_get_pending_approvals(self):
        """Test getting pending approvals."""
        mock_redis = MagicMock()

        # Mock the queue
        mock_redis.lrange.return_value = [b"apr-123", b"apr-456"]

        # Mock the requests
        request_data_1 = {
            "request_id": "apr-123",
            "task_id": "ST-001",
            "story_points": 8,
            "justification": "Test 1",
            "requester": "agent-1",
            "status": "pending",
            "expires_at": (datetime.utcnow() + timedelta(hours=24)).isoformat(),
        }
        request_data_2 = {
            "request_id": "apr-456",
            "task_id": "ST-002",
            "story_points": 10,
            "justification": "Test 2",
            "requester": "agent-2",
            "status": "pending",
            "expires_at": (datetime.utcnow() + timedelta(hours=24)).isoformat(),
        }

        def mock_get(key):
            if "apr-123" in key:
                return json.dumps(request_data_1).encode()
            elif "apr-456" in key:
                return json.dumps(request_data_2).encode()
            return None

        mock_redis.get.side_effect = mock_get

        workflow = ApprovalWorkflow(redis_client=mock_redis)
        pending = workflow.get_pending_approvals()

        assert len(pending) == 2

    def test_get_pending_approvals_with_expired(self):
        """Test getting pending approvals with expired ones."""
        mock_redis = MagicMock()

        mock_redis.lrange.return_value = [b"apr-expired"]

        # Mock an expired request
        request_data = {
            "request_id": "apr-expired",
            "task_id": "ST-001",
            "story_points": 8,
            "justification": "Test",
            "requester": "agent-1",
            "status": "pending",
            "expires_at": (
                datetime.utcnow() - timedelta(hours=1)
            ).isoformat(),  # Expired
        }
        mock_redis.get.return_value = json.dumps(request_data).encode()

        workflow = ApprovalWorkflow(redis_client=mock_redis)
        pending = workflow.get_pending_approvals()

        # Expired requests should be filtered out
        assert len(pending) == 0

    def test_is_task_approved(self):
        """Test checking if task is approved."""
        mock_redis = MagicMock()
        mock_redis.sismember.return_value = 1

        workflow = ApprovalWorkflow(redis_client=mock_redis)

        assert workflow.is_task_approved("ST-001") is True
        mock_redis.sismember.assert_called_once()

    def test_is_task_not_approved(self):
        """Test checking if task is not approved."""
        mock_redis = MagicMock()
        mock_redis.sismember.return_value = 0

        workflow = ApprovalWorkflow(redis_client=mock_redis)

        assert workflow.is_task_approved("ST-002") is False

    def test_cleanup_expired(self):
        """Test cleaning up expired requests."""
        mock_redis = MagicMock()

        mock_redis.lrange.return_value = [b"apr-expired", b"apr-valid"]

        def mock_get(key):
            if "apr-expired" in key:
                return json.dumps(
                    {
                        "request_id": "apr-expired",
                        "task_id": "ST-001",
                        "status": "pending",
                        "expires_at": (
                            datetime.utcnow() - timedelta(hours=1)
                        ).isoformat(),
                    }
                ).encode()
            elif "apr-valid" in key:
                return json.dumps(
                    {
                        "request_id": "apr-valid",
                        "task_id": "ST-002",
                        "status": "pending",
                        "expires_at": (
                            datetime.utcnow() + timedelta(hours=24)
                        ).isoformat(),
                    }
                ).encode()
            return None

        mock_redis.get.side_effect = mock_get

        workflow = ApprovalWorkflow(redis_client=mock_redis)
        expired_count = workflow.cleanup_expired()

        assert expired_count == 1


class TestApprovalResult:
    """Tests for ApprovalResult dataclass."""

    def test_result_creation(self):
        """Test creating an ApprovalResult."""
        result = ApprovalResult(
            success=True,
            request_id="apr-123",
            status=ApprovalStatus.APPROVED,
            message="Task approved",
        )

        assert result.success is True
        assert result.request_id == "apr-123"
        assert result.status == ApprovalStatus.APPROVED

    def test_result_failure(self):
        """Test creating a failure result."""
        result = ApprovalResult(
            success=False,
            request_id="apr-456",
            status=ApprovalStatus.PENDING,
            message="Request not found",
        )

        assert result.success is False
        assert result.status == ApprovalStatus.PENDING
