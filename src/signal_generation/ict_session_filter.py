"""ICT Session Filter - Session-scoped quality gating for signals.

Integrates with existing signal pipeline:
- Uses ICTSessionManager for session state
- Applies quality threshold within session context
- Emits session metrics to Redis
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from signal_generation.models import Signal

from signal_generation.ict_session_manager import ICTSessionManager

logger = logging.getLogger(__name__)

# Redis key pattern for session filter metrics
_FILTER_METRICS_KEY = "chiseai:ict:filter:metrics"


@dataclass
class FilterMetrics:
    """Metrics for session filter tracking.

    Attributes:
        total_processed: Total signals evaluated
        signals_allowed: Signals that passed session filter
        signals_blocked: Signals blocked by session filter
        signals_blocked_no_session: Signals blocked because no session was active
        signals_blocked_duplicate: Signals blocked as duplicates
        signals_blocked_low_quality: Signals blocked due to low quality
        last_updated: Timestamp of last metric update
    """

    total_processed: int = 0
    signals_allowed: int = 0
    signals_blocked: int = 0
    signals_blocked_no_session: int = 0
    signals_blocked_duplicate: int = 0
    signals_blocked_low_quality: int = 0
    last_updated: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def block_rate(self) -> float:
        """Calculate block rate (blocked/total).

        Returns:
            Block rate as ratio (0.0-1.0), 0.0 if no signals processed
        """
        if self.total_processed == 0:
            return 0.0
        return self.signals_blocked / self.total_processed

    @property
    def allow_rate(self) -> float:
        """Calculate allow rate (allowed/total).

        Returns:
            Allow rate as ratio (0.0-1.0), 0.0 if no signals processed
        """
        if self.total_processed == 0:
            return 0.0
        return self.signals_allowed / self.total_processed

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary for export.

        Returns:
            Dictionary with metric values
        """
        return {
            "total_processed": self.total_processed,
            "signals_allowed": self.signals_allowed,
            "signals_blocked": self.signals_blocked,
            "signals_blocked_no_session": self.signals_blocked_no_session,
            "signals_blocked_duplicate": self.signals_blocked_duplicate,
            "signals_blocked_low_quality": self.signals_blocked_low_quality,
            "block_rate": self.block_rate,
            "allow_rate": self.allow_rate,
            "last_updated": self.last_updated.isoformat(),
        }


class ICTSessionFilter:
    """Session-scoped quality filter for ICT signals.

    Applies quality gating within the context of ICT trading sessions.
    Integrates with ICTSessionManager for session state and duplicate detection.

    Behavior:
    - If no session is active, signals are blocked (no session = no trading)
    - If signal_id is duplicate within session, signal is blocked
    - If signal quality_score is below threshold, signal is blocked
    - Otherwise, signal is allowed

    Quality threshold is configurable via:
    1. Constructor parameter
    2. ICT_SIGNAL_QUALITY_THRESHOLD environment variable
    3. Default value (0.5)
    """

    DEFAULT_QUALITY_THRESHOLD = 0.5
    MIN_THRESHOLD = 0.0
    MAX_THRESHOLD = 1.0

    def __init__(
        self,
        session_manager: ICTSessionManager | None = None,
        quality_threshold: float | None = None,
        redis_host: str | None = None,
        redis_port: int | None = None,
    ) -> None:
        """Initialize ICT session filter.

        Args:
            session_manager: ICTSessionManager instance (creates default if None)
            quality_threshold: Quality threshold override (0.0-1.0)
            redis_host: Redis host for metrics (defaults to host.docker.internal)
            redis_port: Redis port (defaults to 6379)
        """
        self._session_manager = session_manager or ICTSessionManager(
            redis_host=redis_host,
            redis_port=redis_port,
        )
        self._threshold = self._resolve_threshold(quality_threshold)
        self.metrics = FilterMetrics()
        self._metrics_lock = threading.Lock()

        # Redis for metrics emission
        self._redis_host = redis_host or os.getenv("REDIS_HOST", "host.docker.internal")
        self._redis_port = redis_port or int(os.getenv("REDIS_PORT", "6379"))
        self._redis_client: Any = None
        self._redis_lock = threading.Lock()

        logger.info(
            f"ICTSessionFilter initialized with quality threshold: {self._threshold:.0%}"
        )

    def _resolve_threshold(self, override: float | None) -> float:
        """Resolve quality threshold from override, env var, or default.

        Args:
            override: Optional threshold override

        Returns:
            Resolved threshold value
        """
        if override is not None:
            return max(self.MIN_THRESHOLD, min(self.MAX_THRESHOLD, override))

        env_threshold = os.getenv("ICT_SIGNAL_QUALITY_THRESHOLD")
        if env_threshold:
            try:
                return max(
                    self.MIN_THRESHOLD,
                    min(self.MAX_THRESHOLD, float(env_threshold)),
                )
            except ValueError:
                logger.warning(
                    f"Invalid ICT_SIGNAL_QUALITY_THRESHOLD: {env_threshold}, "
                    f"using default {self.DEFAULT_QUALITY_THRESHOLD}"
                )

        return self.DEFAULT_QUALITY_THRESHOLD

    def _get_redis(self) -> Any:
        """Get or create Redis client for metrics.

        Returns:
            Redis client instance
        """
        if self._redis_client is None:
            with self._redis_lock:
                if self._redis_client is None:
                    import redis

                    self._redis_client = redis.Redis(
                        host=self._redis_host,
                        port=self._redis_port,
                        db=0,
                        decode_responses=True,
                    )
        return self._redis_client

    def _get_quality_score(self, signal: Signal) -> float | None:
        """Extract quality score from signal metadata.

        Args:
            signal: Signal to evaluate

        Returns:
            Quality score from metadata or None if not present
        """
        return signal.metadata.get("quality_score")

    def _emit_metrics_event(self, signal: Signal, allowed: bool) -> None:
        """Emit metrics event to Redis.

        Args:
            signal: Signal that was evaluated
            allowed: Whether signal was allowed
        """
        try:
            redis_client = self._get_redis()
            event = {
                "signal_id": signal.signal_id,
                "timestamp": datetime.now(UTC).isoformat(),
                "allowed": allowed,
                "token": signal.token,
                "confidence": signal.confidence,
                "has_quality_score": "quality_score" in signal.metadata,
            }
            redis_client.lpush(_FILTER_METRICS_KEY, str(event))
            redis_client.ltrim(_FILTER_METRICS_KEY, 0, 999)
        except Exception as e:
            logger.debug(f"Failed to emit metrics event: {e}")

    def filter_signals(self, signals: list[Signal]) -> list[Signal]:
        """Filter a list of signals through session gate.

        Args:
            signals: List of signals to filter

        Returns:
            List of signals that passed session filtering
        """
        allowed_signals = []
        for signal in signals:
            if self.is_signal_allowed(signal):
                allowed_signals.append(signal)
        return allowed_signals

    def is_signal_allowed(self, signal: Signal) -> bool:
        """Determine if signal is allowed through session filter.

        Args:
            signal: Signal to evaluate

        Returns:
            True if signal passes all session filters
        """
        with self._metrics_lock:
            self.metrics.total_processed += 1

        # Check 1: Is there an active session?
        session = self._session_manager.get_current_session()
        if session is None:
            with self._metrics_lock:
                self.metrics.signals_blocked += 1
                self.metrics.signals_blocked_no_session += 1
            self._emit_metrics_event(signal, allowed=False)
            return False

        # Check 2: Is this a duplicate signal?
        if self._session_manager.is_duplicate(signal.signal_id):
            with self._metrics_lock:
                self.metrics.signals_blocked += 1
                self.metrics.signals_blocked_duplicate += 1
            self._session_manager.record_duplicate(signal.signal_id)
            self._emit_metrics_event(signal, allowed=False)
            return False

        # Check 3: Quality threshold check
        quality_score = self._get_quality_score(signal)
        if quality_score is not None and quality_score < self._threshold:
            with self._metrics_lock:
                self.metrics.signals_blocked += 1
                self.metrics.signals_blocked_low_quality += 1
            self._emit_metrics_event(signal, allowed=False)
            return False

        # Signal passes all checks - record it and allow it
        self._session_manager.record_signal(signal.signal_id)

        with self._metrics_lock:
            self.metrics.signals_allowed += 1
        self._emit_metrics_event(signal, allowed=True)
        return True

    def get_filter_metrics(self) -> FilterMetrics:
        """Get current filter metrics.

        Returns:
            FilterMetrics with current counts and rates
        """
        with self._metrics_lock:
            return FilterMetrics(
                total_processed=self.metrics.total_processed,
                signals_allowed=self.metrics.signals_allowed,
                signals_blocked=self.metrics.signals_blocked,
                signals_blocked_no_session=self.metrics.signals_blocked_no_session,
                signals_blocked_duplicate=self.metrics.signals_blocked_duplicate,
                signals_blocked_low_quality=self.metrics.signals_blocked_low_quality,
                last_updated=self.metrics.last_updated,
            )
