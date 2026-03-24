"""Tests for telemetry processing layer.

ST-CONTROL-001: Telemetry Pipeline
"""

import time

from autonomous_control_plane.config.pipeline_settings import (
    AggregationWindow,
    ProcessingConfig,
)
from autonomous_control_plane.pipeline.ingestion import (
    IngestionSourceType,
    TelemetryEvent,
)
from autonomous_control_plane.pipeline.processing import (
    AggregationBucket,
    DataEnricher,
    DataFilter,
    MetricAggregator,
    MetricDeriver,
    ProcessedMetric,
    TelemetryProcessingLayer,
)


class TestAggregationBucket:
    """Test aggregation bucket."""

    def test_add_value(self):
        """Test adding values to bucket."""
        bucket = AggregationBucket(
            window_start=time.time(),
            window=AggregationWindow.ONE_MINUTE,
        )

        bucket.add_value(10.0)
        bucket.add_value(20.0)
        bucket.add_value(30.0)

        assert len(bucket.values) == 3

    def test_compute_stats(self):
        """Test computing bucket statistics."""
        bucket = AggregationBucket(
            window_start=time.time(),
            window=AggregationWindow.ONE_MINUTE,
        )

        bucket.add_value(10.0)
        bucket.add_value(20.0)
        bucket.add_value(30.0)

        stats = bucket.compute_stats()

        assert stats["count"] == 3
        assert stats["sum"] == 60.0
        assert stats["mean"] == 20.0
        assert stats["min"] == 10.0
        assert stats["max"] == 30.0
        assert "p50" in stats

    def test_empty_bucket_stats(self):
        """Test stats for empty bucket."""
        bucket = AggregationBucket(
            window_start=time.time(),
            window=AggregationWindow.ONE_MINUTE,
        )

        stats = bucket.compute_stats()

        assert stats["count"] == 0
        assert stats["sum"] == 0
        assert stats["mean"] == 0.0

    def test_increment_counter(self):
        """Test incrementing counters."""
        bucket = AggregationBucket(
            window_start=time.time(),
            window=AggregationWindow.ONE_MINUTE,
        )

        bucket.increment_counter("errors")
        bucket.increment_counter("errors")
        bucket.increment_counter("warnings")

        assert bucket.counters["errors"] == 2
        assert bucket.counters["warnings"] == 1

    def test_is_expired(self):
        """Test bucket expiration."""
        bucket = AggregationBucket(
            window_start=time.time() - 120,  # 2 minutes ago
            window=AggregationWindow.ONE_MINUTE,
        )

        assert bucket.is_expired(time.time()) is True

        fresh_bucket = AggregationBucket(
            window_start=time.time(),
            window=AggregationWindow.ONE_MINUTE,
        )

        assert fresh_bucket.is_expired(time.time()) is False


class TestMetricAggregator:
    """Test metric aggregator."""

    def test_add_event(self):
        """Test adding events to aggregator."""
        config = ProcessingConfig()
        aggregator = MetricAggregator(AggregationWindow.ONE_MINUTE, config)

        event = TelemetryEvent(
            source_type=IngestionSourceType.METRICS,
            timestamp=time.time(),
            data={"metric_name": "test", "value": 42.0},
            metadata={"host": "server1"},
        )

        aggregator.add_event(event)

        assert len(aggregator._buckets) > 0

    def test_flush(self):
        """Test flushing expired buckets."""
        config = ProcessingConfig()
        aggregator = MetricAggregator(AggregationWindow.ONE_MINUTE, config)

        # Add event with old timestamp to force expiration
        old_time = time.time() - 120  # 2 minutes ago
        event = TelemetryEvent(
            source_type=IngestionSourceType.METRICS,
            timestamp=old_time,
            data={"metric_name": "test", "value": 42.0},
            metadata={"host": "server1"},
        )

        aggregator.add_event(event)

        # Manually set bucket to expired
        for bucket in aggregator._buckets.values():
            bucket.window_start = old_time - 60

        metrics = aggregator.flush()

        assert len(metrics) > 0
        assert all(isinstance(m, ProcessedMetric) for m in metrics)

    def test_multiple_windows(self):
        """Test aggregation across multiple windows."""
        config = ProcessingConfig()

        aggregators = {
            window: MetricAggregator(window, config)
            for window in [
                AggregationWindow.ONE_MINUTE,
                AggregationWindow.FIVE_MINUTES,
                AggregationWindow.ONE_HOUR,
            ]
        }

        event = TelemetryEvent(
            source_type=IngestionSourceType.METRICS,
            timestamp=time.time(),
            data={"metric_name": "test", "value": 42.0},
            metadata={"host": "server1"},
        )

        for aggregator in aggregators.values():
            aggregator.add_event(event)

        # All aggregators should have the event
        for aggregator in aggregators.values():
            assert len(aggregator._buckets) > 0


class TestMetricDeriver:
    """Test metric deriver."""

    def test_derive_rate(self):
        """Test rate derivation."""
        config = ProcessingConfig(derive_rates=True)
        deriver = MetricDeriver(config)

        # First call returns None (no previous value)
        rate1 = deriver.derive_rate("test_metric", 100.0, time.time())
        assert rate1 is None

        # Second call returns rate
        time.sleep(0.01)
        rate2 = deriver.derive_rate("test_metric", 110.0, time.time())
        assert rate2 is not None
        assert rate2 > 0

    def test_derive_rate_disabled(self):
        """Test rate derivation when disabled."""
        config = ProcessingConfig(derive_rates=False)
        deriver = MetricDeriver(config)

        rate = deriver.derive_rate("test_metric", 100.0, time.time())
        assert rate is None

    def test_derive_percentiles(self):
        """Test percentile derivation."""
        config = ProcessingConfig(derive_percentiles=[50.0, 95.0, 99.0])
        deriver = MetricDeriver(config)

        values = list(range(100))
        percentiles = deriver.derive_percentiles(values)

        assert "p50" in percentiles
        assert "p95" in percentiles
        assert "p99" in percentiles

    def test_clear_history(self):
        """Test clearing derivation history."""
        config = ProcessingConfig(derive_rates=True)
        deriver = MetricDeriver(config)

        deriver.derive_rate("test_metric", 100.0, time.time())
        assert len(deriver._previous_values) > 0

        deriver.clear_history()
        assert len(deriver._previous_values) == 0


class TestDataEnricher:
    """Test data enricher."""

    def test_add_tag_enrichment(self):
        """Test adding tag enrichment."""
        config = ProcessingConfig(
            enrichment_rules=[
                {
                    "type": "add_tag",
                    "tag_name": "environment",
                    "tag_value": "production",
                },
            ]
        )
        enricher = DataEnricher(config)

        event = TelemetryEvent(
            source_type=IngestionSourceType.LOGS,
            timestamp=time.time(),
            data={"message": "test"},
            metadata={},
        )

        enriched = enricher.enrich(event)

        assert enriched.metadata["environment"] == "production"

    def test_add_field_enrichment(self):
        """Test adding field enrichment."""
        config = ProcessingConfig(
            enrichment_rules=[
                {"type": "add_field", "field_name": "processed", "field_value": True},
            ]
        )
        enricher = DataEnricher(config)

        event = TelemetryEvent(
            source_type=IngestionSourceType.LOGS,
            timestamp=time.time(),
            data={"message": "test"},
            metadata={},
        )

        enriched = enricher.enrich(event)

        assert enriched.data["processed"] is True

    def test_compute_enrichment(self):
        """Test compute enrichment."""
        config = ProcessingConfig(
            enrichment_rules=[
                {
                    "type": "compute",
                    "source_fields": ["value1", "value2"],
                    "target_field": "total",
                    "operation": "sum",
                },
            ]
        )
        enricher = DataEnricher(config)

        event = TelemetryEvent(
            source_type=IngestionSourceType.METRICS,
            timestamp=time.time(),
            data={"value1": 10, "value2": 20},
            metadata={},
        )

        enriched = enricher.enrich(event)

        assert enriched.data["total"] == 30


class TestDataFilter:
    """Test data filter."""

    def test_eq_filter(self):
        """Test equality filter."""
        config = ProcessingConfig(
            filter_rules=[
                {"field": "level", "operator": "eq", "value": "error"},
            ]
        )
        filter_obj = DataFilter(config)

        event1 = TelemetryEvent(
            source_type=IngestionSourceType.LOGS,
            timestamp=time.time(),
            data={"level": "error"},
            metadata={},
        )
        event2 = TelemetryEvent(
            source_type=IngestionSourceType.LOGS,
            timestamp=time.time(),
            data={"level": "info"},
            metadata={},
        )

        assert filter_obj.should_keep(event1) is True
        assert filter_obj.should_keep(event2) is False

    def test_gt_filter(self):
        """Test greater-than filter."""
        config = ProcessingConfig(
            filter_rules=[
                {"field": "value", "operator": "gt", "value": 10},
            ]
        )
        filter_obj = DataFilter(config)

        event1 = TelemetryEvent(
            source_type=IngestionSourceType.METRICS,
            timestamp=time.time(),
            data={"value": 20},
            metadata={},
        )
        event2 = TelemetryEvent(
            source_type=IngestionSourceType.METRICS,
            timestamp=time.time(),
            data={"value": 5},
            metadata={},
        )

        assert filter_obj.should_keep(event1) is True
        assert filter_obj.should_keep(event2) is False

    def test_contains_filter(self):
        """Test contains filter."""
        config = ProcessingConfig(
            filter_rules=[
                {"field": "message", "operator": "contains", "value": "error"},
            ]
        )
        filter_obj = DataFilter(config)

        event1 = TelemetryEvent(
            source_type=IngestionSourceType.LOGS,
            timestamp=time.time(),
            data={"message": "An error occurred"},
            metadata={},
        )
        event2 = TelemetryEvent(
            source_type=IngestionSourceType.LOGS,
            timestamp=time.time(),
            data={"message": "Success"},
            metadata={},
        )

        assert filter_obj.should_keep(event1) is True
        assert filter_obj.should_keep(event2) is False


class TestTelemetryProcessingLayer:
    """Test telemetry processing layer."""

    def test_process_event(self):
        """Test processing a single event."""
        layer = TelemetryProcessingLayer()

        event = TelemetryEvent(
            source_type=IngestionSourceType.METRICS,
            timestamp=time.time(),
            data={"metric_name": "test", "value": 42.0},
            metadata={"host": "server1"},
        )

        result = layer.process_event(event)

        assert result is not None
        assert result.event_id == event.event_id

    def test_process_batch(self):
        """Test processing a batch of events."""
        layer = TelemetryProcessingLayer()

        events = [
            TelemetryEvent(
                source_type=IngestionSourceType.METRICS,
                timestamp=time.time(),
                data={"metric_name": "test", "value": float(i)},
                metadata={},
            )
            for i in range(10)
        ]

        results = layer.process_batch(events)

        assert len(results) == 10

    def test_filtering(self):
        """Test that filtering removes events."""
        config = ProcessingConfig(
            filter_rules=[
                {"field": "keep", "operator": "eq", "value": True},
            ]
        )
        layer = TelemetryProcessingLayer(config)

        event1 = TelemetryEvent(
            source_type=IngestionSourceType.LOGS,
            timestamp=time.time(),
            data={"keep": True},
            metadata={},
        )
        event2 = TelemetryEvent(
            source_type=IngestionSourceType.LOGS,
            timestamp=time.time(),
            data={"keep": False},
            metadata={},
        )

        result1 = layer.process_event(event1)
        result2 = layer.process_event(event2)

        assert result1 is not None
        assert result2 is None

    def test_get_metrics(self):
        """Test getting processing metrics."""
        layer = TelemetryProcessingLayer()

        event = TelemetryEvent(
            source_type=IngestionSourceType.METRICS,
            timestamp=time.time(),
            data={"metric_name": "test", "value": 42.0},
            metadata={},
        )

        layer.process_event(event)

        metrics = layer.get_metrics()

        assert metrics["processed_count"] == 1
        assert "aggregation_windows" in metrics

    def test_clear(self):
        """Test clearing processing state."""
        layer = TelemetryProcessingLayer()

        event = TelemetryEvent(
            source_type=IngestionSourceType.METRICS,
            timestamp=time.time(),
            data={"metric_name": "test", "value": 42.0},
            metadata={},
        )

        layer.process_event(event)
        layer.clear()

        metrics = layer.get_metrics()
        assert metrics["processed_count"] == 0


class TestAggregationWindows:
    """Test that all required aggregation windows are supported."""

    def test_one_minute_window(self):
        """Test 1-minute aggregation window."""
        config = ProcessingConfig(aggregation_windows=[AggregationWindow.ONE_MINUTE])
        layer = TelemetryProcessingLayer(config)

        assert AggregationWindow.ONE_MINUTE in layer._aggregators

    def test_five_minute_window(self):
        """Test 5-minute aggregation window."""
        config = ProcessingConfig(aggregation_windows=[AggregationWindow.FIVE_MINUTES])
        layer = TelemetryProcessingLayer(config)

        assert AggregationWindow.FIVE_MINUTES in layer._aggregators

    def test_one_hour_window(self):
        """Test 1-hour aggregation window."""
        config = ProcessingConfig(aggregation_windows=[AggregationWindow.ONE_HOUR])
        layer = TelemetryProcessingLayer(config)

        assert AggregationWindow.ONE_HOUR in layer._aggregators

    def test_all_windows(self):
        """Test all aggregation windows together."""
        config = ProcessingConfig(
            aggregation_windows=[
                AggregationWindow.ONE_MINUTE,
                AggregationWindow.FIVE_MINUTES,
                AggregationWindow.ONE_HOUR,
            ]
        )
        layer = TelemetryProcessingLayer(config)

        assert len(layer._aggregators) == 3
