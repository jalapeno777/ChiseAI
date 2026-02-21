"""Tests for live gating gate manager.

Tests state transitions, approval flow, and kill-switch integration.
"""

from __future__ import annotations

import pytest
from datetime import UTC, datetime, timedelta

from execution.live_gating.gate_manager import (
    ApprovalPacket,
    LiveGateConfig,
    LiveGateManager,
    LiveTradingState,
    PaperTradingEvidence,
)


class TestLiveTradingState:
    """Test LiveTradingState enum."""

    def test_state_values(self):
        """Test state enum values."""
        assert LiveTradingState.DISABLED.value == "disabled"
        assert LiveTradingState.PENDING_APPROVAL.value == "pending_approval"
        assert LiveTradingState.APPROVED.value == "approved"
        assert LiveTradingState.ACTIVE.value == "active"

    def test_state_string_representation(self):
        """Test state string representation."""
        assert str(LiveTradingState.DISABLED) == "disabled"
        assert str(LiveTradingState.ACTIVE) == "active"


class TestLiveGateConfig:
    """Test LiveGateConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = LiveGateConfig()
        assert config.leverage_cap == 3.0
        assert config.daily_loss_cap == 1000.0
        assert config.require_human_approval is True
        assert config.min_paper_trading_days == 30
        assert config.min_sharpe_ratio == 0.0
        assert config.max_drawdown_pct == 10.0

    def test_leverage_cap_enforcement(self):
        """Test leverage cap is enforced at 3.0 max."""
        config = LiveGateConfig(leverage_cap=5.0)
        assert config.leverage_cap == 3.0  # Should be capped

    def test_invalid_leverage(self):
        """Test invalid leverage raises error."""
        with pytest.raises(ValueError, match="Leverage cap must be positive"):
            LiveGateConfig(leverage_cap=0)

    def test_invalid_daily_loss_cap(self):
        """Test invalid daily loss cap raises error."""
        with pytest.raises(ValueError, match="Daily loss cap must be positive"):
            LiveGateConfig(daily_loss_cap=-100)

    def test_to_dict(self):
        """Test config serialization."""
        config = LiveGateConfig(leverage_cap=2.0, daily_loss_cap=500.0)
        d = config.to_dict()
        assert d["leverage_cap"] == 2.0
        assert d["daily_loss_cap"] == 500.0
        assert d["require_human_approval"] is True


class TestPaperTradingEvidence:
    """Test PaperTradingEvidence dataclass."""

    def test_meets_prerequisites_success(self):
        """Test prerequisite check with valid evidence."""
        now = datetime.now(UTC)
        evidence = PaperTradingEvidence(
            duration_days=35.0,
            total_trades=100,
            win_rate_pct=55.0,
            sharpe_ratio=1.5,
            max_drawdown_pct=8.0,
            realized_pnl=1000.0,
            start_date=now - timedelta(days=35),
            end_date=now,
            strategy_id="test-strategy",
        )
        config = LiveGateConfig()
        meets, failures = evidence.meets_prerequisites(config)
        assert meets is True
        assert len(failures) == 0

    def test_meets_prerequisites_duration_failure(self):
        """Test prerequisite check fails on insufficient duration."""
        now = datetime.now(UTC)
        evidence = PaperTradingEvidence(
            duration_days=20.0,  # Less than 30
            total_trades=100,
            win_rate_pct=55.0,
            sharpe_ratio=1.5,
            max_drawdown_pct=8.0,
            realized_pnl=1000.0,
            start_date=now - timedelta(days=20),
            end_date=now,
        )
        config = LiveGateConfig()
        meets, failures = evidence.meets_prerequisites(config)
        assert meets is False
        assert any("duration" in f.lower() for f in failures)

    def test_meets_prerequisites_sharpe_failure(self):
        """Test prerequisite check fails on negative Sharpe."""
        now = datetime.now(UTC)
        evidence = PaperTradingEvidence(
            duration_days=35.0,
            total_trades=100,
            win_rate_pct=55.0,
            sharpe_ratio=-0.5,  # Negative
            max_drawdown_pct=8.0,
            realized_pnl=-100.0,
            start_date=now - timedelta(days=35),
            end_date=now,
        )
        config = LiveGateConfig()
        meets, failures = evidence.meets_prerequisites(config)
        assert meets is False
        assert any("sharpe" in f.lower() for f in failures)

    def test_meets_prerequisites_drawdown_failure(self):
        """Test prerequisite check fails on excessive drawdown."""
        now = datetime.now(UTC)
        evidence = PaperTradingEvidence(
            duration_days=35.0,
            total_trades=100,
            win_rate_pct=55.0,
            sharpe_ratio=1.5,
            max_drawdown_pct=15.0,  # Exceeds 10%
            realized_pnl=1000.0,
            start_date=now - timedelta(days=35),
            end_date=now,
        )
        config = LiveGateConfig()
        meets, failures = evidence.meets_prerequisites(config)
        assert meets is False
        assert any("drawdown" in f.lower() for f in failures)

    def test_meets_prerequisites_min_trades(self):
        """Test prerequisite check warns on low trade count."""
        now = datetime.now(UTC)
        evidence = PaperTradingEvidence(
            duration_days=35.0,
            total_trades=30,  # Less than 50
            win_rate_pct=55.0,
            sharpe_ratio=1.5,
            max_drawdown_pct=8.0,
            realized_pnl=1000.0,
            start_date=now - timedelta(days=35),
            end_date=now,
        )
        config = LiveGateConfig()
        meets, failures = evidence.meets_prerequisites(config)
        # Should still pass but with warning about trades
        assert any("trades" in f.lower() for f in failures)


class TestApprovalPacket:
    """Test ApprovalPacket dataclass."""

    def test_verify_signature_valid(self):
        """Test signature verification with valid signature."""
        now = datetime.now(UTC)
        evidence = PaperTradingEvidence(
            duration_days=35.0,
            total_trades=100,
            win_rate_pct=55.0,
            sharpe_ratio=1.5,
            max_drawdown_pct=8.0,
            realized_pnl=1000.0,
            start_date=now - timedelta(days=35),
            end_date=now,
        )
        packet = ApprovalPacket(
            approver_id="admin",
            timestamp=now,
            signature="a" * 32,  # Valid length signature
            paper_evidence=evidence,
            request_id="REQ-123",
        )
        assert packet.verify_signature() is True

    def test_verify_signature_empty(self):
        """Test signature verification with empty signature."""
        now = datetime.now(UTC)
        evidence = PaperTradingEvidence(
            duration_days=35.0,
            total_trades=100,
            win_rate_pct=55.0,
            sharpe_ratio=1.5,
            max_drawdown_pct=8.0,
            realized_pnl=1000.0,
            start_date=now,
            end_date=now,
        )
        packet = ApprovalPacket(
            approver_id="admin",
            timestamp=now,
            signature="",  # Empty
            paper_evidence=evidence,
            request_id="REQ-123",
        )
        assert packet.verify_signature() is False

    def test_verify_signature_too_short(self):
        """Test signature verification with short signature."""
        now = datetime.now(UTC)
        evidence = PaperTradingEvidence(
            duration_days=35.0,
            total_trades=100,
            win_rate_pct=55.0,
            sharpe_ratio=1.5,
            max_drawdown_pct=8.0,
            realized_pnl=1000.0,
            start_date=now,
            end_date=now,
        )
        packet = ApprovalPacket(
            approver_id="admin",
            timestamp=now,
            signature="short",  # Too short
            paper_evidence=evidence,
            request_id="REQ-123",
        )
        assert packet.verify_signature() is False


class TestLiveGateManager:
    """Test LiveGateManager class."""

    def test_initial_state(self):
        """Test initial state is DISABLED."""
        manager = LiveGateManager()
        assert manager.get_state() == LiveTradingState.DISABLED
        assert manager.is_live_enabled is False

    def test_check_prerequisites(self):
        """Test prerequisite checking."""
        manager = LiveGateManager()
        now = datetime.now(UTC)
        evidence = PaperTradingEvidence(
            duration_days=35.0,
            total_trades=100,
            win_rate_pct=55.0,
            sharpe_ratio=1.5,
            max_drawdown_pct=8.0,
            realized_pnl=1000.0,
            start_date=now - timedelta(days=35),
            end_date=now,
        )
        failures = manager.check_prerequisites(evidence)
        assert len(failures) == 0

    def test_request_approval(self):
        """Test approval request submission."""
        manager = LiveGateManager()
        now = datetime.now(UTC)
        evidence = PaperTradingEvidence(
            duration_days=35.0,
            total_trades=100,
            win_rate_pct=55.0,
            sharpe_ratio=1.5,
            max_drawdown_pct=8.0,
            realized_pnl=1000.0,
            start_date=now - timedelta(days=35),
            end_date=now,
        )
        request = manager.request_approval(evidence)
        assert request.request_id.startswith("REQ-")
        assert request.status == "pending"
        assert manager.get_state() == LiveTradingState.PENDING_APPROVAL

    def test_request_approval_already_pending(self):
        """Test cannot request approval when already pending."""
        manager = LiveGateManager()
        now = datetime.now(UTC)
        evidence = PaperTradingEvidence(
            duration_days=35.0,
            total_trades=100,
            win_rate_pct=55.0,
            sharpe_ratio=1.5,
            max_drawdown_pct=8.0,
            realized_pnl=1000.0,
            start_date=now - timedelta(days=35),
            end_date=now,
        )
        manager.request_approval(evidence)
        with pytest.raises(RuntimeError, match="already pending"):
            manager.request_approval(evidence)

    def test_approve_success(self):
        """Test successful approval."""
        manager = LiveGateManager()
        now = datetime.now(UTC)
        evidence = PaperTradingEvidence(
            duration_days=35.0,
            total_trades=100,
            win_rate_pct=55.0,
            sharpe_ratio=1.5,
            max_drawdown_pct=8.0,
            realized_pnl=1000.0,
            start_date=now - timedelta(days=35),
            end_date=now,
        )
        request = manager.request_approval(evidence)
        packet = ApprovalPacket(
            approver_id="admin",
            timestamp=now,
            signature="a" * 32,
            paper_evidence=evidence,
            request_id=request.request_id,
        )
        result = manager.approve(packet)
        assert result is True
        assert manager.get_state() == LiveTradingState.APPROVED
        assert manager.last_approval == packet

    def test_approve_wrong_state(self):
        """Test cannot approve when not pending."""
        manager = LiveGateManager()
        now = datetime.now(UTC)
        evidence = PaperTradingEvidence(
            duration_days=35.0,
            total_trades=100,
            win_rate_pct=55.0,
            sharpe_ratio=1.5,
            max_drawdown_pct=8.0,
            realized_pnl=1000.0,
            start_date=now,
            end_date=now,
        )
        packet = ApprovalPacket(
            approver_id="admin",
            timestamp=now,
            signature="a" * 32,
            paper_evidence=evidence,
            request_id="REQ-123",
        )
        with pytest.raises(RuntimeError, match="Cannot approve"):
            manager.approve(packet)

    def test_approve_invalid_signature(self):
        """Test approval fails with invalid signature."""
        manager = LiveGateManager()
        now = datetime.now(UTC)
        evidence = PaperTradingEvidence(
            duration_days=35.0,
            total_trades=100,
            win_rate_pct=55.0,
            sharpe_ratio=1.5,
            max_drawdown_pct=8.0,
            realized_pnl=1000.0,
            start_date=now - timedelta(days=35),
            end_date=now,
        )
        request = manager.request_approval(evidence)
        packet = ApprovalPacket(
            approver_id="admin",
            timestamp=now,
            signature="short",  # Invalid
            paper_evidence=evidence,
            request_id=request.request_id,
        )
        with pytest.raises(ValueError, match="Invalid approval signature"):
            manager.approve(packet)

    def test_reject(self):
        """Test rejection of approval request."""
        manager = LiveGateManager()
        now = datetime.now(UTC)
        evidence = PaperTradingEvidence(
            duration_days=35.0,
            total_trades=100,
            win_rate_pct=55.0,
            sharpe_ratio=1.5,
            max_drawdown_pct=8.0,
            realized_pnl=1000.0,
            start_date=now - timedelta(days=35),
            end_date=now,
        )
        manager.request_approval(evidence)
        result = manager.reject("Insufficient evidence")
        assert result is True
        assert manager.get_state() == LiveTradingState.DISABLED

    def test_enable_live_trading(self):
        """Test enabling live trading after approval."""
        manager = LiveGateManager()
        now = datetime.now(UTC)
        evidence = PaperTradingEvidence(
            duration_days=35.0,
            total_trades=100,
            win_rate_pct=55.0,
            sharpe_ratio=1.5,
            max_drawdown_pct=8.0,
            realized_pnl=1000.0,
            start_date=now - timedelta(days=35),
            end_date=now,
        )
        request = manager.request_approval(evidence)
        packet = ApprovalPacket(
            approver_id="admin",
            timestamp=now,
            signature="a" * 32,
            paper_evidence=evidence,
            request_id=request.request_id,
        )
        manager.approve(packet)
        result = manager.enable_live_trading()
        assert result is True
        assert manager.get_state() == LiveTradingState.ACTIVE
        assert manager.is_live_enabled is True

    def test_enable_without_approval(self):
        """Test cannot enable without approval."""
        manager = LiveGateManager()
        with pytest.raises(RuntimeError, match="Cannot enable"):
            manager.enable_live_trading()

    def test_disable_live_trading(self):
        """Test disabling live trading."""
        manager = LiveGateManager()
        now = datetime.now(UTC)
        evidence = PaperTradingEvidence(
            duration_days=35.0,
            total_trades=100,
            win_rate_pct=55.0,
            sharpe_ratio=1.5,
            max_drawdown_pct=8.0,
            realized_pnl=1000.0,
            start_date=now - timedelta(days=35),
            end_date=now,
        )
        request = manager.request_approval(evidence)
        packet = ApprovalPacket(
            approver_id="admin",
            timestamp=now,
            signature="a" * 32,
            paper_evidence=evidence,
            request_id=request.request_id,
        )
        manager.approve(packet)
        manager.enable_live_trading()

        result = manager.disable_live_trading("Kill-switch triggered")
        assert result is True
        assert manager.get_state() == LiveTradingState.DISABLED
        assert manager.is_live_enabled is False
        assert manager.last_approval is None  # Reset after disable

    def test_disable_already_disabled(self):
        """Test disabling when already disabled."""
        manager = LiveGateManager()
        result = manager.disable_live_trading("Test")
        assert result is True  # Idempotent

    def test_state_history(self):
        """Test state transition history."""
        manager = LiveGateManager()
        now = datetime.now(UTC)
        evidence = PaperTradingEvidence(
            duration_days=35.0,
            total_trades=100,
            win_rate_pct=55.0,
            sharpe_ratio=1.5,
            max_drawdown_pct=8.0,
            realized_pnl=1000.0,
            start_date=now - timedelta(days=35),
            end_date=now,
        )
        request = manager.request_approval(evidence)
        packet = ApprovalPacket(
            approver_id="admin",
            timestamp=now,
            signature="a" * 32,
            paper_evidence=evidence,
            request_id=request.request_id,
        )
        manager.approve(packet)
        manager.enable_live_trading()

        history = manager.get_state_history()
        assert len(history) >= 3  # At least 3 transitions
        assert history[0]["old_state"] == "disabled"
        assert history[-1]["new_state"] == "active"

    def test_update_daily_pnl_within_cap(self):
        """Test daily PnL update within cap."""
        manager = LiveGateManager(LiveGateConfig(daily_loss_cap=1000.0))
        result = manager.update_daily_pnl(-500.0)
        assert result is True
        assert manager.get_status()["daily_pnl"] == -500.0

    def test_update_daily_pnl_exceeds_cap(self):
        """Test daily PnL update exceeds cap disables trading."""
        manager = LiveGateManager(LiveGateConfig(daily_loss_cap=100.0))

        # First set up as active
        now = datetime.now(UTC)
        evidence = PaperTradingEvidence(
            duration_days=35.0,
            total_trades=100,
            win_rate_pct=55.0,
            sharpe_ratio=1.5,
            max_drawdown_pct=8.0,
            realized_pnl=1000.0,
            start_date=now - timedelta(days=35),
            end_date=now,
        )
        request = manager.request_approval(evidence)
        packet = ApprovalPacket(
            approver_id="admin",
            timestamp=now,
            signature="a" * 32,
            paper_evidence=evidence,
            request_id=request.request_id,
        )
        manager.approve(packet)
        manager.enable_live_trading()

        # Now exceed daily loss cap
        result = manager.update_daily_pnl(-200.0)
        assert result is False
        assert manager.get_state() == LiveTradingState.DISABLED

    def test_get_status(self):
        """Test getting comprehensive status."""
        manager = LiveGateManager()
        status = manager.get_status()
        assert status["state"] == "disabled"
        assert status["is_live_enabled"] is False
        assert "config" in status
        assert "current_request" in status

    def test_approval_wrong_request_id(self):
        """Test approval fails with wrong request ID."""
        manager = LiveGateManager()
        now = datetime.now(UTC)
        evidence = PaperTradingEvidence(
            duration_days=35.0,
            total_trades=100,
            win_rate_pct=55.0,
            sharpe_ratio=1.5,
            max_drawdown_pct=8.0,
            realized_pnl=1000.0,
            start_date=now - timedelta(days=35),
            end_date=now,
        )
        manager.request_approval(evidence)
        packet = ApprovalPacket(
            approver_id="admin",
            timestamp=now,
            signature="a" * 32,
            paper_evidence=evidence,
            request_id="WRONG-REQ-ID",
        )
        with pytest.raises(ValueError, match="does not match"):
            manager.approve(packet)
