"""ICT (Inner Circle Trader) methodology implementations.

Provides core ICT concepts including liquidity analysis,
order flow, and market structure detection.
"""

import os

# Lazy imports to avoid circular dependencies
_collector_instance = None
_experiment_registry_instance = None
_experiment_factory_instance = None


def get_data_collector():
    """Get or create the global ICT data collector instance.

    The collector is only created if ICT_DATA_COLLECTION_ENABLED
    environment variable is set.

    Returns:
        ICTDataCollector instance or None if not enabled
    """
    global _collector_instance

    if not os.environ.get("ICT_DATA_COLLECTION_ENABLED"):
        return None

    if _collector_instance is None:
        from src.ict.data_collection import ICTDataCollector

        _collector_instance = ICTDataCollector()

    return _collector_instance


def get_experiment_registry():
    """Get or create the global experiment registry instance."""
    global _experiment_registry_instance

    if _experiment_registry_instance is None:
        from src.ict.experiments.registry import ExperimentRegistry

        _experiment_registry_instance = ExperimentRegistry()

    return _experiment_registry_instance


def get_experiment_factory():
    """Get or create the global experiment factory instance."""
    global _experiment_factory_instance

    if _experiment_factory_instance is None:
        from src.ict.experiments.factory import ExperimentFactory

        _experiment_factory_instance = ExperimentFactory()

    return _experiment_factory_instance


__all__ = [
    "get_data_collector",
    "get_experiment_registry",
    "get_experiment_factory",
]
