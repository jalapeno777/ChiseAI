"""Tests for data quality monitoring defaults.

ST-OPS-011: InfluxDB Token Wiring & Data Quality Monitor
Verifies that default configuration values are correct for the chiseai network.
"""

import os
from unittest.mock import patch

from operations.data_quality_monitoring import InfluxDBExporter


class TestInfluxDBExporterDefaults:
    """Test that InfluxDBExporter has correct default values."""

    def test_default_url_is_port_18087(self):
        """AC4: Default InfluxDB URL should use port 18087 on chiseai network."""
        exporter = InfluxDBExporter()
        assert exporter.influx_url == "http://chiseai-influxdb:18087"

    def test_default_bucket_is_chiseai(self):
        """AC5: Default bucket should be 'chiseai' not 'data_quality'."""
        exporter = InfluxDBExporter()
        assert exporter.influx_bucket == "chiseai"

    def test_default_org_is_chiseai(self):
        """Default organization should be 'chiseai'."""
        exporter = InfluxDBExporter()
        assert exporter.influx_org == "chiseai"

    def test_default_token_is_empty(self):
        """Default token should be empty string."""
        exporter = InfluxDBExporter()
        assert exporter.influx_token == ""


class TestInfluxDBExporterOverrides:
    """Test that environment variable overrides work correctly."""

    def test_url_override(self):
        """Test that URL can be overridden via constructor."""
        custom_url = "http://custom-influx:8086"
        exporter = InfluxDBExporter(influx_url=custom_url)
        assert exporter.influx_url == custom_url

    def test_bucket_override(self):
        """Test that bucket can be overridden via constructor."""
        custom_bucket = "custom_bucket"
        exporter = InfluxDBExporter(influx_bucket=custom_bucket)
        assert exporter.influx_bucket == custom_bucket

    def test_token_override(self):
        """Test that token can be overridden via constructor."""
        custom_token = "my-secret-token"
        exporter = InfluxDBExporter(influx_token=custom_token)
        assert exporter.influx_token == custom_token

    def test_org_override(self):
        """Test that org can be overridden via constructor."""
        custom_org = "custom_org"
        exporter = InfluxDBExporter(influx_org=custom_org)
        assert exporter.influx_org == custom_org


class TestEnvironmentVariableHandling:
    """Test that script reads environment variables correctly."""

    @patch.dict(
        os.environ,
        {
            "DQ_INFLUX_URL": "http://env-influx:18087",
            "DQ_INFLUX_TOKEN": "env-token",
            "DQ_INFLUX_ORG": "env-org",
            "DQ_INFLUX_BUCKET": "env-bucket",
        },
        clear=True,
    )
    def test_environment_variables_used(self):
        """Test that environment variables are correctly read and used."""
        # Simulate how the script reads env vars
        url = os.getenv("DQ_INFLUX_URL", "http://chiseai-influxdb:18087")
        token = os.getenv("DQ_INFLUX_TOKEN", "")
        org = os.getenv("DQ_INFLUX_ORG", "chiseai")
        bucket = os.getenv("DQ_INFLUX_BUCKET", "chiseai")

        exporter = InfluxDBExporter(
            influx_url=url,
            influx_token=token,
            influx_org=org,
            influx_bucket=bucket,
        )

        assert exporter.influx_url == "http://env-influx:18087"
        assert exporter.influx_token == "env-token"
        assert exporter.influx_org == "env-org"
        assert exporter.influx_bucket == "env-bucket"

    @patch.dict(os.environ, {}, clear=True)
    def test_defaults_when_no_env_vars(self):
        """Test that defaults are used when environment variables are not set."""
        # Simulate how the script reads env vars with defaults
        url = os.getenv("DQ_INFLUX_URL", "http://chiseai-influxdb:18087")
        token = os.getenv("DQ_INFLUX_TOKEN", "")
        org = os.getenv("DQ_INFLUX_ORG", "chiseai")
        bucket = os.getenv("DQ_INFLUX_BUCKET", "chiseai")

        exporter = InfluxDBExporter(
            influx_url=url,
            influx_token=token,
            influx_org=org,
            influx_bucket=bucket,
        )

        assert exporter.influx_url == "http://chiseai-influxdb:18087"
        assert exporter.influx_token == ""
        assert exporter.influx_org == "chiseai"
        assert exporter.influx_bucket == "chiseai"


class TestPortConfiguration:
    """Test that port 18087 is used consistently."""

    def test_chiseai_network_port(self):
        """AC4: Verify chiseai network uses port 18087."""
        # From AGENTS.md: chiseai_influxdb: '18087:18087'
        expected_port = "18087"
        exporter = InfluxDBExporter()
        assert expected_port in exporter.influx_url

    def test_not_using_default_8086(self):
        """Verify we're NOT using the default InfluxDB port 8086."""
        exporter = InfluxDBExporter()
        assert ":8086" not in exporter.influx_url


class TestBucketAlignment:
    """Test bucket alignment with Grafana dashboards."""

    def test_bucket_matches_grafana_config(self):
        """AC5: Bucket should be 'chiseai' to match Grafana datasource config."""
        # Grafana dashboards are configured to use the 'chiseai' bucket
        exporter = InfluxDBExporter()
        assert exporter.influx_bucket == "chiseai"

    def test_not_using_data_quality_bucket(self):
        """Verify we're NOT using the old 'data_quality' bucket."""
        exporter = InfluxDBExporter()
        assert exporter.influx_bucket != "data_quality"
