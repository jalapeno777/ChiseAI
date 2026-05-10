"""Tests for PAPER-003: Orchestrator Health Key.

Verifies that the orchestrator writes, refreshes, and cleans up a Redis health key.
"""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from execution.paper.orchestrator import PaperTradingOrchestrator


@pytest.fixture
def mock_deps():
    """Create mock dependencies for orchestrator tests."""
    telemetry = MagicMock()
    telemetry.start = AsyncMock()
    telemetry.stop = AsyncMock()

    return {
        "signal_generator": MagicMock(),
        "order_simulator": MagicMock(),
        "position_tracker": MagicMock(),
        "risk_enforcer": MagicMock(),
        "telemetry_collector": telemetry,
        "kill_switch": MagicMock(),
    }


@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    return MagicMock()


@pytest.fixture
def orchestrator(mock_deps, mock_redis):
    """Create an orchestrator with a mock Redis client."""
    return PaperTradingOrchestrator(**mock_deps, redis_client=mock_redis)


class TestHealthKeyOnStartup:
    """AC1: orchestrator writes paper:orchestrator:health on startup."""

    @pytest.mark.asyncio
    async def test_start_writes_health_key(self, orchestrator, mock_redis):
        """start() should write the health key to Redis."""
        await orchestrator.start()

        try:
            mock_redis.setex.assert_called()
            call_args = mock_redis.setex.call_args
            assert call_args[0][0] == PaperTradingOrchestrator.HEALTH_KEY
            assert call_args[0][1] == PaperTradingOrchestrator.HEALTH_TTL_SECONDS
        finally:
            # Clean up
            await orchestrator.stop()


class TestHealthKeyTTL:
    """AC2: health key TTL is 120s."""

    def test_ttl_constant(self):
        """HEALTH_TTL_SECONDS should be 120."""
        assert PaperTradingOrchestrator.HEALTH_TTL_SECONDS == 120

    @pytest.mark.asyncio
    async def test_setex_called_with_120_ttl(self, orchestrator, mock_redis):
        """_update_health should pass TTL=120 to setex."""
        await orchestrator._update_health("running")

        call_args = mock_redis.setex.call_args
        assert call_args[0][1] == 120


class TestHealthKeyRefresh:
    """AC3: processing loop refreshes health key."""

    @pytest.mark.asyncio
    async def test_update_health_refreshes_key(self, orchestrator, mock_redis):
        """Each _update_health call should refresh the key."""
        await orchestrator._update_health("running")
        await orchestrator._update_health("running")

        assert mock_redis.setex.call_count == 2


class TestHealthPayloadFormat:
    """AC4: health payload includes status, timestamp, processed_count."""

    @pytest.mark.asyncio
    async def test_payload_structure(self, orchestrator, mock_redis):
        """Payload should contain status, timestamp, and processed_count."""
        await orchestrator._update_health("running")

        call_args = mock_redis.setex.call_args
        payload_str = call_args[0][2]
        payload = json.loads(payload_str)

        assert "status" in payload
        assert "timestamp" in payload
        assert "processed_count" in payload

    @pytest.mark.asyncio
    async def test_payload_status_running(self, orchestrator, mock_redis):
        """Status should be 'running' when called with 'running'."""
        await orchestrator._update_health("running")

        call_args = mock_redis.setex.call_args
        payload = json.loads(call_args[0][2])
        assert payload["status"] == "running"

    @pytest.mark.asyncio
    async def test_payload_timestamp_is_iso8601(self, orchestrator, mock_redis):
        """Timestamp should be a valid ISO-8601 string."""
        await orchestrator._update_health("running")

        call_args = mock_redis.setex.call_args
        payload = json.loads(call_args[0][2])
        # Should not raise
        datetime.fromisoformat(payload["timestamp"])

    @pytest.mark.asyncio
    async def test_payload_processed_count_is_int(self, orchestrator, mock_redis):
        """processed_count should be an integer."""
        await orchestrator._update_health("running")

        call_args = mock_redis.setex.call_args
        payload = json.loads(call_args[0][2])
        assert isinstance(payload["processed_count"], int)

    @pytest.mark.asyncio
    async def test_payload_reflects_metrics(self, orchestrator, mock_redis):
        """processed_count should reflect actual signals_processed metric."""
        orchestrator._metrics["signals_processed"] = 42
        await orchestrator._update_health("running")

        call_args = mock_redis.setex.call_args
        payload = json.loads(call_args[0][2])
        assert payload["processed_count"] == 42


class TestHealthKeyGracefulStop:
    """AC5: graceful stop clears key or allows TTL expiry predictably.

    Implementation uses Option A: explicit delete on stop.
    """

    @pytest.mark.asyncio
    async def test_stop_deletes_health_key(self, orchestrator, mock_redis):
        """stop() should delete the health key from Redis."""
        await orchestrator.start()

        try:
            await orchestrator.stop()

            mock_redis.delete.assert_called_once_with(
                PaperTradingOrchestrator.HEALTH_KEY
            )
        finally:
            # Ensure stop is called even if assertion fails
            pass

    @pytest.mark.asyncio
    async def test_stop_without_redis_no_error(self, mock_deps):
        """stop() should not raise when redis_client is None."""
        orchestrator = PaperTradingOrchestrator(**mock_deps, redis_client=None)
        # Should not raise
        await orchestrator.start()
        try:
            await orchestrator.stop()
        finally:
            pass


class TestHealthKeyNoRedis:
    """Edge cases: no Redis client provided."""

    @pytest.mark.asyncio
    async def test_update_health_no_redis(self, mock_deps):
        """_update_health should silently skip when redis_client is None."""
        orchestrator = PaperTradingOrchestrator(**mock_deps, redis_client=None)
        # Should not raise
        await orchestrator._update_health("running")

    @pytest.mark.asyncio
    async def test_update_health_redis_error(self, orchestrator, mock_redis):
        """_update_health should not raise when Redis throws an exception."""
        mock_redis.setex.side_effect = Exception("Connection refused")
        # Should not raise
        await orchestrator._update_health("running")
