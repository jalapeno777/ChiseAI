"""Sentiment analysis package for multi-source sentiment collection.

Provides pluggable sentiment sources with normalization to a
standardized [-1, +1] range (extreme fear to extreme greed).
"""

from market_analysis.sentiment.aggregator import (
    AggregatedSentiment,
    BaseSentimentSource,
    SentimentAggregator,
    SentimentDirection,
    SentimentScore,
)
from market_analysis.sentiment.fear_greed_index import FearGreedIndex

__all__ = [
    # Core types
    "SentimentScore",
    "SentimentDirection",
    "AggregatedSentiment",
    # Base class for custom sources
    "BaseSentimentSource",
    # Aggregator
    "SentimentAggregator",
    # Built-in sources
    "FearGreedIndex",
]
