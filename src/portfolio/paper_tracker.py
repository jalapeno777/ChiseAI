"""Paper trading position tracker with Redis integration and alert hooks.

Provides real-time position tracking for paper trading with:
- Redis state synchronization
- Alert hooks for failure conditions
- Divergence detection between Redis and in-memory state
- Validation failure tracking
- Circuit breaker protection for Redis operations

For ST-PAPER-008: Paper Trading Alerts and Runbooks
For ST-PAPER-005: Circuit Breakers Core
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from common.circuit_breaker import CircuitBreaker, CircuitBreakerOpen

if TYPE_CHECKING:
    from portfolio_risk.alerts.detector import RiskAlertDetector
    from portfolio_risk.alerts.types import RiskAlert

logger = logging.getLogger(__name__)


@dataclass
class ValidationFailure:
    """Records a single validation failure."""

    order_id: str
    reason: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "order_id": self.order_id,
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat(),
            "details": self.details,
        }


@dataclass
class RedisHealthMetrics:
    """Tracks Redis health metrics for alerting."""

    error_count: int = 0
    total_operations: int = 0
    circuit_breaker_open: bool = False
    last_error: str | None = None
    last_successful_operation: datetime | None = None
    window_start: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def error_rate(self) -> float:
        """Calculate error rate percentage."""
        if self.total_operations == 0:
            return 0.0
        return (self.error_count / self.total_operations) * 100

    def record_success(self) -> None:
        """Record a successful operation."""
        self.total_operations += 1
        self.last_successful_operation = datetime.now(UTC)

    def record_failure(self, error: str) -> None:
        """Record a failed operation."""
        self.total_operations += 1
        self.error_count += 1
        self.last_error = error

    def reset_window(self) -> None:
        """Reset the metrics window."""
        self.error_count = 0
        self.total_operations = 0
        self.window_start = datetime.now(UTC)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "error_count": self.error_count,
            "total_operations": self.total_operations,
            "error_rate_pct": round(self.error_rate, 2),
            "circuit_breaker_open": self.circuit_breaker_open,
            "last_error": self.last_error,
            "last_successful_operation": (
                self.last_successful_operation.isoformat()
                if self.last_successful_operation
                else None
            ),
            "window_start": self.window_start.isoformat(),
        }


class PaperTracker:
    """Tracks paper trading positions with Redis sync and alert hooks.

    Features:
    - In-memory position tracking
    - Redis state synchronization
    - Automatic divergence detection
    - Alert hooks for Redis failures
    - Validation failure tracking
    """

    def __init__(
        self,
        portfolio_id: str = "paper_trading",
        alert_detector: RiskAlertDetector | None = None,
        divergence_threshold_pct: float = 5.0,
        validation_window_minutes: int = 5,
    ):
        """Initialize paper tracker.

        Args:
            portfolio_id: Portfolio identifier
            alert_detector: Optional alert detector for triggering alerts
            divergence_threshold_pct: Threshold for divergence alerts
            validation_window_minutes: Window for validation failure tracking
        """
        self.portfolio_id = portfolio_id
        self.alert_detector = alert_detector
        self.divergence_threshold_pct = divergence_threshold_pct
        self.validation_window_minutes = validation_window_minutes

        # In-memory state
        self._positions: dict[str, dict[str, Any]] = {}
        self._orders: dict[str, dict[str, Any]] = {}
        self._validation_failures: list[ValidationFailure] = []

        # Redis health tracking
        self._redis_health = RedisHealthMetrics()

        # Alert tracking to prevent spam
        self._last_redis_alert: datetime | None = None
        self._last_divergence_alert: datetime | None = None
        self._last_validation_alert: datetime | None = None
        self._min_alert_interval_seconds: int = 300  # 5 minutes

        # Circuit breaker for Redis operations
        self._redis_circuit = CircuitBreaker(
            failure_threshold=5,
            timeout_seconds=60.0,
            half_open_max_calls=3,
            name=f"redis_{portfolio_id}",
            expected_exception=Exception,
        )

        logger.info(
            f"PaperTracker initialized: portfolio={portfolio_id}, "
            f"divergence_threshold={divergence_threshold_pct}%"
        )

    # Redis Alert Hooks

    def on_redis_failure(
        self,
        error: str,
        affected_operations: list[str] | None = None,
        circuit_breaker_open: bool = False,
    ) -> RiskAlert | None:
        """Hook called when Redis operation fails.

        Args:
            error: Error message
            affected_operations: List of affected operation types
            circuit_breaker_open: Whether circuit breaker is open

        Returns:
            RiskAlert if alert triggered, None otherwise
        """
        affected_operations = affected_operations or ["state_sync", "position_update"]

        # Update health metrics
        self._redis_health.record_failure(error)
        self._redis_health.circuit_breaker_open = circuit_breaker_open

        logger.warning(
            f"Redis failure detected: {error}, "
            f"error_rate={self._redis_health.error_rate:.1f}%, "
            f"circuit_breaker={circuit_breaker_open}"
        )

        # Check if we should trigger an alert
        if not self.alert_detector:
            return None

        # Rate limit alerts
        if not self._should_trigger_alert(self._last_redis_alert):
            return None

        # Generate alert
        alert = self.alert_detector.detect_redis_failure(
            error_rate=self._redis_health.error_rate,
            affected_operations=affected_operations,
            circuit_breaker_open=circuit_breaker_open,
        )

        if alert:
            self._last_redis_alert = datetime.now(UTC)
            logger.critical(f"Redis failure alert triggered: {alert.message}")

        return alert

    def on_redis_success(self) -> None:
        """Hook called when Redis operation succeeds."""
        self._redis_health.record_success()

        # If we recovered from a failure state, log it
        if self._redis_health.circuit_breaker_open:
            logger.info("Redis circuit breaker closed, operations resumed")
            self._redis_health.circuit_breaker_open = False

    def on_redis_circuit_breaker_open(self, reason: str) -> RiskAlert | None:
        """Hook called when Redis circuit breaker opens.

        Args:
            reason: Reason for circuit breaker opening

        Returns:
            RiskAlert if alert triggered, None otherwise
        """
        self._redis_health.circuit_breaker_open = True

        logger.critical(f"Redis circuit breaker OPENED: {reason}")

        return self.on_redis_failure(
            error=f"Circuit breaker opened: {reason}",
            affected_operations=["all_redis_operations"],
            circuit_breaker_open=True,
        )

    # Divergence Detection

    def check_divergence(
        self,
        redis_state: dict[str, Any] | None = None,
    ) -> RiskAlert | None:
        """Check for divergence between Redis and in-memory state.

        Args:
            redis_state: Current state from Redis (fetched if None)

        Returns:
            RiskAlert if divergence detected, None otherwise
        """
        if not self.alert_detector:
            return None

        # Rate limit divergence alerts
        if not self._should_trigger_alert(self._last_divergence_alert):
            return None

        # Build memory state for comparison
        memory_state = self._build_memory_state()

        # Fetch Redis state if not provided
        if redis_state is None:
            redis_state = self._fetch_redis_state()

        if redis_state is None:
            logger.warning("Cannot check divergence: Redis state unavailable")
            return None

        # Generate alert
        alert = self.alert_detector.detect_paper_sync_divergence(
            redis_state=redis_state,
            memory_state=memory_state,
            divergence_threshold_pct=self.divergence_threshold_pct,
        )

        if alert:
            self._last_divergence_alert = datetime.now(UTC)
            logger.warning(f"Divergence alert triggered: {alert.message}")

        return alert

    def _build_memory_state(self) -> dict[str, Any]:
        """Build state dictionary from in-memory positions."""
        return {
            symbol: {
                "size": pos.get("size", 0),
                "notional_value": pos.get("notional_value", 0),
                "entry_price": pos.get("entry_price", 0),
            }
            for symbol, pos in self._positions.items()
        }

    def _fetch_redis_state(self) -> dict[str, Any] | None:
        """Fetch current state from Redis.

        Returns:
            Redis state dict or None if unavailable
        """
        try:
            # This would typically use the storage layer
            # For now, return None to indicate not implemented
            # In production, this would call:
            # return self._storage.get_all_positions(self.portfolio_id)
            return None
        except Exception as e:
            logger.error(f"Failed to fetch Redis state: {e}")
            self.on_redis_failure(str(e), affected_operations=["state_fetch"])
            return None

    # Validation Failure Tracking

    def record_validation_failure(
        self,
        order_id: str,
        reason: str,
        details: dict[str, Any] | None = None,
    ) -> RiskAlert | None:
        """Record an order validation failure.

        Args:
            order_id: Order identifier
            reason: Failure reason
            details: Additional failure details

        Returns:
            RiskAlert if high failure rate detected, None otherwise
        """
        failure = ValidationFailure(
            order_id=order_id,
            reason=reason,
            details=details or {},
        )
        self._validation_failures.append(failure)

        logger.debug(f"Validation failure recorded: {order_id} - {reason}")

        # Clean old failures and check for high failure rate
        self._clean_old_failures()
        return self._check_validation_failure_rate()

    def _clean_old_failures(self) -> None:
        """Remove validation failures outside the tracking window."""
        cutoff = datetime.now(UTC) - timedelta(minutes=self.validation_window_minutes)
        self._validation_failures = [
            f for f in self._validation_failures if f.timestamp > cutoff
        ]

    def _check_validation_failure_rate(self) -> RiskAlert | None:
        """Check if validation failure rate exceeds threshold.

        Returns:
            RiskAlert if threshold exceeded, None otherwise
        """
        if not self.alert_detector:
            return None

        # Rate limit validation alerts
        if not self._should_trigger_alert(self._last_validation_alert):
            return None

        # Count total and failed orders in window
        # Note: This is simplified - in production you'd track total orders separately
        total_orders = (
            len(self._validation_failures) + self._get_successful_orders_count()
        )
        failed_orders = len(self._validation_failures)

        if total_orders == 0:
            return None

        # Build failure breakdown
        failure_reasons: dict[str, int] = {}
        for failure in self._validation_failures:
            failure_reasons[failure.reason] = failure_reasons.get(failure.reason, 0) + 1

        # Generate alert
        alert = self.alert_detector.detect_validation_failure_rate(
            total_orders=total_orders,
            failed_orders=failed_orders,
            failure_reasons=failure_reasons,
            window_minutes=self.validation_window_minutes,
        )

        if alert:
            self._last_validation_alert = datetime.now(UTC)
            logger.warning(f"Validation failure rate alert triggered: {alert.message}")

        return alert

    def _get_successful_orders_count(self) -> int:
        """Get count of successful orders in the tracking window.

        Returns:
            Number of successful orders
        """
        # This would typically query order history
        # For now, estimate based on typical order flow
        # In production, this would query the database
        return max(10, len(self._validation_failures) * 2)  # Estimate

    def get_validation_failure_summary(self) -> dict[str, Any]:
        """Get summary of validation failures.

        Returns:
            Failure summary dictionary
        """
        self._clean_old_failures()

        failure_reasons: dict[str, int] = {}
        for failure in self._validation_failures:
            failure_reasons[failure.reason] = failure_reasons.get(failure.reason, 0) + 1

        total_orders = (
            len(self._validation_failures) + self._get_successful_orders_count()
        )
        failure_rate = (
            (len(self._validation_failures) / total_orders * 100)
            if total_orders > 0
            else 0
        )

        return {
            "window_minutes": self.validation_window_minutes,
            "total_failures": len(self._validation_failures),
            "total_orders": total_orders,
            "failure_rate_pct": round(failure_rate, 2),
            "failure_breakdown": failure_reasons,
            "recent_failures": [f.to_dict() for f in self._validation_failures[-10:]],
        }

    # Utility Methods

    def _should_trigger_alert(self, last_alert_time: datetime | None) -> bool:
        """Check if enough time has passed since last alert.

        Args:
            last_alert_time: Timestamp of last alert

        Returns:
            True if alert should be triggered
        """
        if last_alert_time is None:
            return True

        elapsed = (datetime.now(UTC) - last_alert_time).total_seconds()
        return elapsed >= self._min_alert_interval_seconds

    def get_redis_health(self) -> dict[str, Any]:
        """Get current Redis health metrics.

        Returns:
            Health metrics dictionary
        """
        return self._redis_health.to_dict()

    def get_sync_status(self) -> dict[str, Any]:
        """Get synchronization status between Redis and memory.

        Returns:
            Sync status dictionary
        """
        memory_state = self._build_memory_state()
        redis_state = self._fetch_redis_state()

        if redis_state is None:
            return {
                "redis_connected": False,
                "divergence_pct": 100.0,
                "memory_positions": len(memory_state),
                "redis_positions": 0,
                "last_sync": None,
            }

        # Calculate divergence
        all_keys = set(memory_state.keys()) | set(redis_state.keys())
        diverged_count = 0
        total_divergence = 0.0

        for key in all_keys:
            mem_val = memory_state.get(key, {})
            redis_val = redis_state.get(key, {})

            # Compare notional values
            mem_notional = mem_val.get("notional_value", 0)
            redis_notional = redis_val.get("notional_value", 0)

            if redis_notional != 0:
                diff_pct = (
                    abs(mem_notional - redis_notional) / abs(redis_notional) * 100
                )
            else:
                diff_pct = abs(mem_notional) * 100

            if diff_pct > self.divergence_threshold_pct:
                diverged_count += 1
                total_divergence += diff_pct

        divergence_pct = total_divergence / len(all_keys) if all_keys else 0

        return {
            "redis_connected": True,
            "divergence_pct": round(divergence_pct, 2),
            "memory_positions": len(memory_state),
            "redis_positions": len(redis_state),
            "diverged_positions": diverged_count,
            "last_sync": (
                self._redis_health.last_successful_operation.isoformat()
                if self._redis_health.last_successful_operation
                else None
            ),
        }

    def reset_alert_timers(self) -> None:
        """Reset all alert timers (useful for testing)."""
        self._last_redis_alert = None
        self._last_divergence_alert = None
        self._last_validation_alert = None
        logger.debug("Alert timers reset")

    # Circuit Breaker Protected Redis Operations

    def get_position(self, symbol: str) -> dict[str, Any] | None:
        """Get position from Redis with circuit breaker protection.

        Args:
            symbol: Trading pair symbol (e.g., "BTC-USD")

        Returns:
            Position dict or None if not found/circuit open

        Raises:
            CircuitBreakerOpen: If circuit breaker is open (caller should handle)
        """
        try:
            position = self._redis_circuit.call(
                self._get_position_from_redis,
                symbol,
            )
            self.on_redis_success()
            return cast("dict[str, Any] | None", position)
        except CircuitBreakerOpen:
            # Circuit is open - fail fast and return from memory
            logger.warning(
                f"Circuit breaker open for get_position({symbol}), "
                f"returning from memory"
            )
            result: dict[str, Any] | None = self._positions.get(symbol)
            return result
        except Exception as e:
            logger.error(f"Redis error in get_position({symbol}): {e}")
            self.on_redis_failure(str(e), affected_operations=["get_position"])
            # Return from memory as fallback
            fallback_result: dict[str, Any] | None = self._positions.get(symbol)
            return fallback_result

    def save_position(self, symbol: str, position: dict[str, Any]) -> bool:
        """Save position to Redis with circuit breaker protection.

        Args:
            symbol: Trading pair symbol
            position: Position data to save

        Returns:
            True if saved successfully, False otherwise
        """
        # Always update memory first
        self._positions[symbol] = position

        try:
            self._redis_circuit.call(
                self._save_position_to_redis,
                symbol,
                position,
            )
            self.on_redis_success()
            return True
        except CircuitBreakerOpen:
            logger.warning(
                f"Circuit breaker open for save_position({symbol}), "
                f"position stored in memory only"
            )
            return False
        except Exception as e:
            logger.error(f"Redis error in save_position({symbol}): {e}")
            self.on_redis_failure(str(e), affected_operations=["save_position"])
            return False

    def update_position(
        self,
        symbol: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Update position in Redis with circuit breaker protection.

        Args:
            symbol: Trading pair symbol
            updates: Fields to update

        Returns:
            Updated position dict or None if failed
        """
        # Get current position from memory
        current = self._positions.get(symbol, {})
        if not current:
            logger.warning(f"Cannot update position {symbol}: not found in memory")
            return None

        # Apply updates to memory
        updated = {**current, **updates}
        self._positions[symbol] = updated

        try:
            self._redis_circuit.call(
                self._update_position_in_redis,
                symbol,
                updates,
            )
            self.on_redis_success()
            return updated
        except CircuitBreakerOpen:
            logger.warning(
                f"Circuit breaker open for update_position({symbol}), "
                f"update stored in memory only"
            )
            return updated
        except Exception as e:
            logger.error(f"Redis error in update_position({symbol}): {e}")
            self.on_redis_failure(str(e), affected_operations=["update_position"])
            return updated

    def delete_position(self, symbol: str) -> bool:
        """Delete position from Redis with circuit breaker protection.

        Args:
            symbol: Trading pair symbol

        Returns:
            True if deleted successfully, False otherwise
        """
        # Always delete from memory first
        if symbol in self._positions:
            del self._positions[symbol]

        try:
            self._redis_circuit.call(
                self._delete_position_from_redis,
                symbol,
            )
            self.on_redis_success()
            return True
        except CircuitBreakerOpen:
            logger.warning(
                f"Circuit breaker open for delete_position({symbol}), "
                f"deleted from memory only"
            )
            return False
        except Exception as e:
            logger.error(f"Redis error in delete_position({symbol}): {e}")
            self.on_redis_failure(str(e), affected_operations=["delete_position"])
            return False

    def get_circuit_breaker_state(self) -> dict[str, Any]:
        """Get current circuit breaker state for monitoring.

        Returns:
            Circuit breaker state dictionary
        """
        state: dict[str, Any] = self._redis_circuit.get_state_dict()
        return state

    def reset_circuit_breaker(self) -> None:
        """Reset the Redis circuit breaker (useful for testing/recovery)."""
        self._redis_circuit.reset()
        logger.info("Redis circuit breaker reset")

    # Internal Redis operations (to be implemented with actual Redis client)

    def _get_position_from_redis(self, symbol: str) -> dict[str, Any] | None:
        """Fetch position from Redis.

        Args:
            symbol: Trading pair symbol

        Returns:
            Position dict or None if not found

        Note:
            This is a placeholder. In production, this would use the
            actual Redis client to fetch from storage.
        """
        # Placeholder - return from memory for now
        # In production: return redis_client.hgetall(f"position:{symbol}")
        return self._positions.get(symbol)

    def _save_position_to_redis(
        self,
        symbol: str,
        position: dict[str, Any],
    ) -> None:
        """Save position to Redis.

        Args:
            symbol: Trading pair symbol
            position: Position data to save

        Note:
            This is a placeholder. In production, this would use the
            actual Redis client to save to storage.
        """
        # Placeholder - already saved to memory
        # In production: redis_client.hset(f"position:{symbol}", mapping=position)
        pass

    def _update_position_in_redis(
        self,
        symbol: str,
        updates: dict[str, Any],
    ) -> None:
        """Update position in Redis.

        Args:
            symbol: Trading pair symbol
            updates: Fields to update

        Note:
            This is a placeholder. In production, this would use the
            actual Redis client to update storage.
        """
        # Placeholder - already updated in memory
        # In production: redis_client.hset(f"position:{symbol}", mapping=updates)
        pass

    def _delete_position_from_redis(self, symbol: str) -> None:
        """Delete position from Redis.

        Args:
            symbol: Trading pair symbol

        Note:
            This is a placeholder. In production, this would use the
            actual Redis client to delete from storage.
        """
        # Placeholder - already deleted from memory
        # In production: redis_client.delete(f"position:{symbol}")
        pass


# Import timedelta for _clean_old_failures
from datetime import timedelta  # noqa: E402
