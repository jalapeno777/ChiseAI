"""Debug test for BeliefStore.put() silent failure investigation."""

from __future__ import annotations

import json
import logging
import sys
from unittest.mock import MagicMock

# Configure logging to see our debug output
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)

from autonomous_cognition.beliefs.models import Belief
from autonomous_cognition.beliefs.store import BeliefStore


def test_belief_store_put_get_round_trip():
    """Test that put() persists to Redis and get() can retrieve it using mocks.

    Uses mock Redis to avoid polluting live Redis with test beliefs.
    """
    mock_redis = MagicMock()
    mock_redis.hset.return_value = 1
    mock_redis.set.return_value = True
    mock_redis.hget.return_value = (
        None  # Default: not found until we configure per-call
    )

    store = BeliefStore(redis_client=mock_redis)

    # Create a test belief
    belief = Belief(
        belief_id="debug_test_belief_001",
        statement="This is a test belief for debugging put() silent failure.",
        domain="debug",
        confidence=0.85,
        evidence_refs=["debug_test"],
        sources_quality_score=0.75,
        status="active",
    )

    # Put the belief
    store.put(belief)

    # Verify put() called hset and set on Redis
    mock_redis.hset.assert_called()
    mock_redis.set.assert_called()

    # Configure mock to return belief data on subsequent get() call
    mock_redis.hget.return_value = json.dumps(belief.to_dict())

    # Try to get it back
    retrieved = store.get(belief.belief_id)

    # Assertions
    assert retrieved is not None, "get() returned None after put()"
    assert retrieved.belief_id == belief.belief_id
    assert retrieved.confidence == belief.confidence


def test_belief_store_with_external_redis_client():
    """Test using a mock external redis client to trace the exact execution path."""
    mock_redis = MagicMock()
    mock_redis.hset.return_value = 1  # Success
    mock_redis.set.return_value = True  # Success

    store = BeliefStore(redis_client=mock_redis)

    belief = Belief(
        belief_id="mock_test_belief_001",
        statement="Test with mock redis client.",
        domain="debug",
        confidence=0.90,
        status="active",
    )

    store.put(belief)

    # Verify mock calls
    assert mock_redis.hset.called, "hset was not called during put()"
    assert mock_redis.set.called, "set was not called during put()"
