"""Strong AI System - Belief Embeddings Module.

Provides belief vector representation, validation, and serialization
for neural belief embeddings.
"""

from __future__ import annotations

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
]
