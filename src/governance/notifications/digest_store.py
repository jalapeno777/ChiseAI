"""Redis-backed digest event storage with in-memory fallback.

Provides durable storage for digest-queued events so they survive process restart.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# Redis key patterns
REDIS_QUEUE_KEY = "chise:governance:notifications:digest_queue"
REDIS_SENT_KEY_PREFIX = "chise:governance:notifications:digest:sent:"
FEATURE_FLAG_KEY = "chise:feature_flags:governance:durable_digest_enabled"

# TTL constants
QUEUE_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days
SENT_TTL_SECONDS = 24 * 60 * 60  # 24 hours


def _get_redis_client():
    """Get Redis client with graceful fallback."""
    try:
        from tools.redis_state import (
            redis_state_delete,
            redis_state_expire,
            redis_state_get,
            redis_state_lrange,
            redis_state_rpush,
            redis_state_set,
        )

        return {
            "delete": redis_state_delete,
            "expire": redis_state_expire,
            "get": redis_state_get,
            "lrange": redis_state_lrange,
            "rpush": redis_state_rpush,
            "set": redis_state_set,
        }
    except ImportError:
        return None


class DigestStore:
    """Redis-backed digest event storage with in-memory fallback.

    Uses Redis list as queue with JSON-serialized event blobs.
    Duplicate guard uses event_id with sent key prefix.
    """

    def __init__(self):
        self._redis = _get_redis_client()
        self._memory_buffer: list[dict[str, Any]] = []

    def is_enabled(self) -> bool:
        """Check if durable digest is enabled via feature flag."""
        if self._redis is None:
            return False
        try:
            from tools.redis_state import redis_state_hget

            flag = redis_state_hget(FEATURE_FLAG_KEY, "durable_digest_enabled")
            if flag is None:
                return True  # Default enabled
            return flag.lower() in ("true", "1", "yes", "on")
        except Exception as e:
            logger.warning(f"Failed to read feature flag: {e}")
            return True

    def enqueue(self, event: dict[str, Any]) -> bool:
        """Add event to the digest queue.

        Args:
            event: Event dict to buffer for digest delivery

        Returns:
            True if persisted successfully (Redis or memory)
        """
        event_id = event.get("event_id", f"evt-{len(self._memory_buffer)}")
        event["_queued_at"] = datetime.now().isoformat()

        if self._redis is not None and self.is_enabled():
            try:
                redis_state_rpush = self._redis["rpush"]
                redis_state_expire = self._redis["expire"]

                redis_state_rpush(REDIS_QUEUE_KEY, json.dumps(event))
                redis_state_expire(REDIS_QUEUE_KEY, QUEUE_TTL_SECONDS)
                logger.debug(f"Enqueued event to Redis: {event_id}")
                return True
            except Exception as e:
                logger.warning(f"Redis enqueue failed, using memory: {e}")

        # Fallback to memory
        self._memory_buffer.append(event)
        logger.debug(f"Enqueued event to memory buffer: {event_id}")
        return True

    def dequeue_all(self) -> list[dict[str, Any]]:
        """Get and remove all events from the queue.

        Returns:
            List of queued events (Redis first, then memory buffer)
        """
        events = []

        if self._redis is not None and self.is_enabled():
            try:
                redis_state_lrange = self._redis["lrange"]
                redis_state_delete = self._redis["delete"]

                raw_events = redis_state_lrange(REDIS_QUEUE_KEY, 0, -1)
                for raw in raw_events:
                    try:
                        events.append(json.loads(raw))
                    except (json.JSONDecodeError, TypeError):
                        logger.warning(f"Failed to decode event: {raw}")

                # Clear Redis queue after reading
                if raw_events:
                    redis_state_delete(REDIS_QUEUE_KEY)
                    logger.debug(f"Dequeued {len(events)} events from Redis")
            except Exception as e:
                logger.warning(f"Redis dequeue failed: {e}")

        # Always also return memory buffer events (don't clear until sent)
        if self._memory_buffer:
            events.extend(self._memory_buffer)
            logger.debug(
                f"Including {len(self._memory_buffer)} events from memory buffer"
            )

        return events

    def mark_sent(self, event_id: str) -> None:
        """Mark event as sent to prevent duplicate delivery.

        Args:
            event_id: The event_id to mark as sent
        """
        if self._redis is not None:
            try:
                redis_state_set = self._redis["set"]
                redis_state_expire = self._redis["expire"]

                key = f"{REDIS_SENT_KEY_PREFIX}{event_id}"
                redis_state_set(key, "1")
                redis_state_expire(key, SENT_TTL_SECONDS)
                logger.debug(f"Marked event as sent: {event_id}")
            except Exception as e:
                logger.warning(f"Failed to mark sent in Redis: {e}")

    def is_sent(self, event_id: str) -> bool:
        """Check if event was already sent.

        Args:
            event_id: The event_id to check

        Returns:
            True if event was already sent
        """
        if self._redis is None:
            return False
        try:
            redis_state_get = self._redis["get"]

            key = f"{REDIS_SENT_KEY_PREFIX}{event_id}"
            return redis_state_get(key) is not None
        except Exception as e:
            logger.warning(f"Failed to check sent status: {e}")
            return False

    def count(self) -> int:
        """Get number of events in the queue.

        Returns:
            Total event count (Redis + memory)
        """
        total = 0

        if self._redis is not None and self.is_enabled():
            try:
                redis_state_lrange = self._redis["lrange"]

                raw_events = redis_state_lrange(REDIS_QUEUE_KEY, 0, -1)
                total = len(raw_events)
            except Exception as e:
                logger.warning(f"Failed to get Redis count: {e}")

        total += len(self._memory_buffer)
        return total

    def reload(self) -> list[dict[str, Any]]:
        """Reload events from Redis into memory buffer.

        Called on startup to recover events from Redis after restart.

        Returns:
            List of recovered events
        """
        if self._redis is None or not self.is_enabled():
            return []

        try:
            redis_state_lrange = self._redis["lrange"]

            raw_events = redis_state_lrange(REDIS_QUEUE_KEY, 0, -1)
            recovered = []
            for raw in raw_events:
                try:
                    event = json.loads(raw)
                    recovered.append(event)
                    self._memory_buffer.append(event)
                except (json.JSONDecodeError, TypeError):
                    logger.warning(f"Failed to decode event during reload: {raw}")

            if recovered:
                logger.info(f"Recovered {len(recovered)} events from Redis on startup")

            return recovered
        except Exception as e:
            logger.warning(f"Failed to reload from Redis: {e}")
            return []

    def clear_memory(self) -> None:
        """Clear the memory buffer (called after successful send)."""
        self._memory_buffer.clear()
