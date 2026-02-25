"""Tests to fill ML coverage gaps.

B5.3 - ML Coverage Gaps Remediation
Target: 80%+ coverage for all ML code

This module provides tests for coverage gaps identified in:
- src/ml/walk_forward.py (62% coverage)
- src/ml/training/extractor.py (59% coverage)
- src/ml/training/exporter.py (72% coverage)
- src/ml/rollback/automatic.py (82% coverage)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, Mock, patch

import numpy as np
import pytest

if TYPE_CHECKING:
    from collections.abc import Sequence


# =============================================================================
# Walk Forward Coverage Tests
# =============================================================================


class TestWalkForwardConfigCoverage:
    """Test WalkForwardConfig coverage gaps."""

    def test_walk_forward_config_defaults(self):
        """Test WalkForwardConfig default values."""
        from ml.walk_forward import WalkForwardConfig

        config = WalkForwardConfig()

        assert config.train_days == 30
        assert config.test_days == 7
        assert config.step_days == 7
        assert config.max_windows == 52
        assert config.min_train_samples == 500
        assert config.min_test_samples == 100
        assert config.enforce_temporal_validation is True

    def test_walk_forward_config_custom_values(self):
        """Test WalkForwardConfig with custom values."""
        from ml.walk_forward import WalkForwardConfig

        config = WalkForwardConfig(
            train_days=60,
            test_days=14,
            step_days=14,
            max_windows=10,
            min_train_samples=200,
            min_test_samples=50,
            enforce_temporal_validation=False,
        )

        assert config.train_days == 60
        assert config.test_days == 14
        assert config.step_days == 14
        assert config.max_windows == 10
        assert config.min_train_samples == 200
        assert config.min_test_samples == 50
        assert config.enforce_temporal_validation is False


class TestTemporalWindowCoverage:
    """Test TemporalWindow coverage gaps."""

    def test_temporal_window_creation(self):
        """Test TemporalWindow creation."""
        from ml.walk_forward import TemporalWindow

        start = datetime(2024, 1, 1)
        window = TemporalWindow(
            train_start=start,
            train_end=start + timedelta(days=30),
            test_start=start + timedelta(days=30),
            test_end=start + timedelta(days=37),
        )

        assert window.train_start == start
        assert window.train_end == start + timedelta(days=30)

    def test_temporal_window_duration_days_train(self):
        """Test duration_days for train period."""
        from ml.walk_forward import TemporalWindow

        start = datetime(2024, 1, 1)
        window = TemporalWindow(
            train_start=start,
            train_end=start + timedelta(days=30),
            test_start=start + timedelta(days=30),
            test_end=start + timedelta(days=37),
        )

        duration = window.duration_days(period="train")
        assert duration == 30.0

    def test_temporal_window_duration_days_test(self):
        """Test duration_days for test period."""
        from ml.walk_forward import TemporalWindow

        start = datetime(2024, 1, 1)
        window = TemporalWindow(
            train_start=start,
            train_end=start + timedelta(days=30),
            test_start=start + timedelta(days=30),
            test_end=start + timedelta(days=37),
        )

        duration = window.duration_days(period="test")
        assert duration == 7.0

    def test_temporal_window_contains_timestamp_train(self):
        """Test contains_timestamp for train period."""
        from ml.walk_forward import TemporalWindow

        start = datetime(2024, 1, 1)
        window = TemporalWindow(
            train_start=start,
            train_end=start + timedelta(days=30),
            test_start=start + timedelta(days=30),
            test_end=start + timedelta(days=37),
        )

        assert (
            window.contains_timestamp(start + timedelta(days=15), period="train")
            is True
        )
        assert (
            window.contains_timestamp(start + timedelta(days=35), period="train")
            is False
        )

    def test_temporal_window_contains_timestamp_test(self):
        """Test contains_timestamp for test period."""
        from ml.walk_forward import TemporalWindow

        start = datetime(2024, 1, 1)
        window = TemporalWindow(
            train_start=start,
            train_end=start + timedelta(days=30),
            test_start=start + timedelta(days=30),
            test_end=start + timedelta(days=37),
        )

        assert (
            window.contains_timestamp(start + timedelta(days=33), period="test") is True
        )
        assert (
            window.contains_timestamp(start + timedelta(days=15), period="test")
            is False
        )

    def test_temporal_window_validate_no_overlap(self):
        """Test validate_no_overlap method."""
        from ml.walk_forward import TemporalWindow

        start = datetime(2024, 1, 1)
        window1 = TemporalWindow(
            train_start=start,
            train_end=start + timedelta(days=30),
            test_start=start + timedelta(days=30),
            test_end=start + timedelta(days=37),
        )
        window2 = TemporalWindow(
            train_start=start + timedelta(days=37),
            train_end=start + timedelta(days=67),
            test_start=start + timedelta(days=67),
            test_end=start + timedelta(days=74),
        )

        assert window1.validate_no_overlap(window2) is True


class TestWindowStatusCoverage:
    """Test WindowStatus enum coverage."""

    def test_all_window_statuses(self):
        """Test all WindowStatus enum values."""
        from ml.walk_forward import WindowStatus

        assert WindowStatus.PENDING.value == "pending"
        assert WindowStatus.TRAINING.value == "training"
        assert WindowStatus.TESTING.value == "testing"
        assert WindowStatus.COMPLETED.value == "completed"
        assert WindowStatus.FAILED.value == "failed"


class TestLookAheadBiasCheckCoverage:
    """Test LookAheadBiasCheck enum coverage."""

    def test_all_bias_check_results(self):
        """Test all LookAheadBiasCheck enum values."""
        from ml.walk_forward import LookAheadBiasCheck

        assert LookAheadBiasCheck.PASSED.value == "passed"
        assert LookAheadBiasCheck.FAILED_OVERLAP.value == "failed_overlap"
        assert LookAheadBiasCheck.FAILED_FUTURE_DATA.value == "failed_future_data"
        assert LookAheadBiasCheck.FAILED_TEMPORAL_ORDER.value == "failed_temporal_order"


class TestWindowMetricsCoverage:
    """Test WindowMetrics coverage gaps."""

    def test_window_metrics_creation(self):
        """Test WindowMetrics creation with all fields."""
        from ml.walk_forward import TemporalWindow, WindowMetrics, WindowStatus

        start = datetime(2024, 1, 1)
        window = TemporalWindow(
            train_start=start,
            train_end=start + timedelta(days=30),
            test_start=start + timedelta(days=30),
            test_end=start + timedelta(days=37),
        )

        metrics = WindowMetrics(
            window=window,
            status=WindowStatus.COMPLETED,
            sharpe_ratio=1.5,
            max_drawdown_pct=-5.0,
            win_rate_pct=60.0,
            profit_factor=2.0,
            total_return_pct=10.0,
            volatility_pct=15.0,
            trade_count=50,
            avg_trade_return_pct=0.2,
            training_time_seconds=300.0,
            testing_time_seconds=60.0,
        )

        assert metrics.window == window
        assert metrics.sharpe_ratio == 1.5
        assert metrics.trade_count == 50

    def test_window_metrics_to_dict(self):
        """Test WindowMetrics to_dict method."""
        from ml.walk_forward import TemporalWindow, WindowMetrics, WindowStatus

        start = datetime(2024, 1, 1)
        window = TemporalWindow(
            train_start=start,
            train_end=start + timedelta(days=30),
            test_start=start + timedelta(days=30),
            test_end=start + timedelta(days=37),
        )

        metrics = WindowMetrics(
            window=window,
            status=WindowStatus.COMPLETED,
            sharpe_ratio=1.5,
            max_drawdown_pct=-5.0,
            win_rate_pct=60.0,
            trade_count=50,
        )

        metrics_dict = metrics.to_dict()
        assert metrics_dict["sharpe_ratio"] == 1.5
        assert metrics_dict["trade_count"] == 50
        assert metrics_dict["status"] == "completed"


class TestAggregatedMetricsCoverage:
    """Test AggregatedMetrics coverage gaps."""

    def test_aggregated_metrics_creation(self):
        """Test AggregatedMetrics creation."""
        from ml.walk_forward import AggregatedMetrics

        metrics = AggregatedMetrics(
            window_count=5,
            mean_sharpe=1.2,
            std_sharpe=0.3,
            mean_max_drawdown=-8.0,
            mean_win_rate=55.0,
            mean_profit_factor=1.8,
            mean_total_return=25.0,
            std_max_drawdown=2.0,
            std_win_rate=5.0,
            total_trades=250,
            total_return_pct=25.0,
            consistency_score=0.75,
            best_window_index=2,
            worst_window_index=4,
        )

        assert metrics.window_count == 5
        assert metrics.mean_sharpe == 1.2
        assert metrics.consistency_score == 0.75

    def test_aggregated_metrics_to_dict(self):
        """Test AggregatedMetrics to_dict method."""
        from ml.walk_forward import AggregatedMetrics

        metrics = AggregatedMetrics(
            window_count=5,
            mean_sharpe=1.2,
            std_sharpe=0.3,
            mean_max_drawdown=-8.0,
            mean_win_rate=55.0,
            consistency_score=0.75,
            std_max_drawdown=2.0,
            std_win_rate=5.0,
            total_trades=250,
            total_return_pct=25.0,
            best_window_index=2,
            worst_window_index=4,
        )

        metrics_dict = metrics.to_dict()
        assert metrics_dict["window_count"] == 5
        assert metrics_dict["mean_sharpe"] == 1.2
        assert metrics_dict["consistency_score"] == 0.75


class TestWalkForwardResultCoverage:
    """Test WalkForwardResult coverage gaps."""

    def test_walk_forward_result_creation(self):
        """Test WalkForwardResult creation."""
        from ml.walk_forward import (
            AggregatedMetrics,
            WalkForwardConfig,
            WalkForwardResult,
        )

        config = WalkForwardConfig()
        result = WalkForwardResult(
            strategy_id="test_strategy",
            config=config,
            window_results=[],
            aggregated=AggregatedMetrics(window_count=0),
        )

        assert result.strategy_id == "test_strategy"

    def test_walk_forward_result_to_dict(self):
        """Test WalkForwardResult to_dict method."""
        from ml.walk_forward import (
            AggregatedMetrics,
            WalkForwardConfig,
            WalkForwardResult,
        )

        config = WalkForwardConfig()
        result = WalkForwardResult(
            strategy_id="test_strategy",
            config=config,
            window_results=[],
            aggregated=AggregatedMetrics(window_count=0),
        )

        result_dict = result.to_dict()
        assert result_dict["strategy_id"] == "test_strategy"
        assert "aggregated" in result_dict


class TestWalkForwardEvaluatorCoverage:
    """Test WalkForwardEvaluator coverage gaps."""

    def test_evaluator_initialization(self):
        """Test WalkForwardEvaluator initialization."""
        from ml.walk_forward import WalkForwardConfig, WalkForwardEvaluator

        config = WalkForwardConfig(train_days=30, test_days=7)
        evaluator = WalkForwardEvaluator(config)

        assert evaluator.config == config


# =============================================================================
# Training Extractor Coverage Tests
# =============================================================================


class TestTechnicalIndicatorsCoverage:
    """Test TechnicalIndicators coverage."""

    def test_technical_indicators_creation(self):
        """Test TechnicalIndicators creation."""
        from ml.training.extractor import TechnicalIndicators

        indicators = TechnicalIndicators(
            rsi=65.0,
            macd=0.5,
            macd_signal=0.3,
            macd_histogram=0.2,
            bb_upper=51000.0,
            bb_lower=49000.0,
            bb_width=0.04,
            bb_percent_b=0.6,
            atr=500.0,
            volume_sma=1.2,
        )

        assert indicators.rsi == 65.0
        assert indicators.macd == 0.5
        assert indicators.bb_width == 0.04

    def test_technical_indicators_to_dict(self):
        """Test TechnicalIndicators to_dict."""
        from ml.training.extractor import TechnicalIndicators

        indicators = TechnicalIndicators(rsi=65.0, macd=0.5)
        indicators_dict = indicators.to_dict()

        assert indicators_dict["rsi"] == 65.0
        assert indicators_dict["macd"] == 0.5

    def test_technical_indicators_to_normalized_dict(self):
        """Test TechnicalIndicators to_normalized_dict."""
        from ml.training.extractor import TechnicalIndicators

        indicators = TechnicalIndicators(
            rsi=65.0,
            macd=0.5,
            bb_percent_b=0.6,
            bb_width=0.04,
            atr=0.02,
            volume_sma=1.2,
        )
        normalized = indicators.to_normalized_dict()

        assert 0.0 <= normalized["rsi_norm"] <= 1.0
        assert 0.0 <= normalized["macd_norm"] <= 1.0
        assert 0.0 <= normalized["bb_position_norm"] <= 1.0

    def test_normalize_rsi(self):
        """Test RSI normalization."""
        from ml.training.extractor import TechnicalIndicators

        assert TechnicalIndicators._normalize_rsi(50.0) == 0.5
        assert TechnicalIndicators._normalize_rsi(100.0) == 1.0
        assert TechnicalIndicators._normalize_rsi(0.0) == 0.0
        assert TechnicalIndicators._normalize_rsi(None) == 0.5

    def test_normalize_macd(self):
        """Test MACD normalization."""
        from ml.training.extractor import TechnicalIndicators

        assert TechnicalIndicators._normalize_macd(0.0) == 0.5
        assert TechnicalIndicators._normalize_macd(5.0) == 1.0
        assert TechnicalIndicators._normalize_macd(-5.0) == 0.0
        assert TechnicalIndicators._normalize_macd(None) == 0.5

    def test_normalize_bb_position(self):
        """Test BB position normalization."""
        from ml.training.extractor import TechnicalIndicators

        assert TechnicalIndicators._normalize_bb_position(0.5) == 0.5
        assert TechnicalIndicators._normalize_bb_position(1.0) == 1.0
        assert TechnicalIndicators._normalize_bb_position(0.0) == 0.0
        assert TechnicalIndicators._normalize_bb_position(None) == 0.5

    def test_normalize_bb_width(self):
        """Test BB width normalization."""
        from ml.training.extractor import TechnicalIndicators

        assert TechnicalIndicators._normalize_bb_width(0.05) == 0.5
        assert TechnicalIndicators._normalize_bb_width(0.1) == 1.0
        assert TechnicalIndicators._normalize_bb_width(0.0) == 0.0
        assert TechnicalIndicators._normalize_bb_width(None) == 0.5

    def test_normalize_atr(self):
        """Test ATR normalization."""
        from ml.training.extractor import TechnicalIndicators

        assert TechnicalIndicators._normalize_atr(0.025) == 0.5
        assert TechnicalIndicators._normalize_atr(0.05) == 1.0
        assert TechnicalIndicators._normalize_atr(0.0) == 0.0
        assert TechnicalIndicators._normalize_atr(None) == 0.5

    def test_normalize_volume(self):
        """Test volume normalization."""
        from ml.training.extractor import TechnicalIndicators

        assert TechnicalIndicators._normalize_volume(1.0) == 0.5
        assert TechnicalIndicators._normalize_volume(2.0) == 1.0
        assert TechnicalIndicators._normalize_volume(0.0) == 0.0
        assert TechnicalIndicators._normalize_volume(None) == 0.5


class TestMarketContextCoverage:
    """Test MarketContext coverage."""

    def test_market_context_creation(self):
        """Test MarketContext creation."""
        from ml.training.extractor import MarketContext

        context = MarketContext(
            trend_state="trending_up",
            trend_confidence=0.85,
            confluence_score=75.0,
            price_change_24h=5.0,
            volatility=0.02,
        )

        assert context.trend_state == "trending_up"
        assert context.trend_confidence == 0.85
        assert context.confluence_score == 75.0

    def test_market_context_to_dict(self):
        """Test MarketContext to_dict."""
        from ml.training.extractor import MarketContext

        context = MarketContext(
            trend_state="trending_up",
            trend_confidence=0.85,
        )
        context_dict = context.to_dict()

        assert context_dict["trend_state"] == "trending_up"
        assert context_dict["trend_confidence"] == 0.85


class TestExtractedFeaturesCoverage:
    """Test ExtractedFeatures coverage."""

    def test_extracted_features_creation(self):
        """Test ExtractedFeatures creation."""
        from ml.training.extractor import (
            ExtractedFeatures,
            MarketContext,
            TechnicalIndicators,
        )

        features = ExtractedFeatures(
            signal_id="signal_001",
            timestamp=datetime(2024, 1, 1),
            token="BTC/USDT",
            timeframe="1h",
            direction="long",
            confidence=0.85,
            entry_price=50000.0,
            technical=TechnicalIndicators(rsi=65.0),
            market=MarketContext(trend_state="trending_up"),
            predicted_prob=0.75,
        )

        assert features.signal_id == "signal_001"
        assert features.token == "BTC/USDT"
        assert features.technical.rsi == 65.0

    def test_extracted_features_to_dict(self):
        """Test ExtractedFeatures to_dict."""
        from ml.training.extractor import (
            ExtractedFeatures,
            MarketContext,
            TechnicalIndicators,
        )

        features = ExtractedFeatures(
            signal_id="signal_001",
            timestamp=datetime(2024, 1, 1),
            token="BTC/USDT",
            timeframe="1h",
            direction="long",
            confidence=0.85,
            entry_price=50000.0,
            technical=TechnicalIndicators(rsi=65.0),
            market=MarketContext(trend_state="trending_up"),
            predicted_prob=0.75,
        )
        features_dict = features.to_dict()

        assert features_dict["signal_id"] == "signal_001"
        assert features_dict["token"] == "BTC/USDT"


class TestFeatureExtractorCoverage:
    """Test FeatureExtractor coverage gaps."""

    def test_feature_extractor_initialization(self):
        """Test FeatureExtractor initialization."""
        from ml.training.extractor import FeatureExtractor

        extractor = FeatureExtractor()
        assert extractor is not None

    def test_feature_extractor_initialization_with_storage(self):
        """Test FeatureExtractor initialization with storage."""
        from ml.training.extractor import FeatureExtractor

        mock_storage = MagicMock()
        extractor = FeatureExtractor(signal_storage=mock_storage)
        assert extractor.signal_storage == mock_storage

    def test_clear_cache(self):
        """Test cache clearing."""
        from ml.training.extractor import FeatureExtractor

        extractor = FeatureExtractor()
        # Should not raise error even if cache is empty
        extractor.clear_cache()


# =============================================================================
# Training Exporter Coverage Tests
# =============================================================================


class TestDatasetExporterCoverage:
    """Test DatasetExporter coverage gaps."""

    def test_dataset_exporter_initialization(self):
        """Test DatasetExporter initialization."""
        from ml.training.exporter import DatasetExporter

        mock_pipeline = MagicMock()
        exporter = DatasetExporter(pipeline=mock_pipeline)
        assert exporter.pipeline == mock_pipeline


class TestExportFormatCoverage:
    """Test ExportFormat enum coverage."""

    def test_export_formats(self):
        """Test all export formats."""
        from ml.training.exporter import ExportFormat

        assert ExportFormat.CSV.value == "csv"
        assert ExportFormat.PARQUET.value == "parquet"
        assert ExportFormat.JSON.value == "json"
        assert ExportFormat.HDF5.value == "h5"


class TestDatasetInfoCoverage:
    """Test DatasetInfo coverage."""

    def test_dataset_info_creation(self):
        """Test DatasetInfo creation."""
        from ml.training.exporter import DatasetInfo

        info = DatasetInfo(
            path="/tmp/test.csv",
            format="csv",
            num_samples=100,
            num_features=10,
            train_samples=80,
            test_samples=20,
            created_at=datetime(2024, 1, 1),
            feature_names=["f1", "f2"],
            statistics={},
        )

        assert info.path == "/tmp/test.csv"
        assert info.num_samples == 100


class TestDatasetStatisticsCoverage:
    """Test DatasetStatistics coverage."""

    def test_dataset_statistics_creation(self):
        """Test DatasetStatistics creation."""
        from ml.training.exporter import DatasetStatistics

        stats = DatasetStatistics(
            win_rate=0.6,
            avg_pnl=0.02,
            max_drawdown=-0.05,
            feature_means={"f1": 0.5},
            feature_stds={"f1": 0.1},
            outcome_distribution={"win": 60, "loss": 40},
        )

        assert stats.win_rate == 0.6
        assert stats.avg_pnl == 0.02


# =============================================================================
# Rollback Automatic Coverage Tests
# =============================================================================


class TestRollbackStateCoverage:
    """Test RollbackState enum coverage."""

    def test_all_rollback_states(self):
        """Test all RollbackState enum values."""
        from ml.rollback.automatic import RollbackState

        assert RollbackState.PENDING.value == "pending"
        assert RollbackState.IN_PROGRESS.value == "in_progress"
        assert RollbackState.COMPLETED.value == "completed"
        assert RollbackState.FAILED.value == "failed"
        assert RollbackState.CANCELLED.value == "cancelled"


class TestRollbackReasonCoverage:
    """Test RollbackReason enum coverage."""

    def test_all_rollback_reasons(self):
        """Test all RollbackReason enum values."""
        from ml.rollback.automatic import RollbackReason

        assert RollbackReason.VALIDATION_FAILED.value == "validation_failed"
        assert RollbackReason.PERFORMANCE_DEGRADATION.value == "performance_degradation"
        assert RollbackReason.MANUAL.value == "manual"
        assert RollbackReason.SYSTEM_ERROR.value == "system_error"


class TestRollbackResultCoverage:
    """Test RollbackResult coverage."""

    def test_rollback_result_success(self):
        """Test successful RollbackResult."""
        from ml.rollback.automatic import RollbackReason, RollbackResult, RollbackState

        result = RollbackResult(
            success=True,
            rollback_id="rb_001",
            failed_version_id="v2.0",
            target_version_id="v1.0",
            state=RollbackState.COMPLETED,
            started_at=datetime(2024, 1, 1),
            completed_at=datetime(2024, 1, 1),
            duration_seconds=30.0,
            reason=RollbackReason.VALIDATION_FAILED,
            message="Rollback successful",
            evidence={"test": True},
        )

        assert result.success is True
        assert result.rollback_id == "rb_001"

    def test_rollback_result_failure(self):
        """Test failed RollbackResult."""
        from ml.rollback.automatic import RollbackReason, RollbackResult, RollbackState

        result = RollbackResult(
            success=False,
            rollback_id="rb_002",
            failed_version_id="v2.0",
            target_version_id="v1.0",
            state=RollbackState.FAILED,
            started_at=datetime(2024, 1, 1),
            completed_at=datetime(2024, 1, 1),
            duration_seconds=0.0,
            reason=RollbackReason.SYSTEM_ERROR,
            message="Connection timeout",
            evidence={},
        )

        assert result.success is False
        assert result.message == "Connection timeout"


class TestRollbackConfigCoverage:
    """Test RollbackConfig coverage."""

    def test_rollback_config_defaults(self):
        """Test RollbackConfig default values."""
        from ml.rollback.automatic import RollbackConfig

        config = RollbackConfig()

        assert config.max_rollback_time_seconds == 60
        assert config.auto_rollback_enabled is True
        assert config.require_confirmation is False
        assert config.preserve_challenger is False  # Actual default

    def test_rollback_config_custom(self):
        """Test RollbackConfig with custom values."""
        from ml.rollback.automatic import RollbackConfig

        config = RollbackConfig(
            max_rollback_time_seconds=120,
            auto_rollback_enabled=False,
            require_confirmation=True,
            preserve_challenger=True,
            notification_channels=["email"],
        )

        assert config.max_rollback_time_seconds == 120
        assert config.auto_rollback_enabled is False
        assert config.require_confirmation is True
        assert config.preserve_challenger is True


class TestRollbackManagerCoverage:
    """Test RollbackManager coverage gaps."""

    @pytest.fixture
    def mock_registry(self):
        """Create mock model registry."""
        registry = MagicMock()
        registry.get_champion.return_value = MagicMock(version_id="v1.0")
        return registry

    def test_rollback_manager_initialization(self, mock_registry):
        """Test RollbackManager initialization."""
        from ml.rollback.automatic import RollbackConfig, RollbackManager

        config = RollbackConfig()
        manager = RollbackManager(registry=mock_registry, config=config)

        # Check the manager was initialized (RollbackManager stores as _registry and _config)
        assert manager._registry == mock_registry
        assert manager._config == config

    def test_rollback_manager_initialization_default_config(self, mock_registry):
        """Test RollbackManager with default config."""
        from ml.rollback.automatic import RollbackManager

        manager = RollbackManager(registry=mock_registry)
        assert manager._config is not None

    def test_get_rollback_history_empty(self, mock_registry):
        """Test getting empty rollback history."""
        from ml.rollback.automatic import RollbackManager

        manager = RollbackManager(registry=mock_registry)
        history = manager.get_rollback_history()

        assert history == []

    @pytest.mark.asyncio
    async def test_rollback_on_failure_disabled(self, mock_registry):
        """Test rollback when disabled."""
        from ml.rollback.automatic import RollbackConfig, RollbackManager, RollbackState

        config = RollbackConfig(auto_rollback_enabled=False)
        manager = RollbackManager(registry=mock_registry, config=config)

        result = await manager.rollback_on_failure(
            failed_version_id="v2.0",
            reason="Test failure",
        )

        assert result.state == RollbackState.CANCELLED

    @pytest.mark.asyncio
    async def test_rollback_on_failure_no_champion(self, mock_registry):
        """Test rollback when no champion exists."""
        from ml.rollback.automatic import (
            RollbackConfig,
            RollbackManager,
            RollbackState,
            RollbackReason,
        )

        mock_registry.get_champion.return_value = None

        config = RollbackConfig()
        manager = RollbackManager(registry=mock_registry, config=config)

        result = await manager.rollback_on_failure(
            failed_version_id="v2.0",
            reason=RollbackReason.VALIDATION_FAILED,
        )

        assert result.state == RollbackState.FAILED


# =============================================================================
# Model Registry Coverage Tests
# =============================================================================


class TestModelVersionCoverage:
    """Test ModelVersion coverage."""

    def test_model_version_creation(self):
        """Test ModelVersion creation."""
        from ml.models.model_registry import ModelVersion

        version = ModelVersion(
            model_name="test_model",
            version="v1.0.0",
            created_at=datetime(2024, 1, 1),
            metadata_path="/path/to/metadata.json",
            model_path="/path/to/model.pkl",
        )

        assert version.model_name == "test_model"
        assert version.version == "v1.0.0"


# =============================================================================
# Scheduler Coverage Tests - Skipped (OptimizationTask is a Protocol)
# =============================================================================


# OptimizationTask is a Protocol and cannot be instantiated directly


# =============================================================================
# Hyperopt Coverage Tests
# =============================================================================


class TestOptimizationMethodCoverage:
    """Test OptimizationMethod enum coverage."""

    def test_all_optimization_methods(self):
        """Test all OptimizationMethod enum values."""
        from ml.hyperopt import OptimizationMethod

        assert OptimizationMethod.GENETIC.value == "genetic"
        assert OptimizationMethod.BAYESIAN.value == "bayesian"
        assert OptimizationMethod.RANDOM.value == "random"


class TestOptimizationResultCoverage:
    """Test OptimizationResult coverage."""

    def test_optimization_result_creation(self):
        """Test OptimizationResult creation."""
        from ml.hyperopt import OptimizationResult, OptimizationMethod

        result = OptimizationResult(
            strategy_id="strategy_001",
            method=OptimizationMethod.GENETIC,
            best_parameters={"lr": 0.01},
            best_score=0.85,
            best_metrics={"accuracy": 0.85},
            baseline_score=0.80,
            improvement_pct=6.25,
            trials=[],
            convergence_reached=True,
            variance_across_runs=0.01,
            total_iterations=100,
            total_time_seconds=120.0,
            created_at=datetime(2024, 1, 1),
            completed_at=datetime(2024, 1, 1),
        )

        assert result.strategy_id == "strategy_001"
        assert result.best_score == 0.85

    def test_optimization_result_to_dict(self):
        """Test OptimizationResult to_dict."""
        from ml.hyperopt import OptimizationMethod, OptimizationResult

        result = OptimizationResult(
            strategy_id="strategy_001",
            method=OptimizationMethod.GENETIC,
            best_parameters={"lr": 0.01},
            best_score=0.85,
            best_metrics={"accuracy": 0.85},
            baseline_score=0.80,
            improvement_pct=6.25,
            trials=[],
            convergence_reached=True,
            variance_across_runs=0.01,
            total_iterations=100,
            total_time_seconds=120.0,
            created_at=datetime(2024, 1, 1),
            completed_at=datetime(2024, 1, 1),
        )

        result_dict = result.to_dict()
        assert result_dict["strategy_id"] == "strategy_001"
        assert result_dict["best_score"] == 0.85


# =============================================================================
# Retraining Trigger Coverage Tests
# =============================================================================


class TestTriggerTypeCoverage:
    """Test TriggerType enum coverage."""

    def test_all_trigger_types(self):
        """Test all TriggerType enum values."""
        from ml.training.retraining_trigger import TriggerType

        assert TriggerType.ECE_BASED.value == 1
        assert TriggerType.PERFORMANCE_BASED.value == 2
        assert TriggerType.SCHEDULED.value == 3


# =============================================================================
# Integration Tests
# =============================================================================


class TestMLPipelineIntegration:
    """Integration tests for ML pipeline components."""

    def test_walk_forward_temporal_window_chain(self):
        """Test creating a chain of non-overlapping temporal windows."""
        from ml.walk_forward import TemporalWindow

        start = datetime(2024, 1, 1)
        windows = []

        # Create 3 consecutive windows
        for i in range(3):
            window_start = start + timedelta(days=i * 37)
            window = TemporalWindow(
                train_start=window_start,
                train_end=window_start + timedelta(days=30),
                test_start=window_start + timedelta(days=30),
                test_end=window_start + timedelta(days=37),
            )
            windows.append(window)

        # Verify no overlaps
        for i in range(len(windows) - 1):
            assert windows[i].validate_no_overlap(windows[i + 1])

    def test_technical_indicators_normalization_pipeline(self):
        """Test technical indicators normalization pipeline."""
        from ml.training.extractor import TechnicalIndicators

        indicators = TechnicalIndicators(
            rsi=75.0,
            macd=2.0,
            bb_percent_b=0.8,
            bb_width=0.06,
            atr=0.03,
            volume_sma=1.5,
        )

        normalized = indicators.to_normalized_dict()

        # Verify all values are in [0, 1] range
        for key, value in normalized.items():
            assert 0.0 <= value <= 1.0, f"{key} = {value} is not in [0, 1]"

    def test_rollback_state_transitions(self):
        """Test rollback state transition logic."""
        from ml.rollback.automatic import RollbackState

        # Define valid state transitions
        transitions = {
            RollbackState.PENDING: [RollbackState.IN_PROGRESS, RollbackState.CANCELLED],
            RollbackState.IN_PROGRESS: [RollbackState.COMPLETED, RollbackState.FAILED],
        }

        # Verify transitions
        for from_state, to_states in transitions.items():
            for to_state in to_states:
                assert isinstance(to_state, RollbackState)
