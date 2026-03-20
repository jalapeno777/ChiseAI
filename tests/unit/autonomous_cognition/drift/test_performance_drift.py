"""
Unit tests for performance_drift.py
"""

import pytest
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, MagicMock

from src.autonomous_cognition.drift.performance_drift import (
    PerformanceDriftDetector,
    Baseline,
    DriftResult,
    DriftSeverity,
    RootCauseTag,
    METRIC_CONFIGS,
)


class TestBaseline:
    """Tests for Baseline dataclass."""

    def test_baseline_creation(self):
        """Test creating a baseline."""
        baseline = Baseline(
            metric_name="test_metric",
            mean=10.0,
            std=2.0,
            values=[8.0, 10.0, 12.0],
            window_days=7,
            established_at=datetime.now(UTC),
        )

        assert baseline.metric_name == "test_metric"
        assert baseline.mean == 10.0
        assert baseline.std == 2.0

    def test_baseline_to_dict(self):
        """Test baseline serialization."""
        now = datetime.now(UTC)
        baseline = Baseline(
            metric_name="test_metric",
            mean=10.0,
            std=2.0,
            values=[8.0, 10.0, 12.0],
            window_days=7,
            established_at=now,
        )

        data = baseline.to_dict()

        assert data["metric_name"] == "test_metric"
        assert data["mean"] == 10.0
        assert data["established_at"] == now.isoformat()

    def test_baseline_from_dict(self):
        """Test baseline deserialization."""
        now = datetime.now(UTC)
        data = {
            "metric_name": "test_metric",
            "mean": 10.0,
            "std": 2.0,
            "values": [8.0, 10.0, 12.0],
            "window_days": 7,
            "established_at": now.isoformat(),
        }

        baseline = Baseline.from_dict(data)

        assert baseline.metric_name == "test_metric"
        assert baseline.mean == 10.0
        assert baseline.established_at == now


class TestDriftResult:
    """Tests for DriftResult dataclass."""

    def test_drift_result_creation(self):
        """Test creating a drift result."""
        result = DriftResult(
            metric_name="test_metric",
            current_value=15.0,
            baseline_mean=10.0,
            baseline_std=2.0,
            z_score=2.5,
            is_drift=True,
            severity="warning",
            root_cause_tag="unknown",
            detected_at=datetime.now(UTC),
        )

        assert result.metric_name == "test_metric"
        assert result.is_drift is True
        assert result.severity == "warning"

    def test_drift_result_to_dict(self):
        """Test drift result serialization."""
        now = datetime.now(UTC)
        result = DriftResult(
            metric_name="test_metric",
            current_value=15.0,
            baseline_mean=10.0,
            baseline_std=2.0,
            z_score=2.5,
            is_drift=True,
            severity="warning",
            root_cause_tag="code",
            detected_at=now,
            trend="degrading",
        )

        data = result.to_dict()

        assert data["metric_name"] == "test_metric"
        assert data["is_drift"] is True
        assert data["trend"] == "degrading"
        assert data["detected_at"] == now.isoformat()


class TestPerformanceDriftDetectorInitialization:
    """Tests for detector initialization."""

    def test_detector_init_defaults(self):
        """Test detector with default parameters."""
        detector = PerformanceDriftDetector()

        assert detector.default_window_days == 7
        assert detector.drift_threshold_std == 2.0
        assert detector.redis_client is None
        assert detector.influxdb_client is None

    def test_detector_init_custom(self):
        """Test detector with custom parameters."""
        mock_redis = Mock()
        mock_influx = Mock()

        detector = PerformanceDriftDetector(
            redis_client=mock_redis,
            influxdb_client=mock_influx,
            default_window_days=14,
            drift_threshold_std=1.5,
        )

        assert detector.default_window_days == 14
        assert detector.drift_threshold_std == 1.5
        assert detector.redis_client == mock_redis
        assert detector.influxdb_client == mock_influx


class TestEstablishBaseline:
    """Tests for establish_baseline method."""

    def test_establish_baseline_with_values(self):
        """Test establishing baseline with provided values."""
        detector = PerformanceDriftDetector()
        values = [0.95, 0.96, 0.94, 0.95, 0.96, 0.95, 0.95]

        baseline = detector.establish_baseline(
            metric_name="cycle_success_rate",
            days=7,
            values=values,
        )

        assert baseline.metric_name == "cycle_success_rate"
        assert baseline.window_days == 7
        assert len(baseline.values) == 7
        assert baseline.mean == pytest.approx(0.951, abs=0.01)

    def test_establish_baseline_synthetic(self):
        """Test establishing baseline with synthetic data."""
        detector = PerformanceDriftDetector()

        baseline = detector.establish_baseline(
            metric_name="cycle_success_rate",
            days=7,
        )

        assert baseline.metric_name == "cycle_success_rate"
        assert baseline.window_days == 7
        assert len(baseline.values) == 7 * 24  # Hourly samples

    def test_establish_baseline_empty_values(self):
        """Test error with empty values."""
        detector = PerformanceDriftDetector()

        with pytest.raises(ValueError, match="No values available"):
            detector.establish_baseline(
                metric_name="test_metric",
                values=[],
            )


class TestDetectDrift:
    """Tests for detect_drift method."""

    def test_detect_drift_no_drift(self):
        """Test detection with normal value (no drift)."""
        detector = PerformanceDriftDetector()

        # Establish baseline with some variance (not all same values)
        import random

        random.seed(42)
        values = [0.95 + random.gauss(0, 0.01) for _ in range(168)]
        detector.establish_baseline(
            metric_name="cycle_success_rate",
            values=values,
        )

        # Current value close to baseline mean
        result = detector.detect_drift("cycle_success_rate", 0.95)

        assert result.is_drift is False
        assert result.metric_name == "cycle_success_rate"

    def test_detect_drift_positive(self):
        """Test detection with degraded value (drift detected)."""
        detector = PerformanceDriftDetector()

        # Establish baseline around 0.95
        detector.establish_baseline(
            metric_name="cycle_success_rate",
            values=[0.95] * 168,
        )

        # Current value significantly below baseline
        result = detector.detect_drift("cycle_success_rate", 0.85)

        assert result.is_drift is True
        assert result.z_score < -2.0  # More than 2 std below

    def test_detect_drift_no_baseline(self):
        """Test error when no baseline exists."""
        detector = PerformanceDriftDetector()

        with pytest.raises(ValueError, match="No baseline established"):
            detector.detect_drift("unknown_metric", 0.5)

    def test_detect_drift_with_context(self):
        """Test detection with context for root cause."""
        detector = PerformanceDriftDetector()

        detector.establish_baseline(
            metric_name="qdrant_write_latency",
            values=[100.0] * 168,
        )

        context = {"error": "qdrant connection timeout"}
        result = detector.detect_drift(
            "qdrant_write_latency",
            500.0,
            context=context,
        )

        assert result.is_drift is True
        assert result.root_cause_tag == "infra"

    def test_detect_drift_lower_is_better(self):
        """Test detection for metric where lower is better."""
        detector = PerformanceDriftDetector()

        # Brier score: lower is better
        detector.establish_baseline(
            metric_name="calibration_quality",
            values=[0.15] * 168,
        )

        # Higher Brier score is worse
        result = detector.detect_drift("calibration_quality", 0.25)

        assert result.is_drift is True
        assert result.z_score > 2.0  # More than 2 std above


class TestGetDriftStatus:
    """Tests for get_drift_status method."""

    def test_drift_status_empty(self):
        """Test status with no baselines."""
        detector = PerformanceDriftDetector()

        status = detector.get_drift_status()

        assert status["monitored_metrics"] == []
        assert status["summary"]["total_drifts"] == 0

    def test_drift_status_with_metrics(self):
        """Test status with established baselines."""
        detector = PerformanceDriftDetector()

        detector.establish_baseline("cycle_success_rate", values=[0.95] * 168)
        detector.establish_baseline("learning_velocity", values=[5.0] * 168)

        status = detector.get_drift_status()

        assert len(status["monitored_metrics"]) == 2
        assert "cycle_success_rate" in status["monitored_metrics"]
        assert "learning_velocity" in status["monitored_metrics"]

    def test_drift_status_with_recent_drifts(self):
        """Test status includes recent drifts."""
        detector = PerformanceDriftDetector()

        detector.establish_baseline("cycle_success_rate", values=[0.95] * 168)
        detector.detect_drift("cycle_success_rate", 0.85)  # Trigger drift

        status = detector.get_drift_status()

        assert status["summary"]["total_drifts"] >= 1
        assert len(status["recent_drifts"]) >= 1


class TestGetDriftHistory:
    """Tests for get_drift_history method."""

    def test_drift_history_empty(self):
        """Test history with no detections."""
        detector = PerformanceDriftDetector()

        history = detector.get_drift_history()

        assert history == []

    def test_drift_history_all(self):
        """Test getting all history."""
        detector = PerformanceDriftDetector()

        detector.establish_baseline("cycle_success_rate", values=[0.95] * 168)
        detector.detect_drift("cycle_success_rate", 0.85)
        detector.detect_drift("cycle_success_rate", 0.84)

        history = detector.get_drift_history()

        assert len(history) == 2

    def test_drift_history_filter_by_metric(self):
        """Test filtering history by metric."""
        detector = PerformanceDriftDetector()

        detector.establish_baseline("cycle_success_rate", values=[0.95] * 168)
        detector.establish_baseline("learning_velocity", values=[5.0] * 168)
        detector.detect_drift("cycle_success_rate", 0.85)
        detector.detect_drift("learning_velocity", 2.0)

        history = detector.get_drift_history(metric_name="cycle_success_rate")

        assert len(history) == 1
        assert history[0].metric_name == "cycle_success_rate"

    def test_drift_history_filter_by_severity(self):
        """Test filtering history by severity."""
        detector = PerformanceDriftDetector()

        # Use values with variance to get proper severity calculation
        import random

        random.seed(42)
        values = [0.95 + random.gauss(0, 0.01) for _ in range(168)]
        detector.establish_baseline("cycle_success_rate", values=values)
        result = detector.detect_drift(
            "cycle_success_rate", 0.85
        )  # Should be warning or critical

        history = detector.get_drift_history(severity=result.severity)

        # Should include the drift with matching severity
        assert len(history) >= 1


class TestAlertOnDrift:
    """Tests for alert_on_drift method."""

    def test_alert_no_drift(self):
        """Test no alert when no drift."""
        detector = PerformanceDriftDetector()

        result = DriftResult(
            metric_name="test",
            current_value=10.0,
            baseline_mean=10.0,
            baseline_std=1.0,
            z_score=0.0,
            is_drift=False,
            severity="info",
            root_cause_tag="unknown",
            detected_at=datetime.now(UTC),
        )

        assert detector.alert_on_drift(result) is False

    def test_alert_critical(self):
        """Test alert on critical drift."""
        detector = PerformanceDriftDetector()

        result = DriftResult(
            metric_name="test",
            current_value=10.0,
            baseline_mean=5.0,
            baseline_std=1.0,
            z_score=5.0,
            is_drift=True,
            severity="critical",
            root_cause_tag="infra",
            detected_at=datetime.now(UTC),
        )

        assert detector.alert_on_drift(result) is True

    def test_alert_warning_new(self):
        """Test alert on new warning drift."""
        detector = PerformanceDriftDetector()

        result = DriftResult(
            metric_name="test",
            current_value=10.0,
            baseline_mean=5.0,
            baseline_std=1.0,
            z_score=3.0,
            is_drift=True,
            severity="warning",
            root_cause_tag="code",
            detected_at=datetime.now(UTC),
        )

        assert detector.alert_on_drift(result) is True

    def test_alert_info_degrading(self):
        """Test alert on info with degrading trend."""
        detector = PerformanceDriftDetector()

        result = DriftResult(
            metric_name="test",
            current_value=10.0,
            baseline_mean=5.0,
            baseline_std=1.0,
            z_score=1.8,
            is_drift=True,
            severity="info",
            root_cause_tag="unknown",
            detected_at=datetime.now(UTC),
            trend="degrading",
        )

        assert detector.alert_on_drift(result) is True


class TestRootCauseTagging:
    """Tests for root cause tagging."""

    def test_tag_infra_from_metric(self):
        """Test infra tag from metric name."""
        detector = PerformanceDriftDetector()

        detector.establish_baseline("qdrant_write_latency", values=[100.0] * 168)
        result = detector.detect_drift("qdrant_write_latency", 500.0)

        assert result.root_cause_tag == "infra"

    def test_tag_infra_from_context(self):
        """Test infra tag from context."""
        detector = PerformanceDriftDetector()

        detector.establish_baseline("cycle_success_rate", values=[0.95] * 168)
        result = detector.detect_drift(
            "cycle_success_rate", 0.85, context={"error": "redis connection timeout"}
        )

        assert result.root_cause_tag == "infra"

    def test_tag_code_from_context(self):
        """Test code tag from context."""
        detector = PerformanceDriftDetector()

        detector.establish_baseline("cycle_success_rate", values=[0.95] * 168)
        result = detector.detect_drift(
            "cycle_success_rate", 0.85, context={"event": "deployment completed"}
        )

        assert result.root_cause_tag == "code"

    def test_tag_data_from_context(self):
        """Test data tag from context."""
        detector = PerformanceDriftDetector()

        detector.establish_baseline("cycle_success_rate", values=[0.95] * 168)
        result = detector.detect_drift(
            "cycle_success_rate", 0.85, context={"error": "data corruption detected"}
        )

        assert result.root_cause_tag == "data"

    def test_tag_unknown(self):
        """Test unknown tag when no indicators."""
        detector = PerformanceDriftDetector()

        detector.establish_baseline("cycle_success_rate", values=[0.95] * 168)
        result = detector.detect_drift("cycle_success_rate", 0.85)

        assert result.root_cause_tag == "unknown"


class TestUpdateBaseline:
    """Tests for update_baseline method."""

    def test_update_baseline_adds_value(self):
        """Test updating baseline adds new value."""
        detector = PerformanceDriftDetector()

        original = detector.establish_baseline(
            "cycle_success_rate",
            values=[0.95] * 100,  # Use smaller count to stay under max window
        )
        original_count = len(original.values)

        updated = detector.update_baseline("cycle_success_rate", 0.96)

        assert len(updated.values) == original_count + 1
        assert updated.values[-1] == 0.96

    def test_update_baseline_recalculates(self):
        """Test updating baseline recalculates statistics."""
        detector = PerformanceDriftDetector()

        detector.establish_baseline(
            "cycle_success_rate",
            values=[0.90] * 168,
        )
        original_mean = detector._baselines["cycle_success_rate"].mean

        detector.update_baseline("cycle_success_rate", 0.99)
        updated_mean = detector._baselines["cycle_success_rate"].mean

        assert updated_mean > original_mean

    def test_update_baseline_no_baseline(self):
        """Test error when no baseline exists."""
        detector = PerformanceDriftDetector()

        with pytest.raises(ValueError, match="No baseline established"):
            detector.update_baseline("unknown_metric", 0.5)


class TestMetricConfigs:
    """Tests for metric configurations."""

    def test_metric_configs_exist(self):
        """Test that metric configs are defined."""
        assert "cycle_success_rate" in METRIC_CONFIGS
        assert "learning_velocity" in METRIC_CONFIGS
        assert "calibration_quality" in METRIC_CONFIGS

    def test_cycle_success_rate_config(self):
        """Test cycle success rate configuration."""
        config = METRIC_CONFIGS["cycle_success_rate"]

        assert config["baseline_target"] == 0.95
        assert config["drift_threshold"] == 0.90
        assert config["higher_is_better"] is True

    def test_calibration_quality_config(self):
        """Test calibration quality configuration."""
        config = METRIC_CONFIGS["calibration_quality"]

        assert config["baseline_target"] == 0.15
        assert config["drift_threshold"] == 0.20
        assert config["higher_is_better"] is False

    def test_get_metric_config(self):
        """Test getting metric config from detector."""
        detector = PerformanceDriftDetector()

        config = detector.get_metric_config("cycle_success_rate")

        assert config["baseline_target"] == 0.95
        assert config["higher_is_better"] is True

    def test_get_metric_config_unknown(self):
        """Test getting config for unknown metric."""
        detector = PerformanceDriftDetector()

        config = detector.get_metric_config("unknown_metric")

        assert "baseline_target" in config
        assert "higher_is_better" in config
