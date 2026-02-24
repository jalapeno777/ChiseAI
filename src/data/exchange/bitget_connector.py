"""Bitget API connector for execution market data.

Provides async HTTP client and WebSocket support for Bitget API,
including real-time pricing, fills, positions, and stop orders.

For ST-DATA-002: Execution Market Data Ingestion - Bybit/Bitget
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import hmac
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, cast

import aiohttp
import websockets
from websockets.exceptions import ConnectionClosed, InvalidStatus

logger = logging.getLogger(__name__)


@dataclass
class BitgetConfig:
    """Configuration for Bitget API connection.

    Attributes:
        api_key: Bitget API key
        api_secret: Bitget API secret
        passphrase: Bitget API passphrase
        base_url: REST API base URL
        ws_url: WebSocket base URL
        testnet: Whether to use testnet
    """

    api_key: str = ""
    api_secret: str = ""
    passphrase: str = ""
    base_url: str = "https://api.bitget.com"
    ws_url: str = "wss://ws.bitget.com/v2/ws/public"
    private_ws_url: str = "wss://ws.bitget.com/v2/ws/private"
    testnet: bool = False

    def __post_init__(self) -> None:
        """Adjust URLs for testnet if needed."""
        if self.testnet:
            self.base_url = "https://api.bitget.com"  # Bitget uses same endpoint
            self.ws_url = "wss://ws.bitget.com/v2/ws/public"
            self.private_ws_url = "wss://ws.bitget.com/v2/ws/private"


@dataclass
class ConnectionHealth:
    """Connection health status.

    Attributes:
        is_connected: Whether connection is active
        last_heartbeat: Timestamp of last successful heartbeat
        last_message: Timestamp of last received message
        reconnect_count: Number of reconnections
        latency_ms: Current latency in milliseconds
    """

    is_connected: bool = False
    last_heartbeat: float = 0.0
    last_message: float = 0.0
    reconnect_count: int = 0
    latency_ms: float = 0.0

    @property
    def time_since_last_message(self) -> float:
        """Time since last message in seconds."""
        if self.last_message == 0:
            return float("inf")
        return time.time() - self.last_message


class BitgetConnector:
    """Async HTTP and WebSocket client for Bitget API.

    Provides methods for:
    - Real-time pricing data (<100ms latency)
    - Fill data capture
    - Position queries
    - Stop order (SL/TP) queries
    - Heartbeat monitoring (30s intervals)
    - Exponential backoff reconnect (max 60s)

    For ST-DATA-002: Execution Market Data Ingestion
    """

    # Exponential backoff delays: 1s, 2s, 4s, 8s, 16s, 32s, 60s max
    RECONNECT_DELAYS = [1, 2, 4, 8, 16, 32, 60]
    HEARTBEAT_INTERVAL = 30  # seconds
    MAX_LATENCY_MS = 100  # milliseconds for real-time pricing

    def __init__(self, config: BitgetConfig | None = None) -> None:
        """Initialize Bitget connector.

        Args:
            config: Bitget configuration (uses defaults if None)
        """
        self.config = config or BitgetConfig()
        self._session: aiohttp.ClientSession | None = None
        self._ws: Any | None = None  # WebSocketClientProtocol from websockets
        self._private_ws: Any | None = None  # WebSocketClientProtocol from websockets
        self._health = ConnectionHealth()
        self._reconnect_attempt = 0
        self._running = False
        self._message_callbacks: list[Callable[[dict[str, Any]], None]] = []
        self._price_callbacks: list[Callable[[str, Decimal], None]] = []
        self._fill_callbacks: list[Callable[[dict[str, Any]], None]] = []
        self._heartbeat_task: asyncio.Task | None = None
        self._ws_task: asyncio.Task | None = None

    async def __aenter__(self) -> BitgetConnector:
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.close()

    async def connect(self) -> None:
        """Initialize HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "Content-Type": "application/json",
                    "ACCESS-KEY": self.config.api_key,
                }
            )
            logger.info("Bitget HTTP session initialized")

    async def close(self) -> None:
        """Close all connections."""
        self._running = False

        # Cancel background tasks
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._heartbeat_task

        if self._ws_task and not self._ws_task.done():
            self._ws_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._ws_task

        # Close WebSocket
        if self._ws:
            await self._ws.close()
            self._ws = None

        if self._private_ws:
            await self._private_ws.close()
            self._private_ws = None

        # Close HTTP session
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

        logger.info("Bitget connector closed")

    def _generate_signature(
        self, timestamp: str, method: str, request_path: str, body: str = ""
    ) -> tuple[str, str]:
        """Generate HMAC signature for authenticated requests.

        Bitget uses a specific signing format:
        timestamp + method.upper() + request_path + body

        Args:
            timestamp: Request timestamp in milliseconds
            method: HTTP method (GET, POST, etc.)
            request_path: API endpoint path
            body: Request body (for POST requests)

        Returns:
            Tuple of (signature, passphrase_signature)
        """
        message = timestamp + method.upper() + request_path + body
        signature = base64.b64encode(
            hmac.new(
                self.config.api_secret.encode(),
                message.encode(),
                hashlib.sha256,
            ).digest()
        ).decode()

        # Passphrase also needs to be signed
        passphrase_sig = base64.b64encode(
            hmac.new(
                self.config.api_secret.encode(),
                self.config.passphrase.encode(),
                hashlib.sha256,
            ).digest()
        ).decode()

        return signature, passphrase_sig

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        signed: bool = False,
    ) -> dict[str, Any]:
        """Make HTTP request to Bitget API.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            params: Query parameters or body
            signed: Whether to sign the request

        Returns:
            JSON response as dictionary

        Raises:
            aiohttp.ClientError: On HTTP errors
            ValueError: On API errors
        """
        if self._session is None:
            raise RuntimeError(
                "Client not connected. Use 'async with' or call connect()"
            )

        url = f"{self.config.base_url}{endpoint}"
        headers = {}
        body = ""

        if signed:
            timestamp = str(int(time.time() * 1000))
            signature, passphrase_sig = self._generate_signature(
                timestamp, method, endpoint, body
            )

            headers["ACCESS-TIMESTAMP"] = timestamp
            headers["ACCESS-SIGN"] = signature
            headers["ACCESS-PASSPHRASE"] = passphrase_sig

        try:
            async with self._session.request(
                method,
                url,
                params=params if method == "GET" else None,
                json=params if method != "GET" else None,
                headers=headers,
            ) as response:
                data = await response.json()

                if response.status != 200 or data.get("code") != "00000":
                    error_msg = data.get("msg", f"HTTP {response.status}")
                    raise ValueError(f"Bitget API error: {error_msg}")

                self._health.last_message = time.time()
                return cast(dict[str, Any], data)

        except Exception as e:
            logger.error(f"Bitget API request failed: {e}")
            raise

    # === Public Market Data Methods ===

    async def get_ticker(self, symbol: str) -> dict[str, Any]:
        """Get ticker data for symbol.

        Args:
            symbol: Trading pair (e.g., "BTCUSDT")

        Returns:
            Ticker data with price, volume, etc.
        """
        return await self._make_request(
            "GET",
            "/api/v2/mix/market/ticker",
            params={"symbol": symbol, "productType": "USDT-FUTURES"},
        )

    async def get_orderbook(self, symbol: str, limit: int = 50) -> dict[str, Any]:
        """Get order book snapshot.

        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            limit: Number of bids/asks (1-150)

        Returns:
            Order book data with bids, asks, and timestamp
        """
        return await self._make_request(
            "GET",
            "/api/v2/mix/market/orderbook",
            params={"symbol": symbol, "productType": "USDT-FUTURES", "limit": limit},
        )

    # === Private Account Methods (Signed) ===

    async def get_fills(
        self,
        symbol: str | None = None,
        order_id: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Get fill history.

        Args:
            symbol: Trading pair filter (optional)
            order_id: Order ID filter (optional)
            start_time: Start timestamp (ISO format) (optional)
            end_time: End timestamp (ISO format) (optional)
            limit: Number of records (max 100)

        Returns:
            Fill data with order_id, price, quantity, timestamp, fees
        """
        params: dict[str, Any] = {"productType": "USDT-FUTURES", "limit": limit}

        if symbol:
            params["symbol"] = symbol
        if order_id:
            params["orderId"] = order_id
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time

        return await self._make_request(
            "GET",
            "/api/v2/mix/order/fills",
            params=params,
            signed=True,
        )

    async def get_positions(
        self,
        symbol: str | None = None,
        margin_coin: str | None = None,
    ) -> dict[str, Any]:
        """Get position information.

        Args:
            symbol: Trading pair filter (optional)
            margin_coin: Margin coin filter (optional)

        Returns:
            Position data with size, entry price, leverage, etc.
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

    async def get_stop_orders(
        self,
        symbol: str | None = None,
        order_id: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Get stop loss / take profit orders.

        Args:
            symbol: Trading pair filter (optional)
            order_id: Order ID filter (optional)
            limit: Number of records (max 100)

        Returns:
            Stop order data with trigger price, type, etc.
        """
        params: dict[str, Any] = {
            "productType": "USDT-FUTURES",
            "limit": limit,
        }

        if symbol:
            params["symbol"] = symbol
        if order_id:
            params["orderId"] = order_id

        return await self._make_request(
            "GET",
            "/api/v2/mix/order/orders",
            params=params,
            signed=True,
        )

    # === Order Execution Methods ===

    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: float | None = None,
        time_in_force: str = "GTC",
        reduce_only: bool = False,
    ) -> dict[str, Any]:
        """Place a new order.

        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            side: Order side ("buy" or "sell")
            order_type: Order type ("market", "limit")
            quantity: Order quantity
            price: Order price (required for limit orders)
            time_in_force: Time in force ("GTC", "IOC", "FOK")
            reduce_only: Whether order should only reduce position

        Returns:
            Order result with order_id, price, quantity, etc.
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

        result = await self._make_request(
            "POST",
            "/api/v2/mix/order/place-order",
            params=params,
            signed=True,
        )

        # Extract and normalize result
        order_data = result.get("data", {})
        return {
            "order_id": order_data.get("orderId", ""),
            "symbol": symbol,
            "side": side,
            "order_type": order_type,
            "quantity": quantity,
            "price": price or 0.0,
            "status": order_data.get("status", "created"),
            "raw_response": result,
        }

    async def cancel_order(self, symbol: str, order_id: str) -> dict[str, Any]:
        """Cancel an existing order.

        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            order_id: Order ID to cancel

        Returns:
            Cancel result with status
        """
        params: dict[str, Any] = {
            "symbol": symbol,
            "productType": "USDT-FUTURES",
            "orderId": order_id,
        }

        result = await self._make_request(
            "POST",
            "/api/v2/mix/order/cancel-order",
            params=params,
            signed=True,
        )

        return {
            "order_id": order_id,
            "symbol": symbol,
            "status": "cancelled",
            "raw_response": result,
        }

    async def close_position_market(
        self,
        symbol: str,
        side: str,
        quantity: float,
    ) -> dict[str, Any]:
        """Close a position with a market order.

        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            side: Order side ("buy" to close short, "sell" to close long)
            quantity: Quantity to close

        Returns:
            Close result with order_id, execution price, quantity, etc.
        """
        # Normalize side for closing
        order_side = "sell" if side.lower() == "sell" else "buy"

        # Place market order with reduce_only=True
        result = await self.place_order(
            symbol=symbol,
            side=order_side,
            order_type="market",
            quantity=quantity,
            reduce_only=True,
        )

        # Add close-specific metadata
        result["close_type"] = "market"
        result["original_side"] = side

        logger.info(
            f"Position closed via market order: {symbol} {side} {quantity} "
            f"[order_id={result.get('order_id', 'unknown')}]"
        )

        return result

    # === WebSocket Methods ===

    async def start_websocket(self, symbols: list[str] | None = None) -> None:
        """Start WebSocket connection for real-time data.

        Args:
            symbols: List of symbols to subscribe to (e.g., ["BTCUSDT", "ETHUSDT"])
        """
        self._running = True
        self._ws_task = asyncio.create_task(
            self._websocket_loop(symbols or ["BTCUSDT"])
        )
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _websocket_loop(self, symbols: list[str]) -> None:
        """Main WebSocket connection loop with reconnection."""
        while self._running:
            try:
                await self._connect_and_listen(symbols)
            except Exception as e:
                logger.error(f"WebSocket error: {e}")

            if not self._running:
                break

            # Exponential backoff reconnect
            delay = self.RECONNECT_DELAYS[
                min(self._reconnect_attempt, len(self.RECONNECT_DELAYS) - 1)
            ]
            logger.warning(
                f"Reconnecting in {delay}s (attempt {self._reconnect_attempt + 1})"
            )
            await asyncio.sleep(delay)
            self._reconnect_attempt += 1

    async def _connect_and_listen(self, symbols: list[str]) -> None:
        """Connect to WebSocket and listen for messages."""
        try:
            async with websockets.connect(self.config.ws_url) as ws:
                self._ws = ws
                self._health.is_connected = True
                self._reconnect_attempt = 0  # Reset on successful connection

                # Subscribe to tickers
                subscribe_msg = {
                    "op": "subscribe",
                    "args": [
                        {
                            "instType": "USDT-FUTURES",
                            "channel": "ticker",
                            "instId": s,
                        }
                        for s in symbols
                    ],
                }
                await ws.send(json.dumps(subscribe_msg))
                logger.info(f"Subscribed to WebSocket tickers: {symbols}")

                # Listen for messages
                async for message in ws:
                    if not self._running:
                        break

                    try:
                        data = json.loads(message)
                        await self._handle_message(data)
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON: {message!r}")

        except ConnectionClosed as e:
            logger.warning(f"WebSocket closed: {e}")
        except InvalidStatus as e:
            logger.error(f"WebSocket connection failed: {e}")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
        finally:
            self._health.is_connected = False
            self._ws = None

    async def _handle_message(self, data: dict[str, Any]) -> None:
        """Handle incoming WebSocket message."""
        self._health.last_message = time.time()

        event = data.get("event", "")

        if event == "subscribe":
            logger.info(f"Subscribed: {data}")
            return

        if event == "error":
            logger.error(f"WebSocket error: {data}")
            return

        # Handle ticker data
        arg = data.get("arg", {})
        if arg.get("channel") == "ticker":
            ticker_data = data.get("data", [{}])[0]
            symbol = ticker_data.get("instId", "")
            last_price = ticker_data.get("lastPr", "0")

            if symbol and last_price:
                for callback in self._price_callbacks:
                    try:
                        callback(symbol, Decimal(last_price))
                    except Exception as e:
                        logger.error(f"Price callback error: {e}")

        # Call general message callbacks
        for callback in self._message_callbacks:  # type: ignore[assignment]
            try:
                callback(data)  # type: ignore[call-arg, arg-type]
            except Exception as e:
                logger.error(f"Message callback error: {e}")

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeats to keep connection alive."""
        while self._running:
            try:
                if self._ws and self._health.is_connected:
                    await self._ws.send(json.dumps({"op": "ping"}))
                    logger.debug("Sent heartbeat ping")

                await asyncio.sleep(self.HEARTBEAT_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Heartbeat error: {e}")
                await asyncio.sleep(5)

    async def start_private_websocket(self) -> None:
        """Start private WebSocket for fills and position updates."""
        if not self.config.api_key or not self.config.api_secret:
            raise ValueError("API key and secret required for private WebSocket")

        asyncio.create_task(self._private_websocket_loop())

    async def _private_websocket_loop(self) -> None:
        """Private WebSocket connection loop."""
        while self._running:
            try:
                await self._connect_and_listen_private()
            except Exception as e:
                logger.error(f"Private WebSocket error: {e}")

            if not self._running:
                break

            delay = self.RECONNECT_DELAYS[
                min(self._reconnect_attempt, len(self.RECONNECT_DELAYS) - 1)
            ]
            await asyncio.sleep(delay)

    async def _connect_and_listen_private(self) -> None:
        """Connect to private WebSocket and listen."""
        # Generate auth signature
        timestamp = str(int(time.time()))
        signature, passphrase_sig = self._generate_signature(
            timestamp, "GET", "/user/verify"
        )

        auth_msg = {
            "op": "login",
            "args": [
                {
                    "apiKey": self.config.api_key,
                    "passphrase": passphrase_sig,
                    "timestamp": timestamp,
                    "sign": signature,
                }
            ],
        }

        try:
            async with websockets.connect(self.config.private_ws_url) as ws:
                self._private_ws = ws

                # Authenticate
                await ws.send(json.dumps(auth_msg))

                # Subscribe to order/fill updates
                subscribe_msg = {
                    "op": "subscribe",
                    "args": [
                        {
                            "instType": "USDT-FUTURES",
                            "channel": "orders",
                            "instId": "default",
                        }
                    ],
                }
                await ws.send(json.dumps(subscribe_msg))

                logger.info("Private WebSocket connected and subscribed")

                async for message in ws:
                    if not self._running:
                        break

                    try:
                        data = json.loads(message)
                        await self._handle_private_message(data)
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON: {message!r}")

        except Exception as e:
            logger.error(f"Private WebSocket error: {e}")
        finally:
            self._private_ws = None

    async def _handle_private_message(self, data: dict[str, Any]) -> None:
        """Handle private WebSocket message (fills, positions)."""
        arg = data.get("arg", {})

        if arg.get("channel") == "orders":
            # Order/fill update
            for callback in self._fill_callbacks:
                try:
                    callback(data.get("data", []))
                except Exception as e:
                    logger.error(f"Fill callback error: {e}")

    # === Callback Registration ===

    def on_message(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Register callback for all messages."""
        self._message_callbacks.append(callback)

    def on_price(self, callback: Callable[[str, Decimal], None]) -> None:
        """Register callback for price updates."""
        self._price_callbacks.append(callback)

    def on_fill(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Register callback for fill updates."""
        self._fill_callbacks.append(callback)

    # === Health Monitoring ===

    def get_health(self) -> ConnectionHealth:
        """Get current connection health status."""
        return self._health

    def is_healthy(self) -> bool:
        """Check if connection is healthy.

        Returns:
            True if connected and receiving messages within heartbeat interval
        """
        if not self._health.is_connected:
            return False

        # Check if we've received messages recently (2x heartbeat interval)
        return not self._health.time_since_last_message > self.HEARTBEAT_INTERVAL * 2

    async def health_check(self) -> dict[str, Any]:
        """Perform health check and return status.

        Returns:
            Health status dictionary
        """
        # Try a simple API call
        api_healthy = False
        try:
            await self.get_ticker("BTCUSDT")
            api_healthy = True
        except Exception as e:
            logger.warning(f"Health check API call failed: {e}")

        return {
            "healthy": self.is_healthy() and api_healthy,
            "connected": self._health.is_connected,
            "last_message_seconds_ago": self._health.time_since_last_message,
            "reconnect_count": self._health.reconnect_count,
            "api_accessible": api_healthy,
            "timestamp": time.time(),
        }
