"""Tests for paper trading position tracker with fee tracking.

Tests for PAPER-LOOP-001: Paper Trading Position Tracker
Covers fee tracking functionality added in ST-KPI-FIX-001
"""

from __future__ import annotations

import asyncio
import pytest
from datetime import UTC, datetime

from src.execution.paper.position_tracker import PaperPosition, PaperPositionTracker


class TestPaperPositionFees:
    """Tests for PaperPosition fee tracking."""

    def test_position_has_fee_fields(self):
        """Test that PaperPosition has entry_fees and exit_fees fields."""
        position = PaperPosition(
            position_id="test-1",
            symbol="BTC/USDT",
            side="long",
            entry_price=50000.0,
            quantity=0.1,
            entry_fees=5.0,
            exit_fees=0.0,
        )
        assert position.entry_fees == 5.0
        assert position.exit_fees == 0.0

    def test_position_fee_defaults_to_zero(self):
        """Test that fees default to 0.0 when not provided."""
        position = PaperPosition(
            position_id="test-1",
            symbol="BTC/USDT",
            side="long",
            entry_price=50000.0,
            quantity=0.1,
        )
        assert position.entry_fees == 0.0
        assert position.exit_fees == 0.0
        assert position.total_fees == 0.0

    def test_total_fees_property(self):
        """Test that total_fees returns sum of entry and exit fees."""
        position = PaperPosition(
            position_id="test-1",
            symbol="BTC/USDT",
            side="long",
            entry_price=50000.0,
            quantity=0.1,
            entry_fees=5.0,
            exit_fees=3.0,
        )
        assert position.total_fees == 8.0


class TestPaperPositionPnlWithFees:
    """Tests for PnL calculation with fee deduction."""

    def test_calculate_pnl_without_fees_default(self):
        """Test that calculate_pnl defaults to not deducting fees."""
        position = PaperPosition(
            position_id="test-1",
            symbol="BTC/USDT",
            side="long",
            entry_price=50000.0,
            quantity=0.1,
            entry_fees=5.0,
            exit_fees=3.0,
        )
        # Price went up $1000, gross PnL = $100
        pnl = position.calculate_pnl(51000.0)
        assert pnl == 100.0  # Gross PnL, fees not deducted

    def test_calculate_pnl_with_fees_deducted(self):
        """Test that calculate_pnl with deduct_fees=True returns net PnL."""
        position = PaperPosition(
            position_id="test-1",
            symbol="BTC/USDT",
            side="long",
            entry_price=50000.0,
            quantity=0.1,
            entry_fees=5.0,
            exit_fees=3.0,
        )
        # Price went up $1000, gross PnL = $100, total fees = $8
        pnl = position.calculate_pnl(51000.0, deduct_fees=True)
        assert pnl == 92.0  # Net PnL after fees

    def test_calculate_pnl_short_with_fees(self):
        """Test PnL calculation for short positions with fees."""
        position = PaperPosition(
            position_id="test-1",
            symbol="BTC/USDT",
            side="short",
            entry_price=50000.0,
            quantity=0.1,
            entry_fees=5.0,
            exit_fees=3.0,
        )
        # Price went down $1000, gross PnL = $100
        gross_pnl = position.calculate_pnl(49000.0)
        assert gross_pnl == 100.0

        # Net PnL after fees
        net_pnl = position.calculate_pnl(49000.0, deduct_fees=True)
        assert net_pnl == 92.0

    def test_calculate_pnl_fees_can_make_positive_negative(self):
        """Test that fees can turn a profitable trade into a loss."""
        position = PaperPosition(
            position_id="test-1",
            symbol="BTC/USDT",
            side="long",
            entry_price=50000.0,
            quantity=0.01,  # Small position
            entry_fees=10.0,
            exit_fees=10.0,
        )
        # Price went up $100, gross PnL = $1, but fees are $20
        gross_pnl = position.calculate_pnl(50100.0)
        assert gross_pnl == 1.0

        net_pnl = position.calculate_pnl(50100.0, deduct_fees=True)
        assert net_pnl == -19.0  # Net loss after fees


class TestPaperPositionTrackerFees:
    """Tests for PaperPositionTracker with fee integration."""

    @pytest.fixture
    async def tracker(self):
        """Create a fresh tracker for each test."""
        tracker = PaperPositionTracker()
        yield tracker
        await tracker.clear_all()

    @pytest.mark.asyncio
    async def test_open_position_with_entry_fees(self, tracker):
        """Test that open_position accepts entry_fees parameter."""
        position = await tracker.open_position(
            symbol="BTC/USDT",
            side="long",
            entry_price=50000.0,
            quantity=0.1,
            entry_fees=5.0,
        )
        assert position.entry_fees == 5.0
        assert position.total_fees == 5.0

    @pytest.mark.asyncio
    async def test_open_position_without_entry_fees_defaults_to_zero(self, tracker):
        """Test that open_position defaults entry_fees to 0.0."""
        position = await tracker.open_position(
            symbol="BTC/USDT",
            side="long",
            entry_price=50000.0,
            quantity=0.1,
        )
        assert position.entry_fees == 0.0

    @pytest.mark.asyncio
    async def test_close_position_with_exit_fees(self, tracker):
        """Test that close_position accepts exit_fees and deducts from PnL."""
        position = await tracker.open_position(
            symbol="BTC/USDT",
            side="long",
            entry_price=50000.0,
            quantity=0.1,
            entry_fees=5.0,
        )

        # Close at $51,000 (gross PnL = $100, total fees = $13)
        closed_pos, realized_pnl = await tracker.close_position(
            position_id=position.position_id,
            exit_price=51000.0,
            exit_fees=8.0,
        )

        assert closed_pos.exit_fees == 8.0
        assert closed_pos.total_fees == 13.0
        # Realized PnL should be net after fees
        assert realized_pnl == 87.0  # $100 gross - $13 fees

    @pytest.mark.asyncio
    async def test_close_position_without_exit_fees_defaults_to_zero(self, tracker):
        """Test that close_position defaults exit_fees to 0.0."""
        position = await tracker.open_position(
            symbol="BTC/USDT",
            side="long",
            entry_price=50000.0,
            quantity=0.1,
            entry_fees=5.0,
        )

        # Close without specifying exit_fees
        closed_pos, realized_pnl = await tracker.close_position(
            position_id=position.position_id,
            exit_price=51000.0,
        )

        assert closed_pos.exit_fees == 0.0
        assert closed_pos.total_fees == 5.0
        # Realized PnL should be net after fees (only entry fees)
        assert realized_pnl == 95.0  # $100 gross - $5 entry fees

    @pytest.mark.asyncio
    async def test_close_position_realized_pnl_is_net(self, tracker):
        """Test that realized PnL from close_position is net of all fees.

        This is the critical test for the KPI fix - it verifies that
        close_position now returns net PnL instead of gross PnL.
        """
        position = await tracker.open_position(
            symbol="BTC/USDT",
            side="long",
            entry_price=50000.0,
            quantity=1.0,
            entry_fees=50.0,
        )

        # Close at $50,100 (gross PnL = $100, total fees = $120)
        closed_pos, realized_pnl = await tracker.close_position(
            position_id=position.position_id,
            exit_price=50100.0,
            exit_fees=70.0,
        )

        # Position is now closed
        assert closed_pos.is_open is False
        assert closed_pos.closed_at is not None

        # Realized PnL should be NET (negative in this case)
        # $100 gross profit - $120 total fees = -$20 net loss
        assert realized_pnl == -20.0

        # The position object should also have net realized_pnl
        assert closed_pos.realized_pnl == -20.0

    @pytest.mark.asyncio
    async def test_fee_tracking_in_position_history(self, tracker):
        """Test that fees are preserved in closed position history."""
        position = await tracker.open_position(
            symbol="BTC/USDT",
            side="long",
            entry_price=50000.0,
            quantity=0.1,
            entry_fees=5.0,
        )

        await tracker.close_position(
            position_id=position.position_id,
            exit_price=51000.0,
            exit_fees=8.0,
        )

        closed_positions = await tracker.get_closed_positions()
        assert len(closed_positions) == 1

        closed_pos = closed_positions[0]
        assert closed_pos.entry_fees == 5.0
        assert closed_pos.exit_fees == 8.0
        assert closed_pos.total_fees == 13.0


class TestBackwardCompatibility:
    """Tests to ensure backward compatibility."""

    @pytest.fixture
    async def tracker(self):
        """Create a fresh tracker for each test."""
        tracker = PaperPositionTracker()
        yield tracker
        await tracker.clear_all()

    @pytest.mark.asyncio
    async def test_calculate_pnl_backward_compatible(self, tracker):
        """Test that calculate_pnl still works without deduct_fees argument."""
        position = await tracker.open_position(
            symbol="BTC/USDT",
            side="long",
            entry_price=50000.0,
            quantity=0.1,
        )

        # Should work without deduct_fees parameter (backward compatible)
        pnl = position.calculate_pnl(51000.0)
        assert pnl == 100.0

    @pytest.mark.asyncio
    async def test_open_position_backward_compatible(self, tracker):
        """Test that open_position still works without entry_fees argument."""
        position = await tracker.open_position(
            symbol="BTC/USDT",
            side="long",
            entry_price=50000.0,
            quantity=0.1,
            # No entry_fees parameter
        )
        assert position.entry_fees == 0.0

    @pytest.mark.asyncio
    async def test_close_position_backward_compatible(self, tracker):
        """Test that close_position still works without exit_fees argument."""
        position = await tracker.open_position(
            symbol="BTC/USDT",
            side="long",
            entry_price=50000.0,
            quantity=0.1,
        )

        # Should work without exit_fees parameter (backward compatible)
        closed_pos, pnl = await tracker.close_position(
            position_id=position.position_id,
            exit_price=51000.0,
            # No exit_fees parameter
        )
        assert closed_pos.exit_fees == 0.0
        assert pnl == 100.0


class TestFeeExampleScenario:
    """Realistic scenario test demonstrating the KPI fix.

    This test demonstrates the scenario described in the bug report:
    - Position shows positive gross PnL
    - But net PnL after fees is actually negative
    - KPI should reflect reality (net PnL), not gross PnL
    """

    @pytest.fixture
    async def tracker(self):
        """Create a fresh tracker for each test."""
        tracker = PaperPositionTracker()
        yield tracker
        await tracker.clear_all()

    @pytest.mark.asyncio
    async def test_bybit_reality_vs_paper_kpi(self, tracker):
        """Test demonstrating the Bybit reality vs paper KPI issue.

        Scenario:
        - Open long position of 0.01 BTC at $50,000
        - Entry fees: $10 (taker fee on Bybit)
        - Close at $50,050 (small profit)
        - Exit fees: $10 (taker fee on Bybit)

        Before fix:
        - Paper KPI showed: $0.50 profit (gross)
        - Bybit reality: -$19.50 loss (after fees)

        After fix:
        - Paper KPI shows: -$19.50 loss (net, matching Bybit)
        """
        # Open position with realistic fees
        position = await tracker.open_position(
            symbol="BTC/USDT",
            side="long",
            entry_price=50000.0,
            quantity=0.01,
            entry_fees=10.0,  # Bybit taker fee
        )

        # Gross PnL would be $0.50 (0.01 BTC * $50 price move)
        gross_pnl = position.calculate_pnl(50050.0)
        assert gross_pnl == 0.50

        # But net PnL after fees is negative
        net_pnl = position.calculate_pnl(50050.0, deduct_fees=True)
        assert net_pnl == -9.50  # $0.50 - $10 entry fees

        # Close position with exit fees
        closed_pos, realized_pnl = await tracker.close_position(
            position_id=position.position_id,
            exit_price=50050.0,
            exit_fees=10.0,  # Bybit taker fee
        )

        # Total fees: $20 ($10 entry + $10 exit)
        assert closed_pos.total_fees == 20.0

        # Realized PnL is now NET (matching Bybit reality)
        # $0.50 gross - $20 fees = -$19.50 net loss
        assert realized_pnl == -19.50

        # This is the critical fix: KPI now shows the actual loss,
        # not the misleading gross profit
        print(f"\nKPI Fix Demonstration:")
        print(f"  Gross PnL: ${gross_pnl:.2f}")
        print(f"  Total fees: ${closed_pos.total_fees:.2f}")
        print(f"  Net PnL (reality): ${realized_pnl:.2f}")
        print(f"  KPI now matches Bybit: {'YES' if realized_pnl < 0 else 'NO'}")
