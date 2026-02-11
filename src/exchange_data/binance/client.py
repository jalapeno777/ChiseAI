"""Binance API client for market data ingestion."""

import asyncio
import hashlib
import hmac
import time
from typing import Any, cast

import aiohttp

from exchange_data.binance.config import BinanceConfig


class BinanceClient:
    """Async HTTP client for Binance API.

    Handles authentication, rate limiting, and error handling
    for Binance market data endpoints.
    """

    def __init__(self, config: BinanceConfig | None = None) -> None:
        """Initialize client with configuration.

        Args:
            config: Binance configuration (uses defaults if None)
        """
        self.config = config or BinanceConfig()
        self._session: aiohttp.ClientSession | None = None
        self._rate_limit_remaining: int = 1200
        self._rate_limit_reset: float = 0.0

    async def __aenter__(self) -> "BinanceClient":
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
                headers={"Content-Type": "application/json"}
            )

    async def close(self) -> None:
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    def _generate_signature(self, query_string: str) -> str:
        """Generate HMAC signature for authenticated requests.

        Args:
            query_string: URL-encoded query string

        Returns:
            HMAC SHA256 signature hex digest
        """
        return hmac.new(
            self.config.api_secret.encode(),
            query_string.encode(),
            hashlib.sha256,
        ).hexdigest()

    def _check_rate_limit(self) -> bool:
        """Check if rate limit allows more requests.

        Returns:
            True if request can proceed, False if rate limited
        """
        now = time.time()
        if now >= self._rate_limit_reset:
            self._rate_limit_remaining = 1200
        return self._rate_limit_remaining > 0

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        signed: bool = False,
    ) -> dict[str, Any]:
        """Make HTTP request to Binance API.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint URL
            params: Query parameters
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

        if not self._check_rate_limit():
            wait_time = self._rate_limit_reset - time.time()
            if wait_time > 0:
                await asyncio.sleep(wait_time)

        params = params or {}
        params["timestamp"] = int(time.time() * 1000)

        if signed and self.config.api_key:
            query_string = "&".join(f"{k}={v}" for k, v in params.items())
            params["signature"] = self._generate_signature(query_string)

        headers = {}
        if self.config.api_key:
            headers["X-MBX-APIKEY"] = self.config.api_key

        async with self._session.request(
            method, endpoint, params=params, headers=headers
        ) as response:
            # Update rate limit tracking
            self._rate_limit_remaining = int(
                response.headers.get("X-MBX-USED-WEIGHT-1M", 0)
            )
            reset_time = response.headers.get("X-MBX-ORDER-COUNT-RESET-1M")
            if reset_time:
                self._rate_limit_reset = time.time() + int(reset_time)

            if response.status != 200:
                text = await response.text()
                raise ValueError(f"Binance API error {response.status}: {text}")

            return cast(dict[str, Any], await response.json())

    async def get_order_book(self, symbol: str, limit: int = 100) -> dict[str, Any]:
        """Fetch order book snapshot.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            limit: Number of bids/asks to fetch (max 1000)

        Returns:
            Order book data with bids, asks, and timestamp
        """
        return await self._make_request(
            "GET",
            self.config.orderbook_url,
            params={"symbol": symbol, "limit": limit},
        )

    async def get_open_interest(self, symbol: str) -> dict[str, Any]:
        """Fetch open interest data.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")

        Returns:
            Open interest data with value and timestamp
        """
        return await self._make_request(
            "GET",
            self.config.open_interest_url,
            params={"symbol": symbol},
        )

    async def get_book_ticker(self, symbol: str) -> dict[str, Any]:
        """Fetch best bid/ask price and quantity.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")

        Returns:
            Book ticker with bid/ask prices and quantities
        """
        return await self._make_request(
            "GET",
            self.config.ticker_url,
            params={"symbol": symbol},
        )
