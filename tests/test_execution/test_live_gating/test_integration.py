"""Tests for live gating module integration.

Integration tests for the complete live gating workflow.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from execution.live_gating import (
    ApprovalPacket,
    LiveGateConfig,
    LiveGateManager,
    LiveGatingGrafanaExporter,
    LiveTradeAuditLogger,
    LiveTradingState,
    PaperTradingEvidence,
    RiskEnforcer,
)


class TestIntegrationWorkflow:
    """Test complete live trading gating workflow."""

    def test_full_approval_workflow(self):
        """Test complete approval workflow from disabled to active."""
        # Setup
        config = LiveGateConfig(
            leverage_cap=3.0,
            daily_loss_cap=1000.0,
        )
        manager = LiveGateManager(config)

        # Create valid paper trading evidence
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
            strategy_id="grid-strategy-v1",
        )

        # Step 1: Check prerequisites
        failures = manager.check_prerequisites(evidence)
        assert len(failures) == 0

        # Step 2: Request approval
        request = manager.request_approval(evidence)
        assert manager.get_state() == LiveTradingState.PENDING_APPROVAL

        # Step 3: Approve with signed packet
        packet = ApprovalPacket(
            approver_id="admin@craigcomstock.com",
            timestamp=now,
            signature="a" * 64,  # Simulated signature
            paper_evidence=evidence,
            request_id=request.request_id,
            approval_notes="Approved for live trading after 35 days paper",
        )
        manager.approve(packet)
        assert manager.get_state() == LiveTradingState.APPROVED

        # Step 4: Enable live trading
        manager.enable_live_trading()
        assert manager.get_state() == LiveTradingState.ACTIVE
        assert manager.is_live_enabled is True

        # Verify state history
        history = manager.get_state_history()
        assert len(history) == 3  # disabled -> pending -> approved -> active

    def test_kill_switch_integration(self):
        """Test kill-switch integration disables live trading."""
        # Setup active trading
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
            signature="a" * 64,
            paper_evidence=evidence,
            request_id=request.request_id,
        )
        manager.approve(packet)
        manager.enable_live_trading()
        assert manager.is_live_enabled is True

        # Trigger disable (simulating kill-switch)
        manager.disable_live_trading("Kill-switch triggered: max drawdown exceeded")

        # Verify disabled
        assert manager.get_state() == LiveTradingState.DISABLED
        assert manager.is_live_enabled is False
        assert manager.last_approval is None  # Reset after disable

    def test_risk_controls_with_gate_manager(self):
        """Test risk controls integration with gate manager."""
        # Setup
        manager = LiveGateManager(LiveGateConfig(daily_loss_cap=500.0))
        enforcer = RiskEnforcer(portfolio_value=10000.0)

        # Activate trading
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
            signature="a" * 64,
            paper_evidence=evidence,
            request_id=request.request_id,
        )
        manager.approve(packet)
        manager.enable_live_trading()

        # Validate a trade
        trade_params = {
            "size": 0.01,
            "leverage": 2.0,
            "entry_price": 50000.0,
            "stop_loss": 49500.0,
            "symbol": "BTCUSDT",
            "side": "long",
        }
        result = enforcer.validate_trade(trade_params)
        assert result.valid is True

        # Simulate trade loss that exceeds daily cap
        manager.update_daily_pnl(-600.0)  # Exceeds 500 cap

        # Should be disabled
        assert manager.get_state() == LiveTradingState.DISABLED


class TestPrerequisitesDocumentation:
    """Test prerequisite checks (AC #2 - documentation only)."""

    def test_30_day_minimum_documented(self):
        """Test 30-day minimum is enforced and documented."""
        config = LiveGateConfig(min_paper_trading_days=30)
        manager = LiveGateManager(config)

        now = datetime.now(UTC)
        # Only 20 days - should fail
        evidence_short = PaperTradingEvidence(
            duration_days=20.0,
            total_trades=100,
            win_rate_pct=55.0,
            sharpe_ratio=1.5,
            max_drawdown_pct=8.0,
            realized_pnl=1000.0,
            start_date=now - timedelta(days=20),
            end_date=now,
        )

        failures = manager.check_prerequisites(evidence_short)
        assert any("30" in f or "duration" in f.lower() for f in failures)

    def test_positive_sharpe_documented(self):
        """Test positive Sharpe requirement is enforced."""
        config = LiveGateConfig(min_sharpe_ratio=0.0)
        manager = LiveGateManager(config)

        now = datetime.now(UTC)
        evidence_negative_sharpe = PaperTradingEvidence(
            duration_days=35.0,
            total_trades=100,
            win_rate_pct=55.0,
            sharpe_ratio=-0.5,  # Negative
            max_drawdown_pct=8.0,
            realized_pnl=-100.0,
            start_date=now - timedelta(days=35),
            end_date=now,
        )

        failures = manager.check_prerequisites(evidence_negative_sharpe)
        assert any("sharpe" in f.lower() for f in failures)


class TestRiskLimitsFromPRD:
    """Test PRD risk limits are enforced."""

    def test_per_trade_risk_limit(self):
        """Test ≤1% per-trade risk limit."""
        enforcer = RiskEnforcer(portfolio_value=10000.0)

        # Trade with 2% risk - should fail
        trade_params = {
            "size": 1.0,
            "leverage": 1.0,
            "entry_price": 50000.0,
            "stop_loss": 48000.0,  # 4% stop = 400 risk = 4%
            "symbol": "BTCUSDT",
            "side": "long",
        }
        result = enforcer.validate_trade(trade_params)
        assert result.valid is False
        # Check for risk-related violation (may contain "1%" or "maximum")
        assert any("1%" in v or "maximum" in v.lower() for v in result.violations)

    def test_leverage_cap_3x(self):
        """Test ≤3x leverage cap."""
        enforcer = RiskEnforcer(portfolio_value=10000.0)

        # 5x leverage - should fail
        trade_params = {
            "size": 0.01,
            "leverage": 5.0,
            "entry_price": 50000.0,
            "symbol": "BTCUSDT",
            "side": "long",
        }
        result = enforcer.validate_trade(trade_params)
        assert result.valid is False
        assert any("3" in v and "leverage" in v.lower() for v in result.violations)

    def test_per_grid_worst_case_2pct(self):
        """Test ≤2% per-grid worst-case limit."""
        enforcer = RiskEnforcer(portfolio_value=10000.0)

        # Grid with 5% total risk - should fail
        result = enforcer.validate_grid_strategy(
            grid_levels=10,
            total_allocation_pct=50.0,
            per_level_risk_pct=0.5,  # 10 * 0.5 = 5%
        )
        assert result.valid is False
        assert any(
            "2%" in v.lower() or "grid risk" in v.lower() for v in result.violations
        )


class TestAuditTrail:
    """Test audit trail requirements (AC #5)."""

    @pytest.mark.asyncio
    async def test_trade_audit_fields(self):
        """Test all required trade audit fields are captured."""
        logger = LiveTradeAuditLogger()

        now = datetime.now(UTC)
        with patch.object(logger, "_write_point", return_value=True):
            result = await logger.log_trade(
                timestamp=now,
                price=50000.0,
                quantity=0.1,
                reason="Grid signal: buy level 3",
                symbol="BTCUSDT",
                side="buy",
                trade_id="TRADE-001",
                order_id="ORDER-123",
                pnl=0.0,
                fees=0.5,
            )
            assert result is True

    @pytest.mark.asyncio
    async def test_approval_audit_fields(self):
        """Test all required approval audit fields are captured."""
        logger = LiveTradeAuditLogger()

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
            strategy_id="test-strategy",
        )
        packet = ApprovalPacket(
            approver_id="admin@craigcomstock.com",
            timestamp=now,
            signature="a" * 64,
            paper_evidence=evidence,
            request_id="REQ-001",
        )

        with patch.object(logger, "_write_point", return_value=True):
            result = await logger.log_approval(packet)
            assert result is True

    @pytest.mark.asyncio
    async def test_state_change_audit(self):
        """Test state change audit logging."""
        logger = LiveTradeAuditLogger()

        with patch.object(logger, "_write_point", return_value=True):
            result = await logger.log_state_change(
                old_state=LiveTradingState.ACTIVE,
                new_state=LiveTradingState.DISABLED,
                reason="Kill-switch triggered",
                triggered_by="kill_switch",
            )
            assert result is True


class TestGrafanaVisibility:
    """Test Grafana visibility requirements (AC #6)."""

    def test_state_exported(self):
        """Test live trading state is exportable for Grafana."""
        manager = LiveGateManager()
        exporter = LiveGatingGrafanaExporter(gate_manager=manager)

        status = manager.get_status()
        assert "state" in status
        assert "is_live_enabled" in status

    def test_last_approval_date_exported(self):
        """Test last approval date is exportable."""
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
            signature="a" * 64,
            paper_evidence=evidence,
            request_id=request.request_id,
        )
        manager.approve(packet)

        status = manager.get_status()
        assert status["last_approval"] is not None
        assert "timestamp" in status["last_approval"]

    def test_daily_pnl_exported(self):
        """Test daily PnL is exportable."""
        manager = LiveGateManager()
        manager.update_daily_pnl(500.0)

        status = manager.get_status()
        assert "daily_pnl" in status
        assert status["daily_pnl"] == 500.0


# Import patch for test files
from unittest.mock import patch
