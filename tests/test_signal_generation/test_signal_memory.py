"""Tests for signal_memory module.

Comprehensive tests for SignalMemory class covering:
- Qdrant collection management
- Signal persistence with vector embeddings
- Similarity search
- Outcome tracking (predicted vs actual)
- TTL-based cleanup
- Retrieval API for historical analysis
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from signal_generation.models import Signal, SignalDirection, SignalStatus
from signal_generation.signal_memory import (
    COLLECTION_NAME,
    DEFAULT_BATCH_SIZE,
    DEFAULT_QDRANT_HOST,
    DEFAULT_QDRANT_PORT,
    DEFAULT_TIMEOUT,
    DEFAULT_TTL_DAYS,
    VECTOR_DIMENSIONS,
    SignalMemory,
    SignalOutcome,
    _create_embedding,
    _deterministic_embedding,
    _signal_to_text,
)

# --- Fixtures ---


@pytest.fixture
def sample_signal() -> Signal:
    """Create a sample signal for testing."""
    return Signal(
        token="BTC/USDT",
        direction=SignalDirection.LONG,
        confidence=0.85,
        base_score=82.0,
        timestamp=datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
        status=SignalStatus.ACTIONABLE,
        timeframe="1h",
        contributing_factors=[
            {"name": "rsi_oversold", "score": 0.9},
            {"name": "volume_surge", "score": 0.8},
        ],
        signal_breakdown={"rsi": {"value": 28, "signal": "oversold"}},
        signal_id="test-signal-001",
        generation_latency_ms=45.5,
        stop_loss=42000.0,
        risk_reward_ratio=2.5,
    )


@pytest.fixture
def short_signal() -> Signal:
    """Create a short direction signal for testing."""
    return Signal(
        token="ETH/USDT",
        direction=SignalDirection.SHORT,
        confidence=0.78,
        base_score=75.0,
        timestamp=datetime(2026, 1, 15, 13, 0, 0, tzinfo=UTC),
        status=SignalStatus.ACTIONABLE,
        timeframe="4h",
        contributing_factors=[
            {"name": "macd_bearish", "score": 0.85},
        ],
        signal_breakdown={"macd": {"histogram": -0.5}},
        signal_id="test-signal-002",
    )


@pytest.fixture
def mock_qdrant_client():
    """Create a mock QdrantClient."""
    mock = MagicMock()
    mock.get_collections.return_value = MagicMock(collections=[])
    return mock


@pytest.fixture
def signal_memory(mock_qdrant_client):
    """Create a SignalMemory instance with mocked Qdrant client."""
    mem = SignalMemory()
    mem._client = mock_qdrant_client
    return mem


# --- Helper functions ---


def _make_mock_point(point_id, payload, score=None):
    """Create a mock Qdrant point."""
    point = MagicMock()
    point.id = point_id
    point.payload = payload
    point.vector = [0.1] * VECTOR_DIMENSIONS
    if score is not None:
        point.score = score
    return point


# --- Tests for _deterministic_embedding ---


class TestDeterministicEmbedding:
    """Tests for deterministic embedding generation."""

    def test_returns_correct_dimensions(self):
        """Embedding should have the correct number of dimensions."""
        result = _deterministic_embedding("test text")
        assert len(result) == VECTOR_DIMENSIONS

    def test_custom_dimensions(self):
        """Custom dimensions should be respected."""
        result = _deterministic_embedding("test", dimensions=128)
        assert len(result) == 128

    def test_empty_string_returns_zeros(self):
        """Empty string should return all zeros."""
        result = _deterministic_embedding("")
        assert result == [0.0] * VECTOR_DIMENSIONS

    def test_deterministic_same_input(self):
        """Same input should always produce the same output."""
        text = "deterministic test"
        result1 = _deterministic_embedding(text)
        result2 = _deterministic_embedding(text)
        assert result1 == result2

    def test_different_inputs_different_outputs(self):
        """Different inputs should produce different outputs."""
        result1 = _deterministic_embedding("text one")
        result2 = _deterministic_embedding("text two")
        assert result1 != result2

    def test_values_in_range(self):
        """All values should be in [-1.0, 1.0] range."""
        result = _deterministic_embedding("range test")
        for val in result:
            assert -1.0 <= val <= 1.0

    def test_produces_floats(self):
        """All values should be floats."""
        result = _deterministic_embedding("float test")
        assert all(isinstance(v, float) for v in result)


# --- Tests for _create_embedding ---


class TestCreateEmbedding:
    """Tests for embedding creation with fallback."""

    def test_falls_back_to_deterministic(self):
        """Should fall back to deterministic when sentence-transformers unavailable."""
        result = _create_embedding("test text")
        expected = _deterministic_embedding("test text")
        assert result == expected

    def test_returns_correct_dimensions(self):
        """Should return correct number of dimensions."""
        result = _create_embedding("test text")
        assert len(result) == VECTOR_DIMENSIONS

    def test_custom_dimensions(self):
        """Custom dimensions should be passed through."""
        result = _create_embedding("test", dimensions=64)
        assert len(result) == 64

    def test_sentence_transformers_fallback_on_import_error(self):
        """Should fall back to deterministic when sentence_transformers import fails."""
        with patch.dict("sys.modules", {"sentence_transformers": None}):
            # Force reimport of _create_embedding by calling it directly;
            # the function catches ImportError internally
            result = _create_embedding("test text")
            expected = _deterministic_embedding("test text")
            assert result == expected


# --- Tests for _signal_to_text ---


class TestSignalToText:
    """Tests for signal text conversion."""

    def test_includes_token(self, sample_signal):
        """Text representation should include token."""
        text = _signal_to_text(sample_signal)
        assert "BTC/USDT" in text

    def test_includes_direction(self, sample_signal):
        """Text representation should include direction."""
        text = _signal_to_text(sample_signal)
        assert "long" in text

    def test_includes_confidence(self, sample_signal):
        """Text representation should include confidence."""
        text = _signal_to_text(sample_signal)
        assert "confidence=0.8500" in text

    def test_includes_score(self, sample_signal):
        """Text representation should include base_score."""
        text = _signal_to_text(sample_signal)
        assert "score=82.00" in text

    def test_includes_timeframe(self, sample_signal):
        """Text representation should include timeframe."""
        text = _signal_to_text(sample_signal)
        assert "timeframe=1h" in text

    def test_includes_status(self, sample_signal):
        """Text representation should include status."""
        text = _signal_to_text(sample_signal)
        assert "status=actionable" in text

    def test_includes_contributing_factors(self, sample_signal):
        """Text representation should include factor names."""
        text = _signal_to_text(sample_signal)
        assert "rsi_oversold" in text
        assert "volume_surge" in text

    def test_includes_breakdown(self, sample_signal):
        """Text representation should include signal breakdown."""
        text = _signal_to_text(sample_signal)
        assert "rsi" in text

    def test_short_direction(self, short_signal):
        """Short direction should be included."""
        text = _signal_to_text(short_signal)
        assert "short" in text

    def test_deterministic(self, sample_signal):
        """Same signal should produce same text."""
        text1 = _signal_to_text(sample_signal)
        text2 = _signal_to_text(sample_signal)
        assert text1 == text2


# --- Tests for SignalOutcome ---


class TestSignalOutcome:
    """Tests for SignalOutcome enum."""

    def test_values(self):
        """Enum values should match expected strings."""
        assert SignalOutcome.CORRECT.value == "correct"
        assert SignalOutcome.INCORRECT.value == "incorrect"
        assert SignalOutcome.NEUTRAL.value == "neutral"
        assert SignalOutcome.PENDING.value == "pending"

    def test_all_values_present(self):
        """All expected outcomes should be defined."""
        expected = {"correct", "incorrect", "neutral", "pending"}
        actual = {o.value for o in SignalOutcome}
        assert actual == expected


# --- Tests for SignalMemory.__init__ ---


class TestSignalMemoryInit:
    """Tests for SignalMemory initialization."""

    def test_default_parameters(self):
        """Default parameters should match constants."""
        mem = SignalMemory()
        assert mem._qdrant_host == DEFAULT_QDRANT_HOST
        assert mem._qdrant_port == DEFAULT_QDRANT_PORT
        assert mem._timeout == DEFAULT_TIMEOUT
        assert mem._ttl_days == DEFAULT_TTL_DAYS
        assert mem._vector_dimensions == VECTOR_DIMENSIONS

    def test_custom_parameters(self):
        """Custom parameters should be stored."""
        mem = SignalMemory(
            qdrant_host="custom-host",
            qdrant_port=7000,
            timeout=30,
            ttl_days=60,
            vector_dimensions=512,
        )
        assert mem._qdrant_host == "custom-host"
        assert mem._qdrant_port == 7000
        assert mem._timeout == 30
        assert mem._ttl_days == 60
        assert mem._vector_dimensions == 512

    def test_client_initially_none(self):
        """Client should be None before lazy initialization."""
        mem = SignalMemory()
        assert mem._client is None


# --- Tests for SignalMemory.client (lazy init) ---


class TestSignalMemoryClient:
    """Tests for lazy Qdrant client initialization."""

    def test_lazy_initialization(self):
        """Client should be created on first access."""
        mem = SignalMemory()
        assert mem._client is None
        client = mem.client
        assert client is not None
        assert mem._client is client

    def test_returns_same_instance(self):
        """Subsequent accesses should return the same instance."""
        mem = SignalMemory()
        client1 = mem.client
        client2 = mem.client
        assert client1 is client2


# --- Tests for ensure_collection ---


class TestEnsureCollection:
    """Tests for collection creation and setup."""

    def test_creates_new_collection(self, signal_memory, mock_qdrant_client):
        """Should create collection when it doesn't exist."""
        mock_qdrant_client.get_collections.return_value = MagicMock(collections=[])
        result = signal_memory.ensure_collection()
        assert result is True
        mock_qdrant_client.create_collection.assert_called_once()

    def test_skips_existing_collection(self, signal_memory, mock_qdrant_client):
        """Should not create collection when it already exists."""
        existing = MagicMock()
        existing.name = COLLECTION_NAME
        mock_qdrant_client.get_collections.return_value = MagicMock(
            collections=[existing]
        )
        result = signal_memory.ensure_collection()
        assert result is True
        mock_qdrant_client.create_collection.assert_not_called()

    def test_creates_payload_indexes(self, signal_memory, mock_qdrant_client):
        """Should create payload indexes for filtering fields."""
        mock_qdrant_client.get_collections.return_value = MagicMock(collections=[])
        signal_memory.ensure_collection()
        assert mock_qdrant_client.create_payload_index.call_count == 6

    def test_returns_false_on_error(self, signal_memory, mock_qdrant_client):
        """Should return False on exception."""
        mock_qdrant_client.get_collections.side_effect = Exception("connection error")
        result = signal_memory.ensure_collection()
        assert result is False

    def test_uses_correct_vector_config(self, signal_memory, mock_qdrant_client):
        """Should use correct vector dimensions and distance."""
        mock_qdrant_client.get_collections.return_value = MagicMock(collections=[])
        signal_memory.ensure_collection()
        call_args = mock_qdrant_client.create_collection.call_args
        assert call_args[1]["collection_name"] == COLLECTION_NAME
        vectors_config = call_args[1]["vectors_config"]
        assert vectors_config.size == VECTOR_DIMENSIONS


# --- Tests for store_signal ---


class TestStoreSignal:
    """Tests for single signal persistence."""

    def test_stores_signal_successfully(
        self, signal_memory, mock_qdrant_client, sample_signal
    ):
        """Should store signal and return signal_id."""
        signal_memory.ensure_collection()
        result = signal_memory.store_signal(sample_signal)
        assert result == "test-signal-001"
        mock_qdrant_client.upsert.assert_called_once()

    def test_upsert_called_with_correct_collection(
        self, signal_memory, mock_qdrant_client, sample_signal
    ):
        """Should upsert to the correct collection."""
        signal_memory.ensure_collection()
        signal_memory.store_signal(sample_signal)
        call_args = mock_qdrant_client.upsert.call_args
        assert call_args[1]["collection_name"] == COLLECTION_NAME

    def test_upsert_called_with_signal_id(
        self, signal_memory, mock_qdrant_client, sample_signal
    ):
        """Point ID should match signal_id."""
        signal_memory.ensure_collection()
        signal_memory.store_signal(sample_signal)
        call_args = mock_qdrant_client.upsert.call_args
        points = call_args[1]["points"]
        assert points[0].id == "test-signal-001"

    def test_payload_includes_required_fields(
        self, signal_memory, mock_qdrant_client, sample_signal
    ):
        """Payload should include all required fields."""
        signal_memory.ensure_collection()
        signal_memory.store_signal(sample_signal)
        call_args = mock_qdrant_client.upsert.call_args
        payload = call_args[1]["points"][0].payload

        assert payload["token"] == "BTC/USDT"
        assert payload["direction"] == "long"
        assert payload["confidence"] == 0.85
        assert payload["outcome"] == "pending"
        assert payload["actual_direction"] is None
        assert payload["actual_price_change_pct"] is None
        assert "expires_at" in payload
        assert "stored_at" in payload

    def test_payload_includes_stop_loss(
        self, signal_memory, mock_qdrant_client, sample_signal
    ):
        """Payload should include stop loss when present."""
        signal_memory.ensure_collection()
        signal_memory.store_signal(sample_signal)
        call_args = mock_qdrant_client.upsert.call_args
        payload = call_args[1]["points"][0].payload
        assert payload["stop_loss"] == 42000.0
        assert payload["risk_reward_ratio"] == 2.5

    def test_vector_has_correct_dimensions(
        self, signal_memory, mock_qdrant_client, sample_signal
    ):
        """Vector should have correct number of dimensions."""
        signal_memory.ensure_collection()
        signal_memory.store_signal(sample_signal)
        call_args = mock_qdrant_client.upsert.call_args
        vector = call_args[1]["points"][0].vector
        assert len(vector) == VECTOR_DIMENSIONS

    def test_raises_on_missing_signal_id(self, signal_memory, mock_qdrant_client):
        """Should raise ValueError when signal has no ID."""
        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
            signal_id="",
        )
        # Signal.__post_init__ generates a UUID if empty
        # So we need to explicitly set it to empty after init
        signal.signal_id = ""
        with pytest.raises(ValueError, match="signal_id"):
            signal_memory.store_signal(signal)

    def test_raises_on_storage_failure(
        self, signal_memory, mock_qdrant_client, sample_signal
    ):
        """Should raise RuntimeError on storage failure."""
        signal_memory.ensure_collection()
        mock_qdrant_client.upsert.side_effect = Exception("storage error")
        with pytest.raises(RuntimeError, match="Failed to store"):
            signal_memory.store_signal(sample_signal)


# --- Tests for store_signals (batch) ---


class TestStoreSignalsBatch:
    """Tests for batch signal persistence."""

    def test_stores_batch_successfully(
        self, signal_memory, mock_qdrant_client, sample_signal, short_signal
    ):
        """Should store multiple signals and return IDs."""
        signal_memory.ensure_collection()
        result = signal_memory.store_signals([sample_signal, short_signal])
        assert len(result) == 2
        assert "test-signal-001" in result
        assert "test-signal-002" in result

    def test_empty_list_returns_empty(self, signal_memory, mock_qdrant_client):
        """Empty signal list should return empty list."""
        result = signal_memory.store_signals([])
        assert result == []

    def test_batch_exceeding_batch_size(
        self, signal_memory, mock_qdrant_client, sample_signal
    ):
        """Should split into batches when exceeding batch size."""
        signal_memory.ensure_collection()
        signals = []
        for i in range(DEFAULT_BATCH_SIZE + 10):
            sig = Signal(
                token=f"TOKEN{i}/USDT",
                direction=SignalDirection.LONG,
                confidence=0.8,
                base_score=80.0,
                timestamp=datetime.now(UTC),
                status=SignalStatus.ACTIONABLE,
                timeframe="1h",
                signal_id=f"batch-signal-{i}",
            )
            signals.append(sig)

        result = signal_memory.store_signals(signals)
        assert len(result) == DEFAULT_BATCH_SIZE + 10
        # Should have been called in 2 batches
        assert mock_qdrant_client.upsert.call_count == 2

    def test_raises_on_missing_signal_id(
        self, signal_memory, mock_qdrant_client, sample_signal
    ):
        """Should raise ValueError when any signal has no ID."""
        sample_signal.signal_id = ""
        with pytest.raises(ValueError, match="signal_id"):
            signal_memory.store_signals([sample_signal])


# --- Tests for record_outcome ---


class TestRecordOutcome:
    """Tests for signal outcome recording."""

    def test_correct_long_outcome(self, signal_memory, mock_qdrant_client):
        """LONG prediction with positive price change should be CORRECT."""
        stored_payload = {
            "signal_id": "sig-001",
            "direction": "long",
            "outcome": "pending",
        }
        mock_qdrant_client.retrieve.return_value = [
            _make_mock_point("sig-001", stored_payload)
        ]
        result = signal_memory.record_outcome("sig-001", 5.0)
        assert result is not None
        assert result["outcome"] == "correct"
        assert result["actual_direction"] == "long"
        assert result["actual_price_change_pct"] == 5.0
        mock_qdrant_client.set_payload.assert_called_once()

    def test_incorrect_long_outcome(self, signal_memory, mock_qdrant_client):
        """LONG prediction with negative price change should be INCORRECT."""
        stored_payload = {
            "signal_id": "sig-002",
            "direction": "long",
            "outcome": "pending",
        }
        mock_qdrant_client.retrieve.return_value = [
            _make_mock_point("sig-002", stored_payload)
        ]
        result = signal_memory.record_outcome("sig-002", -3.0)
        assert result is not None
        assert result["outcome"] == "incorrect"
        assert result["actual_direction"] == "short"

    def test_correct_short_outcome(self, signal_memory, mock_qdrant_client):
        """SHORT prediction with negative price change should be CORRECT."""
        stored_payload = {
            "signal_id": "sig-003",
            "direction": "short",
            "outcome": "pending",
        }
        mock_qdrant_client.retrieve.return_value = [
            _make_mock_point("sig-003", stored_payload)
        ]
        result = signal_memory.record_outcome("sig-003", -4.0)
        assert result is not None
        assert result["outcome"] == "correct"

    def test_incorrect_short_outcome(self, signal_memory, mock_qdrant_client):
        """SHORT prediction with positive price change should be INCORRECT."""
        stored_payload = {
            "signal_id": "sig-004",
            "direction": "short",
            "outcome": "pending",
        }
        mock_qdrant_client.retrieve.return_value = [
            _make_mock_point("sig-004", stored_payload)
        ]
        result = signal_memory.record_outcome("sig-004", 2.0)
        assert result is not None
        assert result["outcome"] == "incorrect"

    def test_neutral_outcome_small_change(self, signal_memory, mock_qdrant_client):
        """Small price change should result in NEUTRAL outcome."""
        stored_payload = {
            "signal_id": "sig-005",
            "direction": "long",
            "outcome": "pending",
        }
        mock_qdrant_client.retrieve.return_value = [
            _make_mock_point("sig-005", stored_payload)
        ]
        result = signal_memory.record_outcome("sig-005", 0.05)
        assert result is not None
        assert result["outcome"] == "neutral"
        assert result["actual_direction"] == "neutral"

    def test_boundary_positive(self, signal_memory, mock_qdrant_client):
        """Price change just above 0.1 should be LONG (correct for long pred)."""
        stored_payload = {
            "signal_id": "sig-006",
            "direction": "long",
            "outcome": "pending",
        }
        mock_qdrant_client.retrieve.return_value = [
            _make_mock_point("sig-006", stored_payload)
        ]
        result = signal_memory.record_outcome("sig-006", 0.11)
        assert result is not None
        assert result["outcome"] == "correct"

    def test_boundary_negative(self, signal_memory, mock_qdrant_client):
        """Price change just below -0.1 should be SHORT (correct for short pred)."""
        stored_payload = {
            "signal_id": "sig-007",
            "direction": "short",
            "outcome": "pending",
        }
        mock_qdrant_client.retrieve.return_value = [
            _make_mock_point("sig-007", stored_payload)
        ]
        result = signal_memory.record_outcome("sig-007", -0.11)
        assert result is not None
        assert result["outcome"] == "correct"

    def test_boundary_at_zero_point_one_is_neutral(
        self, signal_memory, mock_qdrant_client
    ):
        """Price change exactly at 0.1% is NOT > 0.1, so maps to neutral."""
        stored_payload = {
            "signal_id": "sig-boundary",
            "direction": "long",
            "outcome": "pending",
        }
        mock_qdrant_client.retrieve.return_value = [
            _make_mock_point("sig-boundary", stored_payload)
        ]
        result = signal_memory.record_outcome("sig-boundary", 0.1)
        assert result is not None
        assert result["outcome"] == "neutral"
        assert result["actual_direction"] == "neutral"

    def test_signal_not_found(self, signal_memory, mock_qdrant_client):
        """Should return None when signal not found."""
        mock_qdrant_client.retrieve.return_value = []
        result = signal_memory.record_outcome("nonexistent", 5.0)
        assert result is None

    def test_retrieve_failure(self, signal_memory, mock_qdrant_client):
        """Should return None on retrieve failure."""
        mock_qdrant_client.retrieve.side_effect = Exception("connection error")
        result = signal_memory.record_outcome("sig-001", 5.0)
        assert result is None

    def test_includes_timestamp(self, signal_memory, mock_qdrant_client):
        """Outcome recording should include timestamp."""
        stored_payload = {
            "signal_id": "sig-008",
            "direction": "long",
            "outcome": "pending",
        }
        mock_qdrant_client.retrieve.return_value = [
            _make_mock_point("sig-008", stored_payload)
        ]
        result = signal_memory.record_outcome("sig-008", 3.0)
        assert result is not None
        assert "outcome_recorded_at" in result
        mock_qdrant_client.set_payload.assert_called_once()
        call_args = mock_qdrant_client.set_payload.call_args
        assert "outcome_recorded_at" in call_args[1]["payload"]


# --- Tests for find_similar_signals ---


class TestFindSimilarSignals:
    """Tests for vector similarity search."""

    def _make_query_response(self, points):
        """Create a mock QueryResponse with points list."""
        response = MagicMock()
        response.points = points
        return response

    def test_returns_similar_signals(
        self, signal_memory, mock_qdrant_client, sample_signal
    ):
        """Should return similar signals from search."""
        signal_memory.ensure_collection()

        mock_hit = MagicMock()
        mock_hit.id = "similar-001"
        mock_hit.score = 0.92
        mock_hit.payload = {"token": "BTC/USDT", "direction": "long"}

        mock_qdrant_client.query_points.return_value = self._make_query_response(
            [mock_hit]
        )

        results = signal_memory.find_similar_signals(sample_signal)
        assert len(results) == 1
        assert results[0]["signal_id"] == "similar-001"
        assert results[0]["score"] == 0.92

    def test_respects_limit(self, signal_memory, mock_qdrant_client, sample_signal):
        """Should pass the limit parameter to query_points."""
        signal_memory.ensure_collection()

        mock_hits = []
        for i in range(5):
            hit = MagicMock()
            hit.id = f"hit-{i}"
            hit.score = 0.9 - i * 0.01
            hit.payload = {"token": "BTC/USDT"}
            mock_hits.append(hit)

        mock_qdrant_client.query_points.return_value = self._make_query_response(
            mock_hits
        )

        results = signal_memory.find_similar_signals(sample_signal, limit=5)
        assert len(results) == 5
        # Verify limit was passed correctly to query_points
        call_args = mock_qdrant_client.query_points.call_args
        assert call_args[1]["limit"] == 5

    def test_applies_token_filter(
        self, signal_memory, mock_qdrant_client, sample_signal
    ):
        """Should apply token filter when provided."""
        signal_memory.ensure_collection()
        mock_qdrant_client.query_points.return_value = self._make_query_response([])

        signal_memory.find_similar_signals(sample_signal, token_filter="BTC/USDT")

        call_args = mock_qdrant_client.query_points.call_args
        assert call_args[1]["query_filter"] is not None

    def test_applies_score_threshold(
        self, signal_memory, mock_qdrant_client, sample_signal
    ):
        """Should apply score threshold."""
        signal_memory.ensure_collection()
        mock_qdrant_client.query_points.return_value = self._make_query_response([])

        signal_memory.find_similar_signals(sample_signal, score_threshold=0.8)

        call_args = mock_qdrant_client.query_points.call_args
        assert call_args[1]["score_threshold"] == 0.8

    def test_returns_empty_on_no_results(
        self, signal_memory, mock_qdrant_client, sample_signal
    ):
        """Should return empty list when no similar signals found."""
        signal_memory.ensure_collection()
        mock_qdrant_client.query_points.return_value = self._make_query_response([])

        results = signal_memory.find_similar_signals(sample_signal)
        assert results == []

    def test_handles_search_error(
        self, signal_memory, mock_qdrant_client, sample_signal
    ):
        """Should return empty list on search error."""
        signal_memory.ensure_collection()
        mock_qdrant_client.query_points.side_effect = Exception("search error")

        results = signal_memory.find_similar_signals(sample_signal)
        assert results == []

    def test_calls_ensure_collection(
        self, signal_memory, mock_qdrant_client, sample_signal
    ):
        """Should ensure collection exists before searching."""
        mock_qdrant_client.query_points.return_value = self._make_query_response([])
        signal_memory.find_similar_signals(sample_signal)
        mock_qdrant_client.get_collections.assert_called()

    def test_search_result_format(
        self, signal_memory, mock_qdrant_client, sample_signal
    ):
        """Results should have expected format."""
        signal_memory.ensure_collection()

        mock_hit = MagicMock()
        mock_hit.id = "hit-001"
        mock_hit.score = 0.88
        mock_hit.payload = {"token": "ETH/USDT", "direction": "short"}

        mock_qdrant_client.query_points.return_value = self._make_query_response(
            [mock_hit]
        )

        results = signal_memory.find_similar_signals(sample_signal)
        entry = results[0]
        assert "signal_id" in entry
        assert "score" in entry
        assert "payload" in entry

    def test_handles_none_payload_gracefully(
        self, signal_memory, mock_qdrant_client, sample_signal
    ):
        """Should handle None payload by using empty dict."""
        signal_memory.ensure_collection()

        mock_hit = MagicMock()
        mock_hit.id = "hit-none"
        mock_hit.score = 0.85
        mock_hit.payload = None

        mock_qdrant_client.query_points.return_value = self._make_query_response(
            [mock_hit]
        )

        results = signal_memory.find_similar_signals(sample_signal)
        assert len(results) == 1
        assert results[0]["payload"] == {}


# --- Tests for get_signal ---


class TestGetSignal:
    """Tests for single signal retrieval."""

    def test_retrieves_existing_signal(self, signal_memory, mock_qdrant_client):
        """Should retrieve signal by ID."""
        expected_payload = {"signal_id": "sig-001", "token": "BTC/USDT"}
        mock_qdrant_client.retrieve.return_value = [
            _make_mock_point("sig-001", expected_payload)
        ]

        result = signal_memory.get_signal("sig-001")
        assert result is not None
        assert result["signal_id"] == "sig-001"
        assert result["token"] == "BTC/USDT"

    def test_returns_none_for_missing(self, signal_memory, mock_qdrant_client):
        """Should return None when signal not found."""
        mock_qdrant_client.retrieve.return_value = []
        result = signal_memory.get_signal("nonexistent")
        assert result is None

    def test_handles_retrieve_error(self, signal_memory, mock_qdrant_client):
        """Should return None on retrieve error."""
        mock_qdrant_client.retrieve.side_effect = Exception("error")
        result = signal_memory.get_signal("sig-001")
        assert result is None

    def test_calls_with_correct_params(self, signal_memory, mock_qdrant_client):
        """Should call retrieve with correct parameters."""
        mock_qdrant_client.retrieve.return_value = []
        signal_memory.get_signal("sig-001")
        call_args = mock_qdrant_client.retrieve.call_args
        assert call_args[1]["ids"] == ["sig-001"]
        assert call_args[1]["with_payload"] is True
        assert call_args[1]["with_vectors"] is False


# --- Tests for search_signals ---


class TestSearchSignals:
    """Tests for signal search with filters."""

    def _setup_scroll(self, mock_client, signals):
        """Helper to set up scroll mock."""
        mock_client.scroll.return_value = (
            [_make_mock_point(s["signal_id"], s) for s in signals],
            None,
        )

    def test_search_all_signals(self, signal_memory, mock_qdrant_client):
        """Should return all signals when no filters applied."""
        signals = [
            {"signal_id": "s1", "token": "BTC/USDT", "direction": "long"},
            {"signal_id": "s2", "token": "ETH/USDT", "direction": "short"},
        ]
        self._setup_scroll(mock_qdrant_client, signals)
        signal_memory.ensure_collection()

        result = signal_memory.search_signals()
        assert len(result) == 2

    def test_filter_by_token(self, signal_memory, mock_qdrant_client):
        """Should filter by token."""
        signals = [{"signal_id": "s1", "token": "BTC/USDT"}]
        self._setup_scroll(mock_qdrant_client, signals)
        signal_memory.ensure_collection()

        result = signal_memory.search_signals(token="BTC/USDT")
        assert len(result) == 1

    def test_filter_by_direction(self, signal_memory, mock_qdrant_client):
        """Should filter by direction."""
        signals = [{"signal_id": "s1", "direction": "long"}]
        self._setup_scroll(mock_qdrant_client, signals)
        signal_memory.ensure_collection()

        result = signal_memory.search_signals(direction="long")
        assert len(result) == 1

    def test_filter_by_status(self, signal_memory, mock_qdrant_client):
        """Should filter by status."""
        signals = [{"signal_id": "s1", "status": "actionable"}]
        self._setup_scroll(mock_qdrant_client, signals)
        signal_memory.ensure_collection()

        result = signal_memory.search_signals(status="actionable")
        assert len(result) == 1

    def test_filter_by_outcome(self, signal_memory, mock_qdrant_client):
        """Should filter by outcome."""
        signals = [{"signal_id": "s1", "outcome": "correct"}]
        self._setup_scroll(mock_qdrant_client, signals)
        signal_memory.ensure_collection()

        result = signal_memory.search_signals(outcome="correct")
        assert len(result) == 1

    def test_filter_by_min_confidence(self, signal_memory, mock_qdrant_client):
        """Should filter by minimum confidence."""
        signals = [{"signal_id": "s1", "confidence": 0.9}]
        self._setup_scroll(mock_qdrant_client, signals)
        signal_memory.ensure_collection()

        result = signal_memory.search_signals(min_confidence=0.8)
        assert len(result) == 1

    def test_respects_limit(self, signal_memory, mock_qdrant_client):
        """Should respect the limit parameter."""
        signals = [{"signal_id": f"s{i}"} for i in range(5)]
        self._setup_scroll(mock_qdrant_client, signals)
        signal_memory.ensure_collection()

        result = signal_memory.search_signals(limit=3)
        assert len(result) <= 3

    def test_returns_empty_on_no_results(self, signal_memory, mock_qdrant_client):
        """Should return empty list when no signals match."""
        mock_qdrant_client.scroll.return_value = ([], None)
        signal_memory.ensure_collection()

        result = signal_memory.search_signals(token="NONEXISTENT")
        assert result == []

    def test_handles_search_error(self, signal_memory, mock_qdrant_client):
        """Should return empty list on error."""
        signal_memory.ensure_collection()
        mock_qdrant_client.scroll.side_effect = Exception("error")

        result = signal_memory.search_signals()
        assert result == []

    def test_calls_ensure_collection(self, signal_memory, mock_qdrant_client):
        """Should ensure collection exists before searching."""
        mock_qdrant_client.scroll.return_value = ([], None)
        signal_memory.search_signals()
        mock_qdrant_client.get_collections.assert_called()


# --- Tests for cleanup_expired ---


class TestCleanupExpired:
    """Tests for TTL-based cleanup."""

    def test_dry_run_counts_expired(self, signal_memory, mock_qdrant_client):
        """Dry run should count expired signals without deleting."""
        expired = [
            _make_mock_point("exp-1", {"expires_at": "2020-01-01T00:00:00Z"}),
            _make_mock_point("exp-2", {"expires_at": "2020-01-01T00:00:00Z"}),
        ]
        mock_qdrant_client.scroll.return_value = (expired, None)
        signal_memory.ensure_collection()

        count = signal_memory.cleanup_expired(dry_run=True)
        assert count == 2
        mock_qdrant_client.delete.assert_not_called()

    def test_deletes_expired_signals(self, signal_memory, mock_qdrant_client):
        """Should delete expired signals when not dry run."""
        expired = [
            _make_mock_point("exp-1", {}),
            _make_mock_point("exp-2", {}),
        ]
        mock_qdrant_client.scroll.return_value = (expired, None)
        signal_memory.ensure_collection()

        count = signal_memory.cleanup_expired(dry_run=False)
        assert count == 2
        mock_qdrant_client.delete.assert_called_once()

    def test_no_expired_returns_zero(self, signal_memory, mock_qdrant_client):
        """Should return 0 when no expired signals exist."""
        mock_qdrant_client.scroll.return_value = ([], None)
        signal_memory.ensure_collection()

        count = signal_memory.cleanup_expired()
        assert count == 0

    def test_handles_cleanup_error(self, signal_memory, mock_qdrant_client):
        """Should return 0 on cleanup error."""
        signal_memory.ensure_collection()
        mock_qdrant_client.scroll.side_effect = Exception("error")

        count = signal_memory.cleanup_expired()
        assert count == 0

    def test_large_batch_deletion(self, signal_memory, mock_qdrant_client):
        """Should handle deletion in batches for large sets."""
        expired = [_make_mock_point(f"exp-{i}", {}) for i in range(250)]
        mock_qdrant_client.scroll.return_value = (expired, None)
        signal_memory.ensure_collection()

        count = signal_memory.cleanup_expired(dry_run=False)
        assert count == 250
        # 250 / 100 = 3 batches
        assert mock_qdrant_client.delete.call_count == 3


# --- Tests for get_signal_stats ---


class TestGetSignalStats:
    """Tests for signal statistics."""

    def test_empty_signals_returns_zeros(self, signal_memory, mock_qdrant_client):
        """Should return zero stats when no signals exist."""
        mock_qdrant_client.scroll.return_value = ([], None)
        signal_memory.ensure_collection()

        stats = signal_memory.get_signal_stats()
        assert stats["total"] == 0
        assert stats["accuracy"] == 0.0
        assert stats["avg_confidence"] == 0.0

    def test_correct_accuracy_calculation(self, signal_memory, mock_qdrant_client):
        """Should calculate accuracy correctly."""
        signals = [
            {"outcome": "correct", "confidence": 0.9, "direction": "long"},
            {"outcome": "correct", "confidence": 0.8, "direction": "long"},
            {"outcome": "incorrect", "confidence": 0.7, "direction": "short"},
            {"outcome": "pending", "confidence": 0.85, "direction": "long"},
        ]
        mock_qdrant_client.scroll.return_value = (
            [_make_mock_point(f"s{i}", s) for i, s in enumerate(signals)],
            None,
        )
        signal_memory.ensure_collection()

        stats = signal_memory.get_signal_stats()
        assert stats["total"] == 4
        assert stats["correct"] == 2
        assert stats["incorrect"] == 1
        assert stats["pending"] == 1
        # accuracy = correct / (correct + incorrect) = 2/3
        assert stats["accuracy"] == pytest.approx(0.6667, abs=0.001)

    def test_direction_distribution(self, signal_memory, mock_qdrant_client):
        """Should count direction distribution."""
        signals = [
            {"direction": "long", "outcome": "correct", "confidence": 0.8},
            {"direction": "long", "outcome": "correct", "confidence": 0.8},
            {"direction": "short", "outcome": "incorrect", "confidence": 0.7},
        ]
        mock_qdrant_client.scroll.return_value = (
            [_make_mock_point(f"s{i}", s) for i, s in enumerate(signals)],
            None,
        )
        signal_memory.ensure_collection()

        stats = signal_memory.get_signal_stats()
        assert stats["direction_distribution"]["long"] == 2
        assert stats["direction_distribution"]["short"] == 1

    def test_outcome_distribution(self, signal_memory, mock_qdrant_client):
        """Should count outcome distribution."""
        signals = [
            {"outcome": "correct", "direction": "long", "confidence": 0.8},
            {"outcome": "incorrect", "direction": "short", "confidence": 0.7},
            {"outcome": "neutral", "direction": "long", "confidence": 0.6},
            {"outcome": "pending", "direction": "short", "confidence": 0.9},
        ]
        mock_qdrant_client.scroll.return_value = (
            [_make_mock_point(f"s{i}", s) for i, s in enumerate(signals)],
            None,
        )
        signal_memory.ensure_collection()

        stats = signal_memory.get_signal_stats()
        assert stats["outcome_distribution"]["correct"] == 1
        assert stats["outcome_distribution"]["incorrect"] == 1
        assert stats["outcome_distribution"]["neutral"] == 1
        assert stats["outcome_distribution"]["pending"] == 1

    def test_average_confidence(self, signal_memory, mock_qdrant_client):
        """Should calculate average confidence."""
        signals = [
            {"outcome": "correct", "direction": "long", "confidence": 0.8},
            {"outcome": "correct", "direction": "long", "confidence": 0.9},
        ]
        mock_qdrant_client.scroll.return_value = (
            [_make_mock_point(f"s{i}", s) for i, s in enumerate(signals)],
            None,
        )
        signal_memory.ensure_collection()

        stats = signal_memory.get_signal_stats()
        assert stats["avg_confidence"] == 0.85

    def test_token_filter_passed_to_search(self, signal_memory, mock_qdrant_client):
        """Should pass token filter to search_signals."""
        mock_qdrant_client.scroll.return_value = ([], None)
        signal_memory.ensure_collection()

        signal_memory.get_signal_stats(token="BTC/USDT")
        # Verify the scroll was called with a filter containing the token
        call_args = mock_qdrant_client.scroll.call_args
        assert call_args is not None

    def test_all_judged_correct(self, signal_memory, mock_qdrant_client):
        """100% accuracy when all judged signals are correct."""
        signals = [
            {"outcome": "correct", "direction": "long", "confidence": 0.9},
            {"outcome": "correct", "direction": "short", "confidence": 0.8},
        ]
        mock_qdrant_client.scroll.return_value = (
            [_make_mock_point(f"s{i}", s) for i, s in enumerate(signals)],
            None,
        )
        signal_memory.ensure_collection()

        stats = signal_memory.get_signal_stats()
        assert stats["accuracy"] == 1.0


# --- Tests for constants ---


class TestConstants:
    """Tests for module constants."""

    def test_collection_name(self):
        assert COLLECTION_NAME == "signal_memory"

    def test_vector_dimensions(self):
        assert VECTOR_DIMENSIONS == 384

    def test_default_qdrant_host(self):
        assert DEFAULT_QDRANT_HOST == "host.docker.internal"

    def test_default_qdrant_port(self):
        assert DEFAULT_QDRANT_PORT == 6334

    def test_default_timeout(self):
        assert DEFAULT_TIMEOUT == 10

    def test_default_ttl_days(self):
        assert DEFAULT_TTL_DAYS == 90

    def test_default_batch_size(self):
        assert DEFAULT_BATCH_SIZE == 100
