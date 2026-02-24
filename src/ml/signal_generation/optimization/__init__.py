"""Signal generation optimization package.

Provides optimization utilities for signal generation pipeline
to ensure low-latency signal processing.
"""

from ml.signal_generation.optimization.async_generator import (
    AsyncSignalGenerator,
    GenerationConfig,
    GenerationResult,
    GenerationStatus,
)
from ml.signal_generation.optimization.pipeline_optimizer import (
    OptimizationResult,
    PipelineOptimizer,
    PipelineStage,
)

__all__ = [
    # Async Generator
    "AsyncSignalGenerator",
    "GenerationConfig",
    "GenerationResult",
    "GenerationStatus",
    # Pipeline Optimizer
    "PipelineOptimizer",
    "PipelineStage",
    "OptimizationResult",
]
