"""Tests for OHLCV fetcher module."""

from datetime import UTC
from unittest.mock import AsyncMock, Mock

import pytest

from data_ingestion.ohlcv_fetcher import (
    CCXTAdapter,
    CircuitBreaker,
    CircuitBreakerOpen,
    ExchangeError,
    OHLCVData,
    OHLCVFetcher,
)
from data_ingestion.timeframe_config import Timeframe


class TestOHLCVData:
    """Test cases for OHLCVData dataclass."""

    def test_creation(self):
        """Test creating OHLCVData instance."""
        data = OHLCVData(
            timestamp=1609459200000,  # 2021-01-01 00:00:00 UTC
            open_price=100.0,
            high_price=110.0,
            low_price=95.0,
            close_price=105.0,
            volume=1000.0,
        )
        assert data.timestamp == 1609459200000
        assert data.open_price == 100.0
        assert data.high_price == 110.0
        assert data.low_price == 95.0
        assert data.close_price == 105.0
        assert data.volume == 1000.0

    def test_datetime_utc_property(self):
        """Test datetime_utc property conversion."""
        data = OHLCVData(
            timestamp=1609459200000,
            open_price=100.0,
            high_price=110.0,
            low_price=95.0,
            close_price=105.0,
            volume=1000.0,
        )
        dt = data.datetime_utc
        assert dt.year == 2021
        assert dt.month == 1
        assert dt.day == 1
        assert dt.tzinfo == UTC


class TestCircuitBreaker:
    """Test cases for CircuitBreaker class."""

    @pytest.mark.asyncio
    async def test_initial_state(self):
        """Test circuit breaker starts closed."""
        cb = CircuitBreaker()
        assert await cb.can_execute() is True
        assert cb._is_open is False

    @pytest.mark.asyncio
    async def test_records_success(self):
        """Test recording success resets failure count."""
        cb = CircuitBreaker(failure_threshold=3)
        await cb.record_failure()
        await cb.record_failure()
        assert cb._failure_count == 2

        await cb.record_success()
        assert cb._failure_count == 0
        assert cb._is_open is False

    @pytest.mark.asyncio
    async def test_opens_after_threshold(self):
        """Test circuit opens after threshold failures."""
        cb = CircuitBreaker(failure_threshold=3)
        await cb.record_failure()
        await cb.record_failure()
        await cb.record_failure()

        assert cb._is_open is True
        assert await cb.can_execute() is False

    @pytest.mark.asyncio
    async def test_resets_after_cooldown(self):
        """Test circuit resets after cooldown period."""
        cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=0.1)
        await cb.record_failure()
        assert cb._is_open is True

        # Wait for cooldown
        import time

        time.sleep(0.15)

        assert await cb.can_execute() is True
        assert cb._is_open is False


class TestCCXTAdapter:
    """Test cases for CCXTAdapter class."""

    @pytest.fixture
    def mock_exchange(self):
        """Create a mock CCXT exchange."""
        exchange = Mock()
        exchange.markets = {"BTC/USDT": {}}
        return exchange

    @pytest.mark.asyncio
    async def test_fetch_ohlcv_success(self, mock_exchange):
        """Test successful OHLCV fetch."""
        # Mock the fetch_ohlcv return value
        mock_candles = [
            [1609459200000, 100.0, 110.0, 95.0, 105.0, 1000.0],
            [1609459260000, 105.0, 115.0, 100.0, 110.0, 1500.0],
        ]
        mock_exchange.fetch_ohlcv = Mock(return_value=mock_candles)

        adapter = CCXTAdapter(exchange_id="binance")
        adapter.exchange = mock_exchange

        result = await adapter.fetch_ohlcv("BTC/USDT", Timeframe.MINUTE_1)

        assert len(result) == 2
        assert result[0].timestamp == 1609459200000
        assert result[0].open_price == 100.0
        assert result[0].high_price == 110.0
        assert result[0].low_price == 95.0
        assert result[0].close_price == 105.0
        assert result[0].volume == 1000.0

    @pytest.mark.asyncio
    async def test_fetch_ohlcv_circuit_breaker_open(self, mock_exchange):
        """Test fetch when circuit breaker is open."""
        adapter = CCXTAdapter(exchange_id="binance")
        adapter.exchange = mock_exchange
        await adapter.circuit_breaker.record_failure()
        await adapter.circuit_breaker.record_failure()
        await adapter.circuit_breaker.record_failure()
        await adapter.circuit_breaker.record_failure()
        await adapter.circuit_breaker.record_failure()

        with pytest.raises(CircuitBreakerOpen):
            await adapter.fetch_ohlcv("BTC/USDT", Timeframe.MINUTE_1)

    @pytest.mark.asyncio
    async def test_check_health_success(self, mock_exchange):
        """Test health check when exchange is healthy."""
        mock_exchange.fetch_time = Mock(return_value=1609459200000)

        adapter = CCXTAdapter(exchange_id="binance")
        adapter.exchange = mock_exchange

        result = await adapter.check_health()
        assert result is True

    @pytest.mark.asyncio
    async def test_check_health_failure(self, mock_exchange):
        """Test health check when exchange is unhealthy."""
        mock_exchange.fetch_time = Mock(side_effect=Exception("Connection error"))

        adapter = CCXTAdapter(exchange_id="binance")
        adapter.exchange = mock_exchange

        result = await adapter.check_health()
        assert result is False


class TestOHLCVFetcher:
    """Test cases for OHLCVFetcher class."""

    @pytest.fixture
    def mock_adapter(self):
        """Create a mock exchange adapter."""
        adapter = Mock()
        adapter.fetch_ohlcv = AsyncMock()
        return adapter

    @pytest.mark.asyncio
    async def test_fetch_success(self, mock_adapter):
        """Test successful fetch with retry."""
        mock_data = [
            OHLCVData(
                timestamp=1609459200000,
                open_price=100.0,
                high_price=110.0,
                low_price=95.0,
                close_price=105.0,
                volume=1000.0,
            )
        ]
        mock_adapter.fetch_ohlcv.return_value = mock_data

        fetcher = OHLCVFetcher(exchange_adapter=mock_adapter)
        result = await fetcher.fetch("BTC/USDT", Timeframe.MINUTE_1)

        assert len(result) == 1
        assert result[0].timestamp == 1609459200000

    @pytest.mark.asyncio
    async def test_fetch_with_retry(self, mock_adapter):
        """Test fetch retries on failure."""
        mock_adapter.fetch_ohlcv.side_effect = [
            ExchangeError("Network error"),
            ExchangeError("Network error"),
            [
                OHLCVData(
                    timestamp=1609459200000,
                    open_price=100.0,
                    high_price=110.0,
                    low_price=95.0,
                    close_price=105.0,
                    volume=1000.0,
                )
            ],
        ]

        fetcher = OHLCVFetcher(
            exchange_adapter=mock_adapter,
            max_retries=3,
            base_delay=0.01,  # Fast for testing
        )
        result = await fetcher.fetch("BTC/USDT", Timeframe.MINUTE_1)

        assert len(result) == 1
        assert mock_adapter.fetch_ohlcv.call_count == 3

    @pytest.mark.asyncio
    async def test_fetch_all_retries_exhausted(self, mock_adapter):
        """Test fetch fails after all retries exhausted."""
        mock_adapter.fetch_ohlcv.side_effect = ExchangeError("Network error")

        fetcher = OHLCVFetcher(
            exchange_adapter=mock_adapter,
            max_retries=2,
            base_delay=0.01,
        )

        with pytest.raises(ExchangeError):
            await fetcher.fetch("BTC/USDT", Timeframe.MINUTE_1)

        assert mock_adapter.fetch_ohlcv.call_count == 2

    @pytest.mark.asyncio
    async def test_fetch_zero_volume_warning(self, mock_adapter, caplog):
        """Test warning logged for zero volume data."""
        mock_data = [
            OHLCVData(
                timestamp=1609459200000,
                open_price=100.0,
                high_price=110.0,
                low_price=95.0,
                close_price=105.0,
                volume=0.0,
            ),
            OHLCVData(
                timestamp=1609459260000,
                open_price=105.0,
                high_price=115.0,
                low_price=100.0,
                close_price=110.0,
                volume=0.0,
            ),
        ]
        mock_adapter.fetch_ohlcv.return_value = mock_data

        fetcher = OHLCVFetcher(exchange_adapter=mock_adapter)

        import logging

        with caplog.at_level(logging.WARNING):
            await fetcher.fetch("BTC/USDT", Timeframe.MINUTE_1)

        assert "Zero volume detected" in caplog.text

    @pytest.mark.asyncio
    async def test_fetch_multiple_timeframes(self, mock_adapter):
        """Test fetching multiple timeframes concurrently."""
        mock_data_1m = [
            OHLCVData(
                timestamp=1609459200000,
                open_price=100.0,
                high_price=110.0,
                low_price=95.0,
                close_price=105.0,
                volume=1000.0,
            )
        ]
        mock_data_5m = [
            OHLCVData(
                timestamp=1609459200000,
                open_price=100.0,
                high_price=115.0,
                low_price=95.0,
                close_price=110.0,
                volume=5000.0,
            )
        ]

        mock_adapter.fetch_ohlcv.side_effect = [mock_data_1m, mock_data_5m]

        fetcher = OHLCVFetcher(exchange_adapter=mock_adapter)
        result = await fetcher.fetch_multiple_timeframes(
            "BTC/USDT", [Timeframe.MINUTE_1, Timeframe.MINUTE_5]
        )

        assert len(result) == 2
        assert Timeframe.MINUTE_1 in result
        assert Timeframe.MINUTE_5 in result
        assert len(result[Timeframe.MINUTE_1]) == 1
        assert len(result[Timeframe.MINUTE_5]) == 1

    @pytest.mark.asyncio
    async def test_fetch_multiple_timeframes_partial_failure(self, mock_adapter):
        """Test fetching multiple timeframes with one failure."""
        mock_data = [
            OHLCVData(
                timestamp=1609459200000,
                open_price=100.0,
                high_price=110.0,
                low_price=95.0,
                close_price=105.0,
                volume=1000.0,
            )
        ]

        mock_adapter.fetch_ohlcv.side_effect = [mock_data, ExchangeError("Failed")]

        fetcher = OHLCVFetcher(exchange_adapter=mock_adapter)
        result = await fetcher.fetch_multiple_timeframes(
            "BTC/USDT", [Timeframe.MINUTE_1, Timeframe.MINUTE_5]
        )

        assert len(result) == 2
        assert len(result[Timeframe.MINUTE_1]) == 1
        assert len(result[Timeframe.MINUTE_5]) == 0  # Failed fetch returns empty
