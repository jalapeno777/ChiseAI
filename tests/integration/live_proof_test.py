"""Integration tests for Bybit endpoint validation.

Tests connectivity, authentication, and market data fetching
for both testnet and live Bybit API endpoints.

For PAPER-LIVE-001: Endpoint Validation & Live Data Harness

Usage:
    pytest tests/integration/live_proof_test.py -v

Environment Variables:
    BYBIT_API_KEY: Bybit API key for authenticated tests
    BYBIT_API_SECRET: Bybit API secret for authenticated tests
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from pathlib import Path

import aiohttp
import pytest
import yaml

# Load configuration
CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "bybit_endpoints.yaml"


def load_config():
    """Load endpoint configuration."""
    try:
        with open(CONFIG_PATH, "r") as f:
            data = yaml.safe_load(f)
            return data.get("bybit", {})
    except FileNotFoundError:
        pytest.skip(f"Config file not found: {CONFIG_PATH}")


@pytest.fixture(scope="module")
def config():
    """Provide endpoint configuration."""
    return load_config()


@pytest.fixture(scope="module")
def api_credentials():
    """Provide API credentials if available."""
    return {
        "key": os.getenv("BYBIT_API_KEY", ""),
        "secret": os.getenv("BYBIT_API_SECRET", ""),
    }


@pytest.fixture(scope="module")
def recv_window(config):
    """Provide receive window from config."""
    return config.get("settings", {}).get("recv_window_ms", 5000)


def generate_signature(
    timestamp: str, api_key: str, api_secret: str, recv_window: int, payload: str = ""
) -> str:
    """Generate HMAC signature for authenticated requests."""
    param_str = timestamp + api_key + str(recv_window) + payload
    return hmac.new(api_secret.encode(), param_str.encode(), hashlib.sha256).hexdigest()


class TestBybitConnectivity:
    """Test basic connectivity to Bybit endpoints."""

    @pytest.mark.asyncio
    async def test_testnet_connectivity(self, config):
        """Test connectivity to Bybit testnet."""
        endpoints = config.get("endpoints", {})
        testnet = endpoints.get("testnet", {})
        base_url = testnet.get("rest_base_url", "https://api-testnet.bybit.com")

        url = f"{base_url}/v5/market/time"

        async with aiohttp.ClientSession() as session:
            start_time = time.time()
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                latency_ms = (time.time() - start_time) * 1000
                data = await resp.json()

                assert resp.status == 200, f"HTTP {resp.status}: {data.get('retMsg')}"
                assert data.get("retCode") == 0, f"API error: {data.get('retMsg')}"
                assert "result" in data
                assert "timeSecond" in data["result"]

                print(f"\nTestnet connectivity: {latency_ms:.2f}ms")

    @pytest.mark.asyncio
    async def test_live_connectivity(self, config):
        """Test connectivity to Bybit live."""
        endpoints = config.get("endpoints", {})
        live = endpoints.get("live", {})
        base_url = live.get("rest_base_url", "https://api.bybit.com")

        url = f"{base_url}/v5/market/time"

        async with aiohttp.ClientSession() as session:
            start_time = time.time()
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                latency_ms = (time.time() - start_time) * 1000
                data = await resp.json()

                assert resp.status == 200, f"HTTP {resp.status}: {data.get('retMsg')}"
                assert data.get("retCode") == 0, f"API error: {data.get('retMsg')}"

                print(f"\nLive connectivity: {latency_ms:.2f}ms")


class TestBybitAuthentication:
    """Test authenticated endpoints."""

    @pytest.mark.asyncio
    async def test_testnet_authentication(self, config, api_credentials, recv_window):
        """Test authenticated access to testnet."""
        if not api_credentials["key"] or not api_credentials["secret"]:
            pytest.skip("No API credentials provided")

        endpoints = config.get("endpoints", {})
        testnet = endpoints.get("testnet", {})
        base_url = testnet.get("rest_base_url", "https://api-testnet.bybit.com")

        url = f"{base_url}/v5/account/info"
        timestamp = str(int(time.time() * 1000))
        signature = generate_signature(
            timestamp, api_credentials["key"], api_credentials["secret"], recv_window
        )

        headers = {
            "X-BAPI-API-KEY": api_credentials["key"],
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": str(recv_window),
            "X-BAPI-SIGN": signature,
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                data = await resp.json()

                # retCode 0 = success
                assert data.get("retCode") == 0, (
                    f"Testnet auth failed: {data.get('retMsg')} "
                    f"(retCode={data.get('retCode')})"
                )
                assert "result" in data

                print("\nTestnet auth: OK")

    @pytest.mark.asyncio
    async def test_live_authentication(self, config, api_credentials, recv_window):
        """Test authenticated access to live."""
        if not api_credentials["key"] or not api_credentials["secret"]:
            pytest.skip("No API credentials provided")

        endpoints = config.get("endpoints", {})
        live = endpoints.get("live", {})
        base_url = live.get("rest_base_url", "https://api.bybit.com")

        url = f"{base_url}/v5/account/info"
        timestamp = str(int(time.time() * 1000))
        signature = generate_signature(
            timestamp, api_credentials["key"], api_credentials["secret"], recv_window
        )

        headers = {
            "X-BAPI-API-KEY": api_credentials["key"],
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": str(recv_window),
            "X-BAPI-SIGN": signature,
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                data = await resp.json()

                # retCode 0 = success
                assert data.get("retCode") == 0, (
                    f"Live auth failed: {data.get('retMsg')} "
                    f"(retCode={data.get('retCode')})"
                )

                print("\nLive auth: OK")


class TestBybitMarketData:
    """Test market data endpoints."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("symbol", ["BTCUSDT", "ETHUSDT"])
    async def test_testnet_market_data_latency(self, config, symbol):
        """Test market data latency on testnet (<100ms target)."""
        endpoints = config.get("endpoints", {})
        testnet = endpoints.get("testnet", {})
        base_url = testnet.get("rest_base_url", "https://api-testnet.bybit.com")

        url = f"{base_url}/v5/market/tickers"

        async with aiohttp.ClientSession() as session:
            start_time = time.time()
            async with session.get(
                url,
                params={"category": "linear", "symbol": symbol},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                latency_ms = (time.time() - start_time) * 1000
                data = await resp.json()

                assert resp.status == 200, f"HTTP {resp.status}"
                assert data.get("retCode") == 0, f"API error: {data.get('retMsg')}"

                result = data.get("result", {})
                tickers = result.get("list", [])
                assert len(tickers) > 0, f"No ticker data for {symbol}"

                ticker = tickers[0]
                assert ticker.get("symbol") == symbol
                assert "lastPrice" in ticker

                # Log latency (don't fail if >100ms, just warn)
                threshold = (
                    config.get("settings", {})
                    .get("latency_threshold_ms", {})
                    .get("market_data", 100)
                )
                print(
                    f"\n{symbol} testnet latency: {latency_ms:.2f}ms (threshold: {threshold}ms)"
                )

                # Note: Latency may exceed threshold due to network conditions
                # This is logged but doesn't fail the test
                if latency_ms > threshold:
                    print(
                        f"   ⚠️  Latency exceeds threshold: {latency_ms:.2f}ms > {threshold}ms"
                    )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("symbol", ["BTCUSDT", "ETHUSDT"])
    async def test_live_market_data_latency(self, config, symbol):
        """Test market data latency on live (<100ms target)."""
        endpoints = config.get("endpoints", {})
        live = endpoints.get("live", {})
        base_url = live.get("rest_base_url", "https://api.bybit.com")

        url = f"{base_url}/v5/market/tickers"

        async with aiohttp.ClientSession() as session:
            start_time = time.time()
            async with session.get(
                url,
                params={"category": "linear", "symbol": symbol},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                latency_ms = (time.time() - start_time) * 1000
                data = await resp.json()

                assert resp.status == 200, f"HTTP {resp.status}"
                assert data.get("retCode") == 0, f"API error: {data.get('retMsg')}"

                result = data.get("result", {})
                tickers = result.get("list", [])
                assert len(tickers) > 0, f"No ticker data for {symbol}"

                ticker = tickers[0]
                assert ticker.get("symbol") == symbol
                assert "lastPrice" in ticker

                # Log latency (don't fail if >100ms, just warn)
                threshold = (
                    config.get("settings", {})
                    .get("latency_threshold_ms", {})
                    .get("market_data", 100)
                )
                print(
                    f"\n{symbol} live latency: {latency_ms:.2f}ms (threshold: {threshold}ms)"
                )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("mode", ["testnet", "live"])
    @pytest.mark.parametrize("symbol", ["BTCUSDT"])
    async def test_market_data_response_format(self, config, mode, symbol):
        """Test market data response format is correct."""
        endpoints = config.get("endpoints", {})
        ep = endpoints.get(mode, {})
        base_url = ep.get("rest_base_url")

        if not base_url:
            pytest.skip(f"No base URL for mode: {mode}")

        url = f"{base_url}/v5/market/tickers"

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                params={"category": "linear", "symbol": symbol},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()

                # Check response structure
                assert "retCode" in data
                assert "retMsg" in data
                assert "result" in data

                result = data["result"]
                assert "category" in result
                assert "list" in result

                tickers = result["list"]
                assert isinstance(tickers, list)

                if tickers:
                    ticker = tickers[0]
                    # Check required fields
                    assert "symbol" in ticker
                    assert "lastPrice" in ticker
                    assert "bid1Price" in ticker
                    assert "ask1Price" in ticker

                    print(f"\n{mode}/{symbol} fields: {list(ticker.keys())}")


class TestEndpointConfiguration:
    """Test endpoint configuration."""

    def test_config_file_exists(self):
        """Verify config file exists."""
        assert CONFIG_PATH.exists(), f"Config file not found: {CONFIG_PATH}"

    def test_config_structure(self, config):
        """Verify config has required structure."""
        assert "endpoints" in config
        assert "testnet" in config["endpoints"]
        assert "live" in config["endpoints"]

        # Check testnet config
        testnet = config["endpoints"]["testnet"]
        assert "rest_base_url" in testnet
        assert "ws_public_url" in testnet
        assert "ws_private_url" in testnet

        # Check live config
        live = config["endpoints"]["live"]
        assert "rest_base_url" in live
        assert "ws_public_url" in live
        assert "ws_private_url" in live

    def test_config_urls(self, config):
        """Verify endpoint URLs are correct."""
        endpoints = config.get("endpoints", {})

        # Testnet URLs
        testnet = endpoints.get("testnet", {})
        assert "api-testnet.bybit.com" in testnet.get("rest_base_url", "")
        assert "stream-testnet.bybit.com" in testnet.get("ws_public_url", "")

        # Live URLs
        live = endpoints.get("live", {})
        assert "api.bybit.com" in live.get("rest_base_url", "")
        assert "stream.bybit.com" in live.get("ws_public_url", "")

    def test_latency_thresholds(self, config):
        """Verify latency thresholds are configured."""
        settings = config.get("settings", {})
        thresholds = settings.get("latency_threshold_ms", {})

        assert "market_data" in thresholds
        assert "authenticated" in thresholds

        # Market data should be <100ms
        assert thresholds["market_data"] == 100


class TestFallbackBehavior:
    """Test fallback behavior configuration."""

    def test_fallback_enabled(self, config):
        """Verify fallback is enabled in config."""
        settings = config.get("settings", {})
        fallback = settings.get("fallback", {})

        assert fallback.get("enabled") is True

    def test_fallback_order(self, config):
        """Verify fallback order is configured."""
        settings = config.get("settings", {})
        fallback = settings.get("fallback", {})

        fallback_order = fallback.get("fallback_order", [])
        assert len(fallback_order) >= 2
        assert "testnet" in fallback_order

    def test_default_mode(self, config):
        """Verify default mode is testnet."""
        settings = config.get("settings", {})
        assert settings.get("default_mode") == "testnet"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
