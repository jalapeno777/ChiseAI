"""ICT Experiments module.

Provides experiment infrastructure for ICT methodology testing,
including experiment keys, registry, and variant implementations.
"""

from src.ict.experiments.key_schema import ExperimentKey
from src.ict.experiments.registry import ExperimentRegistry

__all__ = ["ExperimentKey", "ExperimentRegistry"]
