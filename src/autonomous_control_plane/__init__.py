"""Autonomous Control Plane for ChiseAI.

Unified control plane consolidating fragmented resilience patterns
into a cohesive, continuously operating, self-correcting system.

ST-NS-038: Circuit Breaker Registry & Unified Telemetry
EP-NS-008: Autonomous Control Plane
"""

# Note: Imports deferred to avoid circular import issues
# Import directly from submodules as needed:
#   from autonomous_control_plane.config.settings import Settings
#   from autonomous_control_plane.core.orchestrator import ACPOrchestrator
#   from autonomous_control_plane.events.bus import EventBus

__version__ = "0.1.0"
__all__ = [
    "components",
    "models",
    "telemetry",
    "api",
    "config",
    "core",
    "events",
]
