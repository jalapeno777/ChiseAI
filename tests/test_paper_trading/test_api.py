"""Tests for paper trading API endpoints.

Tests for HOTFIX-PAPER-API-001: Paper Trading API Endpoints
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

# Add src to path
sys.path.insert(0, "src")

from paper_trading.models import (
    OrderSide,
    OrderState,
    OrderType,
    PaperOrder,
    PaperPnL,
    PaperPosition,
    PositionSide,
)
from paper_trading.tracker import PaperTradingTracker


class MockRedis:
    """Mock Redis client for testing."""

    def __init__(self):
        self.data: dict[str, Any] = {}
        self.sets: dict[str, set] = {}
        self.zsets: dict[str, dict] = {}

    def get(self, key: str) -> str | None:
        return self.data.get(key)

    def set(self, key: str, value: str) -> bool:
        self.data[key] = value
        return True

    def delete(self, key: str) -> int:
        if key in self.data:
            del self.data[key]
            return 1
        return 0

    def expire(self, key: str, seconds: int) -> bool:
        return True

    def sadd(self, key: str, member: str) -> int:
        if key not in self.sets:
            self.sets[key] = set()
        self.sets[key].add(member)
        return 1

    def srem(self, key: str, member: str) -> int:
        if key in self.sets and member in self.sets[key]:
            self.sets[key].remove(member)
            return 1
        return 0

    def smembers(self, key: str) -> set:
        return self.sets.get(key, set())

    def scard(self, key: str) -> int:
        return len(self.sets.get(key, set()))

    def zadd(self, key: str, mapping: dict) -> int:
        if key not in self.zsets:
            self.zsets[key] = {}
        self.zsets[key].update(mapping)
        return len(mapping)

    def zrevrange(self, key: str, start: int, end: int) -> list:
        if key not in self.zsets:
            return []
        items = sorted(self.zsets[key].items(), key=lambda x: x[1], reverse=True)
        if end == -1:
            end = len(items)
        else:
            end = end + 1
        return [item[0] for item in items[start:end]]

    def zcard(self, key: str) -> int:
        return len(self.zsets.get(key, {}))


@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    return MockRedis()


@pytest.fixture
def tracker(mock_redis):
    """Create a paper trading tracker with mock Redis."""
    return PaperTradingTracker(portfolio_id="test", redis_client=mock_redis)


@pytest.fixture
def client(tracker):
    """Create a test client with the tracker."""
    # Import here to avoid circular imports
    from api.paper_router import set_tracker
    from main import app

    set_tracker(tracker)
    return TestClient(app)


class TestEndpointRegistration:
    """Tests to verify endpoints are properly registered and return 200."""

    def test_positions_endpoint_returns_200(self, client):
        """Verify /paper/positions endpoint returns HTTP 200."""
        response = client.get("/paper/positions")
        assert response.status_code == 200
        data = response.json()
        assert "success" in data
        assert "data" in data

    def test_positions_by_symbol_endpoint_returns_200(self, client):
        """Verify /paper/positions/{symbol} endpoint returns HTTP 200 or 404."""
        response = client.get("/paper/positions/BTC-USD")
        # Should be 200 if found or 404 if not found
        assert response.status_code in [200, 404]

    def test_orders_endpoint_returns_200(self, client):
        """Verify /paper/orders endpoint returns HTTP 200."""
        response = client.get("/paper/orders")
        assert response.status_code == 200
        data = response.json()
        assert "success" in data
        assert "data" in data

    def test_orders_with_filters(self, client):
        """Verify /paper/orders endpoint accepts filter parameters."""
        response = client.get("/paper/orders?symbol=BTC-USD&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert "success" in data

    def test_orders_with_state_filter_valid(self, client):
        """Verify /paper/orders endpoint accepts valid state filter."""
        response = client.get("/paper/orders?state=filled")
        assert response.status_code == 200
        data = response.json()
        assert "success" in data

    def test_orders_with_state_filter_invalid(self, client):
        """Verify /paper/orders endpoint returns 400 for invalid state."""
        response = client.get("/paper/orders?state=invalid_state")
        assert response.status_code == 400

    def test_order_by_id_endpoint_returns_200_or_404(self, client):
        """Verify /paper/orders/{order_id} endpoint returns HTTP 200 or 404."""
        response = client.get("/paper/orders/test-order-id")
        # Should be 200 if found or 404 if not found
        assert response.status_code in [200, 404]

    def test_pnl_endpoint_returns_200(self, client):
        """Verify /paper/pnl endpoint returns HTTP 200."""
        response = client.get("/paper/pnl")
        assert response.status_code == 200
        data = response.json()
        assert "success" in data
        assert "data" in data
        assert "pnl" in data["data"]

    def test_pnl_endpoint_with_calculate_param(self, client):
        """Verify /paper/pnl endpoint accepts calculate parameter."""
        response = client.get("/paper/pnl?calculate=true")
        assert response.status_code == 200
        data = response.json()
        assert "success" in data

    def test_portfolio_endpoint_returns_200(self, client):
        """Verify /paper/portfolio endpoint returns HTTP 200."""
        response = client.get("/paper/portfolio")
        assert response.status_code == 200
        data = response.json()
        assert "success" in data
        assert "data" in data

    def test_stats_endpoint_returns_200(self, client):
        """Verify /paper/stats endpoint returns HTTP 200."""
        response = client.get("/paper/stats")
        assert response.status_code == 200
        data = response.json()
        assert "success" in data
        assert "data" in data


class TestResponseStructure:
    """Tests to verify response structure is correct."""

    def test_positions_response_structure(self, client):
        """Verify positions response has expected fields."""
        response = client.get("/paper/positions")
        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert "data" in data
        assert "positions" in data["data"]
        assert "count" in data["data"]
        assert "total_unrealized_pnl" in data["data"]
        assert "total_realized_pnl" in data["data"]
        assert "timestamp" in data["data"]

    def test_orders_response_structure(self, client):
        """Verify orders response has expected fields."""
        response = client.get("/paper/orders")
        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert "data" in data
        assert "orders" in data["data"]
        assert "count" in data["data"]
        assert "by_state" in data["data"]
        assert "timestamp" in data["data"]

    def test_pnl_response_structure(self, client):
        """Verify PnL response has expected fields."""
        response = client.get("/paper/pnl")
        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert "data" in data
        assert "pnl" in data["data"]

        pnl = data["data"]["pnl"]
        assert "total_realized_pnl" in pnl
        assert "total_unrealized_pnl" in pnl
        assert "total_pnl" in pnl
        assert "win_count" in pnl
        assert "loss_count" in pnl
        assert "total_trades" in pnl
        assert "win_rate" in pnl

    def test_portfolio_response_structure(self, client):
        """Verify portfolio response has expected fields."""
        response = client.get("/paper/portfolio")
        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert "data" in data
        assert "portfolio_id" in data["data"]
        assert "balance" in data["data"]
        assert "equity" in data["data"]
        assert "positions" in data["data"]
        assert "recent_orders" in data["data"]
        assert "pnl" in data["data"]

    def test_stats_response_structure(self, client):
        """Verify stats response has expected fields."""
        response = client.get("/paper/stats")
        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert "data" in data
        assert "portfolio_id" in data["data"]
        assert "timestamp" in data


class TestTrackerWithMockData:
    """Tests with mock data in the tracker."""

    def test_positions_with_mock_data(self, client, tracker):
        """Test positions endpoint returns data saved in tracker."""
        # Add position to tracker
        position = PaperPosition(
            symbol="BTC-USD",
            side=PositionSide.LONG,
            size=1.0,
            entry_price=50000.0,
            mark_price=51000.0,
            unrealized_pnl=1000.0,
            realized_pnl=0.0,
            created_at=datetime.now(UTC),
        )
        tracker.save_position(position)

        # Query through API
        response = client.get("/paper/positions")
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["count"] == 1
        assert data["data"]["positions"][0]["symbol"] == "BTC-USD"

    def test_orders_with_mock_data(self, client, tracker):
        """Test orders endpoint returns data saved in tracker."""
        # Add order to tracker
        order = PaperOrder(
            order_id="order-001",
            symbol="ETH-USD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=10.0,
            filled_quantity=10.0,
            state=OrderState.FILLED,
            created_at=datetime.now(UTC),
        )
        tracker.save_order(order)

        # Query through API
        response = client.get("/paper/orders")
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["count"] == 1
        assert data["data"]["orders"][0]["symbol"] == "ETH-USD"

    def test_pnl_with_mock_data(self, client, tracker):
        """Test PnL endpoint returns data saved in tracker."""
        # Add PnL to tracker
        pnl = PaperPnL(
            total_realized_pnl=5000.0,
            total_unrealized_pnl=1000.0,
            total_pnl=6000.0,
            win_count=10,
            loss_count=5,
            total_trades=15,
            win_rate=66.67,
        )
        tracker.save_pnl(pnl)

        # Query through API
        response = client.get("/paper/pnl")
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["pnl"]["total_pnl"] == 6000.0
        assert data["data"]["pnl"]["win_count"] == 10

    def test_position_by_symbol_found(self, client, tracker):
        """Test getting specific position that exists."""
        position = PaperPosition(
            symbol="BTC-USD",
            side=PositionSide.LONG,
            size=1.0,
            entry_price=50000.0,
            created_at=datetime.now(UTC),
        )
        tracker.save_position(position)

        response = client.get("/paper/positions/BTC-USD")
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["position"]["symbol"] == "BTC-USD"

    def test_position_by_symbol_not_found(self, client):
        """Test getting specific position that doesn't exist."""
        response = client.get("/paper/positions/XXX-YYY")
        assert response.status_code == 404

    def test_order_by_id_found(self, client, tracker):
        """Test getting specific order that exists."""
        order = PaperOrder(
            order_id="test-order-123",
            symbol="BTC-USD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=1.0,
            state=OrderState.FILLED,
            created_at=datetime.now(UTC),
        )
        tracker.save_order(order)

        response = client.get("/paper/orders/test-order-123")
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["order"]["order_id"] == "test-order-123"

    def test_order_by_id_not_found(self, client):
        """Test getting specific order that doesn't exist."""
        response = client.get("/paper/orders/nonexistent-order")
        assert response.status_code == 404
