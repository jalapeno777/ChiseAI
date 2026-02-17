"""Real-time signal generation module.

This module provides real-time signal generation capabilities that meet
the 75%+ confidence threshold requirement. Signals below 75% are logged
but not surfaced as actionable.

Exports:
    SignalGenerator: Main signal generation orchestrator
    SignalEmitter: Signal emission interface
    ConfidenceFilter: 75% actionable threshold filter
    DataFreshnessChecker: Data freshness validation
    Signal: Signal dataclass
    SignalStatus: Enum for signal status
    AsyncSignalProcessor: Async signal processing with concurrency control
    SignalPipeline: Async signal processing pipeline
"""

from signal_generation.confidence_filter import ConfidenceFilter
from signal_generation.data_freshness_check import DataFreshnessChecker, FreshnessResult
from signal_generation.models import Signal, SignalStatus
from signal_generation.pipeline import (
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
from signal_generation.signal_emitter import (
    DashboardEmitter,
    DiscordEmitter,
    SignalEmitter,
)
from signal_generation.signal_generator import SignalGenerator

__all__ = [
    # Signal Generator
    "SignalGenerator",
    # Signal Emitter
    "SignalEmitter",
    "DiscordEmitter",
    "DashboardEmitter",
    # Confidence Filter
    "ConfidenceFilter",
    # Data Freshness
    "DataFreshnessChecker",
    "FreshnessResult",
    # Models
    "Signal",
    "SignalStatus",
    # Async Pipeline (TASK-ST-NS-026-02)
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
