"""Unit tests for autonomous cognition learning store."""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

# --- Codebase standard: Qdrant default port ---
CODEBASE_QDRANT_PORT = 6334

# Resolve source file relative to repo root
# test is at tests/unit/autonomous_cognition/test_learning_store.py
_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC_FILE = _REPO_ROOT / "src" / "autonomous_cognition" / "learning_store.py"


def test_qdrant_port_default_matches_codebase_standard() -> None:
    """Contract test: LearningStore must use port 6334 as default.

    The codebase standard for Qdrant is port 6334 (mapped from host 6333
    via Docker). Every Qdrant client in the codebase must default to 6334
    when QDRANT_PORT env var is not set.

    This test parses the source file to verify the literal default string,
    ensuring it cannot regress to 6333 or any other value.
    """
    source = _SRC_FILE.read_text(encoding="utf-8")

    # Find the QDRANT_PORT env var default in the source
    match = re.search(
        r'os\.environ\.get\(\s*"QDRANT_PORT"\s*,\s*"(\d+)"\s*\)',
        source,
    )
    assert (
        match is not None
    ), "learning_store.py must contain os.environ.get('QDRANT_PORT', '<port>')"

    port_literal = int(match.group(1))
    assert port_literal == CODEBASE_QDRANT_PORT, (
        f"QDRANT_PORT default is {port_literal}, expected {CODEBASE_QDRANT_PORT}. "
        f"The codebase standard for Qdrant port is {CODEBASE_QDRANT_PORT}."
    )


def test_learning_record_to_payload() -> None:
    """LearningRecord.to_payload() returns expected keys."""
    from autonomous_cognition.learning_store import LearningRecord

    record = LearningRecord(
        record_id="test-001",
        record_type="prediction",
        content="test content",
        metadata={"key": "value"},
    )
    payload = record.to_payload()

    assert payload["record_id"] == "test-001"
    assert payload["record_type"] == "prediction"
    assert payload["content"] == "test content"
    assert payload["metadata"]["key"] == "value"
    assert "created_at" in payload


def test_generate_embedding_deterministic() -> None:
    """generate_embedding produces same output for same input."""
    from autonomous_cognition.learning_store import LearningStore

    vec1 = LearningStore.generate_embedding("hello world", dimensions=16)
    vec2 = LearningStore.generate_embedding("hello world", dimensions=16)

    assert len(vec1) == 16
    assert vec1 == vec2


def test_generate_embedding_empty_string() -> None:
    """generate_embedding returns zero vector for empty string."""
    from autonomous_cognition.learning_store import LearningStore

    vec = LearningStore.generate_embedding("", dimensions=8)

    assert len(vec) == 8
    assert all(v == 0.0 for v in vec)


def test_redis_fallback_when_no_clients() -> None:
    """store_learning returns False when both Qdrant and Redis unavailable."""
    from autonomous_cognition.learning_store import LearningRecord, LearningStore

    store = LearningStore(qdrant_client=None, redis_client=None)
    # Force _get_qdrant_client to return None (no lazy connection)
    with patch.object(store, "_get_qdrant_client", return_value=None):
        record = LearningRecord(
            record_id="test-fallback",
            record_type="outcome",
            content="no clients",
        )

        result = store.store_learning(record)
        assert result is False
