"""Unit tests for position sizing integration and API."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

from portfolio_risk.position_sizing import (
    KellyInputs,
    SizingConfig,
    SizingMethod,
    VolatilityInputs,
)
from portfolio_risk.position_sizing.api import (
    PositionSizingAPI,
    create_position_sizing_routes,
)
from portfolio_risk.position_sizing.integration import (
    PortfolioExposure,
    PositionSizingCache,
    PositionSizingIntegration,
    SizingRecommendation,
)


class TestPortfolioExposure:
    """Tests for PortfolioExposure dataclass."""

    def test_exposure_from_portfolio_state(self) -> None:
        """Test creating exposure from portfolio state."""
        # Create mock portfolio state
        mock_state = Mock()
        mock_state.total_equity = 10000.0
        mock_state.available_equity = 8000.0
        mock_state.margin_used = 2000.0

        # Create mock positions
        mock_pos1 = Mock()
        mock_pos1.is_open = True
        mock_pos1.token = "BTC"
        mock_pos1.notional_value = 5000.0

        mock_pos2 = Mock()
        mock_pos2.is_open = True
        mock_pos2.token = "ETH"
        mock_pos2.notional_value = 3000.0

        mock_state.positions = {"pos1": mock_pos1, "pos2": mock_pos2}
        mock_state.get_open_positions.return_value = [mock_pos1, mock_pos2]

        exposure = PortfolioExposure.from_portfolio_state(mock_state)

        assert exposure.total_equity == 10000.0
        assert exposure.available_equity == 8000.0
        assert exposure.margin_used == 2000.0
        assert exposure.total_exposure_usd == 8000.0  # 5000 + 3000
        assert exposure.exposure_pct == 80.0  # 8000 / 10000 * 100
        assert exposure.open_position_count == 2
        assert exposure.positions_by_token["BTC"] == 5000.0
        assert exposure.positions_by_token["ETH"] == 3000.0

    def test_exposure_with_zero_equity(self) -> None:
        """Test exposure calculation with zero equity."""
        mock_state = Mock()
        mock_state.total_equity = 0.0
        mock_state.available_equity = 0.0
        mock_state.margin_used = 0.0
        mock_state.positions = {}
        mock_state.get_open_positions.return_value = []

        exposure = PortfolioExposure.from_portfolio_state(mock_state)

        assert exposure.exposure_pct == 0.0
        assert exposure.total_exposure_usd == 0.0


class TestPositionSizingIntegration:
    """Tests for PositionSizingIntegration."""

    def test_init_without_tracker(self) -> None:
        """Test initialization without portfolio tracker."""
        integration = PositionSizingIntegration()

        assert integration.portfolio_tracker is None
        assert integration.default_method == SizingMethod.FIXED_FRACTIONAL

    def test_init_with_tracker(self) -> None:
        """Test initialization with portfolio tracker."""
        mock_tracker = Mock()
        mock_tracker.state.total_equity = 10000.0

        integration = PositionSizingIntegration(portfolio_tracker=mock_tracker)

        assert integration.portfolio_tracker == mock_tracker
        assert integration._last_portfolio_equity == 10000.0

    def test_set_portfolio_tracker(self) -> None:
        """Test setting portfolio tracker."""
        integration = PositionSizingIntegration()
        mock_tracker = Mock()
        mock_tracker.state.total_equity = 15000.0

        integration.set_portfolio_tracker(mock_tracker)

        assert integration.portfolio_tracker == mock_tracker
        assert integration._last_portfolio_equity == 15000.0

    def test_get_portfolio_exposure_with_tracker(self) -> None:
        """Test getting exposure with tracker."""
        mock_tracker = Mock()
        mock_tracker.state.total_equity = 10000.0
        mock_tracker.state.available_equity = 8000.0
        mock_tracker.state.margin_used = 2000.0
        mock_tracker.state.positions = {}
        mock_tracker.state.get_open_positions.return_value = []

        integration = PositionSizingIntegration(portfolio_tracker=mock_tracker)
        exposure = integration.get_portfolio_exposure()

        assert exposure is not None
        assert exposure.total_equity == 10000.0

    def test_get_portfolio_exposure_without_tracker(self) -> None:
        """Test getting exposure without tracker."""
        integration = PositionSizingIntegration()
        exposure = integration.get_portfolio_exposure()

        assert exposure is None

    def test_should_recalculate_no_tracker(self) -> None:
        """Test should_recalculate with no tracker."""
        integration = PositionSizingIntegration()
        assert integration.should_recalculate() is False

    def test_should_recalculate_first_time(self) -> None:
        """Test should_recalculate on first sizing."""
        mock_tracker = Mock()
        mock_tracker.state.total_equity = 10000.0

        integration = PositionSizingIntegration(portfolio_tracker=mock_tracker)
        # First calculation - equity was set during init, so should return False
        # until equity changes
        assert integration.should_recalculate() is False
        # After resetting to 0, should return True
        integration._last_portfolio_equity = 0
        assert integration.should_recalculate() is True

    def test_should_recalculate_threshold_met(self) -> None:
        """Test should_recalculate when threshold is met."""
        mock_tracker = Mock()
        mock_tracker.state.total_equity = 10000.0

        integration = PositionSizingIntegration(portfolio_tracker=mock_tracker)
        integration._last_portfolio_equity = 10000.0

        # Change equity by 6% (above 5% threshold)
        mock_tracker.state.total_equity = 10600.0

        assert integration.should_recalculate() is True

    def test_should_recalculate_threshold_not_met(self) -> None:
        """Test should_recalculate when threshold is not met."""
        mock_tracker = Mock()
        mock_tracker.state.total_equity = 10000.0

        integration = PositionSizingIntegration(portfolio_tracker=mock_tracker)
        integration._last_portfolio_equity = 10000.0

        # Change equity by 3% (below 5% threshold)
        mock_tracker.state.total_equity = 10300.0

        assert integration.should_recalculate() is False

    def test_calculate_sizing_without_tracker(self) -> None:
        """Test calculate_sizing without portfolio tracker."""
        integration = PositionSizingIntegration()

        sizing = integration.calculate_sizing(
            token="BTC",
            direction="long",
            entry_price=100.0,
            stop_loss_price=95.0,
        )

        assert sizing.token == "BTC"
        assert sizing.direction == "long"
        assert sizing.entry_price == 100.0
        assert sizing.stop_loss_price == 95.0
        assert sizing.position_size > 0
        assert sizing.total_equity == 10000.0  # Default fallback

    def test_calculate_sizing_with_tracker(self) -> None:
        """Test calculate_sizing with portfolio tracker."""
        mock_tracker = Mock()
        mock_tracker.state.total_equity = 50000.0
        mock_tracker.state.available_equity = 40000.0
        mock_tracker.state.margin_used = 10000.0
        mock_tracker.state.positions = {}
        mock_tracker.state.get_open_positions.return_value = []

        integration = PositionSizingIntegration(portfolio_tracker=mock_tracker)

        sizing = integration.calculate_sizing(
            token="BTC",
            direction="long",
            entry_price=100.0,
            stop_loss_price=95.0,
        )

        assert sizing.total_equity == 50000.0
        assert sizing.available_equity == 40000.0

    def test_calculate_sizing_risk_adjustment_high_exposure(self) -> None:
        """Test risk adjustment with high portfolio exposure."""
        mock_tracker = Mock()
        mock_tracker.state.total_equity = 10000.0
        mock_tracker.state.available_equity = 1000.0  # 90% exposed

        # Create mock positions for high exposure
        mock_pos = Mock()
        mock_pos.is_open = True
        mock_pos.notional_value = 9000.0
        mock_tracker.state.positions = {"pos1": mock_pos}
        mock_tracker.state.get_open_positions.return_value = [mock_pos]

        integration = PositionSizingIntegration(
            portfolio_tracker=mock_tracker,
            config=SizingConfig(default_risk_pct=1.0),
        )

        sizing = integration.calculate_sizing(
            token="BTC",
            direction="long",
            entry_price=100.0,
            stop_loss_price=95.0,
        )

        # Risk should be reduced by 50% due to high exposure (>80%)
        assert sizing.risk_percent <= 0.6  # 1.0 * 0.5 = 0.5, with some rounding

    def test_calculate_sizing_risk_adjustment_medium_exposure(self) -> None:
        """Test risk adjustment with medium portfolio exposure."""
        mock_tracker = Mock()
        mock_tracker.state.total_equity = 10000.0
        mock_tracker.state.available_equity = 3000.0  # 70% exposed

        mock_pos = Mock()
        mock_pos.is_open = True
        mock_pos.notional_value = 7000.0
        mock_tracker.state.positions = {"pos1": mock_pos}
        mock_tracker.state.get_open_positions.return_value = [mock_pos]

        integration = PositionSizingIntegration(
            portfolio_tracker=mock_tracker,
            config=SizingConfig(default_risk_pct=1.0),
        )

        sizing = integration.calculate_sizing(
            token="BTC",
            direction="long",
            entry_price=100.0,
            stop_loss_price=95.0,
        )

        # Risk should be reduced by 25% due to medium exposure (50-80%)
        assert sizing.risk_percent <= 0.8  # 1.0 * 0.75 = 0.75

    def test_calculate_sizing_with_kelly_method(self) -> None:
        """Test calculate_sizing with Kelly Criterion method."""
        integration = PositionSizingIntegration(
            default_method=SizingMethod.KELLY_CRITERION,
        )

        kelly_inputs = KellyInputs(win_probability=0.6, win_loss_ratio=2.0)

        sizing = integration.calculate_sizing(
            token="BTC",
            direction="long",
            entry_price=100.0,
            stop_loss_price=95.0,
            kelly_inputs=kelly_inputs,
        )

        assert sizing.sizing_method == SizingMethod.KELLY_CRITERION
        assert sizing.position_size > 0

    def test_calculate_sizing_with_volatility_method(self) -> None:
        """Test calculate_sizing with volatility-based method."""
        integration = PositionSizingIntegration(
            default_method=SizingMethod.VOLATILITY_BASED,
        )

        vol_inputs = VolatilityInputs(atr_value=2.0, atr_multiplier=2.0)

        sizing = integration.calculate_sizing(
            token="BTC",
            direction="long",
            entry_price=100.0,
            stop_loss_price=95.0,
            volatility_inputs=vol_inputs,
        )

        assert sizing.sizing_method == SizingMethod.VOLATILITY_BASED
        assert sizing.position_size > 0

    def test_calculate_sizing_for_signal(self) -> None:
        """Test calculate_sizing_for_signal."""

        from signal_generation.models import Signal, SignalDirection, SignalStatus

        integration = PositionSizingIntegration()

        signal = Signal(
            signal_id="test-signal-1",
            token="BTC",
            direction=SignalDirection.LONG,
            confidence=0.8,
            base_score=75.0,
            timeframe="1h",
            timestamp=datetime.now(UTC),
            status=SignalStatus.LOGGED_ONLY,
        )

        sizing = integration.calculate_sizing_for_signal(
            signal=signal,
            entry_price=100.0,
            stop_loss_price=95.0,
        )

        assert sizing.signal_id == "test-signal-1"
        assert sizing.token == "BTC"
        assert sizing.direction == "long"

    def test_sizing_recommendation_to_dict(self) -> None:
        """Test SizingRecommendation to_dict method."""
        sizing = SizingRecommendation(
            signal_id="test-1",
            token="BTC",
            direction="long",
            entry_price=100.0,
            stop_loss_price=95.0,
            position_size=2.0,
            notional_value=200.0,
            risk_amount_usd=10.0,
            risk_percent=1.0,
            sizing_method=SizingMethod.FIXED_FRACTIONAL,
            leverage_used=1.0,
            max_position_check=True,
            portfolio_exposure_pct=20.0,
            available_equity=8000.0,
            total_equity=10000.0,
        )

        data = sizing.to_dict()

        assert data["signal_id"] == "test-1"
        assert data["token"] == "BTC"
        assert data["direction"] == "long"
        assert data["sizing_method"] == "FIXED_FRACTIONAL"
        assert data["max_position_check"] is True


class TestPositionSizingCache:
    """Tests for PositionSizingCache."""

    def test_cache_and_retrieve(self) -> None:
        """Test caching and retrieving sizing."""
        integration = PositionSizingIntegration()
        cache = PositionSizingCache(integration)

        sizing = SizingRecommendation(
            signal_id="test-1",
            token="BTC",
            direction="long",
            entry_price=100.0,
            stop_loss_price=95.0,
            position_size=2.0,
            notional_value=200.0,
            risk_amount_usd=10.0,
            risk_percent=1.0,
            sizing_method=SizingMethod.FIXED_FRACTIONAL,
            leverage_used=1.0,
            max_position_check=True,
            portfolio_exposure_pct=20.0,
            available_equity=8000.0,
            total_equity=10000.0,
        )

        cache.cache_sizing("key1", sizing)
        retrieved = cache.get_cached_sizing("key1", Mock(), 100.0, 95.0)

        assert retrieved is not None
        assert retrieved.signal_id == "test-1"

    def test_cache_miss(self) -> None:
        """Test cache miss."""
        integration = PositionSizingIntegration()
        cache = PositionSizingCache(integration)

        retrieved = cache.get_cached_sizing("nonexistent", Mock(), 100.0, 95.0)

        assert retrieved is None

    def test_cache_invalidation_on_equity_change(self) -> None:
        """Test cache invalidation when portfolio equity changes."""
        mock_tracker = Mock()
        mock_tracker.state.total_equity = 10000.0

        integration = PositionSizingIntegration(portfolio_tracker=mock_tracker)
        cache = PositionSizingCache(integration)

        sizing = SizingRecommendation(
            signal_id="test-1",
            token="BTC",
            direction="long",
            entry_price=100.0,
            stop_loss_price=95.0,
            position_size=2.0,
            notional_value=200.0,
            risk_amount_usd=10.0,
            risk_percent=1.0,
            sizing_method=SizingMethod.FIXED_FRACTIONAL,
            leverage_used=1.0,
            max_position_check=True,
            portfolio_exposure_pct=20.0,
            available_equity=8000.0,
            total_equity=10000.0,
        )

        cache.cache_sizing("key1", sizing)

        # Change equity by 6% (above threshold)
        mock_tracker.state.total_equity = 10600.0

        retrieved = cache.get_cached_sizing("key1", Mock(), 100.0, 95.0)

        assert retrieved is None  # Cache invalidated

    def test_explicit_invalidate(self) -> None:
        """Test explicit cache invalidation."""
        integration = PositionSizingIntegration()
        cache = PositionSizingCache(integration)

        sizing = SizingRecommendation(
            signal_id="test-1",
            token="BTC",
            direction="long",
            entry_price=100.0,
            stop_loss_price=95.0,
            position_size=2.0,
            notional_value=200.0,
            risk_amount_usd=10.0,
            risk_percent=1.0,
            sizing_method=SizingMethod.FIXED_FRACTIONAL,
            leverage_used=1.0,
            max_position_check=True,
            portfolio_exposure_pct=20.0,
            available_equity=8000.0,
            total_equity=10000.0,
        )

        cache.cache_sizing("key1", sizing)
        cache.invalidate("key1")

        retrieved = cache.get_cached_sizing("key1", Mock(), 100.0, 95.0)
        assert retrieved is None

    def test_invalidate_all(self) -> None:
        """Test invalidating all cache entries."""
        integration = PositionSizingIntegration()
        cache = PositionSizingCache(integration)

        sizing = SizingRecommendation(
            signal_id="test-1",
            token="BTC",
            direction="long",
            entry_price=100.0,
            stop_loss_price=95.0,
            position_size=2.0,
            notional_value=200.0,
            risk_amount_usd=10.0,
            risk_percent=1.0,
            sizing_method=SizingMethod.FIXED_FRACTIONAL,
            leverage_used=1.0,
            max_position_check=True,
            portfolio_exposure_pct=20.0,
            available_equity=8000.0,
            total_equity=10000.0,
        )

        cache.cache_sizing("key1", sizing)
        cache.cache_sizing("key2", sizing)
        cache.invalidate_all()

        assert cache.get_cached_sizing("key1", Mock(), 100.0, 95.0) is None
        assert cache.get_cached_sizing("key2", Mock(), 100.0, 95.0) is None

    def test_get_cache_stats(self) -> None:
        """Test getting cache statistics."""
        integration = PositionSizingIntegration()
        cache = PositionSizingCache(integration)

        sizing = SizingRecommendation(
            signal_id="test-1",
            token="BTC",
            direction="long",
            entry_price=100.0,
            stop_loss_price=95.0,
            position_size=2.0,
            notional_value=200.0,
            risk_amount_usd=10.0,
            risk_percent=1.0,
            sizing_method=SizingMethod.FIXED_FRACTIONAL,
            leverage_used=1.0,
            max_position_check=True,
            portfolio_exposure_pct=20.0,
            available_equity=8000.0,
            total_equity=10000.0,
        )

        cache.cache_sizing("key1", sizing)
        cache.cache_sizing("key2", sizing)

        stats = cache.get_cache_stats()

        assert stats["cached_items"] == 2
        assert "key1" in stats["cache_keys"]
        assert "key2" in stats["cache_keys"]


class TestPositionSizingAPI:
    """Tests for PositionSizingAPI."""

    def test_init(self) -> None:
        """Test API initialization."""
        integration = PositionSizingIntegration()
        api = PositionSizingAPI(integration)

        assert api.integration == integration
        assert api.enable_caching is True
        assert api._cache is not None

    def test_init_without_caching(self) -> None:
        """Test API initialization without caching."""
        integration = PositionSizingIntegration()
        api = PositionSizingAPI(integration, enable_caching=False)

        assert api.enable_caching is False
        assert api._cache is None

    def test_calculate_position_size_fixed_fractional(self) -> None:
        """Test calculate_position_size with fixed fractional method."""
        integration = PositionSizingIntegration()
        api = PositionSizingAPI(integration)

        result = api.calculate_position_size(
            token="BTC",
            direction="long",
            entry_price=100.0,
            stop_loss_price=95.0,
            method="fixed_fractional",
            risk_percentage=1.0,
        )

        # API returns sizing dict directly (not wrapped)
        assert result["token"] == "BTC"
        assert result["sizing_method"] == "FIXED_FRACTIONAL"
        assert result["position_size"] > 0

    def test_calculate_position_size_kelly(self) -> None:
        """Test calculate_position_size with Kelly method."""
        integration = PositionSizingIntegration()
        api = PositionSizingAPI(integration)

        result = api.calculate_position_size(
            token="BTC",
            direction="long",
            entry_price=100.0,
            stop_loss_price=95.0,
            method="kelly",
            kelly_win_probability=0.6,
            kelly_win_loss_ratio=2.0,
        )

        # API returns sizing dict directly (not wrapped)
        assert result["sizing_method"] == "KELLY_CRITERION"

    def test_calculate_position_size_kelly_missing_params(self) -> None:
        """Test calculate_position_size with Kelly method missing params."""
        integration = PositionSizingIntegration()
        api = PositionSizingAPI(integration)

        # API raises ValueError for missing params (not wrapped response)
        with pytest.raises(ValueError, match="kelly_win_probability"):
            api.calculate_position_size(
                token="BTC",
                direction="long",
                entry_price=100.0,
                stop_loss_price=95.0,
                method="kelly",
            )

    def test_calculate_position_size_volatility(self) -> None:
        """Test calculate_position_size with volatility method."""
        integration = PositionSizingIntegration()
        api = PositionSizingAPI(integration)

        result = api.calculate_position_size(
            token="BTC",
            direction="long",
            entry_price=100.0,
            stop_loss_price=95.0,
            method="volatility",
            atr_value=2.0,
            atr_multiplier=2.0,
        )

        # API returns sizing dict directly (not wrapped)
        assert result["sizing_method"] == "VOLATILITY_BASED"

    def test_calculate_position_size_invalid_method(self) -> None:
        """Test calculate_position_size with invalid method."""
        integration = PositionSizingIntegration()
        api = PositionSizingAPI(integration)

        # API raises ValueError for invalid method (not wrapped response)
        with pytest.raises(ValueError, match="Unknown sizing method"):
            api.calculate_position_size(
                token="BTC",
                direction="long",
                entry_price=100.0,
                stop_loss_price=95.0,
                method="invalid_method",
            )

    def test_get_portfolio_exposure_with_tracker(self) -> None:
        """Test get_portfolio_exposure with tracker."""
        mock_tracker = Mock()
        mock_tracker.state.total_equity = 10000.0
        mock_tracker.state.available_equity = 8000.0
        mock_tracker.state.margin_used = 2000.0
        mock_tracker.state.positions = {}
        mock_tracker.state.get_open_positions.return_value = []

        integration = PositionSizingIntegration(portfolio_tracker=mock_tracker)
        api = PositionSizingAPI(integration)

        result = api.get_portfolio_exposure()

        assert result is not None
        assert result["total_equity"] == 10000.0

    def test_get_portfolio_exposure_without_tracker(self) -> None:
        """Test get_portfolio_exposure without tracker."""
        integration = PositionSizingIntegration()
        api = PositionSizingAPI(integration)

        result = api.get_portfolio_exposure()

        assert result is None

    def test_should_recalculate(self) -> None:
        """Test should_recalculate."""
        mock_tracker = Mock()
        mock_tracker.state.total_equity = 10600.0

        integration = PositionSizingIntegration(portfolio_tracker=mock_tracker)
        integration._last_portfolio_equity = 10000.0

        api = PositionSizingAPI(integration)

        assert api.should_recalculate() is True

    def test_invalidate_cache(self) -> None:
        """Test invalidate_cache."""
        integration = PositionSizingIntegration()
        api = PositionSizingAPI(integration)

        # Should not raise
        api.invalidate_cache()

    def test_get_cache_stats_with_caching(self) -> None:
        """Test get_cache_stats with caching enabled."""
        integration = PositionSizingIntegration()
        api = PositionSizingAPI(integration, enable_caching=True)

        stats = api.get_cache_stats()

        assert stats["caching_enabled"] is True

    def test_get_cache_stats_without_caching(self) -> None:
        """Test get_cache_stats with caching disabled."""
        integration = PositionSizingIntegration()
        api = PositionSizingAPI(integration, enable_caching=False)

        stats = api.get_cache_stats()

        assert stats["caching_enabled"] is False


class TestCreatePositionSizingRoutes:
    """Tests for create_position_sizing_routes."""

    def test_create_routes(self) -> None:
        """Test route creation."""
        integration = PositionSizingIntegration()
        routes = create_position_sizing_routes(integration)

        assert len(routes) == 6

        paths = [r["path"] for r in routes]
        assert "/api/v1/position-size" in paths
        assert "/api/v1/position-size/signal/{signal_id}" in paths
        assert "/api/v1/position-size/portfolio-exposure" in paths
        assert "/api/v1/position-size/should-recalculate" in paths
        assert "/api/v1/position-size/cache" in paths
        assert "/api/v1/position-size/cache/stats" in paths

    def test_create_routes_with_custom_prefix(self) -> None:
        """Test route creation with custom prefix."""
        integration = PositionSizingIntegration()
        routes = create_position_sizing_routes(integration, prefix="/v2")

        paths = [r["path"] for r in routes]
        assert "/v2/position-size" in paths


class TestRouteHandlers:
    """Tests for route handlers."""

    @pytest.mark.asyncio
    async def test_calculate_handler(self) -> None:
        """Test calculate handler."""
        integration = PositionSizingIntegration()
        api = PositionSizingAPI(integration)

        from portfolio_risk.position_sizing.api import _create_calculate_handler

        handler = _create_calculate_handler(api)

        request = {
            "token": "BTC",
            "direction": "long",
            "entry_price": 100.0,
            "stop_loss_price": 95.0,
            "method": "fixed_fractional",
            "risk_percentage": 1.0,
        }

        result = await handler(request)

        assert result["success"] is True
        assert result["data"]["token"] == "BTC"

    @pytest.mark.asyncio
    async def test_calculate_handler_validation_error(self) -> None:
        """Test calculate handler with validation error."""
        integration = PositionSizingIntegration()
        api = PositionSizingAPI(integration)

        from portfolio_risk.position_sizing.api import _create_calculate_handler

        handler = _create_calculate_handler(api)

        request = {
            "token": "BTC",
            "direction": "long",
            "entry_price": 100.0,
            "stop_loss_price": 95.0,
            "method": "kelly",  # Missing Kelly params
        }

        result = await handler(request)

        assert result["success"] is False
        assert result["error_type"] == "validation_error"

    @pytest.mark.asyncio
    async def test_exposure_handler(self) -> None:
        """Test exposure handler."""
        mock_tracker = Mock()
        mock_tracker.state.total_equity = 10000.0
        mock_tracker.state.available_equity = 8000.0
        mock_tracker.state.margin_used = 2000.0
        mock_tracker.state.positions = {}
        mock_tracker.state.get_open_positions.return_value = []

        integration = PositionSizingIntegration(portfolio_tracker=mock_tracker)
        api = PositionSizingAPI(integration)

        from portfolio_risk.position_sizing.api import _create_exposure_handler

        handler = _create_exposure_handler(api)

        result = await handler()

        assert result["success"] is True
        assert result["data"]["total_equity"] == 10000.0

    @pytest.mark.asyncio
    async def test_exposure_handler_no_tracker(self) -> None:
        """Test exposure handler without tracker."""
        integration = PositionSizingIntegration()
        api = PositionSizingAPI(integration)

        from portfolio_risk.position_sizing.api import _create_exposure_handler

        handler = _create_exposure_handler(api)

        result = await handler()

        assert result["success"] is False
        assert result["error_type"] == "not_available"

    @pytest.mark.asyncio
    async def test_recalculate_handler(self) -> None:
        """Test recalculate check handler."""
        mock_tracker = Mock()
        mock_tracker.state.total_equity = 10600.0

        integration = PositionSizingIntegration(portfolio_tracker=mock_tracker)
        integration._last_portfolio_equity = 10000.0

        api = PositionSizingAPI(integration)

        from portfolio_risk.position_sizing.api import _create_recalculate_check_handler

        handler = _create_recalculate_check_handler(api)

        result = await handler()

        assert result["success"] is True
        assert result["data"]["should_recalculate"] is True
        assert result["data"]["threshold_pct"] == 5.0

    @pytest.mark.asyncio
    async def test_invalidate_cache_handler(self) -> None:
        """Test invalidate cache handler."""
        integration = PositionSizingIntegration()
        api = PositionSizingAPI(integration)

        from portfolio_risk.position_sizing.api import _create_invalidate_cache_handler

        handler = _create_invalidate_cache_handler(api)

        result = await handler()

        assert result["success"] is True
        assert "invalidated" in result["message"]

    @pytest.mark.asyncio
    async def test_cache_stats_handler(self) -> None:
        """Test cache stats handler."""
        integration = PositionSizingIntegration()
        api = PositionSizingAPI(integration)

        from portfolio_risk.position_sizing.api import _create_cache_stats_handler

        handler = _create_cache_stats_handler(api)

        result = await handler()

        assert result["success"] is True
        assert "caching_enabled" in result["data"]
