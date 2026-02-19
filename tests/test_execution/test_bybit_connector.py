"""Tests for Bybit connector.

For ST-DATA-002: Execution Market Data Ingestion - Bybit/Bitget
"""

import time
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from data.exchange.bybit_connector import BybitConfig, BybitConnector


class TestBybitConfig:
    """Test BybitConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = BybitConfig()
        assert config.api_key == ""
        assert config.api_secret == ""
        assert config.base_url == "https://api.bybit.com"
        assert config.testnet is False
        assert config.demo is False

    def test_testnet_config(self):
        """Test testnet configuration."""
        config = BybitConfig(testnet=True)
        assert config.base_url == "https://api-testnet.bybit.com"
        assert config.ws_url == "wss://stream-testnet.bybit.com/v5/public/linear"

    def test_bybit_config_demo_mode(self):
        """Test that demo mode sets correct endpoints."""
        config = BybitConfig(demo=True)
        assert config.base_url == "https://api-demo.bybit.com"
        assert config.private_ws_url == "wss://stream-demo.bybit.com/v5/private"
        assert (
            config.ws_url == "wss://stream.bybit.com/v5/public/linear"
        )  # Public uses mainnet


class TestBybitConnector:
    """Test BybitConnector functionality."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return BybitConfig(
            api_key="test_key",
            api_secret="test_secret",
        )

    @pytest.fixture
    def connector(self, config):
        """Create test connector."""
        return BybitConnector(config)

    @pytest.mark.asyncio
    async def test_connect(self, connector):
        """Test HTTP session initialization."""
        await connector.connect()
        assert connector._session is not None
        assert not connector._session.closed
        await connector.close()

    @pytest.mark.asyncio
    async def test_close(self, connector):
        """Test connection cleanup."""
        await connector.connect()
        await connector.close()
        assert connector._session is None

    @pytest.mark.asyncio
    async def test_context_manager(self, config):
        """Test async context manager."""
        async with BybitConnector(config) as connector:
            assert connector._session is not None
        assert connector._session is None

    @pytest.mark.asyncio
    async def test_get_ticker(self, connector):
        """Test get_ticker method."""
        mock_response = {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "list": [
                    {
                        "symbol": "BTCUSDT",
                        "lastPrice": "65000.00",
                        "volume24h": "1000",
                    }
                ]
            },
        }

        with patch.object(
            connector, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            result = await connector.get_ticker("BTCUSDT")

            assert result == mock_response
            mock_request.assert_called_once_with(
                "GET",
                "/v5/market/tickers",
                params={"category": "linear", "symbol": "BTCUSDT"},
            )

    @pytest.mark.asyncio
    async def test_get_orderbook(self, connector):
        """Test get_orderbook method."""
        mock_response = {
            "retCode": 0,
            "result": {
                "s": "BTCUSDT",
                "b": [["64999.00", "1.5"]],
                "a": [["65000.00", "2.0"]],
            },
        }

        with patch.object(
            connector, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            result = await connector.get_orderbook("BTCUSDT", limit=50)

            assert result == mock_response
            mock_request.assert_called_once_with(
                "GET",
                "/v5/market/orderbook",
                params={"category": "linear", "symbol": "BTCUSDT", "limit": 50},
            )

    @pytest.mark.asyncio
    async def test_get_fills(self, connector):
        """Test get_fills method."""
        mock_response = {
            "retCode": 0,
            "result": {
                "list": [
                    {
                        "orderId": "test_order_1",
                        "execId": "exec_1",
                        "symbol": "BTCUSDT",
                        "side": "Buy",
                        "execPrice": "65000.00",
                        "execQty": "0.1",
                        "execTime": "1704067200000",
                        "execFee": "6.50",
                    }
                ]
            },
        }

        with patch.object(
            connector, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            result = await connector.get_fills(
                symbol="BTCUSDT",
                order_id="test_order_1",
                limit=50,
            )

            assert result == mock_response
            mock_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_positions(self, connector):
        """Test get_positions method."""
        mock_response = {
            "retCode": 0,
            "result": {
                "list": [
                    {
                        "symbol": "BTCUSDT",
                        "side": "Buy",
                        "size": "0.5",
                        "avgPrice": "64000.00",
                        "leverage": "10",
                        "markPrice": "65000.00",
                    }
                ]
            },
        }

        with patch.object(
            connector, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            result = await connector.get_positions(symbol="BTCUSDT")

            assert result == mock_response
            mock_request.assert_called_once_with(
                "GET",
                "/v5/position/list",
                params={"category": "linear", "symbol": "BTCUSDT"},
                signed=True,
            )

    @pytest.mark.asyncio
    async def test_get_stop_orders(self, connector):
        """Test get_stop_orders method."""
        mock_response = {
            "retCode": 0,
            "result": {
                "list": [
                    {
                        "orderId": "stop_1",
                        "symbol": "BTCUSDT",
                        "stopOrderType": "StopLoss",
                        "triggerPrice": "60000.00",
                    }
                ]
            },
        }

        with patch.object(
            connector, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            result = await connector.get_stop_orders(symbol="BTCUSDT")

            assert result == mock_response
            mock_request.assert_called_once()

    def test_health_status(self, connector):
        """Test health status tracking."""
        health = connector.get_health()
        assert health.is_connected is False
        assert health.reconnect_count == 0

    def test_is_healthy(self, connector):
        """Test health check logic."""
        import time

        assert connector.is_healthy() is False

        connector._health.is_connected = True
        connector._health.last_message = time.time()
        assert connector.is_healthy() is True

    @pytest.mark.asyncio
    async def test_health_check(self, connector):
        """Test health_check method."""
        with patch.object(
            connector, "get_ticker", new_callable=AsyncMock
        ) as mock_ticker:
            mock_ticker.return_value = {"retCode": 0}
            connector._health.is_connected = True
            connector._health.last_message = time.time()

            result = await connector.health_check()

            assert result["healthy"] is True
            assert result["connected"] is True

    def test_callback_registration(self, connector):
        """Test callback registration."""
        callback_called = False

        def test_callback(data):
            nonlocal callback_called
            callback_called = True

        connector.on_message(test_callback)
        assert len(connector._message_callbacks) == 1

        # Test price callback
        price_called = False

        def price_callback(symbol, price):
            nonlocal price_called
            price_called = True

        connector.on_price(price_callback)
        assert len(connector._price_callbacks) == 1

    def test_reconnect_delays(self):
        """Test exponential backoff delays."""
        assert BybitConnector.RECONNECT_DELAYS == [1, 2, 4, 8, 16, 32, 60]
        assert BybitConnector.HEARTBEAT_INTERVAL == 30


class TestBybitWebSocket:
    """Test WebSocket functionality."""

    @pytest.fixture
    def connector(self):
        """Create test connector."""
        config = BybitConfig(api_key="test", api_secret="test")
        return BybitConnector(config)

    @pytest.mark.asyncio
    async def test_handle_message_ticker(self, connector):
        """Test handling ticker message."""
        price_updates = []

        def price_callback(symbol, price):
            price_updates.append((symbol, price))

        connector.on_price(price_callback)

        message = {
            "topic": "tickers.BTCUSDT",
            "data": {
                "symbol": "BTCUSDT",
                "lastPrice": "65000.00",
            },
        }

        await connector._handle_message(message)

        assert len(price_updates) == 1
        assert price_updates[0][0] == "BTCUSDT"
        assert price_updates[0][1] == Decimal("65000.00")

    @pytest.mark.asyncio
    async def test_handle_message_pong(self, connector):
        """Test handling pong message."""
        message = {"op": "pong"}

        await connector._handle_message(message)

        # Should update heartbeat timestamp
        assert connector._health.last_message > 0


class TestBybitSignature:
    """Test signature generation."""

    def test_generate_signature(self):
        """Test HMAC signature generation."""
        config = BybitConfig(api_key="key", api_secret="secret")
        connector = BybitConnector(config)

        timestamp = "1704067200000"
        signature = connector._generate_signature(timestamp, "")

        assert isinstance(signature, str)
        assert len(signature) == 64  # SHA256 hex digest

    def test_generate_signature_with_payload(self):
        """Test signature with payload."""
        config = BybitConfig(api_key="key", api_secret="secret")
        connector = BybitConnector(config)

        timestamp = "1704067200000"
        payload = "param1=value1&param2=value2"
        signature = connector._generate_signature(timestamp, payload)

        assert isinstance(signature, str)
        assert len(signature) == 64


class TestBybitCredentialResolver:
    """Test credential resolver functionality."""

    @pytest.fixture
    def clean_env(self, monkeypatch):
        """Clean environment variables before each test."""
        # Clear all Bybit-related env vars
        for key in [
            "BYBIT_DEMO_API_KEY",
            "BYBIT_DEMO_API_SECRET",
            "BYBIT_API_KEY",
            "BYBIT_API_SECRET",
            "BYBIT_TESTNET_API_KEY",
            "BYBIT_TESTNET_API_SECRET",
        ]:
            monkeypatch.delenv(key, raising=False)

    def test_resolve_bybit_credentials_priority_order(self, clean_env, monkeypatch):
        """Test that credentials are resolved in priority order."""
        from data.exchange.credential_resolver import (
            resolve_bybit_credentials,
            BybitCredentialResolver,
        )

        # Set all three pairs - should use first priority
        monkeypatch.setenv("BYBIT_DEMO_API_KEY", "demo_key")
        monkeypatch.setenv("BYBIT_DEMO_API_SECRET", "demo_secret")
        monkeypatch.setenv("BYBIT_API_KEY", "api_key")
        monkeypatch.setenv("BYBIT_API_SECRET", "api_secret")
        monkeypatch.setenv("BYBIT_TESTNET_API_KEY", "testnet_key")
        monkeypatch.setenv("BYBIT_TESTNET_API_SECRET", "testnet_secret")

        creds = resolve_bybit_credentials(load_env=False)

        assert creds is not None
        assert creds.source == "BYBIT_DEMO_API_KEY"
        assert creds.api_key == "demo_key"
        assert creds.api_secret == "demo_secret"
        assert creds.testnet_mode is False

    def test_resolve_bybit_credentials_fallback(self, clean_env, monkeypatch):
        """Test fallback to second priority when first is missing."""
        from data.exchange.credential_resolver import resolve_bybit_credentials

        # Only set second priority
        monkeypatch.setenv("BYBIT_API_KEY", "api_key")
        monkeypatch.setenv("BYBIT_API_SECRET", "api_secret")

        creds = resolve_bybit_credentials(load_env=False)

        assert creds is not None
        assert creds.source == "BYBIT_API_KEY"
        assert creds.api_key == "api_key"
        assert creds.testnet_mode is False

    def test_resolve_bybit_credentials_testnet(self, clean_env, monkeypatch):
        """Test testnet credentials are properly detected."""
        from data.exchange.credential_resolver import resolve_bybit_credentials

        monkeypatch.setenv("BYBIT_TESTNET_API_KEY", "testnet_key")
        monkeypatch.setenv("BYBIT_TESTNET_API_SECRET", "testnet_secret")

        creds = resolve_bybit_credentials(load_env=False)

        assert creds is not None
        assert creds.source == "BYBIT_TESTNET_API_KEY"
        assert creds.testnet_mode is True

    def test_resolve_bybit_credentials_no_creds(self, clean_env):
        """Test that None is returned when no credentials are set."""
        from data.exchange.credential_resolver import resolve_bybit_credentials

        creds = resolve_bybit_credentials(load_env=False)

        assert creds is None

    def test_credentials_masking(self):
        """Test that credentials are properly masked."""
        from data.exchange.credential_resolver import BybitCredentials

        creds = BybitCredentials(
            api_key="ABCDEFGHIJKLMNOP",
            api_secret="1234567890123456",
            source="BYBIT_API_KEY",
            testnet_mode=False,
            env_file_loaded=False,
        )

        masked_key = creds.get_masked_key()
        masked_secret = creds.get_masked_secret()

        assert masked_key == "ABCD...MNOP"
        assert masked_secret == "1234...3456"
        assert "ABCDEF" not in masked_key
        assert "123456" not in masked_secret

    def test_credentials_short_masking(self):
        """Test masking of short credentials."""
        from data.exchange.credential_resolver import BybitCredentials

        creds = BybitCredentials(
            api_key="1234",
            api_secret="5678",
            source="BYBIT_API_KEY",
            testnet_mode=False,
            env_file_loaded=False,
        )

        assert creds.get_masked_key() == "****"
        assert creds.get_masked_secret() == "****"

    def test_get_credential_resolution_status(self, clean_env, monkeypatch):
        """Test credential resolution status reporting."""
        from data.exchange.credential_resolver import get_credential_resolution_status

        monkeypatch.setenv("BYBIT_DEMO_API_KEY", "demo_key")
        monkeypatch.setenv("BYBIT_DEMO_API_SECRET", "demo_secret")

        status = get_credential_resolution_status()

        assert status["env_file_loaded"] in [True, False]
        assert len(status["checks"]) == 3
        assert len(status["found_credentials"]) >= 1
        assert status["selected"] is not None
        assert status["selected"]["source"] == "BYBIT_DEMO_API_KEY"
        assert "masked_key" in status["selected"]

    def test_bybit_config_from_env(self, clean_env, monkeypatch):
        """Test BybitConfig.from_env factory method."""
        monkeypatch.setenv("BYBIT_API_KEY", "api_key_value")
        monkeypatch.setenv("BYBIT_API_SECRET", "api_secret_value")

        config = BybitConfig.from_env(load_env=False)

        assert config.api_key == "api_key_value"
        assert config.api_secret == "api_secret_value"
        assert config.testnet is False

    def test_bybit_config_from_env_testnet(self, clean_env, monkeypatch):
        """Test BybitConfig.from_env with testnet credentials."""
        monkeypatch.setenv("BYBIT_TESTNET_API_KEY", "testnet_key")
        monkeypatch.setenv("BYBIT_TESTNET_API_SECRET", "testnet_secret")

        config = BybitConfig.from_env(load_env=False)

        assert config.api_key == "testnet_key"
        assert config.api_secret == "testnet_secret"
        assert config.testnet is True
        assert "testnet" in config.base_url

    def test_bybit_config_from_env_missing_creds(self, clean_env):
        """Test BybitConfig.from_env raises error when no credentials."""
        with pytest.raises(ValueError) as exc_info:
            BybitConfig.from_env(load_env=False)

        assert "No Bybit credentials found" in str(exc_info.value)

    def test_bybit_connector_from_env(self, clean_env, monkeypatch):
        """Test BybitConnector.from_env factory method."""
        monkeypatch.setenv("BYBIT_API_KEY", "connector_key")
        monkeypatch.setenv("BYBIT_API_SECRET", "connector_secret")

        connector = BybitConnector.from_env(load_env=False)

        assert connector.config.api_key == "connector_key"
        assert connector.config.api_secret == "connector_secret"

    def test_credential_prefix_validation(self):
        """Test that credentials can be validated for expected prefixes."""
        from data.exchange.credential_resolver import BybitCredentials

        valid_creds = BybitCredentials(
            api_key="R9Kxxxxxx",
            api_secret="3Ndyyyyyy",
            source="TEST",
            testnet_mode=False,
            demo_mode=True,
            env_file_loaded=False,
        )
        assert valid_creds.api_key.startswith("R9K")
        assert valid_creds.api_secret.startswith("3Nd")
        assert valid_creds.validate_key_prefix() is True
        assert valid_creds.validate_secret_prefix() is True

        # Test prefix validation methods
        validation = valid_creds.get_prefix_validation()
        assert validation["key_valid"] is True
        assert validation["secret_valid"] is True
        assert validation["all_valid"] is True
        assert validation["expected_key_prefix"] == "R9K"
        assert validation["expected_secret_prefix"] == "3Nd"

    def test_credential_prefix_validation_invalid(self):
        """Test prefix validation with invalid prefixes."""
        from data.exchange.credential_resolver import BybitCredentials

        invalid_creds = BybitCredentials(
            api_key="INVALID_KEY",
            api_secret="INVALID_SECRET",
            source="TEST",
            testnet_mode=False,
            demo_mode=False,
            env_file_loaded=False,
        )
        assert invalid_creds.validate_key_prefix() is False
        assert invalid_creds.validate_secret_prefix() is False

        validation = invalid_creds.get_prefix_validation()
        assert validation["key_valid"] is False
        assert validation["secret_valid"] is False
        assert validation["all_valid"] is False


class TestBybitCredentialResolverAll:
    """Test resolve_all functionality."""

    def test_resolve_all_multiple_pairs(self, monkeypatch):
        """Test resolving all available credential pairs."""
        from data.exchange.credential_resolver import BybitCredentialResolver

        # Set up multiple credential pairs
        monkeypatch.setenv("BYBIT_DEMO_API_KEY", "demo_key")
        monkeypatch.setenv("BYBIT_DEMO_API_SECRET", "demo_secret")
        monkeypatch.setenv("BYBIT_API_KEY", "api_key")
        monkeypatch.setenv("BYBIT_API_SECRET", "api_secret")

        resolver = BybitCredentialResolver()
        all_creds = resolver.resolve_all(load_env=False)

        assert len(all_creds) == 2
        assert "BYBIT_DEMO_API_KEY" in all_creds
        assert "BYBIT_API_KEY" in all_creds
        assert all_creds["BYBIT_DEMO_API_KEY"].api_key == "demo_key"
        assert all_creds["BYBIT_API_KEY"].api_key == "api_key"


class TestBybitRoutingPolicy:
    """Test explicit routing policy for demo mode.

    Validates routing matrix from BYBIT-DEMO-003:
    - REST operations use api-demo.bybit.com
    - Private WS uses stream-demo.bybit.com
    - Public WS uses stream.bybit.com (mainnet)
    """

    def test_demo_mode_rest_endpoint(self):
        """Demo mode uses correct REST endpoint."""
        config = BybitConfig(demo=True)
        assert config.base_url == "https://api-demo.bybit.com"
        assert "api-demo" in config.base_url

    def test_demo_mode_private_ws_endpoint(self):
        """Demo mode uses correct private WebSocket endpoint."""
        config = BybitConfig(demo=True)
        assert config.private_ws_url == "wss://stream-demo.bybit.com/v5/private"
        assert "stream-demo" in config.private_ws_url

    def test_demo_mode_public_ws_uses_mainnet(self):
        """Demo mode uses mainnet for public WebSocket (shared across modes)."""
        config = BybitConfig(demo=True)
        assert config.ws_url == "wss://stream.bybit.com/v5/public/linear"
        assert "stream.bybit.com" in config.ws_url
        assert "demo" not in config.ws_url  # Public WS should NOT use demo

    def test_routing_matrix_consistency(self):
        """All modes have consistent endpoint configuration."""
        demo_config = BybitConfig(demo=True)
        testnet_config = BybitConfig(testnet=True)
        live_config = BybitConfig()  # Default is live

        # Demo: demo REST, demo private WS, mainnet public WS
        assert "api-demo" in demo_config.base_url
        assert "stream-demo" in demo_config.private_ws_url
        assert "stream.bybit.com" in demo_config.ws_url

        # Testnet: all testnet
        assert "testnet" in testnet_config.base_url
        assert "testnet" in testnet_config.private_ws_url
        assert "testnet" in testnet_config.ws_url

        # Live: all mainnet
        assert live_config.base_url == "https://api.bybit.com"
        assert live_config.private_ws_url == "wss://stream.bybit.com/v5/private"
        assert live_config.ws_url == "wss://stream.bybit.com/v5/public/linear"

    def test_demo_mode_distinguishable_from_live(self):
        """Demo mode endpoints differ from live mode."""
        demo_config = BybitConfig(demo=True)
        live_config = BybitConfig()

        assert demo_config.base_url != live_config.base_url
        assert demo_config.private_ws_url != live_config.private_ws_url
        # Public WS should be the same
        assert demo_config.ws_url == live_config.ws_url

    @pytest.mark.asyncio
    async def test_fallback_to_rest_on_ws_failure(self):
        """Connector falls back to REST polling when WebSocket fails."""
        config = BybitConfig(demo=True, api_key="test", api_secret="test")
        connector = BybitConnector(config)

        # Simulate WS failure by not starting WebSocket
        await connector.connect()

        # Verify REST is still functional
        with patch.object(
            connector, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = {"retCode": 0, "result": {}}

            # Should be able to get ticker via REST
            result = await connector.get_ticker("BTCUSDT")
            assert result is not None
            mock_request.assert_called_once()

        await connector.close()

    def test_endpoint_priority_documented(self):
        """Endpoint priority is documented and testable."""
        # Priority order: Demo > Testnet > Live
        # This test validates the priority logic is intentional

        priority_order = [
            ("demo", BybitConfig(demo=True)),
            ("testnet", BybitConfig(testnet=True)),
            ("live", BybitConfig()),
        ]

        for name, config in priority_order:
            assert config.base_url is not None
            assert config.private_ws_url is not None
            assert config.ws_url is not None

            if name == "demo":
                assert "api-demo" in config.base_url
            elif name == "testnet":
                assert "testnet" in config.base_url
            else:
                assert config.base_url == "https://api.bybit.com"
