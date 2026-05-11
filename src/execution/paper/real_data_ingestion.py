"""Real Market Data Ingestion Pipeline for BOS/CHoCH validation.

This module provides real-time market data ingestion from Bybit demo API
for ICT (Internal Conservation of Trade) feature validation.

Key Features:
- Live market data ingestion from Bybit demo
- Real trade and order book data capture
- Data quality validation with freshness checks
- Fallback to historical data if live unavailable
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum

from execution.connectors.bybit_demo_connector import BybitDemoConnector

logger = logging.getLogger(__name__)


class DataSource(str, Enum):
    """Data source type for market data."""

    LIVE_BYBIT = "live_bybit"
    HISTORICAL = "historical"
    FALLBACK = "fallback"


class DataFreshness(str, Enum):
    """Data freshness status."""

    FRESH = "fresh"
    STALE = "stale"
    UNKNOWN = "unknown"


@dataclass
class OrderBookEntry:
    """Single order book entry."""

    price: float
    quantity: float
    side: str  # "bid" or "ask"


@dataclass
class OrderBookSnapshot:
    """Order book snapshot with bids and asks."""

    symbol: str
    timestamp: datetime
    bids: list[OrderBookEntry] = field(default_factory=list)
    asks: list[OrderBookEntry] = field(default_factory=list)
    source: DataSource = DataSource.LIVE_BYBIT

    def is_valid(self) -> bool:
        """Check if order book has valid entries."""
        return len(self.bids) > 0 and len(self.asks) > 0

    def get_mid_price(self) -> float | None:
        """Get mid price from best bid/ask."""
        if not self.bids or not self.asks:
            return None
        best_bid = max(self.bids, key=lambda x: x.price).price
        best_ask = min(self.asks, key=lambda x: x.price).price
        return (best_bid + best_ask) / 2


@dataclass
class TradeEntry:
    """Single trade entry."""

    trade_id: str
    symbol: str
    side: str  # "buy" or "sell"
    price: float
    quantity: float
    timestamp: datetime
    source: DataSource = DataSource.LIVE_BYBIT


@dataclass
class MarketDataSnapshot:
    """Combined market data snapshot."""

    symbol: str
    timestamp: datetime
    order_book: OrderBookSnapshot | None = None
    recent_trades: list[TradeEntry] = field(default_factory=list)
    source: DataSource = DataSource.LIVE_BYBIT
    freshness: DataFreshness = DataFreshness.UNKNOWN

    def is_complete(self) -> bool:
        """Check if snapshot has both order book and trades."""
        return self.order_book is not None and len(self.recent_trades) > 0


class RealDataIngestion:
    """Real market data ingestion pipeline for ICT validation.

    This class provides live market data ingestion from Bybit demo API
    with data quality validation and fallback to historical data.

    Attributes:
        connector: Bybit demo connector instance
        _order_book_cache: Cache of recent order book snapshots
        _trades_cache: Cache of recent trades
        _max_age_seconds: Maximum age for data freshness
        _fallback_handler: Optional fallback data provider
    """

    def __init__(
        self,
        connector: BybitDemoConnector | None = None,
        max_age_seconds: int = 30,
        fallback_handler: Callable[[str], list[TradeEntry] | None] | None = None,
    ) -> None:
        """Initialize real data ingestion.

        Args:
            connector: Bybit demo connector (creates one if None)
            max_age_seconds: Maximum age in seconds for data freshness
            fallback_handler: Optional callback for historical data fallback
        """
        self._connector = connector
        self._max_age_seconds = max_age_seconds
        self._fallback_handler = fallback_handler
        self._order_book_cache: dict[str, OrderBookSnapshot] = {}
        self._trades_cache: dict[str, list[TradeEntry]] = {}
        self._last_update: dict[str, datetime] = {}
        self._connected = False
        self._subscription_tasks: dict[str, asyncio.Task] = {}

    async def connect_to_bybit_demo(self) -> bool:
        """Connect to Bybit demo API.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            if self._connector is None:
                # Create new connector from env
                self._connector = BybitDemoConnector.from_env()

            # Perform health check
            health = await self._connector.health_check()
            self._connected = health.get("healthy", False)

            if self._connected:
                logger.info(
                    "Connected to Bybit demo - endpoint=%s, demo_mode=%s",
                    health.get("endpoint"),
                    health.get("demo_mode"),
                )
            else:
                logger.warning(
                    "Bybit demo connection unhealthy - error=%s",
                    health.get("error", "unknown"),
                )

            return self._connected

        except Exception as exc:
            logger.error("Failed to connect to Bybit demo: %s", exc)
            self._connected = False
            return False

    async def subscribe_to_orderbook(self, symbol: str) -> bool:
        """Subscribe to real-time order book data for a symbol.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")

        Returns:
            True if subscription successful
        """
        if self._connector is None:
            logger.error("Cannot subscribe: No connector available")
            return False

        try:
            # Get initial order book via REST API
            bybit_symbol = self._normalize_symbol(symbol)
            ticker = await self._connector.connector.get_ticker(bybit_symbol)

            # Parse order book data from ticker
            result = ticker.get("result", {})
            order_book_data = result.get("orderbook", [])

            if order_book_data:
                # Parse order book entries
                bids = []
                asks = []
                for entry in order_book_data:
                    side = entry.get("side", "")
                    price = float(entry.get("price", 0))
                    quantity = float(entry.get("size", 0))
                    if price > 0 and quantity > 0:
                        order_entry = OrderBookEntry(
                            price=price,
                            quantity=quantity,
                            side=side,
                        )
                        if side.lower() == "buy" or side == "0":
                            bids.append(order_entry)
                        else:
                            asks.append(order_entry)

                snapshot = OrderBookSnapshot(
                    symbol=symbol,
                    timestamp=datetime.now(UTC),
                    bids=bids,
                    asks=asks,
                    source=DataSource.LIVE_BYBIT,
                )
                self._order_book_cache[symbol.upper()] = snapshot
                self._last_update[symbol.upper()] = datetime.now(UTC)

                logger.info(
                    "Order book subscribed for %s - bids=%d, asks=%d",
                    symbol,
                    len(bids),
                    len(asks),
                )
                return True

            # Fallback: create empty snapshot and try to get price data
            snapshot = OrderBookSnapshot(
                symbol=symbol,
                timestamp=datetime.now(UTC),
                bids=[],
                asks=[],
                source=DataSource.HISTORICAL,
            )
            self._order_book_cache[symbol.upper()] = snapshot
            logger.warning(
                "No order book data for %s - using fallback",
                symbol,
            )
            return True

        except Exception as exc:
            logger.error("Failed to subscribe to orderbook for %s: %s", symbol, exc)
            return False

    async def subscribe_to_trades(self, symbol: str) -> bool:
        """Subscribe to real-time trade data for a symbol.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")

        Returns:
            True if subscription successful
        """
        if self._connector is None:
            logger.error("Cannot subscribe: No connector available")
            return False

        try:
            # Get recent trades via REST API
            bybit_symbol = self._normalize_symbol(symbol)
            trades_data = await self._connector.connector.get_public_trade(bybit_symbol)

            trades = []
            if trades_data:
                result = trades_data.get("result", [])
                for trade in result:
                    trade_entry = TradeEntry(
                        trade_id=str(trade.get("tradeId", "")),
                        symbol=symbol.upper(),
                        side=trade.get("side", "").lower(),
                        price=float(trade.get("price", 0)),
                        quantity=float(trade.get("size", 0)),
                        timestamp=datetime.fromtimestamp(
                            int(trade.get("tradeTime", 0)) / 1000,
                            tz=UTC,
                        ),
                        source=DataSource.LIVE_BYBIT,
                    )
                    trades.append(trade_entry)

            self._trades_cache[symbol.upper()] = trades
            self._last_update[symbol.upper()] = datetime.now(UTC)

            logger.info(
                "Trades subscribed for %s - count=%d",
                symbol,
                len(trades),
            )
            return True

        except Exception as exc:
            logger.error("Failed to subscribe to trades for %s: %s", symbol, exc)
            # Try fallback
            return await self.fallback_to_historical(symbol)

    def validate_data_freshness(
        self,
        symbol: str,
        max_age_seconds: int | None = None,
    ) -> DataFreshness:
        """Validate freshness of cached market data.

        Args:
            symbol: Trading pair symbol
            max_age_seconds: Override max age (uses default if None)

        Returns:
            DataFreshness status: FRESH, STALE, or UNKNOWN
        """
        max_age = max_age_seconds or self._max_age_seconds
        symbol_upper = symbol.upper()

        if symbol_upper not in self._last_update:
            return DataFreshness.UNKNOWN

        last_update = self._last_update[symbol_upper]
        age = datetime.now(UTC) - last_update

        if age.total_seconds() <= max_age:
            return DataFreshness.FRESH
        else:
            logger.warning(
                "Data stale for %s - age=%.1fs, max_age=%ds",
                symbol,
                age.total_seconds(),
                max_age,
            )
            return DataFreshness.STALE

    async def fallback_to_historical(self, symbol: str) -> bool:
        """Fallback to historical data when live data unavailable.

        Args:
            symbol: Trading pair symbol

        Returns:
            True if fallback data available
        """
        logger.info("Attempting historical fallback for %s", symbol)

        # Try fallback handler if available
        if self._fallback_handler is not None:
            try:
                historical_trades = self._fallback_handler(symbol)
                if historical_trades:
                    self._trades_cache[symbol.upper()] = historical_trades
                    self._last_update[symbol.upper()] = datetime.now(UTC)
                    logger.info(
                        "Historical fallback successful for %s - trades=%d",
                        symbol,
                        len(historical_trades),
                    )
                    return True
            except Exception as exc:
                logger.error(
                    "Fallback handler failed for %s: %s",
                    symbol,
                    exc,
                )

        # Generate synthetic data for demo purposes
        synthetic_trades = self._generate_synthetic_trades(symbol)
        self._trades_cache[symbol.upper()] = synthetic_trades
        self._last_update[symbol.upper()] = datetime.now(UTC)

        logger.info(
            "Synthetic fallback generated for %s - trades=%d",
            symbol,
            len(synthetic_trades),
        )
        return True

    def _generate_synthetic_trades(self, symbol: str) -> list[TradeEntry]:
        """Generate synthetic trade data for fallback.

        This creates realistic-looking trade data for testing
        when neither live nor historical data is available.

        Args:
            symbol: Trading pair symbol

        Returns:
            List of synthetic trade entries

        Note:
            This method generates synthetic FALLBACK data for testing purposes ONLY.
            These prices (50000.0 for BTC, 1000.0 for others) are MOCK/test values and
            should NEVER be used for live trading price resolution. The trades are
            explicitly marked with DataSource.FALLBACK.
        """
        import random

        trades = []
        base_time = datetime.now(UTC)
        # WARNING: These are synthetic test prices, NOT live market prices
        _SYNTHETIC_BASE_PRICE_BTC = 50000.0
        _SYNTHETIC_BASE_PRICE_OTHER = 1000.0
        base_price = (
            _SYNTHETIC_BASE_PRICE_BTC
            if "BTC" in symbol.upper()
            else _SYNTHETIC_BASE_PRICE_OTHER
        )

        for i in range(10):
            trade = TradeEntry(
                trade_id=f"synthetic_{base_time.timestamp()}_{i}",
                symbol=symbol.upper(),
                side=random.choice(["buy", "sell"]),
                price=base_price + random.uniform(-100, 100),
                quantity=random.uniform(0.001, 1.0),
                timestamp=base_time - timedelta(seconds=i * 5),
                source=DataSource.FALLBACK,
            )
            trades.append(trade)

        return trades

    async def get_market_snapshot(self, symbol: str) -> MarketDataSnapshot | None:
        """Get combined market data snapshot for a symbol.

        Args:
            symbol: Trading pair symbol

        Returns:
            MarketDataSnapshot with order book and trades, or None if unavailable
        """
        symbol_upper = symbol.upper()

        # Ensure we have data
        if symbol_upper not in self._order_book_cache:
            await self.subscribe_to_orderbook(symbol)

        if symbol_upper not in self._trades_cache:
            await self.subscribe_to_trades(symbol)

        # Build snapshot
        order_book = self._order_book_cache.get(symbol_upper)
        trades = self._trades_cache.get(symbol_upper, [])
        freshness = self.validate_data_freshness(symbol)

        # Determine source
        source = DataSource.LIVE_BYBIT
        if freshness == DataFreshness.UNKNOWN:
            source = DataSource.HISTORICAL
        elif freshness == DataFreshness.STALE:
            source = DataSource.FALLBACK

        return MarketDataSnapshot(
            symbol=symbol_upper,
            timestamp=datetime.now(UTC),
            order_book=order_book,
            recent_trades=trades,
            source=source,
            freshness=freshness,
        )

    def get_cached_order_book(self, symbol: str) -> OrderBookSnapshot | None:
        """Get cached order book for a symbol.

        Args:
            symbol: Trading pair symbol

        Returns:
            OrderBookSnapshot or None
        """
        return self._order_book_cache.get(symbol.upper())

    def get_cached_trades(self, symbol: str) -> list[TradeEntry]:
        """Get cached trades for a symbol.

        Args:
            symbol: Trading pair symbol

        Returns:
            List of TradeEntry
        """
        return self._trades_cache.get(symbol.upper(), [])

    def clear_cache(self, symbol: str | None = None) -> None:
        """Clear cached market data.

        Args:
            symbol: Symbol to clear (all if None)
        """
        if symbol is None:
            self._order_book_cache.clear()
            self._trades_cache.clear()
            self._last_update.clear()
        else:
            symbol_upper = symbol.upper()
            self._order_book_cache.pop(symbol_upper, None)
            self._trades_cache.pop(symbol_upper, None)
            self._last_update.pop(symbol_upper, None)

    async def close(self) -> None:
        """Close connections and cleanup resources."""
        # Cancel all subscription tasks
        for task in self._subscription_tasks.values():
            task.cancel()

        self._subscription_tasks.clear()

        # Close connector
        if self._connector is not None:
            await self._connector.close()
            self._connected = False

        logger.info("RealDataIngestion closed")

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        """Normalize symbol into Bybit format."""
        normalized = symbol.upper().strip()
        normalized = normalized.replace("/", "").replace("-", "")
        normalized = normalized.replace(":USDT", "USDT")
        return normalized

    @property
    def is_connected(self) -> bool:
        """Check if connected to Bybit demo."""
        return self._connected
