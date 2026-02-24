"""Multi-modal data types and utilities for signal fusion.

This module provides data structures and types for handling
multi-modal signals from technical, sentiment, and on-chain sources.
"""

from src.neuro_symbolic.multimodal.types import (
    EncodedSignal,
    FusionWeights,
    ModalityType,
    MultiModalSignal,
    SignalBatch,
    SignalMetadata,
    TemporalContext,
)

__all__ = [
    "ModalityType",
    "SignalMetadata",
    "TemporalContext",
    "MultiModalSignal",
    "EncodedSignal",
    "SignalBatch",
    "FusionWeights",
]
