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
import contextlib
import hashlib
import hmac
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from typing import Any, cast

import aiohttp
import websockets
from websockets.asyncio.client import ClientConnection as WebSocketClientProtocol
from websockets.exceptions import ConnectionClosed, InvalidStatus

from data.exchange.bybit_safety import SecurityException, validate_endpoint_url
from data.exchange.bybit_websocket import (
    BybitWebSocketManager,
    CircuitBreakerConfig,
)
from execution.order_idempotency import (
    DuplicateOrderException,
    IdempotencyStore,
    generate_client_order_id,
    get_default_store,
)

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
        - Live mode (both False): RAISES SecurityException (production blocked)

        Raises:
            SecurityException: If demo=False and testnet=False (production mode)
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
        else:
            # Production mode is NOT allowed - raise SecurityException
            raise SecurityException(
                "PRODUCTION ENDPOINT DETECTED: Production mode is not allowed. "
                "Only demo or testnet endpoints are permitted. "
                "Set demo=True or testnet=True to use safe endpoints.",
                endpoint=self.base_url,
                operation="BybitConfig.__post_init__",
            )

        # Validate that all endpoints are safe (demo/testnet only)
        validate_endpoint_url(self.base_url)
        validate_endpoint_url(self.private_ws_url)
        # Public WS can be mainnet for market data, but still validate
        if "private" in self.ws_url:
            validate_endpoint_url(self.ws_url)

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

    def __init__(
        self,
        config: BybitConfig | None = None,
        idempotency_store: IdempotencyStore | None = None,
    ) -> None:
        """Initialize Bybit connector.

        Args:
            config: Bybit configuration (uses defaults if None)
            idempotency_store: Idempotency store for order deduplication
                (uses default store if None)
        """
        self.config = config or BybitConfig()
        self._idempotency_store = idempotency_store or get_default_store()
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

        # WebSocket circuit breaker manager (ST-LAUNCH-002)
        self._ws_manager: BybitWebSocketManager | None = None
        self._circuit_breaker_config = CircuitBreakerConfig(
            failure_threshold=5,
            timeout_seconds=60.0,
            failure_window_seconds=60.0,
            half_open_max_calls=3,
        )

        # Time synchronization for API authentication.
        self._time_offset_ms: int = 0
        self._last_time_sync: float = 0.0

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
            with contextlib.suppress(asyncio.CancelledError):
                await self._heartbeat_task

        if self._ws_task and not self._ws_task.done():
            self._ws_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._ws_task

        # Stop WebSocket manager (ST-LAUNCH-002)
        if self._ws_manager is not None:
            await self._ws_manager.stop()
            self._ws_manager = None

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

    async def _sync_server_time(self) -> None:
        """Synchronize local time with Bybit server time.

        Fetches server time from /v5/market/time and calculates
        the offset between local and server time for authentication.
        """
        try:
            response = await self._make_request("GET", "/v5/market/time")
            result = response.get("result", {})
            # Try nanoseconds first, fallback to seconds
            server_time_ns = result.get("timeNano", 0)
            if server_time_ns:
                server_time_ms = server_time_ns // 1000000
            else:
                server_time_ms = result.get("timeSecond", 0) * 1000

            local_time_ms = int(time.time() * 1000)
            self._time_offset_ms = server_time_ms - local_time_ms
            self._last_time_sync = time.time()

            logger.debug(f"Time sync complete. Offset: {self._time_offset_ms}ms")
        except Exception as e:
            logger.warning(f"Time sync failed: {e}. Using local time.")
            # Graceful fallback: continue with offset=0

    def _get_timestamp(self) -> int:
        """Get current timestamp adjusted for server time offset.

        Returns:
            Timestamp in milliseconds adjusted for server time offset.
        """
        return int(time.time() * 1000) + self._time_offset_ms

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

    async def _sync_server_time(self) -> None:
        """Synchronize local time with Bybit server time.

        Fetches the server time from Bybit API and calculates the offset
        between local time and server time. This offset is used to adjust
        timestamps in authenticated requests to prevent retCode 10003 errors
        caused by clock skew.
        """
        if self._session is None:
            return

        try:
            url = f"{self.config.base_url}/v5/market/time"
            async with self._session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("retCode") == 0:
                        result = data.get("result", {})
                        # Try timeNano first (nanoseconds), fall back to timeSecond
                        server_time_nano = result.get("timeNano", 0)
                        if server_time_nano:
                            server_time_ms = int(server_time_nano) // 1_000_000
                        else:
                            server_time_ms = int(result.get("timeSecond", 0)) * 1000

                        local_time_ms = int(time.time() * 1000)
                        self._time_offset_ms = server_time_ms - local_time_ms
                        self._last_time_sync = time.time()

                        logger.debug(
                            f"Time sync complete: offset={self._time_offset_ms}ms, "
                            f"server_time={server_time_ms}, local_time={local_time_ms}"
                        )
        except Exception as e:
            logger.warning(f"Failed to sync server time: {e}")
            # Continue with local time (offset remains 0)

    def _get_timestamp(self) -> str:
        """Get timestamp adjusted for server time offset.

        Returns:
            Timestamp string in milliseconds adjusted for server time
        """
        local_time_ms = int(time.time() * 1000)
        adjusted_time_ms = local_time_ms + self._time_offset_ms
        return str(adjusted_time_ms)

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
            if self._last_time_sync == 0 or (time.time() - self._last_time_sync) > 30:
                await self._sync_server_time()

            timestamp = self._get_timestamp()
            headers["X-BAPI-TIMESTAMP"] = timestamp
            headers["X-BAPI-RECV-WINDOW"] = str(self.config.recv_window)

            if method == "GET" and params:
                # Build query string in the SAME order as params dict
                # Bybit requires exact ordering - params must match the URL order
                # Python 3.7+ preserves dict insertion order
                payload = "&".join(f"{k}={v}" for k, v in params.items())
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

    async def get_instrument_info(self, symbol: str) -> dict[str, Any]:
        """Get instrument metadata (lot size, min qty, etc.) for a symbol."""
        result = await self._make_request(
            "GET",
            "/v5/market/instruments-info",
            params={"category": "linear", "symbol": symbol},
        )
        instruments = result.get("result", {}).get("list", [])
        if not instruments:
            return {}
        return instruments[0]

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

    async def get_wallet_balance(
        self,
        account_type: str = "UNIFIED",
        coin: str | None = None,
    ) -> dict[str, Any]:
        """Get wallet balance information.

        Calls Bybit V5 /v5/account/wallet-balance endpoint to retrieve
        account balance, equity, and unrealized PnL.

        Args:
            account_type: Account type ("UNIFIED", "CONTRACT", "SPOT")
            coin: Specific coin to query (optional, queries all if None)

        Returns:
            Wallet balance data with:
            - total_equity: Total account equity in USD
            - available_balance: Available balance for trading
            - unrealized_pnl: Unrealized profit/loss
            - coin_balances: List of per-coin balances
        """
        params: dict[str, Any] = {"accountType": account_type}

        if coin:
            params["coin"] = coin

        result = await self._make_request(
            "GET",
            "/v5/account/wallet-balance",
            params=params,
            signed=True,
        )

        # Extract and normalize balance data
        result_data = result.get("result", {})
        list_data = result_data.get("list", [])

        if not list_data:
            return {
                "total_equity": 0.0,
                "available_balance": 0.0,
                "unrealized_pnl": 0.0,
                "coin_balances": [],
                "raw_response": result,
            }

        # Get the first account (usually the primary account)
        account = list_data[0]

        # Parse coin balances
        coin_balances = []
        for coin_data in account.get("coin", []):

            def _parse_float(value: str | None) -> float:
                """Parse float, handling empty strings and None."""
                if not value:
                    return 0.0
                try:
                    return float(value)
                except (ValueError, TypeError):
                    return 0.0

            coin_balances.append(
                {
                    "coin": coin_data.get("coin", ""),
                    "equity": _parse_float(coin_data.get("equity")),
                    "available": _parse_float(coin_data.get("availableToWithdraw")),
                    "unrealized_pnl": _parse_float(coin_data.get("unrealisedPnl")),
                    "wallet_balance": _parse_float(coin_data.get("walletBalance")),
                }
            )

        return {
            "total_equity": float(account.get("totalEquity", "0")),
            "available_balance": float(account.get("totalAvailableBalance", "0")),
            "unrealized_pnl": float(account.get("totalPerpUPL", "0")),
            "coin_balances": coin_balances,
            "raw_response": result,
        }

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
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        """Place a new order with idempotency support.

        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            side: Order side ("Buy" or "Sell")
            order_type: Order type ("Market", "Limit")
            quantity: Order quantity
            price: Order price (required for Limit orders)
            time_in_force: Time in force ("GTC", "IOC", "FOK")
            reduce_only: Whether order should only reduce position
            client_order_id: Optional client order ID (auto-generated if None)

        Returns:
            Order result with order_id, client_order_id, price, quantity, etc.

        Raises:
            DuplicateOrderException: If the same order has already been submitted
        """
        # Generate or use provided client order ID
        if client_order_id is None:
            client_order_id = generate_client_order_id(symbol)

        # Check for duplicate orders
        is_duplicate = await self._idempotency_store.check_duplicate(
            symbol, client_order_id
        )
        if is_duplicate:
            raise DuplicateOrderException(client_order_id, symbol)

        # Quantize quantity based on symbol lot size constraints when available.
        qty_decimal = Decimal(str(quantity))
        try:
            instrument = await self.get_instrument_info(symbol)
            lot_filter = instrument.get("lotSizeFilter", {})
            qty_step = Decimal(str(lot_filter.get("qtyStep", "0")))
            min_qty = Decimal(str(lot_filter.get("minOrderQty", "0")))
            if qty_step > 0:
                qty_decimal = (qty_decimal / qty_step).to_integral_value(
                    rounding=ROUND_DOWN
                ) * qty_step
            if min_qty > 0 and qty_decimal < min_qty:
                qty_decimal = min_qty
        except Exception as e:
            logger.warning(
                "Failed to load instrument lot size for %s, using fallback rounding: %s",
                symbol,
                e,
            )
            qty_decimal = Decimal(str(round(float(quantity), 3)))

        qty_rounded = float(qty_decimal)

        params: dict[str, Any] = {
            "category": "linear",
            "symbol": symbol,
            "side": side.capitalize(),
            "orderType": order_type.capitalize(),
            "qty": str(qty_rounded),
            "timeInForce": time_in_force,
            "reduceOnly": reduce_only,
            "orderLinkId": client_order_id,  # Bybit's clientOrderId field
        }

        if order_type.lower() == "limit" and price is not None:
            params["price"] = str(price)

        try:
            result = await self._make_request(
                "POST",
                "/v5/order/create",
                params=params,
                signed=True,
            )

            # Mark order as submitted in idempotency store
            await self._idempotency_store.mark_submitted(symbol, client_order_id)

            # Extract and normalize result
            order_data = result.get("result", {})
            return {
                "order_id": order_data.get("orderId", ""),
                "client_order_id": client_order_id,
                "symbol": symbol,
                "side": side,
                "order_type": order_type,
                "quantity": quantity,
                "price": price or 0.0,
                "status": order_data.get("orderStatus", "Created"),
                "raw_response": result,
            }
        except Exception:
            # On failure, remove from idempotency store to allow retry
            await self._idempotency_store.remove(symbol, client_order_id)
            raise

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

    async def set_trading_stop(
        self,
        symbol: str,
        take_profit: float | None = None,
        stop_loss: float | None = None,
        position_idx: int = 0,
    ) -> dict[str, Any]:
        """Attach/replace TP-SL settings for a linear position.

        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            take_profit: TP price (optional)
            stop_loss: SL price (optional)
            position_idx: Position index (0 one-way mode)

        Returns:
            Response summary from Bybit.
        """
        params: dict[str, Any] = {
            "category": "linear",
            "symbol": symbol,
            "positionIdx": position_idx,
            "tpslMode": "Full",
        }

        if take_profit is not None and take_profit > 0:
            params["takeProfit"] = str(take_profit)
            params["tpOrderType"] = "Market"
        if stop_loss is not None and stop_loss > 0:
            params["stopLoss"] = str(stop_loss)
            params["slOrderType"] = "Market"

        if "takeProfit" not in params and "stopLoss" not in params:
            raise ValueError("set_trading_stop requires take_profit and/or stop_loss")

        result = await self._make_request(
            "POST",
            "/v5/position/trading-stop",
            params=params,
            signed=True,
        )

        return {
            "symbol": symbol,
            "take_profit": take_profit,
            "stop_loss": stop_loss,
            "position_idx": position_idx,
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

    async def start_websocket(
        self,
        symbols: list[str] | None = None,
        use_circuit_breaker: bool = True,
    ) -> None:
        """Start WebSocket connection for real-time data.

        ST-LAUNCH-002: WebSocket Circuit Breaker Integration

        Args:
            symbols: List of symbols to subscribe to (e.g., ["BTCUSDT", "ETHUSDT"])
            use_circuit_breaker: Whether to enable circuit breaker (default: True)
        """
        self._running = True
        symbols = symbols or ["BTCUSDT"]

        if use_circuit_breaker:
            # Use new circuit breaker WebSocket manager
            self._ws_manager = BybitWebSocketManager(
                ws_url=self.config.ws_url,
                connector=self,
                circuit_breaker_config=self._circuit_breaker_config,
            )

            # Transfer callbacks to manager
            for callback in self._price_callbacks:
                self._ws_manager.register_price_callback(callback)
            for callback in self._message_callbacks:  # type: ignore[assignment]
                self._ws_manager.register_message_callback(callback)

            await self._ws_manager.start(symbols)
            logger.info(f"WebSocket started with circuit breaker: {symbols}")
        else:
            # Legacy mode without circuit breaker
            self._ws_task = asyncio.create_task(self._websocket_loop(symbols))
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

    # === Circuit Breaker Methods (ST-LAUNCH-002) ===

    def get_circuit_breaker_state(self) -> dict[str, Any] | None:
        """Get current circuit breaker state.

        Returns:
            Circuit breaker state dictionary or None if not initialized
        """
        if self._ws_manager is None:
            return None
        return cast(dict[str, Any], self._ws_manager.get_state())

    def force_circuit_open(self, reason: str = "manual") -> None:
        """Manually force WebSocket circuit breaker to open.

        Args:
            reason: Reason for forcing open
        """
        if self._ws_manager is not None:
            self._ws_manager.force_open(reason)
            logger.warning(f"WebSocket circuit breaker manually opened: {reason}")

    def force_circuit_closed(self, reason: str = "manual") -> None:
        """Manually force WebSocket circuit breaker to closed.

        Args:
            reason: Reason for forcing closed
        """
        if self._ws_manager is not None:
            self._ws_manager.force_close(reason)
            logger.info(f"WebSocket circuit breaker manually closed: {reason}")

    def reset_circuit_breaker(self) -> None:
        """Reset WebSocket circuit breaker to initial state."""
        if self._ws_manager is not None:
            self._ws_manager.reset()
            logger.info("WebSocket circuit breaker reset")

    def is_websocket_healthy(self) -> bool:
        """Check if WebSocket connection is healthy (circuit breaker aware).

        Returns:
            True if WebSocket is connected and circuit is closed or half-open
        """
        if self._ws_manager is None:
            return False
        return cast(bool, self._ws_manager.is_healthy())
