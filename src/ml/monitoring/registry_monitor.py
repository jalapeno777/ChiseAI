"""Model Registry monitoring for ChiseAI.

Provides monitoring capabilities for the Model Registry, including version
tracking, validation gate results, shadow mode comparisons, and degradation
event detection. Integrates with InfluxDB for time-series storage.

Example:
    >>> from ml.monitoring.registry_monitor import ModelRegistryMonitor
    >>> from ml.models.model_registry import ModelRegistry
    >>>
    >>> registry = ModelRegistry()
    >>> monitor = ModelRegistryMonitor(registry)
    >>>
    >>> # Record model registration
    >>> monitor.record_model_registration(
    ...     model_name="signal_predictor",
    ...     version="1.0.0",
    ...     metrics={"accuracy": 0.65}
    ... )
    >>>
    >>> # Get version history
    >>> history = monitor.get_version_history("signal_predictor")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Protocol

from ml.models.model_registry import ModelRegistry
from ml.monitoring.registry_metrics import MetricsCollector, NullMetricsCollector

logger = logging.getLogger(__name__)

# InfluxDB availability flag - graceful degradation if not installed
INFLUXDB_AVAILABLE = False
try:
    from influxdb_client import InfluxDBClient
    from influxdb_client.client.write.point import Point
    from influxdb_client.client.write_api import SYNCHRONOUS

    INFLUXDB_AVAILABLE = True
except ImportError:
    pass


class ValidationGateStatus(Enum):
    """Status of validation gate."""

    PASS = "pass"
    FAIL = "fail"
    PENDING = "pending"


class ShadowModeResult(Enum):
    """Result of shadow mode comparison."""

    PROMOTE = "promote"
    REJECT = "reject"
    EXTEND = "extend"
    PENDING = "pending"


@dataclass
class ModelVersionInfo:
    """Information about a model version.

    Attributes:
        model_name: Name of the model
        version: Version string
        created_at: When the version was created
        metrics: Model performance metrics
        tags: Version tags
        status: Current status (champion, challenger, deprecated)
        training_data: Reference to training data
    """

    model_name: str
    version: str
    created_at: datetime
    metrics: dict[str, float] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    status: str = "unknown"
    training_data: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "model_name": self.model_name,
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "metrics": self.metrics,
            "tags": self.tags,
            "status": self.status,
            "training_data": self.training_data,
        }


@dataclass
class ValidationGateRecord:
    """Record of a validation gate evaluation.

    Attributes:
        model_name: Name of the model
        version: Version being validated
        gate_name: Name of the validation gate
        status: Pass/fail/pending
        metrics: Metrics evaluated
        thresholds: Thresholds used
        evaluated_at: When the gate was evaluated
        evaluated_by: Who/what evaluated the gate
    """

    model_name: str
    version: str
    gate_name: str
    status: ValidationGateStatus
    metrics: dict[str, float] = field(default_factory=dict)
    thresholds: dict[str, float] = field(default_factory=dict)
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    evaluated_by: str = "system"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "model_name": self.model_name,
            "version": self.version,
            "gate_name": self.gate_name,
            "status": self.status.value,
            "metrics": self.metrics,
            "thresholds": self.thresholds,
            "evaluated_at": self.evaluated_at.isoformat(),
            "evaluated_by": self.evaluated_by,
        }


@dataclass
class ShadowModeRecord:
    """Record of a shadow mode comparison.

    Attributes:
        model_name: Name of the model
        champion_version: Current champion version
        candidate_version: Candidate version being tested
        result: Promote/reject/extend/pending
        champion_metrics: Champion model metrics
        candidate_metrics: Candidate model metrics
        delta: Difference in metrics
        sample_count: Number of samples compared
        duration_hours: Duration of shadow mode
        started_at: When shadow mode started
        completed_at: When shadow mode completed
    """

    model_name: str
    champion_version: str
    candidate_version: str
    result: ShadowModeResult
    champion_metrics: dict[str, float] = field(default_factory=dict)
    candidate_metrics: dict[str, float] = field(default_factory=dict)
    delta: dict[str, float] = field(default_factory=dict)
    sample_count: int = 0
    duration_hours: float = 0.0
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "model_name": self.model_name,
            "champion_version": self.champion_version,
            "candidate_version": self.candidate_version,
            "result": self.result.value,
            "champion_metrics": self.champion_metrics,
            "candidate_metrics": self.candidate_metrics,
            "delta": self.delta,
            "sample_count": self.sample_count,
            "duration_hours": self.duration_hours,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
        }


@dataclass
class DegradationEvent:
    """Record of a model performance degradation event.

    Attributes:
        model_name: Name of the model
        version: Model version
        metric_name: Name of the degraded metric
        baseline_value: Baseline metric value
        current_value: Current metric value
        degradation_percentage: Percentage of degradation
        detected_at: When degradation was detected
        alert_triggered: Whether an alert was triggered
    """

    model_name: str
    version: str
    metric_name: str
    baseline_value: float
    current_value: float
    degradation_percentage: float
    detected_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    alert_triggered: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "model_name": self.model_name,
            "version": self.version,
            "metric_name": self.metric_name,
            "baseline_value": self.baseline_value,
            "current_value": self.current_value,
            "degradation_percentage": self.degradation_percentage,
            "detected_at": self.detected_at.isoformat(),
            "alert_triggered": self.alert_triggered,
        }


class InfluxDBLogger(Protocol):
    """Protocol for logging registry events to InfluxDB."""

    def log_model_registration(self, info: ModelVersionInfo) -> bool:
        """Log model registration."""
        ...

    def log_validation_gate(self, record: ValidationGateRecord) -> bool:
        """Log validation gate result."""
        ...

    def log_shadow_mode(self, record: ShadowModeRecord) -> bool:
        """Log shadow mode comparison."""
        ...

    def log_degradation(self, event: DegradationEvent) -> bool:
        """Log degradation event."""
        ...


class DefaultInfluxDBLogger:
    """Default InfluxDB logger for registry monitoring."""

    def __init__(
        self,
        url: str = "http://chiseai-influxdb:18087",
        token: str = "chiseai-token",
        org: str = "chiseai",
        bucket: str = "chiseai",
    ):
        """Initialize InfluxDB logger.

        Args:
            url: InfluxDB URL
            token: Authentication token
            org: Organization name
            bucket: Bucket name
        """
        self._url = url
        self._token = token
        self._org = org
        self._bucket = bucket
        self._client = None
        self._write_api = None
        self._available = INFLUXDB_AVAILABLE

    def _get_client(self) -> Any:
        """Get or create InfluxDB client."""
        if not self._available:
            return None

        if self._client is None:
            try:
                self._client = InfluxDBClient(
                    url=self._url, token=self._token, org=self._org
                )
                self._write_api = self._client.write_api(write_options=SYNCHRONOUS)
            except Exception as e:
                logger.warning(f"Failed to create InfluxDB client: {e}")
                return None

        return self._client

    def log_model_registration(self, info: ModelVersionInfo) -> bool:
        """Log model registration to InfluxDB."""
        if not self._available or self._write_api is None:
            self._get_client()
            if self._write_api is None:
                return False

        try:
            # Main registration point
            point = (
                Point("model_registration")
                .tag("model_name", info.model_name)
                .tag("version", info.version)
                .tag("status", info.status)
                .time(info.created_at)
            )

            # Add metrics as fields
            for metric_name, metric_value in info.metrics.items():
                point = point.field(f"metric_{metric_name}", float(metric_value))

            self._write_api.write(bucket=self._bucket, org=self._org, record=point)

            # Log version count per model
            version_point = (
                Point("model_version_count")
                .tag("model_name", info.model_name)
                .field("increment", 1)
                .time(info.created_at)
            )
            self._write_api.write(
                bucket=self._bucket, org=self._org, record=version_point
            )

            logger.debug(f"Logged model registration: {info.model_name}@{info.version}")
            return True

        except Exception as e:
            logger.warning(f"Failed to log model registration: {e}")
            return False

    def log_validation_gate(self, record: ValidationGateRecord) -> bool:
        """Log validation gate result to InfluxDB."""
        if not self._available or self._write_api is None:
            self._get_client()
            if self._write_api is None:
                return False

        try:
            point = (
                Point("validation_gate_result")
                .tag("model_name", record.model_name)
                .tag("version", record.version)
                .tag("gate_name", record.gate_name)
                .tag("status", record.status.value)
                .field("passed", 1 if record.status == ValidationGateStatus.PASS else 0)
                .time(record.evaluated_at)
            )

            # Add metrics
            for metric_name, metric_value in record.metrics.items():
                point = point.field(f"metric_{metric_name}", float(metric_value))

            self._write_api.write(bucket=self._bucket, org=self._org, record=point)
            logger.debug(
                f"Logged validation gate: {record.gate_name} for {record.model_name}"
            )
            return True

        except Exception as e:
            logger.warning(f"Failed to log validation gate: {e}")
            return False

    def log_shadow_mode(self, record: ShadowModeRecord) -> bool:
        """Log shadow mode comparison to InfluxDB."""
        if not self._available or self._write_api is None:
            self._get_client()
            if self._write_api is None:
                return False

        try:
            point = (
                Point("shadow_mode_comparison")
                .tag("model_name", record.model_name)
                .tag("champion_version", record.champion_version)
                .tag("candidate_version", record.candidate_version)
                .tag("result", record.result.value)
                .field("sample_count", record.sample_count)
                .field("duration_hours", record.duration_hours)
                .time(record.started_at)
            )

            # Add delta metrics
            for metric_name, delta_value in record.delta.items():
                point = point.field(f"delta_{metric_name}", float(delta_value))

            self._write_api.write(bucket=self._bucket, org=self._org, record=point)
            logger.debug(f"Logged shadow mode comparison: {record.model_name}")
            return True

        except Exception as e:
            logger.warning(f"Failed to log shadow mode: {e}")
            return False

    def log_degradation(self, event: DegradationEvent) -> bool:
        """Log degradation event to InfluxDB."""
        if not self._available or self._write_api is None:
            self._get_client()
            if self._write_api is None:
                return False

        try:
            point = (
                Point("model_degradation")
                .tag("model_name", event.model_name)
                .tag("version", event.version)
                .tag("metric_name", event.metric_name)
                .tag("alert_triggered", str(event.alert_triggered))
                .field("baseline_value", event.baseline_value)
                .field("current_value", event.current_value)
                .field("degradation_percentage", event.degradation_percentage)
                .time(event.detected_at)
            )

            self._write_api.write(bucket=self._bucket, org=self._org, record=point)
            logger.info(
                f"Logged degradation: {event.model_name} {event.metric_name} "
                f"degraded by {event.degradation_percentage:.1f}%"
            )
            return True

        except Exception as e:
            logger.warning(f"Failed to log degradation: {e}")
            return False


class ModelRegistryMonitor:
    """Monitor for Model Registry state and events.

    Tracks model registrations, validation gates, shadow mode comparisons,
    and degradation events. Provides monitoring and alerting capabilities.

    Example:
        >>> from ml.models.model_registry import ModelRegistry
        >>> from ml.monitoring.registry_monitor import ModelRegistryMonitor
        >>>
        >>> registry = ModelRegistry()
        >>> monitor = ModelRegistryMonitor(registry)
        >>>
        >>> # Record model registration
        >>> monitor.record_model_registration(
        ...     model_name="signal_predictor",
        ...     version="1.0.0",
        ...     metrics={"accuracy": 0.65}
        ... )
        >>>
        >>> # Get version history
        >>> history = monitor.get_version_history("signal_predictor")
    """

    def __init__(
        self,
        registry: ModelRegistry | None = None,
        influx_logger: InfluxDBLogger | None = None,
        metrics_collector: MetricsCollector | None = None,
    ):
        """Initialize registry monitor.

        Args:
            registry: Model registry to monitor
            influx_logger: Optional InfluxDB logger
            metrics_collector: Optional metrics collector
        """
        self._registry = registry
        self._influx_logger = influx_logger or DefaultInfluxDBLogger()
        self._metrics_collector = metrics_collector or NullMetricsCollector()

        # In-memory storage for monitoring data
        self._version_history: dict[str, list[ModelVersionInfo]] = {}
        self._validation_records: list[ValidationGateRecord] = []
        self._shadow_mode_records: list[ShadowModeRecord] = []
        self._degradation_events: list[DegradationEvent] = []

        # Baselines for degradation detection
        self._baselines: dict[str, dict[str, float]] = {}

        self._max_history = 1000

        logger.info("ModelRegistryMonitor initialized")

    def record_model_registration(
        self,
        model_name: str,
        version: str,
        metrics: dict[str, float] | None = None,
        tags: list[str] | None = None,
        training_data: str | None = None,
        created_at: datetime | None = None,
    ) -> ModelVersionInfo:
        """Record a model registration.

        Args:
            model_name: Name of the model
            version: Version string
            metrics: Model performance metrics
            tags: Version tags
            training_data: Reference to training data
            created_at: Creation timestamp

        Returns:
            ModelVersionInfo for the registered version
        """
        info = ModelVersionInfo(
            model_name=model_name,
            version=version,
            created_at=created_at or datetime.now(UTC),
            metrics=metrics or {},
            tags=tags or [],
            training_data=training_data,
        )

        # Store in history
        if model_name not in self._version_history:
            self._version_history[model_name] = []
        self._version_history[model_name].append(info)

        # Trim history if needed
        if len(self._version_history[model_name]) > self._max_history:
            self._version_history[model_name] = self._version_history[model_name][
                -self._max_history :
            ]

        # Log to InfluxDB
        self._influx_logger.log_model_registration(info)

        # Record to metrics collector
        self._metrics_collector.record_model_registered(model_name, version)

        logger.info(f"Recorded model registration: {model_name}@{version}")

        return info

    def record_validation_gate(
        self,
        model_name: str,
        version: str,
        gate_name: str,
        passed: bool,
        metrics: dict[str, float] | None = None,
        thresholds: dict[str, float] | None = None,
        evaluated_by: str = "system",
    ) -> ValidationGateRecord:
        """Record a validation gate evaluation.

        Args:
            model_name: Name of the model
            version: Version being validated
            gate_name: Name of the validation gate
            passed: Whether the gate passed
            metrics: Metrics evaluated
            thresholds: Thresholds used
            evaluated_by: Who/what evaluated the gate

        Returns:
            ValidationGateRecord
        """
        record = ValidationGateRecord(
            model_name=model_name,
            version=version,
            gate_name=gate_name,
            status=ValidationGateStatus.PASS if passed else ValidationGateStatus.FAIL,
            metrics=metrics or {},
            thresholds=thresholds or {},
            evaluated_by=evaluated_by,
        )

        self._validation_records.append(record)

        # Trim history
        if len(self._validation_records) > self._max_history:
            self._validation_records = self._validation_records[-self._max_history :]

        # Log to InfluxDB
        self._influx_logger.log_validation_gate(record)

        logger.info(
            f"Validation gate {gate_name}: {model_name}@{version} "
            f"- {'PASS' if passed else 'FAIL'}"
        )

        return record

    def record_shadow_mode(
        self,
        model_name: str,
        champion_version: str,
        candidate_version: str,
        result: str | ShadowModeResult,
        champion_metrics: dict[str, float] | None = None,
        candidate_metrics: dict[str, float] | None = None,
        delta: dict[str, float] | None = None,
        sample_count: int = 0,
        duration_hours: float = 0.0,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> ShadowModeRecord:
        """Record a shadow mode comparison.

        Args:
            model_name: Name of the model
            champion_version: Current champion version
            candidate_version: Candidate version being tested
            result: Promote/reject/extend/pending
            champion_metrics: Champion model metrics
            candidate_metrics: Candidate model metrics
            delta: Difference in metrics
            sample_count: Number of samples compared
            duration_hours: Duration of shadow mode
            started_at: When shadow mode started
            completed_at: When shadow mode completed

        Returns:
            ShadowModeRecord
        """
        if isinstance(result, str):
            result = ShadowModeResult(result)

        record = ShadowModeRecord(
            model_name=model_name,
            champion_version=champion_version,
            candidate_version=candidate_version,
            result=result,
            champion_metrics=champion_metrics or {},
            candidate_metrics=candidate_metrics or {},
            delta=delta or {},
            sample_count=sample_count,
            duration_hours=duration_hours,
            started_at=started_at or datetime.now(UTC),
            completed_at=completed_at,
        )

        self._shadow_mode_records.append(record)

        # Trim history
        if len(self._shadow_mode_records) > self._max_history:
            self._shadow_mode_records = self._shadow_mode_records[-self._max_history :]

        # Log to InfluxDB
        self._influx_logger.log_shadow_mode(record)

        logger.info(
            f"Shadow mode comparison: {model_name} "
            f"{champion_version} vs {candidate_version} - {result.value}"
        )

        return record

    def record_degradation(
        self,
        model_name: str,
        version: str,
        metric_name: str,
        baseline_value: float,
        current_value: float,
        alert_triggered: bool = False,
    ) -> DegradationEvent:
        """Record a degradation event.

        Args:
            model_name: Name of the model
            version: Model version
            metric_name: Name of the degraded metric
            baseline_value: Baseline metric value
            current_value: Current metric value
            alert_triggered: Whether an alert was triggered

        Returns:
            DegradationEvent
        """
        if baseline_value > 0:
            degradation_percentage = (
                (baseline_value - current_value) / baseline_value * 100
            )
        else:
            degradation_percentage = 0.0

        event = DegradationEvent(
            model_name=model_name,
            version=version,
            metric_name=metric_name,
            baseline_value=baseline_value,
            current_value=current_value,
            degradation_percentage=degradation_percentage,
            alert_triggered=alert_triggered,
        )

        self._degradation_events.append(event)

        # Trim history
        if len(self._degradation_events) > self._max_history:
            self._degradation_events = self._degradation_events[-self._max_history :]

        # Log to InfluxDB
        self._influx_logger.log_degradation(event)

        # Record to metrics collector
        self._metrics_collector.record_failed_operation(
            "degradation_detection",
            model_name,
            "DegradationDetected",
            f"{metric_name} degraded by {degradation_percentage:.1f}%",
        )

        logger.warning(
            f"Degradation detected: {model_name}@{version} {metric_name} "
            f"degraded by {degradation_percentage:.1f}%"
        )

        return event

    def set_baseline(
        self, model_name: str, version: str, metrics: dict[str, float]
    ) -> None:
        """Set baseline metrics for a model version.

        Args:
            model_name: Name of the model
            version: Model version
            metrics: Baseline metrics
        """
        key = f"{model_name}:{version}"
        self._baselines[key] = metrics.copy()
        logger.info(f"Set baseline for {key}: {metrics}")

    def check_degradation(
        self,
        model_name: str,
        version: str,
        current_metrics: dict[str, float],
        threshold_percentage: float = 10.0,
    ) -> list[DegradationEvent]:
        """Check for performance degradation against baseline.

        Args:
            model_name: Name of the model
            version: Model version
            current_metrics: Current metrics
            threshold_percentage: Degradation threshold percentage

        Returns:
            List of degradation events detected
        """
        key = f"{model_name}:{version}"
        baseline = self._baselines.get(key)

        if not baseline:
            logger.warning(f"No baseline set for {key}")
            return []

        events = []

        for metric_name, baseline_value in baseline.items():
            if metric_name not in current_metrics:
                continue

            current_value = current_metrics[metric_name]

            if baseline_value > 0:
                degradation_percentage = (
                    (baseline_value - current_value) / baseline_value * 100
                )

                if degradation_percentage > threshold_percentage:
                    event = self.record_degradation(
                        model_name=model_name,
                        version=version,
                        metric_name=metric_name,
                        baseline_value=baseline_value,
                        current_value=current_value,
                        alert_triggered=True,
                    )
                    events.append(event)

        return events

    def get_version_history(
        self, model_name: str, limit: int = 100
    ) -> list[ModelVersionInfo]:
        """Get version history for a model.

        Args:
            model_name: Name of the model
            limit: Maximum number of versions to return

        Returns:
            List of ModelVersionInfo
        """
        history = self._version_history.get(model_name, [])
        return history[-limit:]

    def get_validation_history(
        self,
        model_name: str | None = None,
        version: str | None = None,
        gate_name: str | None = None,
        limit: int = 100,
    ) -> list[ValidationGateRecord]:
        """Get validation gate history.

        Args:
            model_name: Filter by model name
            version: Filter by version
            gate_name: Filter by gate name
            limit: Maximum number of records

        Returns:
            List of ValidationGateRecord
        """
        records = self._validation_records

        if model_name:
            records = [r for r in records if r.model_name == model_name]

        if version:
            records = [r for r in records if r.version == version]

        if gate_name:
            records = [r for r in records if r.gate_name == gate_name]

        return records[-limit:]

    def get_shadow_mode_history(
        self, model_name: str | None = None, limit: int = 100
    ) -> list[ShadowModeRecord]:
        """Get shadow mode comparison history.

        Args:
            model_name: Filter by model name
            limit: Maximum number of records

        Returns:
            List of ShadowModeRecord
        """
        records = self._shadow_mode_records

        if model_name:
            records = [r for r in records if r.model_name == model_name]

        return records[-limit:]

    def get_degradation_events(
        self,
        model_name: str | None = None,
        version: str | None = None,
        limit: int = 100,
    ) -> list[DegradationEvent]:
        """Get degradation event history.

        Args:
            model_name: Filter by model name
            version: Filter by version
            limit: Maximum number of events

        Returns:
            List of DegradationEvent
        """
        events = self._degradation_events

        if model_name:
            events = [e for e in events if e.model_name == model_name]

        if version:
            events = [e for e in events if e.version == version]

        return events[-limit:]

    def get_models_summary(self) -> dict[str, dict[str, Any]]:
        """Get summary of all monitored models.

        Returns:
            Dictionary with model summaries
        """
        summary = {}

        for model_name, versions in self._version_history.items():
            total_versions = len(versions)
            latest_version = versions[-1] if versions else None

            # Count by status
            status_counts = {}
            for v in versions:
                status_counts[v.status] = status_counts.get(v.status, 0) + 1

            # Get degradation events
            degradation_count = len(
                [e for e in self._degradation_events if e.model_name == model_name]
            )

            # Get validation results
            validations = [
                r for r in self._validation_records if r.model_name == model_name
            ]
            passed_validations = len(
                [r for r in validations if r.status == ValidationGateStatus.PASS]
            )

            summary[model_name] = {
                "total_versions": total_versions,
                "latest_version": latest_version.version if latest_version else None,
                "latest_created_at": latest_version.created_at.isoformat()
                if latest_version
                else None,
                "status_counts": status_counts,
                "degradation_events": degradation_count,
                "validation_pass_rate": (
                    passed_validations / len(validations) * 100 if validations else 0.0
                ),
            }

        return summary

    def clear_history(self) -> None:
        """Clear all monitoring history."""
        self._version_history.clear()
        self._validation_records.clear()
        self._shadow_mode_records.clear()
        self._degradation_events.clear()
        self._baselines.clear()
        logger.info("Registry monitor history cleared")
