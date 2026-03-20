"""Tests for SentimentAggregator, SentimentScore, and AggregatedSentiment."""

from datetime import UTC, datetime

import pytest

from market_analysis.sentiment.aggregator import (
    AggregatedSentiment,
    BaseSentimentSource,
    SentimentAggregator,
    SentimentDirection,
    SentimentScore,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class StubSource(BaseSentimentSource):
    """Stub sentiment source for testing."""

    def __init__(
        self,
        name: str = "StubSource",
        value: float = 0.0,
        confidence: float = 1.0,
        available: bool = True,
        should_fail: bool = False,
    ):
        super().__init__(name=name)
        self._value = value
        self._confidence = confidence
        self._available = available
        self._should_fail = should_fail
        self.fetch_count = 0

    @property
    def description(self) -> str:
        return f"Stub source returning {self._value}"

    def fetch(self) -> SentimentScore:
        self.fetch_count += 1
        if self._should_fail:
            raise RuntimeError("Simulated fetch failure")
        return SentimentScore(
            source=self.name,
            value=self._value,
            timestamp=datetime.now(UTC),
            confidence=self._confidence,
            raw_value=self._value,
        )

    def is_available(self) -> bool:
        return self._available


# ---------------------------------------------------------------------------
# SentimentScore
# ---------------------------------------------------------------------------


class TestSentimentScore:
    """Test cases for SentimentScore dataclass."""

    def test_creation_with_valid_values(self):
        """Test creating a valid SentimentScore."""
        score = SentimentScore(
            source="test",
            value=0.5,
            timestamp=datetime.now(UTC),
        )
        assert score.source == "test"
        assert score.value == 0.5
        assert score.confidence == 1.0
        assert score.raw_value is None

    def test_creation_with_all_fields(self):
        """Test creating SentimentScore with all fields."""
        ts = datetime.now(UTC)
        score = SentimentScore(
            source="test",
            value=-0.3,
            timestamp=ts,
            confidence=0.7,
            raw_value=35.0,
            metadata={"key": "value"},
        )
        assert score.value == -0.3
        assert score.confidence == 0.7
        assert score.raw_value == 35.0
        assert score.metadata == {"key": "value"}

    def test_value_boundary_min(self):
        """Test minimum boundary value -1.0."""
        score = SentimentScore(source="test", value=-1.0, timestamp=datetime.now(UTC))
        assert score.value == -1.0

    def test_value_boundary_max(self):
        """Test maximum boundary value +1.0."""
        score = SentimentScore(source="test", value=1.0, timestamp=datetime.now(UTC))
        assert score.value == 1.0

    def test_value_below_min_raises(self):
        """Test that value below -1.0 raises ValueError."""
        with pytest.raises(ValueError, match="\\[-1, \\+1\\]"):
            SentimentScore(source="test", value=-1.1, timestamp=datetime.now(UTC))

    def test_value_above_max_raises(self):
        """Test that value above +1.0 raises ValueError."""
        with pytest.raises(ValueError, match="\\[-1, \\+1\\]"):
            SentimentScore(source="test", value=1.1, timestamp=datetime.now(UTC))

    def test_confidence_below_zero_raises(self):
        """Test that negative confidence raises ValueError."""
        with pytest.raises(ValueError, match="\\[0, 1\\]"):
            SentimentScore(
                source="test",
                value=0.0,
                timestamp=datetime.now(UTC),
                confidence=-0.1,
            )

    def test_confidence_above_one_raises(self):
        """Test that confidence > 1.0 raises ValueError."""
        with pytest.raises(ValueError, match="\\[0, 1\\]"):
            SentimentScore(
                source="test",
                value=0.0,
                timestamp=datetime.now(UTC),
                confidence=1.1,
            )

    @pytest.mark.parametrize(
        "value, expected",
        [
            (-1.0, SentimentDirection.EXTREME_FEAR),
            (-0.9, SentimentDirection.EXTREME_FEAR),
            (-0.8, SentimentDirection.EXTREME_FEAR),
            (-0.5, SentimentDirection.FEAR),
            (-0.3, SentimentDirection.FEAR),
            (-0.1, SentimentDirection.NEUTRAL),
            (0.0, SentimentDirection.NEUTRAL),
            (0.3, SentimentDirection.NEUTRAL),
            (0.5, SentimentDirection.GREED),
            (0.8, SentimentDirection.GREED),
            (0.9, SentimentDirection.EXTREME_GREED),
            (1.0, SentimentDirection.EXTREME_GREED),
        ],
    )
    def test_direction_mapping(self, value, expected):
        """Test direction mapping for various values."""
        score = SentimentScore(source="test", value=value, timestamp=datetime.now(UTC))
        assert score.direction == expected


# ---------------------------------------------------------------------------
# AggregatedSentiment
# ---------------------------------------------------------------------------


class TestAggregatedSentiment:
    """Test cases for AggregatedSentiment."""

    def test_valid_aggregation(self):
        """Test creating a valid AggregatedSentiment."""
        scores = [
            SentimentScore(source="a", value=0.5, timestamp=datetime.now(UTC)),
            SentimentScore(source="b", value=-0.3, timestamp=datetime.now(UTC)),
        ]
        agg = AggregatedSentiment(
            scores=scores,
            weighted_value=0.1,
            timestamp=datetime.now(UTC),
            sources_count=2,
        )
        assert agg.sources_count == 2
        assert agg.weighted_value == 0.1
        assert agg.direction == SentimentDirection.NEUTRAL

    def test_weighted_value_out_of_range_raises(self):
        """Test that weighted value outside [-1, +1] raises."""
        scores = [
            SentimentScore(source="a", value=0.5, timestamp=datetime.now(UTC)),
        ]
        with pytest.raises(ValueError, match="\\[-1, \\+1\\]"):
            AggregatedSentiment(
                scores=scores,
                weighted_value=1.5,
                timestamp=datetime.now(UTC),
                sources_count=1,
            )

    @pytest.mark.parametrize(
        "value, expected",
        [
            (-1.0, SentimentDirection.EXTREME_FEAR),
            (0.0, SentimentDirection.NEUTRAL),
            (1.0, SentimentDirection.EXTREME_GREED),
        ],
    )
    def test_direction_mapping(self, value, expected):
        """Test direction mapping on aggregated sentiment."""
        agg = AggregatedSentiment(
            scores=[],
            weighted_value=value,
            timestamp=datetime.now(UTC),
            sources_count=0,
        )
        assert agg.direction == expected


# ---------------------------------------------------------------------------
# SentimentAggregator
# ---------------------------------------------------------------------------


class TestSentimentAggregator:
    """Test cases for SentimentAggregator."""

    @pytest.fixture
    def aggregator(self):
        """Create an empty aggregator."""
        return SentimentAggregator()

    def test_init_empty(self, aggregator):
        """Test creating aggregator with no sources."""
        assert aggregator.list_sources() == []

    def test_init_with_sources(self):
        """Test creating aggregator with initial sources."""
        src1 = StubSource(name="src1", value=0.5)
        src2 = StubSource(name="src2", value=-0.3)
        agg = SentimentAggregator(sources=[src1, src2])
        assert set(agg.list_sources()) == {"src1", "src2"}

    def test_register_source(self, aggregator):
        """Test registering a source."""
        src = StubSource(name="test_src")
        aggregator.register(src)
        assert "test_src" in aggregator.list_sources()

    def test_register_duplicate_raises(self, aggregator):
        """Test that registering duplicate source raises ValueError."""
        src = StubSource(name="dup")
        aggregator.register(src)
        with pytest.raises(ValueError, match="already registered"):
            aggregator.register(StubSource(name="dup"))

    def test_register_invalid_type_raises(self, aggregator):
        """Test that registering non-BaseSentimentSource raises TypeError."""
        with pytest.raises(TypeError, match="BaseSentimentSource"):
            aggregator.register("not_a_source")  # type: ignore[arg-type]

    def test_unregister_source(self, aggregator):
        """Test unregistering a source."""
        src = StubSource(name="to_remove")
        aggregator.register(src)
        assert aggregator.unregister("to_remove") is True
        assert "to_remove" not in aggregator.list_sources()

    def test_unregister_missing_returns_false(self, aggregator):
        """Test unregistering non-existent source returns False."""
        assert aggregator.unregister("ghost") is False

    def test_get_source(self, aggregator):
        """Test getting a registered source."""
        src = StubSource(name="findme")
        aggregator.register(src)
        assert aggregator.get_source("findme") is src

    def test_get_source_missing(self, aggregator):
        """Test getting non-existent source returns None."""
        assert aggregator.get_source("missing") is None

    def test_aggregate_single_source(self, aggregator):
        """Test aggregation with a single source."""
        src = StubSource(name="single", value=0.6)
        aggregator.register(src)
        result = aggregator.aggregate()

        assert result.sources_count == 1
        assert result.weighted_value == pytest.approx(0.6)
        assert len(result.scores) == 1
        assert result.scores[0].source == "single"

    def test_aggregate_multiple_equal_confidence(self, aggregator):
        """Test aggregation with multiple sources at equal confidence."""
        aggregator.register(StubSource(name="a", value=0.5))
        aggregator.register(StubSource(name="b", value=-0.5))
        result = aggregator.aggregate()

        assert result.sources_count == 2
        assert result.weighted_value == pytest.approx(0.0)

    def test_aggregate_weighted_confidence(self, aggregator):
        """Test confidence-weighted aggregation."""
        aggregator.register(StubSource(name="high_conf", value=0.8, confidence=0.9))
        aggregator.register(StubSource(name="low_conf", value=-0.8, confidence=0.1))
        result = aggregator.aggregate()

        # (0.8*0.9 + -0.8*0.1) / (0.9+0.1) = (0.72 - 0.08) / 1.0 = 0.64
        assert result.weighted_value == pytest.approx(0.64)

    def test_aggregate_skips_unavailable(self, aggregator):
        """Test that unavailable sources are skipped."""
        aggregator.register(StubSource(name="available", value=0.5, available=True))
        aggregator.register(StubSource(name="offline", value=-0.5, available=False))
        result = aggregator.aggregate()

        assert result.sources_count == 1
        assert result.weighted_value == pytest.approx(0.5)

    def test_aggregate_skips_failing_sources(self, aggregator):
        """Test that failing sources are skipped gracefully."""
        aggregator.register(StubSource(name="working", value=0.3, available=True))
        aggregator.register(
            StubSource(
                name="failing",
                value=0.0,
                available=True,
                should_fail=True,
            )
        )
        result = aggregator.aggregate()

        assert result.sources_count == 1
        assert result.weighted_value == pytest.approx(0.3)

    def test_aggregate_no_sources_raises(self, aggregator):
        """Test that aggregating with no sources raises ValueError."""
        with pytest.raises(ValueError, match="No sentiment sources"):
            aggregator.aggregate()

    def test_aggregate_all_unavailable_raises(self, aggregator):
        """Test that all unavailable sources raises ValueError."""
        aggregator.register(StubSource(name="off1", available=False))
        aggregator.register(StubSource(name="off2", available=False))
        with pytest.raises(ValueError, match="No sentiment sources"):
            aggregator.aggregate()

    def test_aggregate_single_source_call(self, aggregator):
        """Test fetching from a single named source."""
        src = StubSource(name="target", value=0.7)
        aggregator.register(src)
        score = aggregator.aggregate_single("target")

        assert score.value == pytest.approx(0.7)
        assert score.source == "target"

    def test_aggregate_single_missing_raises(self, aggregator):
        """Test fetching from missing source raises KeyError."""
        with pytest.raises(KeyError, match="not found"):
            aggregator.aggregate_single("ghost")

    def test_aggregate_single_unavailable_raises(self, aggregator):
        """Test fetching from unavailable source raises RuntimeError."""
        aggregator.register(StubSource(name="offline", available=False))
        with pytest.raises(RuntimeError, match="not available"):
            aggregator.aggregate_single("offline")

    def test_zero_confidence_fallback(self, aggregator):
        """Test simple average fallback when all confidences are 0."""
        aggregator.register(StubSource(name="a", value=0.5, confidence=0.0))
        aggregator.register(StubSource(name="b", value=-0.5, confidence=0.0))
        result = aggregator.aggregate()

        assert result.weighted_value == pytest.approx(0.0)

    def test_aggregation_metadata(self, aggregator):
        """Test that aggregation metadata includes expected keys."""
        aggregator.register(StubSource(name="src1", value=0.3))
        aggregator.register(StubSource(name="src2", value=0.7))
        result = aggregator.aggregate()

        assert "source_names" in result.metadata
        assert "avg_confidence" in result.metadata
        assert result.metadata["source_names"] == ["src1", "src2"]


# ---------------------------------------------------------------------------
# BaseSentimentSource
# ---------------------------------------------------------------------------


class TestBaseSentimentSource:
    """Test cases for BaseSentimentSource."""

    def test_name_defaults_to_class_name(self):
        """Test that name defaults to class name."""
        src = StubSource()
        assert src.name == "StubSource"

    def test_custom_name(self):
        """Test custom name assignment."""
        src = StubSource(name="CustomName")
        assert src.name == "CustomName"

    def test_get_metadata(self):
        """Test default get_metadata returns expected keys."""
        src = StubSource()
        meta = src.get_metadata()
        assert "name" in meta
        assert "description" in meta
