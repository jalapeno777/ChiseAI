"""Tests for Binance configuration."""

import pytest

from exchange_data.binance.config import BinanceConfig


class TestBinanceConfig:
    """Test Binance configuration."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = BinanceConfig()

        assert config.base_url == "https://fapi.binance.com"
        assert config.ws_url == "wss://fstream.binance.com/ws"
        assert config.orderbook_depth == 100
        assert config.snapshot_interval_ms == 100
        assert config.max_latency_ms == 2000
        assert config.freshness_threshold_sec == 5
        assert config.price_accuracy_pct == 0.01

    def test_default_tokens(self) -> None:
        """Test default token list."""
        config = BinanceConfig()

        assert len(config.tokens) == 10
        assert "BTCUSDT" in config.tokens
        assert "ETHUSDT" in config.tokens
        assert "SOLUSDT" in config.tokens

    def test_custom_tokens(self) -> None:
        """Test custom token list."""
        config = BinanceConfig(tokens=["BTCUSDT", "ETHUSDT"])

        assert config.tokens == ["BTCUSDT", "ETHUSDT"]

    def test_orderbook_url(self) -> None:
        """Test order book URL generation."""
        config = BinanceConfig()

        assert config.orderbook_url == "https://fapi.binance.com/fapi/v1/depth"

    def test_open_interest_url(self) -> None:
        """Test open interest URL generation."""
        config = BinanceConfig()

        assert (
            config.open_interest_url == "https://fapi.binance.com/fapi/v1/openInterest"
        )

    def test_ticker_url(self) -> None:
        """Test ticker URL generation."""
        config = BinanceConfig()

        assert config.ticker_url == "https://fapi.binance.com/fapi/v1/ticker/bookTicker"

    def test_custom_api_credentials(self) -> None:
        """Test custom API credentials."""
        config = BinanceConfig(api_key="test_key", api_secret="test_secret")

        assert config.api_key == "test_key"
        assert config.api_secret == "test_secret"
