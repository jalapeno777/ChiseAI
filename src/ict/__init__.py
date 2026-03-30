"""ICT (Inner Circle Trader) methodology implementations.

Provides core ICT concepts including liquidity analysis,
order flow, and market structure detection.
"""

import os

# Lazy imports for data collection to avoid circular dependencies
_collector_instance = None


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


# Import experiment components for convenience
from src.ict.experiments import ExperimentKey, ExperimentRegistry
from src.ict.experiments.factory import ExperimentFactory

__all__ = [
    "ICTDataCollector",
    "get_data_collector",
    "ExperimentKey",
    "ExperimentRegistry",
    "ExperimentFactory",
]
