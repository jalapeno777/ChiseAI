"""Autonomous Control Plane for ChiseAI.

Unified control plane consolidating fragmented resilience patterns
into a cohesive, continuously operating, self-correcting system.

ST-NS-038: Circuit Breaker Registry & Unified Telemetry
EP-NS-008: Autonomous Control Plane
"""

from autonomous_control_plane.components.failure_pattern_matcher import (
    FailurePatternMatcher,
)
from autonomous_control_plane.components.self_healing_engine import SelfHealingEngine
from autonomous_control_plane.models.healing import LogEntry

__version__ = "0.1.0"
__all__ = [
    "components",
    "models",
    "telemetry",
    "api",
    "config",
    "FailurePatternMatcher",
    "LogEntry",
    "SelfHealingEngine",
]
