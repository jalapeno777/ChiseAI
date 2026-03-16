"""Tests for action_guards module."""

from __future__ import annotations

import pytest
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from autonomous_cognition.action_guards import (
    ActionGuards,
    ActionResult,
    BlockedAction,
)
from autonomous_cognition.policy_engine import (
    AutonomousPolicyEngine,
    PolicyResult,
)


class TestActionGuards:
    """Test cases for ActionGuards class."""

    def test_init_default(self):
        """Test initialization with default parameters."""
        guards = ActionGuards()
        assert guards._max_risk_level == "medium"
        assert guards._redis is None
        assert guards._action_counter == 0

    def test_init_custom_max_risk(self):
        """Test initialization with custom max risk level."""
        guards = ActionGuards(max_risk_level="high")
        assert guards._max_risk_level == "high"

    def test_init_with_policy_engine(self):
        """Test initialization with custom policy engine."""
        engine = AutonomousPolicyEngine()
        guards = ActionGuards(policy_engine=engine)
        assert guards._policy_engine is engine

    def test_enforce_risk_limit_low_risk(self):
        """Test risk limit enforcement allows low risk actions."""
        guards = ActionGuards(max_risk_level="medium")
        decision = {
            "risk_level": "low",
            "action": "test_action",
            "description": "Test description",
        }
        result = guards.enforce_risk_limit(decision)
        assert result is True

    def test_enforce_risk_limit_medium_risk(self):
        """Test risk limit enforcement allows medium risk actions when max is medium."""
        guards = ActionGuards(max_risk_level="medium")
        decision = {
            "risk_level": "medium",
            "action": "test_action",
            "description": "Test description",
        }
        result = guards.enforce_risk_limit(decision)
        assert result is True

    def test_enforce_risk_limit_high_risk_blocked(self):
        """Test risk limit enforcement blocks high risk actions when max is medium."""
        guards = ActionGuards(max_risk_level="medium")
        decision = {
            "risk_level": "high",
            "action": "test_action",
            "description": "Test description",
        }
        result = guards.enforce_risk_limit(decision)
        assert result is False

    def test_enforce_risk_limit_critical_risk_blocked(self):
        """Test risk limit enforcement blocks critical risk actions."""
        guards = ActionGuards(max_risk_level="high")
        decision = {
            "risk_level": "critical",
            "action": "test_action",
            "description": "Test description",
        }
        result = guards.enforce_risk_limit(decision)
        assert result is False

    def test_enforce_risk_limit_invalid_risk(self):
        """Test risk limit enforcement blocks invalid risk levels."""
        guards = ActionGuards(max_risk_level="medium")
        decision = {
            "risk_level": "invalid",
            "action": "test_action",
            "description": "Test description",
        }
        result = guards.enforce_risk_limit(decision)
        assert result is False

    def test_enforce_risk_limit_allows_high_when_max_is_critical(self):
        """Test risk limit enforcement allows high risk when max is critical."""
        guards = ActionGuards(max_risk_level="critical")
        decision = {
            "risk_level": "high",
            "action": "test_action",
            "description": "Test description",
        }
        result = guards.enforce_risk_limit(decision)
        assert result is True

    def test_check_protected_files_no_files(self):
        """Test protected file check with no files."""
        guards = ActionGuards()
        result = guards.check_protected_files([])
        assert result is True

    def test_check_protected_files_safe_files(self):
        """Test protected file check with safe files."""
        guards = ActionGuards()
        result = guards.check_protected_files(["src/safe/file.py", "tests/test.py"])
        assert result is True

    def test_validate_auto_action_allows_low_risk(self):
        """Test full validation allows low risk actions."""
        guards = ActionGuards(max_risk_level="medium")
        decision = {
            "risk_level": "low",
            "action": "safe_action",
            "description": "A safe action",
            "files": ["src/safe.py"],
        }
        result = guards.validate_auto_action(decision)
        assert result.allowed is True
        assert result.blocked is False
        assert result.requires_approval is False

    def test_validate_auto_action_blocks_high_risk(self):
        """Test full validation blocks high risk actions exceeding max."""
        guards = ActionGuards(max_risk_level="medium")
        decision = {
            "risk_level": "high",
            "action": "risky_action",
            "description": "A risky action",
            "files": ["src/risky.py"],
        }
        result = guards.validate_auto_action(decision)
        assert result.allowed is False
        assert result.blocked is True
        assert result.requires_approval is False
        assert (
            "exceeds" in result.reason.lower() or "Risk limit exceeded" in result.reason
        )

    def test_validate_auto_action_requires_approval_for_high_risk(self):
        """Test validation requires approval for high risk within policy."""
        guards = ActionGuards(max_risk_level="high")
        decision = {
            "risk_level": "high",
            "action": "high_risk_action",
            "description": "A high risk action",
            "files": ["src/action.py"],
        }
        result = guards.validate_auto_action(decision)
        # High risk requires approval (not auto-approved)
        assert result.allowed is False
        assert result.requires_approval is True
        assert result.blocked is False

    def test_validate_auto_action_creates_audit_log_id(self):
        """Test validation creates audit log ID."""
        guards = ActionGuards()
        decision = {
            "risk_level": "low",
            "action": "test_action",
            "description": "Test",
        }
        result = guards.validate_auto_action(decision)
        assert result.audit_log_id != ""
        assert result.audit_log_id.startswith("action-")

    def test_log_blocked_action(self):
        """Test logging blocked actions."""
        guards = ActionGuards()
        decision = {
            "risk_level": "high",
            "action": "blocked_action",
            "description": "Blocked",
            "files": ["src/blocked.py"],
        }
        action_id = guards.log_blocked_action(decision, "Test reason")
        assert action_id.startswith("blocked-")
        assert len(guards._blocked_actions) == 1
        blocked = guards._blocked_actions[0]
        assert blocked.action_id == action_id
        assert blocked.reason == "Test reason"
        assert blocked.risk_level == "high"

    def test_get_blocked_actions_summary_empty(self):
        """Test getting summary when no actions blocked."""
        guards = ActionGuards()
        summary = guards.get_blocked_actions_summary()
        assert summary["total_blocked"] == 0
        assert summary["by_risk_level"] == {}
        assert summary["recent_blocked"] == []

    def test_get_blocked_actions_summary_with_blocks(self):
        """Test getting summary with blocked actions."""
        guards = ActionGuards()

        # Add some blocked actions
        guards.log_blocked_action(
            {"risk_level": "high", "action": "action1"}, "Risk limit exceeded"
        )
        guards.log_blocked_action(
            {"risk_level": "critical", "action": "action2"}, "Protected file"
        )
        guards.log_blocked_action(
            {"risk_level": "high", "action": "action3"}, "Risk limit exceeded"
        )

        summary = guards.get_blocked_actions_summary()
        assert summary["total_blocked"] == 3
        assert summary["by_risk_level"]["high"] == 2
        assert summary["by_risk_level"]["critical"] == 1
        assert summary["by_reason_category"]["risk_limit"] == 2
        assert summary["by_reason_category"]["protected_file"] == 1
        assert len(summary["recent_blocked"]) == 3

    def test_get_audit_trail(self):
        """Test getting audit trail."""
        guards = ActionGuards()

        # Create some actions
        decision1 = {"risk_level": "low", "action": "action1", "description": "Test 1"}
        decision2 = {
            "risk_level": "medium",
            "action": "action2",
            "description": "Test 2",
        }

        guards.validate_auto_action(decision1)
        guards.validate_auto_action(decision2)

        trail = guards.get_audit_trail()
        assert len(trail) == 2
        assert trail[0]["action"] == "action2"  # Most recent first
        assert trail[1]["action"] == "action1"

    def test_get_audit_trail_with_limit(self):
        """Test getting audit trail with limit."""
        guards = ActionGuards()

        for i in range(5):
            guards.validate_auto_action(
                {
                    "risk_level": "low",
                    "action": f"action{i}",
                    "description": f"Test {i}",
                }
            )

        trail = guards.get_audit_trail(limit=3)
        assert len(trail) == 3

    def test_get_audit_trail_with_filter(self):
        """Test getting audit trail with action type filter."""
        guards = ActionGuards()

        guards.validate_auto_action(
            {
                "risk_level": "low",
                "action": "special_action",
                "description": "Special",
            }
        )
        guards.validate_auto_action(
            {
                "risk_level": "low",
                "action": "other_action",
                "description": "Other",
            }
        )

        trail = guards.get_audit_trail(action_type="special_action")
        assert len(trail) == 1
        assert trail[0]["action"] == "special_action"

    def test_clear_audit_trail(self):
        """Test clearing audit trail."""
        guards = ActionGuards()

        guards.validate_auto_action(
            {
                "risk_level": "low",
                "action": "action1",
                "description": "Test",
            }
        )
        guards.log_blocked_action(
            {"risk_level": "high", "action": "action2"}, "Blocked"
        )

        assert len(guards._audit_log) > 0
        assert len(guards._blocked_actions) > 0

        guards.clear_audit_trail()

        assert len(guards._audit_log) == 0
        assert len(guards._blocked_actions) == 0

    def test_get_policy_engine(self):
        """Test getting policy engine."""
        engine = AutonomousPolicyEngine()
        guards = ActionGuards(policy_engine=engine)
        assert guards.get_policy_engine() is engine

    def test_reload_policies(self):
        """Test reloading policies."""
        guards = ActionGuards()
        # Should not raise
        guards.reload_policies()

    def test_fail_closed_on_validation_error(self):
        """Test that validation errors result in fail-closed behavior."""
        guards = ActionGuards()

        # Mock policy engine to raise exception
        guards._policy_engine = MagicMock()
        guards._policy_engine.validate_decision.side_effect = Exception("Test error")

        decision = {
            "risk_level": "low",
            "action": "test_action",
            "description": "Test",
        }

        result = guards.validate_auto_action(decision)
        assert result.allowed is False
        assert result.blocked is True
        assert "Validation error" in result.reason

    def test_redis_integration_blocked_action(self):
        """Test Redis integration for blocked actions."""
        mock_redis = MagicMock()
        guards = ActionGuards(redis_client=mock_redis)

        decision = {
            "risk_level": "high",
            "action": "blocked_action",
            "description": "Blocked",
        }

        guards.log_blocked_action(decision, "Test reason")

        # Verify Redis was called
        mock_redis.lpush.assert_called_once()
        call_args = mock_redis.lpush.call_args
        assert call_args[0][0] == guards.REDIS_BLOCKED_ACTIONS_KEY

    def test_redis_integration_audit_log(self):
        """Test Redis integration for audit log."""
        mock_redis = MagicMock()
        guards = ActionGuards(redis_client=mock_redis, max_risk_level="medium")

        decision = {
            "risk_level": "low",
            "action": "test_action",
            "description": "Test",
        }

        guards.validate_auto_action(decision)

        # Verify Redis was called for audit log
        mock_redis.lpush.assert_called()
        # Should be called for both blocked actions and audit log
        assert any(
            call[0][0] == guards.REDIS_AUDIT_LOG_KEY
            for call in mock_redis.lpush.call_args_list
        )

    def test_risk_level_ordering(self):
        """Test that risk level ordering is correct."""
        guards = ActionGuards()
        order = guards._risk_order
        assert order["low"] < order["medium"]
        assert order["medium"] < order["high"]
        assert order["high"] < order["critical"]


class TestBlockedAction:
    """Test cases for BlockedAction dataclass."""

    def test_blocked_action_creation(self):
        """Test creating a BlockedAction."""
        action = BlockedAction(
            action_id="test-123",
            timestamp="2026-03-16T10:00:00Z",
            decision={"action": "test"},
            reason="Test reason",
            risk_level="high",
            files=["src/test.py"],
        )
        assert action.action_id == "test-123"
        assert action.risk_level == "high"
        assert action.files == ["src/test.py"]

    def test_blocked_action_default_files(self):
        """Test BlockedAction with default empty files."""
        action = BlockedAction(
            action_id="test-123",
            timestamp="2026-03-16T10:00:00Z",
            decision={"action": "test"},
            reason="Test reason",
            risk_level="high",
        )
        assert action.files == []


class TestActionResult:
    """Test cases for ActionResult dataclass."""

    def test_action_result_creation(self):
        """Test creating an ActionResult."""
        result = ActionResult(
            allowed=True,
            reason="Test passed",
            risk_level="low",
            requires_approval=False,
            blocked=False,
            audit_log_id="action-123",
        )
        assert result.allowed is True
        assert result.reason == "Test passed"
        assert result.audit_log_id == "action-123"

    def test_action_result_defaults(self):
        """Test ActionResult with default values."""
        result = ActionResult(allowed=False)
        assert result.reason == ""
        assert result.risk_level == "unknown"
        assert result.requires_approval is False
        assert result.blocked is False
        assert result.audit_log_id == ""
