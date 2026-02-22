"""Bitget live trading gating module.

Provides human approval workflow, risk controls, and kill-switch integration
for live trading activation.

For ST-EX-002: Bitget Live Trading Gating Implementation
"""

from __future__ import annotations

from execution.live_gating.audit_logger import LiveTradeAuditLogger
from execution.live_gating.gate_manager import (
    ApprovalPacket,
    ApprovalRequest,
    LiveGateConfig,
    LiveGateManager,
    LiveTradingState,
    PaperTradingEvidence,
)
from execution.live_gating.grafana_exporter import LiveGatingGrafanaExporter
from execution.live_gating.risk_enforcer import RiskEnforcer, ValidationResult

__all__ = [
    # Gate Manager
    "LiveTradingState",
    "LiveGateConfig",
    "ApprovalPacket",
    "ApprovalRequest",
    "PaperTradingEvidence",
    "LiveGateManager",
    # Risk Enforcer
    "RiskEnforcer",
    "ValidationResult",
    # Audit Logger
    "LiveTradeAuditLogger",
    # Grafana Exporter
    "LiveGatingGrafanaExporter",
]
