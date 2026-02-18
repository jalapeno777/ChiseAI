"""Signal processing pipeline with async support.

This module provides the SignalPipeline class for orchestrating
signal generation, processing, and delivery. It integrates with
the async processor for concurrent signal handling.

For TASK-ST-NS-026-02: Async Signal Processing Pipeline
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

# Re-export AsyncSignalProcessor and SignalPipeline from async_processor
# This maintains backward compatibility while centralizing the implementation
from signal_generation.async_processor import (
    AsyncSignalProcessor,
    DeliveryResult,
    EnrichedSignal,
    ProcessingMetrics,
    ProcessingStage,
    SignalPipeline,
    SignalPriority,
    SignalResult,
    ValidationResult,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

__all__ = [
    "AsyncSignalProcessor",
    "SignalPipeline",
    "SignalResult",
    "ValidationResult",
    "EnrichedSignal",
    "DeliveryResult",
    "ProcessingMetrics",
    "ProcessingStage",
    "SignalPriority",
]
