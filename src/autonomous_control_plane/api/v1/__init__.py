"""API v1 routes for the autonomous control plane.

ST-NS-038: Circuit Breaker Registry & Unified Telemetry
"""

from autonomous_control_plane.api.v1.circuit_breakers import (
    router as circuit_breakers_router,
)

__all__ = ["circuit_breakers_router"]
