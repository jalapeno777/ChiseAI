"""
Redis storage implementation for zone persistence.

Uses sorted sets for indexing and hashes for zone data storage.
Key patterns:
    - zones:index:{token}:{timeframe} - Sorted set of zone UUIDs by creation time
    - zones:data:{uuid} - Hash containing zone data
"""

import json
from datetime import datetime
from typing import Optional
from uuid import UUID

import redis

from src.market_analysis.zones.zone_models import Zone, ZoneStatus


class ZoneRedisStorage:
    """Redis storage handler for zones using sorted sets + hashes."""

    # Key patterns
    INDEX_KEY_PATTERN = "zones:index:{token}:{timeframe}"
    DATA_KEY_PATTERN = "zones:data:{uuid}"

    # Capacity constants
    BYTES_PER_ZONE_ESTIMATE = 600  # Estimated bytes per zone for capacity planning
    DEFAULT_CAPACITY = 1000  # ~600KB / 600 bytes per zone

    def __init__(self, redis_client: redis.Redis):
        """
        Initialize Redis storage.

        Args:
            redis_client: Redis client instance
        """
        self._redis = redis_client

    def _index_key(self, token: str, timeframe: str) -> str:
        """Generate index key for token/timeframe."""
        return self.INDEX_KEY_PATTERN.format(token=token, timeframe=timeframe)

    def _data_key(self, uuid: UUID) -> str:
        """Generate data key for zone UUID."""
        return self.DATA_KEY_PATTERN.format(uuid=str(uuid))

    def save(self, zone: Zone) -> None:
        """
        Save zone to Redis.

        Args:
            zone: Zone to save
        """
        # Save zone data as hash
        data_key = self._data_key(zone.uuid)
        zone_data = zone.to_dict()

        # Convert nested dicts to JSON strings for Redis hash
        zone_data["mitigation_history"] = json.dumps(zone_data["mitigation_history"])
        zone_data["price_range"] = json.dumps(zone_data["price_range"])

        self._redis.hset(data_key, mapping=zone_data)

        # Add to index sorted set (score = Unix timestamp)
        index_key = self._index_key(zone.token, zone.timeframe)
        score = zone.creation_time.timestamp()
        self._redis.zadd(index_key, {str(zone.uuid): score})

    def get(self, uuid: UUID) -> Optional[Zone]:
        """
        Retrieve zone by UUID.

        Args:
            uuid: Zone UUID

        Returns:
            Zone if found, None otherwise
        """
        data_key = self._data_key(uuid)
        data = self._redis.hgetall(data_key)

        if not data:
            return None

        # Parse JSON fields (handle both string and already-parsed for mock compatibility)
        if isinstance(data["mitigation_history"], str):
            data["mitigation_history"] = json.loads(data["mitigation_history"])
        if isinstance(data["price_range"], str):
            data["price_range"] = json.loads(data["price_range"])

        return Zone.from_dict(data)

    def get_by_token_timeframe(
        self, token: str, timeframe: str, status: Optional[ZoneStatus] = None
    ) -> list[Zone]:
        """
        Get all zones for a token/timeframe, optionally filtered by status.

        Args:
            token: Trading pair symbol
            timeframe: Trading timeframe
            status: Optional status filter

        Returns:
            List of zones ordered by creation time (newest first)
        """
        index_key = self._index_key(token, timeframe)

        # Get all UUIDs from sorted set (newest first)
        uuids = self._redis.zrevrange(index_key, 0, -1)

        zones = []
        for uuid_str in uuids:
            zone = self.get(UUID(uuid_str))
            if zone and (status is None or zone.status == status):
                zones.append(zone)

        return zones

    def update(self, zone: Zone) -> None:
        """
        Update existing zone (save handles overwrite).

        Args:
            zone: Zone to update
        """
        self.save(zone)

    def delete(self, uuid: UUID) -> bool:
        """
        Delete zone from Redis.

        Args:
            uuid: Zone UUID

        Returns:
            True if zone was deleted, False if not found
        """
        zone = self.get(uuid)
        if not zone:
            return False

        # Delete data hash
        data_key = self._data_key(uuid)
        self._redis.delete(data_key)

        # Remove from index
        index_key = self._index_key(zone.token, zone.timeframe)
        self._redis.zrem(index_key, str(uuid))

        return True

    def count_by_token_timeframe(self, token: str, timeframe: str) -> int:
        """
        Count zones for a token/timeframe.

        Args:
            token: Trading pair symbol
            timeframe: Trading timeframe

        Returns:
            Number of zones
        """
        index_key = self._index_key(token, timeframe)
        return self._redis.zcard(index_key)

    def calculate_storage_size(self, token: str, timeframe: str) -> int:
        """
        Calculate estimated storage size for zones.

        Args:
            token: Trading pair symbol
            timeframe: Trading timeframe

        Returns:
            Estimated size in bytes
        """
        zones = self.get_by_token_timeframe(token, timeframe)
        return len(zones) * self.BYTES_PER_ZONE_ESTIMATE

    def get_capacity_info(self, token: str, timeframe: str) -> dict:
        """
        Get capacity information for token/timeframe.

        Args:
            token: Trading pair symbol
            timeframe: Trading timeframe

        Returns:
            Dict with zone_count, estimated_size_bytes, estimated_size_kb
        """
        zones = self.get_by_token_timeframe(token, timeframe)
        zone_count = len(zones)
        estimated_bytes = zone_count * self.BYTES_PER_ZONE_ESTIMATE

        return {
            "zone_count": zone_count,
            "estimated_size_bytes": estimated_bytes,
            "estimated_size_kb": estimated_bytes / 1024,
            "capacity_check": "OK"
            if estimated_bytes < 614400
            else "NEEDS_CLEANUP",  # 600KB
        }
