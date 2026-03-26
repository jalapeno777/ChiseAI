"""Tests for Live Signal Tester.

For ST-ICT-035: Live Signal Emission Testing
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.execution.signal_emitter.live_signal_tester import (
    DISCORD_WEBHOOK_ENV,
    LatencyMeasurement,
    LiveSignalTester,
    TestSignalResult,
)


class TestLiveSignalTester:
    """Tests for LiveSignalTester class."""

    def test_init_default(self):
        """Test initialization with defaults."""
        tester = LiveSignalTester()

        assert tester.discord_webhook_url is None
        assert tester.feature_flags is not None

    def test_init_with_custom_discord_url(self):
        """Test initialization with custom Discord URL."""
        tester = LiveSignalTester(
            discord_webhook_url="https://discord.com/webhook/test",
        )

        assert tester.discord_webhook_url == "https://discord.com/webhook/test"

    def test_measure_latency_no_measurements(self):
        """Test latency measurement with no data."""
        tester = LiveSignalTester()
        stats = tester.measure_latency()

        assert stats["count"] == 0
        assert stats["avg_ms"] == 0.0
        assert stats["within_threshold_pct"] == 0.0

    def test_measure_latency_with_measurements(self):
        """Test latency measurement with data."""
        tester = LiveSignalTester()

        # Add some measurements
        tester._latency_measurements = [
            LatencyMeasurement(
                signal_type="bos_choch",
                token="BTCUSDT",
                emission_latency_ms=500.0,
                total_latency_ms=500.0,
                within_threshold=True,
            ),
            LatencyMeasurement(
                signal_type="bos_choch",
                token="ETHUSDT",
                emission_latency_ms=1500.0,
                total_latency_ms=1500.0,
                within_threshold=True,
            ),
            LatencyMeasurement(
                signal_type="bos_choch",
                token="SOLUSDT",
                emission_latency_ms=2500.0,
                total_latency_ms=2500.0,
                within_threshold=False,
            ),
        ]

        stats = tester.measure_latency()

        assert stats["count"] == 3
        assert stats["avg_ms"] == 1500.0
        assert stats["max_ms"] == 2500.0
        assert stats["min_ms"] == 500.0
        assert stats["within_threshold_pct"] == pytest.approx(66.67, rel=0.1)

    def test_get_latency_measurements(self):
        """Test getting latency measurements."""
        tester = LiveSignalTester()

        measurement = LatencyMeasurement(
            signal_type="bos_choch",
            token="BTCUSDT",
            emission_latency_ms=500.0,
            total_latency_ms=500.0,
            within_threshold=True,
        )
        tester._latency_measurements.append(measurement)

        measurements = tester.get_latency_measurements()

        assert len(measurements) == 1
        assert measurements[0].token == "BTCUSDT"

    def test_clear_measurements(self):
        """Test clearing latency measurements."""
        tester = LiveSignalTester()

        measurement = LatencyMeasurement(
            signal_type="bos_choch",
            token="BTCUSDT",
            emission_latency_ms=500.0,
            total_latency_ms=500.0,
            within_threshold=True,
        )
        tester._latency_measurements.append(measurement)

        tester.clear_measurements()

        assert len(tester._latency_measurements) == 0

    @pytest.mark.asyncio
    async def test_validate_discord_delivery_no_webhook(self):
        """Test Discord validation with no webhook URL."""
        tester = LiveSignalTester(discord_webhook_url=None)

        with patch.dict("os.environ", {}, clear=True):
            result = await tester.validate_discord_delivery()

        assert result.success is False
        assert "No Discord webhook URL" in result.error

    @pytest.mark.asyncio
    async def test_validate_discord_delivery_success(self):
        """Test successful Discord delivery validation."""
        tester = LiveSignalTester()

        mock_response = MagicMock()
        mock_response.status = 204

        # session.post returns a context manager that yields the response
        mock_post_context = MagicMock()
        mock_post_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_post_context.__aexit__ = AsyncMock()

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_post_context)

        # aiohttp.ClientSession() is a context manager
        mock_session_context = MagicMock()
        mock_session_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_context.__aexit__ = AsyncMock()

        with patch("aiohttp.ClientSession", return_value=mock_session_context):
            with patch.dict(
                "os.environ", {DISCORD_WEBHOOK_ENV: "https://discord.com/webhook/test"}
            ):
                tester.discord_webhook_url = "https://discord.com/webhook/test"
                result = await tester.validate_discord_delivery()

        assert result.success is True
        assert result.webhook_response == "HTTP 204"

    @pytest.mark.asyncio
    async def test_emit_test_signal_flag_disabled(self):
        """Test emit_test_signal when flag disabled."""
        mock_flags = MagicMock()
        mock_flags.is_bos_choch_enabled.return_value = False

        tester = LiveSignalTester(feature_flags=mock_flags)
        result = await tester.emit_test_signal("BTCUSDT")

        assert result is None

    @pytest.mark.asyncio
    async def test_emit_test_signal_flag_enabled(self):
        """Test emit_test_signal when flag enabled."""
        mock_flags = MagicMock()
        mock_flags.is_bos_choch_enabled.return_value = True

        mock_emitter = MagicMock()
        mock_emitter.emit = AsyncMock()
        mock_emitter.emit.return_value = MagicMock(
            success=True,
            channel="discord",
            error=None,
            latency_ms=50.0,
        )

        tester = LiveSignalTester(feature_flags=mock_flags)
        tester._discord_emitter = mock_emitter

        result = await tester.emit_test_signal("BTCUSDT")

        assert result is not None
        assert result.success is True
        mock_emitter.emit.assert_called_once()


class TestLatencyMeasurement:
    """Tests for LatencyMeasurement dataclass."""

    def test_latency_measurement_creation(self):
        """Test LatencyMeasurement creation."""
        measurement = LatencyMeasurement(
            signal_type="bos_choch",
            token="BTCUSDT",
            emission_latency_ms=500.0,
            total_latency_ms=500.0,
            within_threshold=True,
        )

        assert measurement.signal_type == "bos_choch"
        assert measurement.token == "BTCUSDT"
        assert measurement.emission_latency_ms == 500.0
        assert measurement.within_threshold is True
        assert measurement.timestamp is not None


class TestTestSignalResult:
    """Tests for TestSignalResult dataclass."""

    def test_test_signal_result_creation(self):
        """Test TestSignalResult creation."""
        result = TestSignalResult(
            signal_emitted=True,
            latency_ms=150.5,
            discord_delivery=None,
            feature_flag_enabled=True,
        )

        assert result.signal_emitted is True
        assert result.latency_ms == 150.5
        assert result.feature_flag_enabled is True
        assert result.timestamp is not None
