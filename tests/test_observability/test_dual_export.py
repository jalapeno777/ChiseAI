"""Tests for dual-format metric export (Prometheus + InfluxDB).

ST-MVP-008: Verify DualFormatExporter produces valid output for both
Prometheus text exposition format and InfluxDB line protocol.
"""

import pytest

from observability.exporters import DualFormatExporter, ExportFormat


class TestExportFormat:
    """Test ExportFormat enum values."""

    def test_format_values(self):
        assert ExportFormat.PROMETHEUS.value == "prometheus"
        assert ExportFormat.INFLUXDB.value == "influxdb"
        assert ExportFormat.BOTH.value == "both"


class TestDualFormatExporterInit:
    """Test DualFormatExporter initialization."""

    def test_default_format(self):
        exporter = DualFormatExporter()
        assert exporter.export_format == ExportFormat.BOTH
        assert exporter.namespace == "chiseai"

    def test_custom_format(self):
        exporter = DualFormatExporter(export_format=ExportFormat.PROMETHEUS)
        assert exporter.export_format == ExportFormat.PROMETHEUS

    def test_custom_namespace(self):
        exporter = DualFormatExporter(namespace="custom")
        assert exporter.namespace == "custom"


class TestPrometheusTextFormat:
    """Test Prometheus text exposition format output."""

    @pytest.fixture
    def exporter(self) -> DualFormatExporter:
        return DualFormatExporter(export_format=ExportFormat.PROMETHEUS)

    def test_simple_gauge(self, exporter: DualFormatExporter):
        metrics = {
            "model_accuracy": {
                "value": 0.95,
                "type": "gauge",
                "help": "Model accuracy score",
            }
        }
        result = exporter._to_prometheus_text(metrics)

        assert "# HELP chiseai_model_accuracy Model accuracy score" in result
        assert "# TYPE chiseai_model_accuracy gauge" in result
        assert "chiseai_model_accuracy 0.95" in result

    def test_counter_with_labels(self, exporter: DualFormatExporter):
        metrics = {
            "requests_total": {
                "value": 42,
                "type": "counter",
                "labels": {"method": "GET", "status": "200"},
                "help": "Total requests",
            }
        }
        result = exporter._to_prometheus_text(metrics)

        assert "# TYPE chiseai_requests_total counter" in result
        assert 'method="GET"' in result
        assert 'status="200"' in result
        assert "42" in result

    def test_metric_name_sanitization(self, exporter: DualFormatExporter):
        """Metric names with dots should be sanitized for Prometheus."""
        metrics = {
            "model.accuracy.score": {
                "value": 0.88,
                "type": "gauge",
                "help": "Accuracy",
            }
        }
        result = exporter._to_prometheus_text(metrics)

        assert "chiseai_model_accuracy_score" in result
        # Dots should NOT appear in the metric name
        assert "chiseai_model.accuracy.score" not in result

    def test_label_name_sanitization(self, exporter: DualFormatExporter):
        """Label names with dots should also be sanitized."""
        metrics = {
            "test_metric": {
                "value": 1,
                "type": "gauge",
                "labels": {"model.version": "v1"},
                "help": "Test",
            }
        }
        result = exporter._to_prometheus_text(metrics)
        assert 'model_version="v1"' in result

    def test_empty_metrics(self, exporter: DualFormatExporter):
        result = exporter._to_prometheus_text({})
        assert result == ""

    def test_no_labels(self, exporter: DualFormatExporter):
        """Metrics without labels should not have empty braces."""
        metrics = {"uptime": {"value": 100, "type": "gauge", "help": "Uptime"}}
        result = exporter._to_prometheus_text(metrics)
        assert "chiseai_uptime 100" in result
        assert "{}" not in result


class TestInfluxDBLineProtocol:
    """Test InfluxDB line protocol format output."""

    @pytest.fixture
    def exporter(self) -> DualFormatExporter:
        return DualFormatExporter(export_format=ExportFormat.INFLUXDB)

    def test_simple_metric(self, exporter: DualFormatExporter):
        metrics = {
            "model_accuracy": {
                "value": 0.95,
            }
        }
        result = exporter._to_influxdb_line_protocol(metrics)

        assert "chiseai_model_accuracy" in result
        assert "value=0.95" in result

    def test_integer_value(self, exporter: DualFormatExporter):
        """Integer values should get 'i' suffix in InfluxDB."""
        metrics = {"request_count": {"value": 42}}
        result = exporter._to_influxdb_line_protocol(metrics)

        assert "value=42i" in result

    def test_float_value(self, exporter: DualFormatExporter):
        """Float values should NOT get 'i' suffix in InfluxDB."""
        metrics = {"latency": {"value": 1.5}}
        result = exporter._to_influxdb_line_protocol(metrics)

        assert "value=1.5" in result
        assert "value=1.5i" not in result

    def test_tags(self, exporter: DualFormatExporter):
        metrics = {
            "requests": {
                "value": 100,
                "tags": {"method": "GET", "status": "200"},
            }
        }
        result = exporter._to_influxdb_line_protocol(metrics)

        # Tags should be comma-separated after measurement
        assert "chiseai_requests," in result
        assert "method=GET" in result
        assert "status=200" in result

    def test_extra_fields(self, exporter: DualFormatExporter):
        metrics = {
            "latency": {
                "value": 1.5,
                "fields": {"min": 0.1, "max": 3.2},
            }
        }
        result = exporter._to_influxdb_line_protocol(metrics)

        assert "value=1.5" in result
        assert "min=0.1" in result
        assert "max=3.2" in result

    def test_timestamp(self, exporter: DualFormatExporter):
        metrics = {"test": {"value": 1}}
        ts = 1705312200000000000  # 2024-01-15 in nanoseconds
        result = exporter._to_influxdb_line_protocol(metrics, timestamp_ns=ts)

        assert str(ts) in result

    def test_metric_with_timestamp_in_data(self, exporter: DualFormatExporter):
        """Metrics can carry their own timestamp."""
        ts = 1705312200000000000
        metrics = {"test": {"value": 1, "timestamp": ts}}
        result = exporter._to_influxdb_line_protocol(metrics)

        assert str(ts) in result

    def test_dot_names_preserved(self, exporter: DualFormatExporter):
        """Dots in metric names should be preserved for InfluxDB."""
        metrics = {"model.accuracy.score": {"value": 0.88}}
        result = exporter._to_influxdb_line_protocol(metrics)

        assert "chiseai_model.accuracy.score" in result

    def test_empty_metrics(self, exporter: DualFormatExporter):
        result = exporter._to_influxdb_line_protocol({})
        assert result == ""

    def test_escape_special_characters(self):
        exporter = DualFormatExporter()
        assert exporter._escape_influx_value("hello world") == r"hello\ world"
        assert exporter._escape_influx_value("a,b=c") == r"a\,b\=c"


class TestDualFormatExport:
    """Test the combined export_metrics method."""

    @pytest.fixture
    def sample_metrics(self) -> dict:
        return {
            "model_accuracy": {
                "value": 0.95,
                "type": "gauge",
                "help": "Model accuracy",
                "tags": {"model": "v1"},
                "labels": {"model": "v1"},
            }
        }

    def test_both_formats(self, sample_metrics: dict):
        exporter = DualFormatExporter(export_format=ExportFormat.BOTH)
        prom, influx = exporter.export_metrics(sample_metrics)

        assert "chiseai_model_accuracy" in prom
        assert "# TYPE" in prom
        assert "chiseai_model_accuracy" in influx
        assert "value=0.95" in influx

    def test_prometheus_only(self, sample_metrics: dict):
        exporter = DualFormatExporter(export_format=ExportFormat.PROMETHEUS)
        prom, influx = exporter.export_metrics(sample_metrics)

        assert "chiseai_model_accuracy" in prom
        assert influx == ""

    def test_influxdb_only(self, sample_metrics: dict):
        exporter = DualFormatExporter(export_format=ExportFormat.INFLUXDB)
        prom, influx = exporter.export_metrics(sample_metrics)

        assert prom == ""
        assert "chiseai_model_accuracy" in influx

    def test_both_with_timestamp(self, sample_metrics: dict):
        ts = 1705312200000000000
        exporter = DualFormatExporter(export_format=ExportFormat.BOTH)
        prom, influx = exporter.export_metrics(sample_metrics, timestamp_ns=ts)

        # Prometheus format doesn't use nanosecond timestamp in this implementation
        assert prom != ""
        assert str(ts) in influx

    def test_empty_metrics_both(self):
        exporter = DualFormatExporter(export_format=ExportFormat.BOTH)
        prom, influx = exporter.export_metrics({})
        assert prom == ""
        assert influx == ""


class TestDualFormatExporterIntegration:
    """Integration test: full flow from metric data to both formats."""

    def test_multiple_metrics(self):
        exporter = DualFormatExporter(export_format=ExportFormat.BOTH)
        metrics = {
            "model_accuracy.score": {
                "value": 0.92,
                "type": "gauge",
                "help": "Model accuracy",
                "tags": {"version": "2.0"},
                "labels": {"version": "2.0"},
            },
            "requests_total": {
                "value": 1500,
                "type": "counter",
                "help": "Total requests",
                "tags": {"endpoint": "/predict"},
                "labels": {"endpoint": "/predict"},
            },
            "latency_seconds": {
                "value": 0.045,
                "type": "gauge",
                "help": "Request latency",
            },
        }

        prom, influx = exporter.export_metrics(metrics)

        # Prometheus checks
        assert "chiseai_model_accuracy_score" in prom
        assert 'version="2.0"' in prom
        assert "0.92" in prom
        assert "chiseai_requests_total" in prom
        assert "1500" in prom
        assert "chiseai_latency_seconds 0.045" in prom
        # Dots in name should be replaced
        assert "chiseai_model.accuracy.score" not in prom

        # InfluxDB checks
        # "model_accuracy.score" has underscore between model/accuracy, dot between accuracy/score
        assert "chiseai_model_accuracy.score" in influx
        assert "value=0.92" in influx
        assert "value=1500i" in influx
        assert "value=0.045" in influx
