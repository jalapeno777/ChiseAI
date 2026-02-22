"""API endpoint tests for Circuit Breaker Registry.

ST-NS-038: Circuit Breaker Registry & Unified Telemetry

Note: These tests mock the CircuitBreakerRegistry singleton to avoid
isolation issues when running tests together.
"""

import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


class TestCircuitBreakerAPI(unittest.TestCase):
    """Test cases for Circuit Breaker API endpoints."""

    def setUp(self):
        """Set up test fixtures."""
        # Create a fresh FastAPI app for each test
        from fastapi import FastAPI
        from autonomous_control_plane.api.v1.circuit_breakers import router

        self.app = FastAPI()
        self.app.include_router(router, prefix="/api/v1")
        self.client = TestClient(self.app)

    @patch("autonomous_control_plane.api.v1.circuit_breakers._registry")
    def test_get_all_circuit_breakers_empty(self, mock_registry):
        """Test getting all circuit breakers when empty."""
        mock_registry.get_all_states_dict.return_value = {}

        response = self.client.get("/api/v1/circuit-breakers")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 0)
        self.assertEqual(data["circuit_breakers"], {})

    @patch("autonomous_control_plane.api.v1.circuit_breakers._registry")
    def test_get_all_circuit_breakers_with_data(self, mock_registry):
        """Test getting all circuit breakers with data."""
        mock_registry.get_all_states_dict.return_value = {
            "service1": {"name": "service1", "state": "closed"},
            "service2": {"name": "service2", "state": "open"},
        }

        response = self.client.get("/api/v1/circuit-breakers")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 2)
        self.assertIn("service1", data["circuit_breakers"])
        self.assertIn("service2", data["circuit_breakers"])

    @patch("autonomous_control_plane.api.v1.circuit_breakers._registry")
    def test_get_circuit_breaker_found(self, mock_registry):
        """Test getting a specific circuit breaker that exists."""
        mock_state = MagicMock()
        mock_state.to_dict.return_value = {"name": "test_service", "state": "closed"}
        mock_registry.get.return_value = mock_state

        response = self.client.get("/api/v1/circuit-breakers/test_service")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "test_service")
        self.assertEqual(data["state"], "closed")

    @patch("autonomous_control_plane.api.v1.circuit_breakers._registry")
    def test_get_circuit_breaker_not_found(self, mock_registry):
        """Test getting a circuit breaker that doesn't exist."""
        mock_registry.get.return_value = None

        response = self.client.get("/api/v1/circuit-breakers/nonexistent")

        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertIn("not found", data["detail"].lower())

    @patch("autonomous_control_plane.api.v1.circuit_breakers._registry")
    def test_create_circuit_breaker(self, mock_registry):
        """Test creating a new circuit breaker."""
        mock_state = MagicMock()
        mock_state.to_dict.return_value = {"name": "new_service", "state": "closed"}
        mock_registry.register.return_value = mock_state

        response = self.client.post("/api/v1/circuit-breakers/new_service")

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["name"], "new_service")

    @patch("autonomous_control_plane.api.v1.circuit_breakers._registry")
    def test_delete_circuit_breaker_success(self, mock_registry):
        """Test deleting an existing circuit breaker."""
        mock_state = MagicMock()
        mock_registry.unregister.return_value = mock_state

        response = self.client.delete("/api/v1/circuit-breakers/test_service")

        self.assertEqual(response.status_code, 204)

    @patch("autonomous_control_plane.api.v1.circuit_breakers._registry")
    def test_delete_circuit_breaker_not_found(self, mock_registry):
        """Test deleting a nonexistent circuit breaker."""
        mock_registry.unregister.return_value = None

        response = self.client.delete("/api/v1/circuit-breakers/nonexistent")

        self.assertEqual(response.status_code, 404)

    @patch("autonomous_control_plane.api.v1.circuit_breakers._registry")
    def test_force_open_circuit_breaker_success(self, mock_registry):
        """Test forcing open an existing circuit breaker."""
        mock_registry.force_open.return_value = True
        mock_state = MagicMock()
        mock_state.to_dict.return_value = {"name": "test_service", "state": "open"}
        mock_registry.get.return_value = mock_state

        response = self.client.post("/api/v1/circuit-breakers/test_service/force-open")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["state"], "open")

    @patch("autonomous_control_plane.api.v1.circuit_breakers._registry")
    def test_force_open_circuit_breaker_not_found(self, mock_registry):
        """Test forcing open a nonexistent circuit breaker."""
        mock_registry.force_open.return_value = False

        response = self.client.post("/api/v1/circuit-breakers/nonexistent/force-open")

        self.assertEqual(response.status_code, 404)

    @patch("autonomous_control_plane.api.v1.circuit_breakers._registry")
    def test_force_close_circuit_breaker_success(self, mock_registry):
        """Test forcing close an existing circuit breaker."""
        mock_registry.force_close.return_value = True
        mock_state = MagicMock()
        mock_state.to_dict.return_value = {"name": "test_service", "state": "closed"}
        mock_registry.get.return_value = mock_state

        response = self.client.post("/api/v1/circuit-breakers/test_service/force-close")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["state"], "closed")

    @patch("autonomous_control_plane.api.v1.circuit_breakers._registry")
    def test_force_close_circuit_breaker_not_found(self, mock_registry):
        """Test forcing close a nonexistent circuit breaker."""
        mock_registry.force_close.return_value = False

        response = self.client.post("/api/v1/circuit-breakers/nonexistent/force-close")

        self.assertEqual(response.status_code, 404)

    @patch("autonomous_control_plane.api.v1.circuit_breakers._registry")
    def test_reset_circuit_breaker_success(self, mock_registry):
        """Test resetting an existing circuit breaker."""
        mock_registry.reset.return_value = True
        mock_state = MagicMock()
        mock_state.to_dict.return_value = {"name": "test_service", "state": "closed"}
        mock_registry.get.return_value = mock_state

        response = self.client.post("/api/v1/circuit-breakers/test_service/reset")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["state"], "closed")

    @patch("autonomous_control_plane.api.v1.circuit_breakers._registry")
    def test_reset_circuit_breaker_not_found(self, mock_registry):
        """Test resetting a nonexistent circuit breaker."""
        mock_registry.reset.return_value = False

        response = self.client.post("/api/v1/circuit-breakers/nonexistent/reset")

        self.assertEqual(response.status_code, 404)

    @patch("autonomous_control_plane.api.v1.circuit_breakers._registry")
    def test_reset_all_circuit_breakers(self, mock_registry):
        """Test resetting all circuit breakers."""
        response = self.client.post("/api/v1/circuit-breakers/bulk/reset-all")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("reset", data["message"].lower())

    @patch("autonomous_control_plane.api.v1.circuit_breakers._registry")
    def test_force_open_all_circuit_breakers(self, mock_registry):
        """Test forcing open all circuit breakers."""
        response = self.client.post("/api/v1/circuit-breakers/bulk/force-open-all")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("forced open", data["message"].lower())

    @patch("autonomous_control_plane.api.v1.circuit_breakers._registry")
    def test_force_close_all_circuit_breakers(self, mock_registry):
        """Test forcing close all circuit breakers."""
        response = self.client.post("/api/v1/circuit-breakers/bulk/force-close-all")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("forced closed", data["message"].lower())

    @patch("autonomous_control_plane.api.v1.circuit_breakers._registry")
    def test_get_all_health(self, mock_registry):
        """Test getting health for all circuit breakers."""
        mock_health = MagicMock()
        mock_health.is_healthy = True
        mock_health.to_dict.return_value = {
            "name": "service1",
            "is_healthy": True,
            "state": "closed",
        }
        mock_registry.get_all_health.return_value = {"service1": mock_health}

        response = self.client.get("/api/v1/circuit-breakers/health/all")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 1)
        self.assertTrue(data["overall_healthy"])

    @patch("autonomous_control_plane.api.v1.circuit_breakers._registry")
    def test_get_circuit_breaker_health_found(self, mock_registry):
        """Test getting health for a specific circuit breaker."""
        mock_health = MagicMock()
        mock_health.to_dict.return_value = {
            "name": "test_service",
            "is_healthy": True,
            "state": "closed",
        }
        mock_registry.get_health.return_value = mock_health

        response = self.client.get("/api/v1/circuit-breakers/health/test_service")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "test_service")

    @patch("autonomous_control_plane.api.v1.circuit_breakers._registry")
    def test_get_circuit_breaker_health_not_found(self, mock_registry):
        """Test getting health for a nonexistent circuit breaker."""
        mock_registry.get_health.return_value = None

        response = self.client.get("/api/v1/circuit-breakers/health/nonexistent")

        self.assertEqual(response.status_code, 404)

    @patch("autonomous_control_plane.api.v1.circuit_breakers._registry")
    def test_flush_telemetry(self, mock_registry):
        """Test flushing telemetry."""
        response = self.client.post("/api/v1/circuit-breakers/telemetry/flush")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("flushed", data["message"].lower())


if __name__ == "__main__":
    unittest.main()
