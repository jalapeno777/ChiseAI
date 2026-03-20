"""Funding rate analyzer for perpetual futures markets.

Fetches funding rates from Bybit API, calculates funding rate trends
over configurable windows (8h/24h/7d), and detects extreme funding
conditions using percentile-based thresholds. Integrates with
ConfluenceScorer for signal adjustment.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import httpx

from market_analysis.indicators.base import (
    BaseIndicator,
    Signal,
    SignalDirection,
)

logger = logging.getLogger(__name__)

# Bybit API endpoints
BYBIT_V5_PUBLIC = "https://api.bybit.com"
FUNDING_RATE_HISTORY_PATH = "/v5/market/funding/history"


class FundingDirection(Enum):
    """Direction implied by funding rate."""

    POSITIVE = "positive"  # Longs pay shorts (bullish sentiment)
    NEGATIVE = "negative"  # Shorts pay longs (bearish sentiment)
    NEUTRAL = "neutral"  # Near-zero funding


@dataclass
class FundingRatePoint:
    """Single funding rate data point.

    Attributes:
        symbol: Trading pair symbol (e.g. 'BTCUSDT')
        funding_rate: Funding rate as decimal (e.g. 0.0001 = 0.01%)
        timestamp: Unix timestamp in milliseconds
        datetime_utc: UTC datetime of the funding rate
    """

    symbol: str
    funding_rate: float
    timestamp: int

    @property
    def datetime_utc(self) -> datetime:
        """Return timestamp as UTC datetime."""
        return datetime.fromtimestamp(self.timestamp / 1000, tz=UTC)

    @property
    def funding_rate_pct(self) -> float:
        """Return funding rate as percentage."""
        return self.funding_rate * 100

    @property
    def annualized_rate_pct(self) -> float:
        """Return annualized funding rate as percentage.

        Bybit funding occurs every 8 hours (3 times/day).
        """
        return self.funding_rate * 100 * 3 * 365


@dataclass
class FundingTrend:
    """Funding rate trend over a specific window.

    Attributes:
        window_label: Human-readable window label (e.g. '8h', '24h', '7d')
        window_hours: Window size in hours
        mean: Mean funding rate over the window
        median: Median funding rate over the window
        std: Standard deviation of funding rates
        min: Minimum funding rate in window
        max: Maximum funding rate in window
        trend_slope: Linear regression slope (rate per hour)
        current: Most recent funding rate
        sample_count: Number of data points in window
    """

    window_label: str
    window_hours: int
    mean: float
    median: float
    std: float
    min: float
    max: float
    trend_slope: float
    current: float
    sample_count: int


@dataclass
class ExtremeFundingDetection:
    """Result of extreme funding detection.

    Attributes:
        is_extreme: Whether current funding is extreme
        extreme_type: 'high', 'low', or 'none'
        percentile_rank: Percentile rank of current funding (0-100)
        high_threshold: Threshold for extremely high funding
        low_threshold: Threshold for extremely low funding
        severity: Severity score (0.0-1.0, higher = more extreme)
        message: Human-readable description
    """

    is_extreme: bool
    extreme_type: str
    percentile_rank: float
    high_threshold: float
    low_threshold: float
    severity: float
    message: str


@dataclass
class FundingRateResult:
    """Complete funding rate analysis result.

    Attributes:
        symbol: Analyzed symbol
        current_rate: Current funding rate
        trends: Trend data for each window
        extreme_detection: Extreme funding detection result
        signal_adjustment: Recommended signal confidence adjustment
        metadata: Additional analysis metadata
    """

    symbol: str
    current_rate: float
    trends: dict[str, FundingTrend]
    extreme_detection: ExtremeFundingDetection
    signal_adjustment: float
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def funding_direction(self) -> FundingDirection:
        """Determine funding direction from current rate."""
        if self.current_rate > 0.0001:
            return FundingDirection.POSITIVE
        elif self.current_rate < -0.0001:
            return FundingDirection.NEGATIVE
        return FundingDirection.NEUTRAL

    def to_confluence_factor(self) -> dict[str, Any]:
        """Convert result to a confluence factor dict for ConfluenceScorer.

        Returns:
            Dictionary suitable for inclusion in contributing_factors.
        """
        return {
            "type": f"funding_rate_{self.symbol}",
            "indicator": "funding_rate",
            "timeframe": "8h",  # Funding is an 8h cycle
            "direction": self.funding_direction.value,
            "strength": self.extreme_detection.severity,
            "confidence": max(0.0, 1.0 - self.signal_adjustment),
            "weight": 1.0,
            "weighted_score": max(0.0, 1.0 - self.signal_adjustment),
            "raw_value": self.current_rate,
            "funding_rate_pct": self.current_rate * 100,
            "is_extreme": self.extreme_detection.is_extreme,
            "extreme_type": self.extreme_detection.extreme_type,
        }


class FundingRateAnalyzer(BaseIndicator[FundingRateResult]):
    """Analyzer for perpetual futures funding rates.

    Fetches funding rates from Bybit API, computes trends over
    configurable windows, and detects extreme funding conditions
    using percentile-based thresholds.

    Integrates with ConfluenceScorer by providing signal adjustment
    factors based on funding rate extremes.

    Example:
        analyzer = FundingRateAnalyzer(symbol="BTCUSDT")
        result = analyzer.analyze()
        factor = result.to_confluence_factor()
    """

    # Default trend windows in hours
    DEFAULT_WINDOWS = {
        "8h": 8,
        "24h": 24,
        "7d": 168,
    }

    # Default extreme thresholds (percentiles)
    DEFAULT_HIGH_PERCENTILE = 95.0
    DEFAULT_LOW_PERCENTILE = 5.0

    # Signal adjustment parameters
    EXTREME_ADJUSTMENT = 0.25  # Reduce confidence by 25% when extreme
    MODERATE_ADJUSTMENT = 0.10  # Reduce confidence by 10% when moderate

    def __init__(
        self,
        symbol: str = "BTCUSDT",
        windows: dict[str, int] | None = None,
        high_percentile: float = DEFAULT_HIGH_PERCENTILE,
        low_percentile: float = DEFAULT_LOW_PERCENTILE,
        http_client: httpx.AsyncClient | httpx.Client | None = None,
        api_base_url: str = BYBIT_V5_PUBLIC,
    ):
        """Initialize FundingRateAnalyzer.

        Args:
            symbol: Trading pair symbol (e.g. 'BTCUSDT')
            windows: Dict of window_label -> hours (default: 8h, 24h, 7d)
            high_percentile: Percentile threshold for high extreme (0-100)
            low_percentile: Percentile threshold for low extreme (0-100)
            http_client: Optional httpx client for testing/injection
            api_base_url: Bybit API base URL
        """
        super().__init__(name=f"FundingRateAnalyzer_{symbol}")
        self.symbol = symbol
        self.windows = windows or dict(self.DEFAULT_WINDOWS)
        self.high_percentile = high_percentile
        self.low_percentile = low_percentile
        self._http_client = http_client
        self.api_base_url = api_base_url

        # Cache for fetched data
        self._rate_cache: list[FundingRatePoint] = []

    @property
    def description(self) -> str:
        """Get human-readable description."""
        return (
            f"Analyzes funding rates for {self.symbol} from Bybit API, "
            f"computes trends over {list(self.windows.keys())} windows, "
            f"and detects extreme funding conditions."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        """Get current parameter configuration."""
        return {
            "symbol": self.symbol,
            "windows": self.windows,
            "high_percentile": self.high_percentile,
            "low_percentile": self.low_percentile,
            "api_base_url": self.api_base_url,
        }

    def compute(self, data: list) -> FundingRateResult:
        """Compute funding rate analysis.

        Args:
            data: List of FundingRatePoint objects, or empty list.
                  If empty or not FundingRatePoint, data is fetched from API.

        Returns:
            FundingRateResult with complete analysis
        """
        # If data is a list of FundingRatePoint, use it
        if data and all(isinstance(item, FundingRatePoint) for item in data):
            return self.analyze(funding_rates=data)
        # Otherwise fetch from API
        return self.analyze()

    def validate(self, data: list) -> bool:
        """Validate that analysis can be performed.

        Args:
            data: Input data (not used for funding rate analysis)

        Returns:
            True if symbol is set and API is reachable
        """
        return bool(self.symbol) and len(self.symbol) > 0

    def get_metadata(self) -> dict[str, Any]:
        """Get indicator metadata for serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "type": "fundamental",
        }

    def analyze(
        self,
        funding_rates: list[FundingRatePoint] | None = None,
    ) -> FundingRateResult:
        """Run full funding rate analysis.

        Args:
            funding_rates: Optional pre-fetched funding rates.
                If None, rates are fetched from Bybit API.

        Returns:
            FundingRateResult with trends, extreme detection, and
            signal adjustment recommendations.
        """
        start_time = time.perf_counter()

        # Fetch or use provided data
        if funding_rates is None:
            funding_rates = self.fetch_funding_rates()

        if not funding_rates:
            logger.warning("No funding rate data available for %s", self.symbol)
            return self._empty_result()

        # Sort by timestamp descending (newest first)
        sorted_rates = sorted(funding_rates, key=lambda r: r.timestamp, reverse=True)
        self._rate_cache = sorted_rates

        current_rate = sorted_rates[0].funding_rate

        # Calculate trends for each window
        trends = {}
        for label, hours in self.windows.items():
            trends[label] = self._calculate_trend(sorted_rates, label, hours)

        # Detect extreme funding
        extreme_detection = self._detect_extreme(sorted_rates, current_rate)

        # Calculate signal adjustment
        signal_adjustment = self._calculate_signal_adjustment(extreme_detection)

        calc_time_ms = (time.perf_counter() - start_time) * 1000

        return FundingRateResult(
            symbol=self.symbol,
            current_rate=current_rate,
            trends=trends,
            extreme_detection=extreme_detection,
            signal_adjustment=signal_adjustment,
            metadata={
                "data_points": len(sorted_rates),
                "calculation_time_ms": round(calc_time_ms, 3),
                "oldest_timestamp": (
                    sorted_rates[-1].timestamp if sorted_rates else None
                ),
                "newest_timestamp": sorted_rates[0].timestamp if sorted_rates else None,
            },
        )

    def fetch_funding_rates(self, limit: int = 200) -> list[FundingRatePoint]:
        """Fetch funding rate history from Bybit API.

        Args:
            limit: Maximum number of records to fetch (default 200, max 200)

        Returns:
            List of FundingRatePoint sorted newest-first
        """
        url = f"{self.api_base_url}{FUNDING_RATE_HISTORY_PATH}"
        params: dict[str, str | int] = {
            "category": "linear",
            "symbol": self.symbol,
            "limit": min(limit, 200),
        }

        try:
            if isinstance(self._http_client, httpx.AsyncClient):
                # Caller passed an async client but we're in sync context;
                # this is a programming error for the sync path.
                raise TypeError("Use fetch_funding_rates_async() with an AsyncClient")

            client = self._http_client or httpx.Client(timeout=10.0)
            should_close = self._http_client is None

            response = client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            if should_close:
                client.close()

            return self._parse_bybit_response(data)

        except httpx.HTTPStatusError as e:
            logger.error(
                "HTTP error fetching funding rates for %s: %s",
                self.symbol,
                e.response.status_code,
            )
            raise
        except httpx.RequestError as e:
            logger.error(
                "Request error fetching funding rates for %s: %s",
                self.symbol,
                str(e),
            )
            raise

    async def fetch_funding_rates_async(
        self, limit: int = 200
    ) -> list[FundingRatePoint]:
        """Fetch funding rate history from Bybit API (async).

        Args:
            limit: Maximum number of records to fetch

        Returns:
            List of FundingRatePoint sorted newest-first
        """
        url = f"{self.api_base_url}{FUNDING_RATE_HISTORY_PATH}"
        params: dict[str, str | int] = {
            "category": "linear",
            "symbol": self.symbol,
            "limit": min(limit, 200),
        }

        logger.debug("Async fetching funding rates from %s for %s", url, self.symbol)

        if isinstance(self._http_client, httpx.Client):
            # Sync client passed to async method - create a new async one
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                return self._parse_bybit_response(data)

        client = self._http_client or httpx.AsyncClient(timeout=10.0)
        should_close = self._http_client is None

        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            return self._parse_bybit_response(data)
        finally:
            if should_close:
                await client.aclose()

    def _parse_bybit_response(self, data: dict[str, Any]) -> list[FundingRatePoint]:
        """Parse Bybit API response into FundingRatePoint list.

        Args:
            data: Raw JSON response from Bybit API

        Returns:
            List of FundingRatePoint
        """
        if data.get("retCode") != 0:
            error_msg = data.get("retMsg", "Unknown error")
            raise ValueError(
                f"Bybit API error: {error_msg} (retCode={data.get('retCode')})"
            )

        result_list = data.get("result", {}).get("list", [])
        if not result_list:
            return []

        points = []
        for item in result_list:
            points.append(
                FundingRatePoint(
                    symbol=item.get("symbol", self.symbol),
                    funding_rate=float(item.get("fundingRate", "0")),
                    timestamp=int(item.get("fundingRateTimestamp", "0")),
                )
            )

        # Sort newest-first
        return sorted(points, key=lambda p: p.timestamp, reverse=True)

    def _calculate_trend(
        self,
        sorted_rates: list[FundingRatePoint],
        label: str,
        window_hours: int,
    ) -> FundingTrend:
        """Calculate funding rate trend for a specific window.

        Args:
            sorted_rates: Funding rates sorted newest-first
            label: Window label (e.g. '8h', '24h', '7d')
            window_hours: Window size in hours

        Returns:
            FundingTrend with statistics
        """
        now_ms = sorted_rates[0].timestamp
        cutoff_ms = now_ms - (window_hours * 3600 * 1000)

        # Filter rates within window
        window_rates = [r for r in sorted_rates if r.timestamp >= cutoff_ms]

        if not window_rates:
            return FundingTrend(
                window_label=label,
                window_hours=window_hours,
                mean=0.0,
                median=0.0,
                std=0.0,
                min=0.0,
                max=0.0,
                trend_slope=0.0,
                current=0.0,
                sample_count=0,
            )

        # Rates are sorted newest-first; reverse for chronological order
        chronological = list(reversed(window_rates))
        rates = [r.funding_rate for r in chronological]
        n = len(rates)

        mean = sum(rates) / n
        sorted_rates_vals = sorted(rates)
        median = (
            sorted_rates_vals[n // 2]
            if n % 2 == 1
            else (sorted_rates_vals[n // 2 - 1] + sorted_rates_vals[n // 2]) / 2
        )

        variance = sum((r - mean) ** 2 for r in rates) / n if n > 1 else 0.0
        std = variance**0.5

        # Linear regression slope (rate per hour)
        if n >= 2:
            timestamps_hours = [
                (r.timestamp - chronological[0].timestamp) / (3600 * 1000)
                for r in chronological
            ]
            mean_t = sum(timestamps_hours) / n
            mean_r = mean
            numerator = sum(
                (t - mean_t) * (r - mean_r)
                for t, r in zip(timestamps_hours, rates, strict=True)
            )
            denominator = sum((t - mean_t) ** 2 for t in timestamps_hours)
            trend_slope = numerator / denominator if denominator != 0 else 0.0
        else:
            trend_slope = 0.0

        return FundingTrend(
            window_label=label,
            window_hours=window_hours,
            mean=mean,
            median=median,
            std=std,
            min=min(rates),
            max=max(rates),
            trend_slope=trend_slope,
            current=rates[0],  # newest rate
            sample_count=n,
        )

    def _detect_extreme(
        self,
        sorted_rates: list[FundingRatePoint],
        current_rate: float,
    ) -> ExtremeFundingDetection:
        """Detect extreme funding conditions using percentiles.

        Args:
            sorted_rates: Funding rates sorted newest-first
            current_rate: Current funding rate

        Returns:
            ExtremeFundingDetection with analysis
        """
        if len(sorted_rates) < 2:
            return ExtremeFundingDetection(
                is_extreme=False,
                extreme_type="none",
                percentile_rank=50.0,
                high_threshold=0.0,
                low_threshold=0.0,
                severity=0.0,
                message="Insufficient data for extreme detection",
            )

        all_rates = [r.funding_rate for r in sorted_rates]
        sorted_all = sorted(all_rates)
        n = len(sorted_all)

        # Calculate percentile thresholds
        high_idx = int(n * self.high_percentile / 100)
        low_idx = int(n * self.low_percentile / 100)
        high_threshold = sorted_all[min(high_idx, n - 1)]
        low_threshold = sorted_all[min(low_idx, n - 1)]

        # Calculate percentile rank of current rate
        rank = sum(1 for r in all_rates if r <= current_rate) / n * 100

        # Determine extreme status
        is_extreme = False
        extreme_type = "none"
        severity = 0.0
        message = "Funding rate within normal range"

        if current_rate >= high_threshold:
            is_extreme = True
            extreme_type = "high"
            # Severity scales with how far above threshold
            if high_threshold != 0:
                severity = min(
                    1.0,
                    (current_rate - high_threshold) / high_threshold + 0.5,
                )
            else:
                severity = 1.0
            message = (
                f"Extremely HIGH funding rate: {current_rate:.6f} "
                f"(> {self.high_percentile}th percentile: "
                f"{high_threshold:.6f})"
            )
        elif current_rate <= low_threshold:
            is_extreme = True
            extreme_type = "low"
            if low_threshold != 0:
                severity = min(
                    1.0,
                    abs(current_rate - low_threshold) / abs(low_threshold) + 0.5,
                )
            else:
                severity = 1.0
            message = (
                f"Extremely LOW funding rate: {current_rate:.6f} "
                f"(< {self.low_percentile}th percentile: "
                f"{low_threshold:.6f})"
            )

        return ExtremeFundingDetection(
            is_extreme=is_extreme,
            extreme_type=extreme_type,
            percentile_rank=round(rank, 2),
            high_threshold=high_threshold,
            low_threshold=low_threshold,
            severity=round(severity, 4),
            message=message,
        )

    def _calculate_signal_adjustment(self, detection: ExtremeFundingDetection) -> float:
        """Calculate signal confidence adjustment based on extreme funding.

        When funding is extreme, signals in the funding direction are
        less reliable (crowded trade), so confidence should be reduced.

        Args:
            detection: Extreme funding detection result

        Returns:
            Adjustment factor (0.0-1.0) to subtract from confidence
        """
        if not detection.is_extreme:
            return 0.0

        # Scale adjustment by severity
        if detection.severity >= 0.8:
            return self.EXTREME_ADJUSTMENT
        elif detection.severity >= 0.5:
            return self.MODERATE_ADJUSTMENT
        else:
            return self.MODERATE_ADJUSTMENT * 0.5

    def _empty_result(self) -> FundingRateResult:
        """Return an empty result when no data is available."""
        empty_detection = ExtremeFundingDetection(
            is_extreme=False,
            extreme_type="none",
            percentile_rank=0.0,
            high_threshold=0.0,
            low_threshold=0.0,
            severity=0.0,
            message="No data available",
        )

        empty_trends = {}
        for label, hours in self.windows.items():
            empty_trends[label] = FundingTrend(
                window_label=label,
                window_hours=hours,
                mean=0.0,
                median=0.0,
                std=0.0,
                min=0.0,
                max=0.0,
                trend_slope=0.0,
                current=0.0,
                sample_count=0,
            )

        return FundingRateResult(
            symbol=self.symbol,
            current_rate=0.0,
            trends=empty_trends,
            extreme_detection=empty_detection,
            signal_adjustment=0.0,
            metadata={"error": "no_data"},
        )

    def to_signal(self, result: FundingRateResult) -> Signal:
        """Convert funding rate result to standardized signal.

        Args:
            result: FundingRateResult from analysis

        Returns:
            Signal with direction based on funding rate and
            confidence adjusted for extremes
        """
        if not result.trends or result.current_rate == 0.0:
            return Signal(
                direction=SignalDirection.HOLD,
                confidence=0.0,
                timestamp=datetime.now(UTC),
                metadata={"indicator": self.name, "reason": "no_data"},
            )

        # Determine direction from funding rate
        if result.funding_direction == FundingDirection.POSITIVE:
            direction = SignalDirection.SELL  # High funding = crowded long
        elif result.funding_direction == FundingDirection.NEGATIVE:
            direction = SignalDirection.BUY  # Low funding = crowded short
        else:
            direction = SignalDirection.HOLD

        # Base confidence from severity
        base_confidence = min(0.9, result.extreme_detection.severity)

        # Adjust for extremes
        adjusted_confidence = max(0.0, base_confidence - result.signal_adjustment)

        return Signal(
            direction=direction,
            confidence=adjusted_confidence,
            timestamp=datetime.now(UTC),
            metadata={
                "indicator": self.name,
                "symbol": result.symbol,
                "funding_rate": result.current_rate,
                "funding_rate_pct": result.current_rate * 100,
                "is_extreme": result.extreme_detection.is_extreme,
                "extreme_type": result.extreme_detection.extreme_type,
                "severity": result.extreme_detection.severity,
                "signal_adjustment": result.signal_adjustment,
            },
        )

    @staticmethod
    def calculate_percentile(values: list[float], percentile: float) -> float:
        """Calculate a percentile value from a list.

        Args:
            values: List of numeric values
            percentile: Percentile to calculate (0-100)

        Returns:
            Value at the given percentile
        """
        if not values:
            raise ValueError("Cannot calculate percentile of empty list")
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        idx = int(n * percentile / 100)
        idx = min(idx, n - 1)
        return sorted_vals[idx]
