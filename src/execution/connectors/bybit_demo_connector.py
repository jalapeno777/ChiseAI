"""Bybit Demo Connector for authenticated demo trading.

This module provides a bridge between the paper trading orchestrator and
the actual Bybit demo API. It wraps BybitConnector to provide the same
interface as OrderSimulator while making real authenticated API calls to
Bybit demo endpoints.

For REMEDIATION-001: G8 Bybit Demo Provenance

Key Features:
- Authenticated execution to Bybit demo API
- Provenance logging for audit trail
- Mock/sim leakage prevention
- Compatible with OrderSimulator interface
- Comprehensive error handling with typed exceptions
- Retry logic with exponential backoff and jitter
- Full order lifecycle provenance tracking
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import random
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from data.exchange.bybit_connector import BybitConnector
    from execution.paper.models import PaperOrder
    from execution.paper.order_simulator import MarketDataProvider
    from execution.persistence.outcome_persistence import OutcomePersistence

from execution.paper.models import OrderState, PaperFill, PaperOrder
from execution.persistence.outcome_persistence import OutcomePersistence

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Exception Hierarchy
# ---------------------------------------------------------------------------


class BybitAPIError(Exception):
    """Base exception for all Bybit demo connector errors."""

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        status_code: int | None = None,
        operation: str | None = None,
        retryable: bool = False,
    ) -> None:
        self.error_code = error_code
        self.status_code = status_code
        self.operation = operation
        self.retryable = retryable
        super().__init__(message)


class BybitRateLimitError(BybitAPIError):
    """Raised when Bybit API rate limit is exceeded."""

    def __init__(
        self,
        message: str = "Bybit API rate limit exceeded",
        retry_after: float | None = None,
        **kwargs: Any,
    ) -> None:
        self.retry_after = retry_after
        super().__init__(
            message=message,
            error_code=kwargs.get("error_code", "429"),
            status_code=429,
            operation=kwargs.get("operation"),
            retryable=True,
        )


class BybitAuthenticationError(BybitAPIError):
    """Raised when API authentication fails."""

    def __init__(
        self,
        message: str = "Bybit API authentication failed",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            message=message,
            error_code=kwargs.get("error_code", "auth_failed"),
            status_code=kwargs.get("status_code", 401),
            operation=kwargs.get("operation"),
            retryable=False,
        )


class BybitNetworkError(BybitAPIError):
    """Raised on network connectivity issues."""

    def __init__(
        self,
        message: str = "Network error connecting to Bybit API",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            message=message,
            error_code=kwargs.get("error_code", "network_error"),
            operation=kwargs.get("operation"),
            retryable=True,
        )


class BybitOrderError(BybitAPIError):
    """Raised on order-specific failures (insufficient margin, invalid params, etc.)."""

    def __init__(
        self,
        message: str,
        order_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        self.order_id = order_id
        super().__init__(
            message=message,
            error_code=kwargs.get("error_code"),
            status_code=kwargs.get("status_code"),
            operation=kwargs.get("operation"),
            retryable=kwargs.get("retryable", False),
        )


class BybitConnectorError(BybitAPIError):
    """Raised when connector session is unavailable or misconfigured."""

    def __init__(
        self,
        message: str = "Bybit connector is unavailable",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            message=message,
            error_code=kwargs.get("error_code", "connector_error"),
            operation=kwargs.get("operation"),
            retryable=kwargs.get("retryable", True),
        )


# Mapping from Bybit retCode to our typed exceptions.
_BYBIT_ERROR_MAP: dict[str, type[BybitAPIError]] = {
    "10001": BybitRateLimitError,  # Rate limit
    "10002": BybitRateLimitError,  # Rate limit (IP)
    "10003": BybitRateLimitError,  # Rate limit (UID)
    "10004": BybitRateLimitError,  # Rate limit (order)
    "10006": BybitAuthenticationError,  # Invalid API key
    "10007": BybitAuthenticationError,  # Invalid sign
    "10008": BybitAuthenticationError,  # IP not whitelisted
    "10009": BybitAuthenticationError,  # IP restricted
    "10010": BybitAuthenticationError,  # Permission denied
    "10013": BybitAuthenticationError,  # Invalid timestamp
    "10014": BybitAuthenticationError,  # Invalid sign (repeated)
    "110001": BybitOrderError,  # Order does not exist
    "110004": BybitOrderError,  # Duplicate order ID
    "110006": BybitOrderError,  # Insufficient balance
    "110007": BybitOrderError,  # Position not found
    "110008": BybitOrderError,  # Reduce-only but no position
    "110009": BybitOrderError,  # Position crossed auto-deleveraging
    "110010": BybitOrderError,  # TP/SL order error
    "110011": BybitOrderError,  # Conditional order error
    "110012": BybitOrderError,  # Invalid order qty
    "110016": BybitOrderError,  # Order price out of range
    "110018": BybitOrderError,  # Leverage not valid
    "110021": BybitOrderError,  # Qty less than min
    "110022": BybitOrderError,  # Risk limit exceeded
    "13001": BybitOrderError,  # Order already triggered
    "13002": BybitOrderError,  # Order already cancelled
    "13003": BybitOrderError,  # Order already filled
    "13004": BybitOrderError,  # Order not found
    "13005": BybitOrderError,  # Modify order error
    "13006": BybitOrderError,  # Cancel order error
    "13010": BybitOrderError,  # TP/SL not valid
    "13011": BybitOrderError,  # TP/SL price error
    "13013": BybitOrderError,  # Order status not valid
    "13014": BybitOrderError,  # Market order not supported
    "13015": BybitOrderError,  # Quantity exceeds limit
    "170005": BybitOrderError,  # Max position limit exceeded
}


def classify_bybit_error(
    ret_code: str | int | None,
    ret_msg: str = "",
    operation: str | None = None,
) -> BybitAPIError:
    """Classify a Bybit API error response into a typed exception.

    Args:
        ret_code: The Bybit ``retCode`` field.
        ret_msg: The Bybit ``retMsg`` field.
        operation: The operation that triggered the error.

    Returns:
        A typed :class:`BybitAPIError` subclass instance.
    """
    code_str = str(ret_code) if ret_code is not None else "unknown"

    if code_str == "0":
        return BybitAPIError(
            "No error (retCode=0)", error_code="0", operation=operation
        )

    exc_cls = _BYBIT_ERROR_MAP.get(code_str)
    if exc_cls is not None:
        return exc_cls(
            message=ret_msg or f"Bybit API error (code={code_str})",
            error_code=code_str,
            operation=operation,
        )

    # Default: unknown API error (retryable for 5xx-like codes).
    retryable = code_str.startswith("5") or code_str.startswith("3")
    return BybitAPIError(
        message=ret_msg or f"Bybit API error (code={code_str})",
        error_code=code_str,
        operation=operation,
        retryable=retryable,
    )


# ---------------------------------------------------------------------------
# Retry Configuration & Logic
# ---------------------------------------------------------------------------


@dataclass
class RetryConfig:
    """Configuration for exponential-backoff retry with jitter.

    Attributes:
        max_retries: Maximum number of retry attempts (0 = no retry).
        base_delay: Base delay in seconds before first retry.
        max_delay: Maximum delay cap in seconds.
        exponential_base: Multiplier for exponential growth.
        jitter_range: Tuple (low, high) for uniform jitter factor applied
            as a fraction of the computed delay.
    """

    max_retries: int = 3
    base_delay: float = 0.5
    max_delay: float = 30.0
    exponential_base: float = 2.0
    jitter_range: tuple[float, float] = (0.8, 1.2)

    def get_delay(self, attempt: int) -> float:
        """Compute delay for a given retry *attempt* (1-based).

        Uses exponential backoff with jitter.

        Args:
            attempt: Current attempt number (starting at 1).

        Returns:
            Delay in seconds, capped at ``max_delay``.
        """
        delay = self.base_delay * (self.exponential_base ** (attempt - 1))
        delay = min(delay, self.max_delay)
        # Apply uniform jitter.
        jitter_lo, jitter_hi = self.jitter_range
        jitter_factor = random.uniform(jitter_lo, jitter_hi)
        delay *= jitter_factor
        return delay


class ExponentialBackoffRetry:
    """Generic async retry executor with exponential backoff and jitter.

    Args:
        config: Retry configuration.
        retryable_predicate: Optional callable to decide if an exception
            is retryable. Receives the exception, returns bool.
    """

    def __init__(
        self,
        config: RetryConfig | None = None,
        retryable_predicate: Callable[[Exception], bool] | None = None,
    ) -> None:
        self.config = config or RetryConfig()
        self.retryable_predicate = retryable_predicate

    def _is_retryable(self, exc: Exception) -> bool:
        """Determine whether *exc* is retryable."""
        if self.retryable_predicate is not None:
            return self.retryable_predicate(exc)
        if isinstance(exc, BybitAPIError):
            return exc.retryable
        # Default: retry on network / timeout errors.
        return isinstance(exc, (OSError, asyncio.TimeoutError, ConnectionError))

    async def execute(
        self,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Execute *func* with retries.

        Args:
            func: Awaitable callable to execute.
            *args: Positional arguments forwarded to *func*.
            **kwargs: Keyword arguments forwarded to *func*.

        Returns:
            The return value of *func*.

        Raises:
            The last exception if all retries are exhausted.
        """
        last_exc: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            try:
                return await func(*args, **kwargs)  # type: ignore[misc]
            except Exception as exc:
                last_exc = exc
                if not self._is_retryable(exc) or attempt == self.config.max_retries:
                    raise
                delay = self.config.get_delay(attempt)
                logger.warning(
                    "Retry attempt %d/%d for %s: %s (waiting %.2fs)",
                    attempt,
                    self.config.max_retries,
                    getattr(func, "__name__", str(func)),
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
        # Should be unreachable, but guard against None.
        if last_exc is not None:
            raise last_exc  # type: ignore[misc]
        raise RuntimeError("Unexpected retry loop exit with no exception")


# ---------------------------------------------------------------------------
# Provenance Tracking
# ---------------------------------------------------------------------------


class ProvenanceEventType(str, Enum):
    """Types of provenance events for order lifecycle."""

    CONNECTOR_INIT = "connector_init"
    ORDER_PLACED = "order_placed"
    ORDER_FILLED = "order_filled"
    ORDER_PARTIAL = "order_partial"
    ORDER_REJECTED = "order_rejected"
    ORDER_CANCELLED = "order_cancelled"
    ORDER_CANCEL_FAILED = "order_cancel_failed"
    TP_SL_ATTACHED = "tp_sl_attached"
    TP_SL_ATTACH_FAILED = "tp_sl_attach_failed"
    PRICE_FETCHED = "price_fetched"
    BALANCE_FETCHED = "balance_fetched"
    HEALTH_CHECK = "health_check"
    ERROR = "error"


@dataclass
class ProvenanceEvent:
    """A single provenance event in the order lifecycle.

    Attributes:
        event_type: The type of event.
        timestamp: ISO-8601 timestamp.
        order_id: Associated order ID (if applicable).
        symbol: Trading symbol (if applicable).
        details: Arbitrary event details.
    """

    event_type: ProvenanceEventType
    timestamp: str
    order_id: str | None = None
    symbol: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


class ProvenanceTracker:
    """Tracks full order lifecycle provenance events.

    Each event is stored with a timestamp and optional metadata,
    providing a complete audit trail of all connector operations.
    """

    def __init__(self, max_events: int = 10_000) -> None:
        self._events: list[ProvenanceEvent] = []
        self._max_events = max_events

    def record(
        self,
        event_type: ProvenanceEventType,
        order_id: str | None = None,
        symbol: str | None = None,
        **details: Any,
    ) -> ProvenanceEvent:
        """Record a provenance event.

        Args:
            event_type: Type of event.
            order_id: Associated order ID.
            symbol: Trading symbol.
            **details: Arbitrary event details.

        Returns:
            The recorded event.
        """
        event = ProvenanceEvent(
            event_type=event_type,
            timestamp=datetime.now(UTC).isoformat(),
            order_id=order_id,
            symbol=symbol,
            details=details,
        )
        self._events.append(event)
        # Enforce size limit.
        if len(self._events) > self._max_events:
            self._events = self._events[-self._max_events :]
        return event

    def get_events(
        self,
        order_id: str | None = None,
        event_type: ProvenanceEventType | None = None,
        limit: int | None = None,
    ) -> list[ProvenanceEvent]:
        """Query provenance events with optional filters.

        Args:
            order_id: Filter by order ID.
            event_type: Filter by event type.
            limit: Maximum events to return (most recent first).

        Returns:
            List of matching provenance events.
        """
        events = self._events
        if order_id is not None:
            events = [e for e in events if e.order_id == order_id]
        if event_type is not None:
            events = [e for e in events if e.event_type == event_type]
        # Return most recent first.
        events = list(reversed(events))
        if limit is not None:
            events = events[:limit]
        return events

    def get_order_history(self, order_id: str) -> list[ProvenanceEvent]:
        """Get complete provenance history for an order.

        Args:
            order_id: The order ID.

        Returns:
            List of events for this order in chronological order.
        """
        return [e for e in self._events if e.order_id == order_id]

    @property
    def event_count(self) -> int:
        """Total number of recorded events."""
        return len(self._events)

    def clear(self) -> None:
        """Clear all recorded events."""
        self._events.clear()


# ---------------------------------------------------------------------------
# Original DemoProvenance (kept for backward compatibility)
# ---------------------------------------------------------------------------


def hash_api_key(api_key: str | None) -> str:
    """Hash an API key for secure logging.

    Returns the first 4 characters followed by a SHA-256 hash of the
    remainder, providing identification while protecting the full key.

    Args:
        api_key: The API key to hash, or None.

    Returns:
        A string like ``"abcd:a1b2c3..."`` or ``"****"`` if key is None/empty.
    """
    if not api_key or len(api_key) < 4:
        return "****"
    prefix = api_key[:4]
    hashed = hashlib.sha256(api_key[4:].encode()).hexdigest()[:12]
    return f"{prefix}:{hashed}"


@dataclass
class DemoProvenance:
    """Provenance information for demo trading.

    Attributes:
        is_demo: Whether demo mode is active
        endpoint: The Bybit demo endpoint used
        api_key_prefix: First 4 chars + hash of API key for identification
        timestamp: When the provenance was recorded
    """

    is_demo: bool
    endpoint: str
    api_key_prefix: str
    timestamp: str


# ---------------------------------------------------------------------------
# Refactored BybitDemoConnector
# ---------------------------------------------------------------------------


class BybitDemoConnector:
    """Bybit demo connector for authenticated demo trading.

    This class wraps BybitConnector to provide the same interface as
    OrderSimulator while making real authenticated API calls to Bybit
    demo endpoints. It includes provenance logging to prove that trades
    are executed against the actual Bybit demo API.

    Attributes:
        connector: The underlying BybitConnector instance
        market_data: Market data provider for price lookups
        provenance: Provenance information proving demo execution
        provenance_tracker: Full lifecycle provenance tracker
        _orders: Cache of orders placed via this connector
        _redis: Optional Redis client for deduplication
    """

    # Fill polling configuration
    FILL_POLL_INTERVAL_MS = 100
    DEFAULT_POLL_TIMEOUT_MS = 5000
    DEDUP_TTL_HOURS = 24

    def __init__(
        self,
        connector: BybitConnector,
        market_data: MarketDataProvider | None = None,
        retry_config: RetryConfig | None = None,
        redis_client: Any | None = None,
    ) -> None:
        """Initialize the Bybit demo connector.

        Args:
            connector: Configured BybitConnector instance (must be in demo mode)
            market_data: Optional market data provider for price lookups
            retry_config: Optional retry configuration (default: 3 retries)
            redis_client: Optional Redis client for fill deduplication

        Raises:
            ValueError: If connector is not configured for demo mode
            SecurityException: If connector is using production endpoints
        """
        from data.exchange.bybit_safety import SecurityException, validate_endpoint_url

        self.connector = connector
        self.market_data = market_data
        self._orders: dict[str, PaperOrder] = {}
        self._retry_config = retry_config or RetryConfig()
        self._retry = ExponentialBackoffRetry(config=self._retry_config)
        self.provenance_tracker = ProvenanceTracker()
        self._redis = redis_client
        self._outcome_persistence: OutcomePersistence | None = None

        # Validate demo mode
        config = connector.config

        # Check that demo mode is enabled
        if not config.demo:
            raise ValueError(
                "BybitDemoConnector requires demo mode. Ensure BybitConfig.demo=True"
            )

        # Validate endpoints are demo endpoints
        try:
            validate_endpoint_url(config.base_url)
            validate_endpoint_url(config.private_ws_url)
        except SecurityException as e:
            raise SecurityException(
                f"BybitDemoConnector requires demo endpoints. {e}",
                endpoint=config.base_url,
                operation="BybitDemoConnector.__init__",
            ) from e

        # Record provenance
        self.provenance = DemoProvenance(
            is_demo=True,
            endpoint=config.base_url,
            api_key_prefix=hash_api_key(config.api_key),
            timestamp=datetime.now(UTC).isoformat(),
        )

        # Track initialization event
        self.provenance_tracker.record(
            ProvenanceEventType.CONNECTOR_INIT,
            details={
                "endpoint": self.provenance.endpoint,
                "api_key_prefix": self.provenance.api_key_prefix,
            },
        )

        logger.info(
            "BybitDemoConnector initialized - DEMO MODE PROVENANCE: "
            "endpoint=%s, api_key=%s..., timestamp=%s",
            self.provenance.endpoint,
            self.provenance.api_key_prefix,
            self.provenance.timestamp,
        )

    @classmethod
    def from_env(
        cls,
        load_env: bool = True,
        market_data: MarketDataProvider | None = None,
        retry_config: RetryConfig | None = None,
    ) -> BybitDemoConnector:
        """Create connector from environment variables.

        Args:
            load_env: Whether to load .env file
            market_data: Optional market data provider for cached prices
            retry_config: Optional retry configuration

        Returns:
            Configured BybitDemoConnector instance

        Raises:
            ValueError: If demo credentials are not available
        """
        from data.exchange.bybit_connector import BybitConfig, BybitConnector

        # Create config from env (will use BYBIT_DEMO_API_KEY if available)
        config = BybitConfig.from_env(load_env=load_env)

        # Ensure demo mode
        if not config.demo:
            raise ValueError(
                "BYBIT_DEMO_API_KEY not found. "
                "BybitDemoConnector requires demo credentials."
            )

        # Create connector
        connector = BybitConnector(config)

        return cls(connector, market_data=market_data, retry_config=retry_config)

    @staticmethod
    def _normalize_bybit_symbol(symbol: str) -> str:
        """Normalize symbol into Bybit linear symbol format (e.g., BTCUSDT)."""
        normalized = symbol.upper().strip()
        normalized = normalized.replace("/", "").replace("-", "")
        normalized = normalized.replace(":USDT", "USDT")
        return normalized

    async def _ensure_connected(self) -> None:
        """Ensure the underlying connector session is active.

        Raises:
            BybitConnectorError: If the connector session cannot be established.
        """
        try:
            if self.connector._session is None or self.connector._session.closed:
                await self.connector.connect()
        except Exception as exc:
            raise BybitConnectorError(
                f"Cannot establish Bybit session: {exc}",
                operation="_ensure_connected",
            ) from exc

    def _extract_api_error(self, exc: Exception) -> BybitAPIError | None:
        """Attempt to extract structured error info from an exception.

        Checks for Bybit response dict patterns in exception attributes
        and messages.

        Args:
            exc: The caught exception.

        Returns:
            A classified BybitAPIError if extractable, else None.
        """
        # Some connector errors carry a response dict.
        ret_code = None
        ret_msg = ""
        for attr in ("response", "body", "args"):
            val = getattr(exc, attr, None)
            if isinstance(val, dict):
                ret_code = val.get("retCode")
                ret_msg = val.get("retMsg", str(exc))
                break
        if ret_code is not None:
            return classify_bybit_error(
                ret_code=ret_code,
                ret_msg=ret_msg,
                operation=getattr(exc, "operation", None),
            )
        return None

    async def get_market_price(self, symbol: str) -> float | None:
        """Fetch latest market price from Bybit and update local market_data cache."""
        try:
            await self._ensure_connected()

            bybit_symbol = self._normalize_bybit_symbol(symbol)
            ticker = await self._retry.execute(
                self.connector.get_ticker,
                bybit_symbol,
            )
            price_raw = ticker.get("result", {}).get("list", [{}])[0].get("lastPrice")
            if price_raw is None:
                return None
            price = float(price_raw)
            if price <= 0:
                return None

            if self.market_data is not None:
                self.market_data.set_price(symbol, price)
                self.market_data.set_price(bybit_symbol, price)

            self.provenance_tracker.record(
                ProvenanceEventType.PRICE_FETCHED,
                symbol=symbol,
                details={"price": price, "bybit_symbol": bybit_symbol},
            )
            # ErrorRateTracker: record successful price fetch
            try:
                from execution.alerts.error_rate_tracker import (
                    ErrorCategory,
                    ErrorRateTracker,
                )

                ErrorRateTracker().record_operation(
                    ErrorCategory.API,
                    success=True,
                    error_details={
                        "operation": "get_market_price",
                        "symbol": symbol,
                    },
                )
            except Exception as ert_exc:
                logger.debug(
                    "ErrorRateTracker GET_MARKET_PRICE_SUCCESS failed: %s", ert_exc
                )
            return price

        except BybitAPIError as exc:
            self.provenance_tracker.record(
                ProvenanceEventType.ERROR,
                symbol=symbol,
                details={"operation": "get_market_price", "error": str(exc)},
            )
            try:
                from execution.alerts.error_rate_tracker import (
                    ErrorCategory,
                    ErrorRateTracker,
                )

                ErrorRateTracker().record_operation(
                    ErrorCategory.API,
                    success=False,
                    error_details={
                        "operation": "get_market_price",
                        "symbol": symbol,
                        "error": str(exc),
                        "error_code": getattr(exc, "error_code", None),
                    },
                )
            except Exception as ert_exc:
                logger.debug(
                    "ErrorRateTracker GET_MARKET_PRICE_FAIL failed: %s", ert_exc
                )
            logger.warning(
                "Failed to fetch live Bybit market price for %s: %s", symbol, exc
            )
            return None
        except Exception as exc:
            self.provenance_tracker.record(
                ProvenanceEventType.ERROR,
                symbol=symbol,
                details={"operation": "get_market_price", "error": str(exc)},
            )
            try:
                from execution.alerts.error_rate_tracker import (
                    ErrorCategory,
                    ErrorRateTracker,
                )

                ErrorRateTracker().record_operation(
                    ErrorCategory.API,
                    success=False,
                    error_details={
                        "operation": "get_market_price",
                        "symbol": symbol,
                        "error": str(exc),
                    },
                )
            except Exception as ert_exc:
                logger.debug(
                    "ErrorRateTracker GET_MARKET_PRICE_FAIL failed: %s", ert_exc
                )
            logger.warning(
                "Failed to fetch live Bybit market price for %s: %s", symbol, exc
            )
            return None

    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: float | None = None,
        take_profit: float | None = None,
        stop_loss: float | None = None,
    ) -> PaperOrder:
        """Place an order via Bybit demo API.

        This method makes an actual authenticated API call to Bybit demo
        endpoints. It returns a PaperOrder with the actual order details
        from Bybit.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            side: Order side - "buy" or "sell"
            order_type: Order type - "market" or "limit"
            quantity: Order quantity
            price: Order price (required for limit orders)
            take_profit: Optional TP price to attach on venue
            stop_loss: Optional SL price to attach on venue

        Returns:
            PaperOrder with actual Bybit order details
        """
        logger.info(
            "DEMO EXECUTION: Placing %s %s order for %s %s via Bybit demo API at %s",
            order_type,
            side,
            quantity,
            symbol,
            self.provenance.endpoint,
        )

        try:
            await self._ensure_connected()
            venue_symbol = self._normalize_bybit_symbol(symbol)

            # Bybit V5 linear MARKET orders require IOC or FOK — GTC prevents fills
            if order_type.upper() == "MARKET":
                time_in_force = "IOC"
            else:
                time_in_force = "GTC"

            result = await self._retry.execute(
                self.connector.place_order,
                symbol=venue_symbol,
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=price,
                time_in_force=time_in_force,
            )

            # Check for API error in response
            ret_code = result.get("retCode")
            if ret_code is not None and ret_code != 0:
                api_err = classify_bybit_error(
                    ret_code=ret_code,
                    ret_msg=result.get("retMsg", ""),
                    operation="place_order",
                )
                raise api_err

            order = PaperOrder(
                order_id=result.get("order_id", ""),
                symbol=symbol.upper(),
                side=side.lower(),
                order_type=order_type.lower(),
                quantity=quantity,
                price=price if price else 0.0,
            )

            status = result.get("status", "Created")
            if status in ["Filled", "PartiallyFilled"]:
                fill_price = result.get("price", 0.0)
                if isinstance(fill_price, str):
                    try:
                        fill_price = float(fill_price)
                    except (ValueError, TypeError):
                        fill_price = 0.0
                if fill_price == 0.0 and self.market_data:
                    fill_price = (
                        self.market_data.get_price(symbol)
                        or self.market_data.get_price(venue_symbol)
                        or 0.0
                    )

                fill = PaperFill(
                    fill_id=f"fill_{order.order_id}",
                    order_id=order.order_id,
                    symbol=symbol.upper(),
                    side=side.lower(),
                    price=fill_price,
                    quantity=quantity,
                    timestamp=datetime.now(UTC),
                )
                order.add_fill(fill)
                order.state = OrderState.FILLED

                self.provenance_tracker.record(
                    ProvenanceEventType.ORDER_FILLED,
                    order_id=order.order_id,
                    symbol=symbol,
                    details={
                        "status": status,
                        "fill_price": fill_price,
                        "quantity": quantity,
                    },
                )
            else:
                order.state = OrderState.PENDING

            # Store order
            self._orders[order.order_id] = order

            # Poll for fill if order is not immediately filled
            # This handles async fills from Bybit (common for market orders)
            if order.state == OrderState.PENDING:
                order = await self._poll_for_fill(
                    order_id=order.order_id,
                    symbol=symbol,
                    initial_response=result,
                )

            self.provenance_tracker.record(
                ProvenanceEventType.ORDER_PLACED,
                order_id=order.order_id,
                symbol=symbol,
                details={
                    "side": side,
                    "order_type": order_type,
                    "quantity": quantity,
                    "price": price,
                    "status": status,
                },
            )

            # Attach venue-native TP/SL after order acceptance.
            reference_price = float(result.get("price") or order.price or 0.0)
            tp_valid, sl_valid = self._sanitize_trading_stops(
                side=side,
                reference_price=reference_price,
                take_profit=take_profit,
                stop_loss=stop_loss,
            )
            if tp_valid is not None:
                order.metadata["venue_take_profit"] = tp_valid
            if sl_valid is not None:
                order.metadata["venue_stop_loss"] = sl_valid

            if tp_valid is not None or sl_valid is not None:
                await self._attach_trading_stops_with_retry(
                    symbol=venue_symbol,
                    order_id=order.order_id,
                    take_profit=tp_valid,
                    stop_loss=sl_valid,
                )

            # Audit log
            from data.exchange.bybit_safety import audit_log_order_operation

            audit_log_order_operation(
                order_id=order.order_id,
                symbol=symbol,
                side=side,
                price=order.price or 0.0,
                quantity=quantity,
                order_type=order_type,
                status=status,
                operation="place_order_demo",
            )

            logger.info(
                "DEMO EXECUTION SUCCESS: Order %s placed via Bybit demo API. "
                "Status: %s, Fills: %d",
                order.order_id,
                status,
                len(order.fills),
            )

            # ErrorRateTracker: record successful order placement
            try:
                from execution.alerts.error_rate_tracker import (
                    ErrorCategory,
                    ErrorRateTracker,
                )

                ErrorRateTracker().record_operation(
                    ErrorCategory.EXECUTION,
                    success=True,
                    error_details={
                        "operation": "place_order",
                        "order_id": order.order_id,
                        "symbol": symbol,
                        "side": side,
                        "order_type": order_type,
                    },
                )
            except Exception as ert_exc:
                logger.debug("ErrorRateTracker PLACE_ORDER_SUCCESS failed: %s", ert_exc)

            return order

        except BybitAPIError as exc:
            logger.error("DEMO EXECUTION FAILED (API error): %s", exc)
            order = PaperOrder(
                order_id=f"rejected_{uuid.uuid4().hex[:12]}",
                symbol=symbol.upper(),
                side=side.lower(),
                order_type=order_type.lower(),
                quantity=float(quantity) if quantity else 0.001,
            )
            order.reject(f"Bybit demo API error: {exc}")
            self._orders[order.order_id] = order

            self.provenance_tracker.record(
                ProvenanceEventType.ORDER_REJECTED,
                order_id=order.order_id,
                symbol=symbol,
                details={
                    "error_code": exc.error_code,
                    "error": str(exc),
                    "retryable": exc.retryable,
                },
            )
            try:
                from execution.alerts.error_rate_tracker import (
                    ErrorCategory,
                    ErrorRateTracker,
                )

                ErrorRateTracker().record_operation(
                    ErrorCategory.EXECUTION,
                    success=False,
                    error_details={
                        "operation": "place_order",
                        "order_id": order.order_id,
                        "symbol": symbol,
                        "error": str(exc),
                        "error_code": getattr(exc, "error_code", None),
                    },
                )
            except Exception as ert_exc:
                logger.debug("ErrorRateTracker PLACE_ORDER_FAIL failed: %s", ert_exc)
            return order

        except Exception as exc:
            logger.error("DEMO EXECUTION FAILED: %s", exc)

            order = PaperOrder(
                order_id=f"rejected_{uuid.uuid4().hex[:12]}",
                symbol=symbol.upper(),
                side=side.lower(),
                order_type=order_type.lower(),
                quantity=float(quantity) if quantity else 0.001,
            )
            order.reject(f"Bybit demo API error: {exc}")
            self._orders[order.order_id] = order

            self.provenance_tracker.record(
                ProvenanceEventType.ORDER_REJECTED,
                order_id=order.order_id,
                symbol=symbol,
                details={"error": str(exc)},
            )
            try:
                from execution.alerts.error_rate_tracker import (
                    ErrorCategory,
                    ErrorRateTracker,
                )

                ErrorRateTracker().record_operation(
                    ErrorCategory.EXECUTION,
                    success=False,
                    error_details={
                        "operation": "place_order",
                        "order_id": order.order_id,
                        "symbol": symbol,
                        "error": str(exc),
                    },
                )
            except Exception as ert_exc:
                logger.debug("ErrorRateTracker PLACE_ORDER_FAIL failed: %s", ert_exc)
            return order

    def _sanitize_trading_stops(
        self,
        side: str,
        reference_price: float,
        take_profit: float | None,
        stop_loss: float | None,
    ) -> tuple[float | None, float | None]:
        """Ensure TP/SL are on the correct side of entry for venue acceptance."""
        tp = take_profit if take_profit and take_profit > 0 else None
        sl = stop_loss if stop_loss and stop_loss > 0 else None
        if reference_price <= 0:
            return tp, sl

        max_tp_distance_pct = float(os.getenv("BYBIT_TP_MAX_DISTANCE_PCT", "0.30"))
        max_sl_distance_pct = float(os.getenv("BYBIT_SL_MAX_DISTANCE_PCT", "0.20"))
        max_tp_distance_pct = max(0.01, min(max_tp_distance_pct, 5.0))
        max_sl_distance_pct = max(0.01, min(max_sl_distance_pct, 1.0))

        side_norm = side.lower().strip()
        if side_norm == "buy":
            if tp is not None and tp > reference_price * (1 + max_tp_distance_pct):
                clipped = reference_price * (1 + max_tp_distance_pct)
                logger.warning(
                    "Clipping long TP %.6f -> %.6f (max %.1f%% from ref %.6f)",
                    tp,
                    clipped,
                    max_tp_distance_pct * 100.0,
                    reference_price,
                )
                tp = clipped
            if sl is not None and sl < reference_price * (1 - max_sl_distance_pct):
                clipped = reference_price * (1 - max_sl_distance_pct)
                logger.warning(
                    "Clipping long SL %.6f -> %.6f (max %.1f%% from ref %.6f)",
                    sl,
                    clipped,
                    max_sl_distance_pct * 100.0,
                    reference_price,
                )
                sl = clipped
            if tp is not None and tp <= reference_price:
                logger.warning(
                    "Discarding invalid long TP %.6f <= ref %.6f",
                    tp,
                    reference_price,
                )
                tp = None
            if sl is not None and sl >= reference_price:
                logger.warning(
                    "Discarding invalid long SL %.6f >= ref %.6f",
                    sl,
                    reference_price,
                )
                sl = None
        else:
            if tp is not None and tp < reference_price * (1 - max_tp_distance_pct):
                clipped = reference_price * (1 - max_tp_distance_pct)
                logger.warning(
                    "Clipping short TP %.6f -> %.6f (max %.1f%% from ref %.6f)",
                    tp,
                    clipped,
                    max_tp_distance_pct * 100.0,
                    reference_price,
                )
                tp = clipped
            if sl is not None and sl > reference_price * (1 + max_sl_distance_pct):
                clipped = reference_price * (1 + max_sl_distance_pct)
                logger.warning(
                    "Clipping short SL %.6f -> %.6f (max %.1f%% from ref %.6f)",
                    sl,
                    clipped,
                    max_sl_distance_pct * 100.0,
                    reference_price,
                )
                sl = clipped
            if tp is not None and tp >= reference_price:
                logger.warning(
                    "Discarding invalid short TP %.6f >= ref %.6f",
                    tp,
                    reference_price,
                )
                tp = None
            if sl is not None and sl <= reference_price:
                logger.warning(
                    "Discarding invalid short SL %.6f <= ref %.6f",
                    sl,
                    reference_price,
                )
                sl = None

        return tp, sl

    async def _attach_trading_stops_with_retry(
        self,
        symbol: str,
        order_id: str,
        take_profit: float | None,
        stop_loss: float | None,
    ) -> None:
        """Best-effort TP/SL attachment with retries and incident reporting.

        Uses ExponentialBackoffRetry for retry logic with exponential backoff
        and jitter.
        """
        last_error: Exception | None = None
        for attempt in range(1, self._retry_config.max_retries + 1):
            try:
                await self.connector.set_trading_stop(
                    symbol=symbol,
                    take_profit=take_profit,
                    stop_loss=stop_loss,
                    position_idx=0,
                )
                logger.info(
                    "Attached Bybit TP/SL for %s (order_id=%s, tp=%s, sl=%s)",
                    symbol,
                    order_id,
                    take_profit,
                    stop_loss,
                )
                self.provenance_tracker.record(
                    ProvenanceEventType.TP_SL_ATTACHED,
                    order_id=order_id,
                    symbol=symbol,
                    details={
                        "take_profit": take_profit,
                        "stop_loss": stop_loss,
                        "attempt": attempt,
                    },
                )
                # ErrorRateTracker: record successful TP/SL attachment
                try:
                    from execution.alerts.error_rate_tracker import (
                        ErrorCategory,
                        ErrorRateTracker,
                    )

                    ErrorRateTracker().record_operation(
                        ErrorCategory.EXECUTION,
                        success=True,
                        error_details={
                            "operation": "attach_trading_stops",
                            "order_id": order_id,
                            "symbol": symbol,
                            "attempt": attempt,
                        },
                    )
                except Exception as ert_exc:
                    logger.debug(
                        "ErrorRateTracker ATTACH_STOPS_SUCCESS failed: %s", ert_exc
                    )
                return
            except Exception as exc:
                last_error = exc
                if attempt < self._retry_config.max_retries:
                    delay = self._retry_config.get_delay(attempt)
                    logger.warning(
                        "TP/SL attach attempt %d/%d failed for %s: %s (retry in %.2fs)",
                        attempt,
                        self._retry_config.max_retries,
                        symbol,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)

        logger.error(
            "Failed to attach Bybit TP/SL for %s (order_id=%s) after %s attempts: %s",
            symbol,
            order_id,
            self._retry_config.max_retries,
            last_error,
        )

        self.provenance_tracker.record(
            ProvenanceEventType.TP_SL_ATTACH_FAILED,
            order_id=order_id,
            symbol=symbol,
            details={
                "take_profit": take_profit,
                "stop_loss": stop_loss,
                "error": str(last_error),
                "attempts": self._retry_config.max_retries,
            },
        )

        # ErrorRateTracker: record failed TP/SL attachment
        try:
            from execution.alerts.error_rate_tracker import (
                ErrorCategory,
                ErrorRateTracker,
            )

            ErrorRateTracker().record_operation(
                ErrorCategory.EXECUTION,
                success=False,
                error_details={
                    "operation": "attach_trading_stops",
                    "order_id": order_id,
                    "symbol": symbol,
                    "error": str(last_error),
                    "attempts": self._retry_config.max_retries,
                },
            )
        except Exception as ert_exc:
            logger.debug("ErrorRateTracker ATTACH_STOPS_FAIL failed: %s", ert_exc)

        try:
            from execution.incident_reporter import publish_execution_incident

            await publish_execution_incident(
                incident_type="bybit_trading_stop_attach_failure",
                severity="P1",
                title="Bybit TP/SL attach failed",
                message=str(last_error),
                context={
                    "symbol": symbol,
                    "order_id": order_id,
                    "take_profit": take_profit,
                    "stop_loss": stop_loss,
                },
            )
        except Exception:
            logger.exception("Failed to publish TP/SL attachment failure incident")

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order via Bybit demo API.

        Args:
            order_id: ID of order to cancel

        Returns:
            True if cancelled, False otherwise
        """
        order = self._orders.get(order_id)
        if order is None:
            logger.warning("Cancel order failed: Order %s not found", order_id)
            return False

        try:
            await self._ensure_connected()

            await self._retry.execute(
                self.connector.cancel_order,
                symbol=self._normalize_bybit_symbol(order.symbol),
                order_id=order_id,
            )

            order.cancel()

            # Audit log
            from data.exchange.bybit_safety import audit_log_order_operation

            audit_log_order_operation(
                order_id=order_id,
                symbol=order.symbol,
                side=order.side,
                price=order.price or 0.0,
                quantity=order.quantity,
                order_type=order.order_type,
                status="Cancelled",
                operation="cancel_order_demo",
            )

            self.provenance_tracker.record(
                ProvenanceEventType.ORDER_CANCELLED,
                order_id=order_id,
                symbol=order.symbol,
            )

            # ErrorRateTracker: record successful order cancellation
            try:
                from execution.alerts.error_rate_tracker import (
                    ErrorCategory,
                    ErrorRateTracker,
                )

                ErrorRateTracker().record_operation(
                    ErrorCategory.EXECUTION,
                    success=True,
                    error_details={
                        "operation": "cancel_order",
                        "order_id": order_id,
                        "symbol": order.symbol,
                    },
                )
            except Exception as ert_exc:
                logger.debug(
                    "ErrorRateTracker CANCEL_ORDER_SUCCESS failed: %s", ert_exc
                )

            logger.info(
                "DEMO EXECUTION: Order %s cancelled via Bybit demo API",
                order_id,
            )
            return True

        except BybitAPIError as exc:
            logger.error(
                "DEMO EXECUTION: Cancel order %s failed (API error): %s", order_id, exc
            )
            self.provenance_tracker.record(
                ProvenanceEventType.ORDER_CANCEL_FAILED,
                order_id=order_id,
                symbol=order.symbol,
                details={"error_code": exc.error_code, "error": str(exc)},
            )
            try:
                from execution.alerts.error_rate_tracker import (
                    ErrorCategory,
                    ErrorRateTracker,
                )

                ErrorRateTracker().record_operation(
                    ErrorCategory.EXECUTION,
                    success=False,
                    error_details={
                        "operation": "cancel_order",
                        "order_id": order_id,
                        "symbol": order.symbol,
                        "error": str(exc),
                        "error_code": getattr(exc, "error_code", None),
                    },
                )
            except Exception as ert_exc:
                logger.debug("ErrorRateTracker CANCEL_ORDER_FAIL failed: %s", ert_exc)
            return False

        except Exception as exc:
            logger.error("DEMO EXECUTION: Cancel order %s failed: %s", order_id, exc)
            self.provenance_tracker.record(
                ProvenanceEventType.ORDER_CANCEL_FAILED,
                order_id=order_id,
                symbol=order.symbol,
                details={"error": str(exc)},
            )
            try:
                from execution.alerts.error_rate_tracker import (
                    ErrorCategory,
                    ErrorRateTracker,
                )

                ErrorRateTracker().record_operation(
                    ErrorCategory.EXECUTION,
                    success=False,
                    error_details={
                        "operation": "cancel_order",
                        "order_id": order_id,
                        "symbol": order.symbol,
                        "error": str(exc),
                    },
                )
            except Exception as ert_exc:
                logger.debug("ErrorRateTracker CANCEL_ORDER_FAIL failed: %s", ert_exc)
            return False

    def get_order(self, order_id: str) -> PaperOrder | None:
        """Get an order by ID.

        Args:
            order_id: Order identifier

        Returns:
            Order or None if not found
        """
        return self._orders.get(order_id)

    def get_orders(
        self,
        symbol: str | None = None,
        state: OrderState | None = None,
        side: str | None = None,
    ) -> list[PaperOrder]:
        """Get orders with optional filtering.

        Args:
            symbol: Filter by symbol
            state: Filter by order state
            side: Filter by side

        Returns:
            List of matching orders
        """
        orders = list(self._orders.values())

        if symbol:
            orders = [o for o in orders if o.symbol == symbol.upper()]
        if state:
            orders = [o for o in orders if o.state == state]
        if side:
            orders = [o for o in orders if o.side == side.lower()]

        return orders

    def get_position(self, symbol: str) -> dict[str, Any]:
        """Get position for a symbol from Bybit demo API.

        Args:
            symbol: Trading pair symbol

        Returns:
            Dictionary with position data
        """
        symbol = symbol.upper()
        position_qty = 0.0
        total_value = 0.0
        total_filled = 0.0

        for order in self._orders.values():
            if order.symbol != symbol:
                continue

            for fill in order.fills:
                if order.side == "buy":
                    position_qty += fill.quantity
                else:
                    position_qty -= fill.quantity

                total_value += fill.quantity * fill.price
                total_filled += fill.quantity

        avg_price = total_value / total_filled if total_filled > 0 else 0.0

        return {
            "symbol": symbol,
            "quantity": round(position_qty, 8),
            "avg_entry_price": round(avg_price, 8),
            "total_filled": round(total_filled, 8),
        }

    async def get_wallet_balance(
        self,
        account_type: str = "UNIFIED",
        coin: str | None = None,
    ) -> dict[str, Any]:
        """Get wallet balance from Bybit demo API.

        This method makes an authenticated API call to retrieve the
        demo account's wallet balance, equity, and unrealized PnL.
        This provides proof that we're connected to real demo funds.

        Args:
            account_type: Account type ("UNIFIED", "CONTRACT", "SPOT")
            coin: Specific coin to query (optional, queries all if None)

        Returns:
            Dictionary with:
            - total_equity: Total account equity in USD
            - available_balance: Available balance for trading
            - unrealized_pnl: Unrealized profit/loss
            - coin_balances: List of per-coin balances
            - raw_response: Full API response
        """
        logger.info(
            "DEMO BALANCE QUERY: Fetching wallet balance from Bybit demo API at %s",
            self.provenance.endpoint,
        )

        try:
            await self._ensure_connected()

            balance = await self._retry.execute(
                self.connector.get_wallet_balance,
                account_type=account_type,
                coin=coin,
            )

            logger.info(
                "DEMO BALANCE SUCCESS: Total equity=$%.2f, Available=$%.2f, "
                "Unrealized PnL=$%.2f",
                balance.get("total_equity", 0),
                balance.get("available_balance", 0),
                balance.get("unrealized_pnl", 0),
            )

            self.provenance_tracker.record(
                ProvenanceEventType.BALANCE_FETCHED,
                details={
                    "account_type": account_type,
                    "coin": coin,
                    "total_equity": balance.get("total_equity", 0),
                },
            )

            # ErrorRateTracker: record successful wallet balance fetch
            try:
                from execution.alerts.error_rate_tracker import (
                    ErrorCategory,
                    ErrorRateTracker,
                )

                ErrorRateTracker().record_operation(
                    ErrorCategory.API,
                    success=True,
                    error_details={
                        "operation": "get_wallet_balance",
                        "account_type": account_type,
                        "coin": coin,
                    },
                )
            except Exception as ert_exc:
                logger.debug(
                    "ErrorRateTracker GET_WALLET_BALANCE_SUCCESS failed: %s", ert_exc
                )

            return balance

        except BybitAPIError as exc:
            self.provenance_tracker.record(
                ProvenanceEventType.ERROR,
                details={"operation": "get_wallet_balance", "error": str(exc)},
            )
            try:
                from execution.alerts.error_rate_tracker import (
                    ErrorCategory,
                    ErrorRateTracker,
                )

                ErrorRateTracker().record_operation(
                    ErrorCategory.API,
                    success=False,
                    error_details={
                        "operation": "get_wallet_balance",
                        "account_type": account_type,
                        "coin": coin,
                        "error": str(exc),
                        "error_code": getattr(exc, "error_code", None),
                    },
                )
            except Exception as ert_exc:
                logger.debug(
                    "ErrorRateTracker GET_WALLET_BALANCE_FAIL failed: %s", ert_exc
                )
            raise

        except Exception as exc:
            self.provenance_tracker.record(
                ProvenanceEventType.ERROR,
                details={"operation": "get_wallet_balance", "error": str(exc)},
            )
            try:
                from execution.alerts.error_rate_tracker import (
                    ErrorCategory,
                    ErrorRateTracker,
                )

                ErrorRateTracker().record_operation(
                    ErrorCategory.API,
                    success=False,
                    error_details={
                        "operation": "get_wallet_balance",
                        "account_type": account_type,
                        "coin": coin,
                        "error": str(exc),
                    },
                )
            except Exception as ert_exc:
                logger.debug(
                    "ErrorRateTracker GET_WALLET_BALANCE_FAIL failed: %s", ert_exc
                )
            raise

    def get_provenance(self) -> DemoProvenance:
        """Get provenance information proving demo execution.

        Returns:
            DemoProvenance with execution details
        """
        return self.provenance

    def is_demo_mode(self) -> bool:
        """Check if connector is in demo mode.

        Returns:
            True if using demo endpoints
        """
        return self.provenance.is_demo

    async def health_check(self) -> dict[str, Any]:
        """Perform health check on Bybit demo connection.

        Returns:
            Health status dictionary
        """
        try:
            await self._ensure_connected()

            health = await self._retry.execute(self.connector.health_check)

            self.provenance_tracker.record(
                ProvenanceEventType.HEALTH_CHECK,
                details={"healthy": health.get("healthy", False)},
            )

            return {
                "healthy": health.get("healthy", False),
                "demo_mode": self.provenance.is_demo,
                "endpoint": self.provenance.endpoint,
                "api_accessible": health.get("api_accessible", False),
                "provenance": {
                    "is_demo": self.provenance.is_demo,
                    "endpoint": self.provenance.endpoint,
                    "api_key_prefix": self.provenance.api_key_prefix,
                    "timestamp": self.provenance.timestamp,
                },
            }
        except Exception as exc:
            logger.error("Health check failed: %s", exc)
            return {
                "healthy": False,
                "demo_mode": self.provenance.is_demo,
                "endpoint": self.provenance.endpoint,
                "error": str(exc),
            }

    async def close(self) -> None:
        """Close the connector and cleanup resources."""
        await self.connector.close()
        logger.info("BybitDemoConnector closed")

    # -------------------------------------------------------------------------
    # Fill Polling for Async Fills
    # -------------------------------------------------------------------------

    async def _is_duplicate_exec(self, exec_id: str) -> bool:
        """Check if an execution has already been processed (idempotency check).

        Args:
            exec_id: The execution ID from Bybit

        Returns:
            True if already processed, False otherwise
        """
        if self._redis is None:
            return False
        try:
            key = f"bybit:fill:dedup:exec:{exec_id}"
            return bool(self._redis.exists(key))
        except Exception as exc:
            logger.warning("Redis dedup check failed for exec_id=%s: %s", exec_id, exc)
            return False

    def _get_outcome_persistence(self) -> OutcomePersistence:  # type: ignore[misc]
        """Get or create OutcomePersistence instance (lazy init)."""
        if (
            not hasattr(self, "_outcome_persistence")
            or self._outcome_persistence is None
        ):
            self._outcome_persistence = OutcomePersistence(redis_client=self._redis)
        return self._outcome_persistence

    async def _mark_processed_exec(self, exec_id: str) -> None:
        """Mark an execution as processed in Redis.

        Args:
            exec_id: The execution ID from Bybit
        """
        if self._redis is None:
            return
        try:
            key = f"bybit:fill:dedup:exec:{exec_id}"
            ttl_seconds = self.DEDUP_TTL_HOURS * 3600
            self._redis.setex(key, ttl_seconds, "1")
        except Exception as exc:
            logger.warning("Redis dedup mark failed for exec_id=%s: %s", exec_id, exc)

    async def _poll_for_fill(
        self,
        order_id: str,
        symbol: str,
        initial_response: dict[str, Any],
    ) -> PaperOrder:
        """Poll for fill after order placement returns non-FILLED state.

        This handles the case where Bybit fills orders asynchronously,
        which is common for market orders.

        Args:
            order_id: The order ID to poll for
            symbol: The trading symbol
            initial_response: The initial place_order response

        Returns:
            Updated PaperOrder with fill data if detected, otherwise order
            in its current state after timeout
        """
        logger.info("Fill polling started: order_id=%s, symbol=%s", order_id, symbol)

        # Get or create the order from initial response
        order = self._orders.get(order_id)
        if order is None:
            # Reconstruct from initial response if not stored yet
            order = PaperOrder(
                order_id=order_id,
                symbol=symbol.upper(),
                side=initial_response.get("side", "buy").lower(),
                order_type=initial_response.get("order_type", "market").lower(),
                quantity=float(initial_response.get("quantity", 0)),
                price=float(initial_response.get("price") or 0),
            )
            order.state = OrderState.PENDING
            self._orders[order_id] = order

        timeout_ms = int(
            os.getenv("BYBIT_FILL_POLL_TIMEOUT_MS", str(self.DEFAULT_POLL_TIMEOUT_MS))
        )
        deadline = time.time() + (timeout_ms / 1000)
        poll_attempt = 0

        while time.time() < deadline:
            await asyncio.sleep(self.FILL_POLL_INTERVAL_MS / 1000)
            poll_attempt += 1

            logger.debug(
                "Polling for fill: order_id=%s, attempt=%d", order_id, poll_attempt
            )

            try:
                executions = await self._retry.execute(
                    lambda **kw: self.connector.get_fills(**kw),
                    symbol=self._normalize_bybit_symbol(symbol),
                    order_id=order_id,
                )
            except Exception as exc:
                logger.warning(
                    "Fill poll attempt %d failed for order_id=%s: %s",
                    poll_attempt,
                    order_id,
                    exc,
                )
                continue

            exec_list = executions.get("list", [])
            if not exec_list:
                continue

            # Process any new fills
            fills_detected = 0
            for exec_data in exec_list:
                exec_id = exec_data.get("execId")

                # Build a fallback dedup key if execId is missing
                exec_price = float(exec_data.get("execPrice", 0))
                exec_qty = float(exec_data.get("execQty", 0))
                exec_time = exec_data.get(
                    "execTime", str(datetime.now(UTC).timestamp())
                )

                if exec_price <= 0 or exec_qty <= 0:
                    logger.warning(
                        "Skipping fill with invalid price/qty: order_id=%s, exec_id=%s, price=%s, qty=%s",
                        order_id,
                        exec_id,
                        exec_price,
                        exec_qty,
                    )
                    continue

                # Use execId if available, otherwise build a composite key for dedup
                if exec_id:
                    dedup_key = exec_id
                else:
                    # Fallback: use composite key when Bybit doesn't return execId
                    dedup_key = f"{order_id}:{exec_price}:{exec_qty}:{exec_time}"
                    logger.warning(
                        "Bybit fill missing execId, using composite dedup key: order_id=%s, dedup_key=%s",
                        order_id,
                        dedup_key,
                    )

                # Idempotency check
                if await self._is_duplicate_exec(dedup_key):
                    logger.debug(
                        "Skipping duplicate fill: order_id=%s, dedup_key=%s",
                        order_id,
                        dedup_key,
                    )
                    continue

                fill = PaperFill(
                    fill_id=f"fill_{dedup_key}",
                    order_id=order_id,
                    symbol=symbol.upper(),
                    side=order.side,
                    price=exec_price,
                    quantity=exec_qty,
                    timestamp=datetime.now(UTC),
                    exchange_order_id=order_id,  # Native exchange order_id
                    exchange_fill_id=(
                        exec_id if exec_id else dedup_key
                    ),  # Native exchange exec_id
                )
                order.add_fill(fill)
                await self._mark_processed_exec(dedup_key)
                fills_detected += 1

                logger.info(
                    "Fill detected via polling: order_id=%s, exec_id=%s, qty=%s, price=%s",
                    order_id,
                    exec_id or dedup_key,
                    exec_qty,
                    exec_price,
                )

            # Update order state if fills were detected - but DON'T return yet
            # We need to keep polling until order is FILLED or timeout
            if fills_detected > 0:
                # Recalculate totals from all accumulated fills
                order.filled_quantity = sum(f.quantity for f in order.fills)
                order.avg_fill_price = (
                    sum(f.price * f.quantity for f in order.fills)
                    / order.filled_quantity
                )

                # Update state based on whether fully filled
                if order.remaining_quantity <= 0:
                    order.state = OrderState.FILLED
                    order.filled_at = datetime.now(UTC)

                    # Persistence: write fill to Redis for canary KPI trust
                    # AFTER state is finalized (order.state = FILLED)
                    if (
                        os.getenv("BYBIT_FILL_PERSISTENCE_ENABLED", "false").lower()
                        == "true"
                    ):
                        try:
                            persistence = self._get_outcome_persistence()
                            await asyncio.to_thread(persistence.persist_fill, order)
                        except Exception as exc:
                            logger.error(
                                "Failed to persist fill for order_id=%s: %s",
                                order_id,
                                exc,
                            )

                    self.provenance_tracker.record(
                        ProvenanceEventType.ORDER_FILLED,
                        order_id=order_id,
                        symbol=symbol,
                        details={
                            "fills_detected": fills_detected,
                            "total_filled_qty": order.filled_quantity,
                            "avg_fill_price": order.avg_fill_price,
                            "poll_attempts": poll_attempt,
                        },
                    )

                    logger.info(
                        "Fill polling completed (fully filled): order_id=%s, filled_qty=%s, avg_price=%s",
                        order_id,
                        order.filled_quantity,
                        order.avg_fill_price,
                    )
                    return order
                else:
                    # Partial fill - keep polling to get remaining fills
                    # Persistence: write partial fill state to Redis
                    if (
                        os.getenv("BYBIT_FILL_PERSISTENCE_ENABLED", "false").lower()
                        == "true"
                    ):
                        try:
                            persistence = self._get_outcome_persistence()
                            await asyncio.to_thread(persistence.persist_fill, order)
                        except Exception as exc:
                            logger.error(
                                "Failed to persist partial fill for order_id=%s: %s",
                                order_id,
                                exc,
                            )

                    self.provenance_tracker.record(
                        ProvenanceEventType.ORDER_PARTIAL,
                        order_id=order_id,
                        symbol=symbol,
                        details={
                            "fills_detected": fills_detected,
                            "total_filled_qty": order.filled_quantity,
                            "remaining_qty": order.remaining_quantity,
                            "avg_fill_price": order.avg_fill_price,
                            "poll_attempts": poll_attempt,
                        },
                    )

                    logger.info(
                        "Partial fill detected, continuing to poll: order_id=%s, filled_qty=%s, remaining_qty=%s",
                        order_id,
                        order.filled_quantity,
                        order.remaining_quantity,
                    )

        # Timeout - return order in current state
        logger.warning(
            "Fill polling timeout: order_id=%s, fills_found=%d, state=%s",
            order_id,
            len(order.fills),
            order.state.value,
        )

        self.provenance_tracker.record(
            ProvenanceEventType.ERROR,
            order_id=order_id,
            symbol=symbol,
            details={
                "operation": "_poll_for_fill",
                "error": "Fill polling timeout",
                "fills_found": len(order.fills),
                "poll_attempts": poll_attempt,
            },
        )

        return order


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class BybitDemoConnectorFactory:
    """Factory for creating BybitDemoConnector instances.

    This factory provides a way to create either a BybitDemoConnector
    (for authenticated demo trading) or fall back to OrderSimulator
    (if demo credentials are not available).
    """

    @staticmethod
    def create(
        prefer_demo: bool = True,
        market_data: MarketDataProvider | None = None,
        retry_config: RetryConfig | None = None,
    ) -> BybitDemoConnector | Any:
        """Create appropriate connector based on available credentials.

        Args:
            prefer_demo: Whether to prefer demo connector over simulator
            market_data: Optional market data provider
            retry_config: Optional retry configuration

        Returns:
            BybitDemoConnector if demo credentials available, else OrderSimulator
        """
        from execution.paper.order_simulator import OrderSimulator

        if prefer_demo:
            try:
                connector = BybitDemoConnector.from_env(
                    market_data=market_data,
                    retry_config=retry_config,
                )
                logger.info(
                    "BybitDemoConnectorFactory: Created BybitDemoConnector "
                    "with authenticated demo execution"
                )
                return connector
            except (ValueError, Exception) as exc:
                logger.warning(
                    "BybitDemoConnectorFactory: Demo credentials not available (%s). "
                    "Falling back to OrderSimulator.",
                    exc,
                )

        # Fall back to simulator
        simulator = OrderSimulator(market_data=market_data)
        logger.info(
            "BybitDemoConnectorFactory: Created OrderSimulator "
            "(simulated execution - no real API calls)"
        )
        return simulator

    @staticmethod
    def has_demo_credentials() -> bool:
        """Check if demo credentials are available.

        Returns:
            True if BYBIT_DEMO_API_KEY is set
        """
        return bool(os.environ.get("BYBIT_DEMO_API_KEY"))


def create_bybit_demo_connector(
    market_data: MarketDataProvider | None = None,
) -> BybitDemoConnector:
    """Create a BybitDemoConnector from environment.

    Convenience function for creating a demo connector.

    Args:
        market_data: Optional market data provider

    Returns:
        Configured BybitDemoConnector

    Raises:
        ValueError: If demo credentials are not available
    """
    return BybitDemoConnector.from_env(market_data=market_data)
