"""Paper trading tracker for position and order management.

Provides paper trading state tracking with Redis integration.

For HOTFIX-PAPER-API-001: Paper Trading API Endpoints
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from paper_trading.models import (
    OrderSide,
    OrderState,
    OrderType,
    PaperOrder,
    PaperPnL,
    PaperPortfolio,
    PaperPosition,
    PositionSide,
)

logger = logging.getLogger(__name__)


class PaperTradingTracker:
    """Tracks paper trading state with Redis persistence.

    Provides methods for:
    - Position tracking
    - Order management
    - PnL calculation
    - Portfolio state queries

    Key patterns:
    - paper:position:{symbol} - Position data
    - paper:order:{order_id} - Order data
    - paper:portfolio:{portfolio_id} - Portfolio summary
    - paper:pnl:{portfolio_id} - PnL metrics
    """

    # Redis key patterns
    POSITION_KEY_PATTERN = "paper:position:{symbol}"
    ORDER_KEY_PATTERN = "paper:order:{order_id}"
    PORTFOLIO_KEY = "paper:portfolio:{portfolio_id}"
    PNL_KEY = "paper:pnl:{portfolio_id}"
    ORDERS_INDEX_KEY = "paper:orders:index"
    POSITIONS_INDEX_KEY = "paper:positions:index"

    def __init__(
        self,
        portfolio_id: str = "default",
        redis_client: Any | None = None,
        ttl_seconds: int = 604800,  # 7 days
    ):
        """Initialize paper trading tracker.

        Args:
            portfolio_id: Portfolio identifier
            redis_client: Redis client (created if None)
            ttl_seconds: TTL for persisted data
        """
        self.portfolio_id = portfolio_id
        self._redis = redis_client
        self.ttl_seconds = ttl_seconds

        logger.info(f"PaperTradingTracker initialized: portfolio={portfolio_id}")

    def _get_redis(self) -> Any:
        """Get or create Redis client."""
        if self._redis is None:
            try:
                import redis as redis_lib
                import os

                redis_host = os.getenv("REDIS_HOST", "host.docker.internal")
                redis_port = int(os.getenv("REDIS_PORT", "6380"))
                self._redis = redis_lib.Redis(
                    host=redis_host,
                    port=redis_port,
                    decode_responses=True,
                )
                logger.debug(f"Connected to Redis at {redis_host}:{redis_port}")
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}")
                raise
        return self._redis

    # Position methods

    def get_position(self, symbol: str) -> PaperPosition | None:
        """Get position for a symbol.

        Args:
            symbol: Trading pair symbol

        Returns:
            Position data or None if not found
        """
        try:
            redis = self._get_redis()
            key = self.POSITION_KEY_PATTERN.format(symbol=symbol.upper())
            data = redis.get(key)

            if data:
                position_data = json.loads(data)
                return PaperPosition(**position_data)
            return None

        except Exception as e:
            logger.error(f"Failed to get position for {symbol}: {e}")
            return None

    def get_all_positions(self) -> list[PaperPosition]:
        """Get all open positions.

        Returns:
            List of all open positions
        """
        try:
            redis = self._get_redis()

            # Get all position keys from index
            position_keys = redis.smembers(self.POSITIONS_INDEX_KEY)

            positions = []
            for key in position_keys:
                data = redis.get(key)
                if data:
                    position_data = json.loads(data)
                    positions.append(PaperPosition(**position_data))

            return positions

        except Exception as e:
            logger.error(f"Failed to get all positions: {e}")
            return []

    def save_position(self, position: PaperPosition) -> bool:
        """Save a position.

        Args:
            position: Position to save

        Returns:
            True if saved successfully
        """
        try:
            redis = self._get_redis()
            key = self.POSITION_KEY_PATTERN.format(symbol=position.symbol.upper())

            # Update timestamp
            position.updated_at = datetime.now(UTC)

            # Save position
            redis.set(key, json.dumps(position.to_dict()))
            redis.expire(key, self.ttl_seconds)

            # Add to index
            redis.sadd(self.POSITIONS_INDEX_KEY, key)
            redis.expire(self.POSITIONS_INDEX_KEY, self.ttl_seconds)

            logger.debug(f"Saved position: {key}")
            return True

        except Exception as e:
            logger.error(f"Failed to save position: {e}")
            return False

    def delete_position(self, symbol: str) -> bool:
        """Delete a position.

        Args:
            symbol: Trading pair symbol

        Returns:
            True if deleted successfully
        """
        try:
            redis = self._get_redis()
            key = self.POSITION_KEY_PATTERN.format(symbol=symbol.upper())

            redis.delete(key)
            redis.srem(self.POSITIONS_INDEX_KEY, key)

            logger.debug(f"Deleted position: {key}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete position: {e}")
            return False

    # Order methods

    def get_order(self, order_id: str) -> PaperOrder | None:
        """Get order by ID.

        Args:
            order_id: Order identifier

        Returns:
            Order data or None if not found
        """
        try:
            redis = self._get_redis()
            key = self.ORDER_KEY_PATTERN.format(order_id=order_id)
            data = redis.get(key)

            if data:
                order_data = json.loads(data)
                return PaperOrder(**order_data)
            return None

        except Exception as e:
            logger.error(f"Failed to get order {order_id}: {e}")
            return None

    def get_orders(
        self,
        symbol: str | None = None,
        state: OrderState | None = None,
        limit: int = 100,
    ) -> list[PaperOrder]:
        """Get orders with optional filtering.

        Args:
            symbol: Optional symbol filter
            state: Optional state filter
            limit: Maximum number of orders to return

        Returns:
            List of orders
        """
        try:
            redis = self._get_redis()

            # Get all order keys from index
            order_keys = redis.zrevrange(self.ORDERS_INDEX_KEY, 0, limit - 1)

            orders = []
            for key in order_keys:
                data = redis.get(key)
                if data:
                    order_data = json.loads(data)

                    # Apply filters
                    if symbol and order_data.get("symbol") != symbol.upper():
                        continue
                    if state and order_data.get("state") != state.value:
                        continue

                    orders.append(PaperOrder(**order_data))

            return orders

        except Exception as e:
            logger.error(f"Failed to get orders: {e}")
            return []

    def save_order(self, order: PaperOrder) -> bool:
        """Save an order.

        Args:
            order: Order to save

        Returns:
            True if saved successfully
        """
        try:
            redis = self._get_redis()
            key = self.ORDER_KEY_PATTERN.format(order_id=order.order_id)

            # Update timestamp
            order.updated_at = datetime.now(UTC)

            # Save order
            redis.set(key, json.dumps(order.to_dict()))
            redis.expire(key, self.ttl_seconds)

            # Add to time-ordered index
            timestamp = datetime.now(UTC).timestamp()
            redis.zadd(self.ORDERS_INDEX_KEY, {key: timestamp})
            redis.expire(self.ORDERS_INDEX_KEY, self.ttl_seconds)

            logger.debug(f"Saved order: {key}")
            return True

        except Exception as e:
            logger.error(f"Failed to save order: {e}")
            return False

    def update_order_state(
        self,
        order_id: str,
        state: OrderState,
        filled_quantity: float | None = None,
        avg_fill_price: float | None = None,
    ) -> bool:
        """Update order state.

        Args:
            order_id: Order identifier
            state: New order state
            filled_quantity: Optional filled quantity
            avg_fill_price: Optional average fill price

        Returns:
            True if updated successfully
        """
        try:
            order = self.get_order(order_id)
            if not order:
                logger.warning(f"Order not found: {order_id}")
                return False

            order.state = state
            if filled_quantity is not None:
                order.filled_quantity = filled_quantity
            if avg_fill_price is not None:
                order.avg_fill_price = avg_fill_price

            return self.save_order(order)

        except Exception as e:
            logger.error(f"Failed to update order state: {e}")
            return False

    # PnL methods

    def get_pnl(self) -> PaperPnL:
        """Get PnL metrics.

        Returns:
            PnL metrics
        """
        try:
            redis = self._get_redis()
            key = self.PNL_KEY.format(portfolio_id=self.portfolio_id)
            data = redis.get(key)

            if data:
                pnl_data = json.loads(data)
                return PaperPnL(**pnl_data)

            # Return default PnL if not found
            return PaperPnL()

        except Exception as e:
            logger.error(f"Failed to get PnL: {e}")
            return PaperPnL()

    def save_pnl(self, pnl: PaperPnL) -> bool:
        """Save PnL metrics.

        Args:
            pnl: PnL metrics to save

        Returns:
            True if saved successfully
        """
        try:
            redis = self._get_redis()
            key = self.PNL_KEY.format(portfolio_id=self.portfolio_id)

            redis.set(key, json.dumps(pnl.to_dict()))
            redis.expire(key, self.ttl_seconds)

            logger.debug(f"Saved PnL: {key}")
            return True

        except Exception as e:
            logger.error(f"Failed to save PnL: {e}")
            return False

    def calculate_pnl(self) -> PaperPnL:
        """Calculate PnL from positions and orders.

        Returns:
            Calculated PnL metrics
        """
        try:
            positions = self.get_all_positions()
            orders = self.get_orders(limit=1000)

            total_unrealized = sum(p.unrealized_pnl for p in positions)
            total_realized = sum(p.realized_pnl for p in positions)

            # Calculate trade statistics from filled orders
            filled_orders = [o for o in orders if o.state == OrderState.FILLED]

            # Simple PnL calculation (would be more complex in production)
            pnl = PaperPnL(
                total_realized_pnl=total_realized,
                total_unrealized_pnl=total_unrealized,
                total_pnl=total_realized + total_unrealized,
                total_trades=len(filled_orders),
                period_start=datetime.now(UTC),
                period_end=datetime.now(UTC),
            )

            return pnl

        except Exception as e:
            logger.error(f"Failed to calculate PnL: {e}")
            return PaperPnL()

    # Portfolio methods

    def get_portfolio(self) -> PaperPortfolio:
        """Get portfolio summary.

        Returns:
            Portfolio summary
        """
        try:
            redis = self._get_redis()
            key = self.PORTFOLIO_KEY.format(portfolio_id=self.portfolio_id)
            data = redis.get(key)

            if data:
                portfolio_data = json.loads(data)
                return PaperPortfolio(**portfolio_data)

            # Return default portfolio if not found
            return PaperPortfolio(
                portfolio_id=self.portfolio_id,
                balance=10000.0,  # Default starting balance
                equity=10000.0,
                margin_available=10000.0,
            )

        except Exception as e:
            logger.error(f"Failed to get portfolio: {e}")
            return PaperPortfolio(
                portfolio_id=self.portfolio_id,
                balance=10000.0,
                equity=10000.0,
                margin_available=10000.0,
            )

    def save_portfolio(self, portfolio: PaperPortfolio) -> bool:
        """Save portfolio summary.

        Args:
            portfolio: Portfolio to save

        Returns:
            True if saved successfully
        """
        try:
            redis = self._get_redis()
            key = self.PORTFOLIO_KEY.format(portfolio_id=self.portfolio_id)

            portfolio.updated_at = datetime.now(UTC)

            redis.set(key, json.dumps(portfolio.to_dict()))
            redis.expire(key, self.ttl_seconds)

            logger.debug(f"Saved portfolio: {key}")
            return True

        except Exception as e:
            logger.error(f"Failed to save portfolio: {e}")
            return False

    def get_stats(self) -> dict[str, Any]:
        """Get tracker statistics.

        Returns:
            Dictionary with statistics
        """
        try:
            redis = self._get_redis()

            return {
                "portfolio_id": self.portfolio_id,
                "position_count": redis.scard(self.POSITIONS_INDEX_KEY),
                "order_count": redis.zcard(self.ORDERS_INDEX_KEY),
                "ttl_seconds": self.ttl_seconds,
            }

        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {
                "portfolio_id": self.portfolio_id,
                "error": str(e),
            }
