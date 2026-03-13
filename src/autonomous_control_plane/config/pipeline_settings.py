"""Pipeline configuration settings for telemetry processing.

ST-CONTROL-001: Telemetry Pipeline
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AggregationWindow(Enum):
    """Aggregation window sizes for telemetry processing."""

    ONE_MINUTE = 60
    FIVE_MINUTES = 300
    ONE_HOUR = 3600


class IngestionSourceType(Enum):
    """Types of telemetry ingestion sources."""

    LOGS = "logs"
    METRICS = "metrics"
    EVENTS = "events"
    TRACES = "traces"


class ExportDestinationType(Enum):
    """Types of telemetry export destinations."""

    INFLUXDB = "influxdb"
    POSTGRES = "postgres"
    FILE = "file"
    KAFKA = "kafka"


@dataclass
class BufferConfig:
    """Buffer configuration for ingestion."""

    max_size: int = 50000
    overflow_strategy: str = "drop_oldest"  # drop_oldest, drop_newest, block
    flush_threshold: int = 5000
    flush_interval_seconds: float = 5.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "max_size": self.max_size,
            "overflow_strategy": self.overflow_strategy,
            "flush_threshold": self.flush_threshold,
            "flush_interval_seconds": self.flush_interval_seconds,
        }


@dataclass
class RateLimitConfig:
    """Rate limiting configuration for ingestion."""

    enabled: bool = True
    events_per_second: int = 25000
    burst_size: int = 100000
    backpressure_threshold: float = 0.95  # 95% buffer full triggers backpressure

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "enabled": self.enabled,
            "events_per_second": self.events_per_second,
            "burst_size": self.burst_size,
            "backpressure_threshold": self.backpressure_threshold,
        }


@dataclass
class IngestionSourceConfig:
    """Configuration for a telemetry ingestion source."""

    name: str
    source_type: IngestionSourceType
    enabled: bool = True
    buffer: BufferConfig = field(default_factory=BufferConfig)
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    filters: list[dict[str, Any]] = field(default_factory=list)
    sampling_rate: float = 1.0  # 1.0 = no sampling

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "source_type": self.source_type.value,
            "enabled": self.enabled,
            "buffer": self.buffer.to_dict(),
            "rate_limit": self.rate_limit.to_dict(),
            "filters": self.filters,
            "sampling_rate": self.sampling_rate,
        }


@dataclass
class ProcessingConfig:
    """Configuration for telemetry processing."""

    enabled: bool = True
    aggregation_windows: list[AggregationWindow] = field(
        default_factory=lambda: [
            AggregationWindow.ONE_MINUTE,
            AggregationWindow.FIVE_MINUTES,
            AggregationWindow.ONE_HOUR,
        ]
    )
    derive_rates: bool = True
    derive_percentiles: list[float] = field(default_factory=lambda: [50.0, 95.0, 99.0])
    derive_derivatives: bool = True
    enrichment_rules: list[dict[str, Any]] = field(default_factory=list)
    filter_rules: list[dict[str, Any]] = field(default_factory=list)
    high_throughput_mode: bool = False  # When True, disables expensive features

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "enabled": self.enabled,
            "aggregation_windows": [w.value for w in self.aggregation_windows],
            "derive_rates": self.derive_rates,
            "derive_percentiles": self.derive_percentiles,
            "derive_derivatives": self.derive_derivatives,
            "enrichment_rules": self.enrichment_rules,
            "filter_rules": self.filter_rules,
            "high_throughput_mode": self.high_throughput_mode,
        }


@dataclass
class ExportDestinationConfig:
    """Configuration for a telemetry export destination."""

    name: str
    destination_type: ExportDestinationType
    enabled: bool = True
    batch_size: int = 100
    batch_timeout_seconds: float = 5.0
    retry_attempts: int = 3
    retry_backoff_seconds: float = 1.0
    connection_string: str = ""
    health_check_interval_seconds: float = 30.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "destination_type": self.destination_type.value,
            "enabled": self.enabled,
            "batch_size": self.batch_size,
            "batch_timeout_seconds": self.batch_timeout_seconds,
            "retry_attempts": self.retry_attempts,
            "retry_backoff_seconds": self.retry_backoff_seconds,
            "health_check_interval_seconds": self.health_check_interval_seconds,
        }


@dataclass
class DeadLetterQueueConfig:
    """Configuration for dead letter queue."""

    enabled: bool = True
    max_size: int = 10000
    retention_hours: int = 24
    alert_threshold: int = 1000
    storage_type: str = "redis"  # redis, postgres, file

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "enabled": self.enabled,
            "max_size": self.max_size,
            "retention_hours": self.retention_hours,
            "alert_threshold": self.alert_threshold,
            "storage_type": self.storage_type,
        }


@dataclass
class PipelineSettings:
    """Complete pipeline configuration."""

    # Ingestion sources
    sources: list[IngestionSourceConfig] = field(default_factory=list)

    # Processing configuration
    processing: ProcessingConfig = field(default_factory=ProcessingConfig)

    # Export destinations
    destinations: list[ExportDestinationConfig] = field(default_factory=list)

    # Dead letter queue
    dead_letter_queue: DeadLetterQueueConfig = field(
        default_factory=DeadLetterQueueConfig
    )

    # Pipeline lifecycle
    startup_timeout_seconds: float = 30.0
    shutdown_timeout_seconds: float = 30.0
    health_check_interval_seconds: float = 10.0

    def __post_init__(self) -> None:
        """Initialize default sources and destinations if not provided."""
        if not self.sources:
            self.sources = [
                IngestionSourceConfig(
                    name="logs",
                    source_type=IngestionSourceType.LOGS,
                ),
                IngestionSourceConfig(
                    name="metrics",
                    source_type=IngestionSourceType.METRICS,
                ),
                IngestionSourceConfig(
                    name="events",
                    source_type=IngestionSourceType.EVENTS,
                ),
            ]

        if not self.destinations:
            self.destinations = [
                ExportDestinationConfig(
                    name="influxdb",
                    destination_type=ExportDestinationType.INFLUXDB,
                ),
            ]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "sources": [s.to_dict() for s in self.sources],
            "processing": self.processing.to_dict(),
            "destinations": [d.to_dict() for d in self.destinations],
            "dead_letter_queue": self.dead_letter_queue.to_dict(),
            "startup_timeout_seconds": self.startup_timeout_seconds,
            "shutdown_timeout_seconds": self.shutdown_timeout_seconds,
            "health_check_interval_seconds": self.health_check_interval_seconds,
        }

    @classmethod
    def default(cls) -> PipelineSettings:
        """Create default pipeline settings."""
        return cls()


# Global pipeline settings instance
pipeline_settings = PipelineSettings.default()
