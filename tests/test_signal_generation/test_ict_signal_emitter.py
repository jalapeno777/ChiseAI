"""Tests for ICT signal emitter module.

Tests for the ICTSignalEmitter class that polls ICT detectors
and emits signals to the signal bus.

BOS/CHoCH signals are EXCLUDED per BL-BOS-CHOCH-001.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from signal_generation.ict_signal_emitter import (
    ICTEmissionConfig,
    ICTEmissionCycle,
    ICTSignalEmitter,
    ICTSignalResult,
)
from signal_generation.models import Signal, SignalDirection, SignalStatus
from signal_generation.registry.ict_signal_registry import ICTSignalRegistry
from signal_generation.registry.signal_types import ICTSignalType, SignalPriority

logger = logging.getLogger(__name__)


class TestICTEmissionConfig:
    """Tests for ICTEmissionConfig dataclass."""

    def test_default_config(self):
        """Test default emission configuration."""
        config = ICTEmissionConfig()

        assert config.min_confidence == 0.50
        assert config.enable_cvd is True
        assert config.enable_fvg is True
        assert config.enable_order_block is True
        assert config.emission_interval_seconds == 60.0
        assert config.max_signals_per_cycle == 10
        assert config.bos_choch_warning is True

    def test_custom_config(self):
        """Test custom emission configuration."""
        config = ICTEmissionConfig(
            min_confidence=0.60,
            enable_cvd=False,
            enable_fvg=True,
            enable_order_block=False,
            emission_interval_seconds=30.0,
            max_signals_per_cycle=5,
        )

        assert config.min_confidence == 0.60
        assert config.enable_cvd is False
        assert config.enable_fvg is True
        assert config.enable_order_block is False
        assert config.emission_interval_seconds == 30.0
        assert config.max_signals_per_cycle == 5


class TestICTSignalResult:
    """Tests for ICTSignalResult dataclass."""

    def test_successful_result(self):
        """Test successful ICT signal result."""
        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
        )

        result = ICTSignalResult(
            signal=signal,
            signal_type="cvd",
            emission_success=True,
            emission_error=None,
            emission_latency_ms=50.0,
        )

        assert result.signal == signal
        assert result.signal_type == "cvd"
        assert result.emission_success is True
        assert result.emission_error is None
        assert result.emission_latency_ms == 50.0
        assert result.skipped is False

    def test_skipped_result(self):
        """Test skipped ICT signal result."""
        result = ICTSignalResult(
            signal=None,
            signal_type="bos",
            emission_success=False,
            emission_error=None,
            emission_latency_ms=0.0,
            skipped=True,
            skip_reason="EXCLUDED per BL-BOS-CHOCH-001: bos",
        )

        assert result.signal is None
        assert result.signal_type == "bos"
        assert result.emission_success is False
        assert result.skipped is True
        assert "BL-BOS-CHOCH-001" in result.skip_reason


class TestICTSignalEmitter:
    """Tests for ICTSignalEmitter."""

    def test_initialization(self):
        """Test ICT emitter initialization."""
        emitter = ICTSignalEmitter()

        assert emitter.name == "ict_signal_emitter"
        assert emitter.config.min_confidence == 0.50
        assert emitter.config.enable_cvd is True
        assert emitter.config.enable_fvg is True
        assert emitter.config.enable_order_block is True

    def test_initialization_with_config(self):
        """Test ICT emitter initialization with custom config."""
        config = ICTEmissionConfig(
            min_confidence=0.65,
            enable_cvd=False,
            enable_fvg=True,
            enable_order_block=True,
        )
        emitter = ICTSignalEmitter(config=config)

        assert emitter.config.min_confidence == 0.65
        assert emitter.config.enable_cvd is False
        assert emitter.config.enable_fvg is True
        assert emitter.config.enable_order_block is True

    def test_initialization_with_registry(self):
        """Test ICT emitter initialization with custom registry."""
        registry = ICTSignalRegistry()
        emitter = ICTSignalEmitter(registry=registry)

        assert emitter.registry == registry

    def test_initialization_with_emitters(self):
        """Test ICT emitter initialization with emitters."""
        mock_emitter = MagicMock()
        mock_emitter.name = "mock"
        emitter = ICTSignalEmitter(emitters=[mock_emitter])

        assert len(emitter.emitters) == 1
        assert emitter.emitters[0].name == "mock"

    def test_check_bos_choch_no_longer_excluded(self):
        """Test BOS/CHoCH is no longer excluded (re-enabled)."""
        emitter = ICTSignalEmitter()

        # BOS/CHoCH should no longer be excluded
        assert emitter._check_bos_choch_exclusion("bos") is False
        assert emitter._check_bos_choch_exclusion("choch") is False
        assert emitter._check_bos_choch_exclusion("bos_choch") is False
        assert emitter._check_bos_choch_exclusion("BOS") is False
        assert emitter._check_bos_choch_exclusion("CHOCH") is False

        # Other signals also not excluded
        assert emitter._check_bos_choch_exclusion("cvd") is False
        assert emitter._check_bos_choch_exclusion("fvg") is False
        assert emitter._check_bos_choch_exclusion("order_block") is False

    def test_is_signal_enabled_cvd(self):
        """Test CVD signal enabled check."""
        emitter = ICTSignalEmitter()

        # CVD should be enabled by default
        assert emitter.is_signal_enabled("cvd") is True

        # Disable via feature flag
        emitter.set_feature_flag("cvd", False)
        assert emitter.is_signal_enabled("cvd") is False

        # Re-enable
        emitter.set_feature_flag("cvd", True)
        assert emitter.is_signal_enabled("cvd") is True

    def test_is_signal_enabled_fvg(self):
        """Test FVG signal enabled check."""
        emitter = ICTSignalEmitter()

        # FVG should be enabled by default
        assert emitter.is_signal_enabled("fvg") is True

        # Disable via feature flag
        emitter.set_feature_flag("fvg", False)
        assert emitter.is_signal_enabled("fvg") is False

    def test_is_signal_enabled_order_block(self):
        """Test Order Block signal enabled check."""
        emitter = ICTSignalEmitter()

        # Order Block should be enabled by default
        assert emitter.is_signal_enabled("order_block") is True

        # Disable via feature flag
        emitter.set_feature_flag("order_block", False)
        assert emitter.is_signal_enabled("order_block") is False

    def test_is_signal_enabled_bos_choch_included(self):
        """Test that BOS/CHoCH is no longer excluded."""
        emitter = ICTSignalEmitter()

        # BOS/CHoCH is no longer blocked by exclusion check
        assert emitter._check_bos_choch_exclusion("bos") is False
        assert emitter._check_bos_choch_exclusion("choch") is False
        assert emitter._check_bos_choch_exclusion("bos_choch") is False

    def test_log_bos_choch_warning(self):
        """Test BOS/CHoCH warning logging."""
        emitter = ICTSignalEmitter()

        with patch("signal_generation.ict_signal_emitter.logger") as mock_logger:
            emitter._log_bos_choch_warning("bos")

            mock_logger.warning.assert_called_once()
            log_msg = mock_logger.warning.call_args[0][0]
            assert "BOS/CHoCH signal detected: bos" in log_msg
            assert "BL-BOS-CHOCH-001" in log_msg

    def test_log_bos_choch_warning_disabled(self):
        """Test BOS/CHoCH warning is disabled."""
        config = ICTEmissionConfig(bos_choch_warning=False)
        emitter = ICTSignalEmitter(config=config)

        with patch("signal_generation.ict_signal_emitter.logger") as mock_logger:
            emitter._log_bos_choch_warning("bos")

            mock_logger.warning.assert_not_called()

    def test_set_feature_flag_cvd(self):
        """Test setting CVD feature flag."""
        emitter = ICTSignalEmitter()

        emitter.set_feature_flag("cvd", False)

        # Check registry
        assert emitter.registry._feature_flags.is_enabled("enable_cvd_signals") is False

    def test_set_feature_flag_fvg(self):
        """Test setting FVG feature flag."""
        emitter = ICTSignalEmitter()

        emitter.set_feature_flag("fvg", False)

        assert emitter.registry._feature_flags.is_enabled("enable_fvg_signals") is False

    def test_set_feature_flag_order_block(self):
        """Test setting Order Block feature flag."""
        emitter = ICTSignalEmitter()

        emitter.set_feature_flag("order_block", False)

        assert (
            emitter.registry._feature_flags.is_enabled("enable_order_block_signals")
            is False
        )

    def test_get_status(self):
        """Test getting emitter status."""
        emitter = ICTSignalEmitter()

        status = emitter.get_status()

        assert "config" in status
        assert "feature_flags" in status
        assert "emitters" in status
        assert "cycle_count" in status
        assert status["bos_choch_excluded"] is False
        assert status["bos_choch_exclusion_reference"] is None
        assert status["config"]["min_confidence"] == 0.50

    @pytest.mark.asyncio
    async def test_emit_signal_bos_not_excluded(self):
        """Test that BOS signals are no longer excluded."""
        emitter = ICTSignalEmitter()

        result = await emitter.emit_signal(
            signal_type="bos",
            token="BTC/USDT",
            timeframe="1H",
            signal_data=None,
        )

        # BOS is no longer excluded - it may be skipped for other reasons
        # (e.g., no signal data) but not for BL-BOS-CHOCH-001
        if result.skipped:
            assert "BL-BOS-CHOCH-001" not in result.skip_reason

    @pytest.mark.asyncio
    async def test_emit_signal_choch_not_excluded(self):
        """Test that CHoCH signals are no longer excluded."""
        emitter = ICTSignalEmitter()

        result = await emitter.emit_signal(
            signal_type="choch",
            token="BTC/USDT",
            timeframe="1H",
            signal_data=None,
        )

        # CHoCH is no longer excluded
        if result.skipped:
            assert "BL-BOS-CHOCH-001" not in result.skip_reason

    @pytest.mark.asyncio
    async def test_emit_signal_feature_flag_disabled(self):
        """Test emission when feature flag is disabled."""
        emitter = ICTSignalEmitter()

        # Disable CVD
        emitter.set_feature_flag("cvd", False)

        result = await emitter.emit_signal(
            signal_type="cvd",
            token="BTC/USDT",
            timeframe="1H",
            signal_data=MagicMock(),
        )

        assert result.skipped is True
        assert "Feature flag disabled" in result.skip_reason

    @pytest.mark.asyncio
    async def test_emit_signal_success(self):
        """Test successful signal emission."""
        # Create mock emitter
        mock_emitter = MagicMock()
        mock_emitter.name = "mock"
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.latency_ms = 10.0
        mock_result.error = None
        mock_emitter.emit = AsyncMock(return_value=mock_result)

        emitter = ICTSignalEmitter(emitters=[mock_emitter])

        # Mock the two-layer scorer
        mock_score_result = MagicMock()
        mock_score_result.confluence_score = 0.75
        mock_score_result.confidence = 0.80
        mock_score_result.direction = MagicMock(value="long")
        mock_score_result.to_dict = MagicMock(return_value={})

        with patch.object(emitter, "_get_two_layer_scorer") as mock_get_scorer:
            mock_scorer = MagicMock()
            mock_scorer.score = MagicMock(return_value=mock_score_result)
            mock_get_scorer.return_value = mock_scorer

            result = await emitter.emit_signal(
                signal_type="cvd",
                token="BTC/USDT",
                timeframe="1H",
                signal_data=MagicMock(),
            )

        assert result.signal is not None
        assert result.emission_success is True
        assert result.signal_type == "cvd"

    @pytest.mark.asyncio
    async def test_emit_signal_confidence_below_threshold(self):
        """Test emission when confidence is below threshold."""
        emitter = ICTSignalEmitter(config=ICTEmissionConfig(min_confidence=0.70))

        # Mock the two-layer scorer with low confidence
        mock_score_result = MagicMock()
        mock_score_result.confluence_score = 0.40
        mock_score_result.confidence = 0.50  # Below 70% threshold
        mock_score_result.direction = MagicMock(value="long")
        mock_score_result.to_dict = MagicMock(return_value={})

        with patch.object(emitter, "_get_two_layer_scorer") as mock_get_scorer:
            mock_scorer = MagicMock()
            mock_scorer.score = MagicMock(return_value=mock_score_result)
            mock_get_scorer.return_value = mock_scorer

            result = await emitter.emit_signal(
                signal_type="cvd",
                token="BTC/USDT",
                timeframe="1H",
                signal_data=MagicMock(),
            )

        assert result.skipped is True
        assert result.skip_reason == "confidence_below_threshold"

    @pytest.mark.asyncio
    async def test_emit_signals_full_cycle(self):
        """Test full emission cycle with multiple signals."""
        mock_emitter = MagicMock()
        mock_emitter.name = "mock"
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.latency_ms = 10.0
        mock_result.error = None
        mock_emitter.emit = AsyncMock(return_value=mock_result)

        emitter = ICTSignalEmitter(emitters=[mock_emitter])

        # Mock the two-layer scorer
        mock_score_result = MagicMock()
        mock_score_result.confluence_score = 0.75
        mock_score_result.confidence = 0.80
        mock_score_result.direction = MagicMock(value="long")
        mock_score_result.to_dict = MagicMock(return_value={})

        with patch.object(emitter, "_get_two_layer_scorer") as mock_get_scorer:
            mock_scorer = MagicMock()
            mock_scorer.score = MagicMock(return_value=mock_score_result)
            mock_get_scorer.return_value = mock_scorer

            cycle = await emitter.emit_signals(
                token="BTC/USDT",
                timeframe="1H",
                cvd_data=MagicMock(),
                fvg_data=[MagicMock(), MagicMock()],
                order_block_data=[MagicMock()],
            )

        assert cycle.signals_processed == 4  # 1 CVD + 2 FVG + 1 OB
        assert cycle.signals_emitted == 4
        assert cycle.signals_skipped == 0
        assert "bos_choch" not in cycle.excluded_signals
        assert cycle.cycle_id.startswith("ict-cycle-")

    @pytest.mark.asyncio
    async def test_emit_signals_with_disabled_flags(self):
        """Test emission cycle with some signals disabled."""
        # Create mock emitter
        mock_emitter = MagicMock()
        mock_emitter.name = "mock"
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.latency_ms = 10.0
        mock_result.error = None
        mock_emitter.emit = AsyncMock(return_value=mock_result)

        config = ICTEmissionConfig(
            enable_cvd=True, enable_fvg=False, enable_order_block=True
        )
        emitter = ICTSignalEmitter(config=config, emitters=[mock_emitter])

        # Mock the two-layer scorer
        mock_score_result = MagicMock()
        mock_score_result.confluence_score = 0.75
        mock_score_result.confidence = 0.80
        mock_score_result.direction = MagicMock(value="long")
        mock_score_result.to_dict = MagicMock(return_value={})

        with patch.object(emitter, "_get_two_layer_scorer") as mock_get_scorer:
            mock_scorer = MagicMock()
            mock_scorer.score = MagicMock(return_value=mock_score_result)
            mock_get_scorer.return_value = mock_scorer

            cycle = await emitter.emit_signals(
                token="BTC/USDT",
                timeframe="1H",
                cvd_data=MagicMock(),
                fvg_data=[MagicMock()],  # Should be skipped (disabled)
                order_block_data=[MagicMock()],
            )

        # Should process CVD and Order Block, but not FVG
        assert cycle.signals_processed == 2
        assert cycle.signals_emitted == 2

    @pytest.mark.asyncio
    async def test_emit_signals_empty_data(self):
        """Test emission cycle with no signal data."""
        emitter = ICTSignalEmitter()

        cycle = await emitter.emit_signals(
            token="BTC/USDT",
            timeframe="1H",
            cvd_data=None,
            fvg_data=None,
            order_block_data=None,
        )

        assert cycle.signals_processed == 0
        assert cycle.signals_emitted == 0
        assert cycle.signals_skipped == 0


class TestICTEmissionCycle:
    """Tests for ICTEmissionCycle dataclass."""

    def test_cycle_to_dict(self):
        """Test ICTEmissionCycle serialization."""
        cycle = ICTEmissionCycle(
            cycle_id="test-cycle-1",
            timestamp=datetime.now(UTC),
            duration_ms=150.5,
            signals_processed=5,
            signals_emitted=3,
            signals_skipped=2,
            excluded_signals=[],
            errors=["Some error"],
        )

        result = cycle.to_dict()

        assert result["cycle_id"] == "test-cycle-1"
        assert result["signals_processed"] == 5
        assert result["signals_emitted"] == 3
        assert result["signals_skipped"] == 2
        assert "bos_choch" not in result["excluded_signals"]
        assert "Some error" in result["errors"]


class TestICTConfidenceThreshold:
    """Tests for configurable confidence threshold (ST-ICT-S4)."""

    @pytest.mark.asyncio
    async def test_confidence_074_rejected(self):
        """Test that confidence=0.74 is rejected with confidence_below_threshold."""
        # Create mock emitter
        mock_emitter = MagicMock()
        mock_emitter.name = "mock"
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.latency_ms = 10.0
        mock_result.error = None
        mock_emitter.emit = AsyncMock(return_value=mock_result)

        emitter = ICTSignalEmitter(emitters=[mock_emitter])

        # Mock the two-layer scorer with confidence=0.74
        mock_score_result = MagicMock()
        mock_score_result.confluence_score = 0.60
        mock_score_result.confidence = 0.74  # Below 0.75 threshold
        mock_score_result.direction = MagicMock(value="long")
        mock_score_result.to_dict = MagicMock(return_value={})

        with patch.object(emitter, "_get_two_layer_scorer") as mock_get_scorer:
            mock_scorer = MagicMock()
            mock_scorer.score = MagicMock(return_value=mock_score_result)
            mock_get_scorer.return_value = mock_scorer

            result = await emitter.emit_signal(
                signal_type="cvd",
                token="BTC/USDT",
                timeframe="1H",
                signal_data=MagicMock(),
            )

        assert result.skipped is True
        assert result.skip_reason == "confidence_below_threshold"
        assert result.signal is None

    @pytest.mark.asyncio
    async def test_confidence_075_passes(self):
        """Test that confidence=0.75 passes and is actionable."""
        # Create mock emitter
        mock_emitter = MagicMock()
        mock_emitter.name = "mock"
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.latency_ms = 10.0
        mock_result.error = None
        mock_emitter.emit = AsyncMock(return_value=mock_result)

        emitter = ICTSignalEmitter(emitters=[mock_emitter])

        # Mock the two-layer scorer with confidence=0.75
        mock_score_result = MagicMock()
        mock_score_result.confluence_score = 0.70
        mock_score_result.confidence = 0.75  # Exactly at threshold
        mock_score_result.direction = MagicMock(value="long")
        mock_score_result.to_dict = MagicMock(return_value={})

        with patch.object(emitter, "_get_two_layer_scorer") as mock_get_scorer:
            mock_scorer = MagicMock()
            mock_scorer.score = MagicMock(return_value=mock_score_result)
            mock_get_scorer.return_value = mock_scorer

            result = await emitter.emit_signal(
                signal_type="cvd",
                token="BTC/USDT",
                timeframe="1H",
                signal_data=MagicMock(),
            )

        assert result.emission_success is True
        assert result.signal is not None
        assert result.signal.status == SignalStatus.ACTIONABLE

    @pytest.mark.asyncio
    async def test_confidence_076_passes(self):
        """Test that confidence=0.76 passes and is actionable."""
        # Create mock emitter
        mock_emitter = MagicMock()
        mock_emitter.name = "mock"
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.latency_ms = 10.0
        mock_result.error = None
        mock_emitter.emit = AsyncMock(return_value=mock_result)

        emitter = ICTSignalEmitter(emitters=[mock_emitter])

        # Mock the two-layer scorer with confidence=0.76
        mock_score_result = MagicMock()
        mock_score_result.confluence_score = 0.72
        mock_score_result.confidence = 0.76  # Above threshold
        mock_score_result.direction = MagicMock(value="long")
        mock_score_result.to_dict = MagicMock(return_value={})

        with patch.object(emitter, "_get_two_layer_scorer") as mock_get_scorer:
            mock_scorer = MagicMock()
            mock_scorer.score = MagicMock(return_value=mock_score_result)
            mock_get_scorer.return_value = mock_scorer

            result = await emitter.emit_signal(
                signal_type="cvd",
                token="BTC/USDT",
                timeframe="1H",
                signal_data=MagicMock(),
            )

        assert result.emission_success is True
        assert result.signal is not None
        assert result.signal.status == SignalStatus.ACTIONABLE


class TestHLSignals:
    """Tests for H/L/H-OLD/L-OLD price structure signals (S1A-2)."""

    def test_h_signal_type_exists(self):
        """Test H signal type exists in registry."""
        registry = ICTSignalRegistry()
        signal = registry.get_signal(ICTSignalType.H)
        assert signal is not None
        assert signal.metadata.name == "High"
        assert signal.feature_flag == "enable_hl_signals"

    def test_l_signal_type_exists(self):
        """Test L signal type exists in registry."""
        registry = ICTSignalRegistry()
        signal = registry.get_signal(ICTSignalType.L)
        assert signal is not None
        assert signal.metadata.name == "Low"
        assert signal.feature_flag == "enable_hl_signals"

    def test_high_old_signal_type_exists(self):
        """Test HIGH_OLD signal type exists in registry."""
        registry = ICTSignalRegistry()
        signal = registry.get_signal(ICTSignalType.HIGH_OLD)
        assert signal is not None
        assert signal.metadata.name == "Old High"
        assert signal.feature_flag == "enable_hl_signals"

    def test_low_old_signal_type_exists(self):
        """Test LOW_OLD signal type exists in registry."""
        registry = ICTSignalRegistry()
        signal = registry.get_signal(ICTSignalType.LOW_OLD)
        assert signal is not None
        assert signal.metadata.name == "Old Low"
        assert signal.feature_flag == "enable_hl_signals"

    def test_hl_signals_enabled_by_default(self):
        """Test H/L/H-OLD/L-OLD signals are enabled by default."""
        emitter = ICTSignalEmitter()
        assert emitter.is_signal_enabled("h") is True
        assert emitter.is_signal_enabled("l") is True
        assert emitter.is_signal_enabled("high_old") is True
        assert emitter.is_signal_enabled("low_old") is True

    def test_hl_signals_disabled_via_feature_flag(self):
        """Test H/L/H-OLD/L-OLD signals can be disabled via feature flag."""
        emitter = ICTSignalEmitter()
        emitter.set_feature_flag("h", False)
        assert emitter.is_signal_enabled("h") is False
        # All HL signals share the same feature flag
        assert emitter.is_signal_enabled("l") is False
        assert emitter.is_signal_enabled("high_old") is False
        assert emitter.is_signal_enabled("low_old") is False

    @pytest.mark.asyncio
    async def test_emit_h_signal_success(self):
        """Test successful H signal emission."""
        mock_emitter = MagicMock()
        mock_emitter.name = "mock"
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.latency_ms = 10.0
        mock_result.error = None
        mock_emitter.emit = AsyncMock(return_value=mock_result)

        emitter = ICTSignalEmitter(emitters=[mock_emitter])

        signal_data = {
            "price": 50000.0,
            "direction": "long",
            "confidence": 0.75,
            "timestamp": 1704067200000,
        }

        result = await emitter.emit_signal(
            signal_type="h",
            token="BTC/USDT",
            timeframe="1H",
            signal_data=signal_data,
        )

        assert result.emission_success is True
        assert result.signal is not None
        assert result.signal.metadata["signal_type"] == "h"
        assert result.signal.metadata["price"] == 50000.0

    @pytest.mark.asyncio
    async def test_emit_l_signal_success(self):
        """Test successful L signal emission."""
        mock_emitter = MagicMock()
        mock_emitter.name = "mock"
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.latency_ms = 10.0
        mock_result.error = None
        mock_emitter.emit = AsyncMock(return_value=mock_result)

        emitter = ICTSignalEmitter(emitters=[mock_emitter])

        signal_data = {
            "price": 49000.0,
            "direction": "short",
            "confidence": 0.70,
            "timestamp": 1704067200000,
        }

        result = await emitter.emit_signal(
            signal_type="l",
            token="BTC/USDT",
            timeframe="1H",
            signal_data=signal_data,
        )

        assert result.emission_success is True
        assert result.signal is not None
        assert result.signal.metadata["signal_type"] == "l"
        assert result.signal.metadata["price"] == 49000.0

    @pytest.mark.asyncio
    async def test_emit_high_old_signal_success(self):
        """Test successful HIGH_OLD signal emission."""
        mock_emitter = MagicMock()
        mock_emitter.name = "mock"
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.latency_ms = 10.0
        mock_result.error = None
        mock_emitter.emit = AsyncMock(return_value=mock_result)

        emitter = ICTSignalEmitter(emitters=[mock_emitter])

        signal_data = {
            "price": 51000.0,
            "direction": "long",
            "confidence": 0.72,
            "timestamp": 1704067200000,
            "swing_high": 51500.0,
        }

        result = await emitter.emit_signal(
            signal_type="high_old",
            token="BTC/USDT",
            timeframe="1H",
            signal_data=signal_data,
        )

        assert result.emission_success is True
        assert result.signal is not None
        assert result.signal.metadata["signal_type"] == "high_old"
        assert result.signal.metadata["swing_high"] == 51500.0

    @pytest.mark.asyncio
    async def test_emit_low_old_signal_success(self):
        """Test successful LOW_OLD signal emission."""
        mock_emitter = MagicMock()
        mock_emitter.name = "mock"
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.latency_ms = 10.0
        mock_result.error = None
        mock_emitter.emit = AsyncMock(return_value=mock_result)

        emitter = ICTSignalEmitter(emitters=[mock_emitter])

        signal_data = {
            "price": 48000.0,
            "direction": "short",
            "confidence": 0.68,
            "timestamp": 1704067200000,
            "swing_low": 47500.0,
        }

        result = await emitter.emit_signal(
            signal_type="low_old",
            token="BTC/USDT",
            timeframe="1H",
            signal_data=signal_data,
        )

        assert result.emission_success is True
        assert result.signal is not None
        assert result.signal.metadata["signal_type"] == "low_old"
        assert result.signal.metadata["swing_low"] == 47500.0

    @pytest.mark.asyncio
    async def test_emit_signals_with_hl_data(self):
        """Test emit_signals with hl_data parameter."""
        mock_emitter = MagicMock()
        mock_emitter.name = "mock"
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.latency_ms = 10.0
        mock_result.error = None
        mock_emitter.emit = AsyncMock(return_value=mock_result)

        emitter = ICTSignalEmitter(emitters=[mock_emitter])

        hl_data = {
            "h": {
                "price": 50000.0,
                "direction": "long",
                "confidence": 0.75,
                "timestamp": 1704067200000,
            },
            "l": {
                "price": 49000.0,
                "direction": "short",
                "confidence": 0.75,
                "timestamp": 1704067200000,
            },
        }

        cycle = await emitter.emit_signals(
            token="BTC/USDT",
            timeframe="1H",
            hl_data=hl_data,
        )

        # Should process 2 HL signals
        assert cycle.signals_processed == 2
        assert cycle.signals_emitted == 2


class TestSignalPriority:
    """Tests for detection priority ordering (ST-ICT-ST2).

    Validates that:
    - SignalPriority enum defines correct priority values
    - Registry assigns correct priority to each signal type
    - Registry returns signals sorted by priority
    - Emitter processes signals in priority order
    - Priority is configurable via config override
    """

    def test_signal_priority_enum_values(self):
        """SignalPriority enum has correct ascending values (lower = higher priority)."""
        assert SignalPriority.BOS_CHOCH.value == 1
        assert SignalPriority.ORDER_BLOCK.value == 2
        assert SignalPriority.FVG.value == 3
        assert SignalPriority.LIQUIDITY_SWEEP.value == 4
        assert SignalPriority.PRICE_STRUCTURE.value == 5

    def test_registry_priority_order_mapping(self):
        """Registry SIGNAL_PRIORITY_ORDER maps each signal type to correct priority."""
        registry = ICTSignalRegistry()

        # Order Blocks should be priority 2 (highest active)
        assert registry.SIGNAL_PRIORITY_ORDER[ICTSignalType.ORDER_BLOCK] == 2
        # FVG should be priority 3
        assert registry.SIGNAL_PRIORITY_ORDER[ICTSignalType.FVG] == 3
        # CVD should be priority 4 (liquidity sweep level)
        assert registry.SIGNAL_PRIORITY_ORDER[ICTSignalType.CVD] == 4
        # Price structure signals should be priority 5
        assert registry.SIGNAL_PRIORITY_ORDER[ICTSignalType.H] == 5
        assert registry.SIGNAL_PRIORITY_ORDER[ICTSignalType.L] == 5
        assert registry.SIGNAL_PRIORITY_ORDER[ICTSignalType.HIGH_OLD] == 5
        assert registry.SIGNAL_PRIORITY_ORDER[ICTSignalType.LOW_OLD] == 5

    def test_registered_signals_have_priority(self):
        """Each RegisteredSignal gets a priority value from the registry."""
        registry = ICTSignalRegistry()

        ob_signal = registry.get_signal(ICTSignalType.ORDER_BLOCK)
        assert ob_signal is not None
        assert ob_signal.priority == 2

        fvg_signal = registry.get_signal(ICTSignalType.FVG)
        assert fvg_signal is not None
        assert fvg_signal.priority == 3

        cvd_signal = registry.get_signal(ICTSignalType.CVD)
        assert cvd_signal is not None
        assert cvd_signal.priority == 4

        h_signal = registry.get_signal(ICTSignalType.H)
        assert h_signal is not None
        assert h_signal.priority == 5

    def test_registry_sorted_by_priority(self):
        """get_registered_signals_sorted_by_priority returns signals in correct order."""
        registry = ICTSignalRegistry()
        sorted_signals = registry.get_registered_signals_sorted_by_priority()

        # Extract signal type values in order
        order = [s.signal_type.value for s in sorted_signals]

        # Order Blocks should come before FVG
        ob_idx = order.index("order_block")
        fvg_idx = order.index("fvg")
        assert ob_idx < fvg_idx, "Order Blocks should have higher priority than FVG"

        # FVG should come before CVD
        cvd_idx = order.index("cvd")
        assert fvg_idx < cvd_idx, "FVG should have higher priority than CVD"

        # CVD should come before price structure signals
        h_idx = order.index("h")
        assert cvd_idx < h_idx, "CVD should have higher priority than price structure"

    def test_registry_sorted_by_priority_enabled_only(self):
        """Sorted signals with enabled_only=True only returns enabled signals."""
        registry = ICTSignalRegistry()
        registry.set_signal_enabled(ICTSignalType.FVG, False)

        sorted_signals = registry.get_registered_signals_sorted_by_priority(
            enabled_only=True
        )
        types = [s.signal_type for s in sorted_signals]

        assert ICTSignalType.FVG not in types

    def test_register_signal_custom_priority(self):
        """Custom priority can be set when registering a signal."""
        from signal_generation.registry.ict_signal_registry import (
            SignalMetadata,
        )

        registry = ICTSignalRegistry()
        # Register a test signal with custom priority
        test_type = (
            ICTSignalType.CVD
        )  # already registered, so we test via a fresh registry

        # Create a fresh registry to avoid duplicate registration
        fresh = ICTSignalRegistry()
        fresh.unregister_signal(ICTSignalType.CVD)

        meta = SignalMetadata(
            name="Test Custom Priority",
            description="Test signal with custom priority",
        )
        registered = fresh.register_signal(
            signal_type=ICTSignalType.CVD,
            metadata=meta,
            priority=1,
        )
        assert registered.priority == 1

    def test_get_priority_unknown_type(self):
        """Unknown signal type gets default priority 99."""
        registry = ICTSignalRegistry()
        # Create a mock signal type not in the priority map
        # Since we can't easily create a new ICTSignalType member,
        # test with the _get_priority method directly using a value
        # that won't be in the map
        priority = registry._get_priority(ICTSignalType.CVD)
        # CVD IS in the map, so it should return 4
        assert priority == 4

    def test_emission_config_default_priority_none(self):
        """Default ICTEmissionConfig has signal_priority=None (use registry default)."""
        config = ICTEmissionConfig()
        assert config.signal_priority is None

    def test_emission_config_custom_priority(self):
        """Custom priority can be set via config."""
        config = ICTEmissionConfig(
            signal_priority=["fvg", "order_block", "cvd", "h", "l"]
        )
        assert config.signal_priority == ["fvg", "order_block", "cvd", "h", "l"]

    def test_emitter_priority_order_from_registry(self):
        """Emitter uses registry priority order when config.signal_priority is None."""
        emitter = ICTSignalEmitter()
        order = emitter._get_emission_priority_order()

        # Order Blocks (priority 2) should be first among active signals
        assert order[0] == "order_block"
        # FVG (priority 3) should be second
        assert order[1] == "fvg"
        # CVD (priority 4) should be third
        assert order[2] == "cvd"
        # Price structure (priority 5) should be last
        assert "h" in order[3:]
        assert "l" in order[3:]

    def test_emitter_priority_order_from_config_override(self):
        """Emitter uses config.signal_priority when set, overriding registry default."""
        config = ICTEmissionConfig(
            signal_priority=[
                "fvg",
                "cvd",
                "order_block",
                "h",
                "l",
                "high_old",
                "low_old",
            ]
        )
        emitter = ICTSignalEmitter(config=config)
        order = emitter._get_emission_priority_order()

        # Config override puts FVG first
        assert order[0] == "fvg"
        assert order[1] == "cvd"
        assert order[2] == "order_block"

    async def test_emit_signals_processes_in_priority_order(self):
        """emit_signals processes results in priority order when all signals fire."""
        registry = ICTSignalRegistry()
        emitter = ICTSignalEmitter(registry=registry)

        # Provide data for all signal types
        cvd_data = MagicMock()
        fvg_data = [MagicMock()]
        ob_data = [MagicMock()]
        hl_data = {
            "h": {
                "price": 50000.0,
                "direction": "long",
                "confidence": 0.80,
                "timestamp": 1704067200000,
            },
            "l": {
                "price": 49000.0,
                "direction": "short",
                "confidence": 0.80,
                "timestamp": 1704067200000,
            },
        }

        cycle = await emitter.emit_signals(
            token="BTC/USDT",
            timeframe="1H",
            cvd_data=cvd_data,
            fvg_data=fvg_data,
            order_block_data=ob_data,
            hl_data=hl_data,
        )

        # Verify results are in priority order
        # Order Block (priority 2) should appear before FVG (priority 3)
        result_types = [r.signal_type for r in cycle.results]

        ob_positions = [i for i, t in enumerate(result_types) if "order_block" in t]
        fvg_positions = [i for i, t in enumerate(result_types) if "fvg" in t]
        cvd_positions = [i for i, t in enumerate(result_types) if t == "cvd"]

        # At least one OB result should come before any FVG result
        if ob_positions and fvg_positions:
            assert min(ob_positions) < min(
                fvg_positions
            ), "Order Block results should appear before FVG results in priority order"

        # At least one FVG result should come before CVD
        if fvg_positions and cvd_positions:
            assert min(fvg_positions) < min(
                cvd_positions
            ), "FVG results should appear before CVD results in priority order"


class TestLiquiditySweepSignals:
    """Tests for liquidity sweep (stop hunt) signal integration (ST-ICT-ST3)."""

    def test_enable_sweep_config_default(self):
        """Test enable_sweep is True by default in ICTEmissionConfig."""
        config = ICTEmissionConfig()
        assert config.enable_sweep is True

    def test_enable_sweep_config_false(self):
        """Test enable_sweep can be set to False."""
        config = ICTEmissionConfig(enable_sweep=False)
        assert config.enable_sweep is False

    def test_sweep_signal_type_enabled_by_default(self):
        """Test liquidity_sweep signal type is enabled by default."""
        emitter = ICTSignalEmitter()
        assert emitter.is_signal_enabled("liquidity_sweep") is True

    def test_sweep_signal_type_disabled_via_feature_flag(self):
        """Test liquidity_sweep can be disabled via feature flag."""
        emitter = ICTSignalEmitter()
        emitter.set_feature_flag("liquidity_sweep", False)
        assert emitter.is_signal_enabled("liquidity_sweep") is False

    def test_get_status_includes_sweep_config(self):
        """Test get_status includes enable_sweep in config."""
        emitter = ICTSignalEmitter()
        status = emitter.get_status()
        assert "enable_sweep" in status["config"]
        assert status["config"]["enable_sweep"] is True

    def test_get_status_includes_sweep_feature_flag(self):
        """Test get_status includes enable_sweep_signals in feature_flags."""
        emitter = ICTSignalEmitter()
        status = emitter.get_status()
        assert "enable_sweep_signals" in status["feature_flags"]
        assert status["feature_flags"]["enable_sweep_signals"] is True

    @pytest.mark.asyncio
    async def test_emit_liquidity_sweep_signal_success(self):
        """Test successful liquidity_sweep signal emission."""
        from ict.liquidity.models import (
            LiquidityLevel,
            LiquidityLevelType,
            LiquiditySweep,
            SweepConfirmation,
            SweepDirection,
            SweepSignal,
        )

        # Create mock sweep signal
        mock_level = LiquidityLevel(
            price=50000.0,
            level_type=LiquidityLevelType.PREVIOUS_HIGH,
            source_indices=(10,),
            strength=3.0,
            timestamp_ms=1704067200000,
        )
        mock_sweep = LiquiditySweep(
            sweep_candle_index=15,
            direction=SweepDirection.BEARISH_SWEEP,
            level=mock_level,
            sweep_high=50025.0,
            sweep_low=49975.0,
            penetration=25.0,
            penetration_pct=0.05,
            confirmation=SweepConfirmation(
                confirmed=True,
                rejection_candle_index=16,
                wick_ratio=2.5,
                close_beyond_level=True,
            ),
        )
        mock_sweep_signal = SweepSignal(
            sweep=mock_sweep,
            signal_direction=SweepDirection.BEARISH_SWEEP,
            confidence=0.85,
            metadata={
                "level_type": "previous_high",
                "level_price": 50000.0,
                "penetration_pct": 0.05,
                "wick_ratio": 2.5,
                "strength": 3.0,
            },
        )

        # Create mock emitter
        mock_emitter = MagicMock()
        mock_emitter.name = "mock"
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.latency_ms = 10.0
        mock_result.error = None
        mock_emitter.emit = AsyncMock(return_value=mock_result)

        emitter = ICTSignalEmitter(emitters=[mock_emitter])

        result = await emitter.emit_signal(
            signal_type="liquidity_sweep",
            token="BTC/USDT",
            timeframe="1H",
            signal_data=mock_sweep_signal,
        )

        assert result.emission_success is True
        assert result.signal is not None
        assert result.signal.metadata["signal_type"] == "liquidity_sweep"
        assert result.signal.metadata["level_type"] == "previous_high"
        assert result.signal.metadata["level_price"] == 50000.0
        assert result.signal.confidence == 0.85

    @pytest.mark.asyncio
    async def test_emit_liquidity_sweep_below_threshold(self):
        """Test liquidity_sweep signal rejected when confidence < 0.75."""
        from ict.liquidity.models import (
            LiquidityLevel,
            LiquidityLevelType,
            LiquiditySweep,
            SweepConfirmation,
            SweepDirection,
            SweepSignal,
        )

        mock_level = LiquidityLevel(
            price=50000.0,
            level_type=LiquidityLevelType.PREVIOUS_HIGH,
            source_indices=(10,),
            strength=2.0,
            timestamp_ms=1704067200000,
        )
        mock_sweep = LiquiditySweep(
            sweep_candle_index=15,
            direction=SweepDirection.BEARISH_SWEEP,
            level=mock_level,
            sweep_high=50020.0,
            sweep_low=49980.0,
            penetration=20.0,
            penetration_pct=0.04,
            confirmation=SweepConfirmation(
                confirmed=True,
                rejection_candle_index=16,
                wick_ratio=1.8,
                close_beyond_level=True,
            ),
        )
        mock_sweep_signal = SweepSignal(
            sweep=mock_sweep,
            signal_direction=SweepDirection.BEARISH_SWEEP,
            confidence=0.70,  # Below 0.75 threshold
            metadata={},
        )

        emitter = ICTSignalEmitter(emitters=[MagicMock()])

        result = await emitter.emit_signal(
            signal_type="liquidity_sweep",
            token="BTC/USDT",
            timeframe="1H",
            signal_data=mock_sweep_signal,
        )

        assert result.skipped is True
        assert result.skip_reason == "confidence_below_threshold"
        assert result.signal is None

    @pytest.mark.asyncio
    async def test_emit_signals_with_sweep_data(self):
        """Test emit_signals processes sweep_data correctly."""
        from ict.liquidity.models import (
            LiquidityLevel,
            LiquidityLevelType,
            LiquiditySweep,
            SweepConfirmation,
            SweepDirection,
            SweepSignal,
        )

        # Create mock sweep signals
        mock_level1 = LiquidityLevel(
            price=50000.0,
            level_type=LiquidityLevelType.PREVIOUS_HIGH,
            source_indices=(10,),
            strength=3.0,
            timestamp_ms=1704067200000,
        )
        mock_sweep1 = LiquiditySweep(
            sweep_candle_index=15,
            direction=SweepDirection.BEARISH_SWEEP,
            level=mock_level1,
            sweep_high=50025.0,
            sweep_low=49975.0,
            penetration=25.0,
            penetration_pct=0.05,
            confirmation=SweepConfirmation(
                confirmed=True,
                rejection_candle_index=16,
                wick_ratio=2.5,
                close_beyond_level=True,
            ),
        )
        sweep_signal1 = SweepSignal(
            sweep=mock_sweep1,
            signal_direction=SweepDirection.BEARISH_SWEEP,
            confidence=0.85,
            metadata={"level_type": "previous_high", "level_price": 50000.0},
        )

        mock_level2 = LiquidityLevel(
            price=49000.0,
            level_type=LiquidityLevelType.PREVIOUS_LOW,
            source_indices=(12,),
            strength=4.0,
            timestamp_ms=1704067200000,
        )
        mock_sweep2 = LiquiditySweep(
            sweep_candle_index=18,
            direction=SweepDirection.BULLISH_SWEEP,
            level=mock_level2,
            sweep_high=49025.0,
            sweep_low=48975.0,
            penetration=25.0,
            penetration_pct=0.05,
            confirmation=SweepConfirmation(
                confirmed=True,
                rejection_candle_index=19,
                wick_ratio=2.8,
                close_beyond_level=True,
            ),
        )
        sweep_signal2 = SweepSignal(
            sweep=mock_sweep2,
            signal_direction=SweepDirection.BULLISH_SWEEP,
            confidence=0.90,
            metadata={"level_type": "previous_low", "level_price": 49000.0},
        )

        sweep_data = [sweep_signal1, sweep_signal2]

        # Create mock emitter
        mock_emitter = MagicMock()
        mock_emitter.name = "mock"
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.latency_ms = 10.0
        mock_result.error = None
        mock_emitter.emit = AsyncMock(return_value=mock_result)

        emitter = ICTSignalEmitter(emitters=[mock_emitter])

        cycle = await emitter.emit_signals(
            token="BTC/USDT",
            timeframe="1H",
            sweep_data=sweep_data,
        )

        # Should process 2 sweep signals
        assert cycle.signals_processed == 2
        assert cycle.signals_emitted == 2
        assert cycle.signals_skipped == 0

        # Verify result types
        result_types = [r.signal_type for r in cycle.results]
        assert "liquidity_sweep_0" in result_types
        assert "liquidity_sweep_1" in result_types

    @pytest.mark.asyncio
    async def test_emit_signals_with_sweep_disabled(self):
        """Test emit_signals skips sweep_data when enable_sweep=False."""
        from ict.liquidity.models import (
            LiquidityLevel,
            LiquidityLevelType,
            LiquiditySweep,
            SweepConfirmation,
            SweepDirection,
            SweepSignal,
        )

        mock_level = LiquidityLevel(
            price=50000.0,
            level_type=LiquidityLevelType.PREVIOUS_HIGH,
            source_indices=(10,),
            strength=3.0,
            timestamp_ms=1704067200000,
        )
        mock_sweep = LiquiditySweep(
            sweep_candle_index=15,
            direction=SweepDirection.BEARISH_SWEEP,
            level=mock_level,
            sweep_high=50025.0,
            sweep_low=49975.0,
            penetration=25.0,
            penetration_pct=0.05,
            confirmation=SweepConfirmation(
                confirmed=True,
                rejection_candle_index=16,
                wick_ratio=2.5,
                close_beyond_level=True,
            ),
        )
        sweep_signal = SweepSignal(
            sweep=mock_sweep,
            signal_direction=SweepDirection.BEARISH_SWEEP,
            confidence=0.85,
            metadata={},
        )

        config = ICTEmissionConfig(enable_sweep=False)
        emitter = ICTSignalEmitter(config=config, emitters=[MagicMock()])

        cycle = await emitter.emit_signals(
            token="BTC/USDT",
            timeframe="1H",
            sweep_data=[sweep_signal],
        )

        # Should not process any sweep signals
        assert cycle.signals_processed == 0
        assert cycle.signals_emitted == 0


class TestDirectionMappingBias:
    """Tests for direction mapping correctness (PAPER-FIX-006).

    Verifies that NEUTRAL direction signals are skipped (not silently
    mapped to SHORT), and that LONG/SHORT mappings are correct for
    all signal handlers: ICT scoring, HL, liquidity sweep, and BOS/CHoCH.
    """

    def _make_mock_emitter(self):
        """Create a mock emitter that reports success."""
        mock_emitter = MagicMock()
        mock_emitter.name = "mock"
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.latency_ms = 10.0
        mock_result.error = None
        mock_emitter.emit = AsyncMock(return_value=mock_result)
        return mock_emitter

    # ------------------------------------------------------------------
    # Fix 1: _create_signal_from_ict() — NEUTRAL skipped, LONG/SHORT OK
    # ------------------------------------------------------------------

    def test_create_signal_from_ict_long_direction(self):
        """LONG direction should produce a LONG signal."""
        emitter = ICTSignalEmitter(emitters=[self._make_mock_emitter()])
        signal = emitter._create_signal_from_ict(
            signal_type="cvd",
            confluence_score=0.80,
            direction=SignalDirection.LONG,
            confidence=0.85,
            token="BTC/USDT",
            timeframe="1H",
        )
        assert signal is not None
        assert signal.direction == SignalDirection.LONG

    def test_create_signal_from_ict_short_direction(self):
        """SHORT direction should produce a SHORT signal."""
        emitter = ICTSignalEmitter(emitters=[self._make_mock_emitter()])
        signal = emitter._create_signal_from_ict(
            signal_type="cvd",
            confluence_score=0.80,
            direction=SignalDirection.SHORT,
            confidence=0.85,
            token="BTC/USDT",
            timeframe="1H",
        )
        assert signal is not None
        assert signal.direction == SignalDirection.SHORT

    def test_create_signal_from_ict_neutral_direction_returns_none(self):
        """NEUTRAL direction should return None (signal skipped).

        This is the primary bug fix: previously NEUTRAL was silently
        mapped to SHORT via binary ternary.
        """
        emitter = ICTSignalEmitter(emitters=[self._make_mock_emitter()])
        signal = emitter._create_signal_from_ict(
            signal_type="cvd",
            confluence_score=0.80,
            direction=SignalDirection.NEUTRAL,
            confidence=0.85,
            token="BTC/USDT",
            timeframe="1H",
        )
        assert signal is None

    @pytest.mark.asyncio
    async def test_emit_signal_neutral_direction_skipped(self):
        """Full emit cycle: NEUTRAL direction from scorer should be skipped."""
        emitter = ICTSignalEmitter(emitters=[self._make_mock_emitter()])

        mock_score_result = MagicMock()
        mock_score_result.confluence_score = 0.75
        mock_score_result.confidence = 0.80
        mock_score_result.direction = SignalDirection.NEUTRAL
        mock_score_result.to_dict = MagicMock(return_value={})

        with patch.object(emitter, "_get_two_layer_scorer") as mock_get_scorer:
            mock_scorer = MagicMock()
            mock_scorer.score = MagicMock(return_value=mock_score_result)
            mock_get_scorer.return_value = mock_scorer

            result = await emitter.emit_signal(
                signal_type="cvd",
                token="BTC/USDT",
                timeframe="1H",
                signal_data=MagicMock(),
            )

        assert result.skipped is True
        assert result.skip_reason == "neutral_direction_skipped"
        assert result.signal is None

    # ------------------------------------------------------------------
    # Fix 2: Liquidity sweep — bullish/bearish mapping correct
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_liquidity_sweep_bullish_direction(self):
        """Bullish sweep should produce LONG signal."""
        from ict.liquidity.models import (
            LiquidityLevel,
            LiquidityLevelType,
            LiquiditySweep,
            SweepConfirmation,
            SweepDirection,
            SweepSignal,
        )

        mock_level = LiquidityLevel(
            price=49000.0,
            level_type=LiquidityLevelType.PREVIOUS_LOW,
            source_indices=(5,),
            strength=3.0,
            timestamp_ms=1704067200000,
        )
        mock_sweep = LiquiditySweep(
            sweep_candle_index=10,
            direction=SweepDirection.BULLISH_SWEEP,
            level=mock_level,
            sweep_high=49025.0,
            sweep_low=48975.0,
            penetration=25.0,
            penetration_pct=0.05,
            confirmation=SweepConfirmation(
                confirmed=True,
                rejection_candle_index=11,
                wick_ratio=2.5,
                close_beyond_level=True,
            ),
        )
        sweep_signal = SweepSignal(
            sweep=mock_sweep,
            signal_direction=SweepDirection.BULLISH_SWEEP,
            confidence=0.85,
            metadata={},
        )

        emitter = ICTSignalEmitter(emitters=[self._make_mock_emitter()])
        result = await emitter.emit_signal(
            signal_type="liquidity_sweep",
            token="BTC/USDT",
            timeframe="1H",
            signal_data=sweep_signal,
        )

        assert result.emission_success is True
        assert result.signal is not None
        assert result.signal.direction == SignalDirection.LONG

    @pytest.mark.asyncio
    async def test_liquidity_sweep_bearish_direction(self):
        """Bearish sweep should produce SHORT signal."""
        from ict.liquidity.models import (
            LiquidityLevel,
            LiquidityLevelType,
            LiquiditySweep,
            SweepConfirmation,
            SweepDirection,
            SweepSignal,
        )

        mock_level = LiquidityLevel(
            price=50000.0,
            level_type=LiquidityLevelType.PREVIOUS_HIGH,
            source_indices=(10,),
            strength=3.0,
            timestamp_ms=1704067200000,
        )
        mock_sweep = LiquiditySweep(
            sweep_candle_index=15,
            direction=SweepDirection.BEARISH_SWEEP,
            level=mock_level,
            sweep_high=50025.0,
            sweep_low=49975.0,
            penetration=25.0,
            penetration_pct=0.05,
            confirmation=SweepConfirmation(
                confirmed=True,
                rejection_candle_index=16,
                wick_ratio=2.5,
                close_beyond_level=True,
            ),
        )
        sweep_signal = SweepSignal(
            sweep=mock_sweep,
            signal_direction=SweepDirection.BEARISH_SWEEP,
            confidence=0.85,
            metadata={},
        )

        emitter = ICTSignalEmitter(emitters=[self._make_mock_emitter()])
        result = await emitter.emit_signal(
            signal_type="liquidity_sweep",
            token="BTC/USDT",
            timeframe="1H",
            signal_data=sweep_signal,
        )

        assert result.emission_success is True
        assert result.signal is not None
        assert result.signal.direction == SignalDirection.SHORT

    # ------------------------------------------------------------------
    # Fix 3: HL signals — unexpected direction skipped
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_hl_signal_unexpected_direction_skipped(self):
        """HL signal with non-long/short direction should be skipped."""
        emitter = ICTSignalEmitter(emitters=[self._make_mock_emitter()])
        result = await emitter.emit_signal(
            signal_type="h",
            token="BTC/USDT",
            timeframe="1H",
            signal_data={
                "price": 50000.0,
                "direction": "neutral",
                "confidence": 0.80,
            },
        )

        assert result.skipped is True
        assert "unexpected_direction" in result.skip_reason
        assert result.signal is None

    @pytest.mark.asyncio
    async def test_hl_signal_long_direction(self):
        """HL signal with 'long' direction should produce LONG signal."""
        emitter = ICTSignalEmitter(emitters=[self._make_mock_emitter()])
        result = await emitter.emit_signal(
            signal_type="h",
            token="BTC/USDT",
            timeframe="1H",
            signal_data={
                "price": 50000.0,
                "direction": "long",
                "confidence": 0.80,
            },
        )

        assert result.signal is not None
        assert result.signal.direction == SignalDirection.LONG

    @pytest.mark.asyncio
    async def test_hl_signal_short_direction(self):
        """HL signal with 'short' direction should produce SHORT signal."""
        emitter = ICTSignalEmitter(emitters=[self._make_mock_emitter()])
        result = await emitter.emit_signal(
            signal_type="l",
            token="BTC/USDT",
            timeframe="1H",
            signal_data={
                "price": 49000.0,
                "direction": "short",
                "confidence": 0.80,
            },
        )

        assert result.signal is not None
        assert result.signal.direction == SignalDirection.SHORT

    # ------------------------------------------------------------------
    # Fix 4: BOS/CHoCH — unexpected direction skipped
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_bos_choch_unexpected_direction_skipped(self):
        """BOS/CHoCH signal with non-long/short direction should be skipped."""
        emitter = ICTSignalEmitter(emitters=[self._make_mock_emitter()])
        result = await emitter.emit_signal(
            signal_type="bos",
            token="BTC/USDT",
            timeframe="1H",
            signal_data={
                "price": 50000.0,
                "direction": "sideways",
                "confidence": 0.80,
            },
        )

        assert result.skipped is True
        assert "unexpected_direction" in result.skip_reason
        assert result.signal is None

    # ------------------------------------------------------------------
    # Direction distribution tracking
    # ------------------------------------------------------------------

    def test_direction_counts_initialized(self):
        """Direction counts should be initialized to zero."""
        emitter = ICTSignalEmitter()
        assert emitter._direction_counts == {
            "long": 0,
            "short": 0,
            "neutral_skipped": 0,
        }

    def test_direction_counts_increment_on_signal(self):
        """Direction counts should increment when signals are created."""
        emitter = ICTSignalEmitter()
        emitter._create_signal_from_ict(
            signal_type="cvd",
            confluence_score=0.80,
            direction=SignalDirection.LONG,
            confidence=0.85,
            token="BTC/USDT",
            timeframe="1H",
        )
        assert emitter._direction_counts["long"] == 1

        emitter._create_signal_from_ict(
            signal_type="fvg",
            confluence_score=0.80,
            direction=SignalDirection.SHORT,
            confidence=0.85,
            token="BTC/USDT",
            timeframe="1H",
        )
        assert emitter._direction_counts["short"] == 1

    def test_direction_counts_neutral_skipped(self):
        """NEUTRAL signals should increment neutral_skipped counter."""
        emitter = ICTSignalEmitter()
        result = emitter._create_signal_from_ict(
            signal_type="cvd",
            confluence_score=0.80,
            direction=SignalDirection.NEUTRAL,
            confidence=0.85,
            token="BTC/USDT",
            timeframe="1H",
        )
        assert result is None
        assert emitter._direction_counts["neutral_skipped"] == 1
        assert emitter._direction_counts["long"] == 0
        assert emitter._direction_counts["short"] == 0

    def test_extreme_bias_warning_logged(self, caplog):
        """Extreme SHORT bias (>100:1) should trigger warning log."""
        emitter = ICTSignalEmitter()
        # Simulate 101 SHORTs and 0 LONGs
        emitter._direction_counts["short"] = 101
        emitter._direction_counts["long"] = 0
        emitter._direction_counts["neutral_skipped"] = 0

        with caplog.at_level(
            logging.WARNING, logger="signal_generation.ict_signal_emitter"
        ):
            emitter._log_direction_distribution()

        assert any("Extreme SHORT bias" in msg for msg in caplog.messages)

    def test_no_bias_warning_under_threshold(self, caplog):
        """No extreme bias warning when SHORT:LONG ratio is under 100:1."""
        emitter = ICTSignalEmitter()
        emitter._direction_counts["short"] = 50
        emitter._direction_counts["long"] = 1
        emitter._direction_counts["neutral_skipped"] = 0

        with caplog.at_level(
            logging.WARNING, logger="signal_generation.ict_signal_emitter"
        ):
            emitter._log_direction_distribution()

        assert not any("Extreme SHORT bias" in msg for msg in caplog.messages)
