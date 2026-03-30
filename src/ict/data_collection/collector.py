"""ICT Data Collector.

Collects ICT signal events and correlates them with position outcomes
for experiment analysis.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import redis

logger = logging.getLogger(__name__)


@dataclass
class SignalEvent:
    """A signal event captured by the collector.

    Attributes:
        signal_id: Unique signal identifier
        timestamp: When the signal was generated
        symbol: Trading pair symbol
        signal_type: Type of signal (e.g., "entry", "exit", "stop")
        confidence: Signal confidence score (0.0-1.0)
        context: Additional signal context/metadata
        experiment_key: Associated experiment key
    """

    signal_id: str
    timestamp: datetime
    symbol: str
    signal_type: str
    confidence: float
    context: dict[str, Any] = field(default_factory=dict)
    experiment_key: str | None = None


@dataclass
class OutcomeEvent:
    """A position outcome event for correlation.

    Attributes:
        position_id: Associated position identifier
        signal_id: Signal that triggered the position
        outcome: Outcome type ("profit", "loss", "breakeven")
        pnl: Realized PnL
        timestamp: When outcome was recorded
    """

    position_id: str
    signal_id: str
    outcome: str
    pnl: float
    timestamp: datetime


class ICTDataCollector:
    """Collects ICT signal data and correlates with outcomes.

    This collector:
    - Listens to ICT signal events from the signal generation pipeline
    - Stores signal metadata in Redis with key pattern `ict:data:{experiment_key}:{signal_id}`
    - Tracks signal outcomes by correlating with position events
    - Supports enable/disable via start_collection() / stop_collection()

    Attributes:
        _enabled: Whether collection is active
        _signals: In-memory signal buffer before Redis flush
        _outcomes: In-memory outcome buffer
        _lock: Async lock for thread safety
        _redis: Redis client for persistence
    """

    def __init__(self, redis_client: redis.Redis | None = None) -> None:
        """Initialize the ICT data collector.

        Args:
            redis_client: Optional Redis client. If not provided,
                         creates one from environment or localhost.
        """
        self._enabled = False
        self._signals: list[SignalEvent] = []
        self._outcomes: list[OutcomeEvent] = []
        self._lock = asyncio.Lock()
        self._redis = redis_client
        self._flush_task: asyncio.Task | None = None

        logger.info("ICTDataCollector initialized")

    def _get_redis(self) -> redis.Redis:
        """Get or create Redis client.

        Returns:
            Redis client instance
        """
        if self._redis is None:
            import redis as redis_lib

            host = os.environ.get("REDIS_HOST", "localhost")
            port = int(os.environ.get("REDIS_PORT", "6379"))
            self._redis = redis_lib.Redis(host=host, port=port, decode_responses=False)
        return self._redis

    async def start_collection(self) -> None:
        """Start data collection.

        Enables signal capture and starts background flush task.
        """
        async with self._lock:
            if self._enabled:
                logger.warning("Collection already started")
                return

            self._enabled = True
            self._flush_task = asyncio.create_task(self._flush_loop())

            logger.info("ICT data collection started")

    async def stop_collection(self) -> None:
        """Stop data collection.

        Disables signal capture and flushes remaining data to Redis.
        """
        # Acquire lock only for state changes and task cleanup
        async with self._lock:
            if not self._enabled:
                logger.warning("Collection not started")
                return

            self._enabled = False

            # Cancel flush task
            if self._flush_task:
                self._flush_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._flush_task
                self._flush_task = None

        # Call flush OUTSIDE the lock to avoid deadlock
        # (_flush_to_redis acquires the same lock; asyncio.Lock is not reentrant)
        await self._flush_to_redis()

        logger.info("ICT data collection stopped")

    async def collect_signal(
        self,
        symbol: str,
        signal_type: str,
        confidence: float,
        context: dict[str, Any] | None = None,
        experiment_key: str | None = None,
    ) -> str:
        """Collect a signal event.

        Args:
            symbol: Trading pair symbol
            signal_type: Type of signal
            confidence: Confidence score (0.0-1.0)
            context: Additional context metadata
            experiment_key: Associated experiment key

        Returns:
            Generated signal_id
        """
        signal_id = str(uuid.uuid4())
        event = SignalEvent(
            signal_id=signal_id,
            timestamp=datetime.now(UTC),
            symbol=symbol.upper(),
            signal_type=signal_type,
            confidence=confidence,
            context=context or {},
            experiment_key=experiment_key,
        )

        async with self._lock:
            self._signals.append(event)

        logger.debug(
            f"Collected signal: {signal_id} {symbol} {signal_type} "
            f"confidence={confidence:.2f}"
        )

        return signal_id

    async def record_outcome(
        self,
        position_id: str,
        signal_id: str,
        outcome: str,
        pnl: float,
    ) -> None:
        """Record a position outcome for correlation.

        Args:
            position_id: Associated position ID
            signal_id: Signal that triggered the position
            outcome: Outcome type ("profit", "loss", "breakeven")
            pnl: Realized PnL
        """
        event = OutcomeEvent(
            position_id=position_id,
            signal_id=signal_id,
            outcome=outcome,
            pnl=pnl,
            timestamp=datetime.now(UTC),
        )

        async with self._lock:
            self._outcomes.append(event)

        logger.debug(
            f"Recorded outcome: position={position_id} signal={signal_id} "
            f"outcome={outcome} pnl={pnl:.4f}"
        )

    def is_enabled(self) -> bool:
        """Check if collection is enabled.

        Returns:
            True if collection is active
        """
        return self._enabled

    async def _flush_loop(self) -> None:
        """Background task to periodically flush data to Redis."""
        while True:
            try:
                await asyncio.sleep(5)  # Flush every 5 seconds
                await self._flush_to_redis()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in flush loop: {e}")

    async def _flush_to_redis(self) -> None:
        """Flush buffered signals and outcomes to Redis."""
        async with self._lock:
            if not self._signals and not self._outcomes:
                return

            redis_client = self._get_redis()
            signals_to_flush = self._signals.copy()
            outcomes_to_flush = self._outcomes.copy()
            self._signals.clear()
            self._outcomes.clear()

        # Flush signals
        for signal in signals_to_flush:
            key = f"ict:data:{signal.experiment_key or 'default'}:{signal.signal_id}"
            data = {
                "signal_id": signal.signal_id,
                "timestamp": signal.timestamp.isoformat(),
                "symbol": signal.symbol,
                "signal_type": signal.signal_type,
                "confidence": str(signal.confidence),
                "context": str(signal.context),
                "experiment_key": signal.experiment_key or "",
            }
            try:
                redis_client.hset(key, mapping=data)
                redis_client.expire(key, 86400 * 7)  # 7 day TTL
            except Exception as e:
                logger.error(f"Failed to store signal {signal.signal_id}: {e}")

        # Flush outcomes
        for outcome in outcomes_to_flush:
            key = f"ict:outcome:{outcome.position_id}:{outcome.signal_id}"
            data = {
                "position_id": outcome.position_id,
                "signal_id": outcome.signal_id,
                "outcome": outcome.outcome,
                "pnl": str(outcome.pnl),
                "timestamp": outcome.timestamp.isoformat(),
            }
            try:
                redis_client.hset(key, mapping=data)
                redis_client.expire(key, 86400 * 7)  # 7 day TTL
            except Exception as e:
                logger.error(f"Failed to store outcome {outcome.signal_id}: {e}")

        logger.debug(
            f"Flushed {len(signals_to_flush)} signals and "
            f"{len(outcomes_to_flush)} outcomes to Redis"
        )

    async def get_signal_count(self, experiment_key: str | None = None) -> int:
        """Get count of collected signals.

        Args:
            experiment_key: Optional filter by experiment key

        Returns:
            Number of signals collected
        """
        redis_client = self._get_redis()
        pattern = f"ict:data:{experiment_key or '*'}:*"

        try:
            keys = redis_client.keys(pattern)
            return len(keys)
        except Exception as e:
            logger.error(f"Failed to get signal count: {e}")
            return 0

    async def get_outcome_count(self) -> int:
        """Get count of recorded outcomes.

        Returns:
            Number of outcomes recorded
        """
        redis_client = self._get_redis()

        try:
            keys = redis_client.keys("ict:outcome:*")
            return len(keys)
        except Exception as e:
            logger.error(f"Failed to get outcome count: {e}")
            return 0
