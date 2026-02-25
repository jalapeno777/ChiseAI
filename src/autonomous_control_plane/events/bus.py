"""Event bus for the autonomous control plane.

Provides Redis-backed Pub/Sub messaging for inter-component communication
with graceful fallback to in-memory event handling when Redis is unavailable.

EP-NS-008: Autonomous Control Plane
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from autonomous_control_plane.config.settings import settings

if TYPE_CHECKING:
    import redis

logger = logging.getLogger(__name__)


class EventPriority(Enum):
    """Event priority levels."""

    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3


@dataclass
class Event:
    """An event in the ACP event bus."""

    event_type: str
    payload: dict[str, Any]
    source: str = "acp"
    priority: EventPriority = EventPriority.NORMAL
    timestamp: float = field(default_factory=time.time)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert event to dictionary."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "source": self.source,
            "priority": self.priority.value,
            "timestamp": self.timestamp,
            "correlation_id": self.correlation_id,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Event:
        """Create event from dictionary."""
        return cls(
            event_id=data["event_id"],
            event_type=data["event_type"],
            source=data.get("source", "acp"),
            priority=EventPriority(data.get("priority", 2)),
            timestamp=data["timestamp"],
            correlation_id=data.get("correlation_id"),
            payload=data.get("payload", {}),
        )

    def to_json(self) -> str:
        """Serialize event to JSON."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_str: str) -> Event:
        """Deserialize event from JSON."""
        return cls.from_dict(json.loads(json_str))


# Type alias for event handlers
EventHandler = Callable[[Event], None]


class EventBus:
    """Event bus with Redis Pub/Sub and in-memory fallback.

    Provides reliable event distribution across ACP components with
    automatic fallback to in-memory handling when Redis is unavailable.

    Example:
        >>> bus = EventBus()
        >>> bus.start()
        >>> bus.subscribe("circuit_breaker.open", handler)
        >>> bus.publish(Event("circuit_breaker.open", {"service": "redis"}))
    """

    _instance: EventBus | None = None
    _lock = threading.Lock()

    def __new__(cls, redis_client: redis.Redis | None = None) -> EventBus:
        """Singleton pattern for global event bus access."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._initialized = False
                    instance._pending_redis = redis_client
                    cls._instance = instance
        return cls._instance

    def __init__(self, redis_client: redis.Redis | None = None):
        """Initialize the event bus.

        Args:
            redis_client: Optional Redis client (creates new if not provided)
        """
        if self._initialized:
            return

        self._initialized = True
        self._redis = getattr(self, "_pending_redis", None) or redis_client
        self._pubsub = None

        # In-memory fallback
        self._handlers: dict[str, list[EventHandler]] = {}
        self._global_handlers: list[EventHandler] = []
        self._lock = threading.RLock()

        # Connection state
        self._redis_connected = False
        self._running = False

        # Background thread for Redis pub/sub
        self._listener_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

        # Channel prefix for namespacing
        self._channel_prefix = "acp:events:"

    def _get_channel(self, event_type: str) -> str:
        """Get Redis channel name for event type."""
        return f"{self._channel_prefix}{event_type}"

    def _connect_redis(self) -> bool:
        """Establish Redis connection.

        Returns:
            True if connection successful, False otherwise
        """
        if self._redis is not None:
            try:
                self._redis.ping()
                self._redis_connected = True
                return True
            except Exception:
                pass

        try:
            import redis as redis_lib

            self._redis = redis_lib.Redis(
                host=settings.redis.host,
                port=settings.redis.port,
                db=settings.redis.db,
                password=settings.redis.password,
                socket_timeout=settings.redis.socket_timeout,
                socket_connect_timeout=settings.redis.socket_connect_timeout,
                decode_responses=True,
            )
            self._redis.ping()
            self._redis_connected = True
            logger.info(
                f"EventBus: Redis connected to {settings.redis.host}:{settings.redis.port}"
            )
            return True

        except Exception as e:
            logger.warning(
                f"EventBus: Redis connection failed - {e}. Running in in-memory mode."
            )
            self._redis = None
            self._redis_connected = False
            return False

    def start(self) -> None:
        """Start the event bus."""
        with self._lock:
            if self._running:
                logger.warning("EventBus: Already running")
                return

            self._running = True
            self._stop_event.clear()

            # Try to connect to Redis
            if self._connect_redis():
                # Start Redis pub/sub listener
                self._start_redis_listener()

            logger.info("EventBus: Started")

    def _start_redis_listener(self) -> None:
        """Start the Redis pub/sub listener thread."""
        if self._redis is None or not self._redis_connected:
            return

        try:
            self._pubsub = self._redis.pubsub()
            self._listener_thread = threading.Thread(
                target=self._redis_listener_loop,
                name="EventBus-RedisListener",
                daemon=True,
            )
            self._listener_thread.start()
            logger.info("EventBus: Redis pub/sub listener started")
        except Exception as e:
            logger.warning(f"EventBus: Failed to start Redis listener - {e}")
            self._redis_connected = False

    def _redis_listener_loop(self) -> None:
        """Background loop for Redis pub/sub messages."""
        if self._pubsub is None:
            return

        try:
            for message in self._pubsub.listen():
                if self._stop_event.is_set():
                    break

                if message["type"] == "message":
                    try:
                        event = Event.from_json(message["data"])
                        self._dispatch_local(event)
                    except Exception as e:
                        logger.warning(f"EventBus: Failed to process message - {e}")

        except Exception as e:
            logger.warning(f"EventBus: Redis listener error - {e}")
            self._redis_connected = False

    def stop(self) -> None:
        """Stop the event bus."""
        with self._lock:
            if not self._running:
                return

            self._stop_event.set()
            self._running = False

            # Stop Redis pub/sub
            if self._pubsub is not None:
                try:
                    self._pubsub.unsubscribe()
                    self._pubsub.close()
                except Exception as e:
                    logger.warning(f"EventBus: Error closing pub/sub - {e}")
                finally:
                    self._pubsub = None

            # Wait for listener thread
            if self._listener_thread and self._listener_thread.is_alive():
                self._listener_thread.join(timeout=2.0)

            # Close Redis connection
            if self._redis is not None:
                try:
                    self._redis.close()
                except Exception as e:
                    logger.warning(f"EventBus: Error closing Redis - {e}")
                finally:
                    self._redis = None
                    self._redis_connected = False

            logger.info("EventBus: Stopped")

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Subscribe to events of a specific type.

        Args:
            event_type: Type of event to subscribe to
            handler: Callable that receives Event objects
        """
        with self._lock:
            if event_type not in self._handlers:
                self._handlers[event_type] = []
                # Subscribe to Redis channel if connected
                if self._redis_connected and self._pubsub is not None:
                    try:
                        channel = self._get_channel(event_type)
                        self._pubsub.subscribe(channel)
                        logger.debug(
                            f"EventBus: Subscribed to Redis channel '{channel}'"
                        )
                    except Exception as e:
                        logger.warning(f"EventBus: Failed to subscribe to Redis - {e}")

            self._handlers[event_type].append(handler)
            logger.debug(f"EventBus: Handler registered for '{event_type}'")

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """Unsubscribe a handler from an event type.

        Args:
            event_type: Type of event
            handler: Handler to remove
        """
        with self._lock:
            if event_type in self._handlers:
                if handler in self._handlers[event_type]:
                    self._handlers[event_type].remove(handler)
                    logger.debug(f"EventBus: Handler removed from '{event_type}'")

                # Unsubscribe from Redis if no more handlers
                if (
                    not self._handlers[event_type]
                    and self._redis_connected
                    and self._pubsub is not None
                ):
                    try:
                        channel = self._get_channel(event_type)
                        self._pubsub.unsubscribe(channel)
                        logger.debug(
                            f"EventBus: Unsubscribed from Redis channel '{channel}'"
                        )
                    except Exception as e:
                        logger.warning(
                            f"EventBus: Failed to unsubscribe from Redis - {e}"
                        )

    def subscribe_all(self, handler: EventHandler) -> None:
        """Subscribe to all events.

        Args:
            handler: Callable that receives Event objects
        """
        with self._lock:
            self._global_handlers.append(handler)
            logger.debug("EventBus: Global handler registered")

    def unsubscribe_all(self, handler: EventHandler) -> None:
        """Unsubscribe a global handler.

        Args:
            handler: Handler to remove
        """
        with self._lock:
            if handler in self._global_handlers:
                self._global_handlers.remove(handler)
                logger.debug("EventBus: Global handler removed")

    def publish(self, event: Event) -> None:
        """Publish an event.

        Args:
            event: Event to publish
        """
        # Dispatch locally first
        self._dispatch_local(event)

        # Publish to Redis if connected
        if self._redis_connected and self._redis is not None:
            try:
                channel = self._get_channel(event.event_type)
                self._redis.publish(channel, event.to_json())
                logger.debug(f"EventBus: Published '{event.event_type}' to Redis")
            except Exception as e:
                logger.warning(f"EventBus: Failed to publish to Redis - {e}")

    def _dispatch_local(self, event: Event) -> None:
        """Dispatch event to local handlers."""
        handlers_to_call: list[EventHandler] = []

        with self._lock:
            # Get specific handlers
            if event.event_type in self._handlers:
                handlers_to_call.extend(self._handlers[event.event_type])
            # Get global handlers
            handlers_to_call.extend(self._global_handlers)

        # Call handlers outside of lock to avoid deadlocks
        for handler in handlers_to_call:
            try:
                handler(event)
            except Exception as e:
                logger.warning(
                    f"EventBus: Handler error for '{event.event_type}' - {e}"
                )

    def publish_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        source: str = "acp",
        priority: EventPriority = EventPriority.NORMAL,
        correlation_id: str | None = None,
    ) -> None:
        """Publish an event with simplified interface.

        Args:
            event_type: Type of event
            payload: Event payload data
            source: Event source identifier
            priority: Event priority
            correlation_id: Optional correlation ID for tracing
        """
        event = Event(
            event_type=event_type,
            payload=payload,
            source=source,
            priority=priority,
            correlation_id=correlation_id,
        )
        self.publish(event)

    def health_check(self) -> dict[str, Any]:
        """Get health status of the event bus.

        Returns:
            Dictionary with connection status and metrics
        """
        with self._lock:
            redis_healthy = False
            if self._redis_connected and self._redis is not None:
                try:
                    self._redis.ping()
                    redis_healthy = True
                except Exception:
                    pass

            return {
                "running": self._running,
                "redis_connected": self._redis_connected,
                "redis_healthy": redis_healthy,
                "handler_count": sum(len(h) for h in self._handlers.values()),
                "global_handler_count": len(self._global_handlers),
                "subscribed_event_types": list(self._handlers.keys()),
            }


# Global event bus instance
event_bus = EventBus()
