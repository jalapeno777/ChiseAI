"""Bybit V5 API connector for execution market data.

Provides async HTTP client and WebSocket support for Bybit V5 API,
including real-time pricing, fills, positions, and stop orders.

For ST-DATA-002: Execution Market Data Ingestion - Bybit/Bitget

BYBIT DEMO ROUTING POLICY
=========================

Authoritative Endpoints:
- Demo REST base: https://api-demo.bybit.com
- Demo private WS: wss://stream-demo.bybit.com/v5/private
- Public market WS: wss://stream.bybit.com (mainnet for all public data)

Routing Decision Matrix:

| Operation Type | Protocol | Endpoint | Rationale |
|----------------|----------|----------|-----------|
| Market data (tickers, orderbook, klines) | REST | api-demo.bybit.com | Unauthenticated, standard HTTP |
| Account info, positions, balances | REST | api-demo.bybit.com | Authenticated, synchronous query |
| Order placement, modification, cancel | REST | api-demo.bybit.com | Authenticated, requires ack |
| Execution/fill history | REST | api-demo.bybit.com | Authenticated, paginated query |
| Real-time price updates | WebSocket | stream.bybit.com/v5/public | Public feed, lower latency |
| Real-time position updates | WebSocket | stream-demo.bybit.com/v5/private | Private feed, requires auth |
| Real-time fill notifications | WebSocket | stream-demo.bybit.com/v5/private | Private feed, requires auth |

Demo Mode Behavior:
- Uses demo REST for all authenticated operations
- Uses demo private WebSocket for authenticated streaming
- Uses mainnet public WebSocket for market data (shared across all modes)
- Falls back to REST polling if WebSocket connection fails

Fallback Strategy:
1. Attempt WebSocket connection (preferred for real-time)
2. If WS fails, fall back to REST polling (1-5s intervals)
3. Log all fallback events with context
4. Auto-retry WS connection with exponential backoff
"""

from __future__ import annotations

import asyncio
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
from websockets.asyncio.client import ClientConnection as WebSocketClientProtocol
from websockets.exceptions import ConnectionClosed, InvalidStatus

logger = logging.getLogger(__name__)


@dataclass
class BybitConfig:
    """Configuration for Bybit API connection.

    Attributes:
        api_key: Bybit API key
        api_secret: Bybit API secret
        base_url: REST API base URL
        ws_url: WebSocket base URL for public market data
        private_ws_url: WebSocket URL for private data (fills, positions)
        recv_window: Request receive window in milliseconds
        testnet: Whether to use testnet
        demo: Whether to use demo mode (demo accounts on mainnet)
    """

    api_key: str = ""
    api_secret: str = ""
    base_url: str = "https://api.bybit.com"
    ws_url: str = "wss://stream.bybit.com/v5/public/linear"
    private_ws_url: str = "wss://stream.bybit.com/v5/private"
    recv_window: int = 5000
    testnet: bool = False
    demo: bool = False

    def __post_init__(self) -> None:
        """Adjust URLs based on mode (demo, testnet, or live).

        Mode priority:
        - Demo mode (demo=True): Uses api-demo.bybit.com for REST and
          stream-demo.bybit.com for private WS, but mainnet for public WS
        - Testnet mode (testnet=True, demo=False): Uses testnet endpoints
        - Live mode (both False): Uses mainnet endpoints
        """
        if self.demo:
            # Demo mode: demo endpoints for REST and private WS,
            # but mainnet for public market data WS
            self.base_url = "https://api-demo.bybit.com"
            self.ws_url = (
                "wss://stream.bybit.com/v5/public/linear"  # Mainnet for public
            )
            self.private_ws_url = "wss://stream-demo.bybit.com/v5/private"
        elif self.testnet:
            # Testnet mode: all testnet endpoints
            self.base_url = "https://api-testnet.bybit.com"
            self.ws_url = "wss://stream-testnet.bybit.com/v5/public/linear"
            self.private_ws_url = "wss://stream-testnet.bybit.com/v5/private"

    @classmethod
    def from_env(cls, load_env: bool = True) -> BybitConfig:
        """Create configuration from environment variables.

        Uses credential resolver to support multiple env var naming
        conventions in priority order.

        Args:
            load_env: Whether to explicitly load .env file first

        Returns:
            BybitConfig with resolved credentials

        Raises:
            ValueError: If no credentials could be resolved

        Example:
            >>> config = BybitConfig.from_env()
            >>> print(f"Using {config.api_key[:4]}... key")
        """
        from data.exchange.credential_resolver import resolve_bybit_credentials

        credentials = resolve_bybit_credentials(load_env=load_env)

        if not credentials:
            raise ValueError(
                "No Bybit credentials found. Checked (in priority order):\n"
                "  - BYBIT_DEMO_API_KEY / BYBIT_DEMO_API_SECRET\n"
                "  - BYBIT_API_KEY / BYBIT_API_SECRET\n"
                "  - BYBIT_TESTNET_API_KEY / BYBIT_TESTNET_API_SECRET\n"
                "Ensure credentials are set in environment variables or .env file."
            )

        logger.info(f"BybitConfig created from {credentials.source}")

        return cls(
            api_key=credentials.api_key,
            api_secret=credentials.api_secret,
            testnet=credentials.testnet_mode,
            demo=credentials.demo_mode,
        )


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


class BybitConnector:
    """Async HTTP and WebSocket client for Bybit V5 API.

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

    def __init__(self, config: BybitConfig | None = None) -> None:
        """Initialize Bybit connector.

        Args:
            config: Bybit configuration (uses defaults if None)
        """
        self.config = config or BybitConfig()
        self._session: aiohttp.ClientSession | None = None
        self._ws: WebSocketClientProtocol | None = None
        self._private_ws: WebSocketClientProtocol | None = None
        self._health = ConnectionHealth()
        self._reconnect_attempt = 0
        self._running = False
        self._message_callbacks: list[Callable[[dict[str, Any]], None]] = []
        self._price_callbacks: list[Callable[[str, Decimal], None]] = []
        self._fill_callbacks: list[Callable[[dict[str, Any]], None]] = []
        self._heartbeat_task: asyncio.Task | None = None
        self._ws_task: asyncio.Task | None = None

    @classmethod
    def from_env(cls, load_env: bool = True) -> BybitConnector:
        """Create connector with credentials from environment.

        Uses credential resolver to support multiple env var naming
        conventions in priority order.

        Args:
            load_env: Whether to explicitly load .env file first

        Returns:
            BybitConnector with resolved credentials

        Raises:
            ValueError: If no credentials could be resolved

        Example:
            >>> async with BybitConnector.from_env() as connector:
            ...     ticker = await connector.get_ticker("BTCUSDT")
        """
        config = BybitConfig.from_env(load_env=load_env)
        return cls(config)

    async def __aenter__(self) -> BybitConnector:
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
                    "X-BAPI-API-KEY": self.config.api_key,
                }
            )
            logger.info("Bybit HTTP session initialized")

    async def close(self) -> None:
        """Close all connections."""
        self._running = False

        # Cancel background tasks
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        if self._ws_task and not self._ws_task.done():
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass

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

        logger.info("Bybit connector closed")

    def _generate_signature(self, timestamp: str, payload: str = "") -> str:
        """Generate HMAC signature for authenticated requests.

        Args:
            timestamp: Request timestamp in milliseconds
            payload: Request payload (query string or body)

        Returns:
            HMAC SHA256 signature hex digest
        """
        param_str = (
            timestamp + self.config.api_key + str(self.config.recv_window) + payload
        )
        return hmac.new(
            self.config.api_secret.encode(),
            param_str.encode(),
            hashlib.sha256,
        ).hexdigest()

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        signed: bool = False,
    ) -> dict[str, Any]:
        """Make HTTP request to Bybit API.

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
        payload = ""

        if signed:
            timestamp = str(int(time.time() * 1000))
            headers["X-BAPI-TIMESTAMP"] = timestamp
            headers["X-BAPI-RECV-WINDOW"] = str(self.config.recv_window)

            if method == "GET" and params:
                payload = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
            elif params:
                payload = json.dumps(params)

            headers["X-BAPI-SIGN"] = self._generate_signature(timestamp, payload)

        try:
            async with self._session.request(
                method,
                url,
                params=params if method == "GET" else None,
                json=params if method != "GET" else None,
                headers=headers,
            ) as response:
                data = cast(dict[str, Any], await response.json())

                if response.status != 200 or data.get("retCode") != 0:
                    error_msg = data.get("retMsg", f"HTTP {response.status}")
                    raise ValueError(f"Bybit API error: {error_msg}")

                self._health.last_message = time.time()
                return data

        except Exception as e:
            logger.error(f"Bybit API request failed: {e}")
            raise

    # === Public Market Data Methods ===

    async def get_ticker(self, symbol: str) -> dict[str, Any]:
        """Get 24hr ticker data for symbol.

        Args:
            symbol: Trading pair (e.g., "BTCUSDT")

        Returns:
            Ticker data with price, volume, etc.
        """
        return await self._make_request(
            "GET",
            "/v5/market/tickers",
            params={"category": "linear", "symbol": symbol},
        )

    async def get_orderbook(self, symbol: str, limit: int = 50) -> dict[str, Any]:
        """Get order book snapshot.

        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            limit: Number of bids/asks (1, 25, 50, 100, 200, 500)

        Returns:
            Order book data with bids, asks, and timestamp
        """
        return await self._make_request(
            "GET",
            "/v5/market/orderbook",
            params={"category": "linear", "symbol": symbol, "limit": limit},
        )

    # === Private Account Methods (Signed) ===

    async def get_fills(
        self,
        symbol: str | None = None,
        order_id: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Get execution/fill history.

        Args:
            symbol: Trading pair filter (optional)
            order_id: Order ID filter (optional)
            start_time: Start timestamp (ms) (optional)
            end_time: End timestamp (ms) (optional)
            limit: Number of records (max 100)

        Returns:
            Fill data with order_id, price, quantity, timestamp, fees
        """
        params: dict[str, Any] = {"category": "linear", "limit": limit}

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
            "/v5/execution/list",
            params=params,
            signed=True,
        )

    async def get_positions(
        self,
        symbol: str | None = None,
        settle_coin: str | None = None,
    ) -> dict[str, Any]:
        """Get position information.

        Args:
            symbol: Trading pair filter (optional)
            settle_coin: Settle coin filter (optional)

        Returns:
            Position data with size, entry price, leverage, etc.
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

    async def get_stop_orders(
        self,
        symbol: str | None = None,
        order_id: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Get stop loss / take profit orders.

        Args:
            symbol: Trading pair filter (optional)
            order_id: Order ID filter (optional)
            limit: Number of records (max 50)

        Returns:
            Stop order data with trigger price, type, etc.
        """
        params: dict[str, Any] = {
            "category": "linear",
            "limit": limit,
        }

        if symbol:
            params["symbol"] = symbol
        if order_id:
            params["orderId"] = order_id

        return await self._make_request(
            "GET",
            "/v5/order/list",
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
            side: Order side ("Buy" or "Sell")
            order_type: Order type ("Market", "Limit")
            quantity: Order quantity
            price: Order price (required for Limit orders)
            time_in_force: Time in force ("GTC", "IOC", "FOK")
            reduce_only: Whether order should only reduce position

        Returns:
            Order result with order_id, price, quantity, etc.
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

        result = await self._make_request(
            "POST",
            "/v5/order/create",
            params=params,
            signed=True,
        )

        # Extract and normalize result
        order_data = result.get("result", {})
        return {
            "order_id": order_data.get("orderId", ""),
            "symbol": symbol,
            "side": side,
            "order_type": order_type,
            "quantity": quantity,
            "price": price or 0.0,
            "status": order_data.get("orderStatus", "Created"),
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
            "category": "linear",
            "symbol": symbol,
            "orderId": order_id,
        }

        result = await self._make_request(
            "POST",
            "/v5/order/cancel",
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
        order_side = "Sell" if side.lower() == "sell" else "Buy"

        # Place market order with reduce_only=True
        result = await self.place_order(
            symbol=symbol,
            side=order_side,
            order_type="Market",
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
                    "args": [{"channel": "tickers", "symbol": s} for s in symbols],
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
                        # Handle bytes messages by decoding first
                        if isinstance(message, bytes):
                            message = message.decode("utf-8")
                        logger.warning(f"Invalid JSON: {message}")

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

        msg_type = data.get("topic", "")

        if "tickers" in msg_type:
            # Price update
            ticker_data = data.get("data", {})
            symbol = ticker_data.get("symbol", "")
            last_price = ticker_data.get("lastPrice", "0")

            if symbol and last_price:
                for callback in self._price_callbacks:
                    try:
                        callback(symbol, Decimal(last_price))
                    except Exception as e:
                        logger.error(f"Price callback error: {e}")

        elif data.get("op") == "pong":
            # Heartbeat response
            self._health.last_heartbeat = time.time()

        # Call general message callbacks
        for msg_callback in self._message_callbacks:
            try:
                msg_callback(data)
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
        expires = int(time.time() * 1000) + 10000  # 10 seconds from now
        signature = hmac.new(
            self.config.api_secret.encode(),
            f"GET/realtime{expires}".encode(),
            hashlib.sha256,
        ).hexdigest()

        auth_msg = {
            "op": "auth",
            "args": [self.config.api_key, expires, signature],
        }

        try:
            async with websockets.connect(self.config.private_ws_url) as ws:
                self._private_ws = ws

                # Authenticate
                await ws.send(json.dumps(auth_msg))

                # Subscribe to execution updates
                subscribe_msg = {
                    "op": "subscribe",
                    "args": [{"channel": "execution"}],
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
                        # Handle bytes messages by decoding first
                        if isinstance(message, bytes):
                            message = message.decode("utf-8")
                        logger.warning(f"Invalid JSON: {message}")

        except Exception as e:
            logger.error(f"Private WebSocket error: {e}")
        finally:
            self._private_ws = None

    async def _handle_private_message(self, data: dict[str, Any]) -> None:
        """Handle private WebSocket message (fills, positions)."""
        topic = data.get("topic", "")

        if topic == "execution":
            # Fill execution
            for callback in self._fill_callbacks:
                try:
                    callback(data.get("data", {}))
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
        if self._health.time_since_last_message > self.HEARTBEAT_INTERVAL * 2:
            return False

        return True

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
