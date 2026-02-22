"""Storage backends for calibration data.

This module provides storage implementations for calibration records,
including Redis time-series storage and an in-memory fallback.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

from ml.calibration.models import CalibrationConfig, CalibrationRecord, SignalType

logger = logging.getLogger(__name__)


class CalibrationStorage(ABC):
    """Abstract base class for calibration data storage.

        Implementations must provide methods to store, retrieve, and query
    calibration records efficiently.
    """

    @abstractmethod
    async def store(self, record: CalibrationRecord) -> bool:
        """Store a calibration record.

        Args:
            record: CalibrationRecord to store

        Returns:
            True if stored successfully
        """
        ...

    @abstractmethod
    async def store_batch(self, records: Sequence[CalibrationRecord]) -> int:
        """Store multiple calibration records.

        Args:
            records: List of CalibrationRecords to store

        Returns:
            Number of successfully stored records
        """
        ...

    @abstractmethod
    async def get_records(
        self,
        start_time: datetime,
        end_time: datetime,
        signal_type: SignalType | None = None,
        limit: int = 10000,
    ) -> list[CalibrationRecord]:
        """Get calibration records within a time range.

        Args:
            start_time: Start of time range (inclusive)
            end_time: End of time range (inclusive)
            signal_type: Optional signal type filter
            limit: Maximum number of records to return

        Returns:
            List of CalibrationRecord objects
        """
        ...

    @abstractmethod
    async def get_records_by_signal_type(
        self,
        signal_type: SignalType,
        start_time: datetime,
        end_time: datetime,
        limit: int = 10000,
    ) -> list[CalibrationRecord]:
        """Get calibration records for a specific signal type.

        Args:
            signal_type: Signal type to filter by
            start_time: Start of time range
            end_time: End of time range
            limit: Maximum number of records

        Returns:
            List of CalibrationRecord objects
        """
        ...

    @abstractmethod
    async def delete_old_records(self, before: datetime) -> int:
        """Delete records older than the specified time.

        Args:
            before: Delete records before this time

        Returns:
            Number of deleted records
        """
        ...

    @abstractmethod
    async def get_record_count(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> int:
        """Get the total count of records.

        Args:
            start_time: Optional start time filter
            end_time: Optional end time filter

        Returns:
            Number of records
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close the storage connection and release resources."""
        ...


class InMemoryCalibrationStorage(CalibrationStorage):
    """In-memory storage for calibration data.

    Useful for testing and as a fallback when Redis is unavailable.
    Data is not persisted across restarts.
    """

    def __init__(self, config: CalibrationConfig | None = None):
        """Initialize in-memory storage.

        Args:
            config: Optional configuration
        """
        self.config = config or CalibrationConfig()
        self._records: list[CalibrationRecord] = []
        self._closed = False

    async def store(self, record: CalibrationRecord) -> bool:
        """Store a calibration record in memory."""
        if self._closed:
            logger.warning("Storage is closed, cannot store record")
            return False

        self._records.append(record)
        return True

    async def store_batch(self, records: Sequence[CalibrationRecord]) -> int:
        """Store multiple calibration records in memory."""
        if self._closed:
            logger.warning("Storage is closed, cannot store records")
            return 0

        self._records.extend(records)
        return len(records)

    async def get_records(
        self,
        start_time: datetime,
        end_time: datetime,
        signal_type: SignalType | None = None,
        limit: int = 10000,
    ) -> list[CalibrationRecord]:
        """Get calibration records from memory."""
        filtered = [
            r
            for r in self._records
            if start_time <= r.timestamp <= end_time
            and (signal_type is None or r.signal_type == signal_type)
        ]
        return filtered[:limit]

    async def get_records_by_signal_type(
        self,
        signal_type: SignalType,
        start_time: datetime,
        end_time: datetime,
        limit: int = 10000,
    ) -> list[CalibrationRecord]:
        """Get calibration records for a specific signal type from memory."""
        return await self.get_records(start_time, end_time, signal_type, limit)

    async def delete_old_records(self, before: datetime) -> int:
        """Delete old records from memory."""
        original_count = len(self._records)
        self._records = [r for r in self._records if r.timestamp >= before]
        return original_count - len(self._records)

    async def get_record_count(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> int:
        """Get the count of records in memory."""
        if start_time is None and end_time is None:
            return len(self._records)

        filtered = self._records
        if start_time:
            filtered = [r for r in filtered if r.timestamp >= start_time]
        if end_time:
            filtered = [r for r in filtered if r.timestamp <= end_time]
        return len(filtered)

    async def close(self) -> None:
        """Close the storage and clear records."""
        self._closed = True
        self._records.clear()

    def clear(self) -> None:
        """Clear all records (for testing)."""
        self._records.clear()

    def get_all_records(self) -> list[CalibrationRecord]:
        """Get all records (for testing)."""
        return self._records.copy()


class RedisCalibrationStorage(CalibrationStorage):
    """Redis-based storage for calibration data.

    Uses Redis sorted sets for efficient time-series storage and querying.
    Records are stored with timestamps as scores for range queries.

    Schema:
        Key: calibration:{signal_type}:{YYYY-MM-DD}
        Value: JSON-serialized CalibrationRecord
        Score: Unix timestamp (for range queries)
    """

    def __init__(self, config: CalibrationConfig | None = None):
        """Initialize Redis storage.

        Args:
            config: Optional configuration
        """
        self.config = config or CalibrationConfig()
        self._redis_client: Any = None
        self._closed = False

    def _get_redis_client(self) -> Any:
        """Get or create Redis client.

        Returns:
            Redis client instance
        """
        if self._redis_client is None:
            try:
                import redis

                self._redis_client = redis.Redis(
                    host=self.config.redis_host,
                    port=self.config.redis_port,
                    db=self.config.redis_db,
                    decode_responses=True,
                )
                # Test connection
                self._redis_client.ping()
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}")
                raise

        return self._redis_client

    def _get_key(self, record: CalibrationRecord) -> str:
        """Generate Redis key for a record.

        Args:
            record: CalibrationRecord

        Returns:
            Redis key string
        """
        date_str = record.timestamp.strftime("%Y-%m-%d")
        return self.config.get_redis_key(record.signal_type, date_str)

    def _get_keys_for_range(
        self, start_time: datetime, end_time: datetime, signal_type: SignalType | None
    ) -> list[str]:
        """Generate Redis keys for a time range.

        Args:
            start_time: Start of time range
            end_time: End of time range
            signal_type: Optional signal type filter

        Returns:
            List of Redis keys to query
        """
        keys = []
        current = start_time.date()
        end = end_time.date()

        # Generate keys for each day in the range
        while current <= end:
            date_str = current.strftime("%Y-%m-%d")
            if signal_type:
                keys.append(self.config.get_redis_key(signal_type, date_str))
            else:
                # Query all signal types
                for st in SignalType:
                    keys.append(self.config.get_redis_key(st, date_str))
            current += timedelta(days=1)

        return keys

    async def store(self, record: CalibrationRecord) -> bool:
        """Store a calibration record in Redis.

        Args:
            record: CalibrationRecord to store

        Returns:
            True if stored successfully
        """
        if self._closed:
            logger.warning("Storage is closed, cannot store record")
            return False

        try:
            client = self._get_redis_client()
            key = self._get_key(record)
            score = record.timestamp.timestamp()
            value = json.dumps(record.to_dict())

            # Use ZADD for time-series storage
            client.zadd(key, {value: score})

            # Set expiration based on retention config
            expiration_seconds = self.config.retention_days * 86400
            client.expire(key, expiration_seconds)

            logger.debug(f"Stored calibration record {record.signal_id} in Redis")
            return True

        except Exception as e:
            logger.error(f"Failed to store calibration record: {e}")
            return False

    async def store_batch(self, records: Sequence[CalibrationRecord]) -> int:
        """Store multiple calibration records in Redis.

        Args:
            records: List of CalibrationRecords to store

        Returns:
            Number of successfully stored records
        """
        if self._closed:
            logger.warning("Storage is closed, cannot store records")
            return 0

        if not records:
            return 0

        try:
            client = self._get_redis_client()
            pipe = client.pipeline()

            # Group records by key for efficient batching
            records_by_key: dict[str, list[tuple[str, float]]] = {}
            for record in records:
                key = self._get_key(record)
                score = record.timestamp.timestamp()
                value = json.dumps(record.to_dict())

                if key not in records_by_key:
                    records_by_key[key] = []
                records_by_key[key].append((value, score))

            # Add all records to pipeline
            expiration_seconds = self.config.retention_days * 86400
            for key, items in records_by_key.items():
                for value, score in items:
                    pipe.zadd(key, {value: score})
                pipe.expire(key, expiration_seconds)

            # Execute pipeline
            results = pipe.execute()

            # Count successful stores (every other result is ZADD, every other is EXPIRE)
            stored_count = sum(
                1 for i, r in enumerate(results) if i % 2 == 0 and r is not None
            )

            logger.debug(f"Stored batch of {stored_count} calibration records in Redis")
            return stored_count

        except Exception as e:
            logger.error(f"Failed to store calibration batch: {e}")
            return 0

    async def get_records(
        self,
        start_time: datetime,
        end_time: datetime,
        signal_type: SignalType | None = None,
        limit: int = 10000,
    ) -> list[CalibrationRecord]:
        """Get calibration records from Redis.

        Args:
            start_time: Start of time range
            end_time: End of time range
            signal_type: Optional signal type filter
            limit: Maximum number of records

        Returns:
            List of CalibrationRecord objects
        """
        if self._closed:
            logger.warning("Storage is closed, cannot retrieve records")
            return []

        try:
            client = self._get_redis_client()
            keys = self._get_keys_for_range(start_time, end_time, signal_type)

            start_score = start_time.timestamp()
            end_score = end_time.timestamp()

            records = []
            for key in keys:
                # Get records within score range
                results = client.zrangebyscore(
                    key, start_score, end_score, withscores=False
                )

                for result in results:
                    try:
                        data = json.loads(result)
                        record = CalibrationRecord.from_dict(data)
                        records.append(record)

                        if len(records) >= limit:
                            break
                    except (json.JSONDecodeError, KeyError, ValueError) as e:
                        logger.warning(f"Failed to parse calibration record: {e}")
                        continue

                if len(records) >= limit:
                    break

            return records[:limit]

        except Exception as e:
            logger.error(f"Failed to retrieve calibration records: {e}")
            return []

    async def get_records_by_signal_type(
        self,
        signal_type: SignalType,
        start_time: datetime,
        end_time: datetime,
        limit: int = 10000,
    ) -> list[CalibrationRecord]:
        """Get calibration records for a specific signal type from Redis."""
        return await self.get_records(start_time, end_time, signal_type, limit)

    async def delete_old_records(self, before: datetime) -> int:
        """Delete records older than the specified time.

        Args:
            before: Delete records before this time

        Returns:
            Number of deleted records
        """
        if self._closed:
            logger.warning("Storage is closed, cannot delete records")
            return 0

        try:
            client = self._get_redis_client()

            # Scan for all calibration keys
            pattern = f"{self.config.key_prefix}:*"
            keys = []
            cursor = 0

            while True:
                cursor, batch = client.scan(cursor=cursor, match=pattern, count=100)
                keys.extend(batch)
                if cursor == 0:
                    break

            # Remove records older than 'before' from each key
            before_score = before.timestamp()
            deleted_count = 0

            for key in keys:
                # Get count before deletion
                client.zcard(key)
                # Remove records with score < before_score
                removed = client.zremrangebyscore(key, 0, before_score)
                deleted_count += removed

                # If key is now empty, delete it
                if client.zcard(key) == 0:
                    client.delete(key)

            return deleted_count

        except Exception as e:
            logger.error(f"Failed to delete old calibration records: {e}")
            return 0

    async def get_record_count(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> int:
        """Get the total count of records in Redis.

        Args:
            start_time: Optional start time filter
            end_time: Optional end time filter

        Returns:
            Number of records
        """
        if self._closed:
            logger.warning("Storage is closed, cannot count records")
            return 0

        try:
            client = self._get_redis_client()

            # Scan for all calibration keys
            pattern = f"{self.config.key_prefix}:*"
            keys = []
            cursor = 0

            while True:
                cursor, batch = client.scan(cursor=cursor, match=pattern, count=100)
                keys.extend(batch)
                if cursor == 0:
                    break

            if start_time is None and end_time is None:
                # Simple count of all records
                pipe = client.pipeline()
                for key in keys:
                    pipe.zcard(key)
                counts = pipe.execute()
                return sum(counts)
            else:
                # Count within time range
                start_score = start_time.timestamp() if start_time else 0
                end_score = end_time.timestamp() if end_time else float("inf")

                total = 0
                for key in keys:
                    count = client.zcount(key, start_score, end_score)
                    total += count
                return total

        except Exception as e:
            logger.error(f"Failed to count calibration records: {e}")
            return 0

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._redis_client:
            try:
                self._redis_client.close()
            except Exception as e:
                logger.warning(f"Error closing Redis connection: {e}")
            finally:
                self._redis_client = None

        self._closed = True
