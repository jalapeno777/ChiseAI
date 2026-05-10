"""Redis persistence for paper trading positions.

Provides durable storage for position state to survive process restarts.
Part of EP-ICT-006 Phase A remediation.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from redis.asyncio import Redis

if TYPE_CHECKING:
    from .position_tracker import PaperPosition

logger = logging.getLogger(__name__)


class PositionPersistence:
    """Manages Redis persistence for paper trading positions."""

    def __init__(self, redis_client: Redis | None = None) -> None:
        """Initialize persistence manager.

        Args:
            redis_client: Optional Redis client (creates default if None)
        """
        self._provided_redis = redis_client
        self.__redis_client: Redis | None = None
        self._key_prefix = "paper:position:"

    @property
    def _redis(self) -> Redis:
        """Lazy Redis client initialization."""
        if self.__redis_client is None:
            if self._provided_redis is not None:
                self.__redis_client = self._provided_redis
            else:
                self.__redis_client = self._create_default_redis()
        return self.__redis_client

    def _create_default_redis(self) -> Redis:
        """Create default Redis client using centralized redis_config."""
        from .redis_config import REDIS_HOST, REDIS_PORT

        return Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            decode_responses=True,
        )

    async def persist_position(self, position: PaperPosition) -> None:
        """Persist a position to Redis.

        Args:
            position: Position to persist
        """
        if position.is_open:
            # Open positions use primary key
            key = f"{self._key_prefix}{position.position_id}"
            # Clean up any stale closed key if position is reopened
            closed_key = f"{self._key_prefix}closed:{position.position_id}"
            await self._redis.delete(closed_key)
        else:
            # Closed positions use separate key to preserve open state for recovery
            key = f"{self._key_prefix}closed:{position.position_id}"
            # CRITICAL FIX: Delete stale open key when closing a position
            # This prevents stale open-key resurrection bug
            open_key = f"{self._key_prefix}{position.position_id}"
            await self._redis.delete(open_key)
        data = self._serialize_position(position)
        await self._redis.set(key, json.dumps(data))
        logger.debug(
            f"Persisted position {position.position_id} (open={position.is_open})"
        )

    async def remove_position(self, position_id: str) -> None:
        """Remove a position from Redis.

        Args:
            position_id: Position ID to remove
        """
        # Delete both open and closed keys if they exist
        # This ensures clean removal regardless of position state
        open_key = f"{self._key_prefix}{position_id}"
        closed_key = f"{self._key_prefix}closed:{position_id}"
        await self._redis.delete(open_key, closed_key)
        logger.debug(f"Removed position {position_id} from persistence")

    async def load_all_positions(self) -> list[PaperPosition]:
        """Load all persisted positions from Redis.

        Returns:
            List of positions from Redis
        """
        positions = []
        cursor = 0
        # Match both open positions (paper:position:*) and closed positions (paper:position:closed:*)
        pattern = f"{self._key_prefix}*"

        while True:
            cursor, keys = await self._redis.scan(cursor, match=pattern, count=100)
            if keys:
                for key in keys:
                    data = await self._redis.get(key)
                    if data:
                        position = self._deserialize_position(json.loads(data))
                        positions.append(position)
            if cursor == 0:
                break

        logger.info(f"Loaded {len(positions)} positions from Redis persistence")
        return positions

    def _serialize_position(self, position: PaperPosition) -> dict[str, Any]:
        """Serialize position to dictionary."""
        return {
            "position_id": position.position_id,
            "symbol": position.symbol,
            "side": position.side,
            "entry_price": position.entry_price,
            "quantity": position.quantity,
            "unrealized_pnl": position.unrealized_pnl,
            "realized_pnl": position.realized_pnl,
            "opened_at": position.opened_at.isoformat() if position.opened_at else None,
            "closed_at": position.closed_at.isoformat() if position.closed_at else None,
            "metadata": position.metadata,
            "entry_fees": position.entry_fees,
            "exit_fees": position.exit_fees,
            "is_open": position.is_open,
        }

    def _deserialize_position(self, data: dict[str, Any]) -> PaperPosition:
        """Deserialize dictionary to PaperPosition."""
        from datetime import UTC, datetime

        from .position_tracker import PaperPosition

        opened_at = None
        if data.get("opened_at"):
            opened_at = datetime.fromisoformat(data["opened_at"])
        else:
            opened_at = datetime.now(UTC)

        closed_at = None
        if data.get("closed_at"):
            closed_at = datetime.fromisoformat(data["closed_at"])

        position = PaperPosition(
            position_id=data["position_id"],
            symbol=data["symbol"],
            side=data["side"],
            entry_price=data["entry_price"],
            quantity=data["quantity"],
            unrealized_pnl=data.get("unrealized_pnl", 0.0),
            realized_pnl=data.get("realized_pnl", 0.0),
            opened_at=opened_at,
            closed_at=closed_at,
            metadata=data.get("metadata", {}),
            entry_fees=data.get("entry_fees", 0.0),
            exit_fees=data.get("exit_fees", 0.0),
        )

        return position
