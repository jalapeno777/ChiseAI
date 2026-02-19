"""Provider observability for LLM provider chain during burn-in.

Provides structured metrics collection, InfluxDB export, and burn-in monitoring
for provider chain operations including fallback tracking.

For GATE-RECOVERY-003: Provider Observability Fix
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from llm.provider_chain import ErrorCategory

logger = logging.getLogger(__name__)


@dataclass
class ProviderMetrics:
    """Per-provider metrics for burn-in monitoring.

    Attributes:
        provider_name: Name of the provider (e.g., "kimi", "zai")
        provider_label: Human-readable label (e.g., "KIMI K2.5")
        attempts: Total number of attempts made
        successes: Number of successful responses
        failures: Number of failed responses
        fallback_reasons: Count of failures by ErrorCategory
        total_latency_ms: Sum of all latencies for avg calculation
        avg_latency_ms: Average latency in milliseconds
        last_attempt_at: Timestamp of last attempt
        last_success_at: Timestamp of last success
        last_failure_at: Timestamp of last failure
        last_error_category: Category of last error
        last_fallback_reason: Reason for last fallback
    """

    provider_name: str
    provider_label: str = ""
    attempts: int = 0
    successes: int = 0
    failures: int = 0
    fallback_reasons: dict[str, int] = field(default_factory=dict)
    total_latency_ms: float = 0.0
    avg_latency_ms: float = 0.0
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    last_error_category: str | None = None
    last_fallback_reason: str | None = None

    def record_attempt(self, latency_ms: float = 0.0) -> None:
        """Record a provider attempt."""
        self.attempts += 1
        self.total_latency_ms += latency_ms
        self.avg_latency_ms = (
            self.total_latency_ms / self.attempts if self.attempts > 0 else 0.0
        )
        self.last_attempt_at = datetime.now(UTC)

    def record_success(self, latency_ms: float = 0.0) -> None:
        """Record a successful response."""
        self.successes += 1
        self.last_success_at = datetime.now(UTC)

    def record_failure(
        self,
        error_category: ErrorCategory | str,
        fallback_reason: str | None = None,
    ) -> None:
        """Record a failed response with error category.

        Args:
            error_category: The error category (enum or string)
            fallback_reason: Optional detailed reason for fallback
        """
        self.failures += 1
        self.last_failure_at = datetime.now(UTC)

        # Handle both enum and string
        if hasattr(error_category, "name"):
            category_name = error_category.name
        else:
            category_name = str(error_category)

        self.last_error_category = category_name
        self.last_fallback_reason = fallback_reason or category_name

        # Increment fallback reason counter
        if category_name not in self.fallback_reasons:
            self.fallback_reasons[category_name] = 0
        self.fallback_reasons[category_name] += 1

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.attempts == 0:
            return 0.0
        return (self.successes / self.attempts) * 100.0

    @property
    def failure_rate(self) -> float:
        """Calculate failure rate as percentage."""
        if self.attempts == 0:
            return 0.0
        return (self.failures / self.attempts) * 100.0

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary for serialization."""
        return {
            "provider_name": self.provider_name,
            "provider_label": self.provider_label,
            "attempts": self.attempts,
            "successes": self.successes,
            "failures": self.failures,
            "success_rate": self.success_rate,
            "failure_rate": self.failure_rate,
            "fallback_reasons": self.fallback_reasons.copy(),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "total_latency_ms": round(self.total_latency_ms, 2),
            "last_attempt_at": (
                self.last_attempt_at.isoformat() if self.last_attempt_at else None
            ),
            "last_success_at": (
                self.last_success_at.isoformat() if self.last_success_at else None
            ),
            "last_failure_at": (
                self.last_failure_at.isoformat() if self.last_failure_at else None
            ),
            "last_error_category": self.last_error_category,
            "last_fallback_reason": self.last_fallback_reason,
        }


@dataclass
class ChainMetrics:
    """Metrics for the entire provider chain.

    Attributes:
        total_queries: Total number of queries processed
        successful_queries: Number of queries that succeeded
        failed_queries: Number of queries that failed
        fallback_count: Number of times fallback occurred
        providers_used: Set of providers that were used
        provider_metrics: Per-provider metrics
        started_at: When metrics collection started
    """

    total_queries: int = 0
    successful_queries: int = 0
    failed_queries: int = 0
    fallback_count: int = 0
    providers_used: set[str] = field(default_factory=set)
    provider_metrics: dict[str, ProviderMetrics] = field(default_factory=dict)
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def get_or_create_provider_metrics(
        self, provider_name: str, provider_label: str = ""
    ) -> ProviderMetrics:
        """Get or create metrics for a provider."""
        if provider_name not in self.provider_metrics:
            self.provider_metrics[provider_name] = ProviderMetrics(
                provider_name=provider_name,
                provider_label=provider_label or provider_name,
            )
        return self.provider_metrics[provider_name]

    def record_query_start(self) -> None:
        """Record the start of a query."""
        self.total_queries += 1

    def record_query_success(self, provider_name: str) -> None:
        """Record a successful query."""
        self.successful_queries += 1
        self.providers_used.add(provider_name)

    def record_query_failure(self) -> None:
        """Record a failed query (all providers exhausted)."""
        self.failed_queries += 1

    def record_fallback(self) -> None:
        """Record a fallback event."""
        self.fallback_count += 1

    @property
    def overall_success_rate(self) -> float:
        """Calculate overall success rate."""
        if self.total_queries == 0:
            return 0.0
        return (self.successful_queries / self.total_queries) * 100.0

    @property
    def avg_fallbacks_per_query(self) -> float:
        """Calculate average fallbacks per query."""
        if self.total_queries == 0:
            return 0.0
        return self.fallback_count / self.total_queries

    def to_dict(self) -> dict[str, Any]:
        """Convert chain metrics to dictionary."""
        return {
            "total_queries": self.total_queries,
            "successful_queries": self.successful_queries,
            "failed_queries": self.failed_queries,
            "overall_success_rate": round(self.overall_success_rate, 2),
            "fallback_count": self.fallback_count,
            "avg_fallbacks_per_query": round(self.avg_fallbacks_per_query, 2),
            "providers_used": list(self.providers_used),
            "provider_count": len(self.provider_metrics),
            "started_at": self.started_at.isoformat(),
            "provider_metrics": {
                name: metrics.to_dict()
                for name, metrics in self.provider_metrics.items()
            },
        }


class ProviderMetricsExporter:
    """Export provider metrics to InfluxDB and structured logging.

    Provides:
    - InfluxDB point generation for time-series metrics
    - Structured logging for burn-in monitoring
    - Metrics aggregation and reporting
    """

    def __init__(
        self,
        influxdb_client: Any | None = None,
        bucket: str = "chiseai",
        org: str = "chiseai",
        enable_logging: bool = True,
    ):
        """Initialize the metrics exporter.

        Args:
            influxdb_client: Optional InfluxDB client for writing metrics
            bucket: InfluxDB bucket name
            org: InfluxDB organization
            enable_logging: Whether to log metrics to structured logs
        """
        self.influxdb_client = influxdb_client
        self.bucket = bucket
        self.org = org
        self.enable_logging = enable_logging
        self._write_api = None

        if influxdb_client:
            try:
                from influxdb_client.client.write_api import SYNCHRONOUS

                self._write_api = influxdb_client.write_api(write_options=SYNCHRONOUS)
            except Exception as e:
                logger.warning(f"Failed to initialize InfluxDB write API: {e}")

    def export_provider_metrics(
        self,
        metrics: ProviderMetrics,
        timestamp: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Export provider metrics to InfluxDB.

        Args:
            metrics: ProviderMetrics to export
            timestamp: Optional timestamp (defaults to now)

        Returns:
            Dictionary of exported data or None if export failed
        """
        if not self._write_api:
            return None

        try:
            from influxdb_client import Point, WritePrecision

            ts = timestamp or datetime.now(UTC)

            # Create point for provider metrics
            point = (
                Point("llm_provider_metrics")
                .tag("provider_name", metrics.provider_name)
                .tag("provider_label", metrics.provider_label)
                .field("attempts", metrics.attempts)
                .field("successes", metrics.successes)
                .field("failures", metrics.failures)
                .field("success_rate", metrics.success_rate)
                .field("avg_latency_ms", metrics.avg_latency_ms)
                .field("total_latency_ms", metrics.total_latency_ms)
                .time(ts, WritePrecision.NS)
            )

            # Write to InfluxDB
            self._write_api.write(bucket=self.bucket, record=[point])

            # Export fallback reasons as separate points
            for category, count in metrics.fallback_reasons.items():
                fallback_point = (
                    Point("llm_provider_fallbacks")
                    .tag("provider_name", metrics.provider_name)
                    .tag("error_category", category)
                    .field("count", count)
                    .time(ts, WritePrecision.NS)
                )
                self._write_api.write(bucket=self.bucket, record=[fallback_point])

            exported = {
                "provider": metrics.provider_name,
                "timestamp": ts.isoformat(),
                "attempts": metrics.attempts,
                "successes": metrics.successes,
                "failures": metrics.failures,
            }

            if self.enable_logging:
                logger.info(
                    "Provider metrics exported",
                    extra={
                        "provider": metrics.provider_name,
                        "attempts": metrics.attempts,
                        "success_rate": metrics.success_rate,
                    },
                )

            return exported

        except Exception as e:
            logger.warning(f"Failed to export provider metrics to InfluxDB: {e}")
            return None

    def export_chain_metrics(
        self,
        metrics: ChainMetrics,
        timestamp: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Export chain-level metrics to InfluxDB.

        Args:
            metrics: ChainMetrics to export
            timestamp: Optional timestamp (defaults to now)

        Returns:
            Dictionary of exported data or None if export failed
        """
        if not self._write_api:
            return None

        try:
            from influxdb_client import Point, WritePrecision

            ts = timestamp or datetime.now(UTC)

            # Create point for chain metrics
            point = (
                Point("llm_chain_metrics")
                .field("total_queries", metrics.total_queries)
                .field("successful_queries", metrics.successful_queries)
                .field("failed_queries", metrics.failed_queries)
                .field("overall_success_rate", metrics.overall_success_rate)
                .field("fallback_count", metrics.fallback_count)
                .field("avg_fallbacks_per_query", metrics.avg_fallbacks_per_query)
                .field("provider_count", len(metrics.provider_metrics))
                .time(ts, WritePrecision.NS)
            )

            self._write_api.write(bucket=self.bucket, record=[point])

            exported = {
                "timestamp": ts.isoformat(),
                "total_queries": metrics.total_queries,
                "success_rate": metrics.overall_success_rate,
                "fallback_count": metrics.fallback_count,
            }

            if self.enable_logging:
                logger.info(
                    "Chain metrics exported",
                    extra={
                        "total_queries": metrics.total_queries,
                        "success_rate": metrics.overall_success_rate,
                        "fallback_count": metrics.fallback_count,
                    },
                )

            return exported

        except Exception as e:
            logger.warning(f"Failed to export chain metrics to InfluxDB: {e}")
            return None

    def log_burn_in_event(
        self,
        event_type: str,
        provider_name: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Log a structured burn-in event.

        Args:
            event_type: Type of event (e.g., "attempt", "success",
                "failure", "fallback")
            provider_name: Name of the provider
            details: Optional additional details
        """
        if not self.enable_logging:
            return

        log_data = {
            "event_type": event_type,
            "provider": provider_name,
            "timestamp": datetime.now(UTC).isoformat(),
            **(details or {}),
        }

        if event_type == "failure":
            logger.warning(f"Burn-in: Provider {provider_name} failed", extra=log_data)
        elif event_type == "fallback":
            logger.info(
                f"Burn-in: Fallback from {provider_name}",
                extra=log_data,
            )
        else:
            logger.debug(f"Burn-in: {event_type} on {provider_name}", extra=log_data)


def create_metrics_report(metrics: ChainMetrics) -> str:
    """Create a human-readable metrics report for burn-in monitoring.

    Args:
        metrics: ChainMetrics to report on

    Returns:
        Formatted report string
    """
    lines = [
        "=" * 60,
        "LLM Provider Chain Metrics Report",
        "=" * 60,
        f"Period: {metrics.started_at.isoformat()} to {datetime.now(UTC).isoformat()}",
        "",
        "Overall Statistics:",
        f"  Total Queries: {metrics.total_queries}",
        f"  Successful: {metrics.successful_queries} "
        f"({metrics.overall_success_rate:.1f}%)",
        f"  Failed: {metrics.failed_queries}",
        f"  Total Fallbacks: {metrics.fallback_count}",
        f"  Avg Fallbacks/Query: {metrics.avg_fallbacks_per_query:.2f}",
        "",
        "Per-Provider Statistics:",
    ]

    for name, provider_metrics in sorted(metrics.provider_metrics.items()):
        lines.extend(
            [
                f"  {provider_metrics.provider_label or name}:",
                f"    Attempts: {provider_metrics.attempts}",
                f"    Successes: {provider_metrics.successes} "
                f"({provider_metrics.success_rate:.1f}%)",
                f"    Failures: {provider_metrics.failures}",
                f"    Avg Latency: {provider_metrics.avg_latency_ms:.1f}ms",
            ]
        )

        if provider_metrics.fallback_reasons:
            lines.append("    Fallback Reasons:")
            for category, count in sorted(provider_metrics.fallback_reasons.items()):
                lines.append(f"      {category}: {count}")

        lines.append("")

    lines.append("=" * 60)
    return "\n".join(lines)


def aggregate_metrics(
    metrics_list: list[ChainMetrics],
) -> dict[str, Any]:
    """Aggregate multiple ChainMetrics into summary statistics.

    Args:
        metrics_list: List of ChainMetrics to aggregate

    Returns:
        Dictionary with aggregated statistics
    """
    if not metrics_list:
        return {
            "total_queries": 0,
            "successful_queries": 0,
            "failed_queries": 0,
            "success_rate": 0.0,
            "total_fallbacks": 0,
        }

    total_queries = sum(m.total_queries for m in metrics_list)
    successful = sum(m.successful_queries for m in metrics_list)
    failed = sum(m.failed_queries for m in metrics_list)
    fallbacks = sum(m.fallback_count for m in metrics_list)

    return {
        "total_queries": total_queries,
        "successful_queries": successful,
        "failed_queries": failed,
        "success_rate": (
            (successful / total_queries * 100) if total_queries > 0 else 0.0
        ),
        "total_fallbacks": fallbacks,
        "avg_fallbacks_per_query": (
            (fallbacks / total_queries) if total_queries > 0 else 0.0
        ),
        "periods_count": len(metrics_list),
    }
