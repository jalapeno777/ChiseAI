"""Tests for the Bybit Demo Connector.

Comprehensive test suite covering:
- Exception hierarchy and error classification
- Retry logic with exponential backoff and jitter
- Provenance tracking for full order lifecycle
- BybitDemoConnector with clean separation of concerns
"""

from __future__ import annotations

import math
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from execution.connectors.bybit_demo_connector import (
    BybitAPIError,
    BybitAuthenticationError,
    BybitConnectorError,
    BybitDemoConnector,
    BybitDemoConnectorFactory,
    BybitNetworkError,
    BybitOrderError,
    BybitRateLimitError,
    DemoProvenance,
    ExponentialBackoffRetry,
    ProvenanceEvent,
    ProvenanceEventType,
    ProvenanceTracker,
    RetryConfig,
    classify_bybit_error,
    create_bybit_demo_connector,
)
from execution.paper.models import OrderState, PaperFill, PaperOrder

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_connector(demo: bool = True) -> MagicMock:
    """Create a mock BybitConnector with a demo config."""
    config = MagicMock()
    config.demo = demo
    config.base_url = "https://api-testnet.bybit.com"
    config.private_ws_url = "wss://stream-testnet.bybit.com/ws/v5/private"
    config.api_key = "DEMO1234567890"

    connector = MagicMock()
    connector.config = config
    connector._session = MagicMock()
    connector._session.closed = False
    return connector


def _make_market_data() -> MagicMock:
    """Create a mock market data provider."""
    md = MagicMock()
    md.get_price.return_value = None
    md.set_price = MagicMock()
    return md


# ===========================================================================
# Exception Hierarchy Tests
# ===========================================================================


class TestBybitAPIError:
    """Tests for BybitAPIError base exception."""

    def test_base_exception_properties(self) -> None:
        err = BybitAPIError(
            message="test error",
            error_code="10001",
            status_code=429,
            operation="place_order",
            retryable=True,
        )
        assert err.error_code == "10001"
        assert err.status_code == 429
        assert err.operation == "place_order"
        assert err.retryable is True
        assert str(err) == "test error"

    def test_defaults(self) -> None:
        err = BybitAPIError("simple error")
        assert err.error_code is None
        assert err.status_code is None
        assert err.operation is None
        assert err.retryable is False

    def test_is_exception(self) -> None:
        assert issubclass(BybitAPIError, Exception)


class TestBybitRateLimitError:
    """Tests for BybitRateLimitError."""

    def test_rate_limit_properties(self) -> None:
        err = BybitRateLimitError(retry_after=5.0)
        assert err.retry_after == 5.0
        assert err.status_code == 429
        assert err.error_code == "429"
        assert err.retryable is True

    def test_is_api_error(self) -> None:
        assert issubclass(BybitRateLimitError, BybitAPIError)


class TestBybitAuthenticationError:
    """Tests for BybitAuthenticationError."""

    def test_auth_error_not_retryable(self) -> None:
        err = BybitAuthenticationError("bad key")
        assert err.retryable is False
        assert err.status_code == 401
        assert issubclass(BybitAuthenticationError, BybitAPIError)


class TestBybitNetworkError:
    """Tests for BybitNetworkError."""

    def test_network_error_retryable(self) -> None:
        err = BybitNetworkError("timeout")
        assert err.retryable is True
        assert err.status_code is None
        assert issubclass(BybitNetworkError, BybitAPIError)


class TestBybitOrderError:
    """Tests for BybitOrderError."""

    def test_order_error_with_order_id(self) -> None:
        err = BybitOrderError("insufficient margin", order_id="order123")
        assert err.order_id == "order123"
        assert err.retryable is False
        assert issubclass(BybitOrderError, BybitAPIError)

    def test_order_error_retryable_override(self) -> None:
        err = BybitOrderError("temp error", retryable=True)
        assert err.retryable is True


class TestBybitConnectorError:
    """Tests for BybitConnectorError."""

    def test_connector_error_default_retryable(self) -> None:
        err = BybitConnectorError("session down")
        assert err.retryable is True

    def test_connector_error_not_retryable(self) -> None:
        err = BybitConnectorError("bad config", retryable=False)
        assert err.retryable is False


class TestClassifyBybitError:
    """Tests for classify_bybit_error."""

    def test_rate_limit_codes(self) -> None:
        for code in ["10001", "10002", "10003", "10004"]:
            err = classify_bybit_error(code, operation="test")
            assert isinstance(err, BybitRateLimitError), f"code={code}"
            assert err.retryable is True

    def test_auth_codes(self) -> None:
        for code in ["10006", "10007", "10008", "10009", "10010", "10013"]:
            err = classify_bybit_error(code)
            assert isinstance(err, BybitAuthenticationError), f"code={code}"
            assert err.retryable is False

    def test_order_codes(self) -> None:
        for code in ["110001", "110004", "110006", "110012", "13001", "13002"]:
            err = classify_bybit_error(code)
            assert isinstance(err, BybitOrderError), f"code={code}"

    def test_unknown_5xx_retryable(self) -> None:
        err = classify_bybit_error("50001")
        assert isinstance(err, BybitAPIError)
        assert err.retryable is True

    def test_unknown_3xx_retryable(self) -> None:
        err = classify_bybit_error("30001")
        assert isinstance(err, BybitAPIError)
        assert err.retryable is True

    def test_unknown_1xx_not_retryable(self) -> None:
        err = classify_bybit_error("19999")
        assert isinstance(err, BybitAPIError)
        assert err.retryable is False

    def test_no_error_code(self) -> None:
        err = classify_bybit_error(None, "some message")
        assert err.error_code == "unknown"

    def test_ret_code_zero(self) -> None:
        err = classify_bybit_error(0)
        assert err.error_code == "0"

    def test_int_code(self) -> None:
        err = classify_bybit_error(10006)
        assert isinstance(err, BybitAuthenticationError)

    def test_with_custom_message(self) -> None:
        err = classify_bybit_error(
            "110006", ret_msg="Insufficient balance", operation="place_order"
        )
        assert isinstance(err, BybitOrderError)
        assert "Insufficient balance" in str(err)
        assert err.operation == "place_order"


# ===========================================================================
# RetryConfig Tests
# ===========================================================================


class TestRetryConfig:
    """Tests for RetryConfig."""

    def test_default_config(self) -> None:
        config = RetryConfig()
        assert config.max_retries == 3
        assert config.base_delay == 0.5
        assert config.max_delay == 30.0
        assert config.exponential_base == 2.0
        assert config.jitter_range == (0.8, 1.2)

    def test_custom_config(self) -> None:
        config = RetryConfig(
            max_retries=5,
            base_delay=1.0,
            max_delay=60.0,
            exponential_base=3.0,
            jitter_range=(0.5, 1.5),
        )
        assert config.max_retries == 5
        assert config.base_delay == 1.0
        assert config.max_delay == 60.0

    def test_get_delay_attempt_1(self) -> None:
        config = RetryConfig(base_delay=1.0, jitter_range=(1.0, 1.0))
        delay = config.get_delay(1)
        assert delay == 1.0  # base_delay * 2^0 = 1.0

    def test_get_delay_attempt_2(self) -> None:
        config = RetryConfig(base_delay=1.0, jitter_range=(1.0, 1.0))
        delay = config.get_delay(2)
        assert delay == 2.0  # base_delay * 2^1 = 2.0

    def test_get_delay_attempt_3(self) -> None:
        config = RetryConfig(base_delay=1.0, jitter_range=(1.0, 1.0))
        delay = config.get_delay(3)
        assert delay == 4.0  # base_delay * 2^2 = 4.0

    def test_get_delay_max_cap(self) -> None:
        config = RetryConfig(base_delay=1.0, max_delay=3.0, jitter_range=(1.0, 1.0))
        delay = config.get_delay(10)
        assert delay == 3.0  # capped

    def test_get_delay_with_jitter(self) -> None:
        config = RetryConfig(base_delay=10.0, jitter_range=(0.5, 1.5))
        delays = [config.get_delay(1) for _ in range(100)]
        assert all(5.0 <= d <= 15.0 for d in delays)
        # Most should be in the middle range
        assert min(delays) < max(delays)

    def test_get_delay_exponential_base(self) -> None:
        config = RetryConfig(
            base_delay=1.0, exponential_base=3.0, jitter_range=(1.0, 1.0)
        )
        assert config.get_delay(1) == 1.0
        assert config.get_delay(2) == 3.0
        assert config.get_delay(3) == 9.0


# ===========================================================================
# ExponentialBackoffRetry Tests
# ===========================================================================


class TestExponentialBackoffRetry:
    """Tests for ExponentialBackoffRetry."""

    @pytest.mark.asyncio
    async def test_success_first_try(self) -> None:
        func = AsyncMock(return_value="ok")
        retry = ExponentialBackoffRetry(config=RetryConfig(max_retries=3))
        result = await retry.execute(func, "arg1", kwarg="kw1")
        assert result == "ok"
        func.assert_called_once_with("arg1", kwarg="kw1")

    @pytest.mark.asyncio
    async def test_retry_then_success(self) -> None:
        func = AsyncMock(side_effect=[BybitNetworkError("timeout"), "ok"])
        retry = ExponentialBackoffRetry(config=RetryConfig(max_retries=3))
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await retry.execute(func)
        assert result == "ok"
        assert func.call_count == 2

    @pytest.mark.asyncio
    async def test_exhaust_retries(self) -> None:
        func = AsyncMock(side_effect=BybitNetworkError("timeout"))
        retry = ExponentialBackoffRetry(config=RetryConfig(max_retries=2))
        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(BybitNetworkError):
                await retry.execute(func)
        assert func.call_count == 3  # initial attempt + 2 retries

    @pytest.mark.asyncio
    async def test_non_retryable_error_no_retry(self) -> None:
        func = AsyncMock(side_effect=BybitAuthenticationError("bad key"))
        retry = ExponentialBackoffRetry(config=RetryConfig(max_retries=3))
        with pytest.raises(BybitAuthenticationError):
            await retry.execute(func)
        func.assert_called_once()

    @pytest.mark.asyncio
    async def test_custom_retryable_predicate(self) -> None:
        """Custom predicate can override default retryability."""
        func = AsyncMock(side_effect=ValueError("custom"))
        # By default ValueError is NOT retryable.
        retry_default = ExponentialBackoffRetry(config=RetryConfig(max_retries=3))
        with pytest.raises(ValueError):
            await retry_default.execute(func)
        func.assert_called_once()

        # With custom predicate that says ValueError IS retryable.
        func.reset_mock()
        func.side_effect = [ValueError("custom"), "ok"]
        retry_custom = ExponentialBackoffRetry(
            config=RetryConfig(max_retries=3),
            retryable_predicate=lambda e: isinstance(e, ValueError),
        )
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await retry_custom.execute(func)
        assert result == "ok"
        assert func.call_count == 2

    @pytest.mark.asyncio
    async def test_os_error_retryable(self) -> None:
        func = AsyncMock(side_effect=[OSError("connection reset"), "ok"])
        retry = ExponentialBackoffRetry(config=RetryConfig(max_retries=3))
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await retry.execute(func)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_timeout_error_retryable(self) -> None:
        func = AsyncMock(side_effect=[TimeoutError(), "ok"])
        retry = ExponentialBackoffRetry(config=RetryConfig(max_retries=3))
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await retry.execute(func)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_connection_error_retryable(self) -> None:
        func = AsyncMock(side_effect=[ConnectionError("refused"), "ok"])
        retry = ExponentialBackoffRetry(config=RetryConfig(max_retries=3))
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await retry.execute(func)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_zero_max_retries(self) -> None:
        func = AsyncMock(side_effect=BybitNetworkError("timeout"))
        retry = ExponentialBackoffRetry(config=RetryConfig(max_retries=0))
        with pytest.raises(BybitNetworkError):
            await retry.execute(func)
        func.assert_called_once()


# ===========================================================================
# ProvenanceTracker Tests
# ===========================================================================


class TestProvenanceTracker:
    """Tests for ProvenanceTracker."""

    def test_record_event(self) -> None:
        tracker = ProvenanceTracker()
        event = tracker.record(
            ProvenanceEventType.ORDER_PLACED,
            order_id="order1",
            symbol="BTCUSDT",
            side="buy",
        )
        assert event.event_type == ProvenanceEventType.ORDER_PLACED
        assert event.order_id == "order1"
        assert event.symbol == "BTCUSDT"
        assert event.details == {"side": "buy"}
        assert event.timestamp is not None

    def test_event_count(self) -> None:
        tracker = ProvenanceTracker()
        assert tracker.event_count == 0
        tracker.record(ProvenanceEventType.CONNECTOR_INIT)
        tracker.record(ProvenanceEventType.ORDER_PLACED)
        assert tracker.event_count == 2

    def test_clear_events(self) -> None:
        tracker = ProvenanceTracker()
        tracker.record(ProvenanceEventType.CONNECTOR_INIT)
        assert tracker.event_count == 1
        tracker.clear()
        assert tracker.event_count == 0

    def test_get_events_all(self) -> None:
        tracker = ProvenanceTracker()
        tracker.record(ProvenanceEventType.CONNECTOR_INIT)
        tracker.record(ProvenanceEventType.ORDER_PLACED, order_id="o1")
        events = tracker.get_events()
        assert len(events) == 2
        # Most recent first.
        assert events[0].event_type == ProvenanceEventType.ORDER_PLACED

    def test_get_events_by_order_id(self) -> None:
        tracker = ProvenanceTracker()
        tracker.record(ProvenanceEventType.ORDER_PLACED, order_id="o1")
        tracker.record(ProvenanceEventType.ORDER_PLACED, order_id="o2")
        tracker.record(ProvenanceEventType.ORDER_CANCELLED, order_id="o1")
        events = tracker.get_events(order_id="o1")
        assert len(events) == 2
        assert all(e.order_id == "o1" for e in events)

    def test_get_events_by_type(self) -> None:
        tracker = ProvenanceTracker()
        tracker.record(ProvenanceEventType.ORDER_PLACED, order_id="o1")
        tracker.record(ProvenanceEventType.ORDER_CANCELLED, order_id="o1")
        tracker.record(ProvenanceEventType.ORDER_PLACED, order_id="o2")
        events = tracker.get_events(event_type=ProvenanceEventType.ORDER_PLACED)
        assert len(events) == 2

    def test_get_events_limit(self) -> None:
        tracker = ProvenanceTracker()
        for i in range(10):
            tracker.record(ProvenanceEventType.PRICE_FETCHED, symbol=f"SYM{i}")
        events = tracker.get_events(limit=3)
        assert len(events) == 3
        # Most recent first.
        assert events[0].symbol == "SYM9"

    def test_get_order_history_chronological(self) -> None:
        tracker = ProvenanceTracker()
        tracker.record(ProvenanceEventType.ORDER_PLACED, order_id="o1")
        tracker.record(ProvenanceEventType.ORDER_FILLED, order_id="o1")
        tracker.record(ProvenanceEventType.ORDER_CANCELLED, order_id="o2")
        history = tracker.get_order_history("o1")
        assert len(history) == 2
        # Chronological order (oldest first).
        assert history[0].event_type == ProvenanceEventType.ORDER_PLACED
        assert history[1].event_type == ProvenanceEventType.ORDER_FILLED

    def test_max_events_enforcement(self) -> None:
        tracker = ProvenanceTracker(max_events=5)
        for i in range(10):
            tracker.record(ProvenanceEventType.PRICE_FETCHED)
        assert tracker.event_count == 5

    def test_no_matching_events(self) -> None:
        tracker = ProvenanceTracker()
        tracker.record(ProvenanceEventType.ORDER_PLACED, order_id="o1")
        events = tracker.get_events(order_id="nonexistent")
        assert len(events) == 0


class TestProvenanceEvent:
    """Tests for ProvenanceEvent dataclass."""

    def test_default_details(self) -> None:
        event = ProvenanceEvent(
            event_type=ProvenanceEventType.CONNECTOR_INIT,
            timestamp="2025-01-01T00:00:00Z",
        )
        assert event.order_id is None
        assert event.symbol is None
        assert event.details == {}

    def test_with_details(self) -> None:
        event = ProvenanceEvent(
            event_type=ProvenanceEventType.ORDER_PLACED,
            timestamp="2025-01-01T00:00:00Z",
            order_id="o1",
            symbol="BTCUSDT",
            details={"price": 50000.0},
        )
        assert event.details["price"] == 50000.0


class TestProvenanceEventType:
    """Tests for ProvenanceEventType enum."""

    def test_all_types_exist(self) -> None:
        expected = [
            "CONNECTOR_INIT",
            "ORDER_PLACED",
            "ORDER_FILLED",
            "ORDER_PARTIAL",
            "ORDER_REJECTED",
            "ORDER_CANCELLED",
            "ORDER_CANCEL_FAILED",
            "TP_SL_ATTACHED",
            "TP_SL_ATTACH_FAILED",
            "PRICE_FETCHED",
            "BALANCE_FETCHED",
            "HEALTH_CHECK",
            "ERROR",
        ]
        for name in expected:
            assert hasattr(ProvenanceEventType, name), f"Missing {name}"


# ===========================================================================
# DemoProvenance Tests
# ===========================================================================


class TestDemoProvenance:
    """Tests for DemoProvenance dataclass."""

    def test_creation(self) -> None:
        p = DemoProvenance(
            is_demo=True,
            endpoint="https://api-testnet.bybit.com",
            api_key_prefix="DEMO:c775e7b757ed",  # hashed version of "DEMO1234567890"
            timestamp="2025-01-01T00:00:00Z",
        )
        assert p.is_demo is True
        assert p.endpoint == "https://api-testnet.bybit.com"
        assert p.api_key_prefix == "DEMO:c775e7b757ed"


# ===========================================================================
# BybitDemoConnector Tests
# ===========================================================================


class TestBybitDemoConnectorInit:
    """Tests for BybitDemoConnector initialization."""

    @pytest.fixture
    def mock_safety(self) -> MagicMock:
        with patch("data.exchange.bybit_safety.validate_endpoint_url") as mock_validate:
            yield mock_validate

    def test_init_demo_mode(self, mock_safety: MagicMock) -> None:
        connector = _make_mock_connector(demo=True)
        mock_safety.return_value = None
        demo = BybitDemoConnector(connector)
        assert demo.is_demo_mode() is True
        assert demo.provenance.endpoint == "https://api-testnet.bybit.com"
        assert demo.provenance.api_key_prefix == "DEMO:c775e7b757ed"
        assert demo.provenance_tracker.event_count == 1
        init_event = demo.provenance_tracker.get_events()[0]
        assert init_event.event_type == ProvenanceEventType.CONNECTOR_INIT

    def test_init_rejects_production(self) -> None:
        connector = _make_mock_connector(demo=False)
        with pytest.raises(ValueError, match="demo mode"):
            BybitDemoConnector(connector)

    def test_init_security_exception(self) -> None:
        connector = _make_mock_connector(demo=True)
        with patch(
            "data.exchange.bybit_safety.validate_endpoint_url",
            side_effect=Exception("bad endpoint"),
        ):
            with patch(
                "execution.connectors.bybit_demo_connector.SecurityException",
                create=True,
            ) as mock_sec:
                # We need the actual import path.
                pass
        # Simpler approach: directly raise from the imported module.
        from data.exchange.bybit_safety import SecurityException

        connector2 = _make_mock_connector(demo=True)
        with patch(
            "data.exchange.bybit_safety.validate_endpoint_url",
            side_effect=SecurityException("bad endpoint"),
        ):
            with pytest.raises(SecurityException):
                BybitDemoConnector(connector2)

    def test_init_with_retry_config(self, mock_safety: MagicMock) -> None:
        connector = _make_mock_connector(demo=True)
        mock_safety.return_value = None
        retry_config = RetryConfig(max_retries=5, base_delay=2.0)
        demo = BybitDemoConnector(connector, retry_config=retry_config)
        assert demo._retry_config.max_retries == 5
        assert demo._retry_config.base_delay == 2.0

    def test_init_with_market_data(self, mock_safety: MagicMock) -> None:
        connector = _make_mock_connector(demo=True)
        mock_safety.return_value = None
        md = _make_market_data()
        demo = BybitDemoConnector(connector, market_data=md)
        assert demo.market_data is md


class TestBybitDemoConnectorNormalizeSymbol:
    """Tests for symbol normalization."""

    def test_basic_symbol(self) -> None:
        assert BybitDemoConnector._normalize_bybit_symbol("BTCUSDT") == "BTCUSDT"

    def test_lowercase(self) -> None:
        assert BybitDemoConnector._normalize_bybit_symbol("btcusdt") == "BTCUSDT"

    def test_with_slash(self) -> None:
        assert BybitDemoConnector._normalize_bybit_symbol("BTC/USDT") == "BTCUSDT"

    def test_with_dash(self) -> None:
        assert BybitDemoConnector._normalize_bybit_symbol("BTC-USDT") == "BTCUSDT"

    def test_with_colon(self) -> None:
        assert BybitDemoConnector._normalize_bybit_symbol("BTC:USDT") == "BTCUSDT"

    def test_whitespace(self) -> None:
        assert BybitDemoConnector._normalize_bybit_symbol("  BTCUSDT  ") == "BTCUSDT"


class TestBybitDemoConnectorEnsureConnected:
    """Tests for _ensure_connected."""

    @pytest.fixture
    def demo_connector(self) -> BybitDemoConnector:
        with patch(
            "data.exchange.bybit_safety.validate_endpoint_url",
            return_value=None,
        ):
            connector = _make_mock_connector(demo=True)
            return BybitDemoConnector(connector)

    @pytest.mark.asyncio
    async def test_already_connected(self, demo_connector: BybitDemoConnector) -> None:
        demo_connector.connector._session.closed = False
        # Should not call connect.
        await demo_connector._ensure_connected()
        demo_connector.connector.connect.assert_not_called()

    @pytest.mark.asyncio
    async def test_session_none_triggers_connect(
        self, demo_connector: BybitDemoConnector
    ) -> None:
        demo_connector.connector._session = None
        demo_connector.connector.connect = AsyncMock()
        await demo_connector._ensure_connected()
        demo_connector.connector.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_session_closed_triggers_connect(
        self, demo_connector: BybitDemoConnector
    ) -> None:
        demo_connector.connector._session.closed = True
        demo_connector.connector.connect = AsyncMock()
        await demo_connector._ensure_connected()
        demo_connector.connector.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_failure_raises_connector_error(
        self, demo_connector: BybitDemoConnector
    ) -> None:
        demo_connector.connector._session = None
        demo_connector.connector.connect = AsyncMock(
            side_effect=ConnectionError("refused")
        )
        with pytest.raises(BybitConnectorError, match="Cannot establish"):
            await demo_connector._ensure_connected()


class TestBybitDemoConnectorGetMarketPrice:
    """Tests for get_market_price."""

    @pytest.fixture
    def demo_connector(self) -> BybitDemoConnector:
        with patch(
            "data.exchange.bybit_safety.validate_endpoint_url",
            return_value=None,
        ):
            connector = _make_mock_connector(demo=True)
            md = _make_market_data()
            return BybitDemoConnector(connector, market_data=md)

    @pytest.mark.asyncio
    async def test_success(self, demo_connector: BybitDemoConnector) -> None:
        demo_connector.connector.get_ticker = AsyncMock(
            return_value={
                "result": {"list": [{"lastPrice": "50000.50"}]},
            }
        )
        price = await demo_connector.get_market_price("BTCUSDT")
        assert price == 50000.50
        demo_connector.market_data.set_price.assert_any_call("BTCUSDT", 50000.50)
        demo_connector.market_data.set_price.assert_any_call("BTCUSDT", 50000.50)

    @pytest.mark.asyncio
    async def test_no_price(self, demo_connector: BybitDemoConnector) -> None:
        demo_connector.connector.get_ticker = AsyncMock(
            return_value={"result": {"list": [{}]}},
        )
        price = await demo_connector.get_market_price("BTCUSDT")
        assert price is None

    @pytest.mark.asyncio
    async def test_zero_price(self, demo_connector: BybitDemoConnector) -> None:
        demo_connector.connector.get_ticker = AsyncMock(
            return_value={"result": {"list": [{"lastPrice": "0"}]}},
        )
        price = await demo_connector.get_market_price("BTCUSDT")
        assert price is None

    @pytest.mark.asyncio
    async def test_negative_price(self, demo_connector: BybitDemoConnector) -> None:
        demo_connector.connector.get_ticker = AsyncMock(
            return_value={"result": {"list": [{"lastPrice": "-1"}]}},
        )
        price = await demo_connector.get_market_price("BTCUSDT")
        assert price is None

    @pytest.mark.asyncio
    async def test_retryable_error_retries(
        self, demo_connector: BybitDemoConnector
    ) -> None:
        demo_connector.connector.get_ticker = AsyncMock(
            side_effect=[
                BybitNetworkError("timeout"),
                {"result": {"list": [{"lastPrice": "50000.50"}]}},
            ]
        )
        with patch("asyncio.sleep", new_callable=AsyncMock):
            price = await demo_connector.get_market_price("BTCUSDT")
        assert price == 50000.50

    @pytest.mark.asyncio
    async def test_non_retryable_error_returns_none(
        self, demo_connector: BybitDemoConnector
    ) -> None:
        demo_connector.connector.get_ticker = AsyncMock(
            side_effect=BybitAuthenticationError("bad key"),
        )
        price = await demo_connector.get_market_price("BTCUSDT")
        assert price is None

    @pytest.mark.asyncio
    async def test_generic_error_returns_none(
        self, demo_connector: BybitDemoConnector
    ) -> None:
        demo_connector.connector.get_ticker = AsyncMock(
            side_effect=RuntimeError("unexpected"),
        )
        price = await demo_connector.get_market_price("BTCUSDT")
        assert price is None

    @pytest.mark.asyncio
    async def test_provenance_recorded_on_success(
        self, demo_connector: BybitDemoConnector
    ) -> None:
        demo_connector.connector.get_ticker = AsyncMock(
            return_value={"result": {"list": [{"lastPrice": "50000.50"}]}},
        )
        await demo_connector.get_market_price("BTCUSDT")
        events = demo_connector.provenance_tracker.get_events(
            event_type=ProvenanceEventType.PRICE_FETCHED,
        )
        assert len(events) == 1
        assert events[0].symbol == "BTCUSDT"

    @pytest.mark.asyncio
    async def test_provenance_recorded_on_error(
        self, demo_connector: BybitDemoConnector
    ) -> None:
        demo_connector.connector.get_ticker = AsyncMock(
            side_effect=BybitNetworkError("timeout"),
        )
        await demo_connector.get_market_price("BTCUSDT")
        error_events = demo_connector.provenance_tracker.get_events(
            event_type=ProvenanceEventType.ERROR,
        )
        assert len(error_events) >= 1

    @pytest.mark.asyncio
    async def test_no_market_data_provider(self) -> None:
        with patch(
            "data.exchange.bybit_safety.validate_endpoint_url",
            return_value=None,
        ):
            connector = _make_mock_connector(demo=True)
            demo = BybitDemoConnector(connector, market_data=None)
            demo.connector.get_ticker = AsyncMock(
                return_value={"result": {"list": [{"lastPrice": "50000.50"}]}},
            )
            price = await demo.get_market_price("BTCUSDT")
            assert price == 50000.50


class TestBybitDemoConnectorPlaceOrder:
    """Tests for place_order."""

    @pytest.fixture
    def demo_connector(self) -> BybitDemoConnector:
        with patch(
            "data.exchange.bybit_safety.validate_endpoint_url",
            return_value=None,
        ):
            connector = _make_mock_connector(demo=True)
            md = _make_market_data()
            return BybitDemoConnector(connector, market_data=md)

    @pytest.mark.asyncio
    async def test_place_market_order_success(
        self, demo_connector: BybitDemoConnector
    ) -> None:
        demo_connector.connector.place_order = AsyncMock(
            return_value={
                "order_id": "bybit_order_123",
                "status": "Filled",
                "price": "50000.50",
            }
        )
        order = await demo_connector.place_order(
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=0.001,
        )
        assert order.order_id == "bybit_order_123"
        assert order.state == OrderState.FILLED
        assert len(order.fills) == 1
        assert order.fills[0].price == 50000.50
        assert demo_connector.get_order("bybit_order_123") is order

    @pytest.mark.asyncio
    async def test_place_pending_order(
        self, demo_connector: BybitDemoConnector
    ) -> None:
        demo_connector.connector.place_order = AsyncMock(
            return_value={
                "order_id": "bybit_order_456",
                "status": "Created",
            }
        )
        order = await demo_connector.place_order(
            symbol="BTCUSDT",
            side="sell",
            order_type="limit",
            quantity=0.001,
            price=55000.0,
        )
        assert order.state == OrderState.PENDING
        assert len(order.fills) == 0

    @pytest.mark.asyncio
    async def test_place_order_with_tp_sl(
        self, demo_connector: BybitDemoConnector
    ) -> None:
        demo_connector.connector.place_order = AsyncMock(
            return_value={
                "order_id": "bybit_order_789",
                "status": "Filled",
                "price": "50000.50",
            }
        )
        demo_connector.connector.set_trading_stop = AsyncMock()
        order = await demo_connector.place_order(
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=0.001,
            take_profit=55000.0,
            stop_loss=48000.0,
        )
        assert order.metadata.get("venue_take_profit") == 55000.0
        assert order.metadata.get("venue_stop_loss") == 48000.0
        demo_connector.connector.set_trading_stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_place_order_invalid_tp_discarded(
        self, demo_connector: BybitDemoConnector
    ) -> None:
        demo_connector.connector.place_order = AsyncMock(
            return_value={
                "order_id": "bybit_order_999",
                "status": "Filled",
                "price": "50000.50",
            }
        )
        order = await demo_connector.place_order(
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=0.001,
            take_profit=40000.0,  # Below entry for buy - should be discarded
        )
        assert order.metadata.get("venue_take_profit") is None

    @pytest.mark.asyncio
    async def test_place_order_api_error_returns_rejected(
        self, demo_connector: BybitDemoConnector
    ) -> None:
        demo_connector.connector.place_order = AsyncMock(
            side_effect=BybitOrderError(
                "Insufficient balance",
                error_code="110006",
            )
        )
        order = await demo_connector.place_order(
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=0.001,
        )
        assert order.state == OrderState.REJECTED
        assert "Insufficient balance" in (order.reject_reason or "")

    @pytest.mark.asyncio
    async def test_place_order_generic_error_returns_rejected(
        self, demo_connector: BybitDemoConnector
    ) -> None:
        demo_connector.connector.place_order = AsyncMock(
            side_effect=RuntimeError("unexpected"),
        )
        order = await demo_connector.place_order(
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=0.001,
        )
        assert order.state == OrderState.REJECTED

    @pytest.mark.asyncio
    async def test_place_order_provenance(
        self, demo_connector: BybitDemoConnector
    ) -> None:
        demo_connector.connector.place_order = AsyncMock(
            return_value={
                "order_id": "bybit_order_prov",
                "status": "Filled",
                "price": "50000.50",
            }
        )
        await demo_connector.place_order(
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=0.001,
        )
        placed = demo_connector.provenance_tracker.get_events(
            event_type=ProvenanceEventType.ORDER_PLACED,
        )
        assert len(placed) == 1
        filled = demo_connector.provenance_tracker.get_events(
            event_type=ProvenanceEventType.ORDER_FILLED,
        )
        assert len(filled) == 1

    @pytest.mark.asyncio
    async def test_place_market_order_uses_ioc_tif(
        self, demo_connector: BybitDemoConnector
    ) -> None:
        """MARKET orders must use IOC time_in_force for Bybit V5 linear."""
        demo_connector.connector.place_order = AsyncMock(
            return_value={
                "order_id": "bybit_order_mkt",
                "status": "Filled",
                "price": "50000.50",
            }
        )
        await demo_connector.place_order(
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=0.001,
        )
        demo_connector.connector.place_order.assert_awaited_once()
        call_kwargs = demo_connector.connector.place_order.call_args.kwargs
        assert call_kwargs["time_in_force"] == "IOC"

    @pytest.mark.asyncio
    async def test_place_limit_order_uses_gtc_tif(
        self, demo_connector: BybitDemoConnector
    ) -> None:
        """LIMIT orders use GTC time_in_force."""
        demo_connector.connector.place_order = AsyncMock(
            return_value={
                "order_id": "bybit_order_lim",
                "status": "Created",
            }
        )
        await demo_connector.place_order(
            symbol="BTCUSDT",
            side="sell",
            order_type="limit",
            quantity=0.001,
            price=55000.0,
        )
        demo_connector.connector.place_order.assert_awaited_once()
        call_kwargs = demo_connector.connector.place_order.call_args.kwargs
        assert call_kwargs["time_in_force"] == "GTC"

    @pytest.mark.asyncio
    async def test_place_order_rejected_provenance(
        self, demo_connector: BybitDemoConnector
    ) -> None:
        demo_connector.connector.place_order = AsyncMock(
            side_effect=BybitAuthenticationError("bad key"),
        )
        order = await demo_connector.place_order(
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=0.001,
        )
        rejected = demo_connector.provenance_tracker.get_events(
            event_type=ProvenanceEventType.ORDER_REJECTED,
        )
        assert len(rejected) == 1
        assert rejected[0].order_id == order.order_id


class TestBybitDemoConnectorCancelOrder:
    """Tests for cancel_order."""

    @pytest.fixture
    def demo_connector(self) -> BybitDemoConnector:
        with patch(
            "data.exchange.bybit_safety.validate_endpoint_url",
            return_value=None,
        ):
            connector = _make_mock_connector(demo=True)
            return BybitDemoConnector(connector)

    @pytest.mark.asyncio
    async def test_cancel_success(self, demo_connector: BybitDemoConnector) -> None:
        # Pre-populate an order.
        order = PaperOrder(
            order_id="o1",
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=0.001,
        )
        demo_connector._orders["o1"] = order

        demo_connector.connector.cancel_order = AsyncMock()
        with patch("data.exchange.bybit_safety.audit_log_order_operation"):
            result = await demo_connector.cancel_order("o1")
        assert result is True
        assert order.state == OrderState.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_not_found(self, demo_connector: BybitDemoConnector) -> None:
        result = await demo_connector.cancel_order("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_api_error(self, demo_connector: BybitDemoConnector) -> None:
        order = PaperOrder(
            order_id="o2",
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=0.001,
        )
        demo_connector._orders["o2"] = order

        demo_connector.connector.cancel_order = AsyncMock(
            side_effect=BybitOrderError("not found", error_code="13004"),
        )
        with patch("data.exchange.bybit_safety.audit_log_order_operation"):
            result = await demo_connector.cancel_order("o2")
        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_generic_error(
        self, demo_connector: BybitDemoConnector
    ) -> None:
        order = PaperOrder(
            order_id="o3",
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=0.001,
        )
        demo_connector._orders["o3"] = order

        demo_connector.connector.cancel_order = AsyncMock(
            side_effect=RuntimeError("unexpected"),
        )
        with patch("data.exchange.bybit_safety.audit_log_order_operation"):
            result = await demo_connector.cancel_order("o3")
        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_provenance(self, demo_connector: BybitDemoConnector) -> None:
        order = PaperOrder(
            order_id="o4",
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=0.001,
        )
        demo_connector._orders["o4"] = order

        demo_connector.connector.cancel_order = AsyncMock()
        with patch("data.exchange.bybit_safety.audit_log_order_operation"):
            await demo_connector.cancel_order("o4")

        cancelled = demo_connector.provenance_tracker.get_events(
            event_type=ProvenanceEventType.ORDER_CANCELLED,
        )
        assert len(cancelled) == 1


class TestBybitDemoConnectorGetOrders:
    """Tests for get_orders and get_order."""

    @pytest.fixture
    def demo_connector(self) -> BybitDemoConnector:
        with patch(
            "data.exchange.bybit_safety.validate_endpoint_url",
            return_value=None,
        ):
            connector = _make_mock_connector(demo=True)
            dc = BybitDemoConnector(connector)
            # Add some orders.
            o1 = PaperOrder(
                order_id="o1",
                symbol="BTCUSDT",
                side="buy",
                order_type="market",
                quantity=0.001,
            )
            o1.state = OrderState.FILLED
            o2 = PaperOrder(
                order_id="o2",
                symbol="ETHUSDT",
                side="sell",
                order_type="limit",
                quantity=1.0,
                price=3000.0,
            )
            o2.state = OrderState.PENDING
            o3 = PaperOrder(
                order_id="o3",
                symbol="BTCUSDT",
                side="sell",
                order_type="market",
                quantity=0.002,
            )
            o3.state = OrderState.PENDING
            dc._orders = {"o1": o1, "o2": o2, "o3": o3}
            return dc

    def test_get_order_found(self, demo_connector: BybitDemoConnector) -> None:
        order = demo_connector.get_order("o1")
        assert order is not None
        assert order.order_id == "o1"

    def test_get_order_not_found(self, demo_connector: BybitDemoConnector) -> None:
        assert demo_connector.get_order("nonexistent") is None

    def test_get_orders_all(self, demo_connector: BybitDemoConnector) -> None:
        orders = demo_connector.get_orders()
        assert len(orders) == 3

    def test_get_orders_filter_symbol(self, demo_connector: BybitDemoConnector) -> None:
        orders = demo_connector.get_orders(symbol="BTCUSDT")
        assert len(orders) == 2

    def test_get_orders_filter_state(self, demo_connector: BybitDemoConnector) -> None:
        orders = demo_connector.get_orders(state=OrderState.FILLED)
        assert len(orders) == 1
        assert orders[0].order_id == "o1"

    def test_get_orders_filter_side(self, demo_connector: BybitDemoConnector) -> None:
        orders = demo_connector.get_orders(side="sell")
        assert len(orders) == 2

    def test_get_orders_combined_filters(
        self, demo_connector: BybitDemoConnector
    ) -> None:
        orders = demo_connector.get_orders(
            symbol="BTCUSDT",
            state=OrderState.PENDING,
        )
        assert len(orders) == 1
        assert orders[0].order_id == "o3"


class TestBybitDemoConnectorGetPosition:
    """Tests for get_position."""

    @pytest.fixture
    def demo_connector(self) -> BybitDemoConnector:
        with patch(
            "data.exchange.bybit_safety.validate_endpoint_url",
            return_value=None,
        ):
            connector = _make_mock_connector(demo=True)
            dc = BybitDemoConnector(connector)
            return dc

    def test_empty_position(self, demo_connector: BybitDemoConnector) -> None:
        pos = demo_connector.get_position("BTCUSDT")
        assert pos["quantity"] == 0.0
        assert pos["avg_entry_price"] == 0.0

    def test_long_position(self, demo_connector: BybitDemoConnector) -> None:
        fill = PaperFill(
            fill_id="f1",
            order_id="o1",
            symbol="BTCUSDT",
            side="buy",
            price=50000.0,
            quantity=0.001,
        )
        order = PaperOrder(
            order_id="o1",
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=0.001,
        )
        order.add_fill(fill)
        order.state = OrderState.FILLED
        demo_connector._orders["o1"] = order

        pos = demo_connector.get_position("BTCUSDT")
        assert pos["quantity"] == 0.001
        assert pos["avg_entry_price"] == 50000.0

    def test_net_position(self, demo_connector: BybitDemoConnector) -> None:
        buy_fill = PaperFill(
            fill_id="f1",
            order_id="o1",
            symbol="BTCUSDT",
            side="buy",
            price=50000.0,
            quantity=0.002,
        )
        buy_order = PaperOrder(
            order_id="o1",
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=0.002,
        )
        buy_order.add_fill(buy_fill)
        buy_order.state = OrderState.FILLED

        sell_fill = PaperFill(
            fill_id="f2",
            order_id="o2",
            symbol="BTCUSDT",
            side="sell",
            price=51000.0,
            quantity=0.001,
        )
        sell_order = PaperOrder(
            order_id="o2",
            symbol="BTCUSDT",
            side="sell",
            order_type="market",
            quantity=0.001,
        )
        sell_order.add_fill(sell_fill)
        sell_order.state = OrderState.FILLED

        demo_connector._orders = {"o1": buy_order, "o2": sell_order}

        pos = demo_connector.get_position("BTCUSDT")
        assert pos["quantity"] == 0.001
        assert pos["total_filled"] == 0.003


class TestBybitDemoConnectorWalletBalance:
    """Tests for get_wallet_balance."""

    @pytest.fixture
    def demo_connector(self) -> BybitDemoConnector:
        with patch(
            "data.exchange.bybit_safety.validate_endpoint_url",
            return_value=None,
        ):
            connector = _make_mock_connector(demo=True)
            return BybitDemoConnector(connector)

    @pytest.mark.asyncio
    async def test_success(self, demo_connector: BybitDemoConnector) -> None:
        demo_connector.connector.get_wallet_balance = AsyncMock(
            return_value={
                "total_equity": 10000.0,
                "available_balance": 9000.0,
                "unrealized_pnl": 500.0,
            }
        )
        balance = await demo_connector.get_wallet_balance()
        assert balance["total_equity"] == 10000.0
        assert balance["available_balance"] == 9000.0

    @pytest.mark.asyncio
    async def test_api_error_raised(self, demo_connector: BybitDemoConnector) -> None:
        demo_connector.connector.get_wallet_balance = AsyncMock(
            side_effect=BybitRateLimitError(),
        )
        with pytest.raises(BybitRateLimitError):
            await demo_connector.get_wallet_balance()

    @pytest.mark.asyncio
    async def test_generic_error_raised(
        self, demo_connector: BybitDemoConnector
    ) -> None:
        demo_connector.connector.get_wallet_balance = AsyncMock(
            side_effect=RuntimeError("unexpected"),
        )
        with pytest.raises(RuntimeError):
            await demo_connector.get_wallet_balance()

    @pytest.mark.asyncio
    async def test_provenance_recorded(
        self, demo_connector: BybitDemoConnector
    ) -> None:
        demo_connector.connector.get_wallet_balance = AsyncMock(
            return_value={
                "total_equity": 10000.0,
                "available_balance": 9000.0,
                "unrealized_pnl": 500.0,
            }
        )
        await demo_connector.get_wallet_balance()
        events = demo_connector.provenance_tracker.get_events(
            event_type=ProvenanceEventType.BALANCE_FETCHED,
        )
        assert len(events) == 1


class TestBybitDemoConnectorHealthCheck:
    """Tests for health_check."""

    @pytest.fixture
    def demo_connector(self) -> BybitDemoConnector:
        with patch(
            "data.exchange.bybit_safety.validate_endpoint_url",
            return_value=None,
        ):
            connector = _make_mock_connector(demo=True)
            return BybitDemoConnector(connector)

    @pytest.mark.asyncio
    async def test_healthy(self, demo_connector: BybitDemoConnector) -> None:
        demo_connector.connector.health_check = AsyncMock(
            return_value={"healthy": True, "api_accessible": True},
        )
        result = await demo_connector.health_check()
        assert result["healthy"] is True
        assert result["demo_mode"] is True
        assert result["endpoint"] == "https://api-testnet.bybit.com"
        assert "provenance" in result

    @pytest.mark.asyncio
    async def test_unhealthy(self, demo_connector: BybitDemoConnector) -> None:
        demo_connector.connector.health_check = AsyncMock(
            return_value={"healthy": False, "api_accessible": False},
        )
        result = await demo_connector.health_check()
        assert result["healthy"] is False

    @pytest.mark.asyncio
    async def test_error_returns_unhealthy(
        self, demo_connector: BybitDemoConnector
    ) -> None:
        demo_connector.connector.health_check = AsyncMock(
            side_effect=RuntimeError("connection failed"),
        )
        result = await demo_connector.health_check()
        assert result["healthy"] is False
        assert "error" in result


class TestBybitDemoConnectorClose:
    """Tests for close."""

    @pytest.mark.asyncio
    async def test_close(self) -> None:
        with patch(
            "data.exchange.bybit_safety.validate_endpoint_url",
            return_value=None,
        ):
            connector = _make_mock_connector(demo=True)
            connector.close = AsyncMock()
            demo = BybitDemoConnector(connector)
            await demo.close()
            connector.close.assert_called_once()


class TestBybitDemoConnectorSanitizeTradingStops:
    """Tests for _sanitize_trading_stops."""

    @pytest.fixture
    def demo_connector(self) -> BybitDemoConnector:
        with patch(
            "data.exchange.bybit_safety.validate_endpoint_url",
            return_value=None,
        ):
            connector = _make_mock_connector(demo=True)
            return BybitDemoConnector(connector)

    def test_valid_long_tp_sl(self, demo_connector: BybitDemoConnector) -> None:
        tp, sl = demo_connector._sanitize_trading_stops(
            side="buy",
            reference_price=50000.0,
            take_profit=55000.0,
            stop_loss=48000.0,
        )
        assert tp == 55000.0
        assert sl == 48000.0

    def test_valid_short_tp_sl(self, demo_connector: BybitDemoConnector) -> None:
        tp, sl = demo_connector._sanitize_trading_stops(
            side="sell",
            reference_price=50000.0,
            take_profit=45000.0,
            stop_loss=52000.0,
        )
        assert tp == 45000.0
        assert sl == 52000.0

    def test_invalid_long_tp_below_ref(
        self, demo_connector: BybitDemoConnector
    ) -> None:
        tp, sl = demo_connector._sanitize_trading_stops(
            side="buy",
            reference_price=50000.0,
            take_profit=49000.0,
            stop_loss=48000.0,
        )
        assert tp is None  # Discarded: TP <= ref for buy
        assert sl == 48000.0

    def test_invalid_long_sl_above_ref(
        self, demo_connector: BybitDemoConnector
    ) -> None:
        tp, sl = demo_connector._sanitize_trading_stops(
            side="buy",
            reference_price=50000.0,
            take_profit=55000.0,
            stop_loss=51000.0,
        )
        assert tp == 55000.0
        assert sl is None  # Discarded: SL >= ref for buy

    def test_invalid_short_tp_above_ref(
        self, demo_connector: BybitDemoConnector
    ) -> None:
        tp, sl = demo_connector._sanitize_trading_stops(
            side="sell",
            reference_price=50000.0,
            take_profit=51000.0,
            stop_loss=52000.0,
        )
        assert tp is None  # Discarded: TP >= ref for sell
        assert sl == 52000.0

    def test_invalid_short_sl_below_ref(
        self, demo_connector: BybitDemoConnector
    ) -> None:
        tp, sl = demo_connector._sanitize_trading_stops(
            side="sell",
            reference_price=50000.0,
            take_profit=45000.0,
            stop_loss=48000.0,
        )
        assert tp == 45000.0
        assert sl is None  # Discarded: SL <= ref for sell

    def test_zero_reference_price(self, demo_connector: BybitDemoConnector) -> None:
        tp, sl = demo_connector._sanitize_trading_stops(
            side="buy",
            reference_price=0.0,
            take_profit=55000.0,
            stop_loss=48000.0,
        )
        assert tp == 55000.0
        assert sl == 48000.0

    def test_none_tp_sl(self, demo_connector: BybitDemoConnector) -> None:
        tp, sl = demo_connector._sanitize_trading_stops(
            side="buy",
            reference_price=50000.0,
            take_profit=None,
            stop_loss=None,
        )
        assert tp is None
        assert sl is None

    def test_negative_tp_sl(self, demo_connector: BybitDemoConnector) -> None:
        tp, sl = demo_connector._sanitize_trading_stops(
            side="buy",
            reference_price=50000.0,
            take_profit=-100.0,
            stop_loss=-200.0,
        )
        assert tp is None
        assert sl is None

    def test_max_distance_clipping(self, demo_connector: BybitDemoConnector) -> None:
        with patch.dict(os.environ, {"BYBIT_TP_MAX_DISTANCE_PCT": "0.10"}):
            tp, sl = demo_connector._sanitize_trading_stops(
                side="buy",
                reference_price=50000.0,
                take_profit=60000.0,  # 20% away, should be clipped to 10%
                stop_loss=48000.0,
            )
            assert math.isclose(tp, 55000.0)  # 50000 * 1.10


class TestBybitDemoConnectorAttachTradingStops:
    """Tests for _attach_trading_stops_with_retry."""

    @pytest.fixture
    def demo_connector(self) -> BybitDemoConnector:
        with patch(
            "data.exchange.bybit_safety.validate_endpoint_url",
            return_value=None,
        ):
            connector = _make_mock_connector(demo=True)
            rc = RetryConfig(max_retries=3, base_delay=0.1)
            return BybitDemoConnector(connector, retry_config=rc)

    @pytest.mark.asyncio
    async def test_success_first_try(self, demo_connector: BybitDemoConnector) -> None:
        demo_connector.connector.set_trading_stop = AsyncMock()
        await demo_connector._attach_trading_stops_with_retry(
            symbol="BTCUSDT",
            order_id="o1",
            take_profit=55000.0,
            stop_loss=48000.0,
        )
        demo_connector.connector.set_trading_stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_retry_then_success(self, demo_connector: BybitDemoConnector) -> None:
        demo_connector.connector.set_trading_stop = AsyncMock(
            side_effect=[RuntimeError("fail"), None],
        )
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await demo_connector._attach_trading_stops_with_retry(
                symbol="BTCUSDT",
                order_id="o1",
                take_profit=55000.0,
                stop_loss=48000.0,
            )
        assert demo_connector.connector.set_trading_stop.call_count == 2

    @pytest.mark.asyncio
    async def test_all_retries_fail(self, demo_connector: BybitDemoConnector) -> None:
        demo_connector.connector.set_trading_stop = AsyncMock(
            side_effect=RuntimeError("persistent fail"),
        )
        with patch("asyncio.sleep", new_callable=AsyncMock):
            with patch(
                "execution.incident_reporter.publish_execution_incident",
                new_callable=AsyncMock,
            ):
                await demo_connector._attach_trading_stops_with_retry(
                    symbol="BTCUSDT",
                    order_id="o1",
                    take_profit=55000.0,
                    stop_loss=48000.0,
                )
        assert demo_connector.connector.set_trading_stop.call_count == 3

    @pytest.mark.asyncio
    async def test_provenance_on_success(
        self, demo_connector: BybitDemoConnector
    ) -> None:
        demo_connector.connector.set_trading_stop = AsyncMock()
        await demo_connector._attach_trading_stops_with_retry(
            symbol="BTCUSDT",
            order_id="o1",
            take_profit=55000.0,
            stop_loss=48000.0,
        )
        events = demo_connector.provenance_tracker.get_events(
            event_type=ProvenanceEventType.TP_SL_ATTACHED,
        )
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_provenance_on_failure(
        self, demo_connector: BybitDemoConnector
    ) -> None:
        demo_connector.connector.set_trading_stop = AsyncMock(
            side_effect=RuntimeError("persistent fail"),
        )
        with patch("asyncio.sleep", new_callable=AsyncMock):
            with patch(
                "execution.incident_reporter.publish_execution_incident",
                new_callable=AsyncMock,
            ):
                await demo_connector._attach_trading_stops_with_retry(
                    symbol="BTCUSDT",
                    order_id="o1",
                    take_profit=55000.0,
                    stop_loss=48000.0,
                )
        events = demo_connector.provenance_tracker.get_events(
            event_type=ProvenanceEventType.TP_SL_ATTACH_FAILED,
        )
        assert len(events) == 1


class TestBybitDemoConnectorExtractApiError:
    """Tests for _extract_api_error."""

    @pytest.fixture
    def demo_connector(self) -> BybitDemoConnector:
        with patch(
            "data.exchange.bybit_safety.validate_endpoint_url",
            return_value=None,
        ):
            connector = _make_mock_connector(demo=True)
            return BybitDemoConnector(connector)

    def test_extract_from_response_dict(
        self, demo_connector: BybitDemoConnector
    ) -> None:
        exc = MagicMock()
        exc.response = {"retCode": 110006, "retMsg": "Insufficient balance"}
        err = demo_connector._extract_api_error(exc)
        assert err is not None
        assert isinstance(err, BybitOrderError)

    def test_extract_from_body_dict(self, demo_connector: BybitDemoConnector) -> None:
        exc = MagicMock()
        exc.response = None
        exc.body = {"retCode": 10006, "retMsg": "Invalid API key"}
        err = demo_connector._extract_api_error(exc)
        assert err is not None
        assert isinstance(err, BybitAuthenticationError)

    def test_no_structured_data(self, demo_connector: BybitDemoConnector) -> None:
        exc = RuntimeError("plain error")
        err = demo_connector._extract_api_error(exc)
        assert err is None


# ===========================================================================
# BybitDemoConnectorFactory Tests
# ===========================================================================


class TestBybitDemoConnectorFactory:
    """Tests for BybitDemoConnectorFactory."""

    def test_has_demo_credentials_true(self) -> None:
        with patch.dict(os.environ, {"BYBIT_DEMO_API_KEY": "test_key"}):
            assert BybitDemoConnectorFactory.has_demo_credentials() is True

    def test_has_demo_credentials_false(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            assert BybitDemoConnectorFactory.has_demo_credentials() is False

    @pytest.mark.asyncio
    async def test_create_demo_success(self) -> None:
        with patch.dict(os.environ, {"BYBIT_DEMO_API_KEY": "DEMO1234567890"}):
            with patch(
                "data.exchange.bybit_safety.validate_endpoint_url",
                return_value=None,
            ):
                with patch(
                    "data.exchange.bybit_connector.BybitConfig"
                ) as mock_config_cls:
                    config = MagicMock()
                    config.demo = True
                    config.base_url = "https://api-testnet.bybit.com"
                    config.private_ws_url = (
                        "wss://stream-testnet.bybit.com/ws/v5/private"
                    )
                    config.api_key = "DEMO1234567890"
                    mock_config_cls.from_env.return_value = config

                    with patch(
                        "data.exchange.bybit_connector.BybitConnector"
                    ) as mock_conn_cls:
                        mock_conn = MagicMock()
                        mock_conn.config = config
                        mock_conn._session = MagicMock()
                        mock_conn._session.closed = False
                        mock_conn_cls.return_value = mock_conn

                        result = BybitDemoConnectorFactory.create()
                        assert isinstance(result, BybitDemoConnector)

    def test_create_fallback_to_simulator(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with patch("execution.paper.order_simulator.OrderSimulator") as mock_sim:
                mock_sim.return_value = MagicMock()
                result = BybitDemoConnectorFactory.create()
                mock_sim.assert_called_once()

    def test_create_prefer_simulator(self) -> None:
        with patch("execution.paper.order_simulator.OrderSimulator") as mock_sim:
            mock_sim.return_value = MagicMock()
            result = BybitDemoConnectorFactory.create(prefer_demo=False)
            mock_sim.assert_called_once()


class TestCreateBybitDemoConnector:
    """Tests for create_bybit_demo_connector convenience function."""

    def test_delegates_to_from_env(self) -> None:
        with patch(
            "execution.connectors.bybit_demo_connector.BybitDemoConnector.from_env"
        ) as mock_from_env:
            mock_from_env.return_value = MagicMock()
            create_bybit_demo_connector()
            mock_from_env.assert_called_once()


# ===========================================================================
# Fill Polling Tests (ST-FILL-001)
# ===========================================================================


class TestBybitDemoConnectorFillPolling:
    """Tests for fill polling functionality."""

    @pytest.fixture
    def demo_connector(self) -> BybitDemoConnector:
        with patch(
            "data.exchange.bybit_safety.validate_endpoint_url",
            return_value=None,
        ):
            connector = _make_mock_connector(demo=True)
            md = _make_market_data()
            # Create connector with a mock Redis client
            mock_redis = MagicMock()
            mock_redis.exists.return_value = False
            dc = BybitDemoConnector(connector, market_data=md, redis_client=mock_redis)
            return dc

    @pytest.mark.asyncio
    async def test_poll_for_fill_detects_async_fill(
        self, demo_connector: BybitDemoConnector
    ) -> None:
        """Test that _poll_for_fill correctly detects and processes an async fill."""
        order_id = "bybit_order_async_123"
        symbol = "BTCUSDT"

        # Pre-populate order as PENDING
        order = PaperOrder(
            order_id=order_id,
            symbol=symbol.upper(),
            side="buy",
            order_type="market",
            quantity=0.001,
        )
        order.state = OrderState.PENDING
        demo_connector._orders[order_id] = order

        # Mock get_fills to return empty then fill
        demo_connector.connector.get_fills = AsyncMock(
            side_effect=[
                {"list": []},  # First poll: no fills yet
                {  # Second poll: fill detected
                    "list": [
                        {
                            "execId": "exec_123",
                            "execPrice": "50000.50",
                            "execQty": "0.001",
                        }
                    ]
                },
            ]
        )

        result = await demo_connector._poll_for_fill(
            order_id=order_id,
            symbol=symbol,
            initial_response={"order_id": order_id},
        )

        assert result.state == OrderState.FILLED
        assert len(result.fills) == 1
        assert result.fills[0].price == 50000.50
        assert result.fills[0].quantity == 0.001

    @pytest.mark.asyncio
    async def test_poll_for_fill_timeout_returns_pending(
        self, demo_connector: BybitDemoConnector
    ) -> None:
        """Test that _poll_for_fill returns PENDING state on timeout."""
        order_id = "bybit_order_timeout_456"
        symbol = "ETHUSDT"

        # Pre-populate order as PENDING
        order = PaperOrder(
            order_id=order_id,
            symbol=symbol.upper(),
            side="sell",
            order_type="market",
            quantity=1.0,
        )
        order.state = OrderState.PENDING
        demo_connector._orders[order_id] = order

        # Mock get_fills to always return empty list (timeout scenario)
        demo_connector.connector.get_fills = AsyncMock(return_value={"list": []})

        # Set a short timeout via env var for testing
        with patch.dict(os.environ, {"BYBIT_FILL_POLL_TIMEOUT_MS": "200"}):
            result = await demo_connector._poll_for_fill(
                order_id=order_id,
                symbol=symbol,
                initial_response={"order_id": order_id},
            )

        # Should timeout and return order still in PENDING state
        assert result.state == OrderState.PENDING
        assert len(result.fills) == 0

    @pytest.mark.asyncio
    async def test_poll_for_fill_idempotency_skips_duplicate_exec(
        self, demo_connector: BybitDemoConnector
    ) -> None:
        """Test that _poll_for_fill skips already-processed executions."""
        order_id = "bybit_order_dedup_789"
        symbol = "BTCUSDT"

        # Pre-populate order as PENDING
        order = PaperOrder(
            order_id=order_id,
            symbol=symbol.upper(),
            side="buy",
            order_type="market",
            quantity=0.001,
        )
        order.state = OrderState.PENDING
        demo_connector._orders[order_id] = order

        # Mock Redis to say the exec is already processed
        demo_connector._redis.exists.return_value = True
        demo_connector.connector.get_fills = AsyncMock(
            return_value={
                "list": [
                    {
                        "execId": "exec_already_seen",
                        "execPrice": "50000.50",
                        "execQty": "0.001",
                    }
                ]
            }
        )

        result = await demo_connector._poll_for_fill(
            order_id=order_id,
            symbol=symbol,
            initial_response={"order_id": order_id},
        )

        # Should not have processed the duplicate
        assert result.state == OrderState.PENDING
        assert len(result.fills) == 0

    @pytest.mark.asyncio
    async def test_place_order_polls_for_pending_market_order(
        self, demo_connector: BybitDemoConnector
    ) -> None:
        """Test that place_order calls _poll_for_fill for PENDING market orders."""
        # Mock place_order to return Created (PENDING) status
        demo_connector.connector.place_order = AsyncMock(
            return_value={
                "order_id": "bybit_order_market_001",
                "status": "Created",
            }
        )

        # Mock get_fills to return a fill
        demo_connector.connector.get_fills = AsyncMock(
            return_value={
                "list": [
                    {
                        "execId": "exec_market_fill",
                        "execPrice": "50000.00",
                        "execQty": "0.001",
                    }
                ]
            }
        )
        demo_connector.connector.set_trading_stop = AsyncMock()

        with patch("data.exchange.bybit_safety.audit_log_order_operation"):
            order = await demo_connector.place_order(
                symbol="BTCUSDT",
                side="buy",
                order_type="market",
                quantity=0.001,
            )

        # Order should be FILLED after polling
        assert order.state == OrderState.FILLED
        assert len(order.fills) == 1

    @pytest.mark.asyncio
    async def test_place_order_no_poll_when_immediately_filled(
        self, demo_connector: BybitDemoConnector
    ) -> None:
        """Test that place_order does NOT poll when order is immediately filled."""
        # Mock place_order to return Filled status
        demo_connector.connector.place_order = AsyncMock(
            return_value={
                "order_id": "bybit_order_filled_002",
                "status": "Filled",
                "price": "50000.00",
            }
        )

        # Mock market data for fill price fallback
        demo_connector.market_data.get_price.return_value = 50000.00

        # This should NOT call get_fills since already filled
        demo_connector.connector.get_fills = AsyncMock()

        with patch("data.exchange.bybit_safety.audit_log_order_operation"):
            order = await demo_connector.place_order(
                symbol="BTCUSDT",
                side="buy",
                order_type="market",
                quantity=0.001,
            )

        # Order should be FILLED immediately
        assert order.state == OrderState.FILLED
        # get_fills should NOT have been called
        demo_connector.connector.get_fills.assert_not_called()


class TestBybitDemoConnectorDedupMethods:
    """Tests for Redis deduplication methods."""

    @pytest.fixture
    def demo_connector(self) -> BybitDemoConnector:
        with patch(
            "data.exchange.bybit_safety.validate_endpoint_url",
            return_value=None,
        ):
            connector = _make_mock_connector(demo=True)
            mock_redis = MagicMock()
            return BybitDemoConnector(connector, redis_client=mock_redis)

    @pytest.mark.asyncio
    async def test_is_duplicate_exec_returns_true_when_exists(
        self, demo_connector: BybitDemoConnector
    ) -> None:
        """Test _is_duplicate_exec returns True when Redis key exists."""
        demo_connector._redis.exists.return_value = True
        result = await demo_connector._is_duplicate_exec("exec_123")
        assert result is True
        demo_connector._redis.exists.assert_called_once_with(
            "bybit:fill:dedup:exec:exec_123"
        )

    @pytest.mark.asyncio
    async def test_is_duplicate_exec_returns_false_when_not_exists(
        self, demo_connector: BybitDemoConnector
    ) -> None:
        """Test _is_duplicate_exec returns False when Redis key doesn't exist."""
        demo_connector._redis.exists.return_value = False
        result = await demo_connector._is_duplicate_exec("exec_456")
        assert result is False

    @pytest.mark.asyncio
    async def test_is_duplicate_exec_returns_false_when_no_redis(
        self, demo_connector: BybitDemoConnector
    ) -> None:
        """Test _is_duplicate_exec returns False when Redis client is None."""
        demo_connector._redis = None
        result = await demo_connector._is_duplicate_exec("exec_789")
        assert result is False

    @pytest.mark.asyncio
    async def test_mark_processed_exec_sets_key_with_ttl(
        self, demo_connector: BybitDemoConnector
    ) -> None:
        """Test _mark_processed_exec sets Redis key with correct TTL."""
        await demo_connector._mark_processed_exec("exec_abc")
        demo_connector._redis.setex.assert_called_once()
        call_args = demo_connector._redis.setex.call_args
        assert call_args[0][0] == "bybit:fill:dedup:exec:exec_abc"
        assert call_args[0][1] == 24 * 3600  # 24 hours in seconds

    @pytest.mark.asyncio
    async def test_mark_processed_exec_handles_redis_error(
        self, demo_connector: BybitDemoConnector
    ) -> None:
        """Test _mark_processed_exec handles Redis errors gracefully."""
        demo_connector._redis.setex.side_effect = Exception("Redis error")
        # Should not raise
        await demo_connector._mark_processed_exec("exec_error")


class TestBybitDemoConnectorPartialFillAccumulation:
    """Tests for partial fill accumulation during polling (ST-FILL-001)."""

    @pytest.fixture
    def demo_connector(self) -> BybitDemoConnector:
        with patch(
            "data.exchange.bybit_safety.validate_endpoint_url",
            return_value=None,
        ):
            connector = _make_mock_connector(demo=True)
            md = _make_market_data()
            mock_redis = MagicMock()
            mock_redis.exists.return_value = False
            dc = BybitDemoConnector(connector, market_data=md, redis_client=mock_redis)
            return dc

    @pytest.mark.asyncio
    async def test_partial_fill_accumulation_80_percent(
        self, demo_connector: BybitDemoConnector
    ) -> None:
        """Test partial fills accumulate correctly (first 40%, second 40% = 80%).

        Verifies:
        1. First partial fill (40%) updates filled_quantity and state to PARTIAL
        2. Second partial fill (40%) adds to existing fills, total = 80%
        3. Order remains PARTIAL until fully filled
        4. avg_fill_price is weighted average
        """
        order_id = "bybit_order_partial_123"
        symbol = "BTCUSDT"

        # Pre-populate order as PENDING
        order = PaperOrder(
            order_id=order_id,
            symbol=symbol.upper(),
            side="buy",
            order_type="market",
            quantity=1.0,  # Total quantity
        )
        order.state = OrderState.PENDING
        demo_connector._orders[order_id] = order

        # Track call count to return different responses
        call_count = {"count": 0}

        async def mock_get_fills(**kwargs):
            call_count["count"] += 1
            if call_count["count"] == 1:
                # First poll: partial fill (40%)
                return {
                    "list": [
                        {
                            "execId": "exec_partial_1",
                            "execPrice": "50000.00",
                            "execQty": "0.4",
                        }
                    ]
                }
            elif call_count["count"] == 2:
                # Second poll: another partial fill (40% more, total 80%)
                return {
                    "list": [
                        {
                            "execId": "exec_partial_2",
                            "execPrice": "50100.00",
                            "execQty": "0.4",
                        }
                    ]
                }
            else:
                # Subsequent polls: empty (order still PARTIAL, will timeout)
                return {"list": []}

        demo_connector.connector.get_fills = mock_get_fills

        # Set a short timeout to avoid long test
        with patch.dict(os.environ, {"BYBIT_FILL_POLL_TIMEOUT_MS": "500"}):
            result = await demo_connector._poll_for_fill(
                order_id=order_id,
                symbol=symbol,
                initial_response={"order_id": order_id},
            )

        # After two partial fills, should have 80% filled
        assert result.filled_quantity == pytest.approx(0.8), "Should have 0.8 filled"
        assert result.remaining_quantity == pytest.approx(
            0.2
        ), "Should have 0.2 remaining"
        assert result.state == OrderState.PARTIAL, "Should be PARTIAL (not yet filled)"

        # Should have 2 fills accumulated
        assert len(result.fills) == 2, "Should have 2 fills"

        # Verify fill details
        assert result.fills[0].quantity == 0.4
        assert result.fills[0].price == 50000.00
        assert result.fills[1].quantity == 0.4
        assert result.fills[1].price == 50100.00

        # Verify weighted average price
        expected_avg = (0.4 * 50000.0 + 0.4 * 50100.0) / 0.8
        assert result.avg_fill_price == pytest.approx(
            expected_avg
        ), f"Avg price should be {expected_avg}, got {result.avg_fill_price}"

        # Verify PARTIAL state provenance events were recorded
        # (One for each polling cycle where fills were detected)
        partial_events = demo_connector.provenance_tracker.get_events(
            event_type=ProvenanceEventType.ORDER_PARTIAL,
        )
        assert (
            len(partial_events) == 2
        ), f"Should have recorded 2 PARTIAL events (one per fill), got {len(partial_events)}"
        # Verify the details of the most recent PARTIAL event (partial_events[0] is most recent)
        # The most recent PARTIAL event should show 0.8 filled (after second fill was added)
        most_recent_partial = partial_events[0]
        assert most_recent_partial.order_id == order_id
        assert most_recent_partial.details["details"]["total_filled_qty"] == 0.8

    @pytest.mark.asyncio
    async def test_partial_fill_then_complete(
        self, demo_connector: BybitDemoConnector
    ) -> None:
        """Test partial fills accumulate then complete to FILLED state.

        Verifies:
        1. First partial fill (40%) -> PARTIAL state
        2. Second partial fill (40%) -> PARTIAL state continues
        3. Final fill (20%) -> FILLED state, polling stops
        """
        order_id = "bybit_order_complete_456"
        symbol = "BTCUSDT"

        # Pre-populate order
        order = PaperOrder(
            order_id=order_id,
            symbol=symbol.upper(),
            side="buy",
            order_type="market",
            quantity=1.0,
        )
        order.state = OrderState.PENDING
        demo_connector._orders[order_id] = order

        # Mock get_fills to return partial then complete
        demo_connector.connector.get_fills = AsyncMock(
            side_effect=[
                # First poll: partial fill (40%)
                {
                    "list": [
                        {
                            "execId": "exec_complete_1",
                            "execPrice": "50000.00",
                            "execQty": "0.4",
                        }
                    ]
                },
                # Second poll: another partial (40%, total 80%)
                {
                    "list": [
                        {
                            "execId": "exec_complete_2",
                            "execPrice": "50100.00",
                            "execQty": "0.4",
                        }
                    ]
                },
                # Third poll: final fill (20%, total 100%)
                {
                    "list": [
                        {
                            "execId": "exec_complete_3",
                            "execPrice": "50200.00",
                            "execQty": "0.2",
                        }
                    ]
                },
            ]
        )

        with patch.dict(os.environ, {"BYBIT_FILL_POLL_TIMEOUT_MS": "5000"}):
            result = await demo_connector._poll_for_fill(
                order_id=order_id,
                symbol=symbol,
                initial_response={"order_id": order_id},
            )

        # Should be fully filled
        assert result.filled_quantity == pytest.approx(1.0), "Should be fully filled"
        assert result.remaining_quantity == pytest.approx(
            0.0
        ), "Should have nothing remaining"
        assert result.state == OrderState.FILLED, "Should be FILLED"
        assert result.filled_at is not None, "filled_at should be set"

        # Should have all 3 fills
        assert len(result.fills) == 3, "Should have 3 fills"

        # Verify FILLED provenance event
        filled_events = demo_connector.provenance_tracker.get_events(
            event_type=ProvenanceEventType.ORDER_FILLED,
        )
        assert len(filled_events) == 1, "Should have recorded FILLED state"

    @pytest.mark.asyncio
    async def test_missing_exec_id_uses_composite_dedup_key(
        self, demo_connector: BybitDemoConnector
    ) -> None:
        """Test that missing execId falls back to composite dedup key.

        When Bybit doesn't return execId, the connector should:
        1. Use a composite key (order_id:price:qty:time) for deduplication
        2. Still process the fill correctly
        3. Log a warning about missing execId
        """
        order_id = "bybit_order_no_execid_789"
        symbol = "BTCUSDT"

        # Pre-populate order
        order = PaperOrder(
            order_id=order_id,
            symbol=symbol.upper(),
            side="buy",
            order_type="market",
            quantity=0.001,
        )
        order.state = OrderState.PENDING
        demo_connector._orders[order_id] = order

        # Mock get_fills to return fill WITHOUT execId
        demo_connector.connector.get_fills = AsyncMock(
            return_value={
                "list": [
                    {
                        # No execId!
                        "execPrice": "50000.00",
                        "execQty": "0.001",
                        "execTime": "1709654321000",
                    }
                ]
            }
        )

        result = await demo_connector._poll_for_fill(
            order_id=order_id,
            symbol=symbol,
            initial_response={"order_id": order_id},
        )

        # Should still process the fill using composite dedup key
        assert result.state == OrderState.FILLED
        assert len(result.fills) == 1
        assert result.fills[0].price == 50000.00
        assert result.fills[0].quantity == 0.001

    @pytest.mark.asyncio
    async def test_idempotent_fill_same_exec_not_duplicated(
        self, demo_connector: BybitDemoConnector
    ) -> None:
        """Test that the same execution is not recorded twice (idempotency).

        When the same execId appears in multiple polling results:
        1. First occurrence is processed and recorded
        2. Second occurrence is skipped (duplicate)
        3. Only one fill exists in the order
        """
        order_id = "bybit_order_idempotent_101"
        symbol = "BTCUSDT"

        # Pre-populate order
        order = PaperOrder(
            order_id=order_id,
            symbol=symbol.upper(),
            side="buy",
            order_type="market",
            quantity=0.001,
        )
        order.state = OrderState.PENDING
        demo_connector._orders[order_id] = order

        # Mock Redis to track the exec_id as already processed
        async def mock_exists(key: str) -> int:
            if "exec_duplicate_123" in key:
                return 1  # Already processed
            return 0

        demo_connector._redis.exists = AsyncMock(side_effect=mock_exists)

        # Mock get_fills to return the same fill twice
        demo_connector.connector.get_fills = AsyncMock(
            return_value={
                "list": [
                    {
                        "execId": "exec_duplicate_123",
                        "execPrice": "50000.00",
                        "execQty": "0.001",
                    }
                ]
            }
        )

        result = await demo_connector._poll_for_fill(
            order_id=order_id,
            symbol=symbol,
            initial_response={"order_id": order_id},
        )

        # Should not have processed the duplicate
        assert (
            result.state == OrderState.PENDING
        ), "Should remain PENDING (no fill added)"
        assert len(result.fills) == 0, "Duplicate fill should not be recorded"

    @pytest.mark.asyncio
    async def test_invalid_price_qty_fill_skipped(
        self, demo_connector: BybitDemoConnector
    ) -> None:
        """Test that fills with invalid price or qty are skipped."""
        order_id = "bybit_order_invalid_202"
        symbol = "BTCUSDT"

        # Pre-populate order
        order = PaperOrder(
            order_id=order_id,
            symbol=symbol.upper(),
            side="buy",
            order_type="market",
            quantity=0.001,
        )
        order.state = OrderState.PENDING
        demo_connector._orders[order_id] = order

        # Mock get_fills to return fill with zero qty
        demo_connector.connector.get_fills = AsyncMock(
            return_value={
                "list": [
                    {
                        "execId": "exec_zero_qty",
                        "execPrice": "50000.00",
                        "execQty": "0.0",  # Invalid!
                    }
                ]
            }
        )

        result = await demo_connector._poll_for_fill(
            order_id=order_id,
            symbol=symbol,
            initial_response={"order_id": order_id},
        )

        # Fill with zero qty should be skipped
        assert result.state == OrderState.PENDING
        assert len(result.fills) == 0
