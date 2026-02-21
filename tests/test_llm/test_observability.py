"""Tests for LLM provider observability module.

Tests the ProviderMetrics, ChainMetrics, and ProviderMetricsExporter classes
for burn-in monitoring and metrics collection.

For GATE-RECOVERY-003: Provider Observability Fix
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from llm.observability import (
    ChainMetrics,
    ProviderMetrics,
    ProviderMetricsExporter,
    aggregate_metrics,
    create_metrics_report,
)
from llm.provider_chain import ErrorCategory


class TestProviderMetrics:
    """Test suite for ProviderMetrics dataclass."""

    def test_initial_state(self):
        """Test initial state of ProviderMetrics."""
        metrics = ProviderMetrics(provider_name="kimi", provider_label="KIMI K2.5")

        assert metrics.provider_name == "kimi"
        assert metrics.provider_label == "KIMI K2.5"
        assert metrics.attempts == 0
        assert metrics.successes == 0
        assert metrics.failures == 0
        assert metrics.fallback_reasons == {}
        assert metrics.avg_latency_ms == 0.0

    def test_record_attempt(self):
        """Test recording attempts."""
        metrics = ProviderMetrics(provider_name="kimi")

        metrics.record_attempt(latency_ms=100.0)
        assert metrics.attempts == 1
        assert metrics.avg_latency_ms == 100.0
        assert metrics.last_attempt_at is not None

        metrics.record_attempt(latency_ms=200.0)
        assert metrics.attempts == 2
        assert metrics.avg_latency_ms == 150.0  # (100 + 200) / 2

    def test_record_success(self):
        """Test recording successes."""
        metrics = ProviderMetrics(provider_name="kimi")

        metrics.record_attempt(latency_ms=100.0)
        metrics.record_success(latency_ms=100.0)

        assert metrics.successes == 1
        assert metrics.last_success_at is not None

    def test_record_failure_with_enum(self):
        """Test recording failures with ErrorCategory enum."""
        metrics = ProviderMetrics(provider_name="kimi")

        metrics.record_failure(ErrorCategory.AUTH, "Invalid API key")

        assert metrics.failures == 1
        assert metrics.last_error_category == "AUTH"
        assert metrics.last_fallback_reason == "Invalid API key"
        assert metrics.fallback_reasons["AUTH"] == 1

    def test_record_failure_with_string(self):
        """Test recording failures with string category."""
        metrics = ProviderMetrics(provider_name="kimi")

        metrics.record_failure("NETWORK", "Connection timeout")

        assert metrics.failures == 1
        assert metrics.last_error_category == "NETWORK"
        assert metrics.fallback_reasons["NETWORK"] == 1

    def test_multiple_fallback_reasons(self):
        """Test tracking multiple fallback reasons."""
        metrics = ProviderMetrics(provider_name="kimi")

        metrics.record_failure(ErrorCategory.AUTH, "Invalid key")
        metrics.record_failure(ErrorCategory.RATE_LIMIT, "Too many requests")
        metrics.record_failure(ErrorCategory.AUTH, "Another auth error")

        assert metrics.fallback_reasons["AUTH"] == 2
        assert metrics.fallback_reasons["RATE_LIMIT"] == 1
        assert len(metrics.fallback_reasons) == 2

    def test_success_rate_calculation(self):
        """Test success rate calculation."""
        metrics = ProviderMetrics(provider_name="kimi")

        assert metrics.success_rate == 0.0

        metrics.attempts = 10
        metrics.successes = 7
        metrics.failures = 3

        assert metrics.success_rate == 70.0

    def test_failure_rate_calculation(self):
        """Test failure rate calculation."""
        metrics = ProviderMetrics(provider_name="kimi")

        assert metrics.failure_rate == 0.0

        metrics.attempts = 10
        metrics.successes = 7
        metrics.failures = 3

        assert metrics.failure_rate == 30.0

    def test_to_dict(self):
        """Test conversion to dictionary."""
        metrics = ProviderMetrics(provider_name="kimi", provider_label="KIMI K2.5")
        metrics.record_attempt(latency_ms=100.0)
        metrics.record_success(latency_ms=100.0)

        data = metrics.to_dict()

        assert data["provider_name"] == "kimi"
        assert data["provider_label"] == "KIMI K2.5"
        assert data["attempts"] == 1
        assert data["successes"] == 1
        assert data["success_rate"] == 100.0
        assert "fallback_reasons" in data


class TestChainMetrics:
    """Test suite for ChainMetrics dataclass."""

    def test_initial_state(self):
        """Test initial state of ChainMetrics."""
        metrics = ChainMetrics()

        assert metrics.total_queries == 0
        assert metrics.successful_queries == 0
        assert metrics.failed_queries == 0
        assert metrics.fallback_count == 0
        assert metrics.providers_used == set()
        assert metrics.provider_metrics == {}

    def test_get_or_create_provider_metrics(self):
        """Test getting or creating provider metrics."""
        chain = ChainMetrics()

        metrics = chain.get_or_create_provider_metrics("kimi", "KIMI K2.5")

        assert "kimi" in chain.provider_metrics
        assert metrics.provider_name == "kimi"
        assert metrics.provider_label == "KIMI K2.5"

        # Get existing
        metrics2 = chain.get_or_create_provider_metrics("kimi", "Different Label")
        assert metrics2 is metrics
        assert metrics2.provider_label == "KIMI K2.5"  # Original label preserved

    def test_record_query_start(self):
        """Test recording query start."""
        chain = ChainMetrics()

        chain.record_query_start()
        assert chain.total_queries == 1

        chain.record_query_start()
        assert chain.total_queries == 2

    def test_record_query_success(self):
        """Test recording query success."""
        chain = ChainMetrics()

        chain.record_query_success("kimi")
        assert chain.successful_queries == 1
        assert "kimi" in chain.providers_used

    def test_record_query_failure(self):
        """Test recording query failure."""
        chain = ChainMetrics()

        chain.record_query_failure()
        assert chain.failed_queries == 1

    def test_record_fallback(self):
        """Test recording fallback."""
        chain = ChainMetrics()

        chain.record_fallback()
        assert chain.fallback_count == 1

        chain.record_fallback()
        assert chain.fallback_count == 2

    def test_overall_success_rate(self):
        """Test overall success rate calculation."""
        chain = ChainMetrics()

        assert chain.overall_success_rate == 0.0

        chain.total_queries = 10
        chain.successful_queries = 8
        chain.failed_queries = 2

        assert chain.overall_success_rate == 80.0

    def test_avg_fallbacks_per_query(self):
        """Test average fallbacks per query."""
        chain = ChainMetrics()

        assert chain.avg_fallbacks_per_query == 0.0

        chain.total_queries = 10
        chain.fallback_count = 15

        assert chain.avg_fallbacks_per_query == 1.5

    def test_to_dict(self):
        """Test conversion to dictionary."""
        chain = ChainMetrics()
        chain.record_query_start()
        chain.record_query_success("kimi")

        data = chain.to_dict()

        assert data["total_queries"] == 1
        assert data["successful_queries"] == 1
        assert data["overall_success_rate"] == 100.0
        assert "provider_metrics" in data


class TestProviderMetricsExporter:
    """Test suite for ProviderMetricsExporter."""

    def test_initialization_without_influxdb(self):
        """Test initialization without InfluxDB client."""
        exporter = ProviderMetricsExporter()

        assert exporter.influxdb_client is None
        assert exporter._write_api is None
        assert exporter.enable_logging is True

    def test_initialization_with_mock_influxdb(self):
        """Test initialization with mock InfluxDB client."""
        mock_client = MagicMock()
        mock_write_api = MagicMock()
        mock_client.write_api.return_value = mock_write_api

        exporter = ProviderMetricsExporter(influxdb_client=mock_client)

        assert exporter.influxdb_client is mock_client
        assert exporter._write_api is not None

    def test_export_provider_metrics_without_client(self):
        """Test export without InfluxDB client returns None."""
        exporter = ProviderMetricsExporter()
        metrics = ProviderMetrics(provider_name="kimi")

        result = exporter.export_provider_metrics(metrics)

        assert result is None

    @patch("llm.observability.logger")
    def test_log_burn_in_event(self, mock_logger):
        """Test logging burn-in events."""
        exporter = ProviderMetricsExporter(enable_logging=True)

        exporter.log_burn_in_event("attempt", "kimi", {"latency_ms": 100})

        mock_logger.debug.assert_called_once()

    @patch("llm.observability.logger")
    def test_log_burn_in_event_disabled(self, mock_logger):
        """Test that logging is skipped when disabled."""
        exporter = ProviderMetricsExporter(enable_logging=False)

        exporter.log_burn_in_event("attempt", "kimi")

        mock_logger.debug.assert_not_called()

    @patch("llm.observability.logger")
    def test_log_failure_event(self, mock_logger):
        """Test logging failure events at warning level."""
        exporter = ProviderMetricsExporter(enable_logging=True)

        exporter.log_burn_in_event("failure", "kimi", {"error_category": "AUTH"})

        mock_logger.warning.assert_called_once()

    @patch("llm.observability.logger")
    def test_log_fallback_event(self, mock_logger):
        """Test logging fallback events at info level."""
        exporter = ProviderMetricsExporter(enable_logging=True)

        exporter.log_burn_in_event("fallback", "kimi", {"to_provider": "zai"})

        mock_logger.info.assert_called_once()


class TestMetricsReport:
    """Test suite for metrics reporting functions."""

    def test_create_metrics_report(self):
        """Test creating human-readable metrics report."""
        chain = ChainMetrics()
        chain.record_query_start()
        chain.record_query_success("kimi")

        # Add provider metrics
        metrics = chain.get_or_create_provider_metrics("kimi", "KIMI K2.5")
        metrics.record_attempt(100.0)
        metrics.record_success(100.0)

        report = create_metrics_report(chain)

        assert "LLM Provider Chain Metrics Report" in report
        assert "Total Queries: 1" in report
        assert "KIMI K2.5" in report
        assert "Attempts: 1" in report

    def test_create_metrics_report_with_fallbacks(self):
        """Test report includes fallback information."""
        chain = ChainMetrics()
        chain.record_query_start()
        chain.record_fallback()
        chain.record_query_success("zai")

        metrics = chain.get_or_create_provider_metrics("kimi", "KIMI K2.5")
        metrics.record_failure(ErrorCategory.AUTH, "Invalid key")

        report = create_metrics_report(chain)

        assert "Total Fallbacks: 1" in report
        assert "Fallback Reasons" in report
        assert "AUTH: 1" in report


class TestAggregateMetrics:
    """Test suite for metrics aggregation."""

    def test_aggregate_empty_list(self):
        """Test aggregating empty list returns zeros."""
        result = aggregate_metrics([])

        assert result["total_queries"] == 0
        assert result["success_rate"] == 0.0

    def test_aggregate_single_metrics(self):
        """Test aggregating single metrics."""
        chain = ChainMetrics()
        chain.record_query_start()
        chain.record_query_success("kimi")

        result = aggregate_metrics([chain])

        assert result["total_queries"] == 1
        assert result["successful_queries"] == 1
        assert result["success_rate"] == 100.0

    def test_aggregate_multiple_metrics(self):
        """Test aggregating multiple metrics."""
        chain1 = ChainMetrics()
        chain1.record_query_start()
        chain1.record_query_success("kimi")
        chain1.record_fallback()

        chain2 = ChainMetrics()
        chain2.record_query_start()
        chain2.record_query_start()
        chain2.record_query_success("zai")
        chain2.record_query_failure()

        result = aggregate_metrics([chain1, chain2])

        assert result["total_queries"] == 3
        assert result["successful_queries"] == 2
        assert result["failed_queries"] == 1
        assert result["total_fallbacks"] == 1
        assert result["periods_count"] == 2


class TestIntegrationWithProviderChain:
    """Integration tests with LLMProviderChain."""

    @pytest.mark.asyncio
    async def test_metrics_collection_during_query(self):
        """Test that metrics are collected during provider chain queries."""
        from llm.provider_chain import LLMProviderChain, LLMResponse

        with patch.dict(os.environ, {"KIMI_API_KEY": "test-key"}, clear=True):
            chain = LLMProviderChain(enable_metrics=True)

            # Mock successful response (needs to be async)
            async def mock_query(*args, **kwargs):
                return LLMResponse(
                    success=True,
                    content="Test response",
                    confidence_score=75.0,
                    rationale="Test",
                    provider="KIMI K2.5",
                )

            chain._query_kimi = mock_query

            # Query should collect metrics
            result = await chain.query("Test prompt")

            assert result.success is True
            assert chain._chain_metrics is not None
            assert chain._chain_metrics.total_queries == 1
            assert chain._chain_metrics.successful_queries == 1

    def test_get_metrics_report(self):
        """Test getting metrics report from provider chain."""
        from llm.provider_chain import LLMProviderChain

        chain = LLMProviderChain(enable_metrics=True)

        report = chain.get_metrics_report()

        assert report["enabled"] is True
        assert "metrics" in report

    def test_metrics_disabled(self):
        """Test that metrics can be disabled."""
        from llm.provider_chain import LLMProviderChain

        chain = LLMProviderChain(enable_metrics=False)

        assert chain._chain_metrics is None
        report = chain.get_metrics_report()
        assert report["enabled"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
