"""Unit tests for training pipeline module.

Tests TrainingPipeline and related components.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, "/home/tacopants/projects/ChiseAI/src")

from market_analysis.signal_storage.models import (
    OutcomeRecord,
    OutcomeType,
    SignalDirection,
    SignalRecord,
    SignalWithOutcome,
)
from ml.training.extractor import (
    ExtractedFeatures,
    FeatureExtractor,
    MarketContext,
    TechnicalIndicators,
)
from ml.training.pipeline import (
    PipelineConfig,
    PipelineStats,
    TrainingPipeline,
)
from ml.training.schema import TrainingSample


class TestPipelineStats:
    """Tests for PipelineStats dataclass."""

    def test_default_creation(self):
        """Test creating stats with defaults."""
        stats = PipelineStats()
        assert stats.total_signals == 0
        assert stats.successful == 0
        assert stats.failed == 0
        assert stats.skipped == 0
        assert stats.processing_time_ms == 0.0
        assert stats.batch_count == 0

    def test_success_rate_calculation(self):
        """Test success rate calculation."""
        stats = PipelineStats(total_signals=100, successful=85)
        assert stats.success_rate == 85.0

    def test_success_rate_zero_division(self):
        """Test success rate with zero signals."""
        stats = PipelineStats()
        assert stats.success_rate == 0.0

    def test_avg_time_per_signal(self):
        """Test average time calculation."""
        stats = PipelineStats(total_signals=100, processing_time_ms=5000.0)
        assert stats.avg_time_per_signal_ms == 50.0

    def test_to_dict(self):
        """Test conversion to dictionary."""
        stats = PipelineStats(
            total_signals=100,
            successful=85,
            failed=10,
            skipped=5,
            processing_time_ms=5000.0,
            batch_count=5,
        )
        result = stats.to_dict()
        assert result["total_signals"] == 100
        assert result["successful"] == 85
        assert result["success_rate_pct"] == 85.0
        assert result["avg_time_per_signal_ms"] == 50.0


class TestPipelineConfig:
    """Tests for PipelineConfig dataclass."""

    def test_default_creation(self):
        """Test creating config with defaults."""
        config = PipelineConfig()
        assert config.batch_size == 100
        assert config.max_concurrent == 10
        assert config.cache_enabled is True
        assert config.default_outcome_window == timedelta(hours=24)
        assert config.skip_on_missing_data is True
        assert config.enrichment_enabled is True

    def test_custom_config(self):
        """Test creating config with custom values."""
        config = PipelineConfig(
            batch_size=50,
            max_concurrent=5,
            cache_enabled=False,
            default_outcome_window=timedelta(hours=12),
            skip_on_missing_data=False,
            enrichment_enabled=False,
        )
        assert config.batch_size == 50
        assert config.max_concurrent == 5
        assert config.cache_enabled is False


class TestTrainingPipeline:
    """Tests for TrainingPipeline class."""

    @pytest.fixture
    def mock_extractor(self):
        """Create mock feature extractor."""
        extractor = MagicMock(spec=FeatureExtractor)
        extractor.extract_features = AsyncMock()
        return extractor

    @pytest.fixture
    def mock_storage(self):
        """Create mock signal storage."""
        storage = MagicMock()
        storage.get_signal_by_id = AsyncMock()
        storage.get_outcome_by_signal_id = AsyncMock()
        storage.query_signals_with_outcomes = AsyncMock()
        return storage

    @pytest.fixture
    def sample_features(self):
        """Create sample extracted features."""
        return ExtractedFeatures(
            signal_id="test-sig-001",
            timestamp=datetime.now(),
            token="BTC",
            timeframe="1h",
            direction="long",
            confidence=0.85,
            entry_price=45000.0,
            technical=TechnicalIndicators(rsi=65.5, macd=0.5),
            market=MarketContext(trend_state="bullish", confluence_score=75.0),
            predicted_prob=0.85,
        )

    @pytest.fixture
    def sample_outcome(self):
        """Create sample outcome record."""
        return OutcomeRecord(
            signal_id="test-sig-001",
            exit_timestamp=int(datetime.now().timestamp() * 1000) + 86400000,
            is_win=True,
            pnl=500.0,
            exit_price=45500.0,
            duration_hours=24.0,
            outcome_type=OutcomeType.TP_HIT,
        )

    @pytest.mark.asyncio
    async def test_process_signal_success(self, mock_extractor, sample_features):
        """Test successful signal processing."""
        mock_extractor.extract_features.return_value = sample_features

        pipeline = TrainingPipeline(extractor=mock_extractor)
        result = await pipeline.process_signal("test-sig-001")

        assert result is not None
        assert result.sample_id == "test-sig-001"
        assert result.token == "BTC"
        assert result.timeframe == "1h"
        assert result.rsi == 65.5
        assert result.macd == 0.5
        assert result.trend_state == "bullish"
        assert result.confluence_score == 75.0
        assert result.confidence == 0.85
        assert result.confidence_bin == 8  # 0.85 * 10 = 8.5 -> 8

    @pytest.mark.asyncio
    async def test_process_signal_no_features(self, mock_extractor):
        """Test processing when feature extraction fails."""
        mock_extractor.extract_features.return_value = None

        pipeline = TrainingPipeline(extractor=mock_extractor)
        result = await pipeline.process_signal("test-sig-001")

        assert result is None
        assert pipeline.stats.skipped == 1

    @pytest.mark.asyncio
    async def test_process_signal_with_enrichment(
        self, mock_extractor, mock_storage, sample_features, sample_outcome
    ):
        """Test signal processing with outcome enrichment."""
        mock_extractor.extract_features.return_value = sample_features
        mock_storage.get_outcome_by_signal_id.return_value = sample_outcome

        pipeline = TrainingPipeline(
            extractor=mock_extractor,
            signal_storage=mock_storage,
        )
        result = await pipeline.process_signal("test-sig-001")

        assert result is not None
        assert result.outcome == 1  # Win
        assert result.pnl_percent is not None
        assert result.holding_period_minutes == 1440  # 24 hours

    @pytest.mark.asyncio
    async def test_process_signal_skip_enrichment(
        self, mock_extractor, sample_features
    ):
        """Test signal processing with enrichment skipped."""
        mock_extractor.extract_features.return_value = sample_features

        pipeline = TrainingPipeline(extractor=mock_extractor)
        result = await pipeline.process_signal("test-sig-001", skip_enrichment=True)

        assert result is not None
        assert result.outcome is None  # Not enriched

    @pytest.mark.asyncio
    async def test_process_batch(self, mock_extractor):
        """Test batch processing."""
        features_list = [
            ExtractedFeatures(
                signal_id=f"test-sig-{i:03d}",
                timestamp=datetime.now(),
                token="BTC",
                timeframe="1h",
                direction="long",
                confidence=0.85,
                entry_price=45000.0,
                technical=TechnicalIndicators(rsi=65.0 + i),
                market=MarketContext(trend_state="bullish"),
            )
            for i in range(5)
        ]

        # Mock extractor to return different features for each signal
        mock_extractor.extract_features = AsyncMock(side_effect=features_list)

        pipeline = TrainingPipeline(extractor=mock_extractor)
        signal_ids = [f"test-sig-{i:03d}" for i in range(5)]
        results = await pipeline.process_batch(signal_ids, batch_size=2)

        assert len(results) == 5
        assert pipeline.stats.batch_count == 3  # 5 signals / batch_size 2 = 3 batches

    @pytest.mark.asyncio
    async def test_process_batch_with_failures(self, mock_extractor):
        """Test batch processing with some failures."""
        # First two succeed, third fails, rest succeed
        side_effects = [
            ExtractedFeatures(
                signal_id="test-sig-001",
                timestamp=datetime.now(),
                token="BTC",
                timeframe="1h",
                direction="long",
                confidence=0.85,
                entry_price=45000.0,
                technical=TechnicalIndicators(),
                market=MarketContext(),
            ),
            ExtractedFeatures(
                signal_id="test-sig-002",
                timestamp=datetime.now(),
                token="BTC",
                timeframe="1h",
                direction="long",
                confidence=0.85,
                entry_price=45000.0,
                technical=TechnicalIndicators(),
                market=MarketContext(),
            ),
            None,  # This one fails
            ExtractedFeatures(
                signal_id="test-sig-004",
                timestamp=datetime.now(),
                token="BTC",
                timeframe="1h",
                direction="long",
                confidence=0.85,
                entry_price=45000.0,
                technical=TechnicalIndicators(),
                market=MarketContext(),
            ),
        ]

        mock_extractor.extract_features = AsyncMock(side_effect=side_effects)

        pipeline = TrainingPipeline(extractor=mock_extractor)
        signal_ids = [f"test-sig-{i:03d}" for i in range(1, 5)]
        results = await pipeline.process_batch(signal_ids, batch_size=2)

        assert len(results) == 3  # 3 successful
        assert pipeline.stats.skipped == 1

    @pytest.mark.asyncio
    async def test_enrich_with_outcomes(
        self, mock_extractor, mock_storage, sample_outcome
    ):
        """Test outcome enrichment."""
        mock_storage.get_outcome_by_signal_id.return_value = sample_outcome

        sample = TrainingSample(
            sample_id="test-sig-001",
            timestamp=datetime.now(),
            token="BTC",
            timeframe="1h",
            direction="long",
            entry_price=45000.0,
        )

        pipeline = TrainingPipeline(
            extractor=mock_extractor,
            signal_storage=mock_storage,
        )
        enriched = await pipeline.enrich_with_outcomes([sample])

        assert len(enriched) == 1
        assert enriched[0].outcome == 1
        assert enriched[0].pnl_percent is not None
        assert enriched[0].holding_period_minutes == 1440

    @pytest.mark.asyncio
    async def test_enrich_with_outcomes_no_storage(self, mock_extractor):
        """Test enrichment without storage."""
        sample = TrainingSample(
            sample_id="test-sig-001",
            timestamp=datetime.now(),
            token="BTC",
            timeframe="1h",
        )

        pipeline = TrainingPipeline(extractor=mock_extractor)
        enriched = await pipeline.enrich_with_outcomes([sample])

        # Should return samples unchanged
        assert len(enriched) == 1
        assert enriched[0].outcome is None

    def test_create_sample_from_features(self, mock_extractor, sample_features):
        """Test creating sample from features."""
        pipeline = TrainingPipeline(extractor=mock_extractor)
        sample = pipeline._create_sample_from_features(sample_features)

        assert sample.sample_id == "test-sig-001"
        assert sample.token == "BTC"
        assert sample.rsi == 65.5
        assert sample.macd == 0.5
        assert sample.trend_state == "bullish"
        assert sample.confidence_bin == 8

    def test_create_sample_bb_width_calculation(self, mock_extractor):
        """Test BB width calculation."""
        features = ExtractedFeatures(
            signal_id="test-sig-001",
            timestamp=datetime.now(),
            token="BTC",
            timeframe="1h",
            entry_price=45000.0,
            technical=TechnicalIndicators(
                bb_upper=46000.0,
                bb_lower=44000.0,
            ),
            market=MarketContext(),
        )

        pipeline = TrainingPipeline(extractor=mock_extractor)
        sample = pipeline._create_sample_from_features(features)

        # BB width = (46000 - 44000) / 45000 * 100 = 4.44%
        assert sample.bb_width is not None
        assert abs(sample.bb_width - 4.4444) < 0.01

    def test_calculate_pnl_percentage(self, mock_extractor):
        """Test PnL percentage calculation."""
        sample = TrainingSample(
            sample_id="test-sig-001",
            timestamp=datetime.now(),
            token="BTC",
            timeframe="1h",
            direction="long",
            entry_price=45000.0,
        )

        outcome = MagicMock()
        outcome.exit_price = 46000.0

        pipeline = TrainingPipeline(extractor=mock_extractor)
        pnl_pct = pipeline._calculate_pnl_percentage(sample, outcome)

        # (46000 - 45000) / 45000 * 100 = 2.22%
        assert pnl_pct is not None
        assert abs(pnl_pct - 2.2222) < 0.01

    def test_calculate_pnl_percentage_short(self, mock_extractor):
        """Test PnL percentage for short position."""
        sample = TrainingSample(
            sample_id="test-sig-001",
            timestamp=datetime.now(),
            token="BTC",
            timeframe="1h",
            direction="short",
            entry_price=45000.0,
        )

        outcome = MagicMock()
        outcome.exit_price = 44000.0  # Price went down

        pipeline = TrainingPipeline(extractor=mock_extractor)
        pnl_pct = pipeline._calculate_pnl_percentage(sample, outcome)

        # For short: -((44000 - 45000) / 45000 * 100) = 2.22%
        assert pnl_pct is not None
        assert abs(pnl_pct - 2.2222) < 0.01

    @pytest.mark.asyncio
    async def test_process_query_results(self, mock_extractor, mock_storage):
        """Test processing query results."""
        signal = SignalRecord(
            signal_id="test-sig-001",
            token="BTC",
            timestamp=int(datetime.now().timestamp() * 1000),
            direction=SignalDirection.LONG,
            confidence=0.85,
            entry_price=45000.0,
            score=75.0,
            timeframes_used=["1h"],
        )

        outcome = OutcomeRecord(
            signal_id="test-sig-001",
            exit_timestamp=int(datetime.now().timestamp() * 1000) + 86400000,
            is_win=True,
            pnl=500.0,
            exit_price=45500.0,
            duration_hours=24.0,
            outcome_type=OutcomeType.TP_HIT,
        )

        swo = SignalWithOutcome(signal=signal, outcome=outcome)

        # Mock the extractor's _extract_from_signal to return proper features
        mock_extractor._extract_from_signal = MagicMock(
            return_value=ExtractedFeatures(
                signal_id="test-sig-001",
                timestamp=datetime.now(),
                token="BTC",
                timeframe="1h",
                direction="long",
                confidence=0.85,
                entry_price=45000.0,
                technical=TechnicalIndicators(),
                market=MarketContext(),
            )
        )

        pipeline = TrainingPipeline(
            extractor=mock_extractor,
            signal_storage=mock_storage,
        )
        results = await pipeline.process_query_results([swo])

        assert len(results) == 1
        assert results[0].sample_id == "test-sig-001"
        assert results[0].outcome == 1

    @pytest.mark.asyncio
    async def test_process_date_range(self, mock_extractor, mock_storage):
        """Test processing date range."""
        signal = SignalRecord(
            signal_id="test-sig-001",
            token="BTC",
            timestamp=int(datetime.now().timestamp() * 1000),
            direction=SignalDirection.LONG,
            confidence=0.85,
            entry_price=45000.0,
            score=75.0,
            timeframes_used=["1h"],
        )

        outcome = OutcomeRecord(
            signal_id="test-sig-001",
            exit_timestamp=int(datetime.now().timestamp() * 1000) + 86400000,
            is_win=True,
            pnl=500.0,
            exit_price=45500.0,
            duration_hours=24.0,
            outcome_type=OutcomeType.TP_HIT,
        )

        swo = SignalWithOutcome(signal=signal, outcome=outcome)
        mock_storage.query_signals_with_outcomes.return_value = [swo]

        # Mock the extractor's _extract_from_signal to return proper features
        mock_extractor._extract_from_signal = MagicMock(
            return_value=ExtractedFeatures(
                signal_id="test-sig-001",
                timestamp=datetime.now(),
                token="BTC",
                timeframe="1h",
                direction="long",
                confidence=0.85,
                entry_price=45000.0,
                technical=TechnicalIndicators(),
                market=MarketContext(),
            )
        )

        pipeline = TrainingPipeline(
            extractor=mock_extractor,
            signal_storage=mock_storage,
        )

        start_date = datetime.now() - timedelta(days=7)
        end_date = datetime.now()
        results = await pipeline.process_date_range(start_date, end_date, token="BTC")

        assert len(results) == 1
        mock_storage.query_signals_with_outcomes.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_date_range_no_storage(self, mock_extractor):
        """Test date range processing without storage."""
        pipeline = TrainingPipeline(extractor=mock_extractor)

        start_date = datetime.now() - timedelta(days=7)
        end_date = datetime.now()
        results = await pipeline.process_date_range(start_date, end_date)

        assert len(results) == 0

    def test_get_stats(self, mock_extractor):
        """Test getting pipeline stats."""
        pipeline = TrainingPipeline(extractor=mock_extractor)
        pipeline.stats = PipelineStats(
            total_signals=100,
            successful=85,
            failed=10,
            skipped=5,
        )

        stats = pipeline.get_stats()
        assert stats.total_signals == 100
        assert stats.successful == 85

    def test_reset_stats(self, mock_extractor):
        """Test resetting pipeline stats."""
        pipeline = TrainingPipeline(extractor=mock_extractor)
        pipeline.stats = PipelineStats(total_signals=100, successful=85)

        pipeline.reset_stats()
        assert pipeline.stats.total_signals == 0
        assert pipeline.stats.successful == 0
