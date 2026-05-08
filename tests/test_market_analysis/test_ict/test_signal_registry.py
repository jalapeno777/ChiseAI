"""Tests for ICT Signal Registration.

Tests for the ICT signal registry, signal adapter, and feature flag support.

BOS/CHoCH exclusion is verified per BL-BOS-CHOCH-001.
"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from src.market_analysis.ict import (
    CVDAdapter,
    FVGAdapter,
    ICTSignalAdapter,
    ICTSignalData,
    ICTSignalDirection,
    OrderBlockAdapter,
)

from signal_generation.registry import (
    FeatureFlagManager,
    ICTSignalRegistry,
    ICTSignalType,
    SignalMetadata,
    SignalSource,
    get_ict_registry,
)


class TestICTSignalType:
    """Tests for ICTSignalType enum."""

    def test_cvd_signal_type_exists(self) -> None:
        """Test CVD signal type exists."""
        assert ICTSignalType.CVD.value == "cvd"

    def test_fvg_signal_type_exists(self) -> None:
        """Test FVG signal type exists."""
        assert ICTSignalType.FVG.value == "fvg"

    def test_order_block_signal_type_exists(self) -> None:
        """Test Order Block signal type exists."""
        assert ICTSignalType.ORDER_BLOCK.value == "order_block"

    def test_h_signal_type_exists(self) -> None:
        """Test H (High) signal type exists (S1A-2)."""
        assert ICTSignalType.H.value == "h"

    def test_l_signal_type_exists(self) -> None:
        """Test L (Low) signal type exists (S1A-2)."""
        assert ICTSignalType.L.value == "l"

    def test_high_old_signal_type_exists(self) -> None:
        """Test HIGH_OLD (Old High) signal type exists (S1A-2)."""
        assert ICTSignalType.HIGH_OLD.value == "high_old"

    def test_low_old_signal_type_exists(self) -> None:
        """Test LOW_OLD (Old Low) signal type exists (S1A-2)."""
        assert ICTSignalType.LOW_OLD.value == "low_old"

    def test_bos_choch_is_included(self) -> None:
        """Test that BOS/CHoCH is now included (re-enabled)."""
        excluded = ICTSignalType.get_excluded_signals()
        assert "bos_choch" not in excluded

    def test_excluded_signals_list_empty(self) -> None:
        """Test get_excluded_signals returns empty list."""
        excluded = ICTSignalType.get_excluded_signals()
        assert isinstance(excluded, list)
        assert len(excluded) == 0

    def test_signal_types_include_bos_choch(self) -> None:
        """Test that BOS_CHOCH is a valid ICTSignalType member."""
        all_values = [e.value for e in ICTSignalType]
        assert "bos_choch" in all_values


class TestFeatureFlagManager:
    """Tests for FeatureFlagManager."""

    def test_set_and_get_flag(self) -> None:
        """Test setting and getting a feature flag."""
        manager = FeatureFlagManager()
        manager.set_flag("test_flag", True)
        assert manager.is_enabled("test_flag") is True

        manager.set_flag("test_flag", False)
        assert manager.is_enabled("test_flag") is False

    def test_none_flag_is_always_enabled(self) -> None:
        """Test that None flag is always enabled."""
        manager = FeatureFlagManager()
        assert manager.is_enabled(None) is True

    def test_unset_flag_defaults_to_enabled(self) -> None:
        """Test that unset flags default to enabled."""
        manager = FeatureFlagManager()
        assert manager.is_enabled("nonexistent") is True

    def test_get_flag_returns_none_when_not_set(self) -> None:
        """Test get_flag returns None for unset flags."""
        manager = FeatureFlagManager()
        assert manager.get_flag("nonexistent") is None


class TestSignalMetadata:
    """Tests for SignalMetadata dataclass."""

    def test_metadata_creation(self) -> None:
        """Test creating signal metadata."""
        metadata = SignalMetadata(
            name="Test Signal",
            description="A test signal",
            confidence_base=0.75,
            timeframe_default="4H",
            tags=["test"],
        )
        assert metadata.name == "Test Signal"
        assert metadata.confidence_base == 0.75
        assert "test" in metadata.tags

    def test_metadata_to_dict(self) -> None:
        """Test converting metadata to dictionary."""
        metadata = SignalMetadata(
            name="Test Signal",
            description="A test signal",
            confidence_base=0.75,
        )
        d = metadata.to_dict()
        assert d["name"] == "Test Signal"
        assert d["confidence_base"] == 0.75
        assert d["source"] == SignalSource.ICT.value


class TestICTSignalRegistry:
    """Tests for ICTSignalRegistry."""

    def test_default_signals_registered(self) -> None:
        """Test that default ICT signals are registered."""
        registry = ICTSignalRegistry()

        # Check CVD is registered
        cvd = registry.get_signal(ICTSignalType.CVD)
        assert cvd is not None
        assert cvd.metadata.name == "Cumulative Volume Delta"
        assert cvd.feature_flag == "enable_cvd_signals"

        # Check FVG is registered
        fvg = registry.get_signal(ICTSignalType.FVG)
        assert fvg is not None
        assert fvg.metadata.name == "Fair Value Gap"
        assert fvg.feature_flag == "enable_fvg_signals"

        # Check Order Block is registered
        ob = registry.get_signal(ICTSignalType.ORDER_BLOCK)
        assert ob is not None
        assert ob.metadata.name == "Order Block"
        assert ob.feature_flag == "enable_order_block_signals"

    def test_signal_enabled_by_default(self) -> None:
        """Test signals are enabled by default."""
        registry = ICTSignalRegistry()

        assert registry.is_signal_enabled(ICTSignalType.CVD) is True
        assert registry.is_signal_enabled(ICTSignalType.FVG) is True
        assert registry.is_signal_enabled(ICTSignalType.ORDER_BLOCK) is True

    def test_disable_signal_via_feature_flag(self) -> None:
        """Test disabling signal via feature flag."""
        registry = ICTSignalRegistry()

        registry.set_feature_flag("enable_cvd_signals", False)
        assert registry.is_signal_enabled(ICTSignalType.CVD) is False

        # Other signals should still be enabled
        assert registry.is_signal_enabled(ICTSignalType.FVG) is True

    def test_disable_signal_via_set_enabled(self) -> None:
        """Test disabling signal via set_signal_enabled."""
        registry = ICTSignalRegistry()

        result = registry.set_signal_enabled(ICTSignalType.CVD, False)
        assert result is True
        assert registry.is_signal_enabled(ICTSignalType.CVD) is False

    def test_get_registered_signals(self) -> None:
        """Test getting all registered signals."""
        registry = ICTSignalRegistry()

        signals = registry.get_registered_signals()
        # 3 original + 4 new HL signals (H, L, HIGH_OLD, LOW_OLD) = 7
        assert len(signals) == 7

        signal_types = [s.signal_type for s in signals]
        assert ICTSignalType.CVD in signal_types
        assert ICTSignalType.FVG in signal_types
        assert ICTSignalType.ORDER_BLOCK in signal_types
        # New H/L/H-OLD/L-OLD signals (S1A-2)
        assert ICTSignalType.H in signal_types
        assert ICTSignalType.L in signal_types
        assert ICTSignalType.HIGH_OLD in signal_types
        assert ICTSignalType.LOW_OLD in signal_types

    def test_get_registered_signals_enabled_only(self) -> None:
        """Test getting only enabled signals."""
        registry = ICTSignalRegistry()

        # Disable one signal
        registry.set_signal_enabled(ICTSignalType.CVD, False)

        enabled_signals = registry.get_registered_signals(enabled_only=True)
        # 6 remaining (7 - 1 disabled CVD)
        assert len(enabled_signals) == 6

        enabled_types = [s.signal_type for s in enabled_signals]
        assert ICTSignalType.CVD not in enabled_types
        assert ICTSignalType.FVG in enabled_types

    def test_list_signal_types(self) -> None:
        """Test listing signal types."""
        registry = ICTSignalRegistry()

        types = registry.list_signal_types()
        # 3 original + 4 new HL signals = 7
        assert len(types) == 7
        assert ICTSignalType.CVD in types

        # Disable one and check
        registry.set_signal_enabled(ICTSignalType.CVD, False)
        types_disabled = registry.list_signal_types(enabled_only=True)
        # 6 remaining (7 - 1 disabled CVD)
        assert len(types_disabled) == 6
        assert ICTSignalType.CVD not in types_disabled

    def test_no_excluded_signals(self) -> None:
        """Test that there are no excluded signals."""
        registry = ICTSignalRegistry()
        excluded = registry.get_excluded_signals()
        assert "bos_choch" not in excluded

    def test_registry_to_dict(self) -> None:
        """Test converting registry to dictionary."""
        registry = ICTSignalRegistry()

        d = registry.to_dict()
        assert "signals" in d
        assert "excluded_signals" in d
        assert "feature_flags" in d
        # 3 original + 4 new HL signals = 7
        assert len(d["signals"]) == 7

    def test_register_duplicate_signal_raises(self) -> None:
        """Test that registering duplicate signal raises error."""
        registry = ICTSignalRegistry()

        with pytest.raises(ValueError, match="already registered"):
            registry.register_signal(
                signal_type=ICTSignalType.CVD,
                metadata=SignalMetadata(name="Test", description="Test"),
            )

    def test_get_signal_metadata(self) -> None:
        """Test getting signal metadata."""
        registry = ICTSignalRegistry()

        metadata = registry.get_signal_metadata(ICTSignalType.FVG)
        assert metadata is not None
        assert metadata.name == "Fair Value Gap"

        # Non-existent signal
        # Create a mock signal type for testing
        nonexistent = MagicMock(spec=ICTSignalType)
        nonexistent.value = "nonexistent"
        assert registry.get_signal_metadata(nonexistent) is None


class TestGlobalRegistry:
    """Tests for global registry singleton."""

    def test_get_ict_registry_returns_same_instance(self) -> None:
        """Test that get_ict_registry returns singleton."""
        registry1 = get_ict_registry()
        registry2 = get_ict_registry()
        assert registry1 is registry2


class TestICTSignalData:
    """Tests for ICTSignalData dataclass."""

    def test_signal_data_creation(self) -> None:
        """Test creating ICT signal data."""
        data = ICTSignalData(
            signal_type=ICTSignalType.FVG,
            direction=ICTSignalDirection.BULLISH,
            confidence=0.75,
            price_high=50000.0,
            price_low=49000.0,
            timestamp=datetime(2024, 1, 1),
            token="BTC/USDT",
            timeframe="1H",
        )
        assert data.signal_type == ICTSignalType.FVG
        assert data.direction == ICTSignalDirection.BULLISH
        assert data.confidence == 0.75

    def test_signal_data_to_dict(self) -> None:
        """Test converting signal data to dictionary."""
        data = ICTSignalData(
            signal_type=ICTSignalType.ORDER_BLOCK,
            direction=ICTSignalDirection.BEARISH,
            confidence=0.68,
            price_high=51000.0,
            price_low=50000.0,
            timestamp=datetime(2024, 1, 1),
            token="ETH/USDT",
            timeframe="4H",
        )
        d = data.to_dict()
        assert d["signal_type"] == "order_block"
        assert d["direction"] == "bearish"
        assert d["confidence"] == 0.68
        assert d["token"] == "ETH/USDT"


class TestFVGAdapter:
    """Tests for FVGAdapter."""

    def test_convert_bullish_fvg(self) -> None:
        """Test converting bullish FVG."""
        from src.market_analysis.fvg.fvg_detector import (
            FVG,
            FVGDirection,
            FVGMitigation,
        )

        fvg = FVG(
            direction=FVGDirection.BULLISH,
            timestamp=1704067200000,  # 2024-01-01 00:00:00 UTC
            high=50000.0,
            low=49000.0,
            mitigation=FVGMitigation.NONE,
            ce50_reached=False,
        )

        adapter = FVGAdapter()
        result = adapter.convert_fvg(fvg, token="BTC/USDT", timeframe="1H")

        assert isinstance(result, ICTSignalData)
        assert result.signal_type == ICTSignalType.FVG
        assert result.direction == ICTSignalDirection.BULLISH
        assert result.confidence == 0.80  # Based on MITIGATION_CONFIDENCE
        assert result.price_high == 50000.0
        assert result.price_low == 49000.0
        assert result.token == "BTC/USDT"
        assert result.metadata["mitigation_status"] == "none"
        assert result.metadata["ce50_reached"] is False

    def test_convert_bearish_fvg_with_mitigation(self) -> None:
        """Test converting bearish FVG with mitigation."""
        from src.market_analysis.fvg.fvg_detector import (
            FVG,
            FVGDirection,
            FVGMitigation,
        )

        fvg = FVG(
            direction=FVGDirection.BEARISH,
            timestamp=1704067200000,
            high=51000.0,
            low=50000.0,
            mitigation=FVGMitigation.CLOSE,
            ce50_reached=True,
        )

        adapter = FVGAdapter()
        result = adapter.convert_fvg(fvg, token="BTC/USDT", timeframe="1H")

        assert result.direction == ICTSignalDirection.BEARISH
        assert result.confidence == 0.55 + 0.10  # close mitigation + ce50
        assert result.metadata["mitigation_status"] == "close"
        assert result.metadata["ce50_reached"] is True


class TestOrderBlockAdapter:
    """Tests for OrderBlockAdapter."""

    def test_convert_bullish_order_block(self) -> None:
        """Test converting bullish Order Block."""
        from src.market_analysis.order_block.ob_detector import (
            OBDetectionResult,
            OBPolaridade,
        )
        from src.market_analysis.zones import Zone, ZoneType
        from src.market_analysis.zones.zone_models import PriceRange

        zone = Zone(
            zone_type=ZoneType.OB,
            timeframe="1H",
            token="BTC/USDT",
            price_range=PriceRange(high=50000.0, low=49000.0),
        )

        ob_result = OBDetectionResult(
            polarity=OBPolaridade.BULLISH,
            zone=zone,
            anchor_candle_index=10,
            momentum_candle_index=15,
            strength_score=0.75,
            volume_confirmed=True,
        )

        adapter = OrderBlockAdapter()
        result = adapter.convert_ob(ob_result, token="BTC/USDT", timeframe="1H")

        assert isinstance(result, ICTSignalData)
        assert result.signal_type == ICTSignalType.ORDER_BLOCK
        assert result.direction == ICTSignalDirection.BULLISH
        assert result.confidence == 0.75
        assert result.metadata["volume_confirmed"] is True
        assert result.metadata["strength_score"] == 0.75


class TestCVDAdapter:
    """Tests for CVDAdapter."""

    def test_convert_bullish_divergence(self) -> None:
        """Test converting bullish CVD divergence."""
        divergence_data = {
            "direction": "bullish",
            "index": 100,
            "cvd_values": [1.0, 2.0, 3.0],
            "prices": [50000.0, 50100.0, 50200.0],
            "threshold": 0.5,
            "current_price": 50200.0,
        }

        adapter = CVDAdapter()
        result = adapter.convert_divergence(divergence_data, token="BTC/USDT")

        assert isinstance(result, ICTSignalData)
        assert result.signal_type == ICTSignalType.CVD
        assert result.direction == ICTSignalDirection.BULLISH
        assert result.metadata["divergence_index"] == 100


class TestICTSignalAdapter:
    """Tests for main ICTSignalAdapter."""

    def test_adapter_initialization(self) -> None:
        """Test adapter initializes with sub-adapters."""
        adapter = ICTSignalAdapter()
        assert isinstance(adapter.cvd_adapter, CVDAdapter)
        assert isinstance(adapter.fvg_adapter, FVGAdapter)
        assert isinstance(adapter.ob_adapter, OrderBlockAdapter)

    def test_convert_fvg_directly(self) -> None:
        """Test converting FVG directly via main adapter."""
        from src.market_analysis.fvg.fvg_detector import (
            FVG,
            FVGDirection,
            FVGMitigation,
        )

        fvg = FVG(
            direction=FVGDirection.BULLISH,
            timestamp=1704067200000,
            high=50000.0,
            low=49000.0,
            mitigation=FVGMitigation.NONE,
        )

        adapter = ICTSignalAdapter()
        result = adapter.convert_fvg(fvg, token="BTC/USDT")

        assert result.signal_type == ICTSignalType.FVG
        assert result.direction == ICTSignalDirection.BULLISH

    def test_convert_order_block_directly(self) -> None:
        """Test converting Order Block directly via main adapter."""
        from src.market_analysis.order_block.ob_detector import (
            OBDetectionResult,
            OBPolaridade,
        )
        from src.market_analysis.zones import Zone, ZoneType
        from src.market_analysis.zones.zone_models import PriceRange

        zone = Zone(
            zone_type=ZoneType.OB,
            timeframe="1H",
            token="BTC/USDT",
            price_range=PriceRange(high=50000.0, low=49000.0),
        )

        ob_result = OBDetectionResult(
            polarity=OBPolaridade.BEARISH,
            zone=zone,
            anchor_candle_index=10,
            momentum_candle_index=15,
            strength_score=0.70,
            volume_confirmed=False,
        )

        adapter = ICTSignalAdapter()
        result = adapter.convert_order_block(ob_result, token="BTC/USDT")

        assert result.signal_type == ICTSignalType.ORDER_BLOCK
        assert result.direction == ICTSignalDirection.BEARISH

    def test_convert_cvd_directly(self) -> None:
        """Test converting CVD directly via main adapter."""
        divergence_data = {
            "direction": "bearish",
            "index": 50,
            "cvd_values": [1.0, 2.0],
            "prices": [50000.0, 49900.0],
            "threshold": 0.3,
            "current_price": 49900.0,
        }

        adapter = ICTSignalAdapter()
        result = adapter.convert_cvd(divergence_data, token="ETH/USDT")

        assert result.signal_type == ICTSignalType.CVD
        assert result.direction == ICTSignalDirection.BEARISH
        assert result.token == "ETH/USDT"


class TestBOSCHOCHInclusion:
    """Tests verifying BOS/CHoCH is now included in the pipeline."""

    def test_bos_choch_in_signal_types(self) -> None:
        """Test that BOS_CHOCH is a valid ICTSignalType."""
        all_types = [e for e in ICTSignalType]
        type_values = [e.value for e in all_types]
        assert "bos_choch" in type_values

    def test_bos_choch_in_registry(self) -> None:
        """Test that BOS_CHOCH is registered."""
        registry = ICTSignalRegistry()
        registered_types = registry.list_signal_types()

        # BOS_CHOCH should be in registered types
        bos_choch_found = any(
            sig_type.value == "bos_choch" for sig_type in registered_types
        )
        assert bos_choch_found

    def test_bos_choch_not_in_excluded_list(self) -> None:
        """Test that BOS/CHoCH is not in the excluded list."""
        excluded = ICTSignalType.get_excluded_signals()
        assert "bos_choch" not in excluded

        # Also verify via registry
        registry = ICTSignalRegistry()
        assert "bos_choch" not in registry.get_excluded_signals()
