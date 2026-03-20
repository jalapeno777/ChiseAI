"""Tests for FearGreedIndex sentiment source."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import httpx
import pytest

from market_analysis.sentiment.aggregator import (
    SentimentDirection,
    SentimentScore,
)
from market_analysis.sentiment.fear_greed_index import FearGreedIndex

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_api_response():
    """Valid CNN Fear & Greed API response."""
    return {
        "fear_and_greed": {
            "score": 65,
            "value": "Greed",
        }
    }


@pytest.fixture
def fear_greed():
    """Create a FearGreedIndex instance with default settings."""
    return FearGreedIndex()


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


class TestNormalization:
    """Test score normalization logic."""

    @pytest.mark.parametrize(
        "raw, expected",
        [
            (0, -1.0),
            (10, -0.8),
            (25, -0.5),
            (50, 0.0),
            (75, 0.5),
            (90, 0.8),
            (100, 1.0),
        ],
    )
    def test_normalize(self, raw, expected):
        """Test normalization from raw [0,100] to [-1,+1]."""
        assert FearGreedIndex.normalize(raw) == pytest.approx(expected)

    @pytest.mark.parametrize(
        "normalized, expected",
        [
            (-1.0, 0.0),
            (-0.5, 25.0),
            (0.0, 50.0),
            (0.5, 75.0),
            (1.0, 100.0),
        ],
    )
    def test_denormalize(self, normalized, expected):
        """Test denormalization from [-1,+1] to raw [0,100]."""
        assert FearGreedIndex.denormalize(normalized) == pytest.approx(expected)

    def test_normalize_denormalize_roundtrip(self):
        """Test that normalize(denormalize(x)) == x."""
        import random

        for _ in range(20):
            raw = random.randint(0, 100)
            normalized = FearGreedIndex.normalize(raw)
            denormalized = FearGreedIndex.denormalize(normalized)
            assert denormalized == pytest.approx(float(raw))


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestFearGreedIndexInit:
    """Test FearGreedIndex initialization."""

    def test_default_init(self, fear_greed):
        """Test default initialization."""
        assert fear_greed.name == "FearGreedIndex"
        assert fear_greed.last_value is None
        assert fear_greed.last_timestamp is None

    def test_custom_name(self):
        """Test custom name."""
        fg = FearGreedIndex(name="CustomFGI")
        assert fg.name == "CustomFGI"

    def test_custom_timeout(self):
        """Test custom timeout."""
        fg = FearGreedIndex(timeout=30.0)
        assert fg._timeout == 30.0

    def test_description(self, fear_greed):
        """Test that description returns a non-empty string."""
        assert isinstance(fear_greed.description, str)
        assert len(fear_greed.description) > 0

    def test_is_available(self, fear_greed):
        """Test that is_available returns True by default."""
        assert fear_greed.is_available() is True

    def test_get_metadata(self, fear_greed):
        """Test metadata includes expected keys."""
        meta = fear_greed.get_metadata()
        assert "name" in meta
        assert "description" in meta


# ---------------------------------------------------------------------------
# fetch_from_data (unit tests without network)
# ---------------------------------------------------------------------------


class TestFetchFromData:
    """Test parsing API response data without network calls."""

    def test_valid_response(self, fear_greed, sample_api_response):
        """Test parsing a valid API response."""
        score = fear_greed.fetch_from_data(sample_api_response)

        assert isinstance(score, SentimentScore)
        assert score.source == "FearGreedIndex"
        assert score.value == pytest.approx(0.3)  # (65-50)/50 = 0.3
        assert score.raw_value == 65.0
        assert score.confidence == 0.8
        assert score.metadata["raw_score"] == 65
        assert score.metadata["label"] == "Greed"
        assert fear_greed.last_value == 65
        assert fear_greed.last_timestamp is not None

    @pytest.mark.parametrize(
        "raw_score, expected_direction",
        [
            (5, SentimentDirection.EXTREME_FEAR),
            (20, SentimentDirection.FEAR),
            (50, SentimentDirection.NEUTRAL),
            (75, SentimentDirection.GREED),
            (95, SentimentDirection.EXTREME_GREED),
        ],
    )
    def test_direction_mapping(self, fear_greed, raw_score, expected_direction):
        """Test that raw scores map to correct sentiment directions."""
        data = {"fear_and_greed": {"score": raw_score, "value": "label"}}
        score = fear_greed.fetch_from_data(data)
        assert score.direction == expected_direction

    def test_extreme_fear_response(self, fear_greed):
        """Test parsing extreme fear (score=0)."""
        data = {"fear_and_greed": {"score": 0, "value": "Extreme Fear"}}
        score = fear_greed.fetch_from_data(data)
        assert score.value == pytest.approx(-1.0)
        assert score.direction == SentimentDirection.EXTREME_FEAR

    def test_extreme_greed_response(self, fear_greed):
        """Test parsing extreme greed (score=100)."""
        data = {"fear_and_greed": {"score": 100, "value": "Extreme Greed"}}
        score = fear_greed.fetch_from_data(data)
        assert score.value == pytest.approx(1.0)
        assert score.direction == SentimentDirection.EXTREME_GREED

    def test_neutral_response(self, fear_greed):
        """Test parsing neutral (score=50)."""
        data = {"fear_and_greed": {"score": 50, "value": "Neutral"}}
        score = fear_greed.fetch_from_data(data)
        assert score.value == pytest.approx(0.0)
        assert score.direction == SentimentDirection.NEUTRAL

    def test_missing_fear_and_greed_key_raises(self, fear_greed):
        """Test that missing fear_and_greed key raises ValueError."""
        with pytest.raises(ValueError, match="fear_and_greed"):
            fear_greed.fetch_from_data({})

    def test_missing_score_raises(self, fear_greed):
        """Test that missing score field raises ValueError."""
        # Use a non-empty dict so fg_data is truthy but still missing 'score'
        with pytest.raises(ValueError, match="score"):
            fear_greed.fetch_from_data({"fear_and_greed": {"value": "label"}})

    def test_non_numeric_score_raises(self, fear_greed):
        """Test that non-numeric score raises ValueError."""
        data = {"fear_and_greed": {"score": "bad", "value": "label"}}
        with pytest.raises(ValueError, match="numeric"):
            fear_greed.fetch_from_data(data)

    def test_score_below_range_raises(self, fear_greed):
        """Test that score below 0 raises ValueError."""
        data = {"fear_and_greed": {"score": -1, "value": "label"}}
        with pytest.raises(ValueError, match="\\[0, 100\\]"):
            fear_greed.fetch_from_data(data)

    def test_score_above_range_raises(self, fear_greed):
        """Test that score above 100 raises ValueError."""
        data = {"fear_and_greed": {"score": 101, "value": "label"}}
        with pytest.raises(ValueError, match="\\[0, 100\\]"):
            fear_greed.fetch_from_data(data)

    def test_float_score_accepted(self, fear_greed):
        """Test that float score values are accepted."""
        data = {"fear_and_greed": {"score": 55.5, "value": "label"}}
        score = fear_greed.fetch_from_data(data)
        # int(55.5) = 55, normalize(55) = (55-50)/50 = 0.1
        assert score.value == pytest.approx(0.1)

    def test_metadata_populated(self, fear_greed, sample_api_response):
        """Test that metadata contains expected fields."""
        score = fear_greed.fetch_from_data(sample_api_response)
        assert "raw_score" in score.metadata
        assert "label" in score.metadata
        assert "api_url" in score.metadata


# ---------------------------------------------------------------------------
# fetch (with mocked HTTP)
# ---------------------------------------------------------------------------


class TestFetch:
    """Test fetch method with mocked HTTP transport."""

    @patch("market_analysis.sentiment.fear_greed_index.httpx")
    def test_fetch_success(self, mock_httpx, fear_greed, sample_api_response):
        """Test successful fetch from API."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_api_response
        mock_response.raise_for_status = MagicMock()
        mock_httpx.get.return_value = mock_response

        score = fear_greed.fetch()
        assert score.value == pytest.approx(0.3)
        mock_httpx.get.assert_called_once()

    def test_fetch_http_error(self, fear_greed):
        """Test that HTTP errors raise RuntimeError."""
        with patch.object(
            httpx, "get", side_effect=httpx.HTTPError("Connection refused")
        ):
            with pytest.raises(RuntimeError, match="Failed to fetch"):
                fear_greed.fetch()

    @patch("market_analysis.sentiment.fear_greed_index.httpx")
    def test_fetch_invalid_json(self, mock_httpx, fear_greed):
        """Test that invalid JSON raises ValueError."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Not JSON")
        mock_response.raise_for_status = MagicMock()
        mock_httpx.get.return_value = mock_response

        with pytest.raises(ValueError, match="Invalid JSON"):
            fear_greed.fetch()

    @patch("market_analysis.sentiment.fear_greed_index.httpx")
    def test_fetch_timeout(self, mock_httpx, fear_greed):
        """Test that timeout is passed to httpx."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "fear_and_greed": {"score": 50, "value": "Neutral"}
        }
        mock_response.raise_for_status = MagicMock()
        mock_httpx.get.return_value = mock_response

        fg = FearGreedIndex(timeout=5.0)
        fg.fetch()

        _, kwargs = mock_httpx.get.call_args
        assert kwargs["timeout"] == 5.0

    @patch("market_analysis.sentiment.fear_greed_index.httpx")
    def test_fetch_updates_last_value(
        self, mock_httpx, fear_greed, sample_api_response
    ):
        """Test that fetch updates last_value and last_timestamp."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_api_response
        mock_response.raise_for_status = MagicMock()
        mock_httpx.get.return_value = mock_response

        assert fear_greed.last_value is None
        fear_greed.fetch()
        assert fear_greed.last_value == 65
        assert fear_greed.last_timestamp is not None
        assert isinstance(fear_greed.last_timestamp, datetime)
