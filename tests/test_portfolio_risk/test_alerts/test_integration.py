"""Tests for alerts module integration."""

import pytest

from portfolio_risk.alerts import (
    AlertSeverity,
    AlertState,
    AlertSuppressor,
    AlertThresholds,
    AlertType,
    RiskAlert,
    RiskAlertDetector,
    RiskAlertFormatter,
    RiskAlertManager,
    RiskAlertSendResult,
    RiskAlertSender,
)


class TestModuleExports:
    """Test that all expected classes are exported."""

    def test_types_exported(self):
        """Test types are exported."""
        assert AlertSeverity is not None
        assert AlertState is not None
        assert AlertThresholds is not None
        assert AlertType is not None
        assert RiskAlert is not None

    def test_classes_exported(self):
        """Test main classes are exported."""
        assert AlertSuppressor is not None
        assert RiskAlertDetector is not None
        assert RiskAlertFormatter is not None
        assert RiskAlertManager is not None
        assert RiskAlertSendResult is not None
        assert RiskAlertSender is not None

    def test_alert_creation_via_module(self):
        """Test creating alert via module import."""
        alert = RiskAlert(
            alert_type=AlertType.EXPOSURE,
            severity=AlertSeverity.WARNING,
            message="Test",
            threshold=80.0,
            current_value=85.0,
        )

        assert alert.alert_type == AlertType.EXPOSURE
        assert alert.severity == AlertSeverity.WARNING
