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

    def test_check_bos_choch_exclusion(self):
        """Test BOS/CHoCH exclusion check."""
        emitter = ICTSignalEmitter()

        # These should be excluded
        assert emitter._check_bos_choch_exclusion("bos") is True
        assert emitter._check_bos_choch_exclusion("choch") is True
        assert emitter._check_bos_choch_exclusion("bos_choch") is True
        assert emitter._check_bos_choch_exclusion("BOS") is True
        assert emitter._check_bos_choch_exclusion("CHOCH") is True

        # These should not be excluded
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

    def test_is_signal_enabled_bos_choch_excluded(self):
        """Test that BOS/CHoCH is always excluded."""
        emitter = ICTSignalEmitter()

        # BOS should always return False (excluded)
        assert emitter.is_signal_enabled("bos") is False
        assert emitter.is_signal_enabled("choch") is False
        assert emitter.is_signal_enabled("bos_choch") is False

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
        assert status["bos_choch_excluded"] is True
        assert status["bos_choch_exclusion_reference"] == "BL-BOS-CHOCH-001"
        assert status["config"]["min_confidence"] == 0.50

    @pytest.mark.asyncio
    async def test_emit_signal_bos_excluded(self):
        """Test that BOS signals are excluded."""
        emitter = ICTSignalEmitter()

        result = await emitter.emit_signal(
            signal_type="bos",
            token="BTC/USDT",
            timeframe="1H",
            signal_data=None,
        )

        assert result.skipped is True
        assert "EXCLUDED per BL-BOS-CHOCH-001" in result.skip_reason

    @pytest.mark.asyncio
    async def test_emit_signal_choch_excluded(self):
        """Test that CHoCH signals are excluded."""
        emitter = ICTSignalEmitter()

        result = await emitter.emit_signal(
            signal_type="choch",
            token="BTC/USDT",
            timeframe="1H",
            signal_data=None,
        )

        assert result.skipped is True
        assert "EXCLUDED per BL-BOS-CHOCH-001" in result.skip_reason

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
        assert "bos_choch" in cycle.excluded_signals
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
            excluded_signals=["bos_choch"],
            errors=["Some error"],
        )

        result = cycle.to_dict()

        assert result["cycle_id"] == "test-cycle-1"
        assert result["signals_processed"] == 5
        assert result["signals_emitted"] == 3
        assert result["signals_skipped"] == 2
        assert "bos_choch" in result["excluded_signals"]
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
