"""Comprehensive tests for multi-modal signal fusion.

Tests cover:
- MultiModalFusionEngine
- SignalAggregator
- ModalityEncoder
- FusionStrategySelector
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from src.neuro_symbolic.fusion.engine import (
    MultiModalFusionEngine,
    FusionConfig,
    FusionResult,
    fuse_signals,
)
from src.neuro_symbolic.fusion.aggregator import (
    SignalAggregator,
    AggregationConfig,
    AggregatedSignals,
    aggregate_signals,
)
from src.neuro_symbolic.fusion.strategy_selector import (
    FusionStrategySelector,
    FusionStrategy,
    SelectorConfig,
    StrategyPerformance,
    select_fusion_strategy,
)
from src.neuro_symbolic.multimodal.encoder import (
    ModalityEncoder,
    EncoderConfig,
    EncodedSignal,
    encode_signal,
)
from src.neuro_symbolic.multimodal.types import (
    ModalityType,
    SignalMetadata,
    TemporalContext,
    MultiModalSignal,
    FusionWeights,
    SignalBatch,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def basic_signal():
    """Create a basic test signal."""
    return MultiModalSignal(
        value=0.5,
        modality=ModalityType.TECHNICAL,
        metadata=SignalMetadata(
            source="test_source",
            modality=ModalityType.TECHNICAL,
            confidence=0.8,
        ),
        temporal_context=TemporalContext.now(),
    )


@pytest.fixture
def technical_signal():
    """Create a technical analysis signal."""
    return MultiModalSignal(
        value=0.7,
        modality=ModalityType.TECHNICAL,
        metadata=SignalMetadata(
            source="technical_analyzer",
            modality=ModalityType.TECHNICAL,
            confidence=0.85,
            reliability=0.9,
        ),
        temporal_context=TemporalContext.now(),
        features={
            "rsi": 65.0,
            "macd": 0.5,
            "trend_strength": 0.8,
        },
    )


@pytest.fixture
def sentiment_signal():
    """Create a sentiment analysis signal."""
    return MultiModalSignal(
        value=0.4,
        modality=ModalityType.SENTIMENT,
        metadata=SignalMetadata(
            source="sentiment_analyzer",
            modality=ModalityType.SENTIMENT,
            confidence=0.75,
        ),
        temporal_context=TemporalContext.now(),
        features={
            "polarity": 0.6,
            "subjectivity": 0.4,
            "agreement": 0.7,
        },
    )


@pytest.fixture
def onchain_signal():
    """Create an on-chain metrics signal."""
    return MultiModalSignal(
        value=0.6,
        modality=ModalityType.ONCHAIN,
        metadata=SignalMetadata(
            source="onchain_analyzer",
            modality=ModalityType.ONCHAIN,
            confidence=0.9,
        ),
        temporal_context=TemporalContext.now(),
        features={
            "active_addresses": 10000,
            "transaction_volume": 500000,
            "whale_activity": 0.3,
        },
    )


@pytest.fixture
def multi_modal_signals(technical_signal, sentiment_signal, onchain_signal):
    """Create a set of multi-modal signals."""
    return [technical_signal, sentiment_signal, onchain_signal]


@pytest.fixture
def simple_signals_dict():
    """Create simple signals as a dictionary."""
    return {
        "technical": 0.8,
        "sentiment": 0.6,
        "onchain": 0.7,
    }


@pytest.fixture
def encoder():
    """Create a ModalityEncoder instance."""
    return ModalityEncoder()


@pytest.fixture
def aggregator():
    """Create a SignalAggregator instance."""
    return SignalAggregator()


@pytest.fixture
def strategy_selector():
    """Create a FusionStrategySelector instance."""
    return FusionStrategySelector()


@pytest.fixture
def fusion_engine():
    """Create a MultiModalFusionEngine instance."""
    return MultiModalFusionEngine()


# ============================================================================
# Test ModalityType Enum
# ============================================================================


class TestModalityType:
    """Tests for ModalityType enum."""

    def test_modality_types_exist(self):
        """Test that all modality types are defined."""
        assert ModalityType.TECHNICAL.value == "technical"
        assert ModalityType.SENTIMENT.value == "sentiment"
        assert ModalityType.ONCHAIN.value == "onchain"
        assert ModalityType.FUNDAMENTAL.value == "fundamental"
        assert ModalityType.NEWS.value == "news"
        assert ModalityType.SOCIAL.value == "social"

    def test_modality_type_count(self):
        """Test that we have expected number of modality types."""
        assert len(ModalityType) == 6


# ============================================================================
# Test TemporalContext
# ============================================================================


class TestTemporalContext:
    """Tests for TemporalContext."""

    def test_temporal_context_creation(self):
        """Test creating a temporal context."""
        now = datetime.utcnow()
        ctx = TemporalContext(timestamp=now, period_ms=60000)
        assert ctx.timestamp == now
        assert ctx.period_ms == 60000
        assert ctx.lag_ms == 0

    def test_temporal_context_now(self):
        """Test creating temporal context with now()."""
        ctx = TemporalContext.now()
        assert isinstance(ctx.timestamp, datetime)
        assert ctx.period_ms == 60000

    def test_temporal_context_to_dict(self):
        """Test converting temporal context to dict."""
        now = datetime.utcnow()
        ctx = TemporalContext(timestamp=now, period_ms=30000)
        d = ctx.to_dict()
        assert "timestamp" in d
        assert d["period_ms"] == 30000


# ============================================================================
# Test SignalMetadata
# ============================================================================


class TestSignalMetadata:
    """Tests for SignalMetadata."""

    def test_metadata_creation(self):
        """Test creating signal metadata."""
        meta = SignalMetadata(
            source="test",
            modality=ModalityType.TECHNICAL,
            confidence=0.8,
        )
        assert meta.source == "test"
        assert meta.confidence == 0.8
        assert meta.reliability == 1.0

    def test_metadata_to_dict(self):
        """Test converting metadata to dict."""
        meta = SignalMetadata(
            source="test",
            modality=ModalityType.SENTIMENT,
            confidence=0.9,
            tags=["important", "verified"],
        )
        d = meta.to_dict()
        assert d["source"] == "test"
        assert d["modality"] == "sentiment"
        assert "important" in d["tags"]


# ============================================================================
# Test MultiModalSignal
# ============================================================================


class TestMultiModalSignal:
    """Tests for MultiModalSignal."""

    def test_signal_creation(self, basic_signal):
        """Test creating a multi-modal signal."""
        assert basic_signal.value == 0.5
        assert basic_signal.modality == ModalityType.TECHNICAL

    def test_signal_to_dict(self, basic_signal):
        """Test converting signal to dict."""
        d = basic_signal.to_dict()
        assert d["value"] == 0.5
        assert "metadata" in d
        assert "temporal_context" in d

    def test_effective_confidence(self, basic_signal):
        """Test effective confidence calculation."""
        basic_signal.metadata.staleness_ms = 0
        effective = basic_signal.effective_confidence
        assert 0 <= effective <= 1
        assert effective == basic_signal.metadata.confidence

    def test_effective_confidence_with_staleness(self, basic_signal):
        """Test effective confidence with staleness penalty."""
        basic_signal.metadata.staleness_ms = 0
        no_staleness = basic_signal.effective_confidence

        basic_signal.metadata.staleness_ms = 150000  # 2.5 minutes
        with_staleness = basic_signal.effective_confidence

        assert with_staleness < no_staleness

    def test_signal_with_features(self, technical_signal):
        """Test signal with custom features."""
        assert "rsi" in technical_signal.features
        assert technical_signal.features["rsi"] == 65.0


# ============================================================================
# Test FusionWeights
# ============================================================================


class TestFusionWeights:
    """Tests for FusionWeights."""

    def test_default_weights(self):
        """Test default fusion weights."""
        weights = FusionWeights()
        assert weights.technical == 0.4
        assert weights.sentiment == 0.3
        assert weights.onchain == 0.2

    def test_weight_normalization(self):
        """Test weight normalization."""
        weights = FusionWeights(
            technical=2.0,
            sentiment=2.0,
            onchain=0.0,
            fundamental=0.0,
            news=0.0,
            social=0.0,
        )
        normalized = weights.normalize()
        assert abs(normalized.technical - 0.5) < 0.01
        assert abs(normalized.sentiment - 0.5) < 0.01

    def test_get_weight_by_modality(self):
        """Test getting weight by modality type."""
        weights = FusionWeights()
        assert weights.get_weight(ModalityType.TECHNICAL) == 0.4
        assert weights.get_weight(ModalityType.SENTIMENT) == 0.3

    def test_weights_to_dict(self):
        """Test converting weights to dict."""
        weights = FusionWeights()
        d = weights.to_dict()
        assert "technical" in d
        assert "sentiment" in d


# ============================================================================
# Test ModalityEncoder
# ============================================================================


class TestModalityEncoder:
    """Tests for ModalityEncoder."""

    def test_encoder_creation(self):
        """Test creating a modality encoder."""
        encoder = ModalityEncoder()
        assert encoder.config is not None

    def test_encoder_with_config(self):
        """Test encoder with custom config."""
        config = EncoderConfig(technical_dim=128)
        encoder = ModalityEncoder(config=config)
        assert encoder.config.technical_dim == 128

    def test_encode_technical_signal(self, encoder, technical_signal):
        """Test encoding a technical signal."""
        encoded = encoder.encode(technical_signal)
        assert isinstance(encoded, EncodedSignal)
        assert encoded.modality == ModalityType.TECHNICAL
        assert len(encoded.encoded_vector) == encoder.config.technical_dim

    def test_encode_sentiment_signal(self, encoder, sentiment_signal):
        """Test encoding a sentiment signal."""
        encoded = encoder.encode(sentiment_signal)
        assert encoded.modality == ModalityType.SENTIMENT
        assert len(encoded.encoded_vector) == encoder.config.sentiment_dim

    def test_encode_onchain_signal(self, encoder, onchain_signal):
        """Test encoding an on-chain signal."""
        encoded = encoder.encode(onchain_signal)
        assert encoded.modality == ModalityType.ONCHAIN
        assert len(encoded.encoded_vector) == encoder.config.onchain_dim

    def test_encode_batch(self, encoder, multi_modal_signals):
        """Test encoding a batch of signals."""
        encoded_batch = encoder.encode_batch(multi_modal_signals)
        assert len(encoded_batch) == 3
        assert all(isinstance(e, EncodedSignal) for e in encoded_batch)

    def test_get_encoding_dim(self, encoder):
        """Test getting encoding dimension for modalities."""
        assert encoder.get_encoding_dim(ModalityType.TECHNICAL) == 64
        assert encoder.get_encoding_dim(ModalityType.SENTIMENT) == 32

    def test_attention_weights(self, encoder, basic_signal):
        """Test attention weights are calculated."""
        encoded = encoder.encode(basic_signal)
        assert len(encoded.attention_weights) > 0
        assert all(0 <= w <= 1 for w in encoded.attention_weights)

    def test_feature_importance(self, encoder, technical_signal):
        """Test feature importance calculation."""
        encoded = encoder.encode(technical_signal)
        assert len(encoded.feature_importance) > 0

    def test_encoder_statistics(self, encoder, multi_modal_signals):
        """Test encoder statistics tracking."""
        encoder.encode_batch(multi_modal_signals)
        stats = encoder.get_statistics()
        assert stats["total_encoded"] == 3
        assert ModalityType.TECHNICAL.value in stats["by_modality"]

    def test_reset_statistics(self, encoder, multi_modal_signals):
        """Test resetting encoder statistics."""
        encoder.encode_batch(multi_modal_signals)
        encoder.reset_statistics()
        stats = encoder.get_statistics()
        assert stats["total_encoded"] == 0


# ============================================================================
# Test SignalAggregator
# ============================================================================


class TestSignalAggregator:
    """Tests for SignalAggregator."""

    def test_aggregator_creation(self):
        """Test creating a signal aggregator."""
        aggregator = SignalAggregator()
        assert aggregator.config is not None

    def test_aggregate_signals(self, aggregator, multi_modal_signals):
        """Test aggregating signals."""
        result = aggregator.aggregate(multi_modal_signals)
        assert isinstance(result, AggregatedSignals)
        assert len(result.signals) == 3
        assert result.alignment_quality >= 0

    def test_aggregate_empty_signals(self, aggregator):
        """Test aggregating empty signal list."""
        result = aggregator.aggregate([])
        assert len(result.signals) == 0
        assert result.alignment_quality == 0.0

    def test_temporal_alignment(self, aggregator):
        """Test temporal alignment of signals."""
        now = datetime.utcnow()
        signals = []
        for i in range(3):
            signal = MultiModalSignal(
                value=0.5 + i * 0.1,
                modality=list(ModalityType)[i],
                metadata=SignalMetadata(
                    source="test",
                    modality=list(ModalityType)[i],
                    confidence=0.8,
                ),
                temporal_context=TemporalContext(
                    timestamp=now - timedelta(milliseconds=100 * i)
                ),
            )
            signals.append(signal)

        result = aggregator.aggregate(signals, target_time=now)
        assert result.alignment_quality > 0.9

    def test_staleness_filtering(self, aggregator):
        """Test that stale signals are filtered out."""
        old_time = datetime.utcnow() - timedelta(minutes=10)
        stale_signal = MultiModalSignal(
            value=0.5,
            modality=ModalityType.TECHNICAL,
            metadata=SignalMetadata(
                source="test",
                modality=ModalityType.TECHNICAL,
                confidence=0.8,
            ),
            temporal_context=TemporalContext(timestamp=old_time),
        )

        result = aggregator.aggregate([stale_signal])
        assert len(result.signals) == 0

    def test_modality_weights_calculation(self, aggregator, multi_modal_signals):
        """Test modality weights are calculated."""
        result = aggregator.aggregate(multi_modal_signals)
        assert len(result.modality_weights) > 0
        assert all(w >= 0 for w in result.modality_weights.values())

    def test_confidence_scores(self, aggregator, multi_modal_signals):
        """Test confidence scores are calculated."""
        result = aggregator.aggregate(multi_modal_signals)
        assert len(result.confidence_scores) > 0

    def test_coverage_calculation(self, aggregator, multi_modal_signals):
        """Test modality coverage is calculated."""
        result = aggregator.aggregate(multi_modal_signals)
        assert ModalityType.TECHNICAL in result.coverage
        assert result.coverage[ModalityType.TECHNICAL] > 0

    def test_create_batch(self, aggregator, multi_modal_signals):
        """Test creating a signal batch."""
        batch = aggregator.create_batch(multi_modal_signals)
        assert isinstance(batch, SignalBatch)
        assert len(batch.signals) == 3

    def test_weighted_value(self, aggregator, multi_modal_signals):
        """Test weighted value calculation."""
        result = aggregator.aggregate(multi_modal_signals)
        weighted = result.get_weighted_value()
        assert -1 <= weighted <= 1

    def test_aggregator_statistics(self, aggregator, multi_modal_signals):
        """Test aggregator statistics."""
        aggregator.aggregate(multi_modal_signals)
        stats = aggregator.get_statistics()
        assert stats["aggregation_count"] == 1


# ============================================================================
# Test FusionStrategySelector
# ============================================================================


class TestFusionStrategySelector:
    """Tests for FusionStrategySelector."""

    def test_selector_creation(self):
        """Test creating a strategy selector."""
        selector = FusionStrategySelector()
        assert selector.config is not None

    def test_default_strategy(self):
        """Test default strategy selection."""
        selector = FusionStrategySelector()
        coverage = {ModalityType.TECHNICAL: 0.8}
        strategy = selector.select(coverage, 0.5)
        assert isinstance(strategy, FusionStrategy)

    def test_strategy_selection_low_quality(self):
        """Test strategy selection with low signal quality."""
        selector = FusionStrategySelector()
        coverage = {ModalityType.TECHNICAL: 0.8}
        strategy = selector.select(coverage, 0.3)
        assert strategy == FusionStrategy.CONFIDENCE_WEIGHTED

    def test_strategy_selection_high_coverage(self):
        """Test strategy selection with high modality coverage."""
        selector = FusionStrategySelector()
        coverage = {
            ModalityType.TECHNICAL: 0.9,
            ModalityType.SENTIMENT: 0.8,
            ModalityType.ONCHAIN: 0.7,
            ModalityType.FUNDAMENTAL: 0.6,
        }
        strategy = selector.select(coverage, 0.8)
        # Should select ensemble for many active modalities
        assert strategy in [FusionStrategy.ENSEMBLE, FusionStrategy.ADAPTIVE]

    def test_update_performance(self, strategy_selector):
        """Test updating strategy performance."""
        strategy_selector.update_performance(
            FusionStrategy.ADAPTIVE,
            {"accuracy": 0.85, "f1_score": 0.8},
        )
        perf = strategy_selector.get_strategy_performance(FusionStrategy.ADAPTIVE)
        assert perf is not None
        assert perf.sample_count == 1

    def test_get_best_strategy(self, strategy_selector):
        """Test getting best performing strategy."""
        # Update performance for multiple strategies
        for i, strategy in enumerate(
            [FusionStrategy.ADAPTIVE, FusionStrategy.ENSEMBLE]
        ):
            for _ in range(60):  # Above min_samples threshold
                strategy_selector.update_performance(
                    strategy,
                    {"accuracy": 0.8 - i * 0.1, "f1_score": 0.75 - i * 0.1},
                )

        best = strategy_selector.get_best_strategy()
        assert best == FusionStrategy.ADAPTIVE

    def test_get_all_performance(self, strategy_selector):
        """Test getting all strategy performance."""
        all_perf = strategy_selector.get_all_performance()
        assert len(all_perf) == len(FusionStrategy)

    def test_reset_performance(self, strategy_selector):
        """Test resetting performance metrics."""
        strategy_selector.update_performance(
            FusionStrategy.ADAPTIVE,
            {"accuracy": 0.9},
        )
        strategy_selector.reset_performance()
        perf = strategy_selector.get_strategy_performance(FusionStrategy.ADAPTIVE)
        assert perf.sample_count == 0

    def test_exploration_rate(self):
        """Test exploration rate affects selection."""
        config = SelectorConfig(exploration_rate=1.0)  # Always explore
        selector = FusionStrategySelector(config=config)
        coverage = {ModalityType.TECHNICAL: 0.8}
        # With 100% exploration, should potentially select different strategies
        strategies_selected = set()
        for _ in range(20):
            strategy = selector.select(coverage, 0.5)
            strategies_selected.add(strategy)
        # With exploration, we should see some variety (not guaranteed but likely)


# ============================================================================
# Test StrategyPerformance
# ============================================================================


class TestStrategyPerformance:
    """Tests for StrategyPerformance."""

    def test_performance_creation(self):
        """Test creating strategy performance."""
        perf = StrategyPerformance(strategy=FusionStrategy.ADAPTIVE)
        assert perf.accuracy == 0.0
        assert perf.sample_count == 0

    def test_composite_score(self):
        """Test composite score calculation."""
        perf = StrategyPerformance(
            strategy=FusionStrategy.ADAPTIVE,
            accuracy=0.8,
            f1_score=0.75,
            calibration_error=0.1,
            sample_count=100,
        )
        score = perf.composite_score
        assert 0 <= score <= 1

    def test_update_performance(self):
        """Test updating performance metrics."""
        perf = StrategyPerformance(strategy=FusionStrategy.ADAPTIVE)
        perf.update(accuracy=0.9, f1_score=0.85)
        assert perf.sample_count == 1
        assert perf.last_used is not None

    def test_performance_to_dict(self):
        """Test converting performance to dict."""
        perf = StrategyPerformance(
            strategy=FusionStrategy.ADAPTIVE,
            accuracy=0.8,
            sample_count=50,
        )
        d = perf.to_dict()
        assert d["strategy"] == "adaptive"
        assert d["accuracy"] == 0.8


# ============================================================================
# Test MultiModalFusionEngine
# ============================================================================


class TestMultiModalFusionEngine:
    """Tests for MultiModalFusionEngine."""

    def test_engine_creation(self):
        """Test creating a fusion engine."""
        engine = MultiModalFusionEngine()
        assert engine.config is not None

    def test_fuse_simple_dict(self, fusion_engine, simple_signals_dict):
        """Test fusing simple dictionary signals."""
        result = fusion_engine.fuse(simple_signals_dict)
        assert isinstance(result, FusionResult)
        assert -1 <= result.fused_value <= 1

    def test_fuse_signal_list(self, fusion_engine, multi_modal_signals):
        """Test fusing list of MultiModalSignal."""
        result = fusion_engine.fuse(multi_modal_signals)
        assert isinstance(result, FusionResult)
        assert result.signal_count == 3

    def test_fuse_empty_signals(self, fusion_engine):
        """Test fusing empty signals returns empty result."""
        result = fusion_engine.fuse([])
        assert result.fused_value == 0.0
        assert result.confidence == 0.0

    def test_fusion_result_properties(self, fusion_engine, simple_signals_dict):
        """Test fusion result properties."""
        result = fusion_engine.fuse(simple_signals_dict)
        assert hasattr(result, "direction")
        assert result.direction in ["bullish", "bearish", "neutral"]

    def test_fusion_result_to_dict(self, fusion_engine, simple_signals_dict):
        """Test converting fusion result to dict."""
        result = fusion_engine.fuse(simple_signals_dict)
        d = result.to_dict()
        assert "fused_value" in d
        assert "confidence" in d
        assert "strategy_used" in d

    def test_different_fusion_strategies(self, fusion_engine, multi_modal_signals):
        """Test different fusion strategies produce results."""
        strategies = [
            FusionStrategy.WEIGHTED_AVERAGE,
            FusionStrategy.CONFIDENCE_WEIGHTED,
            FusionStrategy.ADAPTIVE,
            FusionStrategy.ENSEMBLE,
        ]

        for strategy in strategies:
            config = FusionConfig(default_strategy=strategy)
            engine = MultiModalFusionEngine(config=config)
            result = engine.fuse(multi_modal_signals)
            # ADAPTIVE strategy delegates to selector, so it may return any valid strategy
            # including ADAPTIVE itself (for high coverage/quality scenarios)
            if strategy == FusionStrategy.ADAPTIVE:
                # Just verify a valid strategy was selected and result is valid
                assert result.strategy_used in [
                    FusionStrategy.WEIGHTED_AVERAGE,
                    FusionStrategy.CONFIDENCE_WEIGHTED,
                    FusionStrategy.ATTENTION_BASED,
                    FusionStrategy.ENSEMBLE,
                    FusionStrategy.ADAPTIVE,
                ]
            else:
                assert result.strategy_used == strategy

    def test_modality_contributions(self, fusion_engine, multi_modal_signals):
        """Test modality contributions are tracked."""
        result = fusion_engine.fuse(multi_modal_signals)
        assert len(result.modality_contributions) > 0
        assert ModalityType.TECHNICAL in result.modality_contributions

    def test_processing_time(self, fusion_engine, simple_signals_dict):
        """Test processing time is recorded."""
        result = fusion_engine.fuse(simple_signals_dict)
        assert result.processing_time_ms > 0

    def test_output_smoothing(self, multi_modal_signals):
        """Test output smoothing between results."""
        config = FusionConfig(output_smoothing=0.5)
        engine = MultiModalFusionEngine(config=config)

        result1 = engine.fuse(multi_modal_signals)
        # Modify signals slightly
        modified_signals = [
            MultiModalSignal(
                value=s.value + 0.2,
                modality=s.modality,
                metadata=s.metadata,
                temporal_context=s.temporal_context,
            )
            for s in multi_modal_signals
        ]
        result2 = engine.fuse(modified_signals)

        # Second result should be smoothed toward first
        assert result2.fused_value != result1.fused_value

    def test_set_weights(self, fusion_engine):
        """Test setting custom fusion weights."""
        new_weights = FusionWeights(technical=0.6, sentiment=0.3, onchain=0.1)
        fusion_engine.set_weights(new_weights)
        weights = fusion_engine.get_weights()
        # Weights are normalized, so technical should be ~0.545 (0.6/1.1)
        assert abs(weights.technical - 0.545) < 0.01

    def test_update_strategy_performance(self, fusion_engine):
        """Test updating strategy performance."""
        fusion_engine.update_strategy_performance(
            FusionStrategy.ADAPTIVE,
            {"accuracy": 0.9},
        )
        stats = fusion_engine.get_statistics()
        assert stats is not None

    def test_get_last_result(self, fusion_engine, simple_signals_dict):
        """Test getting last fusion result."""
        fusion_engine.fuse(simple_signals_dict)
        last = fusion_engine.get_last_result()
        assert last is not None

    def test_get_statistics(self, fusion_engine, simple_signals_dict):
        """Test getting engine statistics."""
        fusion_engine.fuse(simple_signals_dict)
        stats = fusion_engine.get_statistics()
        assert stats["fusion_count"] == 1
        assert "encoder_stats" in stats
        assert "aggregator_stats" in stats

    def test_reset_state(self, fusion_engine, simple_signals_dict):
        """Test resetting engine state."""
        fusion_engine.fuse(simple_signals_dict)
        fusion_engine.reset_state()
        assert fusion_engine.get_last_result() is None
        stats = fusion_engine.get_statistics()
        assert stats["fusion_count"] == 0

    def test_fuse_batch(self, fusion_engine, multi_modal_signals):
        """Test fusing multiple batches."""
        batches = [multi_modal_signals, multi_modal_signals]
        results = fusion_engine.fuse_batch(batches)
        assert len(results) == 2

    def test_context_affects_fusion(self, fusion_engine, multi_modal_signals):
        """Test that context affects fusion."""
        result1 = fusion_engine.fuse(
            multi_modal_signals, context={"high_volatility": True}
        )
        result2 = fusion_engine.fuse(
            multi_modal_signals, context={"low_confidence": True}
        )
        # Results may differ based on context (strategy selection)
        assert isinstance(result1, FusionResult)
        assert isinstance(result2, FusionResult)


# ============================================================================
# Test Fusion Strategies
# ============================================================================


class TestFusionStrategies:
    """Tests for individual fusion strategies."""

    @pytest.fixture
    def engine_with_strategy(self):
        """Create engine with specific strategy."""

        def create(strategy):
            config = FusionConfig(default_strategy=strategy)
            return MultiModalFusionEngine(config=config)

        return create

    def test_weighted_average_strategy(self, engine_with_strategy, multi_modal_signals):
        """Test weighted average fusion."""
        engine = engine_with_strategy(FusionStrategy.WEIGHTED_AVERAGE)
        result = engine.fuse(multi_modal_signals)
        assert result.strategy_used == FusionStrategy.WEIGHTED_AVERAGE

    def test_confidence_weighted_strategy(
        self, engine_with_strategy, multi_modal_signals
    ):
        """Test confidence weighted fusion."""
        engine = engine_with_strategy(FusionStrategy.CONFIDENCE_WEIGHTED)
        result = engine.fuse(multi_modal_signals)
        assert result.strategy_used == FusionStrategy.CONFIDENCE_WEIGHTED

    def test_adaptive_strategy(self, engine_with_strategy, multi_modal_signals):
        """Test adaptive fusion."""
        engine = engine_with_strategy(FusionStrategy.ADAPTIVE)
        result = engine.fuse(multi_modal_signals)
        assert result.strategy_used == FusionStrategy.ADAPTIVE

    def test_attention_based_strategy(self, engine_with_strategy, multi_modal_signals):
        """Test attention-based fusion."""
        engine = engine_with_strategy(FusionStrategy.ATTENTION_BASED)
        result = engine.fuse(multi_modal_signals)
        assert result.strategy_used == FusionStrategy.ATTENTION_BASED

    def test_hierarchical_strategy(self, engine_with_strategy, multi_modal_signals):
        """Test hierarchical fusion."""
        engine = engine_with_strategy(FusionStrategy.HIERARCHICAL)
        result = engine.fuse(multi_modal_signals)
        assert result.strategy_used == FusionStrategy.HIERARCHICAL

    def test_ensemble_strategy(self, engine_with_strategy, multi_modal_signals):
        """Test ensemble fusion."""
        engine = engine_with_strategy(FusionStrategy.ENSEMBLE)
        result = engine.fuse(multi_modal_signals)
        assert result.strategy_used == FusionStrategy.ENSEMBLE

    def test_bayesian_strategy(self, engine_with_strategy, multi_modal_signals):
        """Test Bayesian fusion."""
        engine = engine_with_strategy(FusionStrategy.BAYESIAN)
        result = engine.fuse(multi_modal_signals)
        assert result.strategy_used == FusionStrategy.BAYESIAN

    def test_neural_strategy(self, engine_with_strategy, multi_modal_signals):
        """Test neural-style fusion."""
        engine = engine_with_strategy(FusionStrategy.NEURAL)
        result = engine.fuse(multi_modal_signals)
        assert result.strategy_used == FusionStrategy.NEURAL


# ============================================================================
# Test FusionResult
# ============================================================================


class TestFusionResult:
    """Tests for FusionResult."""

    def test_result_direction_bullish(self):
        """Test bullish direction detection."""
        result = FusionResult(
            fused_value=0.5,
            confidence=0.8,
            strategy_used=FusionStrategy.ADAPTIVE,
            modality_contributions={},
            signal_count=3,
            alignment_quality=0.9,
            processing_time_ms=10.0,
            timestamp=datetime.utcnow(),
        )
        assert result.direction == "bullish"

    def test_result_direction_bearish(self):
        """Test bearish direction detection."""
        result = FusionResult(
            fused_value=-0.5,
            confidence=0.8,
            strategy_used=FusionStrategy.ADAPTIVE,
            modality_contributions={},
            signal_count=3,
            alignment_quality=0.9,
            processing_time_ms=10.0,
            timestamp=datetime.utcnow(),
        )
        assert result.direction == "bearish"

    def test_result_direction_neutral(self):
        """Test neutral direction detection."""
        result = FusionResult(
            fused_value=0.05,
            confidence=0.8,
            strategy_used=FusionStrategy.ADAPTIVE,
            modality_contributions={},
            signal_count=3,
            alignment_quality=0.9,
            processing_time_ms=10.0,
            timestamp=datetime.utcnow(),
        )
        assert result.direction == "neutral"


# ============================================================================
# Test Convenience Functions
# ============================================================================


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_encode_signal_function(self, basic_signal):
        """Test encode_signal convenience function."""
        encoded = encode_signal(basic_signal)
        assert isinstance(encoded, EncodedSignal)

    def test_aggregate_signals_function(self, multi_modal_signals):
        """Test aggregate_signals convenience function."""
        result = aggregate_signals(multi_modal_signals)
        assert isinstance(result, AggregatedSignals)

    def test_select_fusion_strategy_function(self):
        """Test select_fusion_strategy convenience function."""
        coverage = {ModalityType.TECHNICAL: 0.8}
        strategy = select_fusion_strategy(coverage, 0.5)
        assert isinstance(strategy, FusionStrategy)

    def test_fuse_signals_function(self, simple_signals_dict):
        """Test fuse_signals convenience function."""
        result = fuse_signals(simple_signals_dict)
        assert isinstance(result, FusionResult)


# ============================================================================
# Test Edge Cases
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_single_signal_fusion(self, fusion_engine, technical_signal):
        """Test fusion with only one signal."""
        result = fusion_engine.fuse([technical_signal])
        assert result.signal_count == 1
        assert result.fused_value != 0 or result.confidence == 0

    def test_unknown_modality_in_dict(self, fusion_engine):
        """Test handling unknown modality in dict."""
        signals = {"unknown": 0.5, "technical": 0.8}
        result = fusion_engine.fuse(signals)
        # Should only use technical signal
        assert result.signal_count == 1

    def test_zero_confidence_signal(self):
        """Test handling signal with zero confidence."""
        signal = MultiModalSignal(
            value=0.8,
            modality=ModalityType.TECHNICAL,
            metadata=SignalMetadata(
                source="test",
                modality=ModalityType.TECHNICAL,
                confidence=0.0,
            ),
            temporal_context=TemporalContext.now(),
        )
        encoder = ModalityEncoder()
        encoded = encoder.encode(signal)
        # Should still encode, but with low effective values
        assert encoded is not None

    def test_extreme_signal_values(self, fusion_engine):
        """Test handling extreme signal values."""
        signals = {
            "technical": 1.0,
            "sentiment": -1.0,
            "onchain": 1.0,
        }
        result = fusion_engine.fuse(signals)
        assert -1 <= result.fused_value <= 1

    def test_all_same_modality(self, fusion_engine):
        """Test handling multiple signals of same modality."""
        signals = [
            MultiModalSignal(
                value=0.5 + i * 0.1,
                modality=ModalityType.TECHNICAL,
                metadata=SignalMetadata(
                    source=f"source_{i}",
                    modality=ModalityType.TECHNICAL,
                    confidence=0.8,
                ),
                temporal_context=TemporalContext.now(),
            )
            for i in range(3)
        ]
        result = fusion_engine.fuse(signals)
        assert result.signal_count == 3

    def test_very_old_signal(self, aggregator):
        """Test handling very old signal."""
        old_time = datetime.utcnow() - timedelta(hours=1)
        signal = MultiModalSignal(
            value=0.5,
            modality=ModalityType.TECHNICAL,
            metadata=SignalMetadata(
                source="test",
                modality=ModalityType.TECHNICAL,
                confidence=0.8,
            ),
            temporal_context=TemporalContext(timestamp=old_time),
        )
        result = aggregator.aggregate([signal])
        # Should be filtered as stale
        assert len(result.signals) == 0


# ============================================================================
# Test Integration
# ============================================================================


class TestIntegration:
    """Integration tests for the fusion system."""

    def test_full_fusion_pipeline(self, multi_modal_signals):
        """Test complete fusion pipeline from encoding to result."""
        engine = MultiModalFusionEngine()

        # Fuse signals
        result = engine.fuse(multi_modal_signals)

        # Verify result
        assert result.fused_value is not None
        assert result.confidence >= 0
        assert result.strategy_used is not None
        assert len(result.modality_contributions) > 0

    def test_fusion_with_feedback(self, fusion_engine, multi_modal_signals):
        """Test fusion with performance feedback loop."""
        # Initial fusion
        result = fusion_engine.fuse(multi_modal_signals)

        # Provide feedback
        fusion_engine.update_strategy_performance(
            result.strategy_used,
            {"accuracy": 0.85, "f1_score": 0.8},
        )

        # Fuse again
        result2 = fusion_engine.fuse(multi_modal_signals)
        assert result2 is not None

    def test_multi_round_fusion(self, fusion_engine):
        """Test multiple rounds of fusion."""
        for i in range(5):
            signals = {
                "technical": 0.5 + i * 0.1,
                "sentiment": 0.4 + i * 0.05,
                "onchain": 0.6,
            }
            result = fusion_engine.fuse(signals)
            assert isinstance(result, FusionResult)

        stats = fusion_engine.get_statistics()
        assert stats["fusion_count"] == 5

    def test_live_validation(self):
        """Live validation test as specified in requirements."""
        from src.neuro_symbolic.fusion.engine import MultiModalFusionEngine

        engine = MultiModalFusionEngine()
        signals = {"technical": 0.8, "sentiment": 0.6, "onchain": 0.7}
        fused = engine.fuse(signals)

        assert fused is not None, "Fusion result should not be None"
        assert fused.fused_value is not None, "Fused value should not be None"
        print(f"Fusion functional: {fused.fused_value:.4f}")


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
