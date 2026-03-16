"""Strong AI System - Belief Embeddings Module.

Provides belief vector representation, validation, serialization,
and vector search capabilities for neural belief embeddings.
"""

from __future__ import annotations

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
    "BeliefMetadata",
    "BeliefSchema",
    "BeliefVector",
    "ValidationError",
    "to_dict",
    "from_dict",
    "to_json",
    "from_json",
    "save_to_file",
    "load_from_file",
    "BeliefSerializer",
    "BeliefSearchIndex",
    "SearchResult",
    "InMemoryBackend",
    "QdrantBackend",
]
