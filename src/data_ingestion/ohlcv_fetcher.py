"""OHLCV data fetcher using ccxt library.

Provides flexible exchange API integration with retry logic,
circuit breaker pattern, and error handling for market gaps
and low liquidity periods.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import ccxt

from data_ingestion.timeframe_config import TIMEFRAME_CONFIG, Timeframe

logger = logging.getLogger(__name__)


@dataclass
class OHLCVData:
    """OHLCV candle data structure.

    Attributes:
        timestamp: Unix timestamp in milliseconds
        open_price: Opening price
        high_price: High price
        low_price: Low price
        close_price: Closing price
        volume: Trading volume
    """

    timestamp: int
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float

    @property
    def datetime_utc(self) -> datetime:
        """Return timestamp as UTC datetime."""
        return datetime.fromtimestamp(self.timestamp / 1000, tz=UTC)


class CircuitBreaker:
    """Circuit breaker pattern for API failure handling.

    Opens after threshold failures, preventing cascading failures.
    Automatically resets after cooldown period.
    Uses asyncio.Lock to ensure atomic state operations.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        cooldown_seconds: float = 60.0,
    ):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._failure_count = 0
        self._last_failure_time: float | None = None
        self._is_open = False
        self._lock = asyncio.Lock()

    async def record_success(self) -> None:
        """Record a successful API call (thread-safe)."""
        async with self._lock:
            self._failure_count = 0
            self._is_open = False

    async def record_failure(self) -> None:
        """Record a failed API call (thread-safe)."""
        import time

        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._failure_count >= self.failure_threshold:
                self._is_open = True
                logger.warning(
                    f"Circuit breaker opened after {self._failure_count} failures"
                )

    async def can_execute(self) -> bool:
        """Check if execution is allowed (thread-safe).

        Returns:
            True if circuit is closed or cooldown has elapsed
        """
        import time

        async with self._lock:
            if not self._is_open:
                return True

            if self._last_failure_time is None:
                return True

            elapsed = time.time() - self._last_failure_time
            if elapsed >= self.cooldown_seconds:
                logger.info("Circuit breaker cooldown elapsed, resetting")
                self._is_open = False
                self._failure_count = 0
                return True

            return False

    async def reset(self) -> None:
        """Reset the circuit breaker (thread-safe)."""
        async with self._lock:
            self._failure_count = 0
            self._is_open = False
            self._last_failure_time = None


class ExchangeAdapter(ABC):
    """Abstract base class for exchange adapters."""

    @abstractmethod
    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: Timeframe,
        since: int | None = None,
        limit: int | None = None,
    ) -> list[OHLCVData]:
        """Fetch OHLCV data from exchange.

        Args:
            symbol: Trading pair symbol (e.g., "BTC/USDT")
            timeframe: Timeframe enum
            since: Start timestamp in milliseconds (optional)
            limit: Maximum number of candles to fetch (optional)

        Returns:
            List of OHLCVData objects
        """
        pass

    @abstractmethod
    async def check_health(self) -> bool:
        """Check if exchange connection is healthy.

        Returns:
            True if connection is healthy
        """
        pass


class CCXTAdapter(ExchangeAdapter):
    """CCXT-based exchange adapter supporting multiple exchanges."""

    def __init__(
        self,
        exchange_id: str = "binance",
        api_key: str | None = None,
        api_secret: str | None = None,
        sandbox: bool = False,
    ):
        """Initialize CCXT adapter.

        Args:
            exchange_id: CCXT exchange identifier (e.g., "binance", "bybit")
            api_key: API key for authenticated requests (optional)
            api_secret: API secret for authenticated requests (optional)
            sandbox: Use sandbox/testnet environment
        """
        self.exchange_id = exchange_id
        exchange_class = getattr(ccxt, exchange_id)
        config: dict[str, Any] = {"enableRateLimit": True}

        if api_key:
            config["apiKey"] = api_key
        if api_secret:
            config["secret"] = api_secret
        if sandbox:
            config["sandbox"] = True

        self.exchange = exchange_class(config)
        self.circuit_breaker = CircuitBreaker()

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: Timeframe,
        since: int | None = None,
        limit: int | None = None,
    ) -> list[OHLCVData]:
        """Fetch OHLCV data using CCXT.

        Args:
            symbol: Trading pair symbol
            timeframe: Timeframe enum
            since: Start timestamp in milliseconds
            limit: Maximum candles to fetch

        Returns:
            List of OHLCVData objects

        Raises:
            CircuitBreakerOpen: If circuit breaker is open
            ExchangeError: If exchange API fails
        """
        if not await self.circuit_breaker.can_execute():
            raise CircuitBreakerOpen(f"Circuit breaker open for {self.exchange_id}")

        tf_config = TIMEFRAME_CONFIG[timeframe]
        ccxt_tf = tf_config.ccxt_code

        params: dict[str, Any] = {}
        if limit:
            params["limit"] = limit

        try:
            # Load markets if not already loaded
            if not self.exchange.markets:
                await asyncio.to_thread(self.exchange.load_markets)

            # Fetch OHLCV data
            candles = await asyncio.to_thread(
                self.exchange.fetch_ohlcv,
                symbol,
                ccxt_tf,
                since,
                limit,
                params,
            )

            await self.circuit_breaker.record_success()

            # Convert to OHLCVData objects
            result = []
            for candle in candles:
                if len(candle) >= 6:
                    result.append(
                        OHLCVData(
                            timestamp=int(candle[0]),
                            open_price=float(candle[1]),
                            high_price=float(candle[2]),
                            low_price=float(candle[3]),
                            close_price=float(candle[4]),
                            volume=float(candle[5]),
                        )
                    )

            return result

        except ccxt.NetworkError as e:
            await self.circuit_breaker.record_failure()
            logger.warning(f"Network error fetching OHLCV from {self.exchange_id}: {e}")
            raise ExchangeError(f"Network error: {e}") from e

        except ccxt.ExchangeError as e:
            await self.circuit_breaker.record_failure()
            logger.error(f"Exchange error from {self.exchange_id}: {e}")
            raise ExchangeError(f"Exchange error: {e}") from e

        except Exception as e:
            await self.circuit_breaker.record_failure()
            logger.exception(f"Unexpected error fetching OHLCV: {e}")
            raise ExchangeError(f"Unexpected error: {e}") from e

    async def check_health(self) -> bool:
        """Check exchange health by fetching server time."""
        try:
            await asyncio.to_thread(self.exchange.fetch_time)
            return True
        except Exception as e:
            logger.warning(f"Health check failed for {self.exchange_id}: {e}")
            return False


class CircuitBreakerOpen(Exception):
    """Raised when circuit breaker is open."""

    pass


class ExchangeError(Exception):
    """Raised when exchange API fails."""

    pass


class OHLCVFetcher:
    """Main OHLCV fetcher with retry logic and multi-exchange support."""

    def __init__(
        self,
        exchange_adapter: ExchangeAdapter | None = None,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
    ):
        """Initialize OHLCV fetcher.

        Args:
            exchange_adapter: Exchange adapter to use (defaults to CCXTAdapter)
            max_retries: Maximum retry attempts for failed requests
            base_delay: Initial retry delay in seconds
            max_delay: Maximum retry delay in seconds
        """
        self.exchange_adapter = exchange_adapter or CCXTAdapter()
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay

    async def fetch(
        self,
        symbol: str,
        timeframe: Timeframe,
        since: int | None = None,
        limit: int | None = None,
    ) -> list[OHLCVData]:
        """Fetch OHLCV data with exponential backoff retry.

        Args:
            symbol: Trading pair symbol
            timeframe: Timeframe enum
            since: Start timestamp in milliseconds
            limit: Maximum candles to fetch

        Returns:
            List of OHLCVData objects

        Raises:
            ExchangeError: If all retry attempts fail
        """
        delay = self.base_delay

        for attempt in range(self.max_retries):
            try:
                data = await self.exchange_adapter.fetch_ohlcv(
                    symbol, timeframe, since, limit
                )

                # Check for low liquidity (very low volume)
                if data and all(d.volume == 0 for d in data):
                    logger.warning(
                        f"Zero volume detected for {symbol} {timeframe.value}, "
                        "possible low liquidity period"
                    )

                return data

            except CircuitBreakerOpen:
                logger.warning(f"Circuit breaker open, attempt {attempt + 1}")
                if attempt == self.max_retries - 1:
                    raise

            except ExchangeError as e:
                logger.warning(
                    f"Fetch attempt {attempt + 1}/{self.max_retries} failed: {e}"
                )
                if attempt == self.max_retries - 1:
                    raise

            # Exponential backoff with jitter
            await asyncio.sleep(delay)
            delay = min(delay * 2, self.max_delay)

        # Should not reach here, but return empty list as fallback
        return []

    async def fetch_multiple_timeframes(
        self,
        symbol: str,
        timeframes: list[Timeframe],
        since: int | None = None,
        limit: int | None = None,
    ) -> dict[Timeframe, list[OHLCVData]]:
        """Fetch OHLCV data for multiple timeframes concurrently.

        Args:
            symbol: Trading pair symbol
            timeframes: List of Timeframe enums
            since: Start timestamp in milliseconds
            limit: Maximum candles per timeframe

        Returns:
            Dictionary mapping timeframe to list of OHLCVData
        """
        tasks = {tf: self.fetch(symbol, tf, since, limit) for tf in timeframes}

        results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        output: dict[Timeframe, list[OHLCVData]] = {}
        for tf, result in zip(tasks.keys(), results, strict=False):
            if isinstance(result, Exception):
                logger.error(f"Failed to fetch {tf.value}: {result}")
                output[tf] = []
            else:
                # Type narrowing: result is list[OHLCVData] here
                output[tf] = result  # type: ignore[assignment]

        return output
