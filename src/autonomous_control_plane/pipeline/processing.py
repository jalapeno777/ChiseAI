"""Telemetry processing layer for the autonomous control plane.

Provides data transformation, enrichment, aggregation windows,
and metric derivation (rates, percentiles, derivatives).

ST-CONTROL-001: Telemetry Pipeline
"""

from __future__ import annotations

import logging
import statistics
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable

from autonomous_control_plane.config.pipeline_settings import (
    AggregationWindow,
    ProcessingConfig,
    pipeline_settings,
)
from autonomous_control_plane.pipeline.ingestion import TelemetryEvent

logger = logging.getLogger(__name__)


@dataclass
class ProcessedMetric:
    """A processed and aggregated metric."""

    name: str
    timestamp: float
    window: AggregationWindow
    tags: dict[str, str] = field(default_factory=dict)
    fields: dict[str, float | int] = field(default_factory=dict)
    source_events: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "timestamp": self.timestamp,
            "window_seconds": self.window.value,
            "tags": self.tags,
            "fields": self.fields,
            "source_events": self.source_events,
            "metadata": self.metadata,
        }


@dataclass
class AggregationBucket:
    """A bucket for aggregating metrics over a time window."""

    window_start: float
    window: AggregationWindow
    values: list[float] = field(default_factory=list)
    counters: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    tags: dict[str, str] = field(default_factory=dict)

    def add_value(self, value: float) -> None:
        """Add a value to the bucket."""
        self.values.append(value)

    def increment_counter(self, name: str, delta: int = 1) -> None:
        """Increment a counter."""
        self.counters[name] += delta

    def compute_stats(self) -> dict[str, float | int]:
        """Compute statistics for the bucket."""
        if not self.values:
            return {
                "count": 0,
                "sum": 0,
                "mean": 0.0,
                "min": 0.0,
                "max": 0.0,
            }

        stats = {
            "count": len(self.values),
            "sum": sum(self.values),
            "mean": statistics.mean(self.values),
            "min": min(self.values),
            "max": max(self.values),
        }

        # Compute percentiles if enough values
        if len(self.values) >= 2:
            try:
                stats["p50"] = statistics.median(self.values)
                if len(self.values) >= 4:
                    stats["p95"] = self._percentile(self.values, 95)
                    stats["p99"] = self._percentile(self.values, 99)
            except statistics.StatisticsError:
                pass

        return stats

    @staticmethod
    def _percentile(data: list[float], percentile: float) -> float:
        """Calculate percentile using nearest-rank method."""
        sorted_data = sorted(data)
        index = int(len(sorted_data) * percentile / 100)
        return sorted_data[min(index, len(sorted_data) - 1)]

    def is_expired(self, now: float) -> bool:
        """Check if bucket has expired (window passed)."""
        return now >= self.window_start + self.window.value


class MetricAggregator:
    """Aggregates metrics over time windows."""

    def __init__(self, window: AggregationWindow, config: ProcessingConfig):
        """Initialize aggregator.

        Args:
            window: Aggregation window size
            config: Processing configuration
        """
        self.window = window
        self.config = config
        self._buckets: dict[str, AggregationBucket] = {}
        self._lock: Any = None  # Will use threading.Lock in real implementation

    def get_bucket_key(self, event: TelemetryEvent) -> str:
        """Generate bucket key from event tags."""
        # Group by metric name and relevant tags
        tags_str = ":".join(f"{k}={v}" for k, v in sorted(event.metadata.items()))
        return f"{event.data.get('metric_name', 'unknown')}:{tags_str}"

    def add_event(self, event: TelemetryEvent) -> None:
        """Add an event to the appropriate bucket."""
        bucket_key = self.get_bucket_key(event)
        now = time.time()
        window_start = (now // self.window.value) * self.window.value

        if bucket_key not in self._buckets:
            self._buckets[bucket_key] = AggregationBucket(
                window_start=window_start,
                window=self.window,
                tags=event.metadata.copy(),
            )

        bucket = self._buckets[bucket_key]

        # Check if we need to roll to new window
        if bucket.is_expired(now):
            # Start new bucket
            bucket = AggregationBucket(
                window_start=window_start,
                window=self.window,
                tags=event.metadata.copy(),
            )
            self._buckets[bucket_key] = bucket

        # Extract value from event
        value = event.data.get("value")
        if value is not None:
            try:
                bucket.add_value(float(value))
            except (TypeError, ValueError):
                pass

        # Increment counters
        counter_name = event.data.get("counter_name")
        if counter_name:
            bucket.increment_counter(counter_name)

    def get_expired_buckets(self) -> list[AggregationBucket]:
        """Get all expired buckets."""
        now = time.time()
        expired = []
        expired_keys = []

        for key, bucket in self._buckets.items():
            if bucket.is_expired(now):
                expired.append(bucket)
                expired_keys.append(key)

        # Remove expired buckets
        for key in expired_keys:
            del self._buckets[key]

        return expired

    def flush(self) -> list[ProcessedMetric]:
        """Flush expired buckets into processed metrics."""
        expired_buckets = self.get_expired_buckets()
        metrics = []

        for bucket in expired_buckets:
            stats = bucket.compute_stats()
            metric = ProcessedMetric(
                name=bucket.tags.get("metric_name", "unknown"),
                timestamp=bucket.window_start,
                window=self.window,
                tags=bucket.tags,
                fields=stats,
                source_events=stats.get("count", 0),
            )
            metrics.append(metric)

        return metrics


class MetricDeriver:
    """Derives additional metrics from raw values."""

    def __init__(self, config: ProcessingConfig):
        """Initialize deriver.

        Args:
            config: Processing configuration
        """
        self.config = config
        self._previous_values: dict[str, tuple[float, float]] = {}
        # (timestamp, value) by metric key

    def derive_rate(
        self, metric_name: str, current_value: float, timestamp: float
    ) -> float | None:
        """Calculate rate of change (per second).

        Args:
            metric_name: Name of the metric
            current_value: Current value
            timestamp: Current timestamp

        Returns:
            Rate or None if no previous value
        """
        if not self.config.derive_rates:
            return None

        key = f"{metric_name}:rate"
        prev = self._previous_values.get(key)

        if prev is None:
            self._previous_values[key] = (timestamp, current_value)
            return None

        prev_time, prev_value = prev
        time_delta = timestamp - prev_time

        if time_delta <= 0:
            return None

        value_delta = current_value - prev_value
        rate = value_delta / time_delta

        self._previous_values[key] = (timestamp, current_value)
        return rate

    def derive_derivative(
        self, metric_name: str, current_value: float, timestamp: float
    ) -> float | None:
        """Calculate derivative (second derivative of value).

        Args:
            metric_name: Name of the metric
            current_value: Current value
            timestamp: Current timestamp

        Returns:
            Derivative or None if insufficient history
        """
        if not self.config.derive_derivatives:
            return None

        # First get the rate
        rate_key = f"{metric_name}:rate"
        deriv_key = f"{metric_name}:derivative"

        prev_rate = self._previous_values.get(rate_key)
        if prev_rate is None:
            # Store current rate calculation
            self.derive_rate(metric_name, current_value, timestamp)
            return None

        prev_time, prev_value = prev_rate
        time_delta = timestamp - prev_time

        if time_delta <= 0:
            return None

        current_rate = (current_value - prev_value) / time_delta
        prev_deriv = self._previous_values.get(deriv_key)

        if prev_deriv is None:
            self._previous_values[deriv_key] = (timestamp, current_rate)
            return None

        _, prev_rate_value = prev_deriv
        derivative = (current_rate - prev_rate_value) / time_delta

        self._previous_values[deriv_key] = (timestamp, current_rate)
        return derivative

    def derive_percentiles(
        self, values: list[float], percentiles: list[float] | None = None
    ) -> dict[str, float]:
        """Calculate percentiles for a list of values.

        Args:
            values: List of values
            percentiles: Percentiles to calculate (uses config if not provided)

        Returns:
            Dictionary of percentile name to value
        """
        if not values:
            return {}

        percentiles = percentiles or self.config.derive_percentiles
        result = {}

        sorted_values = sorted(values)
        for p in percentiles:
            index = int(len(sorted_values) * p / 100)
            result[f"p{int(p)}"] = sorted_values[min(index, len(sorted_values) - 1)]

        return result

    def clear_history(self, metric_name: str | None = None) -> None:
        """Clear derivation history.

        Args:
            metric_name: Clear only this metric (None for all)
        """
        if metric_name is None:
            self._previous_values.clear()
        else:
            keys_to_remove = [
                k for k in self._previous_values.keys() if k.startswith(metric_name)
            ]
            for key in keys_to_remove:
                del self._previous_values[key]


class DataEnricher:
    """Enriches telemetry data with additional context."""

    def __init__(self, config: ProcessingConfig):
        """Initialize enricher.

        Args:
            config: Processing configuration
        """
        self.config = config
        self._enrichment_functions: dict[
            str, Callable[[dict[str, Any]], dict[str, Any]]
        ] = {}

    def register_enrichment(
        self, name: str, func: Callable[[dict[str, Any]], dict[str, Any]]
    ) -> None:
        """Register an enrichment function.

        Args:
            name: Name of the enrichment
            func: Function that takes data dict and returns enriched data
        """
        self._enrichment_functions[name] = func

    def enrich(self, event: TelemetryEvent) -> TelemetryEvent:
        """Enrich a telemetry event.

        Args:
            event: Event to enrich

        Returns:
            Enriched event
        """
        enriched_data = event.data.copy()

        for rule in self.config.enrichment_rules:
            rule_type = rule.get("type")
            if rule_type == "add_tag":
                tag_name = rule.get("tag_name")
                tag_value = rule.get("tag_value")
                if tag_name and tag_value:
                    event.metadata[tag_name] = tag_value
            elif rule_type == "add_field":
                field_name = rule.get("field_name")
                field_value = rule.get("field_value")
                if field_name is not None:
                    enriched_data[field_name] = field_value
            elif rule_type == "compute":
                # Compute derived fields
                source_fields = rule.get("source_fields", [])
                target_field = rule.get("target_field")
                operation = rule.get("operation")

                if target_field and operation:
                    values = [enriched_data.get(f) for f in source_fields]
                    values = [v for v in values if v is not None]

                    if values:
                        if operation == "sum":
                            enriched_data[target_field] = sum(values)
                        elif operation == "avg":
                            enriched_data[target_field] = sum(values) / len(values)
                        elif operation == "max":
                            enriched_data[target_field] = max(values)
                        elif operation == "min":
                            enriched_data[target_field] = min(values)

        # Apply registered enrichment functions
        for name, func in self._enrichment_functions.items():
            try:
                enriched_data = func(enriched_data)
            except Exception as e:
                logger.warning(f"Enrichment '{name}' failed: {e}")

        return TelemetryEvent(
            source_type=event.source_type,
            timestamp=event.timestamp,
            data=enriched_data,
            metadata=event.metadata.copy(),
            event_id=event.event_id,
        )


class DataFilter:
    """Filters telemetry data based on rules."""

    def __init__(self, config: ProcessingConfig):
        """Initialize filter.

        Args:
            config: Processing configuration
        """
        self.config = config

    def should_keep(self, event: TelemetryEvent) -> bool:
        """Check if event should be kept.

        Args:
            event: Event to check

        Returns:
            True if event passes all filters
        """
        for rule in self.config.filter_rules:
            if not self._apply_rule(event, rule):
                return False
        return True

    def _apply_rule(self, event: TelemetryEvent, rule: dict[str, Any]) -> bool:
        """Apply a single filter rule.

        Args:
            event: Event to check
            rule: Filter rule

        Returns:
            True if event passes the rule
        """
        field = rule.get("field")
        operator = rule.get("operator")
        value = rule.get("value")

        if not field or not operator:
            return True

        # Check in both data and metadata
        event_value = event.data.get(field) or event.metadata.get(field)

        if operator == "eq":
            return event_value == value
        elif operator == "ne":
            return event_value != value
        elif operator == "gt":
            try:
                return float(event_value) > float(value)  # type: ignore
            except (TypeError, ValueError):
                return False
        elif operator == "gte":
            try:
                return float(event_value) >= float(value)  # type: ignore
            except (TypeError, ValueError):
                return False
        elif operator == "lt":
            try:
                return float(event_value) < float(value)  # type: ignore
            except (TypeError, ValueError):
                return False
        elif operator == "lte":
            try:
                return float(event_value) <= float(value)  # type: ignore
            except (TypeError, ValueError):
                return False
        elif operator == "contains":
            return value in str(event_value)
        elif operator == "starts_with":
            return str(event_value).startswith(str(value))
        elif operator == "ends_with":
            return str(event_value).endswith(str(value))
        elif operator == "in":
            return event_value in (value if isinstance(value, list) else [value])
        elif operator == "not_in":
            return event_value not in (value if isinstance(value, list) else [value])

        return True


class TelemetryProcessingLayer:
    """Telemetry processing layer with aggregation and enrichment.

    Processes telemetry events through aggregation windows, derives metrics,
    and enriches data with additional context.

    Example:
        >>> processing = TelemetryProcessingLayer()
        >>> processing.process_event(event)
        >>> metrics = processing.flush()
    """

    def __init__(self, config: ProcessingConfig | None = None):
        """Initialize processing layer.

        Args:
            config: Processing configuration (uses default if not provided)
        """
        self.config = config or pipeline_settings.processing

        # Aggregators for each window
        self._aggregators: dict[AggregationWindow, MetricAggregator] = {
            window: MetricAggregator(window, self.config)
            for window in self.config.aggregation_windows
        }

        # Deriver for computed metrics
        self._deriver = MetricDeriver(self.config)

        # Enricher for data enrichment
        self._enricher = DataEnricher(self.config)

        # Filter for data filtering
        self._filter = DataFilter(self.config)

        # Metrics
        self._processed_count = 0
        self._filtered_count = 0
        self._enriched_count = 0

    def process_event(self, event: TelemetryEvent) -> TelemetryEvent | None:
        """Process a single telemetry event.

        Args:
            event: Event to process

        Returns:
            Processed event or None if filtered out
        """
        if not self.config.enabled:
            return event

        # Apply filtering
        if not self._filter.should_keep(event):
            self._filtered_count += 1
            return None

        # Apply enrichment
        event = self._enricher.enrich(event)
        self._enriched_count += 1

        # Add to aggregators
        for aggregator in self._aggregators.values():
            aggregator.add_event(event)

        self._processed_count += 1
        return event

    def process_batch(self, events: list[TelemetryEvent]) -> list[TelemetryEvent]:
        """Process a batch of events.

        Args:
            events: Events to process

        Returns:
            List of processed events (filtered events removed)
        """
        return [e for e in (self.process_event(ev) for ev in events) if e is not None]

    def flush(self) -> list[ProcessedMetric]:
        """Flush all aggregators and return processed metrics.

        Returns:
            List of processed metrics
        """
        all_metrics = []

        for window, aggregator in self._aggregators.items():
            metrics = aggregator.flush()

            # Derive additional metrics
            for metric in metrics:
                if self.config.derive_rates and "sum" in metric.fields:
                    rate = self._deriver.derive_rate(
                        metric.name,
                        float(metric.fields["sum"]),
                        metric.timestamp,
                    )
                    if rate is not None:
                        metric.fields["rate"] = rate

                if self.config.derive_derivatives and "rate" in metric.fields:
                    deriv = self._deriver.derive_derivative(
                        metric.name,
                        float(metric.fields["rate"]),
                        metric.timestamp,
                    )
                    if deriv is not None:
                        metric.fields["derivative"] = deriv

            all_metrics.extend(metrics)

        return all_metrics

    def get_metrics(self) -> dict[str, Any]:
        """Get processing metrics."""
        return {
            "processed_count": self._processed_count,
            "filtered_count": self._filtered_count,
            "enriched_count": self._enriched_count,
            "aggregation_windows": [w.value for w in self._aggregators.keys()],
            "pending_buckets": sum(
                len(agg._buckets) for agg in self._aggregators.values()
            ),
        }

    def register_enrichment(
        self, name: str, func: Callable[[dict[str, Any]], dict[str, Any]]
    ) -> None:
        """Register a custom enrichment function."""
        self._enricher.register_enrichment(name, func)

    def clear(self) -> None:
        """Clear all processing state."""
        for aggregator in self._aggregators.values():
            aggregator._buckets.clear()
        self._deriver.clear_history()
        self._processed_count = 0
        self._filtered_count = 0
        self._enriched_count = 0


# Singleton instance
processing_layer: TelemetryProcessingLayer | None = None


def get_processing_layer() -> TelemetryProcessingLayer:
    """Get global processing layer instance."""
    global processing_layer
    if processing_layer is None:
        processing_layer = TelemetryProcessingLayer()
    return processing_layer
