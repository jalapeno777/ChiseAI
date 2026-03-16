"""Strong AI System - Belief Embeddings Module.

Provides belief vector representation, validation, serialization,
and vector search capabilities for neural belief embeddings.
"""

from __future__ import annotations

from .cache import BeliefCache, CacheEntry, CacheMetrics
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
    "CacheEntry",
    "CacheMetrics",
    "BeliefMetadata",
    "BeliefPipeline",
    "BeliefSchema",
    "BeliefSearchIndex",
    "BeliefSerializer",
    "BeliefVector",
    "InMemoryBackend",
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
