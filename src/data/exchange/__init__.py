"""Data exchange module for Bybit and Bitget connectors.

For ST-DATA-002: Execution Market Data Ingestion - Bybit/Bitget
For ST-NS-026: Connection Pooling for Exchange APIs
"""

from data.exchange.bitget_connector import BitgetConfig, BitgetConnector
from data.exchange.bybit_connector import BybitConfig, BybitConnector
from data.exchange.pooling import (
    ExchangeConnectionPool,
    PooledBitgetClient,
    PooledBybitClient,
    PoolHealthMonitor,
    PoolMetrics,
)

__all__ = [
    # Original connectors
    "BybitConfig",
    "BybitConnector",
    "BitgetConfig",
    "BitgetConnector",
    # Pooled clients (ST-NS-026)
    "PooledBybitClient",
    "PooledBitgetClient",
    "ExchangeConnectionPool",
    "PoolMetrics",
    "PoolHealthMonitor",
]
