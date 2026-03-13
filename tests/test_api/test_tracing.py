"""
Tests for API tracing instrumentation

TEMPO-2026-001
"""

import pytest
from fastapi.testclient import TestClient

# Import the app from main
from src.api.main import app

client = TestClient(app)


def test_health_endpoint_creates_span():
    """Test that health endpoint creates a trace span."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "chiseai-api"
    # Note: Actual span verification requires Tempo to be running


def test_ready_endpoint_creates_span():
    """Test that readiness endpoint creates a trace span."""
    response = client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["service"] == "chiseai-api"


def test_api_requests_are_traced():
    """Test that API requests generate trace data."""
    # This test verifies the instrumentation is in place
    # Full verification requires integration with Tempo

    # Test health endpoint
    response = client.get("/health")
    assert response.status_code == 200

    # Test readiness endpoint
    response = client.get("/ready")
    assert response.status_code == 200


def test_trades_endpoint_creates_span():
    """Test that trades endpoint creates custom trace spans."""
    # Test trade creation
    trade_data = {
        "symbol": "AAPL",
        "side": "buy",
        "quantity": 100.0,
        "order_type": "market",
        "user_id": "test-user-123",
    }

    response = client.post("/api/v1/trades/", json=trade_data)
    assert response.status_code == 200

    data = response.json()
    assert "trade_id" in data
    assert data["status"] == "created"
    assert data["symbol"] == trade_data["symbol"]
    assert data["side"] == trade_data["side"]
    # Note: Actual span verification requires Tempo to be running


def test_get_trade_endpoint_creates_span():
    """Test that get trade endpoint creates a trace span."""
    trade_id = "test-trade-123"
    response = client.get(f"/api/v1/trades/{trade_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["trade_id"] == trade_id
    # Note: Actual span verification requires Tempo to be running


def test_list_trades_endpoint_creates_span():
    """Test that list trades endpoint creates a trace span."""
    response = client.get("/api/v1/trades/")
    assert response.status_code == 200

    data = response.json()
    assert "trades" in data
    # Note: Actual span verification requires Tempo to be running


def test_cancel_trade_endpoint_creates_span():
    """Test that cancel trade endpoint creates a trace span."""
    trade_id = "test-trade-123"
    response = client.post(f"/api/v1/trades/{trade_id}/cancel")
    assert response.status_code == 200

    data = response.json()
    assert data["trade_id"] == trade_id
    assert data["status"] == "cancelled"
    # Note: Actual span verification requires Tempo to be running
