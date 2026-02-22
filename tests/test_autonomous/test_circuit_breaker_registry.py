"""Unit tests for Circuit Breaker Registry.

ST-NS-038: Circuit Breaker Registry & Unified Telemetry
"""

import unittest
from unittest.mock import MagicMock, patch

from autonomous_control_plane.components.circuit_breaker_registry import (
    CircuitBreakerRegistry,
)
from autonomous_control_plane.models.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitBreakerState,
    CircuitBreakerStateModel,
)


class TestCircuitBreakerRegistry(unittest.TestCase):
    """Test cases for CircuitBreakerRegistry."""

    def setUp(self):
        """Set up test fixtures."""
        # Reset singleton completely
        CircuitBreakerRegistry._instance = None
        # Reset any existing instance's _initialized flag
        if (
            hasattr(CircuitBreakerRegistry, "_instance")
            and CircuitBreakerRegistry._instance is not None
        ):
            CircuitBreakerRegistry._instance._initialized = False
        self.mock_redis = MagicMock()
        self.mock_influxdb = MagicMock()

    def tearDown(self):
        """Tear down test fixtures."""
        CircuitBreakerRegistry._instance = None

    @patch("autonomous_control_plane.components.circuit_breaker_registry.settings")
    def test_register_circuit_breaker(self, mock_settings):
        """Test registering a new circuit breaker."""
        mock_settings.cb_registry_key_prefix = "acp:cb:"
        mock_settings.telemetry.enabled = False

        registry = CircuitBreakerRegistry(
            redis_client=self.mock_redis,
            influxdb_client=None,
        )

        cb = registry.register("test_service", CircuitBreakerConfig())

        self.assertEqual(cb.name, "test_service")
        self.assertEqual(cb.state, CircuitBreakerState.CLOSED)
        self.assertIsNotNone(cb.metrics)

    @patch("autonomous_control_plane.components.circuit_breaker_registry.settings")
    def test_get_circuit_breaker(self, mock_settings):
        """Test getting a circuit breaker."""
        mock_settings.cb_registry_key_prefix = "acp:cb:"
        mock_settings.telemetry.enabled = False

        registry = CircuitBreakerRegistry(
            redis_client=self.mock_redis,
            influxdb_client=None,
        )

        registry.register("test_service")
        cb = registry.get("test_service")

        self.assertIsNotNone(cb)
        self.assertEqual(cb.name, "test_service")

    @patch("autonomous_control_plane.components.circuit_breaker_registry.settings")
    def test_get_nonexistent_circuit_breaker(self, mock_settings):
        """Test getting a nonexistent circuit breaker returns None."""
        mock_settings.cb_registry_key_prefix = "acp:cb:"
        mock_settings.telemetry.enabled = False

        registry = CircuitBreakerRegistry(
            redis_client=self.mock_redis,
            influxdb_client=None,
        )

        cb = registry.get("nonexistent")

        self.assertIsNone(cb)

    @patch("autonomous_control_plane.components.circuit_breaker_registry.settings")
    def test_get_all_states(self, mock_settings):
        """Test getting all circuit breaker states."""
        mock_settings.cb_registry_key_prefix = "acp:cb:"
        mock_settings.telemetry.enabled = False

        registry = CircuitBreakerRegistry(
            redis_client=self.mock_redis,
            influxdb_client=None,
        )

        registry.register("service1")
        registry.register("service2")

        states = registry.get_all_states()

        self.assertEqual(len(states), 2)
        self.assertIn("service1", states)
        self.assertIn("service2", states)

    @patch("autonomous_control_plane.components.circuit_breaker_registry.settings")
    def test_force_open(self, mock_settings):
        """Test forcing a circuit breaker open."""
        mock_settings.cb_registry_key_prefix = "acp:cb:"
        mock_settings.telemetry.enabled = False

        registry = CircuitBreakerRegistry(
            redis_client=self.mock_redis,
            influxdb_client=None,
        )

        registry.register("test_service")
        result = registry.force_open("test_service", "manual_test")

        self.assertTrue(result)
        cb = registry.get("test_service")
        self.assertEqual(cb.state, CircuitBreakerState.OPEN)

    @patch("autonomous_control_plane.components.circuit_breaker_registry.settings")
    def test_force_close(self, mock_settings):
        """Test forcing a circuit breaker closed."""
        mock_settings.cb_registry_key_prefix = "acp:cb:"
        mock_settings.telemetry.enabled = False

        registry = CircuitBreakerRegistry(
            redis_client=self.mock_redis,
            influxdb_client=None,
        )

        registry.register("test_service")
        registry.force_open("test_service")
        result = registry.force_close("test_service", "manual_test")

        self.assertTrue(result)
        cb = registry.get("test_service")
        self.assertEqual(cb.state, CircuitBreakerState.CLOSED)

    @patch("autonomous_control_plane.components.circuit_breaker_registry.settings")
    def test_reset(self, mock_settings):
        """Test resetting a circuit breaker."""
        mock_settings.cb_registry_key_prefix = "acp:cb:"
        mock_settings.telemetry.enabled = False

        registry = CircuitBreakerRegistry(
            redis_client=self.mock_redis,
            influxdb_client=None,
        )

        registry.register("test_service")
        registry.record_failure("test_service", "test error")
        result = registry.reset("test_service")

        self.assertTrue(result)
        cb = registry.get("test_service")
        self.assertEqual(cb.state, CircuitBreakerState.CLOSED)
        self.assertEqual(cb.metrics.failure_count, 0)

    @patch("autonomous_control_plane.components.circuit_breaker_registry.settings")
    def test_record_success(self, mock_settings):
        """Test recording a success."""
        mock_settings.cb_registry_key_prefix = "acp:cb:"
        mock_settings.telemetry.enabled = False

        registry = CircuitBreakerRegistry(
            redis_client=self.mock_redis,
            influxdb_client=None,
        )

        registry.register("test_service")
        registry.record_success("test_service")

        cb = registry.get("test_service")
        self.assertEqual(cb.metrics.success_count, 1)

    @patch("autonomous_control_plane.components.circuit_breaker_registry.settings")
    def test_record_failure_opens_circuit(self, mock_settings):
        """Test that recording failures opens the circuit."""
        mock_settings.cb_registry_key_prefix = "acp:cb:"
        mock_settings.telemetry.enabled = False

        # Create registry with low threshold
        registry = CircuitBreakerRegistry(
            redis_client=self.mock_redis,
            influxdb_client=None,
        )

        config = CircuitBreakerConfig(failure_threshold=3)
        registry.register("test_service", config)

        # Record 3 failures
        registry.record_failure("test_service", "error 1")
        registry.record_failure("test_service", "error 2")
        registry.record_failure("test_service", "error 3")

        cb = registry.get("test_service")
        self.assertEqual(cb.state, CircuitBreakerState.OPEN)

    @patch("autonomous_control_plane.components.circuit_breaker_registry.settings")
    def test_can_execute_in_closed_state(self, mock_settings):
        """Test can_execute returns True in CLOSED state."""
        mock_settings.cb_registry_key_prefix = "acp:cb:"
        mock_settings.telemetry.enabled = False

        registry = CircuitBreakerRegistry(
            redis_client=self.mock_redis,
            influxdb_client=None,
        )

        registry.register("test_service")

        self.assertTrue(registry.can_execute("test_service"))

    @patch("autonomous_control_plane.components.circuit_breaker_registry.settings")
    def test_can_execute_in_open_state(self, mock_settings):
        """Test can_execute returns False in OPEN state."""
        mock_settings.cb_registry_key_prefix = "acp:cb:"
        mock_settings.telemetry.enabled = False

        registry = CircuitBreakerRegistry(
            redis_client=self.mock_redis,
            influxdb_client=None,
        )

        registry.register("test_service")
        registry.force_open("test_service")

        self.assertFalse(registry.can_execute("test_service"))

    @patch("autonomous_control_plane.components.circuit_breaker_registry.settings")
    def test_reset_all(self, mock_settings):
        """Test resetting all circuit breakers."""
        mock_settings.cb_registry_key_prefix = "acp:cb:"
        mock_settings.telemetry.enabled = False

        registry = CircuitBreakerRegistry(
            redis_client=self.mock_redis,
            influxdb_client=None,
        )

        registry.register("service1")
        registry.register("service2")

        registry.record_failure("service1", "error")
        registry.force_open("service2")

        registry.reset_all()

        cb1 = registry.get("service1")
        cb2 = registry.get("service2")

        self.assertEqual(cb1.state, CircuitBreakerState.CLOSED)
        self.assertEqual(cb2.state, CircuitBreakerState.CLOSED)

    @patch("autonomous_control_plane.components.circuit_breaker_registry.settings")
    def test_force_open_all(self, mock_settings):
        """Test forcing all circuit breakers open."""
        mock_settings.cb_registry_key_prefix = "acp:cb:"
        mock_settings.telemetry.enabled = False

        registry = CircuitBreakerRegistry(
            redis_client=self.mock_redis,
            influxdb_client=None,
        )

        registry.register("service1")
        registry.register("service2")

        registry.force_open_all("bulk_test")

        cb1 = registry.get("service1")
        cb2 = registry.get("service2")

        self.assertEqual(cb1.state, CircuitBreakerState.OPEN)
        self.assertEqual(cb2.state, CircuitBreakerState.OPEN)

    @patch("autonomous_control_plane.components.circuit_breaker_registry.settings")
    def test_force_close_all(self, mock_settings):
        """Test forcing all circuit breakers closed."""
        mock_settings.cb_registry_key_prefix = "acp:cb:"
        mock_settings.telemetry.enabled = False

        registry = CircuitBreakerRegistry(
            redis_client=self.mock_redis,
            influxdb_client=None,
        )

        registry.register("service1")
        registry.register("service2")
        registry.force_open("service1")
        registry.force_open("service2")

        registry.force_close_all("bulk_test")

        cb1 = registry.get("service1")
        cb2 = registry.get("service2")

        self.assertEqual(cb1.state, CircuitBreakerState.CLOSED)
        self.assertEqual(cb2.state, CircuitBreakerState.CLOSED)

    @patch("autonomous_control_plane.components.circuit_breaker_registry.settings")
    def test_unregister(self, mock_settings):
        """Test unregistering a circuit breaker."""
        mock_settings.cb_registry_key_prefix = "acp:cb:"
        mock_settings.telemetry.enabled = False

        registry = CircuitBreakerRegistry(
            redis_client=self.mock_redis,
            influxdb_client=None,
        )

        registry.register("test_service")
        result = registry.unregister("test_service")

        self.assertIsNotNone(result)
        self.assertIsNone(registry.get("test_service"))

    @patch("autonomous_control_plane.components.circuit_breaker_registry.settings")
    def test_get_health_closed_state(self, mock_settings):
        """Test health check for closed circuit breaker."""
        mock_settings.cb_registry_key_prefix = "acp:cb:"
        mock_settings.telemetry.enabled = False

        registry = CircuitBreakerRegistry(
            redis_client=self.mock_redis,
            influxdb_client=None,
        )

        registry.register("test_service")
        health = registry.get_health("test_service")

        self.assertIsNotNone(health)
        self.assertTrue(health.is_healthy)
        self.assertEqual(health.state, CircuitBreakerState.CLOSED)

    @patch("autonomous_control_plane.components.circuit_breaker_registry.settings")
    def test_get_health_open_state(self, mock_settings):
        """Test health check for open circuit breaker."""
        mock_settings.cb_registry_key_prefix = "acp:cb:"
        mock_settings.telemetry.enabled = False

        registry = CircuitBreakerRegistry(
            redis_client=self.mock_redis,
            influxdb_client=None,
        )

        registry.register("test_service")
        registry.force_open("test_service")

        health = registry.get_health("test_service")

        self.assertIsNotNone(health)
        self.assertFalse(health.is_healthy)
        self.assertEqual(health.state, CircuitBreakerState.OPEN)

    @patch("autonomous_control_plane.components.circuit_breaker_registry.settings")
    def test_record_rejection(self, mock_settings):
        """Test recording a rejection."""
        mock_settings.cb_registry_key_prefix = "acp:cb:"
        mock_settings.telemetry.enabled = False

        registry = CircuitBreakerRegistry(
            redis_client=self.mock_redis,
            influxdb_client=None,
        )

        registry.register("test_service")
        registry.record_rejection("test_service")

        cb = registry.get("test_service")
        self.assertEqual(cb.metrics.rejection_count, 1)

    @patch("autonomous_control_plane.components.circuit_breaker_registry.settings")
    def test_get_all_health(self, mock_settings):
        """Test getting health for all circuit breakers."""
        mock_settings.cb_registry_key_prefix = "acp:cb:"
        mock_settings.telemetry.enabled = False

        registry = CircuitBreakerRegistry(
            redis_client=self.mock_redis,
            influxdb_client=None,
        )

        registry.register("service1")
        registry.register("service2")
        registry.force_open("service1")

        health = registry.get_all_health()

        self.assertEqual(len(health), 2)
        self.assertFalse(health["service1"].is_healthy)
        self.assertTrue(health["service2"].is_healthy)

    @patch("autonomous_control_plane.components.circuit_breaker_registry.settings")
    def test_get_all_health_empty(self, mock_settings):
        """Test getting health when no circuit breakers exist."""
        mock_settings.cb_registry_key_prefix = "acp:cb:"
        mock_settings.telemetry.enabled = False

        registry = CircuitBreakerRegistry(
            redis_client=self.mock_redis,
            influxdb_client=None,
        )

        health = registry.get_all_health()

        self.assertEqual(len(health), 0)

    @patch("autonomous_control_plane.components.circuit_breaker_registry.settings")
    def test_flush_telemetry(self, mock_settings):
        """Test flushing telemetry."""
        mock_settings.cb_registry_key_prefix = "acp:cb:"
        mock_settings.telemetry.enabled = False

        registry = CircuitBreakerRegistry(
            redis_client=self.mock_redis,
            influxdb_client=None,
        )

        registry.register("test_service")
        # Should not raise exception
        registry.flush_telemetry()

    @patch("autonomous_control_plane.components.circuit_breaker_registry.settings")
    def test_record_success_unknown_circuit_breaker(self, mock_settings):
        """Test recording success for unknown circuit breaker."""
        mock_settings.cb_registry_key_prefix = "acp:cb:"
        mock_settings.telemetry.enabled = False

        registry = CircuitBreakerRegistry(
            redis_client=self.mock_redis,
            influxdb_client=None,
        )

        # Should not raise exception
        registry.record_success("nonexistent")

    @patch("autonomous_control_plane.components.circuit_breaker_registry.settings")
    def test_record_failure_unknown_circuit_breaker(self, mock_settings):
        """Test recording failure for unknown circuit breaker."""
        mock_settings.cb_registry_key_prefix = "acp:cb:"
        mock_settings.telemetry.enabled = False

        registry = CircuitBreakerRegistry(
            redis_client=self.mock_redis,
            influxdb_client=None,
        )

        # Should not raise exception
        registry.record_failure("nonexistent", "error")

    @patch("autonomous_control_plane.components.circuit_breaker_registry.settings")
    def test_record_rejection_unknown_circuit_breaker(self, mock_settings):
        """Test recording rejection for unknown circuit breaker."""
        mock_settings.cb_registry_key_prefix = "acp:cb:"
        mock_settings.telemetry.enabled = False

        registry = CircuitBreakerRegistry(
            redis_client=self.mock_redis,
            influxdb_client=None,
        )

        # Should not raise exception
        registry.record_rejection("nonexistent")

    @patch("autonomous_control_plane.components.circuit_breaker_registry.settings")
    def test_force_open_unknown_circuit_breaker(self, mock_settings):
        """Test forcing open unknown circuit breaker."""
        mock_settings.cb_registry_key_prefix = "acp:cb:"
        mock_settings.telemetry.enabled = False

        registry = CircuitBreakerRegistry(
            redis_client=self.mock_redis,
            influxdb_client=None,
        )

        result = registry.force_open("nonexistent")
        self.assertFalse(result)

    @patch("autonomous_control_plane.components.circuit_breaker_registry.settings")
    def test_force_close_unknown_circuit_breaker(self, mock_settings):
        """Test forcing close unknown circuit breaker."""
        mock_settings.cb_registry_key_prefix = "acp:cb:"
        mock_settings.telemetry.enabled = False

        registry = CircuitBreakerRegistry(
            redis_client=self.mock_redis,
            influxdb_client=None,
        )

        result = registry.force_close("nonexistent")
        self.assertFalse(result)

    @patch("autonomous_control_plane.components.circuit_breaker_registry.settings")
    def test_reset_unknown_circuit_breaker(self, mock_settings):
        """Test resetting unknown circuit breaker."""
        mock_settings.cb_registry_key_prefix = "acp:cb:"
        mock_settings.telemetry.enabled = False

        registry = CircuitBreakerRegistry(
            redis_client=self.mock_redis,
            influxdb_client=None,
        )

        result = registry.reset("nonexistent")
        self.assertFalse(result)

    @patch("autonomous_control_plane.components.circuit_breaker_registry.settings")
    def test_get_health_unknown_circuit_breaker(self, mock_settings):
        """Test getting health for unknown circuit breaker."""
        mock_settings.cb_registry_key_prefix = "acp:cb:"
        mock_settings.telemetry.enabled = False

        registry = CircuitBreakerRegistry(
            redis_client=self.mock_redis,
            influxdb_client=None,
        )

        health = registry.get_health("nonexistent")
        self.assertIsNone(health)

    @patch("autonomous_control_plane.components.circuit_breaker_registry.settings")
    def test_can_execute_unknown_circuit_breaker(self, mock_settings):
        """Test can_execute for unknown circuit breaker allows execution."""
        mock_settings.cb_registry_key_prefix = "acp:cb:"
        mock_settings.telemetry.enabled = False

        registry = CircuitBreakerRegistry(
            redis_client=self.mock_redis,
            influxdb_client=None,
        )

        # Unknown circuit breaker should allow execution
        result = registry.can_execute("nonexistent")
        self.assertTrue(result)

    @patch("autonomous_control_plane.components.circuit_breaker_registry.settings")
    def test_event_handlers(self, mock_settings):
        """Test event handler registration and emission."""
        mock_settings.cb_registry_key_prefix = "acp:cb:"
        mock_settings.telemetry.enabled = False

        registry = CircuitBreakerRegistry(
            redis_client=self.mock_redis,
            influxdb_client=None,
        )

        events = []

        def handler(event):
            events.append(event)

        registry.register_event_handler(handler)
        registry.register("test_service")
        registry.force_open("test_service")

        self.assertGreater(len(events), 0)

        # Unregister handler
        registry.unregister_event_handler(handler)
        registry.force_close("test_service")

        # No new events should have been added
        event_count = len(events)
        registry.force_open("test_service")
        self.assertEqual(len(events), event_count)

    @patch("autonomous_control_plane.components.circuit_breaker_registry.settings")
    def test_health_recommendations(self, mock_settings):
        """Test health recommendations for different states."""
        mock_settings.cb_registry_key_prefix = "acp:cb:"
        mock_settings.telemetry.enabled = False

        registry = CircuitBreakerRegistry(
            redis_client=self.mock_redis,
            influxdb_client=None,
        )

        # Test OPEN state recommendation
        registry.register("open_service")
        registry.force_open("open_service")
        health_open = registry.get_health("open_service")
        self.assertIn("Investigate", health_open.recommendation)

        # Test healthy recommendation
        registry.register("healthy_service")
        health_healthy = registry.get_health("healthy_service")
        self.assertIn("Healthy", health_healthy.recommendation)

    @patch("autonomous_control_plane.components.circuit_breaker_registry.settings")
    def test_force_open_already_open(self, mock_settings):
        """Test forcing open when already open."""
        mock_settings.cb_registry_key_prefix = "acp:cb:"
        mock_settings.telemetry.enabled = False

        registry = CircuitBreakerRegistry(
            redis_client=self.mock_redis,
            influxdb_client=None,
        )

        registry.register("test_service")
        registry.force_open("test_service")

        # Force open again - should still return True
        result = registry.force_open("test_service")
        self.assertTrue(result)

    @patch("autonomous_control_plane.components.circuit_breaker_registry.settings")
    def test_force_close_already_closed(self, mock_settings):
        """Test forcing close when already closed."""
        mock_settings.cb_registry_key_prefix = "acp:cb:"
        mock_settings.telemetry.enabled = False

        registry = CircuitBreakerRegistry(
            redis_client=self.mock_redis,
            influxdb_client=None,
        )

        registry.register("test_service")

        # Force close when already closed - should still return True
        result = registry.force_close("test_service")
        self.assertTrue(result)

    @patch("autonomous_control_plane.components.circuit_breaker_registry.settings")
    def test_register_duplicate(self, mock_settings):
        """Test registering a circuit breaker that already exists."""
        mock_settings.cb_registry_key_prefix = "acp:cb:"
        mock_settings.telemetry.enabled = False

        registry = CircuitBreakerRegistry(
            redis_client=self.mock_redis,
            influxdb_client=None,
        )

        cb1 = registry.register("test_service")
        cb2 = registry.register("test_service")

        # Should return the same circuit breaker
        self.assertIs(cb1, cb2)

    @patch("autonomous_control_plane.components.circuit_breaker_registry.settings")
    def test_get_all_states_dict(self, mock_settings):
        """Test getting all states as dictionaries."""
        mock_settings.cb_registry_key_prefix = "acp:cb:"
        mock_settings.telemetry.enabled = False

        registry = CircuitBreakerRegistry(
            redis_client=self.mock_redis,
            influxdb_client=None,
        )

        registry.register("service1")
        registry.register("service2")

        states_dict = registry.get_all_states_dict()

        self.assertEqual(len(states_dict), 2)
        self.assertIn("service1", states_dict)
        self.assertIn("service2", states_dict)
        self.assertIsInstance(states_dict["service1"], dict)


class TestCircuitBreakerModels(unittest.TestCase):
    """Test cases for circuit breaker models."""

    def test_circuit_breaker_config_to_dict(self):
        """Test CircuitBreakerConfig to_dict."""
        config = CircuitBreakerConfig(
            failure_threshold=10,
            timeout_seconds=30.0,
            half_open_max_calls=5,
        )

        result = config.to_dict()

        self.assertEqual(result["failure_threshold"], 10)
        self.assertEqual(result["timeout_seconds"], 30.0)
        self.assertEqual(result["half_open_max_calls"], 5)

    def test_circuit_breaker_config_from_dict(self):
        """Test CircuitBreakerConfig from_dict."""
        data = {
            "failure_threshold": 10,
            "timeout_seconds": 30.0,
            "half_open_max_calls": 5,
            "expected_exception": "ValueError",
        }

        config = CircuitBreakerConfig.from_dict(data)

        self.assertEqual(config.failure_threshold, 10)
        self.assertEqual(config.timeout_seconds, 30.0)
        self.assertEqual(config.half_open_max_calls, 5)

    def test_circuit_breaker_state_model_to_dict(self):
        """Test CircuitBreakerStateModel to_dict."""
        from autonomous_control_plane.models.circuit_breaker import (
            CircuitBreakerMetrics,
        )

        state = CircuitBreakerStateModel(
            name="test",
            state=CircuitBreakerState.CLOSED,
            config=CircuitBreakerConfig(),
            metrics=CircuitBreakerMetrics(),
        )

        result = state.to_dict()

        self.assertEqual(result["name"], "test")
        self.assertEqual(result["state"], "closed")


if __name__ == "__main__":
    unittest.main()
