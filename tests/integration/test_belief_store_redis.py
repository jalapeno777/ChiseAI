"""Integration tests for BeliefStore Redis backend.

These tests verify the BeliefStore integration with Redis backend,
including roundtrip operations, error handling, and data integrity.
"""

from __future__ import annotations

import json
import threading
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
        belief_id="test_belief_001",
        statement="The sky is blue during clear weather.",
        domain="meteorology",
        confidence=0.95,
        evidence_refs=["sensor_data", "visual_observation"],
        sources_quality_score=0.9,
        status="active",
    )


@pytest.fixture
def large_belief() -> Belief:
    """Create a large belief (>1MB payload) for testing."""
    large_statement = "X" * (1024 * 1024 + 100)  # Just over 1MB
    return Belief(
        belief_id="test_large_belief_001",
        statement=large_statement,
        domain="test",
        confidence=0.5,
        evidence_refs=["generated"],
        sources_quality_score=0.5,
        status="active",
    )


@pytest.fixture
def mock_redis_client():
    """Create a mock Redis client that tracks calls."""
    mock = MagicMock()
    mock.hset = MagicMock(return_value=1)
    mock.set = MagicMock(return_value=True)
    mock.get = MagicMock(return_value=None)
    mock.hgetall = MagicMock(return_value={})
    return mock


# =============================================================================
# Happy Path Tests
# =============================================================================


@pytest.mark.integration
class TestBeliefStoreRedisRoundtrip:
    """Test Redis-backed roundtrip (put -> get returns same data)."""

    def test_put_get_roundtrip_with_mock_redis(self, sample_belief, mock_redis_client):
        """Test that put() stores belief and get() retrieves identical belief."""
        store = BeliefStore(redis_client=mock_redis_client)

        # Put the belief
        result = store.put(sample_belief)
        assert result is True

        # Verify Redis was called
        assert mock_redis_client.hset.called
        assert mock_redis_client.set.called

        # Get should return from memory cache first
        retrieved = store.get(sample_belief.belief_id)
        assert retrieved is not None
        assert retrieved.belief_id == sample_belief.belief_id
        assert retrieved.statement == sample_belief.statement
        assert retrieved.confidence == sample_belief.confidence
        assert retrieved.domain == sample_belief.domain
        assert retrieved.status == sample_belief.status

    def test_put_get_with_redis_persistence(self, sample_belief, mock_redis_client):
        """Test that beliefs are properly serialized to Redis."""
        store = BeliefStore(redis_client=mock_redis_client)

        # Configure mock to return the serialized belief on get
        serialized = json.dumps(sample_belief.to_dict())
        mock_redis_client.get.return_value = serialized

        # Clear memory to force Redis lookup
        store._beliefs.clear()

        # Put belief
        store.put(sample_belief)

        # Get belief (should fetch from Redis since memory is cleared)
        retrieved = store.get(sample_belief.belief_id)

        assert retrieved is not None
        assert retrieved.belief_id == sample_belief.belief_id

        # Verify set was called with correct key format
        expected_key = f"bmad:chiseai:autocog:belief:{sample_belief.belief_id}"
        mock_redis_client.set.assert_called_with(
            expected_key, json.dumps(sample_belief.to_dict())
        )

    def test_multiple_beliefs_roundtrip(self, mock_redis_client):
        """Test storing and retrieving multiple beliefs."""
        store = BeliefStore(redis_client=mock_redis_client)

        beliefs = [
            Belief(
                belief_id=f"belief_{i}",
                statement=f"Test belief statement {i}",
                domain="test",
                confidence=0.8 + (i * 0.02),
                evidence_refs=["test"],
                sources_quality_score=0.7,
                status="active",
            )
            for i in range(5)
        ]

        # Store all beliefs
        for belief in beliefs:
            store.put(belief)

        # Retrieve all beliefs
        for belief in beliefs:
            retrieved = store.get(belief.belief_id)
            assert retrieved is not None
            assert retrieved.belief_id == belief.belief_id
            assert retrieved.confidence == belief.confidence

    def test_belief_update_overwrites_previous(self, sample_belief, mock_redis_client):
        """Test that updating a belief with same ID overwrites."""
        store = BeliefStore(redis_client=mock_redis_client)

        # Store initial belief
        store.put(sample_belief)

        # Update the belief
        updated_belief = Belief(
            belief_id=sample_belief.belief_id,
            statement="Updated statement.",
            domain=sample_belief.domain,
            confidence=0.99,  # Changed
            evidence_refs=["updated_evidence"],
            sources_quality_score=0.95,
            status="active",
        )
        store.put(updated_belief)

        # Retrieve should return updated version
        retrieved = store.get(sample_belief.belief_id)
        assert retrieved is not None
        assert retrieved.statement == "Updated statement."
        assert retrieved.confidence == 0.99
        assert len(retrieved.evidence_refs) == 1


# =============================================================================
# Failure Mode Tests
# =============================================================================


class TestBeliefStoreFailureModes:
    """Test failure mode handling."""

    def test_redis_unavailable_falls_back_to_memory(self, sample_belief):
        """Test graceful fallback to local/memory store when Redis unavailable."""
        # Create store with no Redis client
        store = BeliefStore(redis_client=None)

        # Patch redis_state functions to raise exceptions at the source module
        with patch(
            "tools.redis_state.redis_state_hset",
            side_effect=Exception("Redis connection failed"),
        ):
            with patch(
                "tools.redis_state.redis_state_set",
                side_effect=Exception("Redis connection failed"),
            ):
                # put() should not raise - it catches exceptions
                store.put(sample_belief)

        # Belief should still be in memory
        assert sample_belief.belief_id in store._beliefs
        retrieved = store.get(sample_belief.belief_id)
        assert retrieved is not None
        assert retrieved.belief_id == sample_belief.belief_id

    def test_connection_timeout_handling(self, sample_belief, mock_redis_client):
        """Test proper exception handling on connection timeout."""
        # Make Redis calls raise timeout exception
        mock_redis_client.hset.side_effect = TimeoutError("Connection timed out")
        mock_redis_client.set.side_effect = TimeoutError("Connection timed out")

        store = BeliefStore(redis_client=mock_redis_client)

        # put() should catch exception and not raise
        store.put(sample_belief)

        # Belief should still be in memory
        assert sample_belief.belief_id in store._beliefs

    def test_invalid_data_handling(self, sample_belief, mock_redis_client):
        """Test handling of invalid data from Redis."""
        store = BeliefStore(redis_client=mock_redis_client)

        # Configure mock to return corrupted/invalid JSON
        mock_redis_client.get.return_value = "{ invalid json }"
        store._beliefs.clear()  # Clear memory to force Redis lookup

        # get() should catch exception and return None
        retrieved = store.get(sample_belief.belief_id)
        assert retrieved is None

    def test_missing_belief_returns_none(self, mock_redis_client):
        """Test that getting non-existent belief returns None."""
        store = BeliefStore(redis_client=mock_redis_client)

        # Configure mock to return None (belief not found)
        mock_redis_client.get.return_value = None
        store._beliefs.clear()

        retrieved = store.get("non_existent_belief_id")
        assert retrieved is None


# =============================================================================
# Data Integrity Tests
# =============================================================================


class TestBeliefStoreDataIntegrity:
    """Test data integrity and double-deserialization prevention."""

    def test_no_double_deserialization(self, sample_belief, mock_redis_client):
        """Verify T2 fix: data is not double-deserialized."""
        store = BeliefStore(redis_client=mock_redis_client)

        # Serialize belief
        serialized = json.dumps(sample_belief.to_dict())
        mock_redis_client.get.return_value = serialized

        # Clear memory to force Redis lookup
        store._beliefs.clear()

        # Get should deserialize once
        retrieved = store.get(sample_belief.belief_id)
        assert retrieved is not None

        # The belief should be a Belief object, not a dict
        assert isinstance(retrieved, Belief)
        assert isinstance(retrieved.confidence, float)

    def test_serialized_data_structure_preserved(
        self, sample_belief, mock_redis_client
    ):
        """Test that all belief fields are preserved through serialization."""
        store = BeliefStore(redis_client=mock_redis_client)

        # Configure mock to return serialized belief
        serialized = json.dumps(sample_belief.to_dict())
        mock_redis_client.get.return_value = serialized
        store._beliefs.clear()

        retrieved = store.get(sample_belief.belief_id)

        # Verify all fields
        assert retrieved.belief_id == sample_belief.belief_id
        assert retrieved.statement == sample_belief.statement
        assert retrieved.domain == sample_belief.domain
        assert retrieved.confidence == sample_belief.confidence
        assert retrieved.evidence_refs == sample_belief.evidence_refs
        assert retrieved.sources_quality_score == sample_belief.sources_quality_score
        assert retrieved.status == sample_belief.status
        assert retrieved.created_at == sample_belief.created_at

    def test_special_characters_preserved(self, mock_redis_client):
        """Test that special characters in statements are preserved."""
        belief = Belief(
            belief_id="special_chars_test",
            statement="Test with émoji 🎉 and unicode ñ字",
            domain="test",
            confidence=0.9,
            evidence_refs=["test"],
            sources_quality_score=0.5,
            status="active",
        )

        store = BeliefStore(redis_client=mock_redis_client)
        serialized = json.dumps(belief.to_dict())
        mock_redis_client.get.return_value = serialized
        store._beliefs.clear()

        retrieved = store.get(belief.belief_id)
        assert retrieved.statement == belief.statement


# =============================================================================
# Concurrent Access Tests
# =============================================================================


class TestBeliefStoreConcurrentAccess:
    """Test thread-safety of BeliefStore operations."""

    def test_concurrent_put_operations(self, mock_redis_client):
        """Test that concurrent put() operations are thread-safe."""
        store = BeliefStore(redis_client=mock_redis_client)
        num_beliefs = 50
        errors = []

        def put_belief(i: int):
            try:
                belief = Belief(
                    belief_id=f"concurrent_belief_{i}",
                    statement=f"Statement {i}",
                    domain="test",
                    confidence=0.9,
                    evidence_refs=["test"],
                    sources_quality_score=0.5,
                    status="active",
                )
                store.put(belief)
            except Exception as e:
                errors.append(e)

        # Run concurrent puts
        threads = [
            threading.Thread(target=put_belief, args=(i,)) for i in range(num_beliefs)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # No errors should occur
        assert len(errors) == 0
        # All beliefs should be in memory
        assert len(store._beliefs) == num_beliefs

    def test_concurrent_read_write(self, mock_redis_client):
        """Test concurrent read and write operations."""
        store = BeliefStore(redis_client=mock_redis_client)
        num_operations = 100
        errors = []

        # Pre-populate some beliefs
        for i in range(10):
            belief = Belief(
                belief_id=f"pre_belief_{i}",
                statement=f"Pre-existing belief {i}",
                domain="test",
                confidence=0.9,
                evidence_refs=["test"],
                sources_quality_score=0.5,
                status="active",
            )
            store.put(belief)

        def read_write_operation(i: int):
            try:
                if i % 2 == 0:
                    # Write
                    belief = Belief(
                        belief_id=f"rw_belief_{i}",
                        statement=f"Statement {i}",
                        domain="test",
                        confidence=0.9,
                        evidence_refs=["test"],
                        sources_quality_score=0.5,
                        status="active",
                    )
                    store.put(belief)
                else:
                    # Read
                    store.get(f"pre_belief_{i % 10}")
            except Exception as e:
                errors.append(e)

        # Run concurrent operations
        threads = [
            threading.Thread(target=read_write_operation, args=(i,))
            for i in range(num_operations)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0


# =============================================================================
# Large Payload Tests
# =============================================================================


class TestBeliefStoreLargePayloads:
    """Test handling of beliefs > 1MB."""

    def test_large_belief_stored_in_memory(self, large_belief):
        """Test that large beliefs are stored in memory."""
        store = BeliefStore(redis_client=None)

        # put() should not raise
        store.put(large_belief)

        # Belief should be in memory
        assert large_belief.belief_id in store._beliefs
        retrieved = store.get(large_belief.belief_id)
        assert retrieved is not None
        assert len(retrieved.statement) == len(large_belief.statement)

    def test_large_belief_redis_serialization(self, large_belief, mock_redis_client):
        """Test that large beliefs are properly serialized to Redis."""
        store = BeliefStore(redis_client=mock_redis_client)

        # Capture what gets sent to Redis
        stored_payloads = []

        def capture_set(key: str, value: str):
            stored_payloads.append((key, len(value)))
            return True

        mock_redis_client.set = MagicMock(side_effect=capture_set)

        store.put(large_belief)

        # Verify large payload was sent to Redis
        assert len(stored_payloads) > 0
        key, value_size = stored_payloads[0]
        # Payload should be > 1MB
        assert value_size > 1024 * 1024


# =============================================================================
# list_active Tests
# =============================================================================


class TestBeliefStoreListActive:
    """Test list_active functionality."""

    def test_list_active_returns_only_active(self, mock_redis_client):
        """Test that list_active returns only active beliefs."""
        store = BeliefStore(redis_client=mock_redis_client)

        # Add beliefs with different statuses
        beliefs = [
            Belief(
                belief_id="active_1",
                statement="Active 1",
                domain="test",
                confidence=0.9,
                status="active",
            ),
            Belief(
                belief_id="active_2",
                statement="Active 2",
                domain="test",
                confidence=0.9,
                status="active",
            ),
            Belief(
                belief_id="inactive_1",
                statement="Inactive 1",
                domain="test",
                confidence=0.9,
                status="inactive",
            ),
            Belief(
                belief_id="superseded_1",
                statement="Superseded 1",
                domain="test",
                confidence=0.9,
                status="superseded",
            ),
        ]

        for belief in beliefs:
            store.put(belief)

        active = store.list_active()

        # Should return only active beliefs
        assert len(active) == 2
        assert all(b.status == "active" for b in active)
        assert any(b.belief_id == "active_1" for b in active)
        assert any(b.belief_id == "active_2" for b in active)

    def test_list_active_empty_store(self, mock_redis_client):
        """Test list_active on empty store."""
        store = BeliefStore(redis_client=mock_redis_client)
        mock_redis_client.hgetall.return_value = {}

        active = store.list_active()
        assert len(active) == 0


# =============================================================================
# No Silent Failures Tests
# =============================================================================


@pytest.mark.integration
def test_no_silent_failures_100_iterations(mock_redis_client):
    """Verify put() returns bool (True=success, False=failure) with 100 sequential cycles.

    This test ensures there are no silent failures - every put() must return
    a verifiable boolean indicating success or failure.
    """
    store = BeliefStore(redis_client=mock_redis_client)
    failures = []

    for i in range(100):
        belief = Belief(
            belief_id=f"silent_fail_test_{i}",
            statement=f"Test belief statement {i}",
            domain="test",
            confidence=0.85,
            evidence_refs=[f"ref_{i}"],
            sources_quality_score=0.75,
            status="active",
        )

        # put() must return bool - capture and verify
        result = store.put(belief)
        if not isinstance(result, bool):
            failures.append(
                f"Iteration {i}: put() returned {type(result).__name__}, expected bool"
            )
            continue

        if result is False:
            failures.append(f"Iteration {i}: put() returned False (failure)")
            continue

        # Verify we can retrieve what we put
        retrieved = store.get(belief.belief_id)
        if retrieved is None:
            failures.append(
                f"Iteration {i}: get() returned None after successful put()"
            )
            continue

        if retrieved.belief_id != belief.belief_id:
            failures.append(f"Iteration {i}: retrieved belief_id mismatch")

    assert len(failures) == 0, f"Found {len(failures)} silent failures: {failures[:5]}"
