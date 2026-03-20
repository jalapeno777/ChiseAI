"""Sentiment aggregator for multi-source sentiment collection and normalization.

Provides a pluggable architecture for collecting sentiment from multiple
sources (Fear & Greed Index, social sentiment, news, etc.) and normalizing
all scores to a consistent -1 (extreme fear) to +1 (extreme greed) range.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import numpy as np


class SentimentDirection(Enum):
    """Direction of market sentiment."""

    EXTREME_FEAR = "extreme_fear"
    FEAR = "fear"
    NEUTRAL = "neutral"
    GREED = "greed"
    EXTREME_GREED = "extreme_greed"


@dataclass
class SentimentScore:
    """Normalized sentiment score from a single source.

    Attributes:
        source: Name of the sentiment source
        value: Normalized score in [-1, +1] range (-1 = extreme fear, +1 = extreme greed)
        timestamp: When the score was computed
        confidence: 0.0 to 1.0 confidence in the score
        raw_value: Original raw value before normalization
        metadata: Additional source-specific data
    """

    source: str
    value: float
    timestamp: datetime
    confidence: float = 1.0
    raw_value: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate sentiment score values."""
        if not -1.0 <= self.value <= 1.0:
            raise ValueError(f"Sentiment value must be in [-1, +1], got {self.value}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be in [0, 1], got {self.confidence}")

    @property
    def direction(self) -> SentimentDirection:
        """Map normalized value to sentiment direction."""
        if self.value <= -0.8:
            return SentimentDirection.EXTREME_FEAR
        elif self.value <= -0.3:
            return SentimentDirection.FEAR
        elif self.value <= 0.3:
            return SentimentDirection.NEUTRAL
        elif self.value <= 0.8:
            return SentimentDirection.GREED
        else:
            return SentimentDirection.EXTREME_GREED


@dataclass
class AggregatedSentiment:
    """Aggregated sentiment from multiple sources.

    Attributes:
        scores: Individual source scores
        weighted_value: Confidence-weighted average score
        timestamp: When aggregation was performed
        sources_count: Number of sources contributing
        metadata: Aggregation metadata
    """

    scores: list[SentimentScore]
    weighted_value: float
    timestamp: datetime
    sources_count: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate aggregated sentiment."""
        if not -1.0 <= self.weighted_value <= 1.0:
            raise ValueError(
                f"Weighted value must be in [-1, +1], got {self.weighted_value}"
            )

    @property
    def direction(self) -> SentimentDirection:
        """Map weighted value to sentiment direction."""
        if self.weighted_value <= -0.8:
            return SentimentDirection.EXTREME_FEAR
        elif self.weighted_value <= -0.3:
            return SentimentDirection.FEAR
        elif self.weighted_value <= 0.3:
            return SentimentDirection.NEUTRAL
        elif self.weighted_value <= 0.8:
            return SentimentDirection.GREED
        else:
            return SentimentDirection.EXTREME_GREED


class BaseSentimentSource(ABC):
    """Abstract base class for sentiment data sources.

    All sentiment sources must implement this interface for
    compatibility with SentimentAggregator.
    """

    def __init__(self, name: str | None = None):
        """Initialize sentiment source.

        Args:
            name: Optional custom name (defaults to class name)
        """
        self._name = name or self.__class__.__name__

    @property
    def name(self) -> str:
        """Get source name."""
        return self._name

    @property
    @abstractmethod
    def description(self) -> str:
        """Get human-readable description of the source."""
        pass

    @abstractmethod
    def fetch(self) -> SentimentScore:
        """Fetch current sentiment from this source.

        Returns:
            Normalized SentimentScore in [-1, +1] range
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this source is currently available.

        Returns:
            True if source can provide data
        """
        pass

    def get_metadata(self) -> dict[str, Any]:
        """Get source metadata for serialization.

        Returns:
            Dictionary with name, description, and source-specific info
        """
        return {
            "name": self.name,
            "description": self.description,
        }


class SentimentAggregator:
    """Aggregates sentiment from multiple sources.

    Collects sentiment scores from registered sources, normalizes
    all values to the [-1, +1] range, and computes a confidence-weighted
    average across all available sources.
    """

    def __init__(self, sources: list[BaseSentimentSource] | None = None):
        """Initialize aggregator with optional sources.

        Args:
            sources: List of sentiment sources to register
        """
        self._sources: dict[str, BaseSentimentSource] = {}
        if sources:
            for source in sources:
                self.register(source)

    def register(self, source: BaseSentimentSource) -> None:
        """Register a sentiment source.

        Args:
            source: Sentiment source to add

        Raises:
            TypeError: If source doesn't inherit from BaseSentimentSource
            ValueError: If source name already registered
        """
        if not isinstance(source, BaseSentimentSource):
            raise TypeError(f"{source} must be an instance of BaseSentimentSource")

        if source.name in self._sources:
            raise ValueError(f"Sentiment source '{source.name}' already registered")

        self._sources[source.name] = source

    def unregister(self, name: str) -> bool:
        """Unregister a sentiment source.

        Args:
            name: Source name to remove

        Returns:
            True if unregistered, False if not found
        """
        if name in self._sources:
            del self._sources[name]
            return True
        return False

    def get_source(self, name: str) -> BaseSentimentSource | None:
        """Get a registered source by name.

        Args:
            name: Source name

        Returns:
            Source instance or None if not found
        """
        return self._sources.get(name)

    def list_sources(self) -> list[str]:
        """List all registered source names.

        Returns:
            List of source names
        """
        return list(self._sources.keys())

    def aggregate(self) -> AggregatedSentiment:
        """Aggregate sentiment from all available sources.

        Fetches current sentiment from each available source and
        computes a confidence-weighted average.

        Returns:
            AggregatedSentiment with weighted average and individual scores

        Raises:
            ValueError: If no sources are available
        """
        scores: list[SentimentScore] = []

        for source in self._sources.values():
            if source.is_available():
                try:
                    score = source.fetch()
                    scores.append(score)
                except Exception:
                    # Skip unavailable or failing sources
                    continue

        if not scores:
            raise ValueError("No sentiment sources available")

        return self._compute_aggregation(scores)

    def aggregate_single(self, source_name: str) -> SentimentScore:
        """Fetch sentiment from a single named source.

        Args:
            source_name: Name of the source to query

        Returns:
            SentimentScore from the specified source

        Raises:
            KeyError: If source not found
            RuntimeError: If source is unavailable
        """
        source = self._sources.get(source_name)
        if source is None:
            raise KeyError(f"Source '{source_name}' not found")

        if not source.is_available():
            raise RuntimeError(f"Source '{source_name}' is not available")

        return source.fetch()

    def _compute_aggregation(self, scores: list[SentimentScore]) -> AggregatedSentiment:
        """Compute weighted aggregation of sentiment scores.

        Uses confidence as weight for averaging.

        Args:
            scores: List of normalized sentiment scores

        Returns:
            AggregatedSentiment with weighted average
        """
        values = np.array([s.value for s in scores])
        confidences = np.array([s.confidence for s in scores])

        # Confidence-weighted average
        total_confidence = np.sum(confidences)
        if total_confidence == 0:
            # Fallback to simple average if all confidences are 0
            weighted_value = float(np.mean(values))
        else:
            weighted_value = float(np.sum(values * confidences) / total_confidence)

        # Clamp to [-1, +1] for safety
        weighted_value = float(np.clip(weighted_value, -1.0, 1.0))

        return AggregatedSentiment(
            scores=scores,
            weighted_value=weighted_value,
            timestamp=datetime.utcnow(),
            sources_count=len(scores),
            metadata={
                "source_names": [s.source for s in scores],
                "avg_confidence": float(np.mean(confidences)),
            },
        )
