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


def test_delete_learning_qdrant_cleans_up_points() -> None:
    """delete_learning() calls Qdrant delete with correct point ID."""
    import hashlib
    from unittest.mock import MagicMock

    from autonomous_cognition.learning_store import LearningStore

    mock_qdrant_client = MagicMock()
    store = LearningStore(qdrant_client=mock_qdrant_client, redis_client=None)

    learning_id = "my-learning-123"
    expected_point_id = hashlib.sha256(learning_id.encode("utf-8")).hexdigest()[:32]

    result = store.delete_learning(learning_id)

    assert result is True
    mock_qdrant_client.delete.assert_called_once_with(
        collection_name=store.qdrant_collection,
        points_selector={"points": [expected_point_id]},
    )


def test_delete_learning_removes_from_redis() -> None:
    """delete_learning() cleans up Redis fallback keys."""
    from unittest.mock import MagicMock

    from autonomous_cognition.learning_store import LearningStore

    mock_redis = MagicMock()
    mock_redis.delete.return_value = 1
    store = LearningStore(qdrant_client=None, redis_client=mock_redis)

    with patch.object(store, "_get_qdrant_client", return_value=None):
        result = store.delete_learning("redis-learning-456")

    assert result is True
    # Should attempt both prediction and outcome key patterns
    assert mock_redis.delete.call_count == 2


def test_delete_learning_redis_no_keys() -> None:
    """delete_learning() returns False when Redis has no matching keys."""
    from unittest.mock import MagicMock

    from autonomous_cognition.learning_store import LearningStore

    mock_redis = MagicMock()
    mock_redis.delete.return_value = 0
    store = LearningStore(qdrant_client=None, redis_client=mock_redis)

    with patch.object(store, "_get_qdrant_client", return_value=None):
        result = store.delete_learning("nonexistent-learning")

    assert result is False


def test_delete_learning_error_handling() -> None:
    """delete_learning() returns False when both backends raise exceptions."""
    from unittest.mock import MagicMock

    from autonomous_cognition.learning_store import LearningStore

    mock_qdrant = MagicMock()
    mock_qdrant.delete.side_effect = Exception("Qdrant connection lost")

    mock_redis = MagicMock()
    mock_redis.delete.side_effect = Exception("Redis connection lost")

    store = LearningStore(qdrant_client=mock_qdrant, redis_client=mock_redis)

    result = store.delete_learning("error-learning")

    assert result is False
