"""Tests for signal delivery latency optimization.

Tests cover async pipeline, metadata caching, and latency monitoring
to ensure signal delivery under 1 second.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from execution.signal_delivery import (
    AsyncSignalPipeline,
    DeliveryConfig,
    DeliveryResult,
    DeliveryStatus,
    LatencyMetric,
    LatencyMonitor,
    LatencyThresholds,
    SignalMetadataCache,
    SignalMetadataEntry,
)


class TestDeliveryConfig:
    """Tests for DeliveryConfig."""

    def test_default_config(self) -> None:
        """Test default configuration."""
        config = DeliveryConfig.default()
        assert config.max_latency_ms == 1000.0
        assert config.retry_count == 3
        assert config.batch_size == 100

    def test_high_throughput_config(self) -> None:
        """Test high throughput configuration."""
        config = DeliveryConfig.high_throughput()
        assert config.batch_size == 500
        assert config.max_latency_ms == 2000.0

    def test_low_latency_config(self) -> None:
        """Test low latency configuration."""
        config = DeliveryConfig.low_latency()
        assert config.max_latency_ms == 500.0
        assert config.batch_size == 50


class TestDeliveryResult:
    """Tests for DeliveryResult."""

    def test_success_result(self) -> None:
        """Test successful delivery result."""
        result = DeliveryResult(
            signal_id="sig-123",
            status=DeliveryStatus.DELIVERED,
            latency_ms=500,
            result={"delivered": True},
        )
        assert result.is_success is True
        assert result.is_slow() is False

    def test_slow_result(self) -> None:
        """Test slow delivery result."""
        result = DeliveryResult(
            signal_id="sig-123",
            status=DeliveryStatus.DELIVERED,
            latency_ms=1500,
        )
        assert result.is_success is True
        assert result.is_slow() is True

    def test_failed_result(self) -> None:
        """Test failed delivery result."""
        result = DeliveryResult(
            signal_id="sig-123",
            status=DeliveryStatus.FAILED,
            error="Connection timeout",
        )
        assert result.is_success is False

    def test_to_dict(self) -> None:
        """Test serialization."""
        result = DeliveryResult(
            signal_id="sig-123",
            status=DeliveryStatus.DELIVERED,
            latency_ms=500,
        )
        data = result.to_dict()
        assert data["signal_id"] == "sig-123"
        assert data["status"] == "delivered"
        assert data["latency_ms"] == 500


class TestAsyncSignalPipeline:
    """Tests for AsyncSignalPipeline."""

    @pytest.fixture
    def mock_redis(self) -> AsyncMock:
        """Create mock Redis client."""
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock(return_value=True)
        redis.ping = AsyncMock(return_value=True)
        return redis

    @pytest.fixture
    def pipeline(self, mock_redis: AsyncMock) -> AsyncSignalPipeline:
        """Create pipeline instance."""
        return AsyncSignalPipeline(mock_redis)

    @pytest.mark.asyncio
    async def test_deliver_success(self, pipeline: AsyncSignalPipeline) -> None:
        """Test successful signal delivery."""
        signal = MagicMock(signal_id="sig-123")

        result = await pipeline.deliver(signal)

        assert result.is_success is True
        assert result.latency_ms > 0

    @pytest.mark.asyncio
    async def test_deliver_batch(self, pipeline: AsyncSignalPipeline) -> None:
        """Test batch signal delivery."""
        signals = [MagicMock(signal_id=f"sig-{i}") for i in range(5)]

        results = await pipeline.deliver_batch(signals)

        assert len(results) == 5
        assert all(r.is_success for r in results)

    @pytest.mark.asyncio
    async def test_get_stats(self, pipeline: AsyncSignalPipeline) -> None:
        """Test getting pipeline stats."""
        signal = MagicMock(signal_id="sig-123")
        await pipeline.deliver(signal)

        stats = pipeline.get_stats()

        assert stats["total_delivered"] == 1
        assert stats["avg_latency_ms"] > 0

    @pytest.mark.asyncio
    async def test_health_check_healthy(
        self, pipeline: AsyncSignalPipeline, mock_redis: AsyncMock
    ) -> None:
        """Test health check when healthy."""
        result = await pipeline.health_check()

        assert result["status"] == "healthy"


class TestSignalMetadataCache:
    """Tests for SignalMetadataCache."""

    @pytest.fixture
    def mock_redis(self) -> AsyncMock:
        """Create mock Redis client."""
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock(return_value=True)
        redis.delete = AsyncMock(return_value=1)
        redis.exists = AsyncMock(return_value=1)
        redis.mget = AsyncMock(return_value=[])
        redis.scan = AsyncMock(return_value=(0, []))
        return redis

    @pytest.fixture
    def cache(self, mock_redis: AsyncMock) -> SignalMetadataCache:
        """Create cache instance."""
        return SignalMetadataCache(mock_redis)

    @pytest.mark.asyncio
    async def test_get_miss(self, cache: SignalMetadataCache) -> None:
        """Test cache miss."""
        result = await cache.get("sig-123")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_and_get(
        self, cache: SignalMetadataCache, mock_redis: AsyncMock
    ) -> None:
        """Test setting and getting cache value."""
        import json

        # Set value
        await cache.set("sig-123", {"delivered": True, "latency_ms": 50})

        # Mock get to return the value
        entry = SignalMetadataEntry(
            signal_id="sig-123",
            delivered=True,
            latency_ms=50,
        )
        mock_redis.get = AsyncMock(return_value=json.dumps(entry.to_dict()))

        # Get value
        result = await cache.get("sig-123")

        assert result is not None
        assert result.signal_id == "sig-123"
        assert result.delivered is True

    @pytest.mark.asyncio
    async def test_mark_delivered(
        self, cache: SignalMetadataCache, mock_redis: AsyncMock
    ) -> None:
        """Test marking signal as delivered."""
        result = await cache.mark_delivered("sig-123", 50.0, "exchange")

        assert result is True
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_exists(self, cache: SignalMetadataCache) -> None:
        """Test checking if key exists."""
        result = await cache.exists("sig-123")

        assert result is True

    @pytest.mark.asyncio
    async def test_delete(self, cache: SignalMetadataCache) -> None:
        """Test deleting cache entry."""
        result = await cache.delete("sig-123")

        assert result is True


class TestSignalMetadataEntry:
    """Tests for SignalMetadataEntry."""

    def test_create_entry(self) -> None:
        """Test creating entry."""
        entry = SignalMetadataEntry(
            signal_id="sig-123",
            delivered=True,
            latency_ms=50.0,
            target="exchange",
        )

        assert entry.signal_id == "sig-123"
        assert entry.delivered is True

    def test_to_dict(self) -> None:
        """Test serialization."""
        entry = SignalMetadataEntry(
            signal_id="sig-123",
            delivered=True,
            latency_ms=50.0,
        )

        data = entry.to_dict()

        assert data["signal_id"] == "sig-123"
        assert data["delivered"] is True
        assert data["latency_ms"] == 50.0

    def test_from_dict(self) -> None:
        """Test deserialization."""
        data = {
            "signal_id": "sig-123",
            "delivered": True,
            "latency_ms": 50.0,
            "target": "exchange",
            "retry_count": 0,
            "metadata": {},
        }

        entry = SignalMetadataEntry.from_dict(data)

        assert entry.signal_id == "sig-123"
        assert entry.delivered is True
        assert entry.latency_ms == 50.0


class TestLatencyMonitor:
    """Tests for LatencyMonitor."""

    @pytest.fixture
    def monitor(self) -> LatencyMonitor:
        """Create monitor instance."""
        return LatencyMonitor()

    def test_record_metric(self, monitor: LatencyMonitor) -> None:
        """Test recording a metric."""
        metric = LatencyMetric(
            signal_id="sig-123",
            stage="delivery",
            latency_ms=100,
        )

        is_slow = monitor.record(metric)

        assert is_slow is False  # 100ms is not slow

    def test_record_slow_metric(self, monitor: LatencyMonitor) -> None:
        """Test recording a slow metric."""
        metric = LatencyMetric(
            signal_id="sig-123",
            stage="delivery",
            latency_ms=600,  # Exceeds 500ms warning threshold
        )

        is_slow = monitor.record(metric)

        assert is_slow is True

    def test_get_stats(self, monitor: LatencyMonitor) -> None:
        """Test getting statistics."""
        # Record some metrics
        for i in range(10):
            monitor.record(
                LatencyMetric(
                    signal_id=f"sig-{i}",
                    stage="delivery",
                    latency_ms=100 + i * 10,
                )
            )

        stats = monitor.get_stats("delivery")

        assert stats.count == 10
        assert stats.min_ms == 100
        assert stats.max_ms == 190
        assert stats.p95_ms > 0

    def test_get_slow_metrics(self, monitor: LatencyMonitor) -> None:
        """Test getting slow metrics."""
        # Record fast and slow metrics
        for i in range(5):
            monitor.record(
                LatencyMetric(
                    signal_id=f"sig-fast-{i}",
                    stage="delivery",
                    latency_ms=100,
                )
            )

        for i in range(3):
            monitor.record(
                LatencyMetric(
                    signal_id=f"sig-slow-{i}",
                    stage="delivery",
                    latency_ms=600,  # Slow
                )
            )

        slow = monitor.get_slow_metrics("delivery")

        assert len(slow) == 3

    def test_get_summary(self, monitor: LatencyMonitor) -> None:
        """Test getting latency summary."""
        for i in range(10):
            monitor.record(
                LatencyMetric(
                    signal_id=f"sig-{i}",
                    stage="delivery",
                    latency_ms=100,
                )
            )

        summary = monitor.get_summary()

        assert summary["total_metrics"] == 10
        assert "overall_stats" in summary
        assert "stages" in summary

    def test_check_thresholds(self, monitor: LatencyMonitor) -> None:
        """Test threshold checking."""
        # Record metrics that exceed p95 target
        for i in range(20):
            monitor.record(
                LatencyMetric(
                    signal_id=f"sig-{i}",
                    stage="delivery",
                    latency_ms=900,  # Exceeds p95 target of 800ms
                )
            )

        violations = monitor.check_thresholds()

        assert len(violations) > 0
        assert any(v["type"] == "p95_exceeded" for v in violations)

    def test_stage_breakdown(self, monitor: LatencyMonitor) -> None:
        """Test stage breakdown."""
        # Record metrics for different stages
        for i in range(5):
            monitor.record(
                LatencyMetric(
                    signal_id=f"sig-{i}",
                    stage="delivery",
                    latency_ms=100,
                )
            )

        for i in range(5):
            monitor.record(
                LatencyMetric(
                    signal_id=f"sig-{i}",
                    stage="validation",
                    latency_ms=50,
                )
            )

        breakdown = monitor.get_stage_breakdown()

        assert "delivery" in breakdown
        assert "validation" in breakdown

    def test_health_check(self, monitor: LatencyMonitor) -> None:
        """Test health check."""
        # Record healthy metrics
        for i in range(10):
            monitor.record(
                LatencyMetric(
                    signal_id=f"sig-{i}",
                    stage="delivery",
                    latency_ms=100,
                )
            )

        result = monitor.health_check()

        assert result["status"] == "healthy"


class TestLatencyThresholds:
    """Tests for LatencyThresholds."""

    def test_default_thresholds(self) -> None:
        """Test default thresholds."""
        thresholds = LatencyThresholds.default()
        assert thresholds.warning_ms == 500.0
        assert thresholds.critical_ms == 1000.0

    def test_strict_thresholds(self) -> None:
        """Test strict thresholds."""
        thresholds = LatencyThresholds.strict()
        assert thresholds.warning_ms < LatencyThresholds.default().warning_ms


class TestLatencyMetric:
    """Tests for LatencyMetric."""

    def test_is_slow(self) -> None:
        """Test slow detection."""
        metric = LatencyMetric(
            signal_id="sig-123",
            stage="delivery",
            latency_ms=600,
        )

        assert metric.is_slow() is True

    def test_is_fast(self) -> None:
        """Test fast detection."""
        metric = LatencyMetric(
            signal_id="sig-123",
            stage="delivery",
            latency_ms=100,
        )

        assert metric.is_slow() is False

    def test_to_dict(self) -> None:
        """Test serialization."""
        metric = LatencyMetric(
            signal_id="sig-123",
            stage="delivery",
            latency_ms=100,
            success=True,
        )

        data = metric.to_dict()

        assert data["signal_id"] == "sig-123"
        assert data["stage"] == "delivery"
        assert data["latency_ms"] == 100
