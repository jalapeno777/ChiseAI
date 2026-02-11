"""Exchange data ingestion package for market-structure reference data.

This package provides tools for ingesting order book, liquidity, and open interest
data from cryptocurrency exchanges (Binance as reference venue).
"""

from exchange_data.binance.client import BinanceClient
from exchange_data.binance.config import BinanceConfig
from exchange_data.binance.ingestion import BinanceIngestionService
from exchange_data.binance.liquidity import LiquidityCalculator, LiquidityMetrics
from exchange_data.binance.open_interest import OpenInterestAggregator
from exchange_data.binance.orderbook import OrderBookSnapshot, OrderBookTracker
from exchange_data.binance.validator import DataQualityValidator

__all__ = [
    # Config
    "BinanceConfig",
    # Client
    "BinanceClient",
    # Order Book
    "OrderBookSnapshot",
    "OrderBookTracker",
    # Liquidity
    "LiquidityMetrics",
    "LiquidityCalculator",
    # Open Interest
    "OpenInterestAggregator",
    # Ingestion Service
    "BinanceIngestionService",
    # Validator
    "DataQualityValidator",
]
