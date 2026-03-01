"""Fill data model for execution tracking.

Defines the Fill dataclass for capturing and persisting trade fill data
from exchanges.

For ST-DATA-002: Execution Market Data Ingestion - Bybit/Bitget
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any


@dataclass
class Fill:
    """A trade fill from an exchange.

    Captures all relevant data for a single fill event including
    order linkage, pricing, quantity, fees, and timing.

    Attributes:
        order_id: Exchange order ID that generated this fill
        fill_id: Unique fill identifier from exchange
        symbol: Trading pair symbol (e.g., "BTCUSDT")
        side: Trade side - "buy" or "sell"
        price: Fill price in quote currency
        quantity: Fill quantity in base currency
        timestamp: Fill timestamp (UTC datetime)
        fee: Trading fee amount
        fee_currency: Currency in which fee is denominated
        exchange: Exchange name - "bybit" or "bitget"
        metadata: Additional exchange-specific data

        # ST-VENUE-001: Venue provenance fields
        execution_venue: Where the trade was executed (e.g., "bybit_demo", "local_sim")
        execution_mode: Mode of execution (e.g., "demo", "testnet", "production")
    """

    order_id: str
    fill_id: str
    symbol: str
    side: str  # buy/sell
    price: Decimal
    quantity: Decimal
    timestamp: datetime
    fee: Decimal
    fee_currency: str
    exchange: str  # bybit/bitget
    metadata: dict[str, Any] = field(default_factory=dict)

    # ST-VENUE-001: Venue provenance fields
    execution_venue: str = ""  # e.g., "bybit_demo", "local_sim"
    execution_mode: str = ""  # e.g., "demo", "testnet", "production"

    def __post_init__(self) -> None:
        """Validate and normalize fill data."""
        # Normalize side to lowercase
        self.side = self.side.lower()
        if self.side not in ("buy", "sell"):
            raise ValueError(f"Invalid side: {self.side}. Must be 'buy' or 'sell'")

        # Normalize exchange to lowercase
        self.exchange = self.exchange.lower()
        if self.exchange not in ("bybit", "bitget"):
            raise ValueError(
                f"Invalid exchange: {self.exchange}. Must be 'bybit' or 'bitget'"
            )

        # Ensure timestamp is timezone-aware
        if self.timestamp.tzinfo is None:
            self.timestamp = self.timestamp.replace(tzinfo=UTC)

    @property
    def notional_value(self) -> Decimal:
        """Calculate notional value of the fill (price * quantity)."""
        return self.price * self.quantity

    @property
    def net_quantity(self) -> Decimal:
        """Calculate net quantity after fees (for buy orders)."""
        if self.side == "buy":
            # For buys, fee is deducted from received quantity
            if self.fee_currency == self.symbol.replace("USDT", "").replace("USD", ""):
                return self.quantity - self.fee
        return self.quantity

    @property
    def net_value(self) -> Decimal:
        """Calculate net value after fees (for sell orders)."""
        if self.side == "sell":
            # For sells, fee is deducted from proceeds
            return self.notional_value - self.fee
        return self.notional_value

    def to_dict(self) -> dict[str, Any]:
        """Convert fill to dictionary for serialization.

        Returns:
            Dictionary representation of the fill
        """
        return {
            "order_id": self.order_id,
            "fill_id": self.fill_id,
            "symbol": self.symbol,
            "side": self.side,
            "price": str(self.price),
            "quantity": str(self.quantity),
            "timestamp": self.timestamp.isoformat(),
            "fee": str(self.fee),
            "fee_currency": self.fee_currency,
            "exchange": self.exchange,
            "notional_value": str(self.notional_value),
            "net_quantity": str(self.net_quantity),
            "net_value": str(self.net_value),
            "metadata": self.metadata,
            # ST-VENUE-001: Venue provenance fields
            "execution_venue": self.execution_venue,
            "execution_mode": self.execution_mode,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Fill:
        """Create Fill from dictionary.

        Args:
            data: Dictionary with fill data

        Returns:
            Fill instance
        """
        return cls(
            order_id=data["order_id"],
            fill_id=data["fill_id"],
            symbol=data["symbol"],
            side=data["side"],
            price=Decimal(data["price"]),
            quantity=Decimal(data["quantity"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            fee=Decimal(data["fee"]),
            fee_currency=data["fee_currency"],
            exchange=data["exchange"],
            metadata=data.get("metadata", {}),
            # ST-VENUE-001: Venue provenance fields
            execution_venue=data.get("execution_venue", ""),
            execution_mode=data.get("execution_mode", ""),
        )

    @classmethod
    def from_bybit_response(cls, response: dict[str, Any]) -> Fill:
        """Create Fill from Bybit V5 API response.

        Args:
            response: Bybit API execution/fill response

        Returns:
            Fill instance
        """
        # Bybit V5 API format
        # Reference: https://bybit-exchange.github.io/docs/v5/websocket/private/execution
        symbol = response.get("symbol", "")
        side = response.get("side", "Buy").lower()

        # Normalize side
        side = "buy" if side in ("buy", "b") else "sell"

        # Parse timestamp (Bybit uses milliseconds)
        timestamp_ms = int(response.get("execTime", 0))
        timestamp = datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)

        # Determine fee currency from symbol
        fee_currency = response.get("feeCurrency", "USDT")
        if not fee_currency and symbol:
            # Extract quote currency from symbol (e.g., BTCUSDT -> USDT)
            if "USDT" in symbol:
                fee_currency = "USDT"
            elif "USD" in symbol:
                fee_currency = "USD"
            else:
                fee_currency = "USDT"  # Default

        return cls(
            order_id=response.get("orderId", ""),
            fill_id=response.get("execId", ""),
            symbol=symbol,
            side=side,
            price=Decimal(str(response.get("execPrice", 0))),
            quantity=Decimal(str(response.get("execQty", 0))),
            timestamp=timestamp,
            fee=Decimal(str(response.get("execFee", 0))),
            fee_currency=fee_currency,
            exchange="bybit",
            metadata={
                "exec_type": response.get("execType", ""),
                "is_maker": response.get("isMaker", False),
                "seq": response.get("seq", 0),
                "market_unit": response.get("marketUnit", ""),
            },
            # ST-VENUE-001: Venue provenance fields - derive from context
            execution_venue=response.get("execution_venue", "bybit"),
            execution_mode=response.get("execution_mode", ""),
        )

    @classmethod
    def from_bitget_response(cls, response: dict[str, Any]) -> Fill:
        """Create Fill from Bitget API response.

        Args:
            response: Bitget API fill/execution response

        Returns:
            Fill instance
        """
        # Bitget API format
        # Reference: https://www.bitget.com/api-doc/common/intro
        symbol = response.get("symbol", "")
        side = response.get("side", "buy").lower()

        # Normalize side
        side = "buy" if side in ("buy", "b", "long") else "sell"

        # Parse timestamp (Bitget uses milliseconds)
        timestamp_ms = int(response.get("cTime", response.get("uTime", 0)))
        timestamp = datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)

        # Determine fee currency
        fee_currency = response.get("feeCoin", "USDT")
        if not fee_currency and symbol:
            if "USDT" in symbol:
                fee_currency = "USDT"
            elif "USD" in symbol:
                fee_currency = "USD"
            else:
                fee_currency = "USDT"

        return cls(
            order_id=response.get("orderId", ""),
            fill_id=response.get("tradeId", response.get("fillId", "")),
            symbol=symbol,
            side=side,
            price=Decimal(str(response.get("price", 0))),
            quantity=Decimal(str(response.get("baseVolume", response.get("size", 0)))),
            timestamp=timestamp,
            fee=Decimal(str(response.get("fee", 0))),
            fee_currency=fee_currency,
            exchange="bitget",
            metadata={
                "trade_scope": response.get("tradeScope", ""),
                "order_type": response.get("orderType", ""),
                "force": response.get("force", ""),
                "enter_point_source": response.get("enterPointSource", ""),
            },
            # ST-VENUE-001: Venue provenance fields - derive from context
            execution_venue=response.get("execution_venue", "bitget"),
            execution_mode=response.get("execution_mode", ""),
        )


@dataclass
class FillBatch:
    """Batch of fills for efficient storage and processing.

    Attributes:
        fills: List of Fill objects
        exchange: Exchange name
        batch_timestamp: When batch was created
    """

    fills: list[Fill]
    exchange: str
    batch_timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __len__(self) -> int:
        """Return number of fills in batch."""
        return len(self.fills)

    @property
    def total_notional(self) -> Decimal:
        """Calculate total notional value of all fills."""
        return sum((f.notional_value for f in self.fills), Decimal("0"))

    @property
    def total_fees(self) -> Decimal:
        """Calculate total fees across all fills."""
        return sum((f.fee for f in self.fills), Decimal("0"))

    def to_dict(self) -> dict[str, Any]:
        """Convert batch to dictionary."""
        return {
            "fills": [f.to_dict() for f in self.fills],
            "exchange": self.exchange,
            "batch_timestamp": self.batch_timestamp.isoformat(),
            "count": len(self.fills),
            "total_notional": str(self.total_notional),
            "total_fees": str(self.total_fees),
        }
