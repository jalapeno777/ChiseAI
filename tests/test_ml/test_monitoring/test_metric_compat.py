"""Tests for metric name sanitization and format compatibility.

ST-MVP-008: Verify Prometheus/InfluxDB metric name sanitization,
round-trip fidelity, and alert format compatibility.
"""

from datetime import UTC, datetime

import pytest

from ml.monitoring.registry_alerts import Alert, AlertSeverity
from ml.monitoring.registry_metrics import sanitize_metric_name


class TestSanitizeMetricName:
    """Test sanitize_metric_name for Prometheus and InfluxDB targets."""

    # --- Prometheus target format ---

    def test_prometheus_dots_to_underscores(self):
        """Dots in metric names must become underscores for Prometheus."""
        assert (
            sanitize_metric_name("model.accuracy.score", "prometheus")
            == "model_accuracy_score"
        )

    def test_prometheus_hyphens_to_underscores(self):
        """Hyphens in metric names must become underscores for Prometheus."""
        assert (
            sanitize_metric_name("model-accuracy-score", "prometheus")
            == "model_accuracy_score"
        )

    def test_prometheus_uppercase_to_lowercase(self):
        """Uppercase characters must be lowercased for Prometheus."""
        assert (
            sanitize_metric_name("ModelAccuracyScore", "prometheus")
            == "modelaccuracyscore"
        )

    def test_prometheus_collapse_double_underscores(self):
        """Consecutive underscores should be collapsed."""
        assert (
            sanitize_metric_name("model__accuracy__score", "prometheus")
            == "model_accuracy_score"
        )

    def test_prometheus_strip_leading_trailing_underscores(self):
        """Leading/trailing underscores should be stripped."""
        assert (
            sanitize_metric_name("_model_accuracy_", "prometheus") == "model_accuracy"
        )

    def test_prometheus_numeric_prefix_gets_prefixed(self):
        """Names starting with a digit get 'metric_' prefix for Prometheus."""
        assert sanitize_metric_name("123counter", "prometheus") == "metric_123counter"

    def test_prometheus_already_valid(self):
        """Already valid Prometheus names pass through unchanged."""
        assert (
            sanitize_metric_name("model_accuracy_score", "prometheus")
            == "model_accuracy_score"
        )

    def test_prometheus_mixed_issues(self):
        """Names with dots, hyphens, and uppercase all get fixed."""
        assert (
            sanitize_metric_name("Model.Accuracy-Score", "prometheus")
            == "model_accuracy_score"
        )

    # --- InfluxDB target format ---

    def test_influxdb_dots_preserved(self):
        """Dots are valid in InfluxDB measurement names and should be preserved."""
        assert (
            sanitize_metric_name("model.accuracy.score", "influxdb")
            == "model.accuracy.score"
        )

    def test_influxdb_hyphens_to_underscores(self):
        """Hyphens become underscores for consistency in InfluxDB."""
        assert (
            sanitize_metric_name("model-accuracy-score", "influxdb")
            == "model_accuracy_score"
        )

    def test_influxdb_uppercase_to_lowercase(self):
        """InfluxDB names are lowercased for consistency."""
        assert (
            sanitize_metric_name("ModelAccuracyScore", "influxdb")
            == "modelaccuracyscore"
        )

    def test_influxdb_spaces_to_underscores(self):
        """Spaces should become underscores for InfluxDB."""
        assert (
            sanitize_metric_name("model accuracy score", "influxdb")
            == "model_accuracy_score"
        )

    def test_influxdb_already_valid(self):
        """Already valid InfluxDB names pass through unchanged."""
        assert (
            sanitize_metric_name("model_accuracy_score", "influxdb")
            == "model_accuracy_score"
        )

    # --- Error handling ---

    def test_invalid_format_raises(self):
        """Invalid target format raises ValueError."""
        with pytest.raises(ValueError, match="target_format must be"):
            sanitize_metric_name("metric_name", "statsd")

    def test_empty_string_prometheus(self):
        """Empty string returns empty string."""
        assert sanitize_metric_name("", "prometheus") == ""

    def test_empty_string_influxdb(self):
        """Empty string returns empty string."""
        assert sanitize_metric_name("", "influxdb") == ""


class TestMetricNameRoundTrip:
    """Verify that metric names survive round-trip through sanitizer."""

    ROUND_TRIP_NAMES = [
        "model_accuracy_score",
        "model_retrieval_latency_seconds",
        "registry_operations_total",
        "training_loss",
        "chiseai_model_registry_models_registered",
    ]

    @pytest.mark.parametrize("name", ROUND_TRIP_NAMES)
    def test_prometheus_round_trip(self, name: str):
        """Names that are already Prometheus-valid should round-trip cleanly."""
        sanitized = sanitize_metric_name(name, "prometheus")
        assert sanitized == name

    @pytest.mark.parametrize("name", ROUND_TRIP_NAMES)
    def test_influxdb_round_trip(self, name: str):
        """Names that are already valid should round-trip cleanly through InfluxDB."""
        sanitized = sanitize_metric_name(name, "influxdb")
        assert sanitized == name

    def test_dot_name_prometheus_influx_no_loss(self):
        """A name with dots: converting to Prometheus and back to InfluxDB
        should produce a valid (though dot-less) result without data loss."""
        original = "model.accuracy.score"
        prom = sanitize_metric_name(original, "prometheus")
        influx = sanitize_metric_name(prom, "influxdb")
        # Both should be the same underscore form
        assert prom == "model_accuracy_score"
        assert influx == "model_accuracy_score"

    def test_hyphen_name_dual_format(self):
        """Hyphenated names should convert consistently to both formats."""
        original = "model-accuracy-score"
        prom = sanitize_metric_name(original, "prometheus")
        influx = sanitize_metric_name(original, "influxdb")
        assert prom == "model_accuracy_score"
        assert influx == "model_accuracy_score"


class TestAlertFormatCompatibility:
    """Test alert format conversion for both Prometheus and InfluxDB."""

    @pytest.fixture
    def sample_alert(self) -> Alert:
        """Create a sample alert for testing."""
        return Alert(
            name="high_latency",
            severity=AlertSeverity.WARNING,
            message="Model retrieval latency exceeds 1 second",
            timestamp=datetime(2026, 1, 15, 12, 30, 0, tzinfo=UTC),
            metadata={
                "labels": {"environment": "production", "service": "registry"},
                "annotations": {"runbook": "https://docs/runbook/high-latency"},
            },
        )

    def test_alertmanager_format_structure(self, sample_alert: Alert):
        """Verify Prometheus Alertmanager format has correct structure."""
        result = sample_alert.to_alertmanager_format()

        assert "labels" in result
        assert "annotations" in result
        assert "startsAt" in result
        assert "endsAt" in result

        # Labels
        assert result["labels"]["alertname"] == "high_latency"
        assert result["labels"]["severity"] == "warning"
        assert result["labels"]["environment"] == "production"
        assert result["labels"]["service"] == "registry"

        # Annotations
        assert "message" in result["annotations"]
        assert "timestamp" in result["annotations"]
        assert result["annotations"]["runbook"] == "https://docs/runbook/high-latency"

    def test_alertmanager_format_timestamps(self, sample_alert: Alert):
        """Verify Alertmanager format has valid ISO timestamps."""
        result = sample_alert.to_alertmanager_format()

        # Should be parseable ISO format
        starts = datetime.fromisoformat(result["startsAt"])
        ends = datetime.fromisoformat(result["endsAt"])
        assert ends > starts

    def test_influxdb_format_structure(self, sample_alert: Alert):
        """Verify InfluxDB alert format has correct structure."""
        result = sample_alert.to_influxdb_format()

        assert "measurement" in result
        assert "tags" in result
        assert "fields" in result
        assert "timestamp" in result

        assert result["measurement"] == "alerts"
        assert result["tags"]["alertname"] == "high_latency"
        assert result["tags"]["severity"] == "warning"
        assert result["tags"]["environment"] == "production"
        assert result["fields"]["message"] == "Model retrieval latency exceeds 1 second"

    def test_influxdb_format_nanosecond_timestamp(self, sample_alert: Alert):
        """Verify InfluxDB format uses nanosecond Unix timestamp."""
        result = sample_alert.to_influxdb_format()

        ts = result["timestamp"]
        assert isinstance(ts, int)
        # Should be in nanosecond range (year 2026 in ns ≈ 1.77e18)
        assert ts > 1_000_000_000_000_000_000  # > ~2001 in ns

    def test_influxdb_format_tag_names_sanitized(self):
        """InfluxDB tag names should be sanitized."""
        alert = Alert(
            name="alert-with-hyphens",
            severity=AlertSeverity.CRITICAL,
            message="test",
            metadata={"labels": {"my-tag": "value"}},
        )
        result = alert.to_influxdb_format()
        assert "my-tag" not in result["tags"]
        assert "my_tag" in result["tags"]

    def test_alert_minimal(self):
        """Alert with no metadata should still produce valid formats."""
        alert = Alert(name="simple_alert", severity=AlertSeverity.INFO, message="test")
        am = alert.to_alertmanager_format()
        idb = alert.to_influxdb_format()

        assert am["labels"]["alertname"] == "simple_alert"
        assert idb["tags"]["alertname"] == "simple_alert"
        assert idb["measurement"] == "alerts"
