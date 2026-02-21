"""Circuit Breaker Registry for centralized CB management."""

from typing import Dict, Optional
from datetime import datetime
from src.autonomous_control_plane.models.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerState,
)


class CircuitBreakerRegistry:
    """Centralized registry for all circuit breakers."""

    _instance = None
    _circuit_breakers: Dict[str, CircuitBreaker] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def register(self, name: str, config: CircuitBreakerConfig) -> CircuitBreaker:
        """Register a new circuit breaker."""
        if name in self._circuit_breakers:
            raise ValueError(f"Circuit breaker '{name}' already registered")

        cb = CircuitBreaker(config=config)
        self._circuit_breakers[name] = cb
        return cb

    def get(self, name: str) -> Optional[CircuitBreaker]:
        """Get a circuit breaker by name."""
        return self._circuit_breakers.get(name)

    def get_all_states(self) -> Dict[str, str]:
        """Get all circuit breaker states."""
        return {name: cb.state.value for name, cb in self._circuit_breakers.items()}

    def force_open(self, name: str) -> None:
        """Manually open a circuit breaker."""
        if name not in self._circuit_breakers:
            raise KeyError(f"Circuit breaker '{name}' not found")
        self._circuit_breakers[name].state = CircuitBreakerState.OPEN

    def force_close(self, name: str) -> None:
        """Manually close a circuit breaker."""
        if name not in self._circuit_breakers:
            raise KeyError(f"Circuit breaker '{name}' not found")
        cb = self._circuit_breakers[name]
        cb.state = CircuitBreakerState.CLOSED
        cb.failure_count = 0
        cb.success_count = 0

    def reset_all(self) -> None:
        """Reset all circuit breakers to closed state."""
        for cb in self._circuit_breakers.values():
            cb.state = CircuitBreakerState.CLOSED
            cb.failure_count = 0
            cb.success_count = 0

    def transition_to_half_open(self, name: str) -> bool:
        """Transition a circuit breaker to half-open state."""
        if name not in self._circuit_breakers:
            return False
        cb = self._circuit_breakers[name]
        if cb.state == CircuitBreakerState.OPEN:
            if cb.last_failure_time:
                elapsed = (datetime.utcnow() - cb.last_failure_time).total_seconds()
                if elapsed >= cb.config.recovery_timeout:
                    cb.state = CircuitBreakerState.HALF_OPEN
                    cb.success_count = 0
                    return True
        return False
