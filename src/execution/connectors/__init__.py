"""Execution connectors for live trading.

This module provides connectors for executing trades against
actual exchange APIs. All connectors enforce demo/testnet-only
operation to prevent accidental production trading.

Available connectors:
- BybitDemoConnector: Authenticated demo trading via Bybit API

Safety:
All connectors validate endpoints against allowed demo patterns
and raise SecurityException if production endpoints are detected.
"""

from __future__ import annotations

from execution.connectors.bybit_demo_connector import (
    BybitAPIError,
    BybitAuthenticationError,
    BybitConnectorError,
    BybitDemoConnector,
    BybitDemoConnectorFactory,
    BybitNetworkError,
    BybitOrderError,
    BybitRateLimitError,
    DemoProvenance,
    ExponentialBackoffRetry,
    ProvenanceEvent,
    ProvenanceEventType,
    ProvenanceTracker,
    RetryConfig,
    classify_bybit_error,
    create_bybit_demo_connector,
)

__all__ = [
    "BybitAPIError",
    "BybitAuthenticationError",
    "BybitConnectorError",
    "BybitDemoConnector",
    "BybitDemoConnectorFactory",
    "BybitNetworkError",
    "BybitOrderError",
    "BybitRateLimitError",
    "DemoProvenance",
    "ExponentialBackoffRetry",
    "ProvenanceEvent",
    "ProvenanceEventType",
    "ProvenanceTracker",
    "RetryConfig",
    "classify_bybit_error",
    "create_bybit_demo_connector",
]
