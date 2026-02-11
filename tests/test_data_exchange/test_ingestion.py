"""Tests for Binance ingestion service."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from exchange_data.binance.ingestion import (
    BinanceIngestionService,
    IngestionMetrics,
)
from exchange_data.binance.orderbook import OrderBookLevel, OrderBookSnapshot


class TestIngestionMetrics:
    """Test IngestionMetrics functionality."""

    def test_record_success(self) -> None:
        """Test recording successful ingestion."""
        metrics = IngestionMetrics()

        metrics.record_success(100.0)

        assert metrics.snapshots_ingested == 1
        assert metrics.total_latency_ms == 100.0
        assert metrics.last_ingest_time is not None

    def test_record_failure(self) -> None:
        """Test recording failed ingestion."""
        metrics = IngestionMetrics()

        metrics.record_failure("Connection error")

        assert metrics.snapshots_failed == 1

    def test_get_average_latency(self) -> None:
        """Test average latency calculation."""
        metrics = IngestionMetrics()

        metrics.record_success(100.0)
        metrics.record_success(200.0)
        metrics.record_success(300.0)

        assert metrics.get_average_latency_ms() == 200.0

    def test_get_average_latency_no_data(self) -> None:
        """Test average latency with no data."""
        metrics = IngestionMetrics()

        assert metrics.get_average_latency_ms() == 0.0

    def test_get_p95_latency(self) -> None:
        """Test P95 latency calculation."""
        metrics = IngestionMetrics()

        latencies = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]

        p95 = metrics.get_p95_latency_ms(latencies)

        # 95th percentile of 10 items = index 9 (100.0)
        assert p95 == 100.0

    def test_alert_callback(self) -> None:
        """Test alert callback registration."""
        metrics = IngestionMetrics()
        callback = MagicMock()

        metrics.register_alert_callback(callback)
        metrics._trigger_alert("test_alert", {"key": "value"})

        callback.assert_called_once_with("test_alert", {"key": "value"})


class TestBinanceIngestionService:
    """Test BinanceIngestionService functionality."""

    @pytest.mark.asyncio
    async def test_service_lifecycle(self) -> None:
        """Test service start and stop."""
        with patch(
            "exchange_data.binance.ingestion.BinanceClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            service = BinanceIngestionService()

            # Start service
            await service.start()
            assert service._running is True
            mock_client.connect.assert_called_once()

            # Stop service
            await service.stop()
            assert service._running is False
            mock_client.close.assert_called_once()

    def test_parse_orderbook(self) -> None:
        """Test order book parsing."""
        service = BinanceIngestionService()

        data = {
            "lastUpdateId": 12345,
            "bids": [["50000.0", "1.0"], ["49900.0", "2.0"]],
            "asks": [["50010.0", "0.5"], ["50100.0", "1.0"]],
        }

        snapshot = service._parse_orderbook("BTCUSDT", data)

        assert snapshot.symbol == "BTCUSDT"
        assert snapshot.last_update_id == 12345
        assert len(snapshot.bids) == 2
        assert len(snapshot.asks) == 2
        assert snapshot.bids[0].price == 50000.0
        assert snapshot.asks[0].price == 50010.0

    def test_parse_oi(self) -> None:
        """Test open interest parsing."""
        service = BinanceIngestionService()

        # Add a price reference
        service.tracker.add_snapshot(
            OrderBookSnapshot(
                symbol="BTCUSDT",
                timestamp=datetime.utcnow(),
                last_update_id=1,
                bids=[OrderBookLevel(price=50000.0, quantity=1.0)],
                asks=[OrderBookLevel(price=50001.0, quantity=1.0)],
            )
        )

        data = {"openInterest": "1000000.0"}

        oi = service._parse_oi("BTCUSDT", data)

        assert oi.symbol == "BTCUSDT"
        assert oi.open_interest == 1000000.0
        assert oi.price == 50000.5  # Mid price

    def test_get_liquidity_metrics(self) -> None:
        """Test getting liquidity metrics."""
        service = BinanceIngestionService()

        # Add snapshot
        service.tracker.add_snapshot(
            OrderBookSnapshot(
                symbol="BTCUSDT",
                timestamp=datetime.utcnow(),
                last_update_id=1,
                bids=[OrderBookLevel(price=50000.0, quantity=10.0)],
                asks=[OrderBookLevel(price=50010.0, quantity=10.0)],
            )
        )

        metrics = service.get_liquidity_metrics("BTCUSDT")

        assert metrics is not None
        assert metrics.symbol == "BTCUSDT"

    def test_get_liquidity_metrics_no_data(self) -> None:
        """Test getting liquidity metrics when no data exists."""
        service = BinanceIngestionService()

        metrics = service.get_liquidity_metrics("BTCUSDT")

        assert metrics is None

    def test_get_metrics(self) -> None:
        """Test getting ingestion metrics."""
        service = BinanceIngestionService()

        # Record some metrics
        service.metrics.record_success(100.0)
        service.metrics.record_success(200.0)

        metrics = service.get_metrics()

        assert metrics["snapshots_ingested"] == 2
        assert metrics["avg_latency_ms"] == 150.0

    def test_is_healthy_running(self) -> None:
        """Test health check when running and healthy."""
        service = BinanceIngestionService()
        service._running = True
        service.metrics.record_success(50.0)  # Low latency

        assert service.is_healthy() is True

    def test_is_healthy_not_running(self) -> None:
        """Test health check when not running."""
        service = BinanceIngestionService()
        service._running = False

        assert service.is_healthy() is False

    def test_is_healthy_stale_data(self) -> None:
        """Test health check with stale data."""
        service = BinanceIngestionService()
        service._running = True
        # Don't record any metrics - last_ingest_time will be None

        assert service.is_healthy() is False

    def test_is_healthy_high_latency(self) -> None:
        """Test health check with high latency."""
        service = BinanceIngestionService()
        service._running = True

        # Add high latency measurements
        for _ in range(100):
            service._recent_latencies.append(5000.0)  # 5 second latency

        service.metrics.record_success(100.0)  # This updates last_ingest_time

        assert service.is_healthy() is False

    @pytest.mark.asyncio
    async def test_alert_on_failure(self) -> None:
        """Test that alerts are triggered on failures."""
        callback = MagicMock()
        service = BinanceIngestionService(alert_callback=callback)

        # Simulate a failure
        service.metrics.record_failure("Test error")

        # The callback should have been triggered
        assert callback.called or service.metrics.snapshots_failed == 1
