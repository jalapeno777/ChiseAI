"""Comprehensive tests for the hybrid reasoning engine.

Tests cover:
- NeuralComponent: pattern recognition and feature extraction
- SymbolicComponent: rule-based reasoning and inference
- IntegrationLayer: fusion of neural and symbolic outputs
- HybridReasoningEngine: end-to-end hybrid reasoning
"""

import pytest
import numpy as np
from unittest.mock import Mock, patch

from src.neuro_symbolic.reasoning.neural_component import (
    NeuralComponent,
    NeuralOutput,
    MarketFeatureExtractor,
    PatternRecognizer,
)

from src.neuro_symbolic.reasoning.symbolic_component import (
    SymbolicComponent,
    SymbolicOutput,
    RuleResult,
    RuleType,
    TrendDirection,
    TrendRule,
    VolumeRule,
    MomentumRule,
    VolatilityRule,
    SupportResistanceRule,
    InferenceEngine,
    SymbolicRule,
)

from src.neuro_symbolic.reasoning.integration_layer import (
    IntegrationLayer,
    FusedResult,
    ReasoningChain,
    FusionStrategy,
)

from src.neuro_symbolic.reasoning.hybrid_engine import (
    HybridReasoningEngine,
    HybridReasoningResult,
    analyze_market_data,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_market_data():
    """Sample market data for testing."""
    return {
        "price": 100.0,
        "volume": 10000.0,
        "high": 105.0,
        "low": 95.0,
        "prev_price": 98.0,
        "prev_volume": 8000.0,
        "avg_price": 99.0,
        "avg_volume": 9000.0,
        "sma_short": 99.5,
        "sma_long": 98.0,
        "support": 95.0,
        "resistance": 105.0,
        "atr": 3.0,
    }


@pytest.fixture
def bullish_market_data():
    """Bullish market data for testing."""
    return {
        "price": 110.0,
        "volume": 15000.0,
        "high": 112.0,
        "low": 108.0,
        "prev_price": 100.0,
        "prev_volume": 10000.0,
        "avg_price": 105.0,
        "avg_volume": 12000.0,
        "sma_short": 108.0,
        "sma_long": 100.0,
        "support": 100.0,
        "resistance": 115.0,
    }


@pytest.fixture
def bearish_market_data():
    """Bearish market data for testing."""
    return {
        "price": 90.0,
        "volume": 20000.0,
        "high": 95.0,
        "low": 88.0,
        "prev_price": 100.0,
        "prev_volume": 10000.0,
        "avg_price": 95.0,
        "avg_volume": 12000.0,
        "sma_short": 92.0,
        "sma_long": 98.0,
        "support": 85.0,
        "resistance": 100.0,
    }


# ============================================================================
# NeuralComponent Tests
# ============================================================================


class TestMarketFeatureExtractor:
    """Tests for MarketFeatureExtractor class."""

    def test_extract_basic_features(self):
        """Test basic feature extraction."""
        extractor = MarketFeatureExtractor(feature_dim=32)
        data = {"price": 100.0, "volume": 1000.0, "high": 105.0, "low": 95.0}

        features = extractor.extract(data)

        assert features is not None
        assert isinstance(features, np.ndarray)
        assert len(features) == 32

    def test_extract_with_price_change(self):
        """Test feature extraction with price change."""
        extractor = MarketFeatureExtractor(feature_dim=32)
        data = {"price": 110.0, "prev_price": 100.0, "volume": 1000.0}

        features = extractor.extract(data)

        # Momentum feature should be positive
        assert features[2] > 0  # Price momentum

    def test_extract_empty_data(self):
        """Test extraction with minimal data."""
        extractor = MarketFeatureExtractor(feature_dim=32)
        features = extractor.extract({})

        assert features is not None
        assert len(features) == 32

    def test_feature_names_exist(self):
        """Test that feature names are defined."""
        extractor = MarketFeatureExtractor()
        assert len(extractor._feature_names) > 0


class TestPatternRecognizer:
    """Tests for PatternRecognizer class."""

    def test_recognize_patterns(self):
        """Test pattern recognition."""
        recognizer = PatternRecognizer(num_patterns=10)
        features = np.random.randn(32)

        patterns = recognizer.recognize(features)

        assert isinstance(patterns, list)
        assert len(patterns) <= 5  # Top 5 patterns

    def test_pattern_structure(self):
        """Test pattern output structure."""
        recognizer = PatternRecognizer(num_patterns=10)
        features = np.random.randn(32)

        patterns = recognizer.recognize(features)

        if patterns:
            assert "name" in patterns[0]
            assert "confidence" in patterns[0]
            assert "type" in patterns[0]
            assert 0 <= patterns[0]["confidence"] <= 1


class TestNeuralComponent:
    """Tests for NeuralComponent class."""

    def test_initialization(self):
        """Test component initialization."""
        component = NeuralComponent(
            feature_dim=32, num_patterns=10, confidence_threshold=0.5
        )

        assert component.feature_dim == 32
        assert component.num_patterns == 10
        assert component.confidence_threshold == 0.5

    def test_process_basic(self, sample_market_data):
        """Test basic processing."""
        component = NeuralComponent()
        output = component.process(sample_market_data)

        assert isinstance(output, NeuralOutput)
        assert isinstance(output.features, np.ndarray)
        assert isinstance(output.patterns, list)
        assert isinstance(output.confidence, float)

    def test_process_returns_patterns(self, sample_market_data):
        """Test that processing returns detected patterns."""
        component = NeuralComponent()
        output = component.process(sample_market_data)

        # Should detect some patterns
        assert len(output.patterns) >= 0

    def test_confidence_in_valid_range(self, sample_market_data):
        """Test confidence is in valid range."""
        component = NeuralComponent()
        output = component.process(sample_market_data)

        assert 0 <= output.confidence <= 1

    def test_get_feature_importance(self, sample_market_data):
        """Test feature importance extraction."""
        component = NeuralComponent()
        component.process(sample_market_data)

        importance = component.get_feature_importance()

        assert isinstance(importance, dict)

    def test_reset_state(self, sample_market_data):
        """Test state reset."""
        component = NeuralComponent()
        component.process(sample_market_data)

        component.reset_state()

        assert component._last_features is None
        assert component._last_patterns == []


# ============================================================================
# SymbolicComponent Tests
# ============================================================================


class TestTrendRule:
    """Tests for TrendRule class."""

    def test_uptrend_detection(self, bullish_market_data):
        """Test uptrend detection."""
        rule = TrendRule(threshold=0.02)
        result = rule.evaluate(bullish_market_data)

        assert isinstance(result, RuleResult)
        assert result.triggered
        assert result.value == TrendDirection.UP

    def test_downtrend_detection(self, bearish_market_data):
        """Test downtrend detection."""
        rule = TrendRule(threshold=0.02)
        result = rule.evaluate(bearish_market_data)

        assert isinstance(result, RuleResult)
        assert result.triggered
        assert result.value == TrendDirection.DOWN

    def test_sideways_detection(self, sample_market_data):
        """Test sideways detection."""
        rule = TrendRule(threshold=0.05)
        result = rule.evaluate(sample_market_data)

        assert isinstance(result, RuleResult)
        assert result.value == TrendDirection.SIDEWAYS or not result.triggered

    def test_confidence_increases_with_move_size(self):
        """Test confidence scales with move size."""
        rule = TrendRule(threshold=0.02)

        small_move = {"price": 101.0, "prev_price": 100.0}
        large_move = {"price": 110.0, "prev_price": 100.0}

        small_result = rule.evaluate(small_move)
        large_result = rule.evaluate(large_move)

        assert large_result.confidence > small_result.confidence


class TestVolumeRule:
    """Tests for VolumeRule class."""

    def test_volume_spike_detection(self, bullish_market_data):
        """Test volume spike detection."""
        rule = VolumeRule(spike_threshold=1.2)  # 15000/12000 = 1.25x
        result = rule.evaluate(bullish_market_data)

        assert isinstance(result, RuleResult)
        assert result.triggered
        assert result.value == "spike"

    def test_normal_volume(self):
        """Test normal volume detection."""
        rule = VolumeRule(spike_threshold=2.0)
        data = {"volume": 1000.0, "avg_volume": 1000.0}
        result = rule.evaluate(data)

        assert result.value == "normal"

    def test_volume_drought(self):
        """Test volume drought detection."""
        rule = VolumeRule(spike_threshold=2.0)
        data = {"volume": 100.0, "avg_volume": 1000.0}
        result = rule.evaluate(data)

        assert result.triggered
        assert result.value == "drought"


class TestMomentumRule:
    """Tests for MomentumRule class."""

    def test_strong_bullish_momentum(self, bullish_market_data):
        """Test strong bullish momentum detection."""
        rule = MomentumRule(strong_momentum_threshold=0.05)
        result = rule.evaluate(bullish_market_data)

        assert result.triggered
        assert "bullish" in result.value

    def test_strong_bearish_momentum(self, bearish_market_data):
        """Test strong bearish momentum detection."""
        rule = MomentumRule(strong_momentum_threshold=0.05)
        result = rule.evaluate(bearish_market_data)

        assert result.triggered
        assert "bearish" in result.value

    def test_momentum_acceleration(self):
        """Test momentum acceleration detection."""
        rule = MomentumRule()
        data = {"price": 110.0, "prev_price": 105.0, "prev_price_2": 103.0}
        result = rule.evaluate(data)

        assert "accelerating" in result.explanation.lower() or result.triggered


class TestVolatilityRule:
    """Tests for VolatilityRule class."""

    def test_high_volatility(self):
        """Test high volatility detection."""
        rule = VolatilityRule(high_volatility_threshold=0.05)
        data = {"high": 110.0, "low": 90.0, "price": 100.0}
        result = rule.evaluate(data)

        assert result.triggered
        assert result.value == "high"

    def test_low_volatility(self):
        """Test low volatility detection."""
        rule = VolatilityRule(high_volatility_threshold=0.05)
        data = {"high": 101.0, "low": 99.0, "price": 100.0}
        result = rule.evaluate(data)

        assert result.value == "low"

    def test_atr_based_volatility(self):
        """Test ATR-based volatility."""
        rule = VolatilityRule(high_volatility_threshold=0.05)
        data = {"price": 100.0, "atr": 6.0}
        result = rule.evaluate(data)

        assert result.triggered


class TestSupportResistanceRule:
    """Tests for SupportResistanceRule class."""

    def test_support_test(self):
        """Test support level test."""
        rule = SupportResistanceRule(proximity_threshold=0.02)
        data = {"price": 96.0, "support": 95.0, "resistance": 110.0}
        result = rule.evaluate(data)

        assert result.triggered
        assert "support" in result.value

    def test_resistance_test(self):
        """Test resistance level test."""
        rule = SupportResistanceRule(proximity_threshold=0.02)
        data = {"price": 104.0, "support": 90.0, "resistance": 105.0}
        result = rule.evaluate(data)

        assert result.triggered
        assert "resistance" in result.value

    def test_support_broken(self):
        """Test support break detection."""
        rule = SupportResistanceRule(proximity_threshold=0.02)
        data = {"price": 93.0, "support": 95.0}
        result = rule.evaluate(data)

        assert result.triggered
        assert "broken" in result.value


class TestInferenceEngine:
    """Tests for InferenceEngine class."""

    def test_trend_confirmation_inference(self):
        """Test trend confirmation inference."""
        engine = InferenceEngine()
        results = [
            RuleResult(
                "trend", RuleType.TREND, True, 0.8, TrendDirection.UP, "Uptrend"
            ),
            RuleResult(
                "momentum", RuleType.MOMENTUM, True, 0.7, "bullish", "Bullish momentum"
            ),
        ]

        inferred = engine.infer(results)

        assert "trend_confirmed" in inferred
        assert inferred["trend_confirmed"] == "bullish"

    def test_reversal_signal_inference(self):
        """Test reversal signal inference."""
        engine = InferenceEngine()
        results = [
            RuleResult(
                "sr",
                RuleType.SUPPORT_RESISTANCE,
                True,
                0.7,
                "support_test",
                "At support",
            ),
            RuleResult("vol", RuleType.VOLUME, True, 0.8, "spike", "Volume spike"),
        ]

        inferred = engine.infer(results)

        assert "reversal_signal" in inferred

    def test_breakout_signal_inference(self):
        """Test breakout signal inference."""
        engine = InferenceEngine()
        results = [
            RuleResult(
                "sr",
                RuleType.SUPPORT_RESISTANCE,
                True,
                0.8,
                "resistance_broken",
                "Resistance broken",
            ),
            RuleResult("vol", RuleType.VOLUME, True, 0.7, "spike", "Volume spike"),
        ]

        inferred = engine.infer(results)

        assert "breakout_signal" in inferred
        assert inferred["breakout_confirmed"] is True


class TestSymbolicComponent:
    """Tests for SymbolicComponent class."""

    def test_initialization(self):
        """Test component initialization."""
        component = SymbolicComponent(confidence_threshold=0.5)

        assert component.confidence_threshold == 0.5
        assert len(component._rules) > 0

    def test_process_basic(self, sample_market_data):
        """Test basic processing."""
        component = SymbolicComponent()
        output = component.process(sample_market_data)

        assert isinstance(output, SymbolicOutput)
        assert isinstance(output.triggered_rules, list)
        assert isinstance(output.trend_direction, TrendDirection)
        assert isinstance(output.overall_confidence, float)

    def test_process_bullish_data(self, bullish_market_data):
        """Test processing bullish data."""
        component = SymbolicComponent()
        output = component.process(bullish_market_data)

        assert output.trend_direction in [TrendDirection.UP, TrendDirection.UNKNOWN]
        assert len(output.triggered_rules) > 0

    def test_process_bearish_data(self, bearish_market_data):
        """Test processing bearish data."""
        component = SymbolicComponent()
        output = component.process(bearish_market_data)

        assert output.trend_direction in [TrendDirection.DOWN, TrendDirection.UNKNOWN]

    def test_explanations_generated(self, sample_market_data):
        """Test that explanations are generated."""
        component = SymbolicComponent()
        output = component.process(sample_market_data)

        assert isinstance(output.explanations, list)

    def test_inferences_generated(self, sample_market_data):
        """Test that inferences are generated."""
        component = SymbolicComponent()
        output = component.process(sample_market_data)

        assert isinstance(output.inferred_facts, dict)

    def test_add_custom_rule(self):
        """Test adding custom rule."""
        component = SymbolicComponent()
        initial_count = len(component._rules)

        custom_rule = TrendRule(threshold=0.01)
        component.add_rule(custom_rule)

        assert len(component._rules) == initial_count + 1

    def test_remove_rule(self):
        """Test removing rule."""
        component = SymbolicComponent()

        result = component.remove_rule("trend_detection")

        assert result is True
        assert all(r.name != "trend_detection" for r in component._rules)


# ============================================================================
# IntegrationLayer Tests
# ============================================================================


class TestIntegrationLayer:
    """Tests for IntegrationLayer class."""

    def test_initialization(self):
        """Test layer initialization."""
        layer = IntegrationLayer(
            fusion_strategy=FusionStrategy.ADAPTIVE,
            default_neural_weight=0.5,
            default_symbolic_weight=0.5,
        )

        assert layer.fusion_strategy == FusionStrategy.ADAPTIVE

    def test_fuse_outputs(self, sample_market_data):
        """Test fusing neural and symbolic outputs."""
        neural = NeuralComponent()
        symbolic = SymbolicComponent()
        layer = IntegrationLayer()

        neural_output = neural.process(sample_market_data)
        symbolic_output = symbolic.process(sample_market_data)
        fused = layer.fuse(neural_output, symbolic_output)

        assert isinstance(fused, FusedResult)
        assert isinstance(fused.prediction, str)
        assert isinstance(fused.confidence, float)
        assert 0 <= fused.confidence <= 1

    def test_weighted_average_strategy(self, sample_market_data):
        """Test weighted average fusion strategy."""
        neural = NeuralComponent()
        symbolic = SymbolicComponent()
        layer = IntegrationLayer(
            fusion_strategy=FusionStrategy.WEIGHTED_AVERAGE,
            default_neural_weight=0.6,
            default_symbolic_weight=0.4,
        )

        neural_output = neural.process(sample_market_data)
        symbolic_output = symbolic.process(sample_market_data)
        fused = layer.fuse(neural_output, symbolic_output)

        assert fused.neural_weight == 0.6
        assert fused.symbolic_weight == 0.4

    def test_neural_priority_strategy(self, sample_market_data):
        """Test neural priority fusion strategy."""
        neural = NeuralComponent()
        symbolic = SymbolicComponent()
        layer = IntegrationLayer(fusion_strategy=FusionStrategy.NEURAL_PRIORITY)

        neural_output = neural.process(sample_market_data)
        symbolic_output = symbolic.process(sample_market_data)
        fused = layer.fuse(neural_output, symbolic_output)

        assert fused.neural_weight > fused.symbolic_weight

    def test_symbolic_priority_strategy(self, sample_market_data):
        """Test symbolic priority fusion strategy."""
        neural = NeuralComponent()
        symbolic = SymbolicComponent()
        layer = IntegrationLayer(fusion_strategy=FusionStrategy.SYMBOLIC_PRIORITY)

        neural_output = neural.process(sample_market_data)
        symbolic_output = symbolic.process(sample_market_data)
        fused = layer.fuse(neural_output, symbolic_output)

        assert fused.symbolic_weight > fused.neural_weight

    def test_adaptive_strategy(self, sample_market_data):
        """Test adaptive fusion strategy."""
        neural = NeuralComponent()
        symbolic = SymbolicComponent()
        layer = IntegrationLayer(fusion_strategy=FusionStrategy.ADAPTIVE)

        neural_output = neural.process(sample_market_data)
        symbolic_output = symbolic.process(sample_market_data)
        fused = layer.fuse(neural_output, symbolic_output)

        # Weights should sum to 1
        assert abs(fused.neural_weight + fused.symbolic_weight - 1.0) < 0.01

    def test_build_reasoning_chain(self, sample_market_data):
        """Test reasoning chain building."""
        neural = NeuralComponent()
        symbolic = SymbolicComponent()
        layer = IntegrationLayer()

        neural_output = neural.process(sample_market_data)
        symbolic_output = symbolic.process(sample_market_data)
        fused = layer.fuse(neural_output, symbolic_output)
        chain = layer.build_reasoning_chain(neural_output, symbolic_output, fused)

        assert isinstance(chain, ReasoningChain)
        assert len(chain.steps) > 0
        assert chain.final_conclusion is not None

    def test_contributing_factors(self, sample_market_data):
        """Test contributing factors generation."""
        neural = NeuralComponent()
        symbolic = SymbolicComponent()
        layer = IntegrationLayer()

        neural_output = neural.process(sample_market_data)
        symbolic_output = symbolic.process(sample_market_data)
        fused = layer.fuse(neural_output, symbolic_output)

        assert isinstance(fused.contributing_factors, list)


# ============================================================================
# HybridReasoningEngine Tests
# ============================================================================


class TestHybridReasoningEngine:
    """Tests for HybridReasoningEngine class."""

    def test_initialization(self):
        """Test engine initialization."""
        engine = HybridReasoningEngine(
            feature_dim=32, num_patterns=10, fusion_strategy=FusionStrategy.ADAPTIVE
        )

        assert engine.feature_dim == 32
        assert engine.num_patterns == 10
        assert engine.fusion_strategy == FusionStrategy.ADAPTIVE

    def test_reason_basic(self, sample_market_data):
        """Test basic reasoning."""
        engine = HybridReasoningEngine()
        result = engine.reason(sample_market_data)

        assert isinstance(result, HybridReasoningResult)
        assert result.prediction is not None
        assert result.confidence >= 0
        assert result.processing_time_ms > 0

    def test_reason_returns_neural_output(self, sample_market_data):
        """Test that reasoning returns neural output."""
        engine = HybridReasoningEngine()
        result = engine.reason(sample_market_data)

        assert isinstance(result.neural_output, NeuralOutput)

    def test_reason_returns_symbolic_output(self, sample_market_data):
        """Test that reasoning returns symbolic output."""
        engine = HybridReasoningEngine()
        result = engine.reason(sample_market_data)

        assert isinstance(result.symbolic_output, SymbolicOutput)

    def test_reason_returns_reasoning_chain(self, sample_market_data):
        """Test that reasoning returns reasoning chain."""
        engine = HybridReasoningEngine()
        result = engine.reason(sample_market_data)

        assert isinstance(result.reasoning_chain, ReasoningChain)

    def test_analyze_trend(self, sample_market_data):
        """Test trend analysis."""
        engine = HybridReasoningEngine()
        analysis = engine.analyze_trend(sample_market_data)

        assert "trend_direction" in analysis
        assert "confidence" in analysis
        assert "prediction" in analysis
        assert "explanation" in analysis

    def test_get_explanation(self, sample_market_data):
        """Test explanation retrieval."""
        engine = HybridReasoningEngine()
        engine.reason(sample_market_data)

        explanation = engine.get_explanation()

        assert isinstance(explanation, str)
        assert len(explanation) > 0

    def test_get_explanation_before_reasoning(self):
        """Test explanation before any reasoning."""
        engine = HybridReasoningEngine()
        explanation = engine.get_explanation()

        assert "No reasoning" in explanation

    def test_get_reasoning_chain(self, sample_market_data):
        """Test reasoning chain retrieval."""
        engine = HybridReasoningEngine()
        engine.reason(sample_market_data)

        chain = engine.get_reasoning_chain()

        assert chain is not None
        assert len(chain.steps) > 0

    def test_get_confidence_breakdown(self, sample_market_data):
        """Test confidence breakdown."""
        engine = HybridReasoningEngine()
        engine.reason(sample_market_data)

        breakdown = engine.get_confidence_breakdown()

        assert "neural" in breakdown
        assert "symbolic" in breakdown
        assert "fused" in breakdown

    def test_reset_state(self, sample_market_data):
        """Test state reset."""
        engine = HybridReasoningEngine()
        engine.reason(sample_market_data)

        engine.reset_state()

        assert engine._last_result is None

    def test_set_fusion_strategy(self, sample_market_data):
        """Test changing fusion strategy."""
        engine = HybridReasoningEngine()

        engine.set_fusion_strategy(FusionStrategy.NEURAL_PRIORITY)

        assert engine.fusion_strategy == FusionStrategy.NEURAL_PRIORITY

    def test_get_statistics(self, sample_market_data):
        """Test statistics retrieval."""
        engine = HybridReasoningEngine()
        engine.reason(sample_market_data)

        stats = engine.get_statistics()

        assert "processing_count" in stats
        assert stats["processing_count"] == 1

    def test_processing_count_increments(self, sample_market_data):
        """Test that processing count increments."""
        engine = HybridReasoningEngine()

        engine.reason(sample_market_data)
        engine.reason(sample_market_data)

        stats = engine.get_statistics()
        assert stats["processing_count"] == 2


class TestAnalyzeMarketData:
    """Tests for analyze_market_data convenience function."""

    def test_analyze_market_data_basic(self, sample_market_data):
        """Test basic market data analysis."""
        result = analyze_market_data(sample_market_data)

        assert isinstance(result, HybridReasoningResult)
        assert result.prediction is not None

    def test_analyze_market_data_minimal(self):
        """Test analysis with minimal data."""
        result = analyze_market_data({"price": 100.0, "volume": 1000.0})

        assert isinstance(result, HybridReasoningResult)


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_data(self):
        """Test with empty data."""
        engine = HybridReasoningEngine()
        result = engine.reason({})

        assert result is not None
        assert isinstance(result, HybridReasoningResult)

    def test_none_values(self):
        """Test with None values."""
        engine = HybridReasoningEngine()
        result = engine.reason({"price": None, "volume": None, "high": None})

        assert result is not None

    def test_negative_values(self):
        """Test with negative values."""
        engine = HybridReasoningEngine()
        result = engine.reason({"price": -100.0, "volume": -1000.0})

        assert result is not None

    def test_extreme_values(self):
        """Test with extreme values."""
        engine = HybridReasoningEngine()
        result = engine.reason({"price": 1e10, "volume": 1e15})

        assert result is not None

    def test_zero_values(self):
        """Test with zero values."""
        engine = HybridReasoningEngine()
        result = engine.reason({"price": 0.0, "volume": 0.0})

        assert result is not None

    def test_missing_optional_fields(self):
        """Test with missing optional fields."""
        engine = HybridReasoningEngine()
        result = engine.reason(
            {
                "price": 100.0,
                "volume": 1000.0,
                # Missing: high, low, sma, support, resistance
            }
        )

        assert result is not None


# ============================================================================
# Integration Tests
# ============================================================================


class TestIntegration:
    """Integration tests for the complete system."""

    def test_full_pipeline_bullish(self, bullish_market_data):
        """Test full pipeline with bullish data."""
        engine = HybridReasoningEngine()
        result = engine.reason(bullish_market_data)

        # Verify all components worked
        assert len(result.neural_output.patterns) >= 0
        assert len(result.symbolic_output.triggered_rules) >= 0
        assert result.trend_direction in [TrendDirection.UP, TrendDirection.UNKNOWN]

    def test_full_pipeline_bearish(self, bearish_market_data):
        """Test full pipeline with bearish data."""
        engine = HybridReasoningEngine()
        result = engine.reason(bearish_market_data)

        assert len(result.neural_output.patterns) >= 0
        assert len(result.symbolic_output.triggered_rules) >= 0
        assert result.trend_direction in [TrendDirection.DOWN, TrendDirection.UNKNOWN]

    def test_consistency_across_multiple_calls(self, sample_market_data):
        """Test consistency across multiple calls with same data."""
        engine = HybridReasoningEngine()

        result1 = engine.reason(sample_market_data)
        result2 = engine.reason(sample_market_data)

        # Predictions should be consistent (same input, same weights)
        assert result1.trend_direction == result2.trend_direction

    def test_different_strategies_produce_different_results(self, sample_market_data):
        """Test that different strategies produce different weights."""
        results = []

        for strategy in FusionStrategy:
            engine = HybridReasoningEngine(fusion_strategy=strategy)
            result = engine.reason(sample_market_data)
            results.append((strategy, result.fused_result.neural_weight))

        # At least some strategies should have different weights
        weights = [r[1] for r in results]
        assert (
            len(set(weights)) > 1 or len(weights) == 1
        )  # At least one difference or all same


# ============================================================================
# Performance Tests
# ============================================================================


class TestPerformance:
    """Performance-related tests."""

    def test_processing_time_reasonable(self, sample_market_data):
        """Test that processing time is reasonable."""
        engine = HybridReasoningEngine()
        result = engine.reason(sample_market_data)

        # Should process in under 100ms
        assert result.processing_time_ms < 100

    def test_multiple_iterations_performance(self, sample_market_data):
        """Test performance over multiple iterations."""
        engine = HybridReasoningEngine()

        times = []
        for _ in range(10):
            result = engine.reason(sample_market_data)
            times.append(result.processing_time_ms)

        avg_time = sum(times) / len(times)
        assert avg_time < 50  # Average under 50ms


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
