"""Signal emitter interface and implementations.

Provides abstract interface for signal emission and concrete
implementations for Discord and dashboard emission.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

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
        """Check if bypass is enabled via environment variable."""
        return os.getenv("DISCORD_BYPASS_CONFIDENCE_FILTER", "").lower() in (
            "1",
            "true",
            "yes",
        )

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
        timestamp = datetime.now(timezone.utc).isoformat()
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
            # TODO: Implement actual Discord webhook call
            # This is a placeholder for ST-NS-009 implementation
            # import aiohttp
            # async with aiohttp.ClientSession() as session:
            #     payload = {
            #         "content": signal.to_discord_message(),
            #         "embeds": [...]
            #     }
            #     async with session.post(self.webhook_url, json=payload) as resp:
            #         success = resp.status == 204

            # Placeholder: simulate success
            self._record_signal(signal.token)
            latency_ms = (time.perf_counter() - start_time) * 1000

            logger.info(f"Discord emission: {signal.token} [{signal.direction_str}]")

            return EmissionResult(
                success=True,
                channel="discord",
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
    """

    def __init__(self, dashboard_url: str | None = None):
        """Initialize dashboard emitter.

        Args:
            dashboard_url: Dashboard API URL
        """
        super().__init__("dashboard")
        self.dashboard_url = dashboard_url

    async def emit(self, signal: Signal) -> EmissionResult:
        """Emit signal to dashboard.

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

        # TODO: Implement actual dashboard emission
        # This is a placeholder for ST-NS-008 implementation
        # Dashboard will receive signals via:
        # - WebSocket for real-time updates
        # - REST API for historical storage
        # - Redis pub/sub for distributed systems

        latency_ms = (time.perf_counter() - start_time) * 1000

        logger.debug(f"Dashboard emission: {signal.token} [{signal.direction_str}]")

        return EmissionResult(
            success=True,
            channel="dashboard",
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
