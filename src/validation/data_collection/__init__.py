"""Data Collection Module for ICT Hypothesis Experiments.

This module provides infrastructure for collecting and tracking trading signals
for statistical validation of ICT methodology effectiveness.

Key Components:
- SignalTracker: Redis-based signal and outcome tracking
- ExperimentRunner: Experiment orchestration with early stopping
- ExperimentConfig: Configuration for experiment parameters

Usage:
    from validation.data_collection import SignalTracker, ExperimentRunner

    tracker = SignalTracker(redis_client)
    runner = ExperimentRunner(config=ExperimentConfig(), tracker=tracker)
"""

from validation.data_collection.experiment_runner import (
    ExperimentConfig,
    ExperimentRunner,
    ExperimentState,
)
from validation.data_collection.signal_tracker import (
    SignalGroup,
    SignalOutcome,
    SignalTracker,
    SignalType,
    TrackedSignal,
)

__all__ = [
    "SignalTracker",
    "SignalGroup",
    "SignalType",
    "TrackedSignal",
    "SignalOutcome",
    "ExperimentRunner",
    "ExperimentConfig",
    "ExperimentState",
]
