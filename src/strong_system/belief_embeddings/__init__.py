"""Strong AI System - Belief Embeddings Module.

Provides belief vector representation, validation, serialization,
vector search, and clustering capabilities for neural belief embeddings.
"""

from __future__ import annotations

from .cache import BeliefCache, CacheEntry, CacheMetrics
from .clustering import (
    BeliefClusteringEngine,
    ClusterAssignment,
    ClusteringError,
    ClusterMetrics,
)
from .index import (
    BeliefIndex,
    ClusterInfo,
    HierarchicalLevel,
    IndexError,
)
from .pipeline import (
    BeliefPipeline,
    PipelineConfig,
    PipelineMetrics,
    PipelineStage,
    ProcessingResult,
)
from .search import (
    BeliefSearchIndex,
    InMemoryBackend,
    QdrantBackend,
    SearchResult,
)
from .serialization import (
    BeliefSerializer,
    from_dict,
    from_json,
    load_from_file,
    save_to_file,
    to_dict,
    to_json,
)
from .vector import (
    BeliefMetadata,
    BeliefSchema,
    BeliefVector,
    ValidationError,
)

__all__ = [
    "BeliefCache",
    "BeliefClusteringEngine",
    "BeliefIndex",
    "BeliefMetadata",
    "BeliefPipeline",
    "BeliefSchema",
    "BeliefSearchIndex",
    "BeliefSerializer",
    "BeliefVector",
    "CacheEntry",
    "CacheMetrics",
    "ClusterAssignment",
    "ClusterInfo",
    "ClusterMetrics",
    "ClusteringError",
    "HierarchicalLevel",
    "InMemoryBackend",
    "IndexError",
    "PipelineConfig",
    "PipelineMetrics",
    "PipelineStage",
    "ProcessingResult",
    "QdrantBackend",
    "SearchResult",
    "ValidationError",
    "from_dict",
    "from_json",
    "load_from_file",
    "save_to_file",
    "to_dict",
    "to_json",
]
