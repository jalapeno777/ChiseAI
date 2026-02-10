"""Tests for alert detector."""

from datetime import datetime, timezone

import pytest

from portfolio.state_management.risk_calculator import (
    MarginUtilization,
    RiskLevel,
    RiskMetrics,
    TokenExposure,
)
from portfolio_risk.alerts.detector import RiskAlertDetector
from portfolio_risk.alerts.types import (
    AlertSeverity,
    AlertThresholds,
    AlertType,
)


class TestRiskAlertDetector:
    """Test RiskAlertDetector class."""

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
            timestamp=datetime.now(timezone.utc),
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
        """Test detector initialization with defaults."""
        detector = RiskAlertDetector()

        assert detector.thresholds.exposure_threshold_pct == 80.0
        assert detector.thresholds.margin_utilization_threshold_pct == 80.0
        assert detector.thresholds.concentration_threshold_pct == 50.0

    def test_initialization_custom(self):
        """Test detector initialization with custom thresholds."""
        thresholds = AlertThresholds(
            exposure_threshold_pct=70.0,
            margin_utilization_threshold_pct=75.0,
            concentration_threshold_pct=40.0,
        )
        detector = RiskAlertDetector(thresholds)

        assert detector.thresholds.exposure_threshold_pct == 70.0
        assert detector.thresholds.margin_utilization_threshold_pct == 75.0
        assert detector.thresholds.concentration_threshold_pct == 40.0

    def test_no_alerts_when_within_thresholds(self):
        """Test no alerts when all metrics within thresholds."""
        detector = RiskAlertDetector()

        # 50% exposure, 50% margin, 30% concentration - all within limits
        metrics = self.create_test_metrics(
            net_exposure=5000.0,
            total_equity=10000.0,
            margin_used=5000.0,
            concentration_risk=30.0,
        )

        alerts = detector.detect_alerts(metrics)
        assert len(alerts) == 0

    def test_exposure_alert_triggered(self):
        """Test exposure alert when threshold exceeded."""
        detector = RiskAlertDetector()

        # 90% exposure exceeds 80% threshold
        metrics = self.create_test_metrics(
            net_exposure=9000.0,
            total_equity=10000.0,
            margin_used=5000.0,
            concentration_risk=30.0,
        )

        alerts = detector.detect_alerts(metrics)

        exposure_alerts = [a for a in alerts if a.alert_type == AlertType.EXPOSURE]
        assert len(exposure_alerts) == 1
        assert exposure_alerts[0].current_value == 90.0
        assert exposure_alerts[0].threshold == 80.0

    def test_margin_alert_triggered(self):
        """Test margin utilization alert when threshold exceeded."""
        detector = RiskAlertDetector()

        # 85% margin utilization exceeds 80% threshold
        metrics = self.create_test_metrics(
            net_exposure=5000.0,
            total_equity=10000.0,
            margin_used=8500.0,
            concentration_risk=30.0,
        )

        alerts = detector.detect_alerts(metrics)

        margin_alerts = [
            a for a in alerts if a.alert_type == AlertType.MARGIN_UTILIZATION
        ]
        assert len(margin_alerts) == 1
        assert margin_alerts[0].current_value == 85.0
        assert margin_alerts[0].threshold == 80.0

    def test_concentration_alert_triggered(self):
        """Test concentration alert when threshold exceeded."""
        detector = RiskAlertDetector()

        # 60% concentration exceeds 50% threshold
        metrics = self.create_test_metrics(
            net_exposure=5000.0,
            total_equity=10000.0,
            margin_used=5000.0,
            concentration_risk=60.0,
        )

        alerts = detector.detect_alerts(metrics)

        concentration_alerts = [
            a for a in alerts if a.alert_type == AlertType.CONCENTRATION
        ]
        assert len(concentration_alerts) == 1
        assert concentration_alerts[0].current_value == 60.0
        assert concentration_alerts[0].threshold == 50.0

    def test_multiple_alerts_triggered(self):
        """Test multiple alerts when multiple thresholds exceeded."""
        detector = RiskAlertDetector()

        # All thresholds exceeded
        metrics = self.create_test_metrics(
            net_exposure=9000.0,
            total_equity=10000.0,
            margin_used=8500.0,
            concentration_risk=60.0,
        )

        alerts = detector.detect_alerts(metrics)

        assert len(alerts) == 3
        alert_types = {a.alert_type for a in alerts}
        assert AlertType.EXPOSURE in alert_types
        assert AlertType.MARGIN_UTILIZATION in alert_types
        assert AlertType.CONCENTRATION in alert_types

    def test_exposure_severity_info(self):
        """Test exposure alert with info severity (slightly over)."""
        detector = RiskAlertDetector()

        # 85% exposure is 5% over threshold (info level)
        metrics = self.create_test_metrics(
            net_exposure=8500.0,
            total_equity=10000.0,
            margin_used=5000.0,
            concentration_risk=30.0,
        )

        alerts = detector.detect_alerts(metrics)
        exposure_alert = [a for a in alerts if a.alert_type == AlertType.EXPOSURE][0]

        assert exposure_alert.severity == AlertSeverity.INFO

    def test_exposure_severity_warning(self):
        """Test exposure alert with warning severity (moderately over)."""
        detector = RiskAlertDetector()

        # 95% exposure is 15% over threshold (warning level)
        metrics = self.create_test_metrics(
            net_exposure=9500.0,
            total_equity=10000.0,
            margin_used=5000.0,
            concentration_risk=30.0,
        )

        alerts = detector.detect_alerts(metrics)
        exposure_alert = [a for a in alerts if a.alert_type == AlertType.EXPOSURE][0]

        assert exposure_alert.severity == AlertSeverity.WARNING

    def test_exposure_severity_critical(self):
        """Test exposure alert with critical severity (significantly over)."""
        detector = RiskAlertDetector()

        # 105% exposure is 25% over threshold (critical level)
        metrics = self.create_test_metrics(
            net_exposure=10500.0,
            total_equity=10000.0,
            margin_used=5000.0,
            concentration_risk=30.0,
        )

        alerts = detector.detect_alerts(metrics)
        exposure_alert = [a for a in alerts if a.alert_type == AlertType.EXPOSURE][0]

        assert exposure_alert.severity == AlertSeverity.CRITICAL

    def test_margin_severity_info(self):
        """Test margin alert with info severity."""
        detector = RiskAlertDetector()

        # 82% margin (just over threshold)
        metrics = self.create_test_metrics(
            net_exposure=5000.0,
            total_equity=10000.0,
            margin_used=8200.0,
            concentration_risk=30.0,
        )

        alerts = detector.detect_alerts(metrics)
        margin_alert = [
            a for a in alerts if a.alert_type == AlertType.MARGIN_UTILIZATION
        ][0]

        assert margin_alert.severity == AlertSeverity.INFO

    def test_margin_severity_warning(self):
        """Test margin alert with warning severity."""
        detector = RiskAlertDetector()

        # 87% margin (warning level)
        metrics = self.create_test_metrics(
            net_exposure=5000.0,
            total_equity=10000.0,
            margin_used=8700.0,
            concentration_risk=30.0,
        )

        alerts = detector.detect_alerts(metrics)
        margin_alert = [
            a for a in alerts if a.alert_type == AlertType.MARGIN_UTILIZATION
        ][0]

        assert margin_alert.severity == AlertSeverity.WARNING

    def test_margin_severity_critical(self):
        """Test margin alert with critical severity."""
        detector = RiskAlertDetector()

        # 92% margin (critical level)
        metrics = self.create_test_metrics(
            net_exposure=5000.0,
            total_equity=10000.0,
            margin_used=9200.0,
            concentration_risk=30.0,
        )

        alerts = detector.detect_alerts(metrics)
        margin_alert = [
            a for a in alerts if a.alert_type == AlertType.MARGIN_UTILIZATION
        ][0]

        assert margin_alert.severity == AlertSeverity.CRITICAL

    def test_kill_switch_margin_critical(self):
        """Test kill-switch detection for critical margin."""
        detector = RiskAlertDetector()

        # 97% margin utilization triggers kill-switch
        metrics = self.create_test_metrics(
            net_exposure=5000.0,
            total_equity=10000.0,
            margin_used=9700.0,
            concentration_risk=30.0,
        )

        kill_switch = detector.detect_kill_switch(metrics)

        assert kill_switch is not None
        assert kill_switch.alert_type == AlertType.KILL_SWITCH
        assert kill_switch.severity == AlertSeverity.EMERGENCY
        assert "critical margin" in kill_switch.message.lower()

    def test_kill_switch_extreme_concentration(self):
        """Test kill-switch detection for extreme concentration."""
        detector = RiskAlertDetector()

        # 85% concentration triggers kill-switch
        metrics = self.create_test_metrics(
            net_exposure=5000.0,
            total_equity=10000.0,
            margin_used=5000.0,
            concentration_risk=85.0,
        )

        kill_switch = detector.detect_kill_switch(metrics)

        assert kill_switch is not None
        assert kill_switch.alert_type == AlertType.KILL_SWITCH
        assert kill_switch.severity == AlertSeverity.EMERGENCY
        assert "extreme concentration" in kill_switch.message.lower()

    def test_kill_switch_no_trigger(self):
        """Test kill-switch doesn't trigger when conditions not met."""
        detector = RiskAlertDetector()

        # Normal conditions
        metrics = self.create_test_metrics(
            net_exposure=5000.0,
            total_equity=10000.0,
            margin_used=5000.0,
            concentration_risk=30.0,
        )

        kill_switch = detector.detect_kill_switch(metrics)

        assert kill_switch is None

    def test_update_thresholds(self):
        """Test updating thresholds."""
        detector = RiskAlertDetector()

        new_thresholds = AlertThresholds(
            exposure_threshold_pct=60.0,
            margin_utilization_threshold_pct=70.0,
            concentration_threshold_pct=40.0,
        )

        detector.update_thresholds(new_thresholds)

        assert detector.thresholds.exposure_threshold_pct == 60.0
        assert detector.thresholds.margin_utilization_threshold_pct == 70.0
        assert detector.thresholds.concentration_threshold_pct == 40.0

    def test_zero_equity_handling(self):
        """Test handling of zero equity."""
        detector = RiskAlertDetector()

        metrics = self.create_test_metrics(
            net_exposure=0.0,
            total_equity=0.0,
            margin_used=0.0,
            concentration_risk=0.0,
        )

        alerts = detector.detect_alerts(metrics)

        # Should not crash, should return no alerts
        assert len(alerts) == 0
