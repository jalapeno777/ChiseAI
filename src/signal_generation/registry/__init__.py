"""Signal generation registry module.

This module provides signal registration and management functionality
for the ICT signal generation system.
"""

from signal_generation.registry.ict_signal_registry import (
    FeatureFlagManager,
    ICTSignalRegistry,
    RegisteredSignal,
    SignalMetadata,
    get_ict_registry,
)
from signal_generation.registry.signal_types import (
    ICTSignalType,
    SignalSource,
    SignalType,
)

__all__ = [
    # Signal types
    "SignalType",
    "ICTSignalType",
    "SignalSource",
    # Registry classes
    "ICTSignalRegistry",
    "SignalMetadata",
    "RegisteredSignal",
    "FeatureFlagManager",
    # Registry functions
    "get_ict_registry",
]
