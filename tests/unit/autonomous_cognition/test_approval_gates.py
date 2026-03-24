"""Tests for approval_gates module."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from autonomous_cognition.approval_gates import (
    ApprovalGates,
    ApprovalRequest,
    ApprovalResult,
    ApprovalStatus,
)


class TestApprovalGates:
    """Test cases for ApprovalGates class."""

    def test_init_default(self):
        """Test initialization with default parameters."""
        gates = ApprovalGates()
        assert gates._default_timeout == 3600
        assert gates._redis is None
        assert gates._discord is None

    def test_init_custom_timeout(self):
        """Test initialization with custom timeout."""
        gates = ApprovalGates(default_timeout_seconds=7200)
        assert gates._default_timeout == 7200

    def test_init_with_redis(self):
        """Test initialization with Redis client."""
        mock_redis = MagicMock()
        gates = ApprovalGates(redis_client=mock_redis)
        assert gates._redis is mock_redis

    def test_init_with_discord(self):
        """Test initialization with Discord notifier."""
        mock_discord = MagicMock()
        gates = ApprovalGates(discord_notifier=mock_discord)
        assert gates._discord is mock_discord

    def test_request_approval_creates_request(self):
        """Test that request_approval creates a new request."""
        gates = ApprovalGates()
        decision = {
            "action": "test_action",
            "description": "Test description",
            "risk_level": "high",
            "files": ["src/test.py"],
        }

        result = gates.request_approval(decision)

        assert result.status == ApprovalStatus.PENDING
        assert result.request_id != ""
        assert result.timeout_at > datetime.now(UTC)
        assert result.request_id in gates._requests

    def test_request_approval_stores_evidence(self):
        """Test that request_approval stores evidence packet."""
        gates = ApprovalGates()
        decision = {
            "action": "test_action",
            "description": "Test description",
            "risk_level": "high",
            "evidence": {"key": "value"},
        }

        result = gates.request_approval(decision)
        request = gates._requests[result.request_id]

        assert request.evidence["action"] == "test_action"
        assert request.evidence["supporting_evidence"] == {"key": "value"}
        assert "timestamp" in request.evidence

    def test_request_approval_custom_timeout(self):
        """Test request_approval with custom timeout."""
        gates = ApprovalGates()
        decision = {
            "action": "test_action",
            "description": "Test",
        }

        result = gates.request_approval(decision, timeout_seconds=600)

        expected_timeout = datetime.now(UTC) + timedelta(seconds=600)
        # Allow 1 second tolerance
        assert abs((result.timeout_at - expected_timeout).total_seconds()) < 1

    def test_check_approval_status_pending(self):
        """Test checking status of pending request."""
        gates = ApprovalGates()
        decision = {"action": "test_action"}

        request_result = gates.request_approval(decision)
        status = gates.check_approval_status(request_result.request_id)

        assert status.status == ApprovalStatus.PENDING
        assert status.request_id == request_result.request_id

    def test_check_approval_status_not_found(self):
        """Test checking status of non-existent request."""
        gates = ApprovalGates()

        status = gates.check_approval_status("non-existent-id")

        # Should fail closed (rejected)
        assert status.status == ApprovalStatus.REJECTED
        assert status.notes == "Request not found"

    def test_approve_request_success(self):
        """Test approving a request."""
        gates = ApprovalGates()
        decision = {"action": "test_action"}

        request_result = gates.request_approval(decision)
        approval_result = gates.approve_request(
            request_result.request_id,
            approver="craig",
            notes="Looks good",
        )

        assert approval_result.status == ApprovalStatus.APPROVED
        assert approval_result.approved_by == "craig"
        assert approval_result.notes == "Looks good"

    def test_approve_request_not_found(self):
        """Test approving non-existent request."""
        gates = ApprovalGates()

        result = gates.approve_request("non-existent", "craig")

        # Should fail closed
        assert result.status == ApprovalStatus.REJECTED
        assert result.notes == "Request not found"

    def test_approve_request_already_decided(self):
        """Test approving already decided request."""
        gates = ApprovalGates()
        decision = {"action": "test_action"}

        request_result = gates.request_approval(decision)
        first_result = gates.approve_request(request_result.request_id, "craig")

        # Try to approve again - request moved to history, so it won't be found
        second_result = gates.approve_request(request_result.request_id, "jarvis")

        # Request was moved to history after first approval, so second fails
        assert second_result.status == ApprovalStatus.REJECTED
        assert "not found" in second_result.notes.lower()

    def test_reject_request_success(self):
        """Test rejecting a request."""
        gates = ApprovalGates()
        decision = {"action": "test_action"}

        request_result = gates.request_approval(decision)
        reject_result = gates.reject_request(
            request_result.request_id,
            approver="craig",
            reason="Too risky",
        )

        assert reject_result.status == ApprovalStatus.REJECTED
        assert reject_result.rejected_by == "craig"
        assert reject_result.notes == "Too risky"

    def test_reject_request_not_found(self):
        """Test rejecting non-existent request."""
        gates = ApprovalGates()

        result = gates.reject_request("non-existent", "craig")

        assert result.status == ApprovalStatus.REJECTED
        assert result.notes == "Request not found"

    def test_timeout_request(self):
        """Test timing out a request."""
        gates = ApprovalGates()
        decision = {"action": "test_action"}

        request_result = gates.request_approval(decision)
        timeout_result = gates.timeout_request(request_result.request_id)

        assert timeout_result.status == ApprovalStatus.TIMEOUT
        assert (
            "timed out" in timeout_result.notes.lower()
            or "timeout" in timeout_result.notes.lower()
        )

    def test_timeout_request_not_found(self):
        """Test timing out non-existent request."""
        gates = ApprovalGates()

        result = gates.timeout_request("non-existent")

        assert result.status == ApprovalStatus.REJECTED
        assert result.notes == "Request not found"

    def test_timeout_request_already_decided(self):
        """Test timing out already decided request."""
        gates = ApprovalGates()
        decision = {"action": "test_action"}

        request_result = gates.request_approval(decision)
        gates.approve_request(request_result.request_id, "craig")

        # Request was moved to history, so timeout won't find it
        timeout_result = gates.timeout_request(request_result.request_id)

        # Request not found in active requests
        assert timeout_result.status == ApprovalStatus.REJECTED
        assert "not found" in timeout_result.notes.lower()

    def test_get_pending_requests_empty(self):
        """Test getting pending requests when none exist."""
        gates = ApprovalGates()

        pending = gates.get_pending_requests()

        assert pending == []

    def test_get_pending_requests(self):
        """Test getting pending requests."""
        gates = ApprovalGates()

        decision1 = {"action": "action1"}
        decision2 = {"action": "action2"}

        result1 = gates.request_approval(decision1)
        result2 = gates.request_approval(decision2)

        pending = gates.get_pending_requests()

        assert len(pending) == 2
        # Should be sorted by requested_at
        assert pending[0]["decision"]["action"] == "action1"
        assert pending[1]["decision"]["action"] == "action2"

    def test_get_pending_requests_excludes_decided(self):
        """Test that decided requests are not in pending."""
        gates = ApprovalGates()

        decision1 = {"action": "action1"}
        decision2 = {"action": "action2"}

        result1 = gates.request_approval(decision1)
        result2 = gates.request_approval(decision2)

        # Approve one
        gates.approve_request(result1.request_id, "craig")

        pending = gates.get_pending_requests()

        assert len(pending) == 1
        assert pending[0]["decision"]["action"] == "action2"

    def test_get_approval_history(self):
        """Test getting approval history."""
        gates = ApprovalGates()

        decision = {"action": "test_action"}
        request_result = gates.request_approval(decision)
        gates.approve_request(request_result.request_id, "craig")

        history = gates.get_approval_history()

        assert len(history) == 1
        assert history[0]["status"] == ApprovalStatus.APPROVED.value

    def test_get_approval_history_with_status_filter(self):
        """Test getting approval history with status filter."""
        gates = ApprovalGates()

        # Create and approve one
        result1 = gates.request_approval({"action": "action1"})
        gates.approve_request(result1.request_id, "craig")

        # Create and reject one
        result2 = gates.request_approval({"action": "action2"})
        gates.reject_request(result2.request_id, "craig")

        approved_history = gates.get_approval_history(status=ApprovalStatus.APPROVED)
        rejected_history = gates.get_approval_history(status=ApprovalStatus.REJECTED)

        assert len(approved_history) == 1
        assert len(rejected_history) == 1
        assert approved_history[0]["decision"]["action"] == "action1"
        assert rejected_history[0]["decision"]["action"] == "action2"

    def test_get_approval_history_with_limit(self):
        """Test getting approval history with limit."""
        gates = ApprovalGates()

        for i in range(5):
            result = gates.request_approval({"action": f"action{i}"})
            gates.approve_request(result.request_id, "craig")

        history = gates.get_approval_history(limit=3)

        assert len(history) == 3

    def test_cleanup_expired_requests(self):
        """Test cleaning up expired requests."""
        gates = ApprovalGates()

        # Create request that's already expired (negative timeout means already past)
        result = gates.request_approval(
            {"action": "test"},
            timeout_seconds=-1,  # Already expired
        )

        # Cleanup should find and timeout the expired request
        cleaned = gates.cleanup_expired_requests()

        # Request should be moved to history
        assert result.request_id not in gates._requests
        assert cleaned == 1

    def test_redis_persistence_on_request(self):
        """Test Redis persistence when creating request."""
        mock_redis = MagicMock()
        gates = ApprovalGates(redis_client=mock_redis)

        decision = {"action": "test_action"}
        result = gates.request_approval(decision)

        # Verify Redis hset was called
        mock_redis.hset.assert_called_once()
        call_args = mock_redis.hset.call_args
        assert call_args[0][0] == gates.REDIS_APPROVAL_REQUESTS_KEY
        assert call_args[0][1] == result.request_id

    def test_redis_pubsub_notification(self):
        """Test Redis pub/sub notification."""
        mock_redis = MagicMock()
        gates = ApprovalGates(redis_client=mock_redis)

        decision = {"action": "test_action"}
        gates.request_approval(decision)

        # Verify Redis publish was called
        mock_redis.publish.assert_called_once()
        call_args = mock_redis.publish.call_args
        assert call_args[0][0] == gates.REDIS_APPROVAL_PUBSUB_CHANNEL

    def test_redis_history_persistence(self):
        """Test Redis persistence when moving to history."""
        mock_redis = MagicMock()
        gates = ApprovalGates(redis_client=mock_redis)

        decision = {"action": "test_action"}
        result = gates.request_approval(decision)
        gates.approve_request(result.request_id, "craig")

        # Verify Redis lpush was called for history
        history_calls = [
            call
            for call in mock_redis.lpush.call_args_list
            if call[0][0] == gates.REDIS_APPROVAL_HISTORY_KEY
        ]
        assert len(history_calls) == 1

    def test_approval_request_to_dict(self):
        """Test ApprovalRequest to_dict method."""
        request = ApprovalRequest(
            request_id="test-123",
            decision={"action": "test"},
            risk_level="high",
            requested_at=datetime(2026, 3, 16, 10, 0, 0, tzinfo=UTC),
            timeout_at=datetime(2026, 3, 16, 11, 0, 0, tzinfo=UTC),
            status=ApprovalStatus.PENDING,
        )

        data = request.to_dict()

        assert data["request_id"] == "test-123"
        assert data["risk_level"] == "high"
        assert data["status"] == "pending"
        assert data["requested_at"] == "2026-03-16T10:00:00+00:00"

    def test_approval_request_from_dict(self):
        """Test ApprovalRequest from_dict method."""
        data = {
            "request_id": "test-123",
            "decision": {"action": "test"},
            "risk_level": "high",
            "requested_at": "2026-03-16T10:00:00+00:00",
            "timeout_at": "2026-03-16T11:00:00+00:00",
            "status": "approved",
            "approver": "craig",
            "notes": "Approved",
            "evidence": {"key": "value"},
            "history": [{"event": "created"}],
        }

        request = ApprovalRequest.from_dict(data)

        assert request.request_id == "test-123"
        assert request.status == ApprovalStatus.APPROVED
        assert request.approver == "craig"
        assert request.notes == "Approved"

    def test_history_tracking(self):
        """Test that request history is tracked."""
        gates = ApprovalGates()

        decision = {"action": "test_action"}
        result = gates.request_approval(decision)
        request = gates._requests[result.request_id]

        # Should have initial history entry
        assert len(request.history) == 1
        assert request.history[0]["event"] == "request_created"

        # Approve and check history
        gates.approve_request(result.request_id, "craig", "Approved")

        # Request moved to history, check there
        history_request = gates._history[0]
        assert len(history_request.history) == 2
        assert history_request.history[1]["event"] == "approved"
        assert history_request.history[1]["approver"] == "craig"

    def test_timeout_auto_check_on_status(self):
        """Test that timeout is checked when getting status."""
        gates = ApprovalGates()

        # Create request that's already expired
        result = gates.request_approval(
            {"action": "test"},
            timeout_seconds=-1,  # Already expired
        )

        # Check status - should auto-timeout since already expired
        status = gates.check_approval_status(result.request_id)

        # After timeout, request is moved to history, so status check returns not found
        # But the request should have been timed out
        assert status.status in [ApprovalStatus.TIMEOUT, ApprovalStatus.REJECTED]
        # Either it was timed out (and moved to history) or not found (already in history)


class TestApprovalStatus:
    """Test cases for ApprovalStatus enum."""

    def test_status_values(self):
        """Test approval status values."""
        assert ApprovalStatus.PENDING.value == "pending"
        assert ApprovalStatus.APPROVED.value == "approved"
        assert ApprovalStatus.REJECTED.value == "rejected"
        assert ApprovalStatus.TIMEOUT.value == "timeout"


class TestApprovalResult:
    """Test cases for ApprovalResult dataclass."""

    def test_approval_result_creation(self):
        """Test creating ApprovalResult."""
        result = ApprovalResult(
            request_id="test-123",
            status=ApprovalStatus.APPROVED,
            timeout_at=datetime.now(UTC),
            approved_by="craig",
            notes="Looks good",
        )
        assert result.request_id == "test-123"
        assert result.status == ApprovalStatus.APPROVED
        assert result.approved_by == "craig"

    def test_approval_result_defaults(self):
        """Test ApprovalResult with defaults."""
        result = ApprovalResult(
            request_id="test-123",
            status=ApprovalStatus.PENDING,
            timeout_at=datetime.now(UTC),
        )
        assert result.approved_by is None
        assert result.rejected_by is None
        assert result.notes == ""


class TestSafeFallbackBehavior:
    """Test cases for safe fallback behavior."""

    def test_timeout_safe_fallback(self):
        """Test that timeout results in safe fallback (rejection)."""
        gates = ApprovalGates()

        decision = {"action": "critical_action"}
        result = gates.request_approval(decision, timeout_seconds=0)

        # Wait for timeout
        import time

        time.sleep(0.1)

        timeout_result = gates.timeout_request(result.request_id)

        # Should be rejected (safe fallback)
        assert timeout_result.status == ApprovalStatus.TIMEOUT
        assert "auto-rejected" in timeout_result.notes.lower()

    def test_not_found_fails_closed(self):
        """Test that unknown requests fail closed."""
        gates = ApprovalGates()

        # Check status of non-existent request
        status = gates.check_approval_status("non-existent")
        assert status.status == ApprovalStatus.REJECTED

        # Try to approve non-existent request
        approval = gates.approve_request("non-existent", "craig")
        assert approval.status == ApprovalStatus.REJECTED

        # Try to reject non-existent request
        rejection = gates.reject_request("non-existent", "craig")
        assert rejection.status == ApprovalStatus.REJECTED

    def test_system_failure_during_approval(self):
        """Test handling of system failure during approval."""
        gates = ApprovalGates()

        decision = {"action": "test"}
        result = gates.request_approval(decision)

        # Simulate Redis failure during approval
        gates._redis = MagicMock()
        gates._redis.hset.side_effect = Exception("Redis failure")

        # Should still work (in-memory)
        approval = gates.approve_request(result.request_id, "craig")
        assert approval.status == ApprovalStatus.APPROVED


class TestDiscordIntegration:
    """Test cases for Discord integration."""

    def test_discord_notification_on_request(self):
        """Test Discord notification on new request."""
        mock_discord = MagicMock()
        mock_discord.notify_autocog_event = MagicMock(return_value=None)

        gates = ApprovalGates(discord_notifier=mock_discord)

        decision = {
            "action": "test_action",
            "description": "Test description",
            "risk_level": "high",
        }

        with patch.object(gates, "_notify_discord_request") as mock_notify:
            gates.request_approval(decision)
            mock_notify.assert_called_once()

    def test_discord_notification_on_approval(self):
        """Test Discord notification on approval."""
        mock_discord = MagicMock()
        gates = ApprovalGates(discord_notifier=mock_discord)

        decision = {"action": "test_action"}
        result = gates.request_approval(decision)

        with patch.object(gates, "_notify_discord_approval") as mock_notify:
            gates.approve_request(result.request_id, "craig")
            mock_notify.assert_called_once()

    def test_discord_notification_on_rejection(self):
        """Test Discord notification on rejection."""
        mock_discord = MagicMock()
        gates = ApprovalGates(discord_notifier=mock_discord)

        decision = {"action": "test_action"}
        result = gates.request_approval(decision)

        with patch.object(gates, "_notify_discord_rejection") as mock_notify:
            gates.reject_request(result.request_id, "craig")
            mock_notify.assert_called_once()

    def test_discord_notification_on_timeout(self):
        """Test Discord notification on timeout."""
        mock_discord = MagicMock()
        gates = ApprovalGates(discord_notifier=mock_discord)

        decision = {"action": "test_action"}
        result = gates.request_approval(decision)

        with patch.object(gates, "_notify_discord_timeout") as mock_notify:
            gates.timeout_request(result.request_id)
            mock_notify.assert_called_once()
