"""Integration tests for BeliefStore fallback behavior.

These tests verify the BeliefStore fallback mechanisms when Redis
is unavailable, including graceful degradation and data consistency.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from autonomous_cognition.beliefs.models import Belief
from autonomous_cognition.beliefs.store import BeliefStore

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_belief() -> Belief:
    """Create a sample belief for testing."""
    return Belief(
        belief_id="fallback_test_belief_001",
        statement="Testing fallback behavior.",
        domain="testing",
        confidence=0.85,
        evidence_refs=["test_source"],
        sources_quality_score=0.8,
        status="active",
    )


@pytest.fixture
def mock_redis_client():
    """Create a mock Redis client for fallback tests."""
    mock = MagicMock()
    mock.hset = MagicMock(return_value=1)
    mock.set = MagicMock(return_value=True)
    mock.get = MagicMock(return_value=None)
    mock.hgetall = MagicMock(return_value={})
    return mock


# =============================================================================
# Fallback Behavior Tests
# =============================================================================


class TestBeliefStoreFallback:
    """Test fallback behavior when Redis is unavailable."""

    def test_fallback_to_memory_when_redis_hset_fails(self, sample_belief):
        """Test that memory fallback works when hset fails."""
        store = BeliefStore(redis_client=None)

        with patch(
            "tools.redis_state.redis_state_hset",
            side_effect=Exception("Redis hset failed"),
        ):
            with patch(
                "tools.redis_state.redis_state_set",
                side_effect=Exception("Redis set failed"),
            ):
                # put() should catch exceptions and store in memory
                store.put(sample_belief)

        # Belief should be in memory
        assert sample_belief.belief_id in store._beliefs
        assert (
            store._beliefs[sample_belief.belief_id].statement == sample_belief.statement
        )

    def test_fallback_to_memory_when_redis_set_fails(self, sample_belief):
        """Test that memory fallback works when set fails."""
        store = BeliefStore(redis_client=None)

        with patch("tools.redis_state.redis_state_hset", return_value=True):
            with patch(
                "tools.redis_state.redis_state_set",
                side_effect=Exception("Redis set failed"),
            ):
                store.put(sample_belief)

        assert sample_belief.belief_id in store._beliefs

    def test_fallback_get_from_memory_after_redis_failure(self, sample_belief):
        """Test that get() returns from memory even if Redis fails."""
        store = BeliefStore(redis_client=None)

        # Store in memory first
        store.put(sample_belief)

        # Even if Redis get fails, should return from memory
        with patch(
            "tools.redis_state.redis_state_get",
            side_effect=Exception("Redis get failed"),
        ):
            retrieved = store.get(sample_belief.belief_id)

        assert retrieved is not None
        assert retrieved.belief_id == sample_belief.belief_id

    def test_fallback_to_redis_when_memory_miss(self, sample_belief, mock_redis_client):
        """Test fallback to Redis when belief not in memory."""
        store = BeliefStore(redis_client=mock_redis_client)

        # Serialize and configure mock to return it
        serialized = json.dumps(sample_belief.to_dict())
        mock_redis_client.get.return_value = serialized

        # Memory is empty, should fallback to Redis
        assert sample_belief.belief_id not in store._beliefs
        retrieved = store.get(sample_belief.belief_id)

        assert retrieved is not None
        assert retrieved.belief_id == sample_belief.belief_id
        mock_redis_client.get.assert_called()

    def test_memory_cache_populated_after_redis_fetch(
        self, sample_belief, mock_redis_client
    ):
        """Test that memory cache is populated after fetching from Redis."""
        store = BeliefStore(redis_client=mock_redis_client)

        serialized = json.dumps(sample_belief.to_dict())
        mock_redis_client.get.return_value = serialized

        # Clear memory
        assert len(store._beliefs) == 0

        # Fetch from Redis
        retrieved = store.get(sample_belief.belief_id)

        # Memory should now be populated
        assert sample_belief.belief_id in store._beliefs

    def test_fallback_to_redis_hgetall_when_memory_empty(self, mock_redis_client):
        """Test fallback to Redis hgetall for list_active when memory empty."""
        beliefs_data = {
            "belief_1": json.dumps(
                Belief(
                    belief_id="belief_1",
                    statement="Belief 1",
                    domain="test",
                    confidence=0.9,
                    evidence_refs=[],
                    sources_quality_score=0.5,
                    status="active",
                ).to_dict()
            ),
            "belief_2": json.dumps(
                Belief(
                    belief_id="belief_2",
                    statement="Belief 2",
                    domain="test",
                    confidence=0.8,
                    evidence_refs=[],
                    sources_quality_score=0.5,
                    status="active",
                ).to_dict()
            ),
        }
        mock_redis_client.hgetall.return_value = beliefs_data

        store = BeliefStore(redis_client=mock_redis_client)
        # Clear memory to force Redis lookup
        store._beliefs.clear()

        active = store.list_active()

        assert len(active) == 2
        mock_redis_client.hgetall.assert_called()


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestBeliefStoreErrorHandling:
    """Test error handling in various scenarios."""

    def test_put_with_corrupted_redis_response(self, sample_belief):
        """Test that put() handles corrupted Redis responses gracefully."""
        store = BeliefStore(redis_client=None)

        # Simulate Redis returning corrupted data
        with patch("tools.redis_state.redis_state_hset", return_value="ERROR"):
            with patch("tools.redis_state.redis_state_set", return_value="ERROR"):
                # Should not raise
                store.put(sample_belief)

        assert sample_belief.belief_id in store._beliefs

    def test_get_with_redis_returns_wrong_type(self, sample_belief, mock_redis_client):
        """Test handling when Redis returns unexpected type."""
        store = BeliefStore(redis_client=mock_redis_client)

        # Configure mock to return non-string type
        mock_redis_client.get.return_value = 12345
        store._beliefs.clear()

        # Should catch error and return None
        retrieved = store.get(sample_belief.belief_id)
        assert retrieved is None

    def test_get_with_redis_returns_empty_string(
        self, sample_belief, mock_redis_client
    ):
        """Test handling when Redis returns empty string."""
        store = BeliefStore(redis_client=mock_redis_client)

        mock_redis_client.get.return_value = ""
        store._beliefs.clear()

        retrieved = store.get(sample_belief.belief_id)
        assert retrieved is None

    def test_list_active_with_redis_failure(self, mock_redis_client):
        """Test list_active gracefully handles Redis failure."""
        store = BeliefStore(redis_client=mock_redis_client)

        # Add some beliefs to memory
        store.put(
            Belief(
                belief_id="memory_belief",
                statement="In memory",
                domain="test",
                confidence=0.9,
                evidence_refs=[],
                sources_quality_score=0.5,
                status="active",
            )
        )

        # Make Redis hgetall fail
        mock_redis_client.hgetall.side_effect = Exception("Redis error")

        # Should still return memory beliefs
        active = store.list_active()
        assert len(active) >= 1


# =============================================================================
# Data Consistency Tests
# =============================================================================


class TestBeliefStoreDataConsistency:
    """Test data consistency between memory and Redis."""

    def test_memory_takes_precedence_over_redis(self, sample_belief, mock_redis_client):
        """Test that memory values take precedence over Redis."""
        store = BeliefStore(redis_client=mock_redis_client)

        # Store original belief
        store.put(sample_belief)

        # Modify memory directly
        modified_belief = Belief(
            belief_id=sample_belief.belief_id,
            statement="Modified in memory",
            domain=sample_belief.domain,
            confidence=0.99,
            evidence_refs=sample_belief.evidence_refs,
            sources_quality_score=sample_belief.sources_quality_score,
            status="active",
        )
        store._beliefs[sample_belief.belief_id] = modified_belief

        # Configure Redis to return different data
        redis_version = Belief(
            belief_id=sample_belief.belief_id,
            statement="From Redis",
            domain=sample_belief.domain,
            confidence=0.5,
            evidence_refs=[],
            sources_quality_score=0.5,
            status="active",
        )
        mock_redis_client.get.return_value = json.dumps(redis_version.to_dict())

        # Get should return memory version (precedence)
        retrieved = store.get(sample_belief.belief_id)

        # Memory takes precedence - should get modified version
        assert retrieved.statement == "Modified in memory"
        assert retrieved.confidence == 0.99

    def test_multiple_puts_maintain_consistency(self, mock_redis_client):
        """Test that multiple puts maintain data consistency."""
        store = BeliefStore(redis_client=mock_redis_client)

        for i in range(10):
            belief = Belief(
                belief_id=f"consistency_test_{i}",
                statement=f"Statement {i}",
                domain="test",
                confidence=0.9,
                evidence_refs=["test"],
                sources_quality_score=0.5,
                status="active",
            )
            store.put(belief)

        # All beliefs should be in memory
        assert len(store._beliefs) == 10

        # Each should be retrievable
        for i in range(10):
            retrieved = store.get(f"consistency_test_{i}")
            assert retrieved is not None
            assert retrieved.statement == f"Statement {i}"
