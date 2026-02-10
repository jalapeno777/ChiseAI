"""Tests for alert manager."""

import pytest

from portfolio.state_management.risk_calculator import (
    MarginUtilization,
    RiskMetrics,
    TokenExposure,
)
from portfolio_risk.alerts.manager import RiskAlertManager
from portfolio_risk.alerts.types import (
    AlertSeverity,
    AlertThresholds,
    AlertType,
    RiskAlert,
)
from datetime import UTC, datetime


class TestRiskAlertManager:
    """Test RiskAlertManager class."""

    def create_test_metrics(
        self,
        net_exposure: float = 1000.0,
        total_equity: float = 10000.0,
        margin_used: float = 5000.0,
        concentration_risk: float = 30.0,
    ) -> RiskMetrics:
        """Helper to create test risk metrics."""
        margin_util = MarginUtilization(
            margin_used=margin_used,
            total_equity=total_equity,
            available_equity=total_equity - margin_used,
        )

        return RiskMetrics(
            timestamp=datetime.now(UTC),
            portfolio_id="test_portfolio",
            total_exposure=net_exposure,
            net_exposure=net_exposure,
            gross_exposure=net_exposure,
            margin_utilization=margin_util,
            token_exposures=[
                TokenExposure(token="BTC", long_notional=net_exposure),
            ],
            long_exposure=net_exposure,
            short_exposure=0.0,
            concentration_risk=concentration_risk,
        )

    def test_initialization_defaults(self):
        """Test manager initialization with defaults."""
        manager = RiskAlertManager()

        assert manager.thresholds.exposure_threshold_pct == 80.0
        assert manager.detector is not None
        assert manager.sender is not None

    def test_initialization_custom(self):
        """Test manager initialization with custom thresholds."""
        thresholds = AlertThresholds(
            exposure_threshold_pct=70.0,
            margin_utilization_threshold_pct=75.0,
            concentration_threshold_pct=40.0,
        )
        manager = RiskAlertManager(thresholds=thresholds)

        assert manager.thresholds.exposure_threshold_pct == 70.0

    @pytest.mark.asyncio
    async def test_initialize(self):
        """Test manager initialization."""
        manager = RiskAlertManager()
        result = await manager.initialize()

        # Will be False because no webhook configured
        assert result is False

    @pytest.mark.asyncio
    async def test_process_risk_metrics_no_alerts(self):
        """Test processing metrics with no alerts."""
        manager = RiskAlertManager()

        # Normal metrics - no alerts
        metrics = self.create_test_metrics(
            net_exposure=5000.0,
            total_equity=10000.0,
            margin_used=5000.0,
            concentration_risk=30.0,
        )

        results = await manager.process_risk_metrics(metrics)

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_process_risk_metrics_with_alerts(self):
        """Test processing metrics with alerts."""
        manager = RiskAlertManager()

        # Metrics that trigger alerts
        metrics = self.create_test_metrics(
            net_exposure=9000.0,  # 90% exposure
            total_equity=10000.0,
            margin_used=8500.0,  # 85% margin
            concentration_risk=60.0,  # 60% concentration
        )

        results = await manager.process_risk_metrics(metrics)

        # Should have 3 alerts (all will fail due to no webhook)
        assert len(results) == 3

    def test_check_kill_switch_no_trigger(self):
        """Test kill-switch check with no trigger."""
        manager = RiskAlertManager()

        metrics = self.create_test_metrics(
            net_exposure=5000.0,
            total_equity=10000.0,
            margin_used=5000.0,
            concentration_risk=30.0,
        )

        kill_switch = manager.check_kill_switch(metrics)

        assert kill_switch is None

    def test_check_kill_switch_triggered(self):
        """Test kill-switch check with trigger."""
        manager = RiskAlertManager()

        metrics = self.create_test_metrics(
            net_exposure=5000.0,
            total_equity=10000.0,
            margin_used=9700.0,  # 97% margin - critical
            concentration_risk=30.0,
        )

        kill_switch = manager.check_kill_switch(metrics)

        assert kill_switch is not None
        assert kill_switch.alert_type == AlertType.KILL_SWITCH

    @pytest.mark.asyncio
    async def test_send_kill_switch_alert(self):
        """Test sending kill-switch alert."""
        manager = RiskAlertManager()

        alert = RiskAlert(
            alert_type=AlertType.KILL_SWITCH,
            severity=AlertSeverity.EMERGENCY,
            message="KILL SWITCH ACTIVATED",
            threshold=95.0,
            current_value=97.0,
            portfolio_id="test",
        )

        result = await manager.send_kill_switch_alert(alert)

        # Will fail due to no webhook, but tests the path
        assert result.alert_type == "kill_switch"

    def test_update_thresholds(self):
        """Test updating thresholds."""
        manager = RiskAlertManager()

        new_thresholds = AlertThresholds(
            exposure_threshold_pct=60.0,
            margin_utilization_threshold_pct=70.0,
            concentration_threshold_pct=40.0,
        )

        manager.update_thresholds(new_thresholds)

        assert manager.thresholds.exposure_threshold_pct == 60.0
        assert manager.detector.thresholds.exposure_threshold_pct == 60.0

    def test_get_stats(self):
        """Test getting stats."""
        manager = RiskAlertManager()
        stats = manager.get_stats()

        assert "thresholds" in stats
        assert "sender" in stats
        assert stats["thresholds"]["exposure_threshold_pct"] == 80.0

    @pytest.mark.asyncio
    async def test_health_check(self):
        """Test health check."""
        manager = RiskAlertManager()
        health = await manager.health_check()

        assert "healthy" in health
        assert "sender" in health
        assert "thresholds" in health

    @pytest.mark.asyncio
    async def test_close(self):
        """Test closing manager."""
        manager = RiskAlertManager()

        # Should not raise
        await manager.close()
