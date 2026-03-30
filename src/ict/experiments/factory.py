"""Experiment Factory.

Factory for creating ICT experiment instances by experiment ID.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.ict.experiments.b1_baseline import B1BaselineExperiment
from src.ict.experiments.b2_enhanced import B2EnhancedExperiment
from src.ict.experiments.b3_timeframe_variant import B3TimeframeExperiment
from src.ict.experiments.b4_signal_weight_variant import B4SignalWeightExperiment
from src.ict.experiments.b5_threshold_variant import B5ThresholdExperiment

if TYPE_CHECKING:
    from src.ict.data_collection.collector import ICTDataCollector
    from src.ict.experiments.registry import ExperimentRegistry

logger = logging.getLogger(__name__)


class ExperimentFactory:
    """Factory for creating ICT experiment instances.

    Maps experiment IDs to experiment class instances.
    """

    _EXPERIMENT_MAP = {
        "ICT-B1": B1BaselineExperiment,
        "ICT-B2": B2EnhancedExperiment,
        "ICT-B3": B3TimeframeExperiment,
        "ICT-B4": B4SignalWeightExperiment,
        "ICT-B5": B5ThresholdExperiment,
    }

    @classmethod
    def create_experiment(
        cls,
        experiment_id: str,
        collector: ICTDataCollector,
        registry: ExperimentRegistry | None = None,
        **kwargs,
    ):
        """Create an experiment instance by ID.

        Args:
            experiment_id: Experiment identifier (e.g., "ICT-B1")
            collector: ICT data collector instance
            registry: Optional experiment registry
            **kwargs: Additional arguments to pass to experiment constructor

        Returns:
            Experiment instance

        Raises:
            ValueError: If experiment_id is not recognized
        """
        experiment_class = cls._EXPERIMENT_MAP.get(experiment_id)
        if experiment_class is None:
            raise ValueError(
                f"Unknown experiment ID: {experiment_id}. "
                f"Available: {list(cls._EXPERIMENT_MAP.keys())}"
            )

        logger.info(f"Creating experiment {experiment_id}")
        return experiment_class(collector=collector, registry=registry, **kwargs)

    @classmethod
    def list_experiments(cls) -> list[str]:
        """List all available experiment IDs.

        Returns:
            List of experiment ID strings
        """
        return list(cls._EXPERIMENT_MAP.keys())

    @classmethod
    def is_valid_experiment(cls, experiment_id: str) -> bool:
        """Check if an experiment ID is valid.

        Args:
            experiment_id: Experiment identifier to check

        Returns:
            True if experiment ID is recognized
        """
        return experiment_id in cls._EXPERIMENT_MAP
