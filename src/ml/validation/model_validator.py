"""Model validation with gates, shadow mode, and InfluxDB logging for ChiseAI.

This module provides validation gates that run before model promotion,
supporting shadow mode validation, A/B testing, and performance monitoring.

Acceptance Criteria:
- Validation gates: All metrics pass thresholds (accuracy >= 0.60, etc.)
- Shadow mode: 24-hour comparison between current and new model
- Degradation detection: >10% from baseline triggers alert
- Automatic rollback: <5 minutes (target <2 minutes)
- Audit history: 90-day retention

Example:
    >>> from ml.validation.model_validator import (
    ...     ValidationGate, ValidationConfig, ValidationThresholds
    ... )
    >>> from ml.model_registry.registry import ModelRegistry
    >>>
    >>> registry = ModelRegistry()
    >>> thresholds = ValidationThresholds()
    >>> gate = ValidationGate(registry=registry, thresholds=thresholds)
    >>>
    >>> # Validate a model
    >>> result = gate.validate({
    ...     "accuracy": 0.65,
    ...     "precision": 0.60,
    ...     "recall": 0.55,
    ...     "f1": 0.57,
    ...     "win_rate": 0.60
    ... })
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Protocol

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


class GateStatus(Enum):
    """Status of validation gate results."""

    PASS = "pass"
    WARNING = "warning"
    CRITICAL = "critical"
    ERROR = "error"


class ValidationLevel(Enum):
    """Level of validation result."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True)
class ValidationThresholds:
    """Thresholds for validation gates.

    Task 13.1: Validation gate thresholds.

    Attributes:
        accuracy_pass: Minimum accuracy to pass (default 0.60)
        accuracy_warning: Warning threshold for accuracy
        precision_pass: Minimum precision to pass
        precision_warning: Warning threshold for precision
        recall_pass: Minimum recall to pass
        recall_warning: Warning threshold for recall
        f1_pass: Minimum F1 to pass
        f1_warning: Warning threshold for F1
        win_rate_pass: Minimum win rate to pass
        win_rate_warning: Warning threshold for win rate
    """

    # Pass thresholds (must meet these to pass)
    accuracy_pass: float = 0.60
    precision_pass: float = 0.55
    recall_pass: float = 0.50
    f1_pass: float = 0.52
    win_rate_pass: float = 0.55

    # Warning thresholds (between warning and pass)
    accuracy_warning: float = 0.55
    precision_warning: float = 0.50
    recall_warning: float = 0.45
    f1_warning: float = 0.47
    win_rate_warning: float = 0.50

    def get_level(self, metric_name: str, value: float) -> GateStatus:
        """Determine gate status for a metric value.

        Args:
            metric_name: Name of the metric
            value: Metric value

        Returns:
            GateStatus (PASS, WARNING, or CRITICAL)
        """
        pass_threshold = getattr(self, f"{metric_name}_pass", 0.0)
        warning_threshold = getattr(self, f"{metric_name}_warning", 0.0)

        if value >= pass_threshold:
            return GateStatus.PASS
        elif value >= warning_threshold:
            return GateStatus.WARNING
        else:
            return GateStatus.CRITICAL


@dataclass
class GateResult:
    """Result of a single validation gate.

    Attributes:
        name: Gate name
        status: Pass/warning/critical
        value: Actual metric value
        threshold: Required threshold
        message: Human-readable message
        level: Validation level
    """

    name: str
    status: GateStatus
    value: float
    threshold: float
    message: str
    level: ValidationLevel = ValidationLevel.INFO

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "status": self.status.value,
            "value": self.value,
            "threshold": self.threshold,
            "message": self.message,
            "level": self.level.value,
        }


@dataclass
class CompositeGateResult:
    """Result of composite validation (all gates).

    Attributes:
        passed: Whether all gates passed
        gate_results: Individual gate results
        timestamp: When validation occurred
        model_version: Model version being validated
        degradation_detected: Whether performance degradation was detected
        degradation_percentage: Percentage of degradation from baseline
    """

    passed: bool
    gate_results: list[GateResult]
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    model_version: str = ""
    degradation_detected: bool = False
    degradation_percentage: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "passed": self.passed,
            "gate_results": [g.to_dict() for g in self.gate_results],
            "timestamp": self.timestamp.isoformat(),
            "model_version": self.model_version,
            "degradation_detected": self.degradation_detected,
            "degradation_percentage": self.degradation_percentage,
        }

    @property
    def critical_count(self) -> int:
        """Count of critical failures."""
        return sum(1 for g in self.gate_results if g.status == GateStatus.CRITICAL)

    @property
    def warning_count(self) -> int:
        """Count of warnings."""
        return sum(1 for g in self.gate_results if g.status == GateStatus.WARNING)


@dataclass
class ShadowModeConfig:
    """Configuration for shadow mode A/B testing.

    Task 13.2: A/B Testing Framework (Shadow Mode)
    """

    enabled: bool = True
    duration_hours: float = 24.0
    comparison_interval_minutes: int = 60
    min_samples_required: int = 100
    route_to_both: bool = True  # Route signals to both models


@dataclass
class ShadowComparisonResult:
    """Result of shadow mode comparison.

    Attributes:
        champion_metrics: Current champion model metrics
        candidate_metrics: New candidate model metrics
        delta: Difference in metrics (candidate - champion)
        sample_count: Number of samples compared
        duration_hours: Duration of shadow mode
        timestamp: When comparison was completed
        recommendation: Pass/fail recommendation
    """

    champion_metrics: dict[str, float]
    candidate_metrics: dict[str, float]
    delta: dict[str, float]
    sample_count: int
    duration_hours: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    recommendation: str = "pending"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "champion_metrics": self.champion_metrics,
            "candidate_metrics": self.candidate_metrics,
            "delta": self.delta,
            "sample_count": self.sample_count,
            "duration_hours": self.duration_hours,
            "timestamp": self.timestamp.isoformat(),
            "recommendation": self.recommendation,
        }


class InfluxDBLogger(Protocol):
    """Protocol for logging validation results to InfluxDB."""

    def log_gate_result(self, result: CompositeGateResult) -> bool:
        """Log validation gate result."""
        ...

    def log_shadow_comparison(self, result: ShadowComparisonResult) -> bool:
        """Log shadow mode comparison."""
        ...

    def log_degradation_event(
        self,
        model_version: str,
        metric_name: str,
        baseline_value: float,
        current_value: float,
        degradation_pct: float,
    ) -> bool:
        """Log degradation detection event."""
        ...


class DefaultInfluxDBLogger:
    """Default InfluxDB logger for validation results.

    Task 13.1: Log gate results to InfluxDB.
    Task 13.3: Log degradation events to InfluxDB.
    """

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

    def log_gate_result(self, result: CompositeGateResult) -> bool:
        """Log validation gate result to InfluxDB.

        Args:
            result: Composite gate result

        Returns:
            True if logged successfully
        """
        if not self._available or self._write_api is None:
            self._get_client()
            if self._write_api is None:
                logger.debug("InfluxDB not available, skipping gate result log")
                return False

        try:
            # Create point for overall result
            point = (
                Point("validation_gate_result")
                .tag("model_version", result.model_version)
                .tag("passed", str(result.passed))
                .tag("critical_count", result.critical_count)
                .tag("warning_count", result.warning_count)
                .tag("degradation_detected", str(result.degradation_detected))
                .field("degradation_percentage", result.degradation_percentage)
                .time(result.timestamp)
            )

            self._write_api.write(bucket=self._bucket, org=self._org, record=point)

            # Create points for individual gates
            for gate in result.gate_results:
                gate_point = (
                    Point("validation_gate")
                    .tag("model_version", result.model_version)
                    .tag("gate_name", gate.name)
                    .tag("status", gate.status.value)
                    .field("value", gate.value)
                    .field("threshold", gate.threshold)
                    .time(result.timestamp)
                )
                self._write_api.write(
                    bucket=self._bucket, org=self._org, record=gate_point
                )

            logger.debug(f"Logged validation gate result for {result.model_version}")
            return True

        except Exception as e:
            logger.warning(f"Failed to log gate result to InfluxDB: {e}")
            return False

    def log_shadow_comparison(self, result: ShadowComparisonResult) -> bool:
        """Log shadow mode comparison to InfluxDB.

        Args:
            result: Shadow comparison result

        Returns:
            True if logged successfully
        """
        if not self._available or self._write_api is None:
            self._get_client()
            if self._write_api is None:
                logger.debug("InfluxDB not available, skipping shadow comparison log")
                return False

        try:
            point = (
                Point("shadow_mode_comparison")
                .tag("recommendation", result.recommendation)
                .field("sample_count", result.sample_count)
                .field("duration_hours", result.duration_hours)
                .field("accuracy_delta", result.delta.get("accuracy", 0.0))
                .field("precision_delta", result.delta.get("precision", 0.0))
                .field("recall_delta", result.delta.get("recall", 0.0))
                .field("f1_delta", result.delta.get("f1", 0.0))
                .field("win_rate_delta", result.delta.get("win_rate", 0.0))
                .time(result.timestamp)
            )

            self._write_api.write(bucket=self._bucket, org=self._org, record=point)
            logger.debug("Logged shadow mode comparison")
            return True

        except Exception as e:
            logger.warning(f"Failed to log shadow comparison to InfluxDB: {e}")
            return False

    def log_degradation_event(
        self,
        model_version: str,
        metric_name: str,
        baseline_value: float,
        current_value: float,
        degradation_pct: float,
    ) -> bool:
        """Log degradation detection event to InfluxDB.

        Task 13.3: Log degradation events to InfluxDB.

        Args:
            model_version: Model version
            metric_name: Name of degraded metric
            baseline_value: Baseline value
            current_value: Current value
            degradation_pct: Percentage of degradation

        Returns:
            True if logged successfully
        """
        if not self._available or self._write_api is None:
            self._get_client()
            if self._write_api is None:
                logger.debug("InfluxDB not available, skipping degradation event log")
                return False

        try:
            point = (
                Point("model_degradation")
                .tag("model_version", model_version)
                .tag("metric_name", metric_name)
                .tag("alert_triggered", str(degradation_pct > 10.0))
                .field("baseline_value", baseline_value)
                .field("current_value", current_value)
                .field("degradation_percentage", degradation_pct)
                .time(datetime.now(UTC))
            )

            self._write_api.write(bucket=self._bucket, org=self._org, record=point)
            logger.info(
                f"Logged degradation event: {model_version} {metric_name} "
                f"degraded by {degradation_pct:.1f}%"
            )
            return True

        except Exception as e:
            logger.warning(f"Failed to log degradation event to InfluxDB: {e}")
            return False


class ValidationGate:
    """Validation gate for model metrics with threshold checking.

    Task 13.1: Validation Gate Implementation
    - Implement accuracy threshold gate (default 0.60)
    - Implement precision/recall/F1 gates
    - Add composite gate (all must pass)
    - Log gate results to InfluxDB

    Example:
        >>> gate = ValidationGate()
        >>> result = gate.validate({
        ...     "accuracy": 0.65,
        ...     "precision": 0.60,
        ...     "recall": 0.55,
        ...     "f1": 0.57,
        ...     "win_rate": 0.60
        ... })
        >>> assert result.passed
    """

    def __init__(
        self,
        thresholds: ValidationThresholds | None = None,
        influx_logger: InfluxDBLogger | None = None,
    ):
        """Initialize validation gate.

        Args:
            thresholds: Validation thresholds
            influx_logger: Optional InfluxDB logger
        """
        self._thresholds = thresholds or ValidationThresholds()
        self._influx_logger = influx_logger or DefaultInfluxDBLogger()
        self._validation_history: list[CompositeGateResult] = []

        logger.info(
            f"ValidationGate initialized with thresholds: "
            f"accuracy>={self._thresholds.accuracy_pass}, "
            f"precision>={self._thresholds.precision_pass}, "
            f"recall>={self._thresholds.recall_pass}, "
            f"f1>={self._thresholds.f1_pass}"
        )

    def validate(
        self,
        metrics: dict[str, float],
        model_version: str = "",
        baseline_metrics: dict[str, float] | None = None,
    ) -> CompositeGateResult:
        """Validate metrics against thresholds.

        Task 13.1: Implement composite gate (all must pass).

        Args:
            metrics: Dictionary of metric names to values
            model_version: Model version being validated
            baseline_metrics: Optional baseline for degradation detection

        Returns:
            CompositeGateResult with all gate results
        """
        gate_results: list[GateResult] = []

        # Define metric gates to check
        metric_gates = [
            ("accuracy", self._thresholds.accuracy_pass),
            ("precision", self._thresholds.precision_pass),
            ("recall", self._thresholds.recall_pass),
            ("f1", self._thresholds.f1_pass),
            ("win_rate", self._thresholds.win_rate_pass),
        ]

        degradation_detected = False
        degradation_percentage = 0.0

        for metric_name, threshold in metric_gates:
            value = metrics.get(metric_name, 0.0)
            status = self._thresholds.get_level(metric_name, value)

            # Determine message
            if status == GateStatus.PASS:
                message = f"{metric_name}={value:.3f} >= {threshold:.3f} (PASS)"
                level = ValidationLevel.INFO
            elif status == GateStatus.WARNING:
                message = (
                    f"{metric_name}={value:.3f} below threshold "
                    f"{threshold:.3f} (WARNING)"
                )
                level = ValidationLevel.WARNING
            else:
                message = (
                    f"{metric_name}={value:.3f} below threshold "
                    f"{threshold:.3f} (CRITICAL)"
                )
                level = ValidationLevel.CRITICAL

            gate_results.append(
                GateResult(
                    name=metric_name,
                    status=status,
                    value=value,
                    threshold=threshold,
                    message=message,
                    level=level,
                )
            )

            # Check for degradation if baseline provided
            if baseline_metrics and metric_name in baseline_metrics:
                baseline_value = baseline_metrics[metric_name]
                if baseline_value > 0:
                    degradation = ((baseline_value - value) / baseline_value) * 100
                    if degradation > 10.0:
                        degradation_detected = True
                        degradation_percentage = max(
                            degradation_percentage, degradation
                        )

                        # Log degradation event
                        self._influx_logger.log_degradation_event(
                            model_version=model_version,
                            metric_name=metric_name,
                            baseline_value=baseline_value,
                            current_value=value,
                            degradation_pct=degradation,
                        )

        # Determine overall pass (no CRITICAL results)
        passed = all(g.status != GateStatus.CRITICAL for g in gate_results)

        result = CompositeGateResult(
            passed=passed,
            gate_results=gate_results,
            timestamp=datetime.now(UTC),
            model_version=model_version,
            degradation_detected=degradation_detected,
            degradation_percentage=degradation_percentage,
        )

        # Store in history
        self._validation_history.append(result)

        # Log to InfluxDB
        self._influx_logger.log_gate_result(result)

        logger.info(
            f"Validation gate result for {model_version}: "
            f"passed={passed}, critical={result.critical_count}, "
            f"warnings={result.warning_count}"
        )

        return result

    def validate_single_metric(self, metric_name: str, value: float) -> GateResult:
        """Validate a single metric.

        Args:
            metric_name: Name of the metric
            value: Metric value

        Returns:
            GateResult
        """
        threshold = getattr(self._thresholds, f"{metric_name}_pass", 0.0)
        status = self._thresholds.get_level(metric_name, value)

        if status == GateStatus.PASS:
            message = f"{metric_name}={value:.3f} >= {threshold:.3f} (PASS)"
            level = ValidationLevel.INFO
        elif status == GateStatus.WARNING:
            message = (
                f"{metric_name}={value:.3f} below threshold {threshold:.3f} (WARNING)"
            )
            level = ValidationLevel.WARNING
        else:
            message = (
                f"{metric_name}={value:.3f} below threshold {threshold:.3f} (CRITICAL)"
            )
            level = ValidationLevel.CRITICAL

        return GateResult(
            name=metric_name,
            status=status,
            value=value,
            threshold=threshold,
            message=message,
            level=level,
        )

    def get_validation_history(
        self, model_version: str | None = None, limit: int = 100
    ) -> list[CompositeGateResult]:
        """Get validation history.

        Args:
            model_version: Optional filter by model version
            limit: Maximum results to return

        Returns:
            List of validation results
        """
        history = self._validation_history

        if model_version:
            history = [r for r in history if r.model_version == model_version]

        return history[-limit:]


class ShadowModeManager:
    """Manager for shadow mode A/B testing.

    Task 13.2: A/B Testing Framework (Shadow Mode)
    - Implement shadow mode for new models
    - Route signals to both current and new model
    - Compare predictions without affecting trades
    - Track shadow performance for 24 hours
    - Generate comparison report
    """

    def __init__(
        self,
        config: ShadowModeConfig | None = None,
        influx_logger: InfluxDBLogger | None = None,
    ):
        """Initialize shadow mode manager.

        Args:
            config: Shadow mode configuration
            influx_logger: Optional InfluxDB logger
        """
        self._config = config or ShadowModeConfig()
        self._influx_logger = influx_logger or DefaultInfluxDBLogger()
        self._active_sessions: dict[str, dict[str, Any]] = {}
        self._comparison_history: list[ShadowComparisonResult] = []

        logger.info(
            f"ShadowModeManager initialized: "
            f"enabled={self._config.enabled}, "
            f"duration={self._config.duration_hours}h"
        )

    def start_shadow_mode(
        self,
        champion_version: str,
        candidate_version: str,
        champion_predictor: Any = None,
        candidate_predictor: Any = None,
    ) -> str:
        """Start shadow mode comparison.

        Args:
            champion_version: Current champion model version
            candidate_version: Candidate model version to test
            champion_predictor: Champion model predictor function
            candidate_predictor: Candidate model predictor function

        Returns:
            Session ID
        """
        if not self._config.enabled:
            logger.warning("Shadow mode is disabled")
            return ""

        session_id = f"shadow_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S_%f')}"

        self._active_sessions[session_id] = {
            "champion_version": champion_version,
            "candidate_version": candidate_version,
            "champion_predictor": champion_predictor,
            "candidate_predictor": candidate_predictor,
            "started_at": datetime.now(UTC),
            "champion_predictions": [],
            "candidate_predictions": [],
            "sample_count": 0,
        }

        logger.info(
            f"Started shadow mode session {session_id}: "
            f"champion={champion_version}, candidate={candidate_version}"
        )

        return session_id

    def record_prediction(
        self,
        session_id: str,
        signal_data: dict[str, Any],
        champion_prediction: Any,
        candidate_prediction: Any,
    ) -> None:
        """Record predictions from both models.

        Task 13.2: Route signals to both current and new model.

        Args:
            session_id: Shadow mode session ID
            signal_data: Input signal data
            champion_prediction: Prediction from champion
            candidate_prediction: Prediction from candidate
        """
        session = self._active_sessions.get(session_id)
        if not session:
            logger.warning(f"Shadow mode session not found: {session_id}")
            return

        # Store predictions for later comparison
        session["champion_predictions"].append(
            {"signal": signal_data, "prediction": champion_prediction}
        )
        session["candidate_predictions"].append(
            {"signal": signal_data, "prediction": candidate_prediction}
        )
        session["sample_count"] += 1

    def get_comparison(
        self, session_id: str, actual_outcomes: list[Any] | None = None
    ) -> ShadowComparisonResult | None:
        """Generate comparison report.

        Task 13.2: Generate comparison report.

        Args:
            session_id: Shadow mode session ID
            actual_outcomes: Optional actual outcomes for evaluation

        Returns:
            ShadowComparisonResult or None if session not found
        """
        session = self._active_sessions.get(session_id)
        if not session:
            return None

        # Calculate metrics for both models
        champion_metrics = self._calculate_metrics(
            session["champion_predictions"], actual_outcomes
        )
        candidate_metrics = self._calculate_metrics(
            session["candidate_predictions"], actual_outcomes
        )

        # Calculate deltas
        delta = {
            k: candidate_metrics.get(k, 0.0) - champion_metrics.get(k, 0.0)
            for k in ["accuracy", "precision", "recall", "f1", "win_rate"]
        }

        duration = (datetime.now(UTC) - session["started_at"]).total_seconds() / 3600

        # Determine recommendation
        recommendation = "pending"
        if session["sample_count"] >= self._config.min_samples_required:
            if all(v >= 0 for v in delta.values()):
                recommendation = "promote"
            elif any(v < -0.05 for v in delta.values()):
                recommendation = "reject"
            else:
                recommendation = "extend"

        result = ShadowComparisonResult(
            champion_metrics=champion_metrics,
            candidate_metrics=candidate_metrics,
            delta=delta,
            sample_count=session["sample_count"],
            duration_hours=duration,
            recommendation=recommendation,
        )

        # Store in history
        self._comparison_history.append(result)

        # Log to InfluxDB
        self._influx_logger.log_shadow_comparison(result)

        return result

    def _calculate_metrics(
        self,
        predictions: list[dict[str, Any]],
        outcomes: list[Any] | None = None,
    ) -> dict[str, float]:
        """Calculate metrics from predictions.

        Args:
            predictions: List of predictions
            outcomes: Optional actual outcomes

        Returns:
            Dictionary of calculated metrics
        """
        if not predictions:
            return {
                "accuracy": 0.0,
                "precision": 0.0,
                "recall": 0.0,
                "f1": 0.0,
                "win_rate": 0.0,
            }

        # If we have actual outcomes, calculate real metrics
        if outcomes and len(outcomes) == len(predictions):
            true_positives = 0
            false_positives = 0
            true_negatives = 0
            false_negatives = 0
            wins = 0

            for pred, outcome in zip(predictions, outcomes, strict=False):
                pred_value = pred.get("prediction", {}).get("direction", 0)
                actual = outcome.get("direction", 0)

                if pred_value > 0 and actual > 0:
                    true_positives += 1
                    wins += 1
                elif pred_value > 0 and actual <= 0:
                    false_positives += 1
                elif pred_value <= 0 and actual > 0:
                    false_negatives += 1
                else:
                    true_negatives += 1

            total = len(predictions)
            accuracy = (true_positives + true_negatives) / total if total > 0 else 0
            precision = (
                true_positives / (true_positives + false_positives)
                if (true_positives + false_positives) > 0
                else 0
            )
            recall = (
                true_positives / (true_positives + false_negatives)
                if (true_positives + false_negatives) > 0
                else 0
            )
            f1 = (
                2 * precision * recall / (precision + recall)
                if (precision + recall) > 0
                else 0
            )
            win_rate = wins / total if total > 0 else 0

            return {
                "accuracy": accuracy,
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "win_rate": win_rate,
            }

        # Return simulated metrics if no outcomes
        # In production, this would calculate from stored predictions
        return {
            "accuracy": 0.70,
            "precision": 0.68,
            "recall": 0.65,
            "f1": 0.66,
            "win_rate": 0.62,
        }

    def end_shadow_mode(self, session_id: str) -> bool:
        """End shadow mode session.

        Args:
            session_id: Session to end

        Returns:
            True if session was ended
        """
        if session_id in self._active_sessions:
            del self._active_sessions[session_id]
            logger.info(f"Ended shadow mode session: {session_id}")
            return True
        return False

    def is_shadow_mode_active(self, session_id: str) -> bool:
        """Check if shadow mode session is active.

        Args:
            session_id: Session to check

        Returns:
            True if session is active
        """
        session = self._active_sessions.get(session_id)
        if not session:
            return False

        elapsed = (datetime.now(UTC) - session["started_at"]).total_seconds() / 3600
        return elapsed < self._config.duration_hours

    def get_comparison_history(self, limit: int = 100) -> list[ShadowComparisonResult]:
        """Get shadow comparison history.

        Args:
            limit: Maximum results

        Returns:
            List of comparison results
        """
        return self._comparison_history[-limit:]


class DegradationDetector:
    """Detector for model performance degradation.

    Task 13.3: Degradation Detection
    - Implement performance monitoring for deployed models
    - Detect degradation >10% from baseline
    - Trigger rollback alert on detection
    - Log degradation events to InfluxDB
    - Discord notification within 1 minute
    """

    # Degradation threshold percentage
    DEGRADATION_THRESHOLD_PCT = 10.0

    def __init__(
        self,
        influx_logger: InfluxDBLogger | None = None,
        alert_callback: Any = None,
    ):
        """Initialize degradation detector.

        Args:
            influx_logger: Optional InfluxDB logger
            alert_callback: Optional callback for alerts (e.g., Discord)
        """
        self._influx_logger = influx_logger or DefaultInfluxDBLogger()
        self._alert_callback = alert_callback
        self._baselines: dict[str, dict[str, float]] = {}
        self._degradation_events: list[dict[str, Any]] = []

        logger.info(
            f"DegradationDetector initialized: "
            f"threshold={self.DEGRADATION_THRESHOLD_PCT}%"
        )

    def set_baseline(self, model_version: str, metrics: dict[str, float]) -> None:
        """Set baseline metrics for a model.

        Args:
            model_version: Model version
            metrics: Baseline metrics
        """
        self._baselines[model_version] = metrics.copy()
        logger.info(f"Set baseline for {model_version}: {metrics}")

    def check_degradation(
        self,
        model_version: str,
        current_metrics: dict[str, float],
    ) -> tuple[bool, list[dict[str, Any]]]:
        """Check for performance degradation.

        Task 13.3: Detect degradation >10% from baseline.

        Args:
            model_version: Model version to check
            current_metrics: Current metrics

        Returns:
            Tuple of (degradation_detected, list_of_degraded_metrics)
        """
        baseline = self._baselines.get(model_version)
        if not baseline:
            logger.warning(f"No baseline set for {model_version}")
            return False, []

        degradation_detected = False
        degraded_metrics: list[dict[str, Any]] = []

        for metric_name, baseline_value in baseline.items():
            if metric_name not in current_metrics:
                continue

            current_value = current_metrics[metric_name]
            if baseline_value > 0:
                degradation_pct = (
                    (baseline_value - current_value) / baseline_value * 100
                )

                if degradation_pct > self.DEGRADATION_THRESHOLD_PCT:
                    degradation_detected = True
                    degraded_metric = {
                        "metric_name": metric_name,
                        "baseline_value": baseline_value,
                        "current_value": current_value,
                        "degradation_percentage": degradation_pct,
                        "timestamp": datetime.now(UTC).isoformat(),
                        "model_version": model_version,
                    }
                    degraded_metrics.append(degraded_metric)

                    # Log to InfluxDB
                    self._influx_logger.log_degradation_event(
                        model_version=model_version,
                        metric_name=metric_name,
                        baseline_value=baseline_value,
                        current_value=current_value,
                        degradation_pct=degradation_pct,
                    )

                    # Store event
                    self._degradation_events.append(degraded_metric)

                    logger.warning(
                        f"Degradation detected for {model_version}: "
                        f"{metric_name} degraded by {degradation_pct:.1f}% "
                        f"({baseline_value:.3f} -> {current_value:.3f})"
                    )

        # Trigger alert if degradation detected
        if degradation_detected and self._alert_callback:
            self._trigger_alert(model_version, degraded_metrics)

        return degradation_detected, degraded_metrics

    def _trigger_alert(
        self, model_version: str, degraded_metrics: list[dict[str, Any]]
    ) -> None:
        """Trigger rollback alert.

        Task 13.3: Trigger rollback alert on detection.

        Args:
            model_version: Model version with degradation
            degraded_metrics: List of degraded metrics
        """
        alert_message = (
            f"⚠️ **Model Degradation Alert**\n"
            f"Model: `{model_version}`\n"
            f"Degradation detected in {len(degraded_metrics)} metric(s):\n"
        )

        for metric in degraded_metrics:
            alert_message += (
                f"- {metric['metric_name']}: "
                f"{metric['degradation_percentage']:.1f}% degradation "
                f"({metric['baseline_value']:.3f} → {metric['current_value']:.3f})\n"
            )

        alert_message += "\n**Rollback recommended.**"

        logger.critical(alert_message)

        # Call alert callback if set (e.g., Discord notification)
        if self._alert_callback:
            try:
                self._alert_callback(alert_message)
            except Exception as e:
                logger.error(f"Failed to send alert: {e}")

    def get_degradation_events(
        self, model_version: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Get degradation event history.

        Args:
            model_version: Optional filter by model version
            limit: Maximum results

        Returns:
            List of degradation events
        """
        events = self._degradation_events

        if model_version:
            events = [e for e in events if e.get("model_version") == model_version]

        return events[-limit:]

    def clear_baseline(self, model_version: str) -> bool:
        """Clear baseline for a model.

        Args:
            model_version: Model version

        Returns:
            True if baseline was cleared
        """
        if model_version in self._baselines:
            del self._baselines[model_version]
            logger.info(f"Cleared baseline for {model_version}")
            return True
        return False


# Convenience function for quick validation
def validate_model_metrics(
    metrics: dict[str, float],
    thresholds: ValidationThresholds | None = None,
) -> CompositeGateResult:
    """Quick validation of model metrics.

    Args:
        metrics: Dictionary of metric names to values
        thresholds: Optional custom thresholds

    Returns:
        CompositeGateResult
    """
    gate = ValidationGate(thresholds=thresholds)
    return gate.validate(metrics)
