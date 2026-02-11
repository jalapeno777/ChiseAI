"""Risk alert integration module.

Provides risk threshold alert detection, suppression, formatting,
and Discord sending for portfolio risk management.

For ST-NS-016: Risk Threshold Alert System
"""

from __future__ import annotations

__all__ = [
    "AlertSeverity",
    "AlertState",
    "AlertSuppressor",
    "AlertThresholds",
    "AlertType",
    "RiskAlert",
    "RiskAlertDetector",
    "RiskAlertFormatter",
    "RiskAlertManager",
    "RiskAlertSendResult",
    "RiskAlertSender",
]

from .detector import RiskAlertDetector
from .formatter import RiskAlertFormatter
from .manager import RiskAlertManager
from .sender import RiskAlertSender, RiskAlertSendResult
from .suppressor import AlertSuppressor
from .types import (
    AlertSeverity,
    AlertState,
    AlertThresholds,
    AlertType,
    RiskAlert,
)
