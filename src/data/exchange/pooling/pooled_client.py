"""Pooled exchange client wrapper.

Provides drop-in replacements for Bybit and Bitget connectors
that use connection pooling for improved performance.

For ST-NS-026: Connection Pooling for Exchange APIs
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any


from data.exchange.pooling.connection_pool import ExchangeConnectionPool, PoolMetrics

logger = logging.getLogger(__name__)


@dataclass
class OrderResult:
    """Result from placing an order."""

    order_id: str
    symbol: str
    side: str
    order_type: str
    quantity: float
    price: float
    status: str
    raw_response: dict[str, Any]


@dataclass
class OrderBook:
    """Order book data."""

    symbol: str
    bids: list[list[str]]  # [price, size]
    asks: list[list[str]]  # [price, size]
    timestamp: int
    raw_response: dict[str, Any]


class PooledExchangeClient:
    """Base class for pooled exchange clients.

    Wraps exchange-specific API calls with connection pooling
    for reduced latency and improved throughput.
    """

    def __init__(
        self,
        exchange: str,
        api_key: str = "",
        api_secret: str = "",
        passphrase: str = "",  # For Bitget
        base_url: str = "",
        pool_config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize pooled exchange client.

        Args:
            exchange: Exchange name
            api_key: API key
            api_secret: API secret
            passphrase: API passphrase (Bitget only)
            base_url: API base URL
            pool_config: Connection pool configuration
        """
        self.exchange = exchange
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.base_url = base_url

        # Default pool config
        pool_config = pool_config or {}
        pool_config.setdefault("pool_size", 10)
        pool_config.setdefault("max_connections", 20)
        pool_config.setdefault("connection_timeout", 30)
        pool_config.setdefault("keepalive", True)
        pool_config.setdefault(
            "rate_limit", {"requests_per_minute": 60, "burst_size": 5}
        )

        # Initialize pool
        self._pool = ExchangeConnectionPool(
            exchange=exchange,
            pool_size=pool_config["pool_size"],
            max_connections=pool_config["max_connections"],
            connection_timeout=pool_config["connection_timeout"],
            keepalive=pool_config["keepalive"],
            rate_limit=pool_config["rate_limit"],
        )

        self._callbacks: dict[str, list[Callable]] = {
            "price": [],
            "message": [],
            "fill": [],
        }

    async def __aenter__(self) -> PooledExchangeClient:
        """Async context manager entry."""
        await self._pool.initialize()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self._pool.close_all()

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        signed: bool = False,
    ) -> dict[str, Any]:
        """Make an HTTP request using pooled connection.

        Args:
            method: HTTP method
            endpoint: API endpoint
            params: Query/body parameters
            signed: Whether to sign the request

        Returns:
            JSON response
        """
        url = f"{self.base_url}{endpoint}"
        headers = {}

        if signed:
            headers.update(self._sign_request(method, endpoint, params))

        async with self._pool.get_connection() as conn:
            async with conn.session.request(
                method,
                url,
                params=params if method == "GET" else None,
                json=params if method != "GET" else None,
                headers=headers,
            ) as response:
                response.raise_for_status()
                return await response.json()

    def _sign_request(
        self, method: str, endpoint: str, params: dict[str, Any] | None = None
    ) -> dict[str, str]:
        """Sign a request - override in subclass."""
        raise NotImplementedError("Subclasses must implement _sign_request")

    def get_metrics(self) -> PoolMetrics:
        """Get pool metrics."""
        return self._pool.get_metrics()

    def on_price(self, callback: Callable[[str, Decimal], None]) -> None:
        """Register price callback."""
        self._callbacks["price"].append(callback)

    def on_message(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Register message callback."""
        self._callbacks["message"].append(callback)

    def on_fill(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Register fill callback."""
        self._callbacks["fill"].append(callback)


class PooledBybitClient(PooledExchangeClient):
    """Pooled Bybit V5 API client.

    Drop-in replacement for BybitConnector with connection pooling.

    Example:
        async with PooledBybitClient(api_key="...", api_secret="...") as client:
            price = await client.get_price("BTCUSDT")
            print(f"BTC price: {price}")
    """

    DEFAULT_BASE_URL = "https://api.bybit.com"
    DEFAULT_RATE_LIMIT = {"requests_per_minute": 120, "burst_size": 10}
    RECV_WINDOW = 5000

    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
        base_url: str = "",
        testnet: bool = False,
        pool_config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize pooled Bybit client.

        Args:
            api_key: Bybit API key
            api_secret: Bybit API secret
            base_url: API base URL (uses default if not provided)
            testnet: Use testnet endpoints
            pool_config: Pool configuration
        """
        if testnet:
            base_url = "https://api-testnet.bybit.com"
        elif not base_url:
            base_url = self.DEFAULT_BASE_URL

        # Apply Bybit-specific rate limits
        pool_config = pool_config or {}
        pool_config.setdefault("rate_limit", self.DEFAULT_RATE_LIMIT)

        super().__init__(
            exchange="bybit",
            api_key=api_key,
            api_secret=api_secret,
            base_url=base_url,
            pool_config=pool_config,
        )

        self.testnet = testnet

    def _sign_request(
        self, method: str, endpoint: str, params: dict[str, Any] | None = None
    ) -> dict[str, str]:
        """Sign request for Bybit API."""
        timestamp = str(int(time.time() * 1000))

        # Build payload string
        payload = ""
        if method == "GET" and params:
            payload = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        elif params:
            payload = json.dumps(params)

        param_str = timestamp + self.api_key + str(self.RECV_WINDOW) + payload
        signature = hmac.new(
            self.api_secret.encode(),
            param_str.encode(),
            hashlib.sha256,
        ).hexdigest()

        return {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": str(self.RECV_WINDOW),
            "X-BAPI-SIGN": signature,
        }

    async def get_price(self, symbol: str) -> float:
        """Get current price for a symbol.

        Args:
            symbol: Trading pair (e.g., "BTCUSDT")

        Returns:
            Current last price
        """
        response = await self._make_request(
            "GET",
            "/v5/market/tickers",
            params={"category": "linear", "symbol": symbol},
        )

        result = response.get("result", {})
        list_data = result.get("list", [{}])
        if list_data:
            return float(list_data[0].get("lastPrice", 0))
        return 0.0

    async def get_orderbook(self, symbol: str, limit: int = 50) -> OrderBook:
        """Get order book for a symbol.

        Args:
            symbol: Trading pair
            limit: Number of levels (1, 25, 50, 100, 200, 500)

        Returns:
            OrderBook data
        """
        response = await self._make_request(
            "GET",
            "/v5/market/orderbook",
            params={"category": "linear", "symbol": symbol, "limit": limit},
        )

        result = response.get("result", {})
        return OrderBook(
            symbol=symbol,
            bids=result.get("b", []),
            asks=result.get("a", []),
            timestamp=result.get("ts", 0),
            raw_response=response,
        )

    async def get_ticker(self, symbol: str) -> dict[str, Any]:
        """Get 24hr ticker data.

        Args:
            symbol: Trading pair

        Returns:
            Ticker data
        """
        return await self._make_request(
            "GET",
            "/v5/market/tickers",
            params={"category": "linear", "symbol": symbol},
        )

    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: float | None = None,
        time_in_force: str = "GTC",
        reduce_only: bool = False,
    ) -> OrderResult:
        """Place an order.

        Args:
            symbol: Trading pair
            side: "Buy" or "Sell"
            order_type: "Market" or "Limit"
            quantity: Order quantity
            price: Order price (for limit orders)
            time_in_force: Time in force
            reduce_only: Whether to reduce position only

        Returns:
            Order result
        """
        params: dict[str, Any] = {
            "category": "linear",
            "symbol": symbol,
            "side": side.capitalize(),
            "orderType": order_type.capitalize(),
            "qty": str(quantity),
            "timeInForce": time_in_force,
            "reduceOnly": reduce_only,
        }

        if order_type.lower() == "limit" and price is not None:
            params["price"] = str(price)

        response = await self._make_request(
            "POST",
            "/v5/order/create",
            params=params,
            signed=True,
        )

        result = response.get("result", {})
        return OrderResult(
            order_id=result.get("orderId", ""),
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price or 0.0,
            status=result.get("orderStatus", "Created"),
            raw_response=response,
        )

    async def cancel_order(self, symbol: str, order_id: str) -> dict[str, Any]:
        """Cancel an order.

        Args:
            symbol: Trading pair
            order_id: Order ID to cancel

        Returns:
            Cancel result
        """
        return await self._make_request(
            "POST",
            "/v5/order/cancel",
            params={
                "category": "linear",
                "symbol": symbol,
                "orderId": order_id,
            },
            signed=True,
        )

    async def get_positions(
        self,
        symbol: str | None = None,
        settle_coin: str | None = None,
    ) -> dict[str, Any]:
        """Get position information.

        Args:
            symbol: Filter by symbol
            settle_coin: Filter by settle coin

        Returns:
            Position data
        """
        params: dict[str, Any] = {"category": "linear"}
        if symbol:
            params["symbol"] = symbol
        if settle_coin:
            params["settleCoin"] = settle_coin

        return await self._make_request(
            "GET",
            "/v5/position/list",
            params=params,
            signed=True,
        )

    async def get_fills(
        self,
        symbol: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Get fill/execution history.

        Args:
            symbol: Filter by symbol
            limit: Number of records

        Returns:
            Fill data
        """
        params: dict[str, Any] = {"category": "linear", "limit": limit}
        if symbol:
            params["symbol"] = symbol

        return await self._make_request(
            "GET",
            "/v5/execution/list",
            params=params,
            signed=True,
        )


class PooledBitgetClient(PooledExchangeClient):
    """Pooled Bitget API client.

    Drop-in replacement for BitgetConnector with connection pooling.

    Example:
        async with PooledBitgetClient(
            api_key="...",
            api_secret="...",
            passphrase="..."
        ) as client:
            price = await client.get_price("BTCUSDT")
            print(f"BTC price: {price}")
    """

    DEFAULT_BASE_URL = "https://api.bitget.com"
    DEFAULT_RATE_LIMIT = {"requests_per_minute": 60, "burst_size": 5}

    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
        passphrase: str = "",
        base_url: str = "",
        testnet: bool = False,
        pool_config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize pooled Bitget client.

        Args:
            api_key: Bitget API key
            api_secret: Bitget API secret
            passphrase: Bitget API passphrase
            base_url: API base URL
            testnet: Use testnet (not applicable for Bitget)
            pool_config: Pool configuration
        """
        if not base_url:
            base_url = self.DEFAULT_BASE_URL

        # Apply Bitget-specific rate limits
        pool_config = pool_config or {}
        pool_config.setdefault("rate_limit", self.DEFAULT_RATE_LIMIT)

        super().__init__(
            exchange="bitget",
            api_key=api_key,
            api_secret=api_secret,
            passphrase=passphrase,
            base_url=base_url,
            pool_config=pool_config,
        )

    def _sign_request(
        self, method: str, endpoint: str, params: dict[str, Any] | None = None
    ) -> dict[str, str]:
        """Sign request for Bitget API."""
        import base64

        timestamp = str(int(time.time() * 1000))
        body = json.dumps(params) if params else ""

        message = timestamp + method.upper() + endpoint + body
        signature = base64.b64encode(
            hmac.new(
                self.api_secret.encode(),
                message.encode(),
                hashlib.sha256,
            ).digest()
        ).decode()

        passphrase_sig = base64.b64encode(
            hmac.new(
                self.api_secret.encode(),
                self.passphrase.encode(),
                hashlib.sha256,
            ).digest()
        ).decode()

        return {
            "ACCESS-KEY": self.api_key,
            "ACCESS-TIMESTAMP": timestamp,
            "ACCESS-SIGN": signature,
            "ACCESS-PASSPHRASE": passphrase_sig,
            "Content-Type": "application/json",
        }

    async def get_price(self, symbol: str) -> float:
        """Get current price for a symbol.

        Args:
            symbol: Trading pair (e.g., "BTCUSDT")

        Returns:
            Current last price
        """
        response = await self._make_request(
            "GET",
            "/api/v2/mix/market/ticker",
            params={"symbol": symbol, "productType": "USDT-FUTURES"},
        )

        data = response.get("data", [{}])
        if data:
            return float(data[0].get("lastPr", 0))
        return 0.0

    async def get_orderbook(self, symbol: str, limit: int = 50) -> OrderBook:
        """Get order book for a symbol.

        Args:
            symbol: Trading pair
            limit: Number of levels (1-150)

        Returns:
            OrderBook data
        """
        response = await self._make_request(
            "GET",
            "/api/v2/mix/market/orderbook",
            params={
                "symbol": symbol,
                "productType": "USDT-FUTURES",
                "limit": limit,
            },
        )

        data = response.get("data", {})
        return OrderBook(
            symbol=symbol,
            bids=data.get("bids", []),
            asks=data.get("asks", []),
            timestamp=data.get("ts", 0),
            raw_response=response,
        )

    async def get_ticker(self, symbol: str) -> dict[str, Any]:
        """Get ticker data.

        Args:
            symbol: Trading pair

        Returns:
            Ticker data
        """
        return await self._make_request(
            "GET",
            "/api/v2/mix/market/ticker",
            params={"symbol": symbol, "productType": "USDT-FUTURES"},
        )

    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: float | None = None,
        time_in_force: str = "GTC",
        reduce_only: bool = False,
    ) -> OrderResult:
        """Place an order.

        Args:
            symbol: Trading pair
            side: "buy" or "sell"
            order_type: "market" or "limit"
            quantity: Order quantity
            price: Order price (for limit orders)
            time_in_force: Time in force
            reduce_only: Whether to reduce position only

        Returns:
            Order result
        """
        params: dict[str, Any] = {
            "symbol": symbol,
            "productType": "USDT-FUTURES",
            "marginMode": "crossed",
            "marginCoin": "USDT",
            "side": side.lower(),
            "orderType": order_type.lower(),
            "size": str(quantity),
            "timeInForceValue": time_in_force,
            "reduceOnly": reduce_only,
        }

        if order_type.lower() == "limit" and price is not None:
            params["price"] = str(price)

        response = await self._make_request(
            "POST",
            "/api/v2/mix/order/place-order",
            params=params,
            signed=True,
        )

        data = response.get("data", {})
        return OrderResult(
            order_id=data.get("orderId", ""),
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price or 0.0,
            status=data.get("status", "created"),
            raw_response=response,
        )

    async def cancel_order(self, symbol: str, order_id: str) -> dict[str, Any]:
        """Cancel an order.

        Args:
            symbol: Trading pair
            order_id: Order ID to cancel

        Returns:
            Cancel result
        """
        return await self._make_request(
            "POST",
            "/api/v2/mix/order/cancel-order",
            params={
                "symbol": symbol,
                "productType": "USDT-FUTURES",
                "orderId": order_id,
            },
            signed=True,
        )

    async def get_positions(
        self,
        symbol: str | None = None,
        margin_coin: str | None = None,
    ) -> dict[str, Any]:
        """Get position information.

        Args:
            symbol: Filter by symbol
            margin_coin: Filter by margin coin

        Returns:
            Position data
        """
        params: dict[str, Any] = {"productType": "USDT-FUTURES"}
        if symbol:
            params["symbol"] = symbol
        if margin_coin:
            params["marginCoin"] = margin_coin

        return await self._make_request(
            "GET",
            "/api/v2/mix/position/all-position",
            params=params,
            signed=True,
        )

    async def get_fills(
        self,
        symbol: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Get fill history.

        Args:
            symbol: Filter by symbol
            limit: Number of records

        Returns:
            Fill data
        """
        params: dict[str, Any] = {"productType": "USDT-FUTURES", "limit": limit}
        if symbol:
            params["symbol"] = symbol

        return await self._make_request(
            "GET",
            "/api/v2/mix/order/fills",
            params=params,
            signed=True,
        )
