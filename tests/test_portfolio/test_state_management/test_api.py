"""Tests for portfolio API."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from portfolio.state_management.api import PortfolioAPI, create_portfolio_routes
from portfolio.state_management.models import (
    Balance,
    PortfolioSnapshot,
    PortfolioState,
    Position,
    PositionDirection,
)
from portfolio.state_management.tracker import PortfolioTracker


@pytest.fixture
def mock_tracker():
    """Create a mock portfolio tracker."""
    tracker = MagicMock(spec=PortfolioTracker)
    tracker.portfolio_id = "test-portfolio"
    tracker.state = PortfolioState(portfolio_id="test-portfolio")
    tracker.get_snapshots = AsyncMock(return_value=[])
    return tracker


@pytest.fixture
def api(mock_tracker):
    """Create a PortfolioAPI with mock tracker."""
    return PortfolioAPI(mock_tracker, cache_ttl_ms=1000)


class TestPortfolioAPISummary:
    """Tests for portfolio summary endpoint."""

    def test_get_portfolio_summary(self, api, mock_tracker):
        """Test getting portfolio summary."""
        mock_tracker.state.update_balance("USDT", free=100000.0, locked=20000.0)
        mock_tracker.state.add_position(
            Position(
                position_id="pos-1",
                token="BTC",
                direction=PositionDirection.LONG,
                entry_price=50000.0,
                quantity=1.0,
                current_price=51000.0,
            )
        )

        summary = api.get_portfolio_summary()

        assert summary["portfolio_id"] == "test-portfolio"
        assert summary["total_equity"] == 121000.0  # 120000 + 1000 unrealized
        assert summary["available_equity"] == 70000.0  # 120000 - 50000 margin
        assert summary["open_positions"] == 1


class TestPortfolioAPIPositions:
    """Tests for positions endpoints."""

    def test_get_positions_all(self, api, mock_tracker):
        """Test getting all positions."""
        mock_tracker.state.add_position(
            Position(
                position_id="pos-1",
                token="BTC",
                direction=PositionDirection.LONG,
                entry_price=50000.0,
                quantity=1.0,
                current_price=51000.0,
            )
        )
        mock_tracker.state.add_position(
            Position(
                position_id="pos-2",
                token="ETH",
                direction=PositionDirection.LONG,
                entry_price=3000.0,
                quantity=10.0,
                current_price=3100.0,
            )
        )

        positions = api.get_positions()

        assert len(positions) == 2
        assert positions[0]["token"] in ["BTC", "ETH"]

    def test_get_positions_filtered_by_token(self, api, mock_tracker):
        """Test getting positions filtered by token."""
        mock_tracker.state.add_position(
            Position(
                position_id="pos-1",
                token="BTC",
                direction=PositionDirection.LONG,
                entry_price=50000.0,
                quantity=1.0,
                current_price=51000.0,
            )
        )
        mock_tracker.state.add_position(
            Position(
                position_id="pos-2",
                token="ETH",
                direction=PositionDirection.LONG,
                entry_price=3000.0,
                quantity=10.0,
                current_price=3100.0,
            )
        )

        positions = api.get_positions(token="BTC")

        assert len(positions) == 1
        assert positions[0]["token"] == "BTC"

    def test_get_position_by_id(self, api, mock_tracker):
        """Test getting a specific position."""
        mock_tracker.state.add_position(
            Position(
                position_id="pos-1",
                token="BTC",
                direction=PositionDirection.LONG,
                entry_price=50000.0,
                quantity=1.0,
                current_price=51000.0,
            )
        )

        position = api.get_position("pos-1")

        assert position is not None
        assert position["position_id"] == "pos-1"
        assert position["token"] == "BTC"

    def test_get_position_not_found(self, api, mock_tracker):
        """Test getting a non-existent position."""
        position = api.get_position("non-existent")

        assert position is None


class TestPortfolioAPIBalances:
    """Tests for balances endpoints."""

    def test_get_balances_all(self, api, mock_tracker):
        """Test getting all balances."""
        mock_tracker.state.update_balance("USDT", free=10000.0, locked=2000.0)
        mock_tracker.state.update_balance("BTC", free=1.0, locked=0.5)

        balances = api.get_balances()

        assert len(balances) == 2

    def test_get_balance_by_token(self, api, mock_tracker):
        """Test getting balance for specific token."""
        mock_tracker.state.update_balance("USDT", free=10000.0, locked=2000.0)

        balance = api.get_balances(token="USDT")

        assert balance["token"] == "USDT"
        assert balance["free"] == 10000.0

    def test_get_balance_not_found(self, api, mock_tracker):
        """Test getting balance for token with no balance."""
        balance = api.get_balances(token="XYZ")

        assert balance["token"] == "XYZ"
        assert balance["free"] == 0.0


class TestPortfolioAPIPnL:
    """Tests for PnL endpoints."""

    def test_get_pnl_summary(self, api, mock_tracker):
        """Test getting PnL summary."""
        mock_tracker.state.add_position(
            Position(
                position_id="pos-1",
                token="BTC",
                direction=PositionDirection.LONG,
                entry_price=50000.0,
                quantity=1.0,
                current_price=51000.0,
            )
        )
        mock_tracker.state.add_position(
            Position(
                position_id="pos-2",
                token="ETH",
                direction=PositionDirection.SHORT,
                entry_price=3000.0,
                quantity=10.0,
                current_price=2900.0,
            )
        )

        pnl = api.get_pnl_summary()

        assert pnl["total_unrealized_pnl"] == 2000.0  # 1000 + 1000
        assert pnl["long_pnl"] == 1000.0
        assert pnl["short_pnl"] == 1000.0
        assert "BTC" in pnl["pnl_by_token"]
        assert "ETH" in pnl["pnl_by_token"]


class TestPortfolioAPIHistorical:
    """Tests for historical data endpoints."""

    @pytest.mark.asyncio
    async def test_get_historical_snapshots(self, api, mock_tracker):
        """Test getting historical snapshots."""
        snapshots = [
            PortfolioSnapshot(
                snapshot_id="snap-1",
                portfolio_id="test-portfolio",
                timestamp=1234567890000,
                total_equity=100000.0,
                available_equity=80000.0,
                margin_used=20000.0,
                unrealized_pnl=5000.0,
                realized_pnl=2000.0,
                position_count=5,
            )
        ]
        mock_tracker.get_snapshots.return_value = snapshots

        result = await api.get_historical_snapshots()

        assert len(result) == 1
        assert result[0]["snapshot_id"] == "snap-1"

    @pytest.mark.asyncio
    async def test_get_equity_curve(self, api, mock_tracker):
        """Test getting equity curve data."""
        snapshots = [
            PortfolioSnapshot(
                snapshot_id="snap-1",
                portfolio_id="test-portfolio",
                timestamp=1234567890000,
                total_equity=100000.0,
                available_equity=80000.0,
                margin_used=20000.0,
                unrealized_pnl=5000.0,
                realized_pnl=2000.0,
                position_count=5,
            ),
            PortfolioSnapshot(
                snapshot_id="snap-2",
                portfolio_id="test-portfolio",
                timestamp=1234567950000,
                total_equity=105000.0,
                available_equity=85000.0,
                margin_used=20000.0,
                unrealized_pnl=8000.0,
                realized_pnl=2000.0,
                position_count=5,
            ),
        ]
        mock_tracker.get_snapshots.return_value = snapshots

        curve = await api.get_equity_curve()

        assert len(curve) == 2
        assert curve[0]["timestamp"] == 1234567890000
        assert curve[1]["timestamp"] == 1234567950000


class TestPortfolioAPIState:
    """Tests for full state endpoint."""

    def test_get_full_state(self, api, mock_tracker):
        """Test getting complete portfolio state."""
        mock_tracker.state.update_balance("USDT", free=10000.0)
        mock_tracker.state.add_position(
            Position(
                position_id="pos-1",
                token="BTC",
                direction=PositionDirection.LONG,
                entry_price=50000.0,
                quantity=1.0,
                current_price=51000.0,
            )
        )

        state = api.get_full_state()

        assert state["portfolio_id"] == "test-portfolio"
        assert "positions" in state
        assert "balances" in state
        assert "pos-1" in state["positions"]


class TestPortfolioAPIHealth:
    """Tests for health check endpoint."""

    def test_health_check(self, api, mock_tracker):
        """Test health check."""
        mock_tracker.state.last_update = 1234567890000

        health = api.health_check()

        assert health["status"] == "healthy"
        assert health["portfolio_id"] == "test-portfolio"
        assert "latency_ms" in health
        assert health["last_update"] == 1234567890000


class TestCreatePortfolioRoutes:
    """Tests for route factory function."""

    def test_create_routes(self, mock_tracker):
        """Test creating portfolio routes."""
        routes = create_portfolio_routes(mock_tracker)

        assert len(routes) == 9

        # Check expected routes exist
        paths = [r["path"] for r in routes]
        assert "/portfolio/summary" in paths
        assert "/portfolio/positions" in paths
        assert "/portfolio/balances" in paths
        assert "/portfolio/pnl" in paths
        assert "/portfolio/state" in paths
        assert "/portfolio/health" in paths
