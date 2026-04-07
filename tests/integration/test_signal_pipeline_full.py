"""Integration test for full signal pipeline (TASK-M1).

Tests the complete signal pipeline:
  signal emission → signal_type tagging → confidence threshold →
  cache dedup → quality filter → persistence

Uses fakeredis and mock Qdrant to exercise all pipeline stages
without external dependencies.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from signal_generation.confidence_filter import ConfidenceFilter
from signal_generation.dedup import SignalDeduper
from signal_generation.models import Signal, SignalDirection, SignalStatus
from signal_generation.quality_filter import QualityFilter
from signal_generation.signal_memory import SignalMemory

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_signal(
    signal_id: str | None = None,
    token: str = "BTC/USDT",
    direction: SignalDirection = SignalDirection.LONG,
    confidence: float = 0.85,
    status: SignalStatus = SignalStatus.ACTIONABLE,
    timeframe: str = "1h",
    timestamp: datetime | None = None,
    metadata: dict | None = None,
) -> Signal:
    """Build a Signal object with sensible defaults for testing."""
    return Signal(
        token=token,
        direction=direction,
        confidence=confidence,
        base_score=confidence * 100,
        timestamp=timestamp or datetime(2026, 4, 5, 12, 0, 0, tzinfo=UTC),
        status=status,
        timeframe=timeframe,
        signal_id=signal_id or str(uuid.uuid4()),
        metadata=metadata or {},
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_redis():
    """Mock Redis client for deduper."""
    mock = MagicMock()
    mock.ping.return_value = True
    mock.get.return_value = None
    mock.set.return_value = True
    mock.delete.return_value = 1
    return mock


@pytest.fixture
def mock_qdrant():
    """Mock Qdrant client for signal memory."""
    mock = MagicMock()
    mock.get_collections.return_value = MagicMock(collections=[])
    mock.upsert.return_value = True
    return mock


# ---------------------------------------------------------------------------
# Pipeline Integration Tests
# ---------------------------------------------------------------------------


class TestFullSignalPipeline:
    """Test the complete signal processing pipeline end-to-end."""

    @pytest.mark.asyncio
    async def test_signal_emission_with_type_tagging(self):
        """Test that signals are emitted with correct signal_type metadata."""
        signal = _make_signal(
            signal_id="pipeline-emit-001",
            token="ETH/USDT",
            direction=SignalDirection.LONG,
            confidence=0.88,
            metadata={
                "signal_type": "fvg",
                "quality_score": 0.75,
            },
        )

        # Verify signal_type tagging in metadata
        assert signal.metadata.get("signal_type") == "fvg"
        assert signal.token == "ETH/USDT"
        assert signal.direction == SignalDirection.LONG
        assert signal.confidence == 0.88

    def test_confidence_threshold_filter_passes_high_confidence(self):
        """Test that high confidence signals pass the confidence filter."""
        filter = ConfidenceFilter(threshold=0.75)

        signal = _make_signal(
            signal_id="conf-pass-001",
            confidence=0.88,
            status=SignalStatus.ACTIONABLE,
        )

        result = filter.filter(signal)

        assert result.is_actionable is True
        assert result.confidence == 0.88
        assert result.threshold == 0.75

    def test_confidence_threshold_filter_rejects_low_confidence(self):
        """Test that low confidence signals are filtered by confidence threshold."""
        filter = ConfidenceFilter(threshold=0.75)

        signal = _make_signal(
            signal_id="conf-fail-001",
            confidence=0.60,
            status=SignalStatus.LOGGED_ONLY,
        )

        result = filter.filter(signal)

        assert result.is_actionable is False
        assert result.confidence == 0.60

    def test_confidence_threshold_boundary_at_75_percent(self):
        """Test boundary case: signal at exactly 75% threshold."""
        filter = ConfidenceFilter(threshold=0.75)

        signal = _make_signal(
            signal_id="conf-boundary-001",
            confidence=0.75,
            status=SignalStatus.ACTIONABLE,
        )

        result = filter.filter(signal)

        # 75% should meet threshold (>=)
        assert result.is_actionable is True

    def test_cache_dedup_allows_unique_signals(self, mock_redis):
        """Test that unique signals are not marked as duplicates."""
        deduper = SignalDeduper()
        deduper._redis_client = mock_redis

        signal = _make_signal(
            signal_id="dedup-unique-001",
            token="BTC/USDT",
        )

        result = deduper.is_duplicate(signal)

        assert result.is_duplicate is False
        assert result.signal_id == "dedup-unique-001"

    def test_cache_dedup_detects_duplicate_signals(self, mock_redis):
        """Test that signals with same ID within window are marked as duplicates.

        Uses side_effect to simulate real Redis behavior:
        - First call with a new key returns True (key set, not duplicate)
        - Subsequent calls return None (key exists, is duplicate)
        """
        deduper = SignalDeduper()
        deduper._redis_client = mock_redis

        signal = _make_signal(
            signal_id="dedup-dup-001",
            token="BTC/USDT",
        )

        # Simulate Redis: first set succeeds (not duplicate), second returns None (duplicate)
        mock_redis.set.side_effect = [True, None]

        # First call - not a duplicate (Redis set succeeded)
        result1 = deduper.is_duplicate(signal)
        assert result1.is_duplicate is False

        # Second call with same signal - now a duplicate (Redis set returned None)
        result2 = deduper.is_duplicate(signal)
        assert result2.is_duplicate is True

    def test_quality_filter_passes_high_quality(self):
        """Test that signals with high quality_score pass the quality filter."""
        filter = QualityFilter(threshold=0.5)

        signal = _make_signal(
            signal_id="quality-pass-001",
            metadata={"quality_score": 0.75},
        )

        result = filter.filter(signal)

        assert result.is_qualified is True
        assert result.quality_score == 0.75
        assert result.threshold == 0.5

    def test_quality_filter_rejects_low_quality(self):
        """Test that signals with low quality_score are filtered."""
        filter = QualityFilter(threshold=0.5)

        signal = _make_signal(
            signal_id="quality-fail-001",
            metadata={"quality_score": 0.30},
        )

        result = filter.filter(signal)

        assert result.is_qualified is False
        assert result.quality_score == 0.30

    def test_quality_filter_rejects_missing_quality_score(self):
        """Test that signals missing quality_score are filtered."""
        filter = QualityFilter(threshold=0.5)

        signal = _make_signal(
            signal_id="quality-missing-001",
            metadata={},  # No quality_score
        )

        result = filter.filter(signal)

        assert result.is_qualified is False
        assert result.quality_score is None
        assert "missing" in result.reason.lower()

    def test_quality_filter_boundary_at_50_percent(self):
        """Test boundary case: signal at exactly 50% quality threshold."""
        filter = QualityFilter(threshold=0.5)

        signal = _make_signal(
            signal_id="quality-boundary-001",
            metadata={"quality_score": 0.50},
        )

        result = filter.filter(signal)

        # 50% should meet threshold (>=)
        assert result.is_qualified is True

    @patch.object(SignalMemory, "client", new_callable=lambda: MagicMock())
    def test_persistence_stores_signal(self, mock_qdrant_client):
        """Test that SignalMemory can store signals to Qdrant."""
        memory = SignalMemory()
        memory._client = mock_qdrant_client

        signal = _make_signal(
            signal_id="persist-001",
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            metadata={"signal_type": "cvd", "quality_score": 0.70},
        )

        # Ensure collection exists (mocked)
        with patch.object(memory, "ensure_collection", return_value=True):
            stored_id = memory.store_signal(signal)

        assert stored_id == "persist-001"
        mock_qdrant_client.upsert.assert_called_once()

    def test_full_pipeline_integration(self, mock_redis):
        """Test complete pipeline flow through all stages.

        This test verifies:
        1. Signal is created with signal_type tagging
        2. Confidence filter accepts high-confidence signals
        3. Deduper allows unique signals through
        4. Quality filter accepts high-quality signals
        5. Signal is ready for persistence
        """
        # Stage 1: Create signal with tagging
        signal = _make_signal(
            signal_id="full-pipeline-001",
            token="ETH/USDT",
            direction=SignalDirection.SHORT,
            confidence=0.92,  # High confidence
            status=SignalStatus.ACTIONABLE,
            metadata={
                "signal_type": "order_block",
                "quality_score": 0.85,  # High quality
            },
        )

        # Verify signal_type tagging
        assert signal.metadata.get("signal_type") == "order_block"

        # Stage 2: Confidence threshold check
        conf_filter = ConfidenceFilter(threshold=0.75)
        conf_result = conf_filter.filter(signal)
        assert conf_result.is_actionable is True

        # Stage 3: Cache deduplication check
        deduper = SignalDeduper()
        deduper._redis_client = mock_redis
        dedup_result = deduper.is_duplicate(signal)
        assert dedup_result.is_duplicate is False

        # Stage 4: Quality filter check
        qual_filter = QualityFilter(threshold=0.5)
        qual_result = qual_filter.filter(signal)
        assert qual_result.is_qualified is True

        # Stage 5: Signal is ready for persistence
        assert signal.is_actionable is True

    def test_full_pipeline_filters_duplicate_with_low_quality(self, mock_redis):
        """Test that pipeline correctly filters a duplicate signal.

        Even if a signal has high confidence, it should be filtered
        by the deduper if it's a duplicate.
        """
        # Signal with high confidence but marked as duplicate
        signal = _make_signal(
            signal_id="dup-filter-001",
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.90,
            metadata={"signal_type": "fvg", "quality_score": 0.80},
        )

        deduper = SignalDeduper()
        deduper._redis_client = mock_redis

        # Simulate: set() returns None (key exists = duplicate)
        # get() returns a timestamp for the duplicate's original timestamp
        mock_redis.set = MagicMock(return_value=None)  # Key exists
        mock_redis.get = MagicMock(return_value="1775591719.123")  # Original timestamp

        dedup_result = deduper.is_duplicate(signal)
        assert dedup_result.is_duplicate is True

        # Pipeline should stop at dedup stage for duplicates
        # (no further processing needed)

    def test_full_pipeline_filters_low_confidence(self):
        """Test that pipeline correctly filters low confidence signals."""
        signal = _make_signal(
            signal_id="low-conf-pipeline-001",
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.50,  # Below threshold
            status=SignalStatus.LOGGED_ONLY,
            metadata={"signal_type": "bos", "quality_score": 0.90},
        )

        conf_filter = ConfidenceFilter(threshold=0.75)
        conf_result = conf_filter.filter(signal)

        assert conf_result.is_actionable is False
        # Should not proceed to dedup or quality filter

    def test_full_pipeline_filters_low_quality(self):
        """Test that pipeline correctly filters low quality signals."""
        signal = _make_signal(
            signal_id="low-qual-pipeline-001",
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,  # Above confidence threshold
            status=SignalStatus.ACTIONABLE,
            metadata={"signal_type": "choch", "quality_score": 0.20},  # Low quality
        )

        # Pass confidence filter
        conf_filter = ConfidenceFilter(threshold=0.75)
        conf_result = conf_filter.filter(signal)
        assert conf_result.is_actionable is True

        # Fail quality filter
        qual_filter = QualityFilter(threshold=0.5)
        qual_result = qual_filter.filter(signal)
        assert qual_result.is_qualified is False

    def test_pipeline_with_ict_signal_types(self, mock_redis):
        """Test pipeline correctly handles various ICT signal types."""
        ict_types = ["cvd", "fvg", "order_block", "bos", "choch"]

        for signal_type in ict_types:
            signal = _make_signal(
                signal_id=f"ict-{signal_type}-001",
                token="BTC/USDT",
                direction=SignalDirection.LONG,
                confidence=0.88,
                status=SignalStatus.ACTIONABLE,
                metadata={
                    "signal_type": signal_type,
                    "quality_score": 0.75,
                },
            )

            # Verify signal_type tagging
            assert signal.metadata.get("signal_type") == signal_type

            # Verify confidence filter
            conf_filter = ConfidenceFilter(threshold=0.75)
            conf_result = conf_filter.filter(signal)
            assert conf_result.is_actionable is True

            # Verify deduper
            deduper = SignalDeduper()
            deduper._redis_client = mock_redis
            dedup_result = deduper.is_duplicate(signal)
            assert dedup_result.is_duplicate is False

            # Verify quality filter
            qual_filter = QualityFilter(threshold=0.5)
            qual_result = qual_filter.filter(signal)
            assert qual_result.is_qualified is True


class TestSignalPipelineDeterminism:
    """Test that pipeline produces deterministic, repeatable results."""

    def test_same_signal_produces_same_result(self, mock_redis):
        """Test that the same signal always produces the same pipeline result.

        This test verifies determinism by checking that:
        1. Confidence filter always returns same result for same signal
        2. Quality filter always returns same result for same signal
        3. Deduper behavior is consistent (first call = not duplicate,
           second call via cache = duplicate)
        """
        signal = _make_signal(
            signal_id="deterministic-001",
            token="ETH/USDT",
            direction=SignalDirection.SHORT,
            confidence=0.85,
            status=SignalStatus.ACTIONABLE,
            metadata={"signal_type": "fvg", "quality_score": 0.72},
        )

        # Configure mock: first set succeeds, subsequent calls for same key
        # return None (duplicate) via local cache (not Redis)
        mock_redis.set.return_value = True  # Fresh signal, set succeeds

        # Run through pipeline twice
        conf_filter = ConfidenceFilter(threshold=0.75)
        deduper = SignalDeduper()
        deduper._redis_client = mock_redis
        qual_filter = QualityFilter(threshold=0.5)

        # First pass - fresh signal, not in local cache yet
        result1_conf = conf_filter.filter(signal)
        result1_dedup = deduper.is_duplicate(signal)
        result1_qual = qual_filter.filter(signal)

        # Second pass - same signal, should use local cache (already added)
        result2_conf = conf_filter.filter(signal)
        result2_dedup = deduper.is_duplicate(signal)  # Will hit local cache
        result2_qual = qual_filter.filter(signal)

        # Confidence and quality results should be identical
        assert result1_conf.is_actionable == result2_conf.is_actionable
        assert result1_qual.is_qualified == result2_qual.is_qualified

        # Deduper: first call = not duplicate, second call = duplicate (local cache)
        # This is the expected deterministic behavior
        assert result1_dedup.is_duplicate is False  # First call, Redis set succeeded
        assert result2_dedup.is_duplicate is True  # Second call, found in local cache

    def test_different_signals_produce_different_results(self, mock_redis):
        """Test that different signals can produce different pipeline results."""
        signal_high = _make_signal(
            signal_id="diff-high-001",
            confidence=0.90,
            metadata={"quality_score": 0.80},
        )
        signal_low = _make_signal(
            signal_id="diff-low-001",
            confidence=0.60,
            metadata={"quality_score": 0.30},
        )

        conf_filter = ConfidenceFilter(threshold=0.75)
        qual_filter = QualityFilter(threshold=0.5)

        result_high = conf_filter.filter(signal_high)
        result_low = conf_filter.filter(signal_low)

        assert result_high.is_actionable is True
        assert result_low.is_actionable is False
        # Different confidence should yield different actionable status

        qual_high = qual_filter.filter(signal_high)
        qual_low = qual_filter.filter(signal_low)

        assert qual_high.is_qualified is True
        assert qual_low.is_qualified is False
