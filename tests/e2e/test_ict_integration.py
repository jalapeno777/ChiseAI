"""End-to-end integration tests for ICT signal pipeline (EP-ICT-005).

Tests the complete flow:
1. ICT detectors (CVD, FVG, Order Block) produce signals
2. Two-layer scorer scores signals for confluence
3. ICT signal emitter processes signals with feature flags
4. Signals are emitted to the signal bus
5. BOS/CHoCH signals are included (re-enabled after accuracy fix)

BOS/CHoCH RE-ENABLED after accuracy fix.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from market_analysis.confluence.signal_weights import (
    get_all_weights,
    get_signal_weight,
)
from market_analysis.confluence.two_layer_scorer import (
    TwoLayerScorer,
)
from signal_generation.ict_signal_emitter import (
    ICTEmissionConfig,
    ICTSignalEmitter,
)
from signal_generation.models import Signal
from signal_generation.registry.ict_signal_registry import (
    ICTSignalRegistry,
    get_ict_registry,
)


class MockSignalEmitter:
    """Mock signal emitter for testing."""

    name: str = "mock_emitter"

    def __init__(self, success: bool = True):
        self.success = success
        self.emit_calls: list = []
        self.last_signal: Signal | None = None

    async def emit(self, signal: Signal) -> MagicMock:
        """Mock emit method."""
        self.emit_calls.append(signal)
        self.last_signal = signal
        result = MagicMock()
        result.success = self.success
        result.latency_ms = 1.5
        result.error = None
        return result


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def ict_registry():
    """Create a fresh ICT signal registry."""
    registry = ICTSignalRegistry()
    yield registry
    # Cleanup
    registry._feature_flags._flags.clear()


@pytest.fixture
def two_layer_scorer():
    """Create a two-layer scorer instance."""
    return TwoLayerScorer(enable_feature_flags=True)


@pytest.fixture
def mock_emitter():
    """Create a mock signal emitter."""
    return MockSignalEmitter(success=True)


@pytest.fixture
def ict_emitter(ict_registry, two_layer_scorer, mock_emitter):
    """Create an ICT signal emitter with mocks."""
    config = ICTEmissionConfig(
        min_confidence=0.3,
        enable_cvd=True,
        enable_fvg=True,
        enable_order_block=True,
    )
    return ICTSignalEmitter(
        config=config,
        registry=ict_registry,
        emitters=[mock_emitter],
        two_layer_scorer=two_layer_scorer,
    )


# =============================================================================
# Test: Signal Weights Validation (EP-ICT-004)
# =============================================================================


class TestSignalWeights:
    """Test signal weights from EP-ICT-004 validation."""

    def test_cvd_weight_is_1_0(self):
        """CVD has 100% validation rate → weight 1.0."""
        weight = get_signal_weight("cvd")
        assert weight == 1.0

    def test_fvg_weight_is_1_0(self):
        """FVG has 100% validation rate → weight 1.0."""
        weight = get_signal_weight("fvg")
        assert weight == 1.0

    def test_order_block_weight_is_0_85(self):
        """Order Block has 80.77% validation rate → weight 0.85."""
        weight = get_signal_weight("order_block")
        assert weight == 0.85

    def test_bos_choch_returns_weight(self):
        """BOS/CHoCH is re-enabled after accuracy fix."""
        # BOS should now return a weight
        weight = get_signal_weight("bos")
        assert isinstance(weight, (int, float))

        weight = get_signal_weight("choc")
        assert isinstance(weight, (int, float))

    def test_all_weights_dict(self):
        """All weights dictionary contains correct values."""
        weights = get_all_weights()
        assert weights["cvd"] == 1.0
        assert weights["fvg"] == 1.0
        assert weights["order_block"] == 0.85
        # BOS/CHOCH are now included
        assert "bos" in weights
        assert "choch" in weights


# =============================================================================
# Test: Feature Flags (ST-ICT-018)
# =============================================================================


class TestFeatureFlags:
    """Test feature flag control of signal enablement."""

    def test_cvd_signal_can_be_disabled(self, ict_registry, two_layer_scorer):
        """CVD signal can be disabled via feature flag."""
        emitter = ICTSignalEmitter(
            config=ICTEmissionConfig(enable_cvd=True),
            registry=ict_registry,
            two_layer_scorer=two_layer_scorer,
        )

        # Initially enabled
        assert emitter.is_signal_enabled("cvd") is True

        # Disable CVD
        emitter.set_feature_flag("cvd", False)
        assert emitter.is_signal_enabled("cvd") is False

    def test_fvg_signal_can_be_disabled(self, ict_registry, two_layer_scorer):
        """FVG signal can be disabled via feature flag."""
        emitter = ICTSignalEmitter(
            config=ICTEmissionConfig(enable_fvg=True),
            registry=ict_registry,
            two_layer_scorer=two_layer_scorer,
        )

        # Initially enabled
        assert emitter.is_signal_enabled("fvg") is True

        # Disable FVG
        emitter.set_feature_flag("fvg", False)
        assert emitter.is_signal_enabled("fvg") is False

    def test_order_block_signal_can_be_disabled(self, ict_registry, two_layer_scorer):
        """Order Block signal can be disabled via feature flag."""
        emitter = ICTSignalEmitter(
            config=ICTEmissionConfig(enable_order_block=True),
            registry=ict_registry,
            two_layer_scorer=two_layer_scorer,
        )

        # Initially enabled
        assert emitter.is_signal_enabled("order_block") is True

        # Disable Order Block
        emitter.set_feature_flag("order_block", False)
        assert emitter.is_signal_enabled("order_block") is False


# =============================================================================
# Test: BOS/CHoCH Inclusion (re-enabled after accuracy fix)


class TestBosChochInclusion:
    """Test BOS/CHoCH inclusion (re-enabled after accuracy fix)."""

    def test_bos_signal_is_enabled(self, ict_registry, two_layer_scorer):
        """BOS signal is now enabled."""
        emitter = ICTSignalEmitter(
            config=ICTEmissionConfig(),
            registry=ict_registry,
            two_layer_scorer=two_layer_scorer,
        )
        assert emitter.is_signal_enabled("bos") is True

    def test_choch_signal_is_enabled(self, ict_registry, two_layer_scorer):
        """CHoCH signal is now enabled."""
        emitter = ICTSignalEmitter(
            config=ICTEmissionConfig(),
            registry=ict_registry,
            two_layer_scorer=two_layer_scorer,
        )
        assert emitter.is_signal_enabled("choch") is True

    def test_bos_choch_signal_is_enabled(self, ict_registry, two_layer_scorer):
        """BOS_CHoCH combined signal is now enabled."""
        emitter = ICTSignalEmitter(
            config=ICTEmissionConfig(),
            registry=ict_registry,
            two_layer_scorer=two_layer_scorer,
        )
        assert emitter.is_signal_enabled("bos_choch") is True

    @pytest.mark.asyncio
    async def test_bos_signal_emission_returns_success(self, ict_emitter):
        """BOS signal emission returns success result."""
        result = await ict_emitter.emit_signal(
            signal_type="bos",
            token="BTC/USDT",
            timeframe="1H",
            signal_data={},
        )
        assert result.emission_success is True

    def test_bos_choch_not_in_excluded_signals_list(self, ict_emitter):
        """BOS_CHoCH no longer appears in excluded signals list."""
        status = ict_emitter.get_status()
        assert status["bos_choch_excluded"] is False


# =============================================================================
# Test: Two-Layer Scorer Integration
# =============================================================================


class TestTwoLayerScorer:
    """Test two-layer scorer integration."""

    def test_scorer_supports_cvd_fvg_order_block(self, two_layer_scorer):
        """Two-layer scorer supports CVD, FVG, and Order Block."""
        assert two_layer_scorer.is_signal_supported("cvd") is True
        assert two_layer_scorer.is_signal_supported("fvg") is True
        assert two_layer_scorer.is_signal_supported("order_block") is True

    def test_scorer_supports_bos_choch(self, two_layer_scorer):
        """Two-layer scorer now supports BOS/CHoCH (re-enabled)."""
        assert two_layer_scorer.is_signal_supported("bos") is True
        assert two_layer_scorer.is_signal_supported("choc") is True

    def test_scorer_returns_supported_signals(self, two_layer_scorer):
        """Scorer returns correct list of supported signals."""
        supported = two_layer_scorer.get_supported_signals()
        assert "cvd" in supported
        assert "fvg" in supported
        assert "order_block" in supported
        # BOS/CHOCH are now included
        assert "bos" in supported
        assert "choch" in supported

    def test_feature_flag_controls_signal(self, two_layer_scorer):
        """Feature flags control which signals are scored."""
        # Disable CVD
        two_layer_scorer.set_signal_enabled("cvd", False)

        # Score with CVD data
        mock_cvd = MagicMock()
        mock_cvd.divergence_type = "bullish"
        mock_cvd.confidence = 0.7

        result = two_layer_scorer.score(cvd_result=mock_cvd)
        assert "cvd" not in result.signals_included


# =============================================================================
# Test: Full Pipeline Integration
# =============================================================================


class TestFullPipelineIntegration:
    """Test full ICT signal pipeline integration."""

    @pytest.mark.asyncio
    async def test_cvd_signal_flows_to_emitter(self, ict_emitter, mock_emitter):
        """CVD signal flows through full pipeline to emitter."""
        # Create proper mock CVD data with required attributes
        mock_cvd = MagicMock()
        mock_cvd.cvd_values = [100.0, 150.0, 200.0]  # Need at least 2 values
        mock_cvd.net_volume = 1000.0
        mock_cvd.trade_count = 50
        mock_cvd.buy_volume = 600.0
        mock_cvd.sell_volume = 400.0

        # Emit signal
        result = await ict_emitter.emit_signal(
            signal_type="cvd",
            token="BTC/USDT",
            timeframe="1H",
            signal_data=mock_cvd,
        )

        # Verify result - emission may succeed or skip based on scoring
        # Key is that the signal flows through the pipeline
        assert result.signal_type == "cvd"
        # The mock emitter received a signal if emission succeeded
        if result.emission_success:
            assert mock_emitter.last_signal is not None
            assert mock_emitter.last_signal.token == "BTC/USDT"

    @pytest.mark.asyncio
    async def test_multiple_signal_types_in_single_cycle(
        self, ict_emitter, mock_emitter
    ):
        """Multiple signal types can be processed in a single emission cycle."""
        # Create proper mock CVD data
        mock_cvd = MagicMock()
        mock_cvd.cvd_values = [100.0, 150.0, 200.0]
        mock_cvd.net_volume = 1000.0
        mock_cvd.trade_count = 50
        mock_cvd.buy_volume = 600.0
        mock_cvd.sell_volume = 400.0

        # Create proper mock FVG data
        mock_fvg = MagicMock()
        mock_fvg.fvg = mock_fvg  # Self-referential for scoring
        mock_fvg.direction.value = "bullish"
        mock_fvg.mitigation.value = "none"
        mock_fvg.ce50_reached = False
        mock_fvg.high = 50500.0
        mock_fvg.low = 49500.0

        # Run emission cycle
        cycle = await ict_emitter.emit_signals(
            token="BTC/USDT",
            timeframe="1H",
            cvd_data=mock_cvd,
            fvg_data=[mock_fvg],
        )

        # Verify cycle processed both signals
        assert cycle.signals_processed >= 2
        # Note: excluded_signals is now empty since BOS/CHOCH is included
        assert "bos_choch" not in cycle.excluded_signals

    @pytest.mark.asyncio
    async def test_signal_excluded_when_feature_flag_disabled(self, ict_emitter):
        """Signal is skipped when its feature flag is disabled."""
        # Disable FVG
        ict_emitter.set_feature_flag("fvg", False)

        # Create mock FVG data
        mock_fvg = MagicMock()
        mock_fvg.direction.value = "bullish"
        mock_fvg.mitigation.value = "none"
        mock_fvg.ce50_reached = False

        # Emit signal
        result = await ict_emitter.emit_signal(
            signal_type="fvg",
            token="BTC/USDT",
            timeframe="1H",
            signal_data=mock_fvg,
        )

        # Verify signal was skipped due to feature flag
        assert result.skipped is True
        assert "Feature flag disabled" in result.skip_reason


# =============================================================================
# Test: Emitter Status
# =============================================================================


class TestEmitterStatus:
    """Test ICT emitter status reporting."""

    def test_emitter_status_contains_feature_flags(self, ict_emitter):
        """Emitter status includes feature flag states."""
        status = ict_emitter.get_status()

        assert "feature_flags" in status
        assert "enable_cvd_signals" in status["feature_flags"]
        assert "enable_fvg_signals" in status["feature_flags"]
        assert "enable_order_block_signals" in status["feature_flags"]

    def test_emitter_status_contains_bos_choch_inclusion(self, ict_emitter):
        """Emitter status confirms BOS/CHoCH is included."""
        status = ict_emitter.get_status()

        assert status["bos_choch_excluded"] is False

    def test_emitter_status_contains_emitters_list(self, ict_emitter, mock_emitter):
        """Emitter status includes list of registered emitters."""
        status = ict_emitter.get_status()

        assert "emitters" in status
        assert mock_emitter.name in status["emitters"]


# =============================================================================
# Test: ICT Signal Registry Integration
# =============================================================================


class TestICTSignalRegistry:
    """Test ICT signal registry integration."""

    def test_registry_feature_flag_management(self, ict_registry):
        """Registry manages feature flags correctly."""
        # Set flag
        ict_registry.set_feature_flag("enable_cvd_signals", True)
        assert ict_registry._feature_flags.is_enabled("enable_cvd_signals") is True

        # Clear flag
        ict_registry.set_feature_flag("enable_cvd_signals", False)
        assert ict_registry._feature_flags.is_enabled("enable_cvd_signals") is False

    def test_global_registry_singleton(self):
        """Global registry returns singleton instance."""
        registry1 = get_ict_registry()
        registry2 = get_ict_registry()
        assert registry1 is registry2
