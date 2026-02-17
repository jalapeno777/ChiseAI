"""Tests for alert detector."""

from datetime import UTC, datetime

from portfolio.state_management.risk_calculator import (
    MarginUtilization,
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


class TestPaperTradingAlerts:
    """Test paper trading specific alert methods (ST-PAPER-008)."""

    def test_redis_failure_alert_triggered(self):
        """Test Redis failure alert when circuit breaker opens."""
        from portfolio_risk.alerts.detector import RiskAlertDetector
        from portfolio_risk.alerts.types import AlertSeverity, AlertType

        detector = RiskAlertDetector()

        # Circuit breaker open should trigger alert
        alert = detector.detect_redis_failure(
            error_rate=75.0,
            affected_operations=["state_sync", "position_update"],
            circuit_breaker_open=True,
        )

        assert alert is not None
        assert alert.alert_type == AlertType.REDIS_FAILURE
        assert alert.severity == AlertSeverity.CRITICAL
        assert "circuit breaker" in alert.message.lower()
        assert "75.0%" in alert.message
        assert "state_sync" in alert.metadata["affected_operations"]
        assert "recovery_steps_link" in alert.metadata

    def test_redis_failure_alert_high_error_rate(self):
        """Test Redis failure alert with high error rate."""
        from portfolio_risk.alerts.detector import RiskAlertDetector
        from portfolio_risk.alerts.types import AlertSeverity, AlertType

        detector = RiskAlertDetector()

        # High error rate should trigger alert even if circuit breaker closed
        alert = detector.detect_redis_failure(
            error_rate=60.0,
            affected_operations=["order_sync"],
            circuit_breaker_open=False,
        )

        assert alert is not None
        assert alert.alert_type == AlertType.REDIS_FAILURE
        assert alert.severity == AlertSeverity.CRITICAL

    def test_redis_failure_alert_no_trigger(self):
        """Test Redis failure alert doesn't trigger when healthy."""
        from portfolio_risk.alerts.detector import RiskAlertDetector

        detector = RiskAlertDetector()

        # Low error rate and closed circuit breaker should not trigger
        alert = detector.detect_redis_failure(
            error_rate=10.0,
            affected_operations=["state_sync"],
            circuit_breaker_open=False,
        )

        assert alert is None

    def test_paper_sync_divergence_alert_triggered(self):
        """Test paper sync divergence alert when states differ."""
        from portfolio_risk.alerts.detector import RiskAlertDetector
        from portfolio_risk.alerts.types import AlertSeverity, AlertType

        detector = RiskAlertDetector()

        redis_state = {
            "BTC": {"notional_value": 10000.0},
            "ETH": {"notional_value": 5000.0},
        }
        memory_state = {
            "BTC": {"notional_value": 10600.0},  # 6% divergence
            "ETH": {"notional_value": 5000.0},  # No divergence
        }

        alert = detector.detect_paper_sync_divergence(
            redis_state=redis_state,
            memory_state=memory_state,
            divergence_threshold_pct=5.0,
        )

        assert alert is not None
        assert alert.alert_type == AlertType.PAPER_SYNC_DIVERGENCE
        assert alert.severity == AlertSeverity.CRITICAL
        assert "divergence" in alert.message.lower()
        assert "BTC" in alert.metadata["affected_positions"]
        assert alert.metadata["divergence_count"] == 1

    def test_paper_sync_divergence_alert_no_trigger(self):
        """Test divergence alert doesn't trigger when within threshold."""
        from portfolio_risk.alerts.detector import RiskAlertDetector

        detector = RiskAlertDetector()

        redis_state = {
            "BTC": {"notional_value": 10000.0},
        }
        memory_state = {
            "BTC": {"notional_value": 10200.0},  # 2% divergence, under 5% threshold
        }

        alert = detector.detect_paper_sync_divergence(
            redis_state=redis_state,
            memory_state=memory_state,
            divergence_threshold_pct=5.0,
        )

        assert alert is None

    def test_paper_sync_divergence_multiple_positions(self):
        """Test divergence alert with multiple diverged positions."""
        from portfolio_risk.alerts.detector import RiskAlertDetector
        from portfolio_risk.alerts.types import AlertType

        detector = RiskAlertDetector()

        redis_state = {
            "BTC": {"notional_value": 10000.0},
            "ETH": {"notional_value": 5000.0},
            "SOL": {"notional_value": 2000.0},
        }
        memory_state = {
            "BTC": {"notional_value": 11000.0},  # 10% divergence
            "ETH": {"notional_value": 5500.0},  # 10% divergence
            "SOL": {"notional_value": 2000.0},  # No divergence
        }

        alert = detector.detect_paper_sync_divergence(
            redis_state=redis_state,
            memory_state=memory_state,
            divergence_threshold_pct=5.0,
        )

        assert alert is not None
        assert alert.alert_type == AlertType.PAPER_SYNC_DIVERGENCE
        assert alert.metadata["divergence_count"] == 2
        assert "BTC" in alert.metadata["affected_positions"]
        assert "ETH" in alert.metadata["affected_positions"]

    def test_validation_failure_rate_alert_triggered(self):
        """Test validation failure rate alert when threshold exceeded."""
        from portfolio_risk.alerts.detector import RiskAlertDetector
        from portfolio_risk.alerts.types import AlertSeverity, AlertType

        detector = RiskAlertDetector()

        failure_reasons = {
            "insufficient_funds": 8,
            "price_stale": 2,
            "size_too_small": 5,
        }

        alert = detector.detect_validation_failure_rate(
            total_orders=100,
            failed_orders=15,
            failure_reasons=failure_reasons,
            window_minutes=5,
            threshold_pct=10.0,
        )

        assert alert is not None
        assert alert.alert_type == AlertType.VALIDATION_FAILURE_RATE
        assert alert.severity == AlertSeverity.WARNING
        assert "15.0%" in alert.message
        assert "validation" in alert.message.lower()
        assert alert.metadata["failure_breakdown"] == failure_reasons
        assert alert.metadata["most_common_reason"] == "insufficient_funds"

    def test_validation_failure_rate_alert_no_trigger(self):
        """Test validation failure alert doesn't trigger when under threshold."""
        from portfolio_risk.alerts.detector import RiskAlertDetector

        detector = RiskAlertDetector()

        alert = detector.detect_validation_failure_rate(
            total_orders=100,
            failed_orders=5,
            failure_reasons={"insufficient_funds": 5},
            window_minutes=5,
            threshold_pct=10.0,
        )

        assert alert is None

    def test_validation_failure_rate_zero_orders(self):
        """Test validation failure alert with zero orders."""
        from portfolio_risk.alerts.detector import RiskAlertDetector

        detector = RiskAlertDetector()

        alert = detector.detect_validation_failure_rate(
            total_orders=0,
            failed_orders=0,
            failure_reasons={},
            window_minutes=5,
            threshold_pct=10.0,
        )

        assert alert is None

    def test_validation_failure_rate_breakdown(self):
        """Test validation failure alert includes correct breakdown."""
        from portfolio_risk.alerts.detector import RiskAlertDetector

        detector = RiskAlertDetector()

        failure_reasons = {
            "insufficient_funds": 10,
            "market_closed": 3,
            "price_stale": 2,
        }

        alert = detector.detect_validation_failure_rate(
            total_orders=50,
            failed_orders=15,
            failure_reasons=failure_reasons,
            window_minutes=5,
            threshold_pct=10.0,
        )

        assert alert is not None
        assert alert.metadata["total_orders"] == 50
        assert alert.metadata["failed_orders"] == 15
        assert alert.metadata["failure_rate_pct"] == 30.0
        assert alert.metadata["window_minutes"] == 5
