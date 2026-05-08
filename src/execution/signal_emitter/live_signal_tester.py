"""Live Signal Emission Testing Module.

Provides live signal emission testing capabilities for BOS/CHoCH signals.
Tests signal emission latency and Discord delivery validation.

For ST-ICT-035: Live Signal Emission Testing
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from signal_generation.models import Signal, SignalDirection, SignalStatus
from signal_generation.signal_emitter import DiscordEmitter, EmissionResult
from src.config.ict_feature_flags import ICTFeatureFlags, get_ict_feature_flags

logger = logging.getLogger(__name__)

# Discord webhook environment variable
DISCORD_WEBHOOK_ENV = "DISCORD_WEBHOOK_URL"


@dataclass
class LatencyMeasurement:
    """Latency measurement result.

    Attributes:
        signal_type: Type of signal tested
        token: Trading pair token
        emission_latency_ms: Time to emit signal in milliseconds
        total_latency_ms: Total end-to-end latency
        within_threshold: Whether latency was under 2 seconds
        timestamp: When measurement was taken
    """

    signal_type: str
    token: str
    emission_latency_ms: float
    total_latency_ms: float
    within_threshold: bool
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class DiscordDeliveryResult:
    """Discord delivery validation result.

    Attributes:
        success: Whether delivery was successful
        webhook_response: HTTP status or response
        error: Error message if failed
        message_id: Discord message ID if successful
        timestamp: When delivery was attempted
    """

    success: bool
    webhook_response: str
    error: str | None = None
    message_id: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class TestSignalResult:
    """Result of a test signal emission.

    Attributes:
        signal_emitted: Whether signal was emitted
        latency_ms: Emission latency
        discord_delivery: Discord delivery result
        feature_flag_enabled: Whether feature flag was enabled
        error: Error message if emission failed
        timestamp: When test was performed
    """

    signal_emitted: bool
    latency_ms: float
    discord_delivery: DiscordDeliveryResult | None
    feature_flag_enabled: bool
    error: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class LiveSignalTester:
    """Live signal tester for BOS/CHoCH emission validation.

    Tests signal emission latency and Discord delivery without actual execution.
    Feature flag controlled - only emits if ict:bos_choch:enabled is True.

    For ST-ICT-035: Live Signal Emission Testing
    """

    LATENCY_THRESHOLD_MS = 2000  # 2 seconds max latency

    def __init__(
        self,
        discord_webhook_url: str | None = None,
        feature_flags: ICTFeatureFlags | None = None,
    ):
        """Initialize live signal tester.

        Args:
            discord_webhook_url: Discord webhook URL (or from env DISCORD_WEBHOOK_URL)
            feature_flags: ICT feature flags instance (defaults to global)
        """
        self.discord_webhook_url = discord_webhook_url
        self.feature_flags = feature_flags or get_ict_feature_flags()
        self._discord_emitter: DiscordEmitter | None = None
        self._latency_measurements: list[LatencyMeasurement] = []

    def _get_discord_emitter(self) -> DiscordEmitter:
        """Get or create Discord emitter.

        Returns:
            DiscordEmitter instance
        """
        if self._discord_emitter is None:
            self._discord_emitter = DiscordEmitter(
                webhook_url=self.discord_webhook_url,
                threshold=0.0,  # Allow all signals for testing
            )
        return self._discord_emitter

    def check_feature_flag(self) -> bool:
        """Check if BOS/CHoCH feature flag is enabled.

        Returns:
            True if ict:bos_choch:enabled is True
        """
        return self.feature_flags.is_bos_choch_enabled()

    async def test_signal_emission(self, symbol: str) -> TestSignalResult:
        """Test signal emission for a symbol.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")

        Returns:
            TestSignalResult with emission details
        """
        # Check feature flag first
        feature_enabled = self.check_feature_flag()

        if not feature_enabled:
            logger.info(
                f"BOS/CHoCH feature flag disabled - skipping emission test for {symbol}"
            )
            return TestSignalResult(
                signal_emitted=False,
                latency_ms=0.0,
                discord_delivery=None,
                feature_flag_enabled=False,
                error="Feature flag ict:bos_choch:enabled is False",
            )

        # Create test signal
        test_signal = Signal(
            token=symbol,
            direction=SignalDirection.LONG,
            confidence=0.75,
            base_score=75.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
            contributing_factors=[{"type": "bos_choch", "weight": 1.0}],
            metadata={"test": True, "test_type": "ST-ICT-035"},
        )

        # Emit and measure latency
        emitter = self._get_discord_emitter()
        start_time = time.perf_counter()

        try:
            result = await emitter.emit(test_signal, bypass_confidence_filter=True)
            latency_ms = (time.perf_counter() - start_time) * 1000

            # Record latency measurement
            measurement = LatencyMeasurement(
                signal_type="bos_choch",
                token=symbol,
                emission_latency_ms=latency_ms,
                total_latency_ms=latency_ms,
                within_threshold=latency_ms < self.LATENCY_THRESHOLD_MS,
            )
            self._latency_measurements.append(measurement)

            # Validate Discord delivery
            discord_result = DiscordDeliveryResult(
                success=result.success,
                webhook_response=(
                    f"HTTP {result.latency_ms:.1f}ms" if result.success else "Failed"
                ),
                error=result.error,
            )

            logger.info(
                f"Test signal emitted for {symbol}: latency={latency_ms:.1f}ms "
                f"success={result.success}"
            )

            return TestSignalResult(
                signal_emitted=True,
                latency_ms=latency_ms,
                discord_delivery=discord_result,
                feature_flag_enabled=True,
            )

        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.error(f"Signal emission test failed for {symbol}: {e}")

            return TestSignalResult(
                signal_emitted=False,
                latency_ms=latency_ms,
                discord_delivery=None,
                feature_flag_enabled=True,
                error=str(e),
            )

    def measure_latency(self) -> dict[str, Any]:
        """Calculate latency statistics from recorded measurements.

        Returns:
            Dictionary with latency statistics
        """
        if not self._latency_measurements:
            return {
                "count": 0,
                "avg_ms": 0.0,
                "p95_ms": 0.0,
                "max_ms": 0.0,
                "within_threshold_pct": 0.0,
            }

        latencies = [m.emission_latency_ms for m in self._latency_measurements]
        sorted_latencies = sorted(latencies)
        count = len(sorted_latencies)

        p95_index = int(count * 0.95)
        within_count = sum(1 for m in self._latency_measurements if m.within_threshold)

        return {
            "count": count,
            "avg_ms": round(sum(latencies) / count, 2),
            "p95_ms": (
                round(sorted_latencies[p95_index], 2)
                if p95_index < count
                else sorted_latencies[-1]
            ),
            "max_ms": round(max(latencies), 2),
            "min_ms": round(min(latencies), 2),
            "within_threshold_pct": round((within_count / count) * 100, 2),
        }

    async def validate_discord_delivery(
        self,
        webhook_url: str | None = None,
    ) -> DiscordDeliveryResult:
        """Validate Discord webhook delivery with a test message.

        Args:
            webhook_url: Discord webhook URL to test (uses configured URL if not provided)

        Returns:
            DiscordDeliveryResult with delivery status
        """
        test_url = webhook_url or self.discord_webhook_url

        if not test_url:
            # Try to get from environment
            import os

            test_url = os.getenv(DISCORD_WEBHOOK_ENV)

        if not test_url:
            return DiscordDeliveryResult(
                success=False,
                webhook_response="No webhook URL",
                error="No Discord webhook URL configured",
            )

        try:
            import aiohttp

            test_payload = {
                "content": f"🧪 **BOS/CHoCH Live Signal Test** | {datetime.now(UTC).isoformat()}",
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    test_url, json=test_payload, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 204:
                        return DiscordDeliveryResult(
                            success=True,
                            webhook_response=f"HTTP {resp.status}",
                            message_id="test_delivery",
                        )
                    else:
                        body = await resp.text()
                        return DiscordDeliveryResult(
                            success=False,
                            webhook_response=f"HTTP {resp.status}",
                            error=f"Discord returned {resp.status}: {body[:200]}",
                        )

        except TimeoutError:
            return DiscordDeliveryResult(
                success=False,
                webhook_response="Timeout",
                error="Discord webhook request timed out after 10 seconds",
            )
        except Exception as e:
            return DiscordDeliveryResult(
                success=False,
                webhook_response="Error",
                error=str(e),
            )

    async def emit_test_signal(
        self,
        symbol: str,
        direction: SignalDirection = SignalDirection.LONG,
        confidence: float = 0.75,
    ) -> EmissionResult | None:
        """Emit a test signal if feature flag is enabled.

        Args:
            symbol: Trading pair symbol
            direction: Signal direction (default LONG)
            confidence: Signal confidence (default 0.75)

        Returns:
            EmissionResult if emitted, None if feature flag disabled
        """
        if not self.check_feature_flag():
            logger.info("BOS/CHoCH feature flag disabled - emit_test_signal skipped")
            return None

        test_signal = Signal(
            token=symbol,
            direction=direction,
            confidence=confidence,
            base_score=confidence * 100,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
            contributing_factors=[{"type": "bos_choch_test", "weight": 1.0}],
            metadata={"test_emission": True},
        )

        emitter = self._get_discord_emitter()
        result = await emitter.emit(test_signal, bypass_confidence_filter=True)

        logger.info(
            f"Test signal emitted: {symbol} {direction.value} "
            f"(confidence={confidence:.0%}) -> success={result.success}"
        )

        return result

    def get_latency_measurements(self) -> list[LatencyMeasurement]:
        """Get all recorded latency measurements.

        Returns:
            List of LatencyMeasurement records
        """
        return self._latency_measurements.copy()

    def clear_measurements(self) -> None:
        """Clear all recorded latency measurements."""
        self._latency_measurements.clear()
        logger.info("Latency measurements cleared")

    def get_feature_flag_status(self) -> dict[str, Any]:
        """Get current feature flag status.

        Returns:
            Dictionary with feature flag status
        """
        return {
            "ict_bos_choch_enabled": self.check_feature_flag(),
            "redis_key": ICTFeatureFlags.KEY_BOS_CHOCH,
            "default_value": True,
            "safety_note": "BOS/CHoCH enabled by default (accuracy fix applied)",
        }
