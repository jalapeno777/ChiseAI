"""Tests for ValidationGate and related classes in model_validator.py.

Tests ValidationGate initialization, validation methods, threshold checking,
degradation detection, and validation history tracking.
"""

from unittest.mock import MagicMock

import pytest

from ml.validation.model_validator import (
    CompositeGateResult,
    GateResult,
    GateStatus,
    ValidationGate,
    ValidationLevel,
    ValidationThresholds,
    validate_model_metrics,
)


class TestValidationThresholds:
    """Tests for ValidationThresholds dataclass."""

    def test_default_thresholds(self):
        """Test default threshold values are set correctly."""
        t = ValidationThresholds()
        assert t.accuracy_pass == 0.60
        assert t.precision_pass == 0.55
        assert t.recall_pass == 0.50
        assert t.f1_pass == 0.52
        assert t.win_rate_pass == 0.55

    def test_custom_thresholds(self):
        """Test custom threshold values."""
        t = ValidationThresholds(accuracy_pass=0.80, precision_pass=0.75)
        assert t.accuracy_pass == 0.80
        assert t.precision_pass == 0.75
        # Other defaults preserved
        assert t.recall_pass == 0.50

    def test_get_level_pass(self, default_thresholds):
        """Test get_level returns PASS for values above pass threshold."""
        result = default_thresholds.get_level("accuracy", 0.70)
        assert result == GateStatus.PASS

    def test_get_level_warning(self, default_thresholds):
        """Test get_level returns WARNING for values between warning and pass."""
        result = default_thresholds.get_level("accuracy", 0.57)
        assert result == GateStatus.WARNING

    def test_get_level_critical(self, default_thresholds):
        """Test get_level returns CRITICAL for values below warning threshold."""
        result = default_thresholds.get_level("accuracy", 0.40)
        assert result == GateStatus.CRITICAL

    def test_get_level_unknown_metric(self, default_thresholds):
        """Test get_level with unknown metric defaults thresholds to 0.0, so any value passes."""
        result = default_thresholds.get_level("unknown_metric", 0.99)
        # getattr returns 0.0 for unknown metrics, so 0.99 >= 0.0 -> PASS
        assert result == GateStatus.PASS

    def test_get_level_unknown_metric_zero(self, default_thresholds):
        """Test get_level with unknown metric and zero value passes (>= 0.0)."""
        result = default_thresholds.get_level("unknown_metric", 0.0)
        assert result == GateStatus.PASS

    def test_frozen_immutability(self):
        """Test that ValidationThresholds is frozen (immutable)."""
        t = ValidationThresholds()
        with pytest.raises(AttributeError):
            t.accuracy_pass = 0.99


class TestGateResult:
    """Tests for GateResult dataclass."""

    def test_to_dict(self):
        """Test GateResult serialization to dict."""
        gr = GateResult(
            name="accuracy",
            status=GateStatus.PASS,
            value=0.75,
            threshold=0.60,
            message="accuracy=0.750 >= 0.600 (PASS)",
            level=ValidationLevel.INFO,
        )
        d = gr.to_dict()
        assert d["name"] == "accuracy"
        assert d["status"] == "pass"
        assert d["value"] == 0.75
        assert d["threshold"] == 0.60
        assert d["level"] == "info"


class TestCompositeGateResult:
    """Tests for CompositeGateResult dataclass."""

    def test_critical_count(self):
        """Test counting critical gate results."""
        gate_results = [
            GateResult("a", GateStatus.PASS, 0.7, 0.6, "pass", ValidationLevel.INFO),
            GateResult(
                "b", GateStatus.CRITICAL, 0.3, 0.5, "crit", ValidationLevel.CRITICAL
            ),
            GateResult(
                "c", GateStatus.CRITICAL, 0.2, 0.5, "crit", ValidationLevel.CRITICAL
            ),
        ]
        result = CompositeGateResult(passed=False, gate_results=gate_results)
        assert result.critical_count == 2

    def test_warning_count(self):
        """Test counting warning gate results."""
        gate_results = [
            GateResult("a", GateStatus.PASS, 0.7, 0.6, "pass", ValidationLevel.INFO),
            GateResult(
                "b", GateStatus.WARNING, 0.57, 0.6, "warn", ValidationLevel.WARNING
            ),
            GateResult(
                "c", GateStatus.WARNING, 0.48, 0.5, "warn", ValidationLevel.WARNING
            ),
        ]
        result = CompositeGateResult(passed=True, gate_results=gate_results)
        assert result.warning_count == 2

    def test_to_dict(self):
        """Test CompositeGateResult serialization."""
        gate_results = [
            GateResult("a", GateStatus.PASS, 0.7, 0.6, "pass", ValidationLevel.INFO),
        ]
        result = CompositeGateResult(
            passed=True,
            gate_results=gate_results,
            model_version="v1",
        )
        d = result.to_dict()
        assert d["passed"] is True
        assert len(d["gate_results"]) == 1
        assert d["model_version"] == "v1"
        assert "timestamp" in d


class TestValidationGateInit:
    """Tests for ValidationGate initialization."""

    def test_default_initialization(self):
        """Test default initialization creates default thresholds."""
        gate = ValidationGate()
        assert gate._thresholds.accuracy_pass == 0.60
        assert isinstance(gate._validation_history, list)

    def test_custom_thresholds(self, custom_thresholds, mock_influx_logger):
        """Test initialization with custom thresholds."""
        gate = ValidationGate(
            thresholds=custom_thresholds,
            influx_logger=mock_influx_logger,
        )
        assert gate._thresholds.accuracy_pass == 0.80

    def test_empty_history_on_init(self, validation_gate):
        """Test that validation history is empty on initialization."""
        assert len(validation_gate._validation_history) == 0


class TestValidationGateValidate:
    """Tests for ValidationGate.validate() method."""

    def test_all_metrics_pass(
        self, validation_gate, passing_metrics, mock_influx_logger
    ):
        """Test validation with all passing metrics."""
        result = validation_gate.validate(passing_metrics, model_version="v1")
        assert result.passed is True
        assert result.model_version == "v1"
        assert result.critical_count == 0
        mock_influx_logger.log_gate_result.assert_called_once()

    def test_critical_metrics_fail(
        self, validation_gate, failing_metrics, mock_influx_logger
    ):
        """Test validation with all failing metrics."""
        result = validation_gate.validate(failing_metrics, model_version="v_fail")
        assert result.passed is False
        assert result.critical_count == 5
        assert result.model_version == "v_fail"

    def test_warning_metrics(self, validation_gate, warning_metrics):
        """Test validation with warning-level metrics (no critical)."""
        result = validation_gate.validate(warning_metrics)
        # Warnings don't fail the gate
        assert result.passed is True
        assert result.warning_count == 5

    def test_missing_metric_defaults_to_zero(self, validation_gate, mock_influx_logger):
        """Test that missing metrics default to 0.0 (critical)."""
        result = validation_gate.validate({}, model_version="v_empty")
        assert result.passed is False
        # All 5 metrics should be critical (default 0.0)
        assert result.critical_count == 5

    def test_partial_metrics(self, validation_gate, mock_influx_logger):
        """Test validation with only some metrics provided."""
        result = validation_gate.validate(
            {"accuracy": 0.70, "precision": 0.60},
            model_version="v_partial",
        )
        # accuracy and precision pass; recall, f1, win_rate default to 0.0
        assert result.passed is False
        assert result.critical_count == 3  # recall, f1, win_rate

    def test_validation_stored_in_history(self, validation_gate, passing_metrics):
        """Test that each validation is stored in history."""
        validation_gate.validate(passing_metrics, model_version="v1")
        validation_gate.validate(passing_metrics, model_version="v2")
        assert len(validation_gate._validation_history) == 2

    def test_degradation_detection(
        self, validation_gate, passing_metrics, mock_influx_logger
    ):
        """Test degradation detection with baseline metrics."""
        baseline = {
            "accuracy": 0.90,
            "precision": 0.85,
            "recall": 0.80,
            "f1": 0.82,
            "win_rate": 0.85,
        }
        result = validation_gate.validate(
            passing_metrics,
            model_version="v_degrade",
            baseline_metrics=baseline,
        )
        assert result.degradation_detected is True
        assert result.degradation_percentage > 0
        # Degradation events should be logged
        assert mock_influx_logger.log_degradation_event.called

    def test_no_degradation_when_improved(self, validation_gate, mock_influx_logger):
        """Test no degradation when current metrics are better than baseline."""
        current = {
            "accuracy": 0.90,
            "precision": 0.85,
            "recall": 0.80,
            "f1": 0.82,
            "win_rate": 0.85,
        }
        baseline = {
            "accuracy": 0.70,
            "precision": 0.65,
            "recall": 0.60,
            "f1": 0.62,
            "win_rate": 0.65,
        }
        result = validation_gate.validate(
            current,
            model_version="v_improve",
            baseline_metrics=baseline,
        )
        assert result.degradation_detected is False


class TestValidationGateSingleMetric:
    """Tests for ValidationGate.validate_single_metric() method."""

    def test_single_metric_pass(self, validation_gate):
        """Test validating a single passing metric."""
        result = validation_gate.validate_single_metric("accuracy", 0.70)
        assert result.status == GateStatus.PASS
        assert result.name == "accuracy"
        assert result.value == 0.70

    def test_single_metric_critical(self, validation_gate):
        """Test validating a single failing metric."""
        result = validation_gate.validate_single_metric("accuracy", 0.40)
        assert result.status == GateStatus.CRITICAL

    def test_single_metric_warning(self, validation_gate):
        """Test validating a single warning metric."""
        result = validation_gate.validate_single_metric("accuracy", 0.57)
        assert result.status == GateStatus.WARNING


class TestValidationGateHistory:
    """Tests for ValidationGate.get_validation_history() method."""

    def test_get_all_history(self, validation_gate, passing_metrics):
        """Test getting all validation history."""
        validation_gate.validate(passing_metrics, model_version="v1")
        validation_gate.validate(passing_metrics, model_version="v2")
        validation_gate.validate(passing_metrics, model_version="v3")
        history = validation_gate.get_validation_history()
        assert len(history) == 3

    def test_filter_by_model_version(
        self, validation_gate, passing_metrics, failing_metrics
    ):
        """Test filtering history by model version."""
        validation_gate.validate(passing_metrics, model_version="v1")
        validation_gate.validate(failing_metrics, model_version="v2")
        validation_gate.validate(passing_metrics, model_version="v1")
        history = validation_gate.get_validation_history(model_version="v1")
        assert len(history) == 2
        assert all(r.model_version == "v1" for r in history)

    def test_history_limit(self, validation_gate, passing_metrics):
        """Test history limit parameter."""
        for i in range(10):
            validation_gate.validate(passing_metrics, model_version=f"v{i}")
        history = validation_gate.get_validation_history(limit=3)
        assert len(history) == 3


class TestDegradationDetector:
    """Tests for DegradationDetector class."""

    def test_set_and_check_baseline_no_degradation(self):
        """Test baseline check with no degradation."""
        from ml.validation.model_validator import DegradationDetector

        detector = DegradationDetector(influx_logger=MagicMock())
        detector.set_baseline("v1", {"accuracy": 0.70, "precision": 0.65})
        degraded, events = detector.check_degradation(
            "v1", {"accuracy": 0.69, "precision": 0.64}
        )
        assert degraded is False
        assert len(events) == 0

    def test_check_degradation_detected(self):
        """Test that >10% degradation is detected."""
        from ml.validation.model_validator import DegradationDetector

        mock_logger = MagicMock()
        detector = DegradationDetector(influx_logger=mock_logger)
        detector.set_baseline("v1", {"accuracy": 0.80})
        degraded, events = detector.check_degradation("v1", {"accuracy": 0.65})
        # (0.80 - 0.65) / 0.80 = 18.75% > 10%
        assert degraded is True
        assert len(events) == 1
        assert events[0]["degradation_percentage"] == pytest.approx(18.75)

    def test_check_no_baseline_set(self):
        """Test check returns False when no baseline is set."""
        from ml.validation.model_validator import DegradationDetector

        detector = DegradationDetector(influx_logger=MagicMock())
        degraded, events = detector.check_degradation("v_unknown", {"accuracy": 0.50})
        assert degraded is False
        assert events == []

    def test_alert_callback_triggered(self):
        """Test that alert callback is called on degradation."""
        from ml.validation.model_validator import DegradationDetector

        alert_callback = MagicMock()
        detector = DegradationDetector(
            influx_logger=MagicMock(),
            alert_callback=alert_callback,
        )
        detector.set_baseline("v1", {"accuracy": 0.90})
        detector.check_degradation("v1", {"accuracy": 0.50})
        alert_callback.assert_called_once()

    def test_clear_baseline(self):
        """Test clearing a baseline."""
        from ml.validation.model_validator import DegradationDetector

        detector = DegradationDetector(influx_logger=MagicMock())
        detector.set_baseline("v1", {"accuracy": 0.70})
        assert detector.clear_baseline("v1") is True
        assert detector.clear_baseline("v1") is False

    def test_get_degradation_events(self):
        """Test retrieving degradation events."""
        from ml.validation.model_validator import DegradationDetector

        detector = DegradationDetector(influx_logger=MagicMock())
        detector.set_baseline("v1", {"accuracy": 0.90})
        detector.check_degradation("v1", {"accuracy": 0.50})
        detector.set_baseline("v2", {"accuracy": 0.80})
        detector.check_degradation("v2", {"accuracy": 0.40})
        events = detector.get_degradation_events()
        assert len(events) == 2
        events_v1 = detector.get_degradation_events(model_version="v1")
        assert len(events_v1) == 1


class TestValidateModelMetrics:
    """Tests for the validate_model_metrics convenience function."""

    def test_quick_validation_pass(self):
        """Test quick validation with passing metrics."""
        result = validate_model_metrics(
            {
                "accuracy": 0.75,
                "precision": 0.70,
                "recall": 0.65,
                "f1": 0.67,
                "win_rate": 0.70,
            },
        )
        assert result.passed is True

    def test_quick_validation_fail(self):
        """Test quick validation with failing metrics."""
        result = validate_model_metrics({"accuracy": 0.30})
        assert result.passed is False

    def test_quick_validation_custom_thresholds(self):
        """Test quick validation with custom thresholds."""
        high_thresholds = ValidationThresholds(accuracy_pass=0.90)
        result = validate_model_metrics(
            {"accuracy": 0.85},
            thresholds=high_thresholds,
        )
        assert result.passed is False
