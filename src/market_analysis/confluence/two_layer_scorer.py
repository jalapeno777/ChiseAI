"""Two-Layer Scorer for ICT Signals.

This module provides the main entry point for the two-layer scoring system:
- Layer 1: Individual Signal Scoring (CVD, FVG, Order Block)
- Layer 2: Confluence Aggregation

The two-layer scorer takes raw ICT signal data and produces a unified
confluence score with consensus direction.

Supported Signals (per EP-ICT-004 validation):
- CVD (Cumulative Volume Delta): 100% validated → weight 1.0
- FVG (Fair Value Gap): 100% validated → weight 1.0
- Order Block: 80.77% validated → weight 0.85

EXCLUDED Signals (per BL-BOS-CHOCH-001):
- BOS (Break of Structure) - NOT SUPPORTED
- CHoCH (Change of Character) - NOT SUPPORTED

Usage:
    scorer = TwoLayerScorer()
    result = scorer.score(
        cvd_result=cvd_data,
        fvg_results=[fvg1, fvg2],
        order_blocks=[ob1],
        timeframe="1H"
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from market_analysis.confluence.layer1_signal_scorer import Layer1Score
    from market_analysis.confluence.layer2_confluence_aggregator import (
        Layer2ConfluenceResult,
    )
    from market_analysis.cvd.cvd_calculator import CVDResult
    from market_analysis.fvg.fvg_detector import FVGDetectionResult
    from market_analysis.order_block.ob_detector import OBDetectionResult

from market_analysis.confluence.layer1_signal_scorer import (
    Layer1SignalScorer,
)
from market_analysis.confluence.layer2_confluence_aggregator import (
    Layer2ConfluenceAggregator,
)
from market_analysis.confluence.signal_aggregator import SignalDirection
from market_analysis.confluence.signal_weights import (
    ICTSignalType,
)


@dataclass
class TwoLayerScore:
    """Final two-layer scoring result.

    Attributes:
        confluence_score: Normalized confluence score (0.0-1.0)
        direction: Consensus direction
        confidence: Overall confidence (0.0-1.0)
        layer1_scores: Individual Layer 1 scores
        layer2_result: Layer 2 aggregation result
        is_strong_signal: Whether this is a strong trading signal
        signals_included: List of signal types that contributed
        signals_excluded: List of signal types that were excluded
        metadata: Additional scoring metadata
        timestamp: Calculation timestamp
    """

    confluence_score: float
    direction: SignalDirection
    confidence: float
    layer1_scores: list[Layer1Score] = field(default_factory=list)
    layer2_result: Layer2ConfluenceResult | None = None
    is_strong_signal: bool = False
    signals_included: list[str] = field(default_factory=list)
    signals_excluded: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: int | None = None

    def __post_init__(self) -> None:
        """Validate and calculate derived fields."""
        self.confluence_score = max(0.0, min(1.0, self.confluence_score))
        self.confidence = max(0.0, min(1.0, self.confidence))
        self.is_strong_signal = self.confluence_score >= 0.7 and self.confidence >= 0.5

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization.

        Returns:
            Dictionary representation of the score
        """
        result = {
            "confluence_score": round(self.confluence_score, 3),
            "direction": str(self.direction),
            "confidence": round(self.confidence, 3),
            "is_strong_signal": self.is_strong_signal,
            "signals_included": self.signals_included,
            "signals_excluded": self.signals_excluded,
            "layer1_scores": [s.to_dict() for s in self.layer1_scores],
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }
        if self.layer2_result:
            result["layer2"] = self.layer2_result.to_dict()
        return result


class TwoLayerScorer:
    """Two-layer scorer for ICT signals.

    Combines Layer 1 individual signal scoring with Layer 2 confluence
    aggregation to produce unified trading signals.

    Supported signals: CVD, FVG, Order Block
    Excluded signals: BOS, CHoCH (per BL-BOS-CHOCH-001)
    """

    def __init__(
        self,
        min_confidence_threshold: float = 0.3,
        min_signals: int = 1,
        enable_feature_flags: bool = True,
    ):
        """Initialize two-layer scorer.

        Args:
            min_confidence_threshold: Minimum confidence for Layer 1 signals
            min_signals: Minimum signals required for valid Layer 2 confluence
            enable_feature_flags: Whether to enable per-signal feature flags
        """
        self.layer1_scorer = Layer1SignalScorer(min_confidence_threshold)
        self.layer2_aggregator = Layer2ConfluenceAggregator(
            min_signals=min_signals,
            enable_feature_flags=enable_feature_flags,
        )

    def set_signal_enabled(self, signal_type: str, enabled: bool) -> None:
        """Enable or disable a specific signal type.

        Args:
            signal_type: The signal type (cvd, fvg, order_block)
            enabled: Whether the signal type is enabled
        """
        self.layer2_aggregator.set_feature_flag(signal_type, enabled)

    def is_signal_supported(self, signal_type: str) -> bool:
        """Check if a signal type is supported.

        Args:
            signal_type: The signal type to check

        Returns:
            True if the signal type is supported
        """
        return ICTSignalType.is_valid_signal(signal_type)

    def score(
        self,
        cvd_result: CVDResult | None = None,
        fvg_results: list[FVGDetectionResult] | None = None,
        order_blocks: list[OBDetectionResult] | None = None,
        price_data: list[float] | None = None,
        current_price: float | None = None,
        timeframe: str = "1H",
        timestamp: int | None = None,
    ) -> TwoLayerScore:
        """Score all available ICT signals through two-layer scoring.

        Args:
            cvd_result: Optional CVD calculation result
            fvg_results: Optional list of FVG detection results
            order_blocks: Optional list of Order Block detection results
            price_data: Optional price data for CVD divergence detection
            current_price: Optional current price for FVG mitigation check
            timeframe: Timeframe of the signals
            timestamp: Optional timestamp for the calculation

        Returns:
            TwoLayerScore with combined scoring results
        """
        excluded_signals: list[str] = []
        layer1_scores: list[Layer1Score] = []
        included_signals: list[str] = []

        # Score CVD if available and enabled
        if cvd_result is not None and self.layer2_aggregator.is_signal_enabled("cvd"):
            cvd_score = self.layer1_scorer.score_cvd(cvd_result, timeframe, price_data)
            if cvd_score is not None:
                layer1_scores.append(cvd_score)
                included_signals.append("cvd")
        elif cvd_result is not None:
            excluded_signals.append("cvd")

        # Score FVGs if available and enabled
        if fvg_results and self.layer2_aggregator.is_signal_enabled("fvg"):
            fvg_scores = self.layer1_scorer.score_multiple_fvgs(fvg_results, timeframe)
            layer1_scores.extend(fvg_scores)
            if fvg_scores:
                included_signals.append("fvg")
        elif fvg_results:
            excluded_signals.append("fvg")

        # Score Order Blocks if available and enabled
        if order_blocks and self.layer2_aggregator.is_signal_enabled("order_block"):
            ob_scores = self.layer1_scorer.score_multiple_order_blocks(
                order_blocks, timeframe
            )
            layer1_scores.extend(ob_scores)
            if ob_scores:
                included_signals.append("order_block")
        elif order_blocks:
            excluded_signals.append("order_block")

        # Aggregate through Layer 2
        layer2_result = self.layer2_aggregator.aggregate(layer1_scores, timestamp)

        # Build final result
        return TwoLayerScore(
            confluence_score=layer2_result.confluence_score,
            direction=layer2_result.direction,
            confidence=layer2_result.confidence,
            layer1_scores=layer1_scores,
            layer2_result=layer2_result,
            signals_included=included_signals,
            signals_excluded=excluded_signals,
            metadata={
                "min_confidence_threshold": self.layer1_scorer.min_confidence_threshold,
                "min_signals": self.layer2_aggregator.min_signals,
                "total_layer1_scores": len(layer1_scores),
            },
            timestamp=timestamp,
        )

    def score_single_signal(
        self,
        signal_type: str,
        signal_data: Any,
        timeframe: str = "1H",
        **kwargs: Any,
    ) -> TwoLayerScore | None:
        """Score a single signal type.

        Args:
            signal_type: Type of signal (cvd, fvg, order_block)
            signal_data: The signal data (varies by type)
            timeframe: Timeframe of the signal
            **kwargs: Additional arguments (price_data, current_price, etc.)

        Returns:
            TwoLayerScore or None if signal type not supported
        """
        if not self.is_signal_supported(signal_type):
            return None

        if signal_type == "cvd":
            return self.score(
                cvd_result=signal_data,
                timeframe=timeframe,
                price_data=kwargs.get("price_data"),
            )
        elif signal_type == "fvg":
            fvg_results = (
                signal_data if isinstance(signal_data, list) else [signal_data]
            )
            return self.score(
                fvg_results=fvg_results,
                timeframe=timeframe,
                current_price=kwargs.get("current_price"),
            )
        elif signal_type == "order_block":
            ob_results = signal_data if isinstance(signal_data, list) else [signal_data]
            return self.score(order_blocks=ob_results, timeframe=timeframe)

        return None

    def get_supported_signals(self) -> list[str]:
        """Get list of supported signal types.

        Returns:
            List of supported signal type strings
        """
        return [s.value for s in ICTSignalType.get_supported_signals()]

    def get_signal_weights(self) -> dict[str, float]:
        """Get weights for all supported signals.

        Returns:
            Dictionary mapping signal type to weight
        """
        from market_analysis.confluence.signal_weights import get_all_weights

        return get_all_weights()
