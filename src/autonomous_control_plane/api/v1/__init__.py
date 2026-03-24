"""API v1 routes for the autonomous control plane.

ST-NS-038: Circuit Breaker Registry & Unified Telemetry
"""

from autonomous_control_plane.api.v1.circuit_breakers import (
    get_registry,
    set_registry,
)
from autonomous_control_plane.api.v1.circuit_breakers import (
    router as circuit_breakers_router,
)
from autonomous_control_plane.api.v1.retry import (
    get_budget_manager,
    set_budget_manager,
)
from autonomous_control_plane.api.v1.rollback import (
    get_automation_coordinator,
    get_coordinator,
    set_automation_coordinator,
    set_coordinator,
)

__all__ = [
    "circuit_breakers_router",
    "set_registry",
    "get_registry",
    "set_budget_manager",
    "get_budget_manager",
    "set_coordinator",
    "get_coordinator",
    "set_automation_coordinator",
    "get_automation_coordinator",
]
