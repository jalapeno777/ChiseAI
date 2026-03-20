"""Fear and Greed Index integration.

Fetches the CNN Fear & Greed Index and normalizes it to the
standardized [-1, +1] sentiment range used by SentimentAggregator.

The CNN Fear & Greed Index ranges from 0 (Extreme Fear) to 100 (Extreme Greed).
"""

import logging
from datetime import datetime
from typing import Any

import httpx

from market_analysis.sentiment.aggregator import BaseSentimentSource, SentimentScore

logger = logging.getLogger(__name__)

# CNN Fear & Greed Index API endpoint
DEFAULT_API_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"


class FearGreedIndex(BaseSentimentSource):
    """CNN Fear and Greed Index sentiment source.

    Fetches the current Fear & Greed Index value from the CNN API
    and normalizes it to the [-1, +1] range.

    Normalization mapping:
        - 0 (Extreme Fear)   -> -1.0
        - 50 (Neutral)       ->  0.0
        - 100 (Extreme Greed) -> +1.0
    """

    def __init__(
        self,
        api_url: str = DEFAULT_API_URL,
        timeout: float = 10.0,
        name: str | None = None,
    ):
        """Initialize Fear & Greed Index client.

        Args:
            api_url: URL for the Fear & Greed Index API
            timeout: HTTP request timeout in seconds
            name: Optional custom name
        """
        super().__init__(name=name or "FearGreedIndex")
        self._api_url = api_url
        self._timeout = timeout
        self._last_value: int | None = None
        self._last_timestamp: datetime | None = None

    @property
    def description(self) -> str:
        """Get description of the Fear & Greed Index source."""
        return (
            "CNN Fear and Greed Index - measures market sentiment "
            "based on volatility, momentum, volume, and social data"
        )

    @property
    def last_value(self) -> int | None:
        """Get the last fetched raw index value."""
        return self._last_value

    @property
    def last_timestamp(self) -> datetime | None:
        """Get the timestamp of the last fetch."""
        return self._last_timestamp

    def is_available(self) -> bool:
        """Check if the API is available.

        Returns:
            True (assumes available; actual check on fetch)
        """
        return True

    def fetch(self) -> SentimentScore:
        """Fetch current Fear & Greed Index and normalize.

        Returns:
            SentimentScore with normalized value in [-1, +1]

        Raises:
            RuntimeError: If API request fails
            ValueError: If response data is invalid
        """
        try:
            response = httpx.get(self._api_url, timeout=self._timeout)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise RuntimeError(f"Failed to fetch Fear & Greed Index: {e}") from e

        try:
            data = response.json()
        except ValueError as e:
            raise ValueError(f"Invalid JSON response from Fear & Greed API: {e}") from e

        return self._parse_response(data)

    def fetch_from_data(self, data: dict[str, Any]) -> SentimentScore:
        """Create SentimentScore from raw API response data.

        Useful for testing or when data is cached.

        Args:
            data: Raw API response dictionary

        Returns:
            Normalized SentimentScore
        """
        return self._parse_response(data)

    @staticmethod
    def normalize(raw_value: int | float) -> float:
        """Normalize raw Fear & Greed Index to [-1, +1].

        Args:
            raw_value: Raw index value in [0, 100]

        Returns:
            Normalized value in [-1, +1]
        """
        return (float(raw_value) - 50.0) / 50.0

    @staticmethod
    def denormalize(normalized_value: float) -> float:
        """Convert normalized value back to raw index.

        Args:
            normalized_value: Normalized value in [-1, +1]

        Returns:
            Raw index value in [0, 100]
        """
        return (normalized_value * 50.0) + 50.0

    def _parse_response(self, data: dict[str, Any]) -> SentimentScore:
        """Parse API response into SentimentScore.

        Args:
            data: Raw API response

        Returns:
            Normalized SentimentScore

        Raises:
            ValueError: If required fields are missing
        """
        # Extract the current fear_greed value from the response
        # The CNN API returns a 'fear_and_greed' object with 'score' field
        fg_data = data.get("fear_and_greed", {})
        if not fg_data:
            raise ValueError("Missing 'fear_and_greed' in response data")

        raw_value = fg_data.get("score")
        if raw_value is None:
            raise ValueError("Missing 'score' in fear_and_greed data")

        if not isinstance(raw_value, (int, float)):
            raise ValueError(f"Expected numeric score, got {type(raw_value).__name__}")

        # Validate range
        raw_int = int(raw_value)
        if not 0 <= raw_int <= 100:
            raise ValueError(f"Fear & Greed score must be in [0, 100], got {raw_int}")

        normalized = self.normalize(raw_int)

        self._last_value = raw_int
        self._last_timestamp = datetime.utcnow()

        # Extract label if available
        label = fg_data.get("value", "")

        return SentimentScore(
            source=self.name,
            value=normalized,
            timestamp=self._last_timestamp,
            confidence=0.8,  # Fixed confidence for external API
            raw_value=float(raw_int),
            metadata={
                "raw_score": raw_int,
                "label": label,
                "api_url": self._api_url,
            },
        )
