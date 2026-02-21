"""Tests for Circuit Breaker Registry (ST-NS-038)."""

import pytest
from datetime import datetime, timedelta
from src.autonomous_control_plane.models.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerState,
)
from src.autonomous_control_plane.components.circuit_breaker_registry import (
    CircuitBreakerRegistry,
)


class TestCircuitBreakerModels:
    """Test circuit breaker data models."""

    def test_circuit_breaker_state_enum(self):
        assert CircuitBreakerState.CLOSED.value == "closed"
        assert CircuitBreakerState.OPEN.value == "open"
        assert CircuitBreakerState.HALF_OPEN.value == "half_open"

    def test_circuit_breaker_config_defaults(self):
        config = CircuitBreakerConfig(name="test")
        assert config.failure_threshold == 5
        assert config.recovery_timeout == 60
        assert config.half_open_max_calls == 3

    def test_circuit_breaker_creation(self):
        config = CircuitBreakerConfig(name="test")
        cb = CircuitBreaker(config=config)
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.failure_count == 0
        assert cb.can_execute() is True

    def test_circuit_breaker_record_success(self):
        config = CircuitBreakerConfig(name="test")
        cb = CircuitBreaker(config=config)
        cb.record_success()
        assert cb.failure_count == 0

    def test_circuit_breaker_record_failure(self):
        config = CircuitBreakerConfig(name="test", failure_threshold=3)
        cb = CircuitBreaker(config=config)
        cb.record_failure()
        assert cb.failure_count == 1
        assert cb.state == CircuitBreakerState.CLOSED

    def test_circuit_breaker_opens_after_threshold(self):
        config = CircuitBreakerConfig(name="test", failure_threshold=2)
        cb = CircuitBreaker(config=config)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN
        assert cb.can_execute() is False


class TestCircuitBreakerRegistry:
    """Test circuit breaker registry functionality."""

    def setup_method(self):
        # Reset singleton for each test
        CircuitBreakerRegistry._instance = None
        CircuitBreakerRegistry._circuit_breakers = {}

    def test_registry_singleton(self):
        reg1 = CircuitBreakerRegistry()
        reg2 = CircuitBreakerRegistry()
        assert reg1 is reg2

    def test_register_circuit_breaker(self):
        registry = CircuitBreakerRegistry()
        config = CircuitBreakerConfig(name="test-service")
        cb = registry.register("test-service", config)
        assert cb.config.name == "test-service"

    def test_register_duplicate_raises_error(self):
        registry = CircuitBreakerRegistry()
        config = CircuitBreakerConfig(name="test")
        registry.register("test", config)
        with pytest.raises(ValueError, match="already registered"):
            registry.register("test", config)

    def test_get_circuit_breaker(self):
        registry = CircuitBreakerRegistry()
        config = CircuitBreakerConfig(name="test")
        registry.register("test", config)
        cb = registry.get("test")
        assert cb is not None

    def test_get_nonexistent_returns_none(self):
        registry = CircuitBreakerRegistry()
        cb = registry.get("nonexistent")
        assert cb is None

    def test_get_all_states(self):
        registry = CircuitBreakerRegistry()
        registry.register("svc1", CircuitBreakerConfig(name="svc1"))
        registry.register("svc2", CircuitBreakerConfig(name="svc2"))
        states = registry.get_all_states()
        assert len(states) == 2
        assert states["svc1"] == "closed"

    def test_force_open(self):
        registry = CircuitBreakerRegistry()
        registry.register("test", CircuitBreakerConfig(name="test"))
        registry.force_open("test")
        cb = registry.get("test")
        assert cb.state == CircuitBreakerState.OPEN

    def test_force_close(self):
        registry = CircuitBreakerRegistry()
        registry.register("test", CircuitBreakerConfig(name="test"))
        registry.force_open("test")
        registry.force_close("test")
        cb = registry.get("test")
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.failure_count == 0

    def test_reset_all(self):
        registry = CircuitBreakerRegistry()
        registry.register("svc1", CircuitBreakerConfig(name="svc1"))
        registry.register("svc2", CircuitBreakerConfig(name="svc2"))
        registry.force_open("svc1")
        registry.reset_all()
        assert registry.get("svc1").state == CircuitBreakerState.CLOSED
        assert registry.get("svc2").state == CircuitBreakerState.CLOSED

    def test_transition_to_half_open(self):
        registry = CircuitBreakerRegistry()
        config = CircuitBreakerConfig(name="test", recovery_timeout=0)
        registry.register("test", config)
        registry.force_open("test")
        # Manually set last_failure_time to past
        cb = registry.get("test")
        cb.last_failure_time = datetime.utcnow() - timedelta(seconds=1)
        result = registry.transition_to_half_open("test")
        assert result is True
        assert cb.state == CircuitBreakerState.HALF_OPEN
