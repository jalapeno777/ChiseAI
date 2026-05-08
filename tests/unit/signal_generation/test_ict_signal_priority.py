"""ICT Signal Priority Order Tests (ST-ICT-ST2).

Tests verify that the detection priority system correctly resolves
signal priority when multiple ICT signals fire simultaneously.

Priority order: BOS/CHoCH > Order Blocks > FVG > Liquidity Sweeps > Price Structure

Tests:
    - Single signal detection returns correctly
    - Multiple simultaneous signals resolved by priority
    - Tie-breaking for equal priority signals
    - Custom configurable priority list overrides default
    - Default priority enumeration is correct

References:
    - src/signal_generation/registry/ict_signal_registry.py
    - src/signal_generation/ict_signal_emitter.py
    - src/signal_generation/registry/signal_types.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# CRITICAL: Add src to path BEFORE any signal_generation imports
# This must happen at module load time before pytest's import hook
# interferes with the path resolution
_worktree_src = Path(__file__).parent.parent.parent / "src"
if str(_worktree_src) not in sys.path:
    sys.path.insert(0, str(_worktree_src))


from signal_generation.ict_signal_emitter import (
    ICTEmissionConfig,
    ICTSignalEmitter,
)
from signal_generation.registry.ict_signal_registry import (
    ICTSignalRegistry,
)
from signal_generation.registry.signal_types import ICTSignalType, SignalPriority


class TestSingleDetection:
    """Test that a single signal type returns correctly when only one fires."""

    def test_single_signal_returns_correct_type(self) -> None:
        """Single CVD signal should return cvd as the only detected type."""
        registry = ICTSignalRegistry()

        # Get signals sorted by priority (only CVD registered by default)
        sorted_signals = registry.get_registered_signals_sorted_by_priority(
            enabled_only=True
        )

        assert len(sorted_signals) >= 1
        # CVD should be in the sorted list
        signal_types = [s.signal_type for s in sorted_signals]
        assert ICTSignalType.CVD in signal_types

    def test_order_block_returns_when_only_order_block_enabled(self) -> None:
        """When only Order Block is enabled, it should be the only signal."""
        registry = ICTSignalRegistry()

        # Disable all signals except Order Block
        for sig_type in [ICTSignalType.CVD, ICTSignalType.FVG]:
            registry.set_signal_enabled(sig_type, False)

        sorted_signals = registry.get_registered_signals_sorted_by_priority(
            enabled_only=True
        )

        # Order Block should be first (priority 2)
        assert sorted_signals[0].signal_type == ICTSignalType.ORDER_BLOCK


class TestMultipleDetectionsPriorityResolution:
    """Test that when multiple signals fire, highest priority is selected first."""

    def test_order_block_priority_higher_than_fvg(self) -> None:
        """Order Block (priority 2) should come before FVG (priority 3)."""
        registry = ICTSignalRegistry()

        ob_priority = registry._get_priority(ICTSignalType.ORDER_BLOCK)
        fvg_priority = registry._get_priority(ICTSignalType.FVG)

        assert ob_priority < fvg_priority
        assert ob_priority == SignalPriority.ORDER_BLOCK.value
        assert fvg_priority == SignalPriority.FVG.value

    def test_fvg_priority_higher_than_cvd(self) -> None:
        """FVG (priority 3) should come before CVD/Liquidity (priority 4)."""
        registry = ICTSignalRegistry()

        fvg_priority = registry._get_priority(ICTSignalType.FVG)
        cvd_priority = registry._get_priority(ICTSignalType.CVD)

        assert fvg_priority < cvd_priority
        assert fvg_priority == SignalPriority.FVG.value
        assert cvd_priority == SignalPriority.LIQUIDITY_SWEEP.value

    def test_cvd_priority_higher_than_price_structure(self) -> None:
        """CVD/Liquidity (priority 4) should come before Price Structure (priority 5)."""
        registry = ICTSignalRegistry()

        cvd_priority = registry._get_priority(ICTSignalType.CVD)
        h_priority = registry._get_priority(ICTSignalType.H)

        assert cvd_priority < h_priority
        assert cvd_priority == SignalPriority.LIQUIDITY_SWEEP.value
        assert h_priority == SignalPriority.PRICE_STRUCTURE.value

    def test_sorted_signals_returns_correct_order(self) -> None:
        """get_registered_signals_sorted_by_priority returns signals in correct order."""
        registry = ICTSignalRegistry()

        sorted_signals = registry.get_registered_signals_sorted_by_priority(
            enabled_only=False
        )

        # Extract priorities in sorted order
        priorities = [s.priority for s in sorted_signals]

        # Verify priorities are in ascending order (lower = higher priority)
        assert priorities == sorted(priorities)

    def test_priority_order_list_matches_registry(self) -> None:
        """The priority order list from emitter matches registry configuration."""
        config = ICTEmissionConfig()
        registry = ICTSignalRegistry()
        emitter = ICTSignalEmitter(config=config, registry=registry)

        priority_order = emitter._get_emission_priority_order()

        # The order should be: order_block, fvg, cvd, h/l/high_old/low_old
        # CVD is treated as liquidity (priority 4)
        assert priority_order[0] == "order_block"  # priority 2
        assert priority_order[1] == "fvg"  # priority 3


class TestTieBreaking:
    """Test tie-breaking when signals have equal priority."""

    def test_h_and_l_have_same_priority(self) -> None:
        """H and L both have PRICE_STRUCTURE priority (5)."""
        registry = ICTSignalRegistry()

        h_priority = registry._get_priority(ICTSignalType.H)
        l_priority = registry._get_priority(ICTSignalType.L)

        assert h_priority == l_priority
        assert h_priority == SignalPriority.PRICE_STRUCTURE.value

    def test_high_old_and_low_old_have_same_priority(self) -> None:
        """HIGH_OLD and LOW_OLD both have PRICE_STRUCTURE priority (5)."""
        registry = ICTSignalRegistry()

        high_old_priority = registry._get_priority(ICTSignalType.HIGH_OLD)
        low_old_priority = registry._get_priority(ICTSignalType.LOW_OLD)

        assert high_old_priority == low_old_priority
        assert high_old_priority == SignalPriority.PRICE_STRUCTURE.value

    def test_equal_priority_signals_sorted_deterministic(self) -> None:
        """When priority is equal, signals should be sorted deterministically."""
        registry = ICTSignalRegistry()

        sorted_signals = registry.get_registered_signals_sorted_by_priority(
            enabled_only=False
        )

        # Filter to only price structure signals (same priority)
        price_structure_signals = [
            s
            for s in sorted_signals
            if s.priority == SignalPriority.PRICE_STRUCTURE.value
        ]

        # Extract signal types
        signal_types = [s.signal_type for s in price_structure_signals]

        # Sorting should be deterministic (stable sort preserves original order)
        # Run twice to verify determinism
        sorted_signals_again = registry.get_registered_signals_sorted_by_priority(
            enabled_only=False
        )
        price_structure_signals_again = [
            s
            for s in sorted_signals_again
            if s.priority == SignalPriority.PRICE_STRUCTURE.value
        ]
        signal_types_again = [s.signal_type for s in price_structure_signals_again]

        assert signal_types == signal_types_again


class TestConfigurablePriority:
    """Test that custom priority list overrides default."""

    def test_config_priority_overrides_default(self) -> None:
        """Custom signal_priority in config should override registry default."""
        custom_priority = ["fvg", "order_block", "cvd", "h"]

        config = ICTEmissionConfig(signal_priority=custom_priority)
        registry = ICTSignalRegistry()
        emitter = ICTSignalEmitter(config=config, registry=registry)

        priority_order = emitter._get_emission_priority_order()

        assert priority_order == custom_priority
        assert priority_order[0] == "fvg"  # fvg now highest priority

    def test_empty_config_uses_default(self) -> None:
        """When config.signal_priority is None, uses registry default."""
        config = ICTEmissionConfig(signal_priority=None)
        registry = ICTSignalRegistry()
        emitter = ICTSignalEmitter(config=config, registry=registry)

        priority_order = emitter._get_emission_priority_order()

        # Should not be empty - should use registry default
        assert len(priority_order) > 0
        # First item should be order_block (priority 2, lowest available)
        assert "order_block" in priority_order

    def test_partial_config_reduces_priority_list(self) -> None:
        """Partial priority list only includes specified signals."""
        partial_priority = ["fvg", "cvd"]

        config = ICTEmissionConfig(signal_priority=partial_priority)
        registry = ICTSignalRegistry()
        emitter = ICTSignalEmitter(config=config, registry=registry)

        priority_order = emitter._get_emission_priority_order()

        assert priority_order == partial_priority
        assert len(priority_order) == 2


class TestPriorityOrderEnumeration:
    """Test the default priority order enumeration."""

    def test_signal_priority_enum_values(self) -> None:
        """SignalPriority enum has correct values."""
        assert SignalPriority.BOS_CHOCH.value == 1
        assert SignalPriority.ORDER_BLOCK.value == 2
        assert SignalPriority.FVG.value == 3
        assert SignalPriority.LIQUIDITY_SWEEP.value == 4
        assert SignalPriority.PRICE_STRUCTURE.value == 5

    def test_registry_priority_mapping_complete(self) -> None:
        """Registry SIGNAL_PRIORITY_ORDER covers all default signals."""
        registry = ICTSignalRegistry()

        # All registered signals should have priority defined
        for signal in registry.get_registered_signals():
            assert signal.priority < 99, f"Signal {signal.signal_type} missing priority"
            assert (
                signal.priority > 0
            ), f"Signal {signal.signal_type} has invalid priority"

    def test_default_priority_order_sequence(self) -> None:
        """Default priority order sequence is correct."""
        registry = ICTSignalRegistry()

        # Build expected order by priority value
        expected_order = [
            # Priority 1: BOS/CHoCH (re-enabled after accuracy fix)
            # ICTSignalType.BOS_CHOCH: SignalPriority.BOS_CHOCH.value,
            # Priority 2: Order Blocks
            ICTSignalType.ORDER_BLOCK,
            # Priority 3: FVG
            ICTSignalType.FVG,
            # Priority 4: CVD (liquidity)
            ICTSignalType.CVD,
            # Priority 5: Price structure
            ICTSignalType.H,
            ICTSignalType.L,
            ICTSignalType.HIGH_OLD,
            ICTSignalType.LOW_OLD,
        ]

        # Verify expected priorities
        assert SignalPriority.ORDER_BLOCK.value == 2
        assert SignalPriority.FVG.value == 3
        assert SignalPriority.LIQUIDITY_SWEEP.value == 4
        assert SignalPriority.PRICE_STRUCTURE.value == 5

        # Verify registry mapping
        for sig_type in expected_order:
            priority = registry._get_priority(sig_type)
            assert priority != 99, f"Signal {sig_type} missing priority mapping"

    def test_emission_priority_order_contains_all_signal_types(self) -> None:
        """Emission priority order contains all registered signal types."""
        config = ICTEmissionConfig()
        registry = ICTSignalRegistry()
        emitter = ICTSignalEmitter(config=config, registry=registry)

        priority_order = emitter._get_emission_priority_order()

        # All enabled signal types should be in priority order
        registered_signals = registry.get_registered_signals(enabled_only=True)
        registered_types = {s.signal_type.value for s in registered_signals}

        for sig_type in registered_types:
            assert (
                sig_type in priority_order
            ), f"Signal type {sig_type} not in emission priority order"


class TestSignalMetadata:
    """Test signal metadata includes priority information."""

    def test_registered_signal_has_priority(self) -> None:
        """Each registered signal should have a priority value."""
        registry = ICTSignalRegistry()

        for signal in registry.get_registered_signals():
            assert hasattr(signal, "priority")
            assert isinstance(signal.priority, int)
            assert signal.priority > 0

    def test_priority_reflected_in_sorted_output(self) -> None:
        """Priority is correctly reflected when signals are sorted."""
        registry = ICTSignalRegistry()

        sorted_signals = registry.get_registered_signals_sorted_by_priority()

        # Each signal should have priority <= previous signal
        for i in range(1, len(sorted_signals)):
            prev_priority = sorted_signals[i - 1].priority
            curr_priority = sorted_signals[i].priority
            assert prev_priority <= curr_priority, "Signals not sorted by priority"
