"""Correlation analysis engine for portfolio risk management.

Provides correlation matrix calculation, rolling window correlations,
and diversification scoring for portfolio positions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, cast

import numpy as np

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class CorrelationMethod(Enum):
    """Correlation calculation method enumeration."""

    PEARSON = "pearson"
    SPEARMAN = "spearman"

    def __str__(self) -> str:
        """Return string representation."""
        return self.value


@dataclass
class CorrelationResult:
    """Result of correlation analysis.

    Attributes:
        tokens: List of token symbols in the correlation matrix
        correlation_matrix: 2D numpy array of correlation values (-1 to 1)
        method: Correlation method used (pearson or spearman)
        window_size: Window size for rolling calculations (0 for full series)
        timestamp: Analysis timestamp (Unix ms)
        diversification_score: Portfolio diversification score (0 to 100)
    """

    tokens: list[str]
    correlation_matrix: np.ndarray
    method: CorrelationMethod
    window_size: int
    timestamp: int
    diversification_score: float

    def to_dict(self) -> dict:
        """Convert result to dictionary for serialization."""
        return {
            "tokens": self.tokens,
            "correlation_matrix": self.correlation_matrix.tolist(),
            "method": self.method.value,
            "window_size": self.window_size,
            "timestamp": self.timestamp,
            "diversification_score": round(self.diversification_score, 4),
        }


@dataclass
class RollingCorrelationResult:
    """Result of rolling window correlation analysis.

    Attributes:
        tokens: List of token symbols
        rolling_correlations: Dictionary of token pairs to correlation time series
        window_size: Rolling window size
        timestamps: List of timestamps for each correlation point
        method: Correlation method used
    """

    tokens: list[str]
    rolling_correlations: dict[tuple[str, str], list[float]]
    window_size: int
    timestamps: list[int]
    method: CorrelationMethod

    def to_dict(self) -> dict:
        """Convert result to dictionary for serialization."""
        # Convert tuple keys to string keys for JSON serialization
        corr_dict = {f"{k[0]}_{k[1]}": v for k, v in self.rolling_correlations.items()}
        return {
            "tokens": self.tokens,
            "rolling_correlations": corr_dict,
            "window_size": self.window_size,
            "timestamps": self.timestamps,
            "method": self.method.value,
        }


class CorrelationEngine:
    """Engine for calculating correlations between portfolio positions.

    The CorrelationEngine provides:
    - Correlation matrix calculation across all portfolio positions
    - Time-series correlations using Pearson or Spearman methods
    - Rolling window correlations for trend analysis
    - Diversification scoring based on correlation matrix

    Attributes:
        method: Default correlation method (pearson or spearman)
        min_data_points: Minimum data points required for calculation
    """

    def __init__(
        self,
        method: CorrelationMethod = CorrelationMethod.PEARSON,
        min_data_points: int = 10,
    ):
        """Initialize correlation engine.

        Args:
            method: Default correlation method
            min_data_points: Minimum data points required for calculation
        """
        self.method = method
        self.min_data_points = min_data_points

    def _get_current_time_ms(self) -> int:
        """Get current time in milliseconds."""
        import time

        return int(time.time() * 1000)

    def calculate_correlation_matrix(
        self,
        price_data: dict[str, np.ndarray],
        method: CorrelationMethod | None = None,
    ) -> CorrelationResult:
        """Calculate correlation matrix across all tokens.

        Args:
            price_data: Dictionary mapping token symbols to price arrays
            method: Correlation method (defaults to engine default)

        Returns:
            CorrelationResult with correlation matrix and metadata

        Raises:
            ValueError: If insufficient data points or tokens
        """
        method = method or self.method
        tokens = list(price_data.keys())

        if len(tokens) < 2:
            logger.warning("Need at least 2 tokens for correlation calculation")
            # Return identity matrix for single token
            return CorrelationResult(
                tokens=tokens,
                correlation_matrix=np.array([[1.0]]),
                method=method,
                window_size=0,
                timestamp=self._get_current_time_ms(),
                diversification_score=0.0,
            )

        # Validate data and compute returns
        returns_data = {}
        for token, prices in price_data.items():
            if len(prices) < self.min_data_points:
                logger.warning(
                    f"Insufficient data points for {token}: {len(prices)} < "
                    f"{self.min_data_points}"
                )
                continue

            # Calculate log returns
            returns = self._calculate_returns(prices)
            if len(returns) > 0:
                returns_data[token] = returns

        if len(returns_data) < 2:
            logger.warning("Need at least 2 tokens with valid returns")
            # Return identity matrix
            n = len(tokens)
            return CorrelationResult(
                tokens=tokens,
                correlation_matrix=np.eye(n),
                method=method,
                window_size=0,
                timestamp=self._get_current_time_ms(),
                diversification_score=0.0,
            )

        # Build returns matrix (tokens x time periods)
        valid_tokens = list(returns_data.keys())
        min_length = min(len(r) for r in returns_data.values())

        returns_matrix = np.zeros((len(valid_tokens), min_length))
        for i, token in enumerate(valid_tokens):
            returns_matrix[i] = returns_data[token][:min_length]

        # Calculate correlation matrix
        if method == CorrelationMethod.PEARSON:
            corr_matrix = np.corrcoef(returns_matrix)
        else:  # SPEARMAN
            from scipy import stats

            corr_matrix = np.zeros((len(valid_tokens), len(valid_tokens)))
            for i in range(len(valid_tokens)):
                for j in range(len(valid_tokens)):
                    if i == j:
                        corr_matrix[i, j] = 1.0
                    else:
                        corr, _ = stats.spearmanr(returns_matrix[i], returns_matrix[j])
                        corr_matrix[i, j] = corr if not np.isnan(corr) else 0.0

        # Ensure correlation matrix is valid (-1 to 1 range)
        corr_matrix = np.clip(corr_matrix, -1.0, 1.0)

        # Calculate diversification score
        div_score = self._calculate_diversification_score(corr_matrix, valid_tokens)

        return CorrelationResult(
            tokens=valid_tokens,
            correlation_matrix=corr_matrix,
            method=method,
            window_size=0,
            timestamp=self._get_current_time_ms(),
            diversification_score=div_score,
        )

    def calculate_rolling_correlations(
        self,
        price_data: dict[str, np.ndarray],
        window_size: int = 30,
        method: CorrelationMethod | None = None,
    ) -> RollingCorrelationResult:
        """Calculate rolling window correlations for trend analysis.

        Args:
            price_data: Dictionary mapping token symbols to price arrays
            window_size: Rolling window size in periods
            method: Correlation method (defaults to engine default)

        Returns:
            RollingCorrelationResult with time series of correlations

        Raises:
            ValueError: If insufficient data for window size
        """
        method = method or self.method
        tokens = list(price_data.keys())

        if len(tokens) < 2:
            logger.warning("Need at least 2 tokens for rolling correlation")
            return RollingCorrelationResult(
                tokens=tokens,
                rolling_correlations={},
                window_size=window_size,
                timestamps=[],
                method=method,
            )

        if window_size < self.min_data_points:
            raise ValueError(
                f"Window size {window_size} must be >= "
                f"min_data_points {self.min_data_points}"
            )

        # Calculate returns for all tokens
        returns_data = {}
        for token, prices in price_data.items():
            if len(prices) < window_size + 1:
                logger.warning(
                    f"Insufficient data for {token}: {len(prices)} < {window_size + 1}"
                )
                continue
            returns = self._calculate_returns(prices)
            if len(returns) > 0:
                returns_data[token] = returns

        if len(returns_data) < 2:
            logger.warning("Need at least 2 tokens with valid returns")
            return RollingCorrelationResult(
                tokens=tokens,
                rolling_correlations={},
                window_size=window_size,
                timestamps=[],
                method=method,
            )

        valid_tokens = list(returns_data.keys())
        min_length = min(len(r) for r in returns_data.values())

        if min_length < window_size:
            raise ValueError(
                f"Insufficient data points ({min_length}) for window size "
                f"({window_size})"
            )

        # Build returns matrix
        returns_matrix = np.zeros((len(valid_tokens), min_length))
        for i, token in enumerate(valid_tokens):
            returns_matrix[i] = returns_data[token][:min_length]

        # Calculate rolling correlations
        rolling_corrs: dict[tuple[str, str], list[float]] = {}
        timestamps: list[int] = []

        # Generate timestamps (using index as proxy)
        base_time = self._get_current_time_ms()
        timestamps = [
            base_time - (min_length - i) * 86400000
            for i in range(window_size, min_length)
        ]

        # Calculate correlations for each window
        for i in range(len(valid_tokens)):
            for j in range(i + 1, len(valid_tokens)):
                token_pair = (valid_tokens[i], valid_tokens[j])
                rolling_corrs[token_pair] = []

                for end_idx in range(window_size, min_length):
                    window_i = returns_matrix[i, end_idx - window_size : end_idx]
                    window_j = returns_matrix[j, end_idx - window_size : end_idx]

                    if method == CorrelationMethod.PEARSON:
                        corr = np.corrcoef(window_i, window_j)[0, 1]
                    else:  # SPEARMAN
                        from scipy import stats

                        corr, _ = stats.spearmanr(window_i, window_j)

                    # Handle NaN values
                    if np.isnan(corr):
                        corr = 0.0

                    rolling_corrs[token_pair].append(float(np.clip(corr, -1.0, 1.0)))

        return RollingCorrelationResult(
            tokens=valid_tokens,
            rolling_correlations=rolling_corrs,
            window_size=window_size,
            timestamps=timestamps,
            method=method,
        )

    def _calculate_returns(self, prices: np.ndarray) -> np.ndarray:
        """Calculate log returns from price series.

        Args:
            prices: Array of price values

        Returns:
            Array of log returns
        """
        if len(prices) < 2:
            return np.array([])

        # Use log returns for better statistical properties
        log_prices = np.log(prices)
        returns = np.diff(log_prices)
        return cast(np.ndarray, returns)

    def _calculate_diversification_score(
        self, correlation_matrix: np.ndarray, tokens: list[str]
    ) -> float:
        """Calculate portfolio diversification score.

        The diversification score ranges from 0 (no diversification,
        all assets perfectly correlated) to 100 (perfect diversification,
        all assets uncorrelated or negatively correlated).

        Args:
            correlation_matrix: Correlation matrix between tokens
            tokens: List of token symbols

        Returns:
            Diversification score from 0 to 100
        """
        n = len(tokens)
        if n < 2:
            return 0.0

        # Extract upper triangle (excluding diagonal)
        upper_tri_indices = np.triu_indices(n, k=1)
        correlations = correlation_matrix[upper_tri_indices]

        if len(correlations) == 0:
            return 0.0

        # Calculate average absolute correlation
        avg_abs_corr = np.mean(np.abs(correlations))

        # Diversification score is inverse of average correlation
        # Perfect diversification = 0 correlation average -> score 100
        # No diversification = 1 correlation average -> score 0
        score = (1.0 - avg_abs_corr) * 100.0

        return float(np.clip(score, 0.0, 100.0))

    def get_correlation_between_tokens(
        self, correlation_result: CorrelationResult, token1: str, token2: str
    ) -> float | None:
        """Get correlation value between two specific tokens.

        Args:
            correlation_result: CorrelationResult containing the matrix
            token1: First token symbol
            token2: Second token symbol

        Returns:
            Correlation value between -1 and 1, or None if tokens not found
        """
        if (
            token1 not in correlation_result.tokens
            or token2 not in correlation_result.tokens
        ):
            return None

        idx1 = correlation_result.tokens.index(token1)
        idx2 = correlation_result.tokens.index(token2)

        return float(correlation_result.correlation_matrix[idx1, idx2])

    def get_high_correlation_pairs(
        self,
        correlation_result: CorrelationResult,
        threshold: float = 0.7,
    ) -> list[dict]:
        """Get pairs of tokens with correlation above threshold.

        Args:
            correlation_result: CorrelationResult containing the matrix
            threshold: Correlation threshold (absolute value)

        Returns:
            List of dictionaries with token pairs and correlation values
        """
        high_corr_pairs = []
        n = len(correlation_result.tokens)

        for i in range(n):
            for j in range(i + 1, n):
                corr = correlation_result.correlation_matrix[i, j]
                if abs(corr) >= threshold:
                    high_corr_pairs.append(
                        {
                            "token1": correlation_result.tokens[i],
                            "token2": correlation_result.tokens[j],
                            "correlation": round(float(corr), 4),
                            "abs_correlation": round(float(abs(corr)), 4),
                        }
                    )

        # Sort by absolute correlation descending
        high_corr_pairs.sort(key=lambda x: float(x["abs_correlation"]), reverse=True)  # type: ignore[arg-type]

        return high_corr_pairs

    def get_diversification_recommendations(
        self, correlation_result: CorrelationResult
    ) -> list[dict]:
        """Get diversification recommendations based on correlation analysis.

        Args:
            correlation_result: CorrelationResult containing the matrix

        Returns:
            List of recommendation dictionaries
        """
        recommendations = []

        # Get high correlation pairs
        high_corr = self.get_high_correlation_pairs(correlation_result, threshold=0.8)

        if high_corr:
            for pair in high_corr[:5]:  # Top 5 highest correlations
                recommendations.append(
                    {
                        "type": "reduce_concentration",
                        "severity": (
                            "high" if pair["abs_correlation"] > 0.9 else "medium"
                        ),
                        "message": (
                            f"{pair['token1']} and {pair['token2']} are highly "
                            f"correlated ({pair['correlation']:.2f}). Consider "
                            f"reducing position sizes or removing one."
                        ),
                        "tokens": [pair["token1"], pair["token2"]],
                        "correlation": pair["correlation"],
                    }
                )

        # Check overall diversification score
        if correlation_result.diversification_score < 30:
            recommendations.append(
                {
                    "type": "improve_diversification",
                    "severity": "high",
                    "message": (
                        f"Portfolio diversification score is low "
                        f"({correlation_result.diversification_score:.1f}/100). "
                        f"Consider adding uncorrelated assets."
                    ),
                    "score": correlation_result.diversification_score,
                }
            )
        elif correlation_result.diversification_score < 60:
            recommendations.append(
                {
                    "type": "improve_diversification",
                    "severity": "medium",
                    "message": (
                        f"Portfolio diversification score is moderate "
                        f"({correlation_result.diversification_score:.1f}/100). "
                        f"Consider reviewing position correlations."
                    ),
                    "score": correlation_result.diversification_score,
                }
            )

        return recommendations
