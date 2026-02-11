"""Binance exchange configuration."""

from dataclasses import dataclass
from typing import List


@dataclass
class BinanceConfig:
    """Configuration for Binance data ingestion.

    Attributes:
        api_key: Binance API key (optional for public endpoints)
        api_secret: Binance API secret (optional for public endpoints)
        base_url: Base URL for Binance API
        ws_url: WebSocket URL for real-time data
        tokens: List of token symbols to track (e.g., ["BTCUSDT", "ETHUSDT"])
        orderbook_depth: Depth of order book to fetch (default 100)
        snapshot_interval_ms: Interval between order book snapshots in ms (default 100)
        max_latency_ms: Maximum acceptable latency in ms (default 2000)
        freshness_threshold_sec: Data freshness threshold in seconds (default 5)
        price_accuracy_pct: Price accuracy tolerance in percent (default 0.01)
    """

    api_key: str = ""
    api_secret: str = ""
    base_url: str = "https://fapi.binance.com"
    ws_url: str = "wss://fstream.binance.com/ws"
    tokens: List[str] = None  # type: ignore
    orderbook_depth: int = 100
    snapshot_interval_ms: int = 100
    max_latency_ms: int = 2000
    freshness_threshold_sec: int = 5
    price_accuracy_pct: float = 0.01

    def __post_init__(self) -> None:
        """Set default tokens if not provided."""
        if self.tokens is None:
            self.tokens = [
                "BTCUSDT",
                "ETHUSDT",
                "SOLUSDT",
                "XRPUSDT",
                "DOGEUSDT",
                "ADAUSDT",
                "AVAXUSDT",
                "LINKUSDT",
                "DOTUSDT",
                "MATICUSDT",
            ]

    @property
    def orderbook_url(self) -> str:
        """Get order book endpoint URL."""
        return f"{self.base_url}/fapi/v1/depth"

    @property
    def open_interest_url(self) -> str:
        """Get open interest endpoint URL."""
        return f"{self.base_url}/fapi/v1/openInterest"

    @property
    def ticker_url(self) -> str:
        """Get ticker/price endpoint URL."""
        return f"{self.base_url}/fapi/v1/ticker/bookTicker"
