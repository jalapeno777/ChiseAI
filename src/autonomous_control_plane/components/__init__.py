"""Components module for the autonomous control plane.

ST-NS-038: Circuit Breaker Registry & Unified Telemetry
"""

from autonomous_control_plane.components.circuit_breaker_registry import (
    CircuitBreakerRegistry,
)

__all__ = ["CircuitBreakerRegistry"]
