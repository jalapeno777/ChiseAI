"""Debug test for BeliefStore.put() silent failure investigation."""

from __future__ import annotations

import logging
import sys

# Configure logging to see our debug output
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)

from autonomous_cognition.beliefs.models import Belief
from autonomous_cognition.beliefs.store import BeliefStore


def test_belief_store_put_get_round_trip():
    """Test that put() actually persists to Redis and get() can retrieve it.

    This test investigates the 'silent failure' issue where put() appears to succeed
    but data is not actually persisted to Redis.
    """
    # Create a fresh BeliefStore with no external redis client (uses module-level tools)
    store = BeliefStore(redis_client=None)

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

    print("\n" + "=" * 70)
    print("DEBUG TEST: BeliefStore.put() silent failure investigation")
    print("=" * 70)
    print(f"\n1. Created belief: {belief.belief_id}")
    print(f"   Statement: {belief.statement}")
    print(f"   Confidence: {belief.confidence}")

    # Put the belief
    print(f"\n2. Calling store.put(belief)...")
    store.put(belief)
    print(f"   put() returned (method is void)")

    # Check if it's in memory
    print(f"\n3. Checking memory cache...")
    in_memory = belief.belief_id in store._beliefs
    print(f"   In memory: {in_memory}")
    if in_memory:
        print(f"   Memory content: {store._beliefs[belief.belief_id]}")

    # Try to get it back using get()
    print(f"\n4. Calling store.get('{belief.belief_id}')...")
    retrieved = store.get(belief.belief_id)

    if retrieved is None:
        print(f"   WARNING: get() returned None!")
        print(f"   This indicates the belief was NOT persisted to Redis.")
    else:
        print(f"   SUCCESS: Retrieved belief: {retrieved.belief_id}")
        print(f"   Statement: {retrieved.statement}")
        print(f"   Confidence: {retrieved.confidence}")
        print(f"   Status: {retrieved.status}")

    # Additional verification: Create a NEW store instance and try to get the belief
    # This simulates a fresh process that relies solely on Redis
    print(f"\n5. Creating NEW BeliefStore instance to verify Redis persistence...")
    fresh_store = BeliefStore(redis_client=None)

    # Clear the new store's memory cache to force Redis lookup
    fresh_store._beliefs.clear()
    print(f"   Cleared fresh store memory cache")

    # Try to get the belief from the new store
    fresh_retrieved = fresh_store.get(belief.belief_id)

    if fresh_retrieved is None:
        print(f"   FAILURE: Fresh store could NOT retrieve belief from Redis!")
        print(
            f"   This confirms the 'silent failure' - put() did NOT persist to Redis."
        )
    else:
        print(f"   SUCCESS: Fresh store retrieved belief from Redis")
        print(f"   Belief ID: {fresh_retrieved.belief_id}")

    print("\n" + "=" * 70)
    print("DEBUG TEST COMPLETE")
    print("=" * 70 + "\n")

    # Assertions for test result
    # If Redis persistence failed, the belief would be None after fresh store retrieval
    assert retrieved is not None, (
        "First retrieval failed - belief not found after put()"
    )
    assert fresh_retrieved is not None, (
        "Fresh store retrieval failed - belief not persisted to Redis"
    )


def test_belief_store_with_external_redis_client():
    """Test using a mock external redis client to trace the exact execution path."""
    from unittest.mock import MagicMock

    print("\n" + "=" * 70)
    print("DEBUG TEST 2: Tracing with external redis_client")
    print("=" * 70)

    # Create a mock Redis client
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

    print(f"\n1. Calling store.put(belief) with mock Redis client...")
    store.put(belief)

    print(f"\n2. Verifying mock calls...")
    print(f"   mock_redis.hset called: {mock_redis.hset.called}")
    print(f"   mock_redis.hset call_args: {mock_redis.hset.call_args}")
    print(f"   mock_redis.set called: {mock_redis.set.called}")
    print(f"   mock_redis.set call_args: {mock_redis.set.call_args}")

    print("\n" + "=" * 70)
    print("DEBUG TEST 2 COMPLETE")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    print("Running BeliefStore.put() debug investigation tests...")
    print("=" * 70 + "\n")

    try:
        test_belief_store_put_get_round_trip()
    except Exception as e:
        print(f"\nTest 1 failed with exception: {e}")
        import traceback

        traceback.print_exc()

    try:
        test_belief_store_with_external_redis_client()
    except Exception as e:
        print(f"\nTest 2 failed with exception: {e}")
        import traceback

        traceback.print_exc()
