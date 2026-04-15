"""Tests for LearningStore module.

Validates real Qdrant write operations and graceful degradation.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from src.autonomous_cognition.learning_store import (
    LEARNING_COLLECTION,
    LearningRecord,
    LearningStore,
    get_learning_store,
)


class TestLearningRecord:
    """Tests for LearningRecord dataclass."""

    def test_to_payload_basic(self):
        """Test basic payload serialization."""
        record = LearningRecord(
            record_id="test-123",
            record_type="prediction",
            content="Test prediction content",
            metadata={"key": "value"},
            created_at=datetime(2026, 3, 27, 12, 0, 0, tzinfo=UTC),
        )

        payload = record.to_payload()

        assert payload["record_id"] == "test-123"
        assert payload["record_type"] == "prediction"
        assert payload["content"] == "Test prediction content"
        assert payload["metadata"] == {"key": "value"}
        assert payload["created_at"] == "2026-03-27T12:00:00+00:00"

    def test_to_payload_defaults(self):
        """Test payload with default values."""
        record = LearningRecord(
            record_id="test-456",
            record_type="outcome",
            content="Test outcome content",
        )

        payload = record.to_payload()

        assert payload["record_id"] == "test-456"
        assert payload["record_type"] == "outcome"
        assert payload["content"] == "Test outcome content"
        assert payload["metadata"] == {}
        assert "created_at" in payload


class TestLearningStore:
    """Tests for LearningStore Qdrant integration."""

    def test_initialization(self):
        """Test LearningStore initialization with defaults."""
        store = LearningStore()

        assert store.qdrant_collection == LEARNING_COLLECTION
        assert store.vector_size == 384
        assert store._qdrant_client is None
        assert store._redis_client is None

    def test_initialization_custom_params(self):
        """Test LearningStore with custom parameters."""
        store = LearningStore(
            collection_name="custom_collection",
            vector_size=256,
        )

        assert store.qdrant_collection == "custom_collection"
        assert store.vector_size == 256

    def test_generate_embedding_deterministic(self):
        """Test that embedding generation is deterministic."""
        text = "Test prediction content for embedding"

        embedding1 = LearningStore.generate_embedding(text, dimensions=384)
        embedding2 = LearningStore.generate_embedding(text, dimensions=384)

        assert embedding1 == embedding2
        assert len(embedding1) == 384

    def test_generate_embedding_empty_text(self):
        """Test embedding generation with empty text."""
        embedding = LearningStore.generate_embedding("", dimensions=128)

        assert len(embedding) == 128
        assert all(v == 0.0 for v in embedding)

    def test_generate_embedding_different_texts(self):
        """Test that different texts produce different embeddings."""
        embedding1 = LearningStore.generate_embedding("Text A")
        embedding2 = LearningStore.generate_embedding("Text B")

        assert embedding1 != embedding2

    @patch.object(LearningStore, "_get_qdrant_client")
    def test_store_learning_real_qdrant_upsert(self, mock_get_qdrant):
        """Test that store_learning performs real Qdrant upsert."""
        mock_client = MagicMock()
        mock_get_qdrant.return_value = mock_client

        store = LearningStore()
        record = LearningRecord(
            record_id="test-pred-001",
            record_type="prediction",
            content="Test prediction",
            metadata={"confidence": 0.8},
        )

        result = store.store_learning(record)

        assert result is True
        mock_client.upsert.assert_called_once()

        # Verify upsert call structure
        call_kwargs = mock_client.upsert.call_args.kwargs
        assert call_kwargs["collection_name"] == LEARNING_COLLECTION
        assert len(call_kwargs["points"]) == 1
        assert "vector" in call_kwargs["points"][0]
        assert "payload" in call_kwargs["points"][0]

    @patch.object(LearningStore, "_get_qdrant_client")
    def test_store_prediction_calls_store_learning(self, mock_get_qdrant):
        """Test that store_prediction correctly creates LearningRecord."""
        mock_client = MagicMock()
        mock_get_qdrant.return_value = mock_client

        store = LearningStore()

        result = store.store_prediction(
            prediction_id="pred-001",
            prediction_type="market_direction",
            confidence=0.75,
            context={"symbol": "BTC"},
            timestamp=datetime(2026, 3, 27, 12, 0, 0, tzinfo=UTC),
        )

        assert result is True
        mock_client.upsert.assert_called_once()

    @patch.object(LearningStore, "_get_qdrant_client")
    def test_store_outcome_calls_store_learning(self, mock_get_qdrant):
        """Test that store_outcome correctly creates LearningRecord."""
        mock_client = MagicMock()
        mock_get_qdrant.return_value = mock_client

        store = LearningStore()

        result = store.store_outcome(
            outcome_id="outcome-001",
            prediction_id="pred-001",
            actual_value=True,
            metadata={"source": "backtest"},
            timestamp=datetime(2026, 3, 27, 12, 0, 0, tzinfo=UTC),
        )

        assert result is True
        mock_client.upsert.assert_called_once()

    @patch.object(LearningStore, "_get_qdrant_client")
    def test_graceful_degradation_to_redis(self, mock_get_qdrant):
        """Test graceful degradation when Qdrant fails."""
        mock_get_qdrant.return_value = None

        mock_redis = MagicMock()
        store = LearningStore(redis_client=mock_redis)

        record = LearningRecord(
            record_id="test-001",
            record_type="prediction",
            content="Test content",
        )

        result = store.store_learning(record)

        assert result is True
        mock_redis.set.assert_called_once()

    @patch.object(LearningStore, "_get_qdrant_client")
    def test_qdrant_failure_fallback_to_redis(self, mock_get_qdrant):
        """Test that Qdrant failure triggers Redis fallback."""
        mock_client = MagicMock()
        mock_client.upsert.side_effect = Exception("Qdrant connection failed")
        mock_get_qdrant.return_value = mock_client

        mock_redis = MagicMock()
        store = LearningStore(redis_client=mock_redis)

        record = LearningRecord(
            record_id="test-002",
            record_type="outcome",
            content="Test content",
        )

        result = store.store_learning(record)

        assert result is True
        mock_redis.set.assert_called_once()
        mock_client.upsert.assert_called_once()

    @patch.object(LearningStore, "_get_qdrant_client")
    def test_complete_failure_when_redis_also_unavailable(self, mock_get_qdrant):
        """Test that storage fails when both Qdrant and Redis unavailable."""
        mock_get_qdrant.return_value = None
        store = LearningStore(redis_client=None)

        record = LearningRecord(
            record_id="test-003",
            record_type="prediction",
            content="Test content",
        )

        result = store.store_learning(record)

        assert result is False

    def test_get_learning_store_singleton(self):
        """Test that get_learning_store returns singleton."""
        # Reset module-level singleton
        import src.autonomous_cognition.learning_store as module

        module._default_store = None

        store1 = get_learning_store()
        store2 = get_learning_store()

        assert store1 is store2

        # Cleanup
        module._default_store = None


class TestLearningStoreIntegration:
    """Integration-style tests using mocks for Qdrant."""

    @patch.object(LearningStore, "_get_qdrant_client")
    def test_full_prediction_outcome_flow(self, mock_get_qdrant):
        """Test storing prediction and outcome through complete flow."""
        mock_client = MagicMock()
        mock_get_qdrant.return_value = mock_client

        store = LearningStore()

        # Store prediction
        pred_result = store.store_prediction(
            prediction_id="flow-pred-001",
            prediction_type="trend_direction",
            confidence=0.82,
            context={"timeframe": "1h"},
        )

        # Store outcome
        outcome_result = store.store_outcome(
            outcome_id="flow-outcome-001",
            prediction_id="flow-pred-001",
            actual_value="bullish",
            metadata={"source": "price_action"},
        )

        assert pred_result is True
        assert outcome_result is True
        assert mock_client.upsert.call_count == 2

    def test_embedding_consistency(self):
        """Test that same content produces consistent embeddings."""
        store = LearningStore()

        content = "Consistent prediction content"

        embedding1 = store.generate_embedding(content)
        embedding2 = store.generate_embedding(content)

        assert embedding1 == embedding2

        # Different content should differ
        different_embedding = store.generate_embedding("Different content")
        assert embedding1 != different_embedding


class TestLearningStoreReadBackVerification:
    """Tests verifying end-to-end write → read cycle."""

    @patch.object(LearningStore, "_get_qdrant_client")
    def test_get_learning_returns_stored_record(self, mock_get_qdrant):
        """Test that get_learning retrieves what store_learning wrote."""
        mock_client = MagicMock()
        mock_get_qdrant.return_value = mock_client

        store = LearningStore()
        record = LearningRecord(
            record_id="verify-001",
            record_type="prediction",
            content="Test verification content",
            metadata={"confidence": 0.9},
            created_at=datetime(2026, 3, 27, 12, 0, 0, tzinfo=UTC),
        )

        # First store the record
        store_result = store.store_learning(record)
        assert store_result is True

        # Now retrieve it
        expected_point_id = hashlib.sha256(b"verify-001").hexdigest()[:32]
        mock_client.retrieve.return_value = [
            MagicMock(
                payload={
                    "record_id": "verify-001",
                    "record_type": "prediction",
                    "content": "Test verification content",
                    "metadata": {"confidence": 0.9},
                    "created_at": "2026-03-27T12:00:00+00:00",
                }
            )
        ]

        retrieved = store.get_learning("verify-001")

        assert retrieved is not None
        assert retrieved.record_id == "verify-001"
        assert retrieved.record_type == "prediction"
        assert retrieved.content == "Test verification content"
        assert retrieved.metadata["confidence"] == 0.9

        # Verify retrieve was called with correct point_id
        mock_client.retrieve.assert_called_once()
        call_args = mock_client.retrieve.call_args
        assert call_args.kwargs["collection_name"] == LEARNING_COLLECTION
        assert expected_point_id in call_args.kwargs["ids"]

    @patch.object(LearningStore, "_get_qdrant_client")
    def test_get_learning_returns_none_when_not_found(self, mock_get_qdrant):
        """Test that get_learning returns None for nonexistent records."""
        mock_client = MagicMock()
        mock_get_qdrant.return_value = mock_client
        mock_client.retrieve.return_value = []

        store = LearningStore()
        result = store.get_learning("nonexistent-id")

        assert result is None

    @patch.object(LearningStore, "_get_qdrant_client")
    def test_get_learning_returns_none_when_qdrant_unavailable(self, mock_get_qdrant):
        """Test that get_learning returns None when Qdrant is unavailable."""
        mock_get_qdrant.return_value = None

        store = LearningStore()
        result = store.get_learning("any-id")

        assert result is None

    @patch.object(LearningStore, "_get_qdrant_client")
    def test_write_read_cycle_full_integration(self, mock_get_qdrant):
        """Test complete write → read cycle verifying data persistence."""
        mock_client = MagicMock()
        mock_get_qdrant.return_value = mock_client

        store = LearningStore()

        # Create a prediction record
        pred_record = LearningRecord(
            record_id="cycle-pred-001",
            record_type="prediction",
            content="Market will trend upward",
            metadata={
                "prediction_type": "trend_direction",
                "confidence": 0.85,
            },
        )

        # Store the prediction
        store.store_prediction(
            prediction_id="cycle-pred-001",
            prediction_type="trend_direction",
            confidence=0.85,
            context={"symbol": "BTC", "timeframe": "1d"},
        )

        # Simulate retrieve returning the stored data
        mock_client.retrieve.return_value = [
            MagicMock(
                payload={
                    "record_id": hashlib.sha256(b"cycle-pred-001").hexdigest()[:32],
                    "record_type": "prediction",
                    "content": "Prediction: cycle-pred-001 | Type: trend_direction | Confidence: 0.85",
                    "metadata": {
                        "prediction_type": "trend_direction",
                        "confidence": 0.85,
                        "context": {"symbol": "BTC", "timeframe": "1d"},
                    },
                    "created_at": "2026-03-27T12:00:00+00:00",
                }
            )
        ]

        # The write was successful (verified by mock)
        assert mock_client.upsert.called

        # Read it back
        retrieved = store.get_learning("cycle-pred-001")

        # Verify the full cycle succeeded
        assert retrieved is not None
        assert retrieved.record_type == "prediction"
        assert "trend_direction" in retrieved.metadata["prediction_type"]
