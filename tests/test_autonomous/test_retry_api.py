"""Tests for retry API routes using FastAPI TestClient.

Tests:
- All API endpoints with mocked dependencies
- GET /api/v1/retry/budgets - List all service budgets
- GET /api/v1/retry/budgets/{service} - Get specific service budget
- POST /api/v1/retry/budgets/{service}/reset - Reset budget
- GET /api/v1/retry/dead-letter - List DLQ items
- POST /api/v1/retry/dead-letter/{id}/retry - Retry DLQ item
- DELETE /api/v1/retry/dead-letter/{id} - Delete DLQ item
- GET /api/v1/retry/metrics - Get retry metrics
- GET /api/v1/retry/circuit-breakers - Get circuit breaker states
- Error cases and edge cases

For ST-NS-039: Retry Coordinator with Budget Management - Coverage Improvement
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from src.autonomous_control_plane.api.v1.retry import (
    router as retry_router,
    set_retry_coordinator,
    get_retry_coordinator,
)
from src.autonomous_control_plane.components.retry_coordinator import RetryCoordinator


# Create test app
@pytest.fixture
def app():
    """Create a FastAPI app with retry router."""
    app = FastAPI()
    app.include_router(retry_router)
    return app


@pytest.fixture
def mock_coordinator():
    """Create a mock retry coordinator."""
    coordinator = MagicMock(spec=RetryCoordinator)
    return coordinator


@pytest.fixture
def client(app, mock_coordinator):
    """Create a test client with mocked coordinator."""
    # Reset the global coordinator
    set_retry_coordinator(mock_coordinator)

    with TestClient(app) as test_client:
        yield test_client

    # Clean up
    set_retry_coordinator(None)


class TestRetryAPIBudgets:
    """Tests for budget-related API endpoints."""

    def test_list_budgets_success(self, client, mock_coordinator):
        """Test GET /api/v1/retry/budgets returns all budgets."""
        mock_coordinator.get_all_budgets.return_value = [
            {
                "service_name": "service_a",
                "current_count": 5,
                "limit": 100,
                "remaining": 95,
                "is_exceeded": False,
            },
            {
                "service_name": "service_b",
                "current_count": 50,
                "limit": 100,
                "remaining": 50,
                "is_exceeded": False,
            },
        ]

        response = client.get("/api/v1/retry/budgets")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["count"] == 2
        assert len(data["data"]["budgets"]) == 2

    def test_list_budgets_empty(self, client, mock_coordinator):
        """Test GET /api/v1/retry/budgets with no budgets."""
        mock_coordinator.get_all_budgets.return_value = []

        response = client.get("/api/v1/retry/budgets")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["count"] == 0
        assert data["data"]["budgets"] == []

    def test_list_budgets_error(self, client, mock_coordinator):
        """Test GET /api/v1/retry/budgets handles errors."""
        mock_coordinator.get_all_budgets.side_effect = Exception("Database error")

        response = client.get("/api/v1/retry/budgets")

        assert response.status_code == 500
        assert "Failed to list budgets" in response.json()["detail"]

    def test_get_budget_success(self, client, mock_coordinator):
        """Test GET /api/v1/retry/budgets/{service} returns budget."""
        mock_coordinator.get_budget_status.return_value = {
            "service_name": "test_service",
            "current_count": 10,
            "limit": 100,
            "remaining": 90,
            "is_exceeded": False,
        }

        response = client.get("/api/v1/retry/budgets/test_service")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["service_name"] == "test_service"
        assert data["data"]["current_count"] == 10

    def test_get_budget_not_found(self, client, mock_coordinator):
        """Test GET /api/v1/retry/budgets/{service} for non-existent service."""
        mock_coordinator.get_budget_status.return_value = {
            "service_name": "nonexistent",
            "current_count": 0,
            "limit": 100,
            "remaining": 100,
            "is_exceeded": False,
        }

        response = client.get("/api/v1/retry/budgets/nonexistent")

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["current_count"] == 0

    def test_get_budget_error(self, client, mock_coordinator):
        """Test GET /api/v1/retry/budgets/{service} handles errors."""
        mock_coordinator.get_budget_status.side_effect = Exception("Service error")

        response = client.get("/api/v1/retry/budgets/test_service")

        assert response.status_code == 500

    def test_reset_budget_success(self, client, mock_coordinator):
        """Test POST /api/v1/retry/budgets/{service}/reset resets budget."""
        mock_coordinator.reset_budget.return_value = None

        response = client.post("/api/v1/retry/budgets/test_service/reset")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "test_service" in data["message"]
        mock_coordinator.reset_budget.assert_called_once_with("test_service")

    def test_reset_budget_error(self, client, mock_coordinator):
        """Test POST /api/v1/retry/budgets/{service}/reset handles errors."""
        mock_coordinator.reset_budget.side_effect = Exception("Reset failed")

        response = client.post("/api/v1/retry/budgets/test_service/reset")

        assert response.status_code == 500


class TestRetryAPIDeadLetter:
    """Tests for dead letter queue API endpoints."""

    def test_list_dead_letter_items(self, client, mock_coordinator):
        """Test GET /api/v1/retry/dead-letter returns DLQ items."""
        mock_coordinator.get_dlq_items.return_value = [
            {
                "id": "item-1",
                "service_name": "service_a",
                "operation": "fetch_data",
                "error_message": "Timeout",
                "retry_count": 3,
                "status": "DLQ",
            },
            {
                "id": "item-2",
                "service_name": "service_b",
                "operation": "process_data",
                "error_message": "Connection refused",
                "retry_count": 5,
                "status": "DLQ",
            },
        ]

        response = client.get("/api/v1/retry/dead-letter")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["count"] == 2
        assert len(data["data"]["items"]) == 2

    def test_list_dead_letter_items_with_filter(self, client, mock_coordinator):
        """Test GET /api/v1/retry/dead-letter with service filter."""
        mock_coordinator.get_dlq_items.return_value = [
            {
                "id": "item-1",
                "service_name": "service_a",
                "operation": "fetch_data",
                "error_message": "Timeout",
                "retry_count": 3,
                "status": "DLQ",
            },
        ]

        response = client.get("/api/v1/retry/dead-letter?service=service_a")

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["service_filter"] == "service_a"
        mock_coordinator.get_dlq_items.assert_called_once_with(
            service_name="service_a", limit=100
        )

    def test_list_dead_letter_items_with_limit(self, client, mock_coordinator):
        """Test GET /api/v1/retry/dead-letter with limit parameter."""
        mock_coordinator.get_dlq_items.return_value = []

        response = client.get("/api/v1/retry/dead-letter?limit=50")

        assert response.status_code == 200
        mock_coordinator.get_dlq_items.assert_called_once_with(
            service_name=None, limit=50
        )

    def test_list_dead_letter_items_error(self, client, mock_coordinator):
        """Test GET /api/v1/retry/dead-letter handles errors."""
        mock_coordinator.get_dlq_items.side_effect = Exception("DLQ error")

        response = client.get("/api/v1/retry/dead-letter")

        assert response.status_code == 500

    def test_retry_dead_letter_item_success(self, client, mock_coordinator):
        """Test POST /api/v1/retry/dead-letter/{id}/retry marks item for retry."""
        mock_coordinator.retry_dlq_item.return_value = True

        response = client.post("/api/v1/retry/dead-letter/item-123/retry")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "item-123" in data["message"]
        mock_coordinator.retry_dlq_item.assert_called_once_with("item-123")

    def test_retry_dead_letter_item_not_found(self, client, mock_coordinator):
        """Test POST /api/v1/retry/dead-letter/{id}/retry for non-existent item."""
        mock_coordinator.retry_dlq_item.return_value = False

        response = client.post("/api/v1/retry/dead-letter/nonexistent/retry")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_retry_dead_letter_item_error(self, client, mock_coordinator):
        """Test POST /api/v1/retry/dead-letter/{id}/retry handles errors."""
        mock_coordinator.retry_dlq_item.side_effect = Exception("Retry failed")

        response = client.post("/api/v1/retry/dead-letter/item-123/retry")

        assert response.status_code == 500

    def test_delete_dead_letter_item_success(self, client, mock_coordinator):
        """Test DELETE /api/v1/retry/dead-letter/{id} deletes item."""
        mock_coordinator.delete_dlq_item.return_value = True

        response = client.delete("/api/v1/retry/dead-letter/item-123")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "deleted" in data["message"].lower()
        mock_coordinator.delete_dlq_item.assert_called_once_with("item-123")

    def test_delete_dead_letter_item_not_found(self, client, mock_coordinator):
        """Test DELETE /api/v1/retry/dead-letter/{id} for non-existent item."""
        mock_coordinator.delete_dlq_item.return_value = False

        response = client.delete("/api/v1/retry/dead-letter/nonexistent")

        assert response.status_code == 404

    def test_delete_dead_letter_item_error(self, client, mock_coordinator):
        """Test DELETE /api/v1/retry/dead-letter/{id} handles errors."""
        mock_coordinator.delete_dlq_item.side_effect = Exception("Delete failed")

        response = client.delete("/api/v1/retry/dead-letter/item-123")

        assert response.status_code == 500


class TestRetryAPIMetrics:
    """Tests for metrics API endpoints."""

    def test_get_metrics_success(self, client, mock_coordinator):
        """Test GET /api/v1/retry/metrics returns metrics."""
        mock_coordinator.get_metrics.return_value = {
            "total_attempts": 100,
            "total_successes": 85,
            "total_failures": 15,
            "total_budget_exceeded": 2,
            "total_dlq": 5,
            "success_rate": 0.85,
            "avg_backoff_ms": 150.5,
        }

        response = client.get("/api/v1/retry/metrics")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["total_attempts"] == 100
        assert data["data"]["success_rate"] == 0.85

    def test_get_metrics_empty(self, client, mock_coordinator):
        """Test GET /api/v1/retry/metrics with no data."""
        mock_coordinator.get_metrics.return_value = {
            "total_attempts": 0,
            "total_successes": 0,
            "total_failures": 0,
            "total_budget_exceeded": 0,
            "total_dlq": 0,
            "success_rate": 0,
            "avg_backoff_ms": 0,
        }

        response = client.get("/api/v1/retry/metrics")

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["total_attempts"] == 0

    def test_get_metrics_error(self, client, mock_coordinator):
        """Test GET /api/v1/retry/metrics handles errors."""
        mock_coordinator.get_metrics.side_effect = Exception("Metrics error")

        response = client.get("/api/v1/retry/metrics")

        assert response.status_code == 500


class TestRetryAPICircuitBreakers:
    """Tests for circuit breaker API endpoints."""

    def test_get_circuit_breaker_states_success(self, client, mock_coordinator):
        """Test GET /api/v1/retry/circuit-breakers returns states."""
        mock_coordinator.get_circuit_breaker_states.return_value = {
            "circuit_a": {
                "state": "CLOSED",
                "failure_count": 0,
                "last_failure_time": None,
            },
            "circuit_b": {
                "state": "OPEN",
                "failure_count": 5,
                "last_failure_time": "2026-02-20T12:00:00",
            },
        }

        response = client.get("/api/v1/retry/circuit-breakers")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["count"] == 2
        assert "circuit_a" in data["data"]["circuit_breakers"]
        assert "circuit_b" in data["data"]["circuit_breakers"]

    def test_get_circuit_breaker_states_empty(self, client, mock_coordinator):
        """Test GET /api/v1/retry/circuit-breakers with no circuits."""
        mock_coordinator.get_circuit_breaker_states.return_value = {}

        response = client.get("/api/v1/retry/circuit-breakers")

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["count"] == 0

    def test_get_circuit_breaker_states_error(self, client, mock_coordinator):
        """Test GET /api/v1/retry/circuit-breakers handles errors."""
        mock_coordinator.get_circuit_breaker_states.side_effect = Exception(
            "Circuit breaker error"
        )

        response = client.get("/api/v1/retry/circuit-breakers")

        assert response.status_code == 500


class TestRetryAPINotInitialized:
    """Tests for when coordinator is not initialized."""

    @pytest.fixture
    def client_no_coordinator(self, app):
        """Create a test client without coordinator."""
        # Ensure no coordinator is set
        set_retry_coordinator(None)

        with TestClient(app) as test_client:
            yield test_client

    def test_list_budgets_not_initialized(self, client_no_coordinator):
        """Test GET /api/v1/retry/budgets returns 503 when not initialized."""
        response = client_no_coordinator.get("/api/v1/retry/budgets")

        assert response.status_code == 503
        assert "not initialized" in response.json()["detail"].lower()

    def test_get_budget_not_initialized(self, client_no_coordinator):
        """Test GET /api/v1/retry/budgets/{service} returns 503 when not initialized."""
        response = client_no_coordinator.get("/api/v1/retry/budgets/test_service")

        assert response.status_code == 503

    def test_reset_budget_not_initialized(self, client_no_coordinator):
        """Test POST /api/v1/retry/budgets/{service}/reset returns 503 when not initialized."""
        response = client_no_coordinator.post(
            "/api/v1/retry/budgets/test_service/reset"
        )

        assert response.status_code == 503

    def test_list_dead_letter_not_initialized(self, client_no_coordinator):
        """Test GET /api/v1/retry/dead-letter returns 503 when not initialized."""
        response = client_no_coordinator.get("/api/v1/retry/dead-letter")

        assert response.status_code == 503

    def test_retry_dlq_item_not_initialized(self, client_no_coordinator):
        """Test POST /api/v1/retry/dead-letter/{id}/retry returns 503 when not initialized."""
        response = client_no_coordinator.post(
            "/api/v1/retry/dead-letter/item-123/retry"
        )

        assert response.status_code == 503

    def test_delete_dlq_item_not_initialized(self, client_no_coordinator):
        """Test DELETE /api/v1/retry/dead-letter/{id} returns 503 when not initialized."""
        response = client_no_coordinator.delete("/api/v1/retry/dead-letter/item-123")

        assert response.status_code == 503

    def test_get_metrics_not_initialized(self, client_no_coordinator):
        """Test GET /api/v1/retry/metrics returns 503 when not initialized."""
        response = client_no_coordinator.get("/api/v1/retry/metrics")

        assert response.status_code == 503

    def test_get_circuit_breakers_not_initialized(self, client_no_coordinator):
        """Test GET /api/v1/retry/circuit-breakers returns 503 when not initialized."""
        response = client_no_coordinator.get("/api/v1/retry/circuit-breakers")

        assert response.status_code == 503


class TestRetryAPIEdgeCases:
    """Tests for edge cases in API."""

    def test_list_dead_letter_limit_bounds(self, client, mock_coordinator):
        """Test limit parameter bounds."""
        mock_coordinator.get_dlq_items.return_value = []

        # Test with minimum limit
        response = client.get("/api/v1/retry/dead-letter?limit=1")
        assert response.status_code == 200

        # Test with maximum limit
        response = client.get("/api/v1/retry/dead-letter?limit=1000")
        assert response.status_code == 200

    def test_list_dead_letter_invalid_limit(self, client, mock_coordinator):
        """Test limit parameter validation."""
        mock_coordinator.get_dlq_items.return_value = []

        # Limit below minimum should fail validation
        response = client.get("/api/v1/retry/dead-letter?limit=0")
        assert response.status_code == 422  # Validation error

        # Limit above maximum should fail validation
        response = client.get("/api/v1/retry/dead-letter?limit=1001")
        assert response.status_code == 422

    def test_service_name_with_special_characters(self, client, mock_coordinator):
        """Test service names with special characters."""
        mock_coordinator.get_budget_status.return_value = {
            "service_name": "service-with-dashes",
            "current_count": 0,
            "limit": 100,
            "remaining": 100,
            "is_exceeded": False,
        }

        response = client.get("/api/v1/retry/budgets/service-with-dashes")
        assert response.status_code == 200

    def test_service_name_with_dots(self, client, mock_coordinator):
        """Test service names with dots."""
        mock_coordinator.get_budget_status.return_value = {
            "service_name": "service.v1",
            "current_count": 0,
            "limit": 100,
            "remaining": 100,
            "is_exceeded": False,
        }

        response = client.get("/api/v1/retry/budgets/service.v1")
        assert response.status_code == 200

    def test_dlq_item_id_format(self, client, mock_coordinator):
        """Test DLQ item ID with UUID format."""
        mock_coordinator.retry_dlq_item.return_value = True

        uuid_id = "550e8400-e29b-41d4-a716-446655440000"
        response = client.post(f"/api/v1/retry/dead-letter/{uuid_id}/retry")
        assert response.status_code == 200
        mock_coordinator.retry_dlq_item.assert_called_once_with(uuid_id)

    def test_response_structure_consistency(self, client, mock_coordinator):
        """Test that all successful responses have consistent structure."""
        mock_coordinator.get_all_budgets.return_value = []

        response = client.get("/api/v1/retry/budgets")
        data = response.json()

        # All responses should have 'success' field
        assert "success" in data
        # Successful responses should have 'data' field
        assert "data" in data


class TestRetryAPIHelperFunctions:
    """Tests for API helper functions."""

    def test_set_retry_coordinator(self):
        """Test setting the global retry coordinator."""
        mock_coordinator = MagicMock()

        set_retry_coordinator(mock_coordinator)

        assert get_retry_coordinator() == mock_coordinator

    def test_get_retry_coordinator_none(self):
        """Test getting coordinator when none is set."""
        set_retry_coordinator(None)

        assert get_retry_coordinator() is None

    def test_set_retry_coordinator_override(self):
        """Test that setting coordinator overrides previous value."""
        mock_coordinator1 = MagicMock()
        mock_coordinator2 = MagicMock()

        set_retry_coordinator(mock_coordinator1)
        assert get_retry_coordinator() == mock_coordinator1

        set_retry_coordinator(mock_coordinator2)
        assert get_retry_coordinator() == mock_coordinator2
