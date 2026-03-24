"""Tests for telemetry ingestion layer.

ST-CONTROL-001: Telemetry Pipeline
"""

import time

from autonomous_control_plane.config.pipeline_settings import (
    BufferConfig,
    IngestionSourceConfig,
    IngestionSourceType,
    RateLimitConfig,
)
from autonomous_control_plane.pipeline.ingestion import (
    CircularBuffer,
    IngestionSource,
    IngestionStatus,
    TelemetryEvent,
    TelemetryIngestionLayer,
    TokenBucketRateLimiter,
)


class TestTokenBucketRateLimiter:
    """Test token bucket rate limiter."""

    def test_initial_tokens_at_burst_size(self):
        """Test that initial tokens equal burst size."""
        limiter = TokenBucketRateLimiter(rate=10, burst_size=5)
        assert limiter.tokens == 5

    def test_acquire_tokens(self):
        """Test acquiring tokens."""
        limiter = TokenBucketRateLimiter(rate=10, burst_size=5)
        assert limiter.acquire(1) is True
        assert limiter.tokens == 4

    def test_acquire_fails_when_empty(self):
        """Test that acquire fails when no tokens available."""
        limiter = TokenBucketRateLimiter(rate=1, burst_size=1)
        assert limiter.acquire(1) is True
        assert limiter.acquire(1) is False

    def test_token_refill_over_time(self):
        """Test that tokens refill over time."""
        limiter = TokenBucketRateLimiter(rate=100, burst_size=1)
        assert limiter.acquire(1) is True
        time.sleep(0.02)  # Wait for refill
        assert limiter.get_available_tokens() > 0


class TestCircularBuffer:
    """Test circular buffer."""

    def test_put_and_get(self):
        """Test putting and getting events."""
        buffer = CircularBuffer(max_size=10)
        event = TelemetryEvent(
            source_type=IngestionSourceType.LOGS,
            timestamp=time.time(),
            data={"test": "data"},
        )

        assert buffer.put(event) is True
        retrieved = buffer.get(timeout=0.1)
        assert retrieved is not None
        assert retrieved.event_id == event.event_id

    def test_buffer_full_drop_oldest(self):
        """Test that oldest events are dropped when buffer full."""
        buffer = CircularBuffer(max_size=2, overflow_strategy="drop_oldest")

        event1 = TelemetryEvent(
            source_type=IngestionSourceType.LOGS,
            timestamp=time.time(),
            data={"id": 1},
        )
        event2 = TelemetryEvent(
            source_type=IngestionSourceType.LOGS,
            timestamp=time.time(),
            data={"id": 2},
        )
        event3 = TelemetryEvent(
            source_type=IngestionSourceType.LOGS,
            timestamp=time.time(),
            data={"id": 3},
        )

        buffer.put(event1)
        buffer.put(event2)
        buffer.put(event3)  # Should drop event1

        # event1 should be dropped, event2 and event3 remain
        assert buffer.size() == 2

    def test_buffer_full_drop_newest(self):
        """Test that newest events are dropped when buffer full."""
        buffer = CircularBuffer(max_size=2, overflow_strategy="drop_newest")

        event1 = TelemetryEvent(
            source_type=IngestionSourceType.LOGS,
            timestamp=time.time(),
            data={"id": 1},
        )
        event2 = TelemetryEvent(
            source_type=IngestionSourceType.LOGS,
            timestamp=time.time(),
            data={"id": 2},
        )
        event3 = TelemetryEvent(
            source_type=IngestionSourceType.LOGS,
            timestamp=time.time(),
            data={"id": 3},
        )

        buffer.put(event1)
        buffer.put(event2)
        result = buffer.put(event3)  # Should fail

        assert result is False
        assert buffer.size() == 2

    def test_get_batch(self):
        """Test getting batch of events."""
        buffer = CircularBuffer(max_size=10)

        for i in range(5):
            buffer.put(
                TelemetryEvent(
                    source_type=IngestionSourceType.LOGS,
                    timestamp=time.time(),
                    data={"id": i},
                )
            )

        batch = buffer.get_batch(max_size=3, timeout=0.1)
        assert len(batch) == 3
        assert buffer.size() == 2

    def test_clear(self):
        """Test clearing buffer."""
        buffer = CircularBuffer(max_size=10)

        for i in range(5):
            buffer.put(
                TelemetryEvent(
                    source_type=IngestionSourceType.LOGS,
                    timestamp=time.time(),
                    data={"id": i},
                )
            )

        events = buffer.clear()
        assert len(events) == 5
        assert buffer.size() == 0


class TestIngestionSource:
    """Test ingestion source."""

    def test_ingest_accepted(self):
        """Test that valid events are accepted."""
        config = IngestionSourceConfig(
            name="test",
            source_type=IngestionSourceType.LOGS,
            rate_limit=RateLimitConfig(enabled=False),
        )
        source = IngestionSource(config)

        result = source.ingest({"message": "test"})

        assert result.status == IngestionStatus.ACCEPTED
        assert result.event_id is not None

    def test_ingest_disabled_source(self):
        """Test that disabled source rejects events."""
        config = IngestionSourceConfig(
            name="test",
            source_type=IngestionSourceType.LOGS,
            enabled=False,
        )
        source = IngestionSource(config)

        result = source.ingest({"message": "test"})

        assert result.status == IngestionStatus.REJECTED_FILTERED

    def test_ingest_rate_limited(self):
        """Test rate limiting."""
        config = IngestionSourceConfig(
            name="test",
            source_type=IngestionSourceType.LOGS,
            rate_limit=RateLimitConfig(
                enabled=True,
                events_per_second=1,
                burst_size=1,
            ),
        )
        source = IngestionSource(config)

        # First event should succeed
        result1 = source.ingest({"message": "test1"})
        assert result1.status == IngestionStatus.ACCEPTED

        # Second event should be rate limited
        result2 = source.ingest({"message": "test2"})
        assert result2.status == IngestionStatus.REJECTED_RATE_LIMIT

    def test_ingest_sampling(self):
        """Test sampling."""
        config = IngestionSourceConfig(
            name="test",
            source_type=IngestionSourceType.LOGS,
            rate_limit=RateLimitConfig(enabled=False),
            sampling_rate=0.0,  # Drop all
        )
        source = IngestionSource(config)

        result = source.ingest({"message": "test"})
        assert result.status == IngestionStatus.REJECTED_SAMPLING

    def test_filter_rules(self):
        """Test filter rules."""
        config = IngestionSourceConfig(
            name="test",
            source_type=IngestionSourceType.LOGS,
            rate_limit=RateLimitConfig(enabled=False),
            filters=[
                {"field": "level", "operator": "eq", "value": "error"},
            ],
        )
        source = IngestionSource(config)

        # Event matching filter should be accepted
        result1 = source.ingest({"message": "test", "level": "error"})
        assert result1.status == IngestionStatus.ACCEPTED

        # Event not matching filter should be rejected
        result2 = source.ingest({"message": "test", "level": "info"})
        assert result2.status == IngestionStatus.REJECTED_FILTERED

    def test_get_metrics(self):
        """Test getting ingestion metrics."""
        config = IngestionSourceConfig(
            name="test",
            source_type=IngestionSourceType.LOGS,
            rate_limit=RateLimitConfig(enabled=False),
        )
        source = IngestionSource(config)

        source.ingest({"message": "test1"})
        source.ingest({"message": "test2"})

        metrics = source.get_metrics()
        assert metrics["accepted"] == 2


class TestTelemetryIngestionLayer:
    """Test telemetry ingestion layer."""

    def test_get_source(self):
        """Test getting source by name."""
        layer = TelemetryIngestionLayer()

        source = layer.get_source("logs")
        assert source is not None
        assert source.name == "logs"

    def test_ingest_log(self):
        """Test log ingestion."""
        layer = TelemetryIngestionLayer()

        result = layer.ingest_log({"message": "test", "level": "info"})
        assert result.status == IngestionStatus.ACCEPTED

    def test_ingest_metric(self):
        """Test metric ingestion."""
        layer = TelemetryIngestionLayer()

        result = layer.ingest_metric({"metric_name": "test", "value": 42.0})
        assert result.status == IngestionStatus.ACCEPTED

    def test_ingest_event(self):
        """Test event ingestion."""
        layer = TelemetryIngestionLayer()

        result = layer.ingest_event({"event_type": "test"})
        assert result.status == IngestionStatus.ACCEPTED

    def test_get_all_metrics(self):
        """Test getting metrics from all sources."""
        layer = TelemetryIngestionLayer()

        layer.ingest_log({"message": "test"})
        layer.ingest_metric({"metric_name": "test", "value": 1.0})

        metrics = layer.get_all_metrics()
        assert "logs" in metrics
        assert "metrics" in metrics

    def test_get_backpressure_status(self):
        """Test getting backpressure status."""
        layer = TelemetryIngestionLayer()

        status = layer.get_backpressure_status()
        assert "utilization" in status
        assert "is_under_backpressure" in status
        assert "source_stats" in status

    def test_add_and_remove_source(self):
        """Test adding and removing sources."""
        layer = TelemetryIngestionLayer()

        config = IngestionSourceConfig(
            name="custom",
            source_type=IngestionSourceType.TRACES,
        )
        source = layer.add_source(config)
        assert source.name == "custom"

        removed = layer.remove_source("custom")
        assert removed is not None

        # Should return None for non-existent source
        removed = layer.remove_source("custom")
        assert removed is None


class TestIngestionPerformance:
    """Test ingestion performance requirements."""

    def test_ingestion_rate(self):
        """Test that ingestion can handle high event rates."""
        config = IngestionSourceConfig(
            name="test",
            source_type=IngestionSourceType.LOGS,
            buffer=BufferConfig(max_size=100000),
            rate_limit=RateLimitConfig(enabled=False),
        )
        source = IngestionSource(config)

        # Ingest 1000 events
        start_time = time.time()
        for i in range(1000):
            source.ingest({"id": i, "data": "x" * 100})
        elapsed = time.time() - start_time

        # Should handle 1000 events in less than 1 second
        assert elapsed < 1.0
        assert source.get_metrics()["accepted"] == 1000
