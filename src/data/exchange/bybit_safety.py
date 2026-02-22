"""Bybit safety and security assertions.

This module provides:
- Demo mode enforcement (only demo/testnet endpoints allowed)
- Environment validation against allowed demo patterns
- Kill switch integration for emergency position closure
- Audit logging for all order operations

For ST-LAUNCH-001: Bybit Environment Assertions

Authoritative Endpoints:
- REST API: https://api-demo.bybit.com
- Private WebSocket: wss://stream-demo.bybit.com/v5/private
- Public WebSocket: wss://stream.bybit.com/v5/public (mainnet for public)
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# ============================================================================
# Endpoint Configuration
# ============================================================================

DEMO_ENDPOINTS: dict[str, list[str]] = {
    "rest": ["api-demo.bybit.com", "api-testnet.bybit.com"],
    "private_ws": ["stream-demo.bybit.com"],
    # Public WS uses mainnet as it's public data only
    "public_ws": ["stream.bybit.com", "stream-testnet.bybit.com"],
}

PRODUCTION_ENDPOINTS: dict[str, list[str]] = {
    "rest": ["api.bybit.com", "api.bytick.com"],
    "private_ws": ["stream.bybit.com"],  # Production private uses same as public
    "public_ws": ["stream.bybit.com"],
}

# All allowed demo patterns (compiled regex for efficiency)
# This includes demo and testnet endpoints
DEMO_PATTERNS: dict[str, re.Pattern[str]] = {
    "rest": re.compile(r"https://(?:api-demo|api-testnet)\.bybit\.com", re.IGNORECASE),
    "private_ws": re.compile(
        r"wss://stream-(?:demo|testnet)\.bybit\.com/v5/private", re.IGNORECASE
    ),
    # Public WS allows mainnet and testnet (public data is safe)
    # Includes all public market data paths (linear, spot, etc.)
    "public_ws": re.compile(
        r"wss://stream(?:[-]?testnet)?\.bybit\.com/v5/public", re.IGNORECASE
    ),
}

# Production patterns (for detection)
# Note: Only block production PRIVATE endpoints, not public market data
PRODUCTION_PATTERNS: dict[str, re.Pattern[str]] = {
    "rest": re.compile(r"https://api\.(?:by(?:bit|tick))\.com", re.IGNORECASE),
    # Production private is stream.bybit.com with /v5/private (authenticated)
    "private_ws": re.compile(r"wss://stream\.bybit\.com/v5/private", re.IGNORECASE),
    # Public WS - only block if it's a private stream on production
    "public_ws": re.compile(r"wss://stream\.bybit\.com/v5/private", re.IGNORECASE),
}


# ============================================================================
# Security Exception
# ============================================================================


class SecurityException(Exception):
    """Raised when production endpoint access is detected.

    This is a critical security exception that blocks any production
    endpoint access to ensure demo-only operation.

    Attributes:
        endpoint: The endpoint URL that was attempted
        operation: The operation that was attempted
        timestamp: When the attempt occurred (ISO format)
    """

    def __init__(
        self,
        message: str,
        endpoint: str = "",
        operation: str = "",
    ) -> None:
        self.endpoint = endpoint
        self.operation = operation
        self.timestamp = datetime.now(UTC).isoformat()
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "error": "SecurityException",
            "message": str(self),
            "endpoint": self.endpoint,
            "operation": self.operation,
            "timestamp": self.timestamp,
        }


# ============================================================================
# Endpoint Validation
# ============================================================================


def validate_demo_endpoint(
    endpoint: str,
    endpoint_type: str = "rest",
) -> None:
    """Validate that endpoint is an allowed demo endpoint.

    Args:
        endpoint: The endpoint URL to validate
        endpoint_type: Type of endpoint ("rest", "private_ws", "public_ws")

    Raises:
        SecurityException: If endpoint is a production endpoint
    """
    # Check production patterns first (most critical)
    if endpoint_type in PRODUCTION_PATTERNS:
        if PRODUCTION_PATTERNS[endpoint_type].match(endpoint):
            raise SecurityException(
                f"PRODUCTION ENDPOINT DETECTED: {endpoint} "
                f"This is not allowed. Only demo endpoints are permitted.",
                endpoint=endpoint,
                operation=f"validate_{endpoint_type}",
            )

    # Check demo patterns
    if endpoint_type in DEMO_PATTERNS:
        if not DEMO_PATTERNS[endpoint_type].match(endpoint):
            raise SecurityException(
                f"INVALID DEMO ENDPOINT: {endpoint} "
                f"Not in allowed demo patterns for {endpoint_type}",
                endpoint=endpoint,
                operation=f"validate_{endpoint_type}",
            )


def validate_endpoint_url(endpoint: str) -> None:
    """Validate endpoint URL against all known patterns.

    Args:
        endpoint: The endpoint URL to validate

    Raises:
        SecurityException: If endpoint is a production endpoint
    """
    # Determine endpoint type from URL
    endpoint_type = _classify_endpoint(endpoint)

    # Validate against allowed demo patterns
    validate_demo_endpoint(endpoint, endpoint_type)


def _classify_endpoint(endpoint: str) -> str:
    """Classify endpoint type from URL.

    Args:
        endpoint: The endpoint URL

    Returns:
        Endpoint type: "rest", "private_ws", or "public_ws"
    """
    if endpoint.startswith("wss://"):
        if "private" in endpoint:
            return "private_ws"
        return "public_ws"
    return "rest"


def is_demo_endpoint(endpoint: str) -> bool:
    """Check if endpoint is a valid demo endpoint.

    Args:
        endpoint: The endpoint URL to check

    Returns:
        True if endpoint is a valid demo endpoint
    """
    try:
        endpoint_type = _classify_endpoint(endpoint)
        if endpoint_type in DEMO_PATTERNS:
            return DEMO_PATTERNS[endpoint_type].match(endpoint) is not None
    except SecurityException:
        return False
    return False


# ============================================================================
# Kill Switch Integration
# ============================================================================

# Redis key for kill switch
KILL_SWITCH_KEY = "launch:safety:kill_switch:triggered"
KILL_SWITCH_CHECK_INTERVAL = 1.0  # seconds


@dataclass
class KillSwitchStatus:
    """Kill switch status.

    Attributes:
        triggered: Whether kill switch is triggered
        triggered_at: When kill switch was triggered (ISO format)
        reason: Reason for kill switch trigger
    """

    triggered: bool = False
    triggered_at: str | None = None
    reason: str | None = None


class KillSwitchMonitor:
    """Monitor for kill switch trigger.

    Listens to Redis for kill switch activation and provides
    callbacks for emergency position closure.
    """

    def __init__(
        self,
        check_interval: float = KILL_SWITCH_CHECK_INTERVAL,
    ) -> None:
        """Initialize kill switch monitor.

        Args:
            check_interval: How often to check for kill switch (seconds)
        """
        self.check_interval = check_interval
        self._running = False
        self._task: asyncio.Task | None = None
        self._callbacks: list[Callable[[], Any]] = []
        self._last_triggered: bool = False

    def add_callback(self, callback: Callable[[], Any]) -> None:
        """Add callback to be called when kill switch triggers.

        Args:
            callback: Async function to call for emergency closure
        """
        self._callbacks.append(callback)

    async def start(self) -> None:
        """Start monitoring for kill switch."""
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())

    async def stop(self) -> None:
        """Stop monitoring for kill switch."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                status = await get_kill_switch_status()

                # Trigger callbacks if newly triggered
                if status.triggered and not self._last_triggered:
                    logger.warning(
                        f"KILL SWITCH TRIGGERED: {status.reason} "
                        f"[at {status.triggered_at}]"
                    )
                    # Execute all callbacks
                    for callback in self._callbacks:
                        try:
                            if asyncio.iscoroutinefunction(callback):
                                await callback()
                            else:
                                callback()
                        except Exception as e:
                            logger.error(f"Kill switch callback error: {e}")

                self._last_triggered = status.triggered

            except Exception as e:
                logger.error(f"Kill switch monitor error: {e}")

            await asyncio.sleep(self.check_interval)


def get_kill_switch_status() -> KillSwitchStatus:
    """Get current kill switch status from Redis.

    Returns:
        Current kill switch status

    Note:
        Falls back to environment variable if Redis unavailable
    """
    try:
        # Try Redis first
        from tools import redis_state_get

        result = redis_state_get(key=KILL_SWITCH_KEY)
        if result:
            import json

            data = json.loads(result)
            return KillSwitchStatus(
                triggered=data.get("triggered", False),
                triggered_at=data.get("triggered_at"),
                reason=data.get("reason"),
            )
    except Exception as e:
        logger.debug(f"Redis unavailable for kill switch: {e}")

    # Fallback to environment variable
    kill_switch = os.environ.get("BYBIT_KILL_SWITCH", "").lower()
    if kill_switch in ("1", "true", "yes"):
        return KillSwitchStatus(
            triggered=True,
            triggered_at=datetime.now(UTC).isoformat(),
            reason="Environment variable override",
        )

    return KillSwitchStatus()


async def setup_kill_switch_listener(
    callbacks: list[Callable[[], Any]],
    check_interval: float = KILL_SWITCH_CHECK_INTERVAL,
) -> KillSwitchMonitor:
    """Set up kill switch listener with callbacks.

    Args:
        callbacks: List of async callbacks to execute on kill switch
        check_interval: How often to check for kill switch (seconds)

    Returns:
        Started KillSwitchMonitor instance
    """
    monitor = KillSwitchMonitor(check_interval=check_interval)
    for callback in callbacks:
        monitor.add_callback(callback)
    await monitor.start()
    return monitor


# ============================================================================
# Audit Logging
# ============================================================================

# In-memory audit log for order operations (for 90-day retention)
_order_audit_log: list[dict[str, Any]] = []
_audit_log_lock = threading.Lock()

# Maximum entries for in-memory log (~90 days at 1000 orders/day)
MAX_AUDIT_LOG_ENTRIES = 90000


@dataclass
class OrderAuditEntry:
    """Audit entry for order operations.

    Attributes:
        timestamp: When the operation occurred (ISO format)
        order_id: The order ID
        symbol: Trading symbol
        side: Order side (buy/sell)
        price: Order price
        quantity: Order quantity
        order_type: Order type (market/limit)
        status: Order status
        operation: The operation performed
    """

    timestamp: str
    order_id: str
    symbol: str
    side: str
    price: float
    quantity: float
    order_type: str
    status: str
    operation: str


def audit_log_order_operation(
    order_id: str,
    symbol: str,
    side: str,
    price: float,
    quantity: float,
    order_type: str,
    status: str,
    operation: str,
) -> None:
    """Log order operation for audit trail.

    Args:
        order_id: The order ID
        symbol: Trading symbol
        side: Order side (buy/sell)
        price: Order price
        quantity: Order quantity
        order_type: Order type (market/limit)
        status: Order status
        operation: The operation performed (place, cancel, close, etc.)
    """
    entry = OrderAuditEntry(
        timestamp=datetime.now(UTC).isoformat(),
        order_id=order_id,
        symbol=symbol,
        side=side,
        price=price,
        quantity=quantity,
        order_type=order_type,
        status=status,
        operation=operation,
    )

    entry_dict = {
        "timestamp": entry.timestamp,
        "order_id": entry.order_id,
        "symbol": entry.symbol,
        "side": entry.side,
        "price": entry.price,
        "quantity": entry.quantity,
        "order_type": entry.order_type,
        "status": entry.status,
        "operation": entry.operation,
    }

    with _audit_log_lock:
        _order_audit_log.append(entry_dict)

        # Trim old entries if over limit
        while len(_order_audit_log) > MAX_AUDIT_LOG_ENTRIES:
            _order_audit_log.pop(0)

    # Also try to log to PostgreSQL if available
    _log_to_database(entry_dict)

    logger.info(
        f"AUDIT: {operation} order {order_id} | {symbol} {side} "
        f"@ {price} x {quantity} | status: {status}"
    )


def _log_to_database(entry: dict[str, Any]) -> None:
    """Log audit entry to PostgreSQL if available.

    Args:
        entry: Audit entry dictionary
    """
    try:
        # Try to use the audit logging infrastructure
        # This is a best-effort log - don't fail if unavailable
        import asyncio

        from sqlalchemy import text
        from tools import get_postgres_connection

        # Run in async context
        async def _do_insert():
            conn = await get_postgres_connection()
            async with conn.connect() as session:
                await session.execute(
                    text("""
                        INSERT INTO order_audit_log (
                            timestamp, order_id, symbol, side, price,
                            quantity, order_type, status, operation
                        ) VALUES (
                            :timestamp, :order_id, :symbol, :side, :price,
                            :quantity, :order_type, :status, :operation
                        )
                    """),
                    entry,
                )
                await session.commit()

        asyncio.get_event_loop().run_until_complete(_do_insert())

    except Exception as e:
        # Log to debug - this is best-effort
        logger.debug(f"Database audit log unavailable: {e}")


def get_audit_log(
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    order_id: str | None = None,
    symbol: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Query audit log with filters.

    Args:
        start_time: Filter entries after this time
        end_time: Filter entries before this time
        order_id: Filter by order ID
        symbol: Filter by symbol
        limit: Maximum entries to return

    Returns:
        List of matching audit entries
    """
    with _audit_log_lock:
        results = list(_order_audit_log)

    # Apply filters
    if start_time:
        results = [e for e in results if e["timestamp"] >= start_time.isoformat()]

    if end_time:
        results = [e for e in results if e["timestamp"] <= end_time.isoformat()]

    if order_id:
        results = [e for e in results if e["order_id"] == order_id]

    if symbol:
        results = [e for e in results if e["symbol"] == symbol]

    # Return most recent first, limited
    results = sorted(results, key=lambda x: x["timestamp"], reverse=True)
    return results[:limit]


# ============================================================================
# Demo Mode Enforcement Decorator
# ============================================================================

from functools import wraps


def enforce_demo_mode(operation_name: str = ""):
    """Decorator to enforce demo mode on API methods.

    Args:
        operation_name: Name of operation for error messages

    Usage:
        @enforce_demo_mode("place_order")
        async def place_order(self, ...):
            ...
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            # Validate endpoint before operation
            endpoint = getattr(self.config, "base_url", "")
            if endpoint:
                validate_endpoint_url(endpoint)

            # Also validate private_ws if used
            private_ws = getattr(self.config, "private_ws_url", "")
            if private_ws:
                validate_endpoint_url(private_ws)

            # Proceed with operation
            return await func(self, *args, **kwargs)

        return wrapper

    return decorator
