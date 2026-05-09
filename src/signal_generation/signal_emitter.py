"""Signal emitter interface and implementations.

Provides abstract interface for signal emission and concrete
implementations for Discord and dashboard emission.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from signal_generation.models import Signal

if TYPE_CHECKING:
    from signal_generation.models import Signal

logger = logging.getLogger(__name__)


@dataclass
class EmissionResult:
    """Result of signal emission attempt.

    Attributes:
        success: Whether emission was successful
        channel: Channel the signal was emitted to
        error: Error message if emission failed
        latency_ms: Time taken to emit (ms)
    """

    success: bool
    channel: str
    error: str | None = None
    latency_ms: float = 0.0


class SignalEmitter(ABC):
    """Abstract base class for signal emitters.

        Signal emitters are responsible for sending actionable signals
    to various destinations (Discord, dashboard, etc.).
    """

    def __init__(self, name: str):
        """Initialize emitter.

        Args:
            name: Emitter name/identifier
        """
        self.name = name
        self._enabled = True

    @abstractmethod
    async def emit(self, signal: Signal) -> EmissionResult:
        """Emit a signal to the destination.

        Args:
            signal: The signal to emit

        Returns:
            EmissionResult with status
        """
        pass

    @abstractmethod
    async def emit_batch(self, signals: list[Signal]) -> list[EmissionResult]:
        """Emit multiple signals.

        Args:
            signals: List of signals to emit

        Returns:
            List of EmissionResults
        """
        pass

    def enable(self) -> None:
        """Enable this emitter."""
        self._enabled = True
        logger.info(f"Emitter '{self.name}' enabled")

    def disable(self) -> None:
        """Disable this emitter."""
        self._enabled = False
        logger.info(f"Emitter '{self.name}' disabled")

    @property
    def is_enabled(self) -> bool:
        """Check if emitter is enabled."""
        return self._enabled


class DiscordEmitter(SignalEmitter):
    """Discord signal emitter implementation.

    Emits actionable signals to Discord via webhook.
    Configurable threshold separate from internal actionable threshold.

    For ST-NS-009: Discord Integration
    """

    DEFAULT_DISCORD_THRESHOLD = 0.40  # 40% default per validation registry

    def __init__(
        self,
        webhook_url: str | None = None,
        threshold: float = DEFAULT_DISCORD_THRESHOLD,
        max_signals_per_hour: int = 10,
    ):
        """Initialize Discord emitter.

        Args:
            webhook_url: Discord webhook URL (or from env DISCORD_WEBHOOK_URL)
            threshold: Minimum confidence for Discord alerts (default 40%)
            max_signals_per_hour: Rate limit for signals per token per hour
        """
        super().__init__("discord")
        self.webhook_url = webhook_url or self._get_webhook_from_env()
        self.threshold = threshold
        self.max_signals_per_hour = max_signals_per_hour

        # Rate limiting state
        self._signal_counts: dict[str, list[float]] = {}  # token -> timestamps

    def _get_webhook_from_env(self) -> str | None:
        """Get webhook URL from environment."""
        return os.getenv("DISCORD_WEBHOOK_URL")

    def _get_bypass_from_env(self) -> bool:
        """Check if bypass is enabled via environment variable.

        Returns:
            True if CHISEAI_BYPASS_CONFIDENCE_FILTER is set to a truthy value.
            Emits a WARNING log when bypass is active.
        """
        bypass = os.getenv("CHISEAI_BYPASS_CONFIDENCE_FILTER", "").lower() in (
            "1",
            "true",
            "yes",
        )
        if bypass:
            logger.warning(
                "CHISEAI_BYPASS_CONFIDENCE_FILTER is active — "
                "confidence filtering is disabled for Discord emissions"
            )
        return bypass

    def _log_bypass_event(
        self,
        signal_id: str,
        confidence: float,
        bypass_reason: str,
    ) -> None:
        """Log a confidence filter bypass event.

        Args:
            signal_id: Unique signal identifier
            confidence: Signal confidence score
            bypass_reason: Reason for bypassing the confidence filter
        """
        timestamp = datetime.now(UTC).isoformat()
        logger.warning(
            f"CONFIDENCE_BYPASS: signal_id={signal_id} "
            f"confidence={confidence:.2%} "
            f"reason={bypass_reason} "
            f"timestamp={timestamp}"
        )

    def _check_rate_limit(self, token: str) -> bool:
        """Check if token has exceeded rate limit.

        Args:
            token: Trading pair token

        Returns:
            True if under rate limit, False if exceeded
        """
        import time

        now = time.time()
        hour_ago = now - 3600

        # Get recent signals for this token
        timestamps = self._signal_counts.get(token, [])
        recent = [t for t in timestamps if t > hour_ago]

        # Update stored timestamps
        self._signal_counts[token] = recent

        return len(recent) < self.max_signals_per_hour

    def _record_signal(self, token: str) -> None:
        """Record a signal emission for rate limiting.

        Args:
            token: Trading pair token
        """
        import time

        if token not in self._signal_counts:
            self._signal_counts[token] = []
        self._signal_counts[token].append(time.time())

    def _format_message(self, signal: Signal) -> str:
        """Format signal as Discord message content.

        Args:
            signal: Signal to format

        Returns:
            Formatted message string
        """
        direction_emoji = "🟢" if signal.direction_str == "long" else "🔴"
        return (
            f"{direction_emoji} **{signal.direction_str.upper()}** Signal | "
            f"{signal.token} | Confidence: {signal.confidence:.0%}"
        )

    def _should_use_embed(self, signal: Signal) -> bool:
        """Check if signal should use rich embed format.

        Args:
            signal: Signal to check

        Returns:
            True if embed should be used
        """
        # Use embed for higher confidence signals
        return signal.confidence >= 0.6

    def _build_embed(self, signal: Signal) -> dict:
        """Build Discord embed for signal.

        Args:
            signal: Signal to build embed for

        Returns:
            Discord embed dictionary
        """
        embed = {
            "title": f"{signal.direction_str.upper()} Signal: {signal.token}",
            "color": 0x00FF00 if signal.direction_str == "long" else 0xFF0000,
            "fields": [
                {
                    "name": "Direction",
                    "value": signal.direction_str.upper(),
                    "inline": True,
                },
                {
                    "name": "Confidence",
                    "value": f"{signal.confidence:.1%}",
                    "inline": True,
                },
                {"name": "Token", "value": signal.token, "inline": True},
            ],
        }

        # Add entry price if available
        fields: list[dict[str, Any]] = embed["fields"]  # type: ignore[assignment]
        if hasattr(signal, "entry_price") and signal.entry_price:
            fields.append(
                {
                    "name": "Entry Price",
                    "value": str(signal.entry_price),
                    "inline": True,
                }
            )

        # Add stop loss if available
        if hasattr(signal, "stop_loss") and signal.stop_loss:
            fields.append(
                {"name": "Stop Loss", "value": str(signal.stop_loss), "inline": True}
            )

        # Add take profit if available
        if hasattr(signal, "take_profit") and signal.take_profit:
            fields.append(
                {
                    "name": "Take Profit",
                    "value": str(signal.take_profit),
                    "inline": True,
                }
            )

        return embed

    async def emit(
        self,
        signal: Signal,
        bypass_confidence_filter: bool = False,
    ) -> EmissionResult:
        """Emit signal to Discord.

        Args:
            signal: Signal to emit
            bypass_confidence_filter: Skip confidence threshold check (ST-CONF-003 AC6)

        Returns:
            EmissionResult with status
        """
        import time

        start_time = time.perf_counter()

        if not self._enabled:
            return EmissionResult(
                success=False,
                channel="discord",
                error="Emitter is disabled",
                latency_ms=0.0,
            )

        # Skip rate-limited signals gracefully
        status_value = getattr(getattr(signal, "status", None), "value", None)
        if status_value == "rate_limited":
            logger.info(
                "Skipping rate-limited signal: %s [%s]",
                signal.token,
                getattr(signal, "direction_str", "unknown"),
            )
            return EmissionResult(
                success=False,
                channel="discord",
                error="Signal is rate-limited",
                latency_ms=0.0,
            )

        if not self.webhook_url:
            return EmissionResult(
                success=False,
                channel="discord",
                error="No Discord webhook URL configured",
                latency_ms=0.0,
            )

        # Check confidence threshold (unless bypassed)
        if signal.confidence < self.threshold:
            # Check for environment variable override
            env_bypass = self._get_bypass_from_env()
            if bypass_confidence_filter or env_bypass:
                # Log bypass event
                bypass_reason = (
                    "explicit_bypass_param"
                    if bypass_confidence_filter
                    else "env_variable_override"
                )
                self._log_bypass_event(
                    signal_id=signal.signal_id,
                    confidence=signal.confidence,
                    bypass_reason=bypass_reason,
                )
            else:
                return EmissionResult(
                    success=False,
                    channel="discord",
                    error=(
                        f"Signal confidence {signal.confidence:.1%} below "
                        f"Discord threshold {self.threshold:.0%}"
                    ),
                    latency_ms=0.0,
                )

        # Check rate limit
        if not self._check_rate_limit(signal.token):
            return EmissionResult(
                success=False,
                channel="discord",
                error=(
                    f"Rate limit exceeded for {signal.token} "
                    f"({self.max_signals_per_hour}/hour)"
                ),
                latency_ms=0.0,
            )

        try:
            # Send to Discord via webhook
            import aiohttp

            # Build message payload
            payload = {
                "content": self._format_message(signal),
                "embeds": (
                    [self._build_embed(signal)]
                    if self._should_use_embed(signal)
                    else None
                ),
            }
            # Remove None values
            payload = {k: v for k, v in payload.items() if v is not None}

            # Send webhook request
            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=payload) as resp:
                    if resp.status == 204:
                        self._record_signal(signal.token)
                        latency_ms = (time.perf_counter() - start_time) * 1000
                        logger.info(
                            f"Discord emission: {signal.token} [{signal.direction_str}]"
                        )
                        return EmissionResult(
                            success=True,
                            channel="discord",
                            latency_ms=latency_ms,
                        )
                    elif resp.status == 429:
                        latency_ms = (time.perf_counter() - start_time) * 1000
                        error_msg = "Discord rate limited"
                        logger.warning(f"Discord emission rate limited: {signal.token}")
                        return EmissionResult(
                            success=False,
                            channel="discord",
                            error=error_msg,
                            latency_ms=latency_ms,
                        )
                    else:
                        latency_ms = (time.perf_counter() - start_time) * 1000
                        body = await resp.text()
                        error_msg = f"Discord HTTP {resp.status}: {body}"
                        logger.error(f"Discord emission failed: {error_msg}")
                        return EmissionResult(
                            success=False,
                            channel="discord",
                            error=error_msg,
                            latency_ms=latency_ms,
                        )

        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.error(f"Discord emission failed: {e}")
            return EmissionResult(
                success=False,
                channel="discord",
                error=str(e),
                latency_ms=latency_ms,
            )

    async def emit_batch(self, signals: list[Signal]) -> list[EmissionResult]:
        """Emit multiple signals to Discord.

        Args:
            signals: List of signals to emit

        Returns:
            List of EmissionResults
        """
        results = []
        for signal in signals:
            result = await self.emit(signal)
            results.append(result)
        return results


class DashboardEmitter(SignalEmitter):
    """Dashboard signal emitter interface.

    For ST-NS-008: Dashboard Integration
    Provides interface for emitting signals to the dashboard.
    Uses Redis streams for distributed signal delivery.
    """

    # Redis stream key for dashboard signals
    STREAM_KEY = "chiseai:signals:dashboard"

    # Redis connection settings (matches iteration_logging.py)
    DEFAULT_REDIS_HOST = "chiseai-redis"
    DEFAULT_REDIS_PORT = 6380
    DEFAULT_REDIS_DB = 0

    def __init__(
        self,
        dashboard_url: str | None = None,
        redis_host: str | None = None,
        redis_port: int | None = None,
        redis_db: int | None = None,
    ):
        """Initialize dashboard emitter.

        Args:
            dashboard_url: Dashboard API URL (unused but kept for interface compatibility)
            redis_host: Redis host (defaults to host.docker.internal)
            redis_port: Redis port (defaults to 6380)
            redis_db: Redis DB (defaults to 0)
        """
        super().__init__("dashboard")
        self.dashboard_url = dashboard_url
        self.redis_host = redis_host or self.DEFAULT_REDIS_HOST
        self.redis_port = redis_port or self.DEFAULT_REDIS_PORT
        self.redis_db = redis_db if redis_db is not None else self.DEFAULT_REDIS_DB
        self._redis_client: Any = None

    def _get_redis_client(self) -> Any:
        """Get or create Redis client.

        Returns:
            Redis client or None if connection fails
        """
        import logging

        if self._redis_client is not None:
            return self._redis_client

        try:
            import redis

            client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                db=self.redis_db,
                decode_responses=True,
            )
            # Test connection
            client.ping()
            self._redis_client = client
            return client
        except Exception as e:
            logging.getLogger(__name__).warning(
                f"Dashboard emitter: Redis connection failed: {e}"
            )
            return None

    def _emit_to_redis(self, payload: dict[str, Any]) -> bool:
        """Emit signal payload to Redis stream.

        Args:
            payload: Signal payload dictionary

        Returns:
            True if emission succeeded, False otherwise
        """
        import json

        client = self._get_redis_client()
        if client is None:
            return False

        try:
            # Add to Redis stream with auto-generated ID
            client.xadd(self.STREAM_KEY, {"data": json.dumps(payload)})
            return True
        except Exception as e:
            logging.getLogger(__name__).warning(
                f"Dashboard emitter: Failed to add to stream: {e}"
            )
            return False

    async def emit(self, signal: Signal) -> EmissionResult:
        """Emit signal to dashboard via Redis stream.

        Args:
            signal: Signal to emit

        Returns:
            EmissionResult with status
        """
        import time

        start_time = time.perf_counter()

        if not self._enabled:
            return EmissionResult(
                success=False,
                channel="dashboard",
                error="Emitter is disabled",
                latency_ms=0.0,
            )

        # Skip rate-limited signals gracefully
        status_value = getattr(getattr(signal, "status", None), "value", None)
        if status_value == "rate_limited":
            logger.info(
                "Skipping rate-limited signal: %s [%s]",
                signal.token,
                getattr(signal, "direction_str", "unknown"),
            )
            return EmissionResult(
                success=False,
                channel="dashboard",
                error="Signal is rate-limited",
                latency_ms=0.0,
            )

        # Convert signal to dashboard payload using existing method
        payload = signal.to_dashboard_payload()

        # Emit to Redis stream
        success = self._emit_to_redis(payload)

        latency_ms = (time.perf_counter() - start_time) * 1000

        if success:
            logger.debug(f"Dashboard emission: {signal.token} [{signal.direction_str}]")
            return EmissionResult(
                success=True,
                channel="dashboard",
                latency_ms=latency_ms,
            )
        else:
            return EmissionResult(
                success=False,
                channel="dashboard",
                error="Failed to emit to Redis stream",
                latency_ms=latency_ms,
            )

    async def emit_batch(self, signals: list[Signal]) -> list[EmissionResult]:
        """Emit multiple signals to dashboard.

        Args:
            signals: List of signals to emit

        Returns:
            List of EmissionResults
        """
        results = []
        for signal in signals:
            result = await self.emit(signal)
            results.append(result)
        return results


class CompositeEmitter(SignalEmitter):
    """Composite emitter that sends to multiple destinations.

    Emits signals to all configured emitters (Discord, Dashboard, etc.).
    """

    def __init__(self, emitters: list[SignalEmitter] | None = None):
        """Initialize composite emitter.

        Args:
            emitters: List of emitters to use
        """
        super().__init__("composite")
        self.emitters = emitters or []

    def add_emitter(self, emitter: SignalEmitter) -> None:
        """Add an emitter to the composite.

        Args:
            emitter: Emitter to add
        """
        self.emitters.append(emitter)

    async def emit(self, signal: Signal) -> EmissionResult:
        """Emit signal to all configured emitters.

        Args:
            signal: Signal to emit

        Returns:
            Aggregate EmissionResult
        """
        if not self.emitters:
            return EmissionResult(
                success=False,
                channel="composite",
                error="No emitters configured",
            )

        results = await self.emit_batch([signal])
        return (
            results[0]
            if results
            else EmissionResult(
                success=False,
                channel="composite",
                error="No results",
            )
        )

    async def emit_batch(self, signals: list[Signal]) -> list[EmissionResult]:
        """Emit multiple signals to all emitters.

        Args:
            signals: List of signals to emit

        Returns:
            List of EmissionResults (one per signal)
        """
        all_results = []

        for signal in signals:
            signal_results = []
            for emitter in self.emitters:
                try:
                    result = await emitter.emit(signal)
                    signal_results.append(result)
                except Exception as e:
                    logger.error(f"Emitter {emitter.name} failed: {e}")
                    signal_results.append(
                        EmissionResult(
                            success=False,
                            channel=emitter.name,
                            error=str(e),
                        )
                    )

            # Aggregate results for this signal
            success = any(r.success for r in signal_results)
            errors = [r.error for r in signal_results if r.error]
            total_latency = sum(r.latency_ms for r in signal_results)

            all_results.append(
                EmissionResult(
                    success=success,
                    channel="composite",
                    error="; ".join(errors) if errors else None,
                    latency_ms=total_latency,
                )
            )

        return all_results
