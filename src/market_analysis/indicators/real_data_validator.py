"""Real Data Feature Validation for ICT indicators.

This module provides validation of ICT (Internal Conservation of Trade)
feature extraction on real market data, including drift detection,
data normalization, and edge case handling.

Key Features:
- Feature extraction validation on real data
- Feature drift detection against baseline
- Data normalization verification
- Edge case handling (gaps, volatility)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import numpy as np

from execution.paper.real_data_ingestion import (
    MarketDataSnapshot,
    OrderBookEntry,
    OrderBookSnapshot,
    TradeEntry,
)

logger = logging.getLogger(__name__)


class DriftStatus(str, Enum):
    """Feature drift detection status."""

    STABLE = "stable"
    DRIFT_DETECTED = "drift_detected"
    UNKNOWN = "unknown"


class NormalizationStatus(str, Enum):
    """Data normalization status."""

    NORMALIZED = "normalized"
    NEEDS_NORMALIZATION = "needs_normalization"
    INVALID = "invalid"


class EdgeCaseType(str, Enum):
    """Type of edge case detected."""

    DATA_GAP = "data_gap"
    HIGH_VOLATILITY = "high_volatility"
    LOW_LIQUIDITY = "low_liquidity"
    PRICE_SPIKE = "price_spike"
    STALE_DATA = "stale_data"
    NONE = "none"


@dataclass
class FeatureValidationResult:
    """Result of feature validation on data."""

    is_valid: bool
    features: dict[str, float] = field(default_factory=dict)
    validation_errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class DriftDetectionResult:
    """Result of feature drift detection."""

    status: DriftStatus
    drift_score: float
    changed_features: dict[str, float] = field(default_factory=dict)
    baseline_features: dict[str, float] = field(default_factory=dict)
    current_features: dict[str, float] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class EdgeCaseResult:
    """Result of edge case detection."""

    edge_case_type: EdgeCaseType
    severity: str  # "low", "medium", "high"
    details: dict[str, Any] = field(default_factory=dict)
    affected_features: list[str] = field(default_factory=list)


class RealDataValidator:
    """Validator for ICT features on real market data.

    This class validates ICT feature extraction on real data,
    detects feature drift, normalizes data, and handles edge cases.

    Attributes:
        _drift_threshold: Threshold for drift detection (default 0.15 = 15%)
        _volatility_threshold: Threshold for high volatility detection
        _gap_tolerance: Maximum allowed data gap in seconds
        _baseline_features: Cached baseline features for drift detection
    """

    def __init__(
        self,
        drift_threshold: float = 0.15,
        volatility_threshold: float = 2.0,
        gap_tolerance_seconds: int = 60,
    ) -> None:
        """Initialize real data validator.

        Args:
            drift_threshold: Threshold for drift detection (0.0 to 1.0)
            volatility_threshold: Standard deviation multiplier for volatility
            gap_tolerance_seconds: Maximum allowed gap between data points
        """
        self._drift_threshold = drift_threshold
        self._volatility_threshold = volatility_threshold
        self._gap_tolerance = gap_tolerance_seconds
        self._baseline_features: dict[str, float] = {}
        self._baseline_timestamp: datetime | None = None

    def validate_features(self, data: MarketDataSnapshot) -> FeatureValidationResult:
        """Validate ICT features extracted from market data.

        Args:
            data: Market data snapshot from real data ingestion

        Returns:
            FeatureValidationResult with validation status and extracted features
        """
        errors: list[str] = []
        warnings: list[str] = []
        features: dict[str, float] = {}

        # Validate data completeness
        if not data.is_complete():
            errors.append(
                f"Incomplete data: order_book={data.order_book is not None}, "
                f"trades={len(data.recent_trades)}"
            )

        # Extract features from order book
        if data.order_book is not None:
            ob_features = self._extract_order_book_features(data.order_book)
            features.update(ob_features)

        # Extract features from trades
        if data.recent_trades:
            trade_features = self._extract_trade_features(data.recent_trades)
            features.update(trade_features)

        # Validate feature ranges
        for feature_name, value in features.items():
            if not self._is_feature_valid(feature_name, value):
                warnings.append(f"Feature {feature_name}={value} outside normal range")

        # Check data freshness
        if data.freshness.value == "stale":
            warnings.append("Data is stale - age may affect feature accuracy")

        is_valid = len(errors) == 0

        logger.info(
            "Feature validation for %s - valid=%s, features=%d, errors=%d",
            data.symbol,
            is_valid,
            len(features),
            len(errors),
        )

        return FeatureValidationResult(
            is_valid=is_valid,
            features=features,
            validation_errors=errors,
            warnings=warnings,
        )

    def detect_feature_drift(
        self,
        baseline: dict[str, float] | None = None,
        current: dict[str, float] | None = None,
    ) -> DriftDetectionResult:
        """Detect drift between baseline and current features.

        Args:
            baseline: Baseline features (uses stored baseline if None)
            current: Current features (extracts from latest data if None)

        Returns:
            DriftDetectionResult with drift status and scores
        """
        # Use stored baseline if not provided
        if baseline is None:
            if not self._baseline_features:
                return DriftDetectionResult(
                    status=DriftStatus.UNKNOWN,
                    drift_score=0.0,
                    changed_features={},
                    baseline_features={},
                    current_features={},
                )
            baseline = self._baseline_features.copy()

        if current is None:
            return DriftDetectionResult(
                status=DriftStatus.UNKNOWN,
                drift_score=0.0,
                changed_features={},
                baseline_features=baseline,
                current_features={},
            )

        # Calculate drift
        changed_features: dict[str, float] = {}
        drift_scores: list[float] = []

        all_features = set(baseline.keys()) | set(current.keys())

        for feature in all_features:
            base_val = baseline.get(feature, 0.0)
            curr_val = current.get(feature, 0.0)

            if base_val != 0.0:
                # Calculate relative change
                rel_change = abs(curr_val - base_val) / abs(base_val)
                changed_features[feature] = rel_change
                drift_scores.append(rel_change)
            elif curr_val != 0.0:
                # New feature that wasn't in baseline
                changed_features[feature] = 1.0
                drift_scores.append(1.0)

        # Overall drift score is mean of individual scores
        drift_score = float(np.mean(drift_scores)) if drift_scores else 0.0

        # Determine status
        if drift_score > self._drift_threshold:
            status = DriftStatus.DRIFT_DETECTED
            logger.warning(
                "Feature drift detected - score=%.3f, threshold=%.3f, "
                "changed_features=%s",
                drift_score,
                self._drift_threshold,
                list(changed_features.keys()),
            )
        else:
            status = DriftStatus.STABLE

        return DriftDetectionResult(
            status=status,
            drift_score=drift_score,
            changed_features=changed_features,
            baseline_features=baseline,
            current_features=current,
        )

    def set_baseline(self, features: dict[str, float]) -> None:
        """Set baseline features for drift detection.

        Args:
            features: Baseline feature dictionary
        """
        self._baseline_features = features.copy()
        self._baseline_timestamp = datetime.now(UTC)
        logger.info(
            "Baseline features set - count=%d, timestamp=%s",
            len(features),
            self._baseline_timestamp.isoformat(),
        )

    def normalize_data(
        self,
        data: MarketDataSnapshot,
    ) -> tuple[MarketDataSnapshot, NormalizationStatus]:
        """Normalize market data for consistent feature extraction.

        Args:
            data: Raw market data snapshot

        Returns:
            Tuple of (normalized snapshot, normalization status)
        """
        if data.order_book is None or not data.recent_trades:
            return data, NormalizationStatus.NEEDS_NORMALIZATION

        try:
            # Normalize prices to mid price
            mid_price = data.order_book.get_mid_price()
            if mid_price is None or mid_price <= 0:
                return data, NormalizationStatus.INVALID

            # Check if normalization needed
            normalized_bids = []
            for bid in data.order_book.bids:
                normalized_bids.append(
                    OrderBookEntry(
                        price=(bid.price - mid_price) / mid_price,
                        quantity=bid.quantity,
                        side=bid.side,
                    )
                )

            normalized_asks = []
            for ask in data.order_book.asks:
                normalized_asks.append(
                    OrderBookEntry(
                        price=(ask.price - mid_price) / mid_price,
                        quantity=ask.quantity,
                        side=ask.side,
                    )
                )

            # Normalize trade prices
            normalized_trades = []
            for trade in data.recent_trades:
                normalized_trades.append(
                    TradeEntry(
                        trade_id=trade.trade_id,
                        symbol=trade.symbol,
                        side=trade.side,
                        price=(trade.price - mid_price) / mid_price,
                        quantity=trade.quantity,
                        timestamp=trade.timestamp,
                        source=trade.source,
                    )
                )

            # Create normalized snapshot
            normalized_snapshot = MarketDataSnapshot(
                symbol=data.symbol,
                timestamp=data.timestamp,
                order_book=OrderBookSnapshot(
                    symbol=data.order_book.symbol,
                    timestamp=data.order_book.timestamp,
                    bids=normalized_bids,
                    asks=normalized_asks,
                    source=data.order_book.source,
                ),
                recent_trades=normalized_trades,
                source=data.source,
                freshness=data.freshness,
            )

            return normalized_snapshot, NormalizationStatus.NORMALIZED

        except Exception as exc:
            logger.error("Normalization failed for %s: %s", data.symbol, exc)
            return data, NormalizationStatus.INVALID

    def handle_edge_cases(
        self,
        data: MarketDataSnapshot,
    ) -> EdgeCaseResult:
        """Detect and handle edge cases in market data.

        Args:
            data: Market data snapshot

        Returns:
            EdgeCaseResult describing any detected edge cases
        """
        edge_cases: list[EdgeCaseType] = []
        details: dict[str, Any] = {}
        severity = "low"

        # Check for data gaps
        gap_result = self._detect_data_gaps(data)
        if gap_result:
            edge_cases.append(EdgeCaseType.DATA_GAP)
            details["gap_seconds"] = gap_result
            severity = "medium"

        # Check for high volatility
        volatility_result = self._detect_high_volatility(data)
        if volatility_result:
            edge_cases.append(EdgeCaseType.HIGH_VOLATILITY)
            details["volatility_score"] = volatility_result
            severity = "high"

        # Check for low liquidity
        liquidity_result = self._detect_low_liquidity(data)
        if liquidity_result:
            edge_cases.append(EdgeCaseType.LOW_LIQUIDITY)
            details["liquidity_score"] = liquidity_result
            severity = max(severity, "medium")

        # Check for price spikes
        spike_result = self._detect_price_spikes(data)
        if spike_result:
            edge_cases.append(EdgeCaseType.PRICE_SPIKE)
            details["spike_magnitude"] = spike_result
            severity = "high"

        # Check for stale data
        if data.freshness.value == "stale":
            edge_cases.append(EdgeCaseType.STALE_DATA)
            details["data_age"] = str(data.timestamp)
            severity = max(severity, "medium")

        # Determine final edge case type
        if not edge_cases:
            edge_case_type = EdgeCaseType.NONE
        else:
            # Return most severe edge case
            edge_case_type = max(edge_cases, key=lambda x: x.value)

        affected_features = []
        if edge_case_type in [EdgeCaseType.HIGH_VOLATILITY, EdgeCaseType.PRICE_SPIKE]:
            affected_features = ["price", "returns", "momentum"]

        logger.info(
            "Edge case detection for %s - type=%s, severity=%s",
            data.symbol,
            edge_case_type.value,
            severity,
        )

        return EdgeCaseResult(
            edge_case_type=edge_case_type,
            severity=severity,
            details=details,
            affected_features=affected_features,
        )

    def _extract_order_book_features(
        self,
        order_book: OrderBookSnapshot,
    ) -> dict[str, float]:
        """Extract features from order book.

        Args:
            order_book: Order book snapshot

        Returns:
            Dictionary of feature name to value
        """
        features: dict[str, float] = {}

        if not order_book.is_valid():
            return features

        # Bid-ask spread
        best_bid = max(order_book.bids, key=lambda x: x.price).price
        best_ask = min(order_book.asks, key=lambda x: x.price).price
        spread = (best_ask - best_bid) / best_bid if best_bid > 0 else 0.0
        features["bid_ask_spread"] = spread

        # Order book imbalance
        total_bid_qty = sum(b.quantity for b in order_book.bids)
        total_ask_qty = sum(a.quantity for a in order_book.asks)
        imbalance = (
            (total_bid_qty - total_ask_qty) / (total_bid_qty + total_ask_qty)
            if (total_bid_qty + total_ask_qty) > 0
            else 0.0
        )
        features["order_book_imbalance"] = imbalance

        # Weighted mid price
        mid_price = order_book.get_mid_price()
        if mid_price:
            features["mid_price"] = mid_price

        return features

    def _extract_trade_features(
        self,
        trades: list[TradeEntry],
    ) -> dict[str, float]:
        """Extract features from trade data.

        Args:
            trades: List of trade entries

        Returns:
            Dictionary of feature name to value
        """
        features: dict[str, float] = {}

        if not trades:
            return features

        # Trade rate (trades per minute)
        if len(trades) >= 2:
            time_span = (
                trades[0].timestamp - trades[-1].timestamp
            ).total_seconds() / 60.0
            if time_span > 0:
                features["trade_rate"] = len(trades) / time_span
            else:
                features["trade_rate"] = float(len(trades))
        else:
            features["trade_rate"] = float(len(trades))

        # Buy-sell ratio
        buy_count = sum(1 for t in trades if t.side == "buy")
        sell_count = sum(1 for t in trades if t.side == "sell")
        total = buy_count + sell_count
        features["buy_sell_ratio"] = (
            (buy_count - sell_count) / total if total > 0 else 0.0
        )

        # Average trade size
        avg_size = np.mean([t.quantity for t in trades])
        features["avg_trade_size"] = float(avg_size)

        # Price volatility from trades
        prices = [t.price for t in trades]
        if len(prices) >= 2:
            features["trade_price_std"] = float(np.std(prices))

        # Momentum (price change over trades)
        if len(prices) >= 2:
            momentum = (prices[0] - prices[-1]) / prices[-1] if prices[-1] > 0 else 0.0
            features["trade_momentum"] = momentum

        return features

    def _is_feature_valid(self, feature_name: str, value: float) -> bool:
        """Check if feature value is within valid range.

        Args:
            feature_name: Name of feature
            value: Feature value

        Returns:
            True if value is valid
        """
        # Define reasonable ranges for key features
        valid_ranges: dict[str, tuple[float, float]] = {
            "bid_ask_spread": (0.0, 0.1),  # 0 to 10%
            "order_book_imbalance": (-1.0, 1.0),  # -1 to 1
            "buy_sell_ratio": (-1.0, 1.0),  # -1 to 1
            "trade_rate": (0.0, 1000.0),  # 0 to 1000 trades/min
            "avg_trade_size": (0.0, 1000.0),  # 0 to 1000 units
        }

        if feature_name not in valid_ranges:
            return True  # Unknown features are considered valid

        min_val, max_val = valid_ranges[feature_name]
        return min_val <= value <= max_val

    def _detect_data_gaps(self, data: MarketDataSnapshot) -> float | None:
        """Detect gaps in market data.

        Args:
            data: Market data snapshot

        Returns:
            Gap duration in seconds, or None if no gap
        """
        if not data.recent_trades:
            return float(self._gap_tolerance * 2)

        # Check time between most recent and oldest trade
        if len(data.recent_trades) >= 2:
            oldest = min(t.timestamp for t in data.recent_trades)
            newest = max(t.timestamp for t in data.recent_trades)
            gap = (newest - oldest).total_seconds()

            if gap > self._gap_tolerance:
                return gap

        return None

    def _detect_high_volatility(self, data: MarketDataSnapshot) -> float | None:
        """Detect high volatility in market data.

        Args:
            data: Market data snapshot

        Returns:
            Volatility score, or None if normal
        """
        if not data.recent_trades or len(data.recent_trades) < 2:
            return None

        prices = [t.price for t in data.recent_trades]
        returns = np.diff(prices) / prices[:-1] if len(prices) > 1 else []

        if len(returns) < 2:
            return None

        volatility = float(np.std(returns))

        # Volatility is high if absolute std dev exceeds threshold
        # Default threshold: 0.001 = 0.1% per trade interval
        if volatility > 0.001:
            return volatility

        return None

    def _detect_low_liquidity(self, data: MarketDataSnapshot) -> float | None:
        """Detect low liquidity in market data.

        Args:
            data: Market data snapshot

        Returns:
            Liquidity score (lower = less liquid), or None if normal
        """
        if data.order_book is None:
            return 0.5  # Unknown liquidity

        total_bid_qty = sum(b.quantity for b in data.order_book.bids)
        total_ask_qty = sum(a.quantity for a in data.order_book.asks)
        total_qty = total_bid_qty + total_ask_qty

        # Liquidity threshold
        if total_qty < 1.0:  # Less than 1 unit total
            return total_qty

        return None

    def _detect_price_spikes(self, data: MarketDataSnapshot) -> float | None:
        """Detect price spikes in market data.

        Args:
            data: Market data snapshot

        Returns:
            Spike magnitude, or None if no spike
        """
        if not data.recent_trades or len(data.recent_trades) < 3:
            return None

        prices = [t.price for t in data.recent_trades]
        median_price = float(np.median(prices))

        if median_price == 0:
            return None

        # Check for prices far from median
        max_deviation = max(abs(p - median_price) / median_price for p in prices)
        if max_deviation > 0.05:  # 5% deviation threshold
            return max_deviation

        return None

    def get_baseline_features(self) -> dict[str, float]:
        """Get stored baseline features.

        Returns:
            Baseline feature dictionary
        """
        return self._baseline_features.copy()

    def clear_baseline(self) -> None:
        """Clear stored baseline features."""
        self._baseline_features.clear()
        self._baseline_timestamp = None
