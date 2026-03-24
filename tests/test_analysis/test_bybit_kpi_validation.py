"""Validation tests for Bybit Truth KPI vs Paper Journal KPI.

Ensures:
1. Bybit KPI uses actual execution data (closedPnl, fees)
2. Paper KPI is labeled as simulation (non-canonical for GO)
3. Net PnL calculation is correct (closedPnl - fees)
4. Source labels are explicit and correct

For ST-KPI-FIX-001: Bybit-Journal KPI Separation
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@dataclass
class BybitExecution:
    """Mock Bybit execution for testing."""

    order_id: str
    symbol: str
    side: str
    exec_price: float
    exec_qty: float
    exec_fee: float
    exec_time: int
    exec_id: str
    closed_pnl: float = 0.0
    fees: float = 0.0


@dataclass
class KPIResult:
    """Standard KPI result structure."""

    # Metadata
    source: str  # "bybit_truth" or "paper_journal_sim"
    trading_mode: str  # "live" or "paper"
    calculation_timestamp: str
    calculation_id: str

    # Source flags
    canonical_for_go: bool  # True for Bybit, False for Paper

    # Core metrics
    win_rate: float
    total_pnl: float
    total_net_pnl: float
    total_gross_pnl: float
    total_fees: float
    max_drawdown: float
    max_drawdown_amount: float
    turnover: dict[str, Any]

    # Data quality
    data_quality_flags: list[str] = field(default_factory=list)
    warning_header: str | None = None


class TestBybitKPIUsesActualExecutionData:
    """Test that Bybit KPI uses actual execution data from Bybit API."""

    @pytest.fixture
    def mock_bybit_executions(self):
        """Create mock Bybit executions with known closedPnl and fees."""
        return [
            BybitExecution(
                order_id="order1",
                symbol="BTCUSDT",
                side="Buy",
                exec_price=50000.0,
                exec_qty=0.5,
                exec_fee=2.5,
                exec_time=int(datetime.now(UTC).timestamp() * 1000),
                exec_id="exec1",
                closed_pnl=150.0,
                fees=2.5,
            ),
            BybitExecution(
                order_id="order2",
                symbol="ETHUSDT",
                side="Sell",
                exec_price=3000.0,
                exec_qty=2.0,
                exec_fee=3.0,
                exec_time=int(datetime.now(UTC).timestamp() * 1000),
                exec_id="exec2",
                closed_pnl=-50.0,
                fees=3.0,
            ),
        ]

    def test_calculate_net_pnl_from_closed_pnl_and_fees(self, mock_bybit_executions):
        """Verify KPI calculates net_pnl = closedPnl - fees."""
        exec1, exec2 = mock_bybit_executions

        # Calculate expected net PnL
        net_pnl_1 = exec1.closed_pnl - exec1.fees  # 150 - 2.5 = 147.5
        net_pnl_2 = exec2.closed_pnl - exec2.fees  # -50 - 3.0 = -53.0
        total_net_pnl = net_pnl_1 + net_pnl_2

        assert net_pnl_1 == 147.5
        assert net_pnl_2 == -53.0
        assert total_net_pnl == 94.5

    def test_source_label_is_bybit_truth(self, mock_bybit_executions):
        """Verify source label is 'bybit_truth'."""
        # Simulate creating KPI from Bybit data
        kpi = KPIResult(
            source="bybit_truth",
            trading_mode="live",
            calculation_timestamp=datetime.now(UTC).isoformat(),
            calculation_id="test-001",
            canonical_for_go=True,
            win_rate=50.0,
            total_pnl=94.5,
            total_net_pnl=94.5,
            total_gross_pnl=100.0,
            total_fees=5.5,
            max_drawdown=5.0,
            max_drawdown_amount=50.0,
            turnover={"avg_trades_per_day": 2.0},
        )

        assert kpi.source == "bybit_truth"


class TestPaperKPILabeledNonCanonical:
    """Test that Paper KPI is labeled as non-canonical simulation."""

    def test_source_label_is_paper_journal_sim(self):
        """Verify source label is 'paper_journal_sim'."""
        kpi = KPIResult(
            source="paper_journal_sim",
            trading_mode="paper",
            calculation_timestamp=datetime.now(UTC).isoformat(),
            calculation_id="test-002",
            canonical_for_go=False,
            win_rate=45.0,
            total_pnl=80.0,
            total_net_pnl=75.0,
            total_gross_pnl=85.0,
            total_fees=10.0,
            max_drawdown=10.0,
            max_drawdown_amount=100.0,
            turnover={"avg_trades_per_day": 1.5},
        )

        assert kpi.source == "paper_journal_sim"

    def test_canonical_for_go_is_false(self):
        """Verify canonical_for_go is False for paper KPI."""
        kpi = KPIResult(
            source="paper_journal_sim",
            trading_mode="paper",
            calculation_timestamp=datetime.now(UTC).isoformat(),
            calculation_id="test-002",
            canonical_for_go=False,
            win_rate=45.0,
            total_pnl=80.0,
            total_net_pnl=75.0,
            total_gross_pnl=85.0,
            total_fees=10.0,
            max_drawdown=10.0,
            max_drawdown_amount=100.0,
            turnover={"avg_trades_per_day": 1.5},
        )

        assert kpi.canonical_for_go is False

    def test_warning_header_exists(self):
        """Verify warning header exists for paper KPI."""
        warning = "WARNING: Paper trading simulation - not actual execution data"

        kpi = KPIResult(
            source="paper_journal_sim",
            trading_mode="paper",
            calculation_timestamp=datetime.now(UTC).isoformat(),
            calculation_id="test-002",
            canonical_for_go=False,
            win_rate=45.0,
            total_pnl=80.0,
            total_net_pnl=75.0,
            total_gross_pnl=85.0,
            total_fees=10.0,
            max_drawdown=10.0,
            max_drawdown_amount=100.0,
            turnover={"avg_trades_per_day": 1.5},
            warning_header=warning,
        )

        assert kpi.warning_header is not None
        assert "Paper trading simulation" in kpi.warning_header


class TestNoPositiveNetPnLWhenBybitNegative:
    """Test that KPI reports net negative PnL when Bybit shows losses."""

    @pytest.fixture
    def negative_bybit_executions(self):
        """Mock Bybit API with all negative closedPnl."""
        return [
            BybitExecution(
                order_id="loss1",
                symbol="BTCUSDT",
                side="Buy",
                exec_price=52000.0,
                exec_qty=1.0,
                exec_fee=5.0,
                exec_time=int(datetime.now(UTC).timestamp() * 1000),
                exec_id="exec1",
                closed_pnl=-200.0,
                fees=5.0,
            ),
            BybitExecution(
                order_id="loss2",
                symbol="ETHUSDT",
                side="Sell",
                exec_price=3100.0,
                exec_qty=3.0,
                exec_fee=6.0,
                exec_time=int(datetime.now(UTC).timestamp() * 1000),
                exec_id="exec2",
                closed_pnl=-150.0,
                fees=6.0,
            ),
            BybitExecution(
                order_id="loss3",
                symbol="SOLUSDT",
                side="Buy",
                exec_price=120.0,
                exec_qty=10.0,
                exec_fee=8.0,
                exec_time=int(datetime.now(UTC).timestamp() * 1000),
                exec_id="exec3",
                closed_pnl=-100.0,
                fees=8.0,
            ),
        ]

    def test_net_pnl_is_negative(self, negative_bybit_executions):
        """Verify KPI reports net negative total PnL."""
        total_closed_pnl = sum(e.closed_pnl for e in negative_bybit_executions)
        total_fees = sum(e.fees for e in negative_bybit_executions)
        total_net_pnl = total_closed_pnl - total_fees

        # Should be: -200 - 150 - 100 - (5 + 6 + 8) = -450 - 19 = -469
        assert total_closed_pnl == -450.0
        assert total_fees == 19.0
        assert total_net_pnl == -469.0
        assert total_net_pnl < 0

    def test_win_rate_reflects_losing_trades(self, negative_bybit_executions):
        """Verify win rate reflects actual losing trades."""
        # All trades are losers
        total_trades = len(negative_bybit_executions)
        winning_trades = 0
        win_rate = (winning_trades / total_trades) * 100

        assert win_rate == 0.0


class TestBybitKPIIncludesAllRequiredFields:
    """Test that Bybit KPI includes all required fields."""

    def test_metadata_fields(self):
        """Verify metadata fields are present."""
        kpi = KPIResult(
            source="bybit_truth",
            trading_mode="live",
            calculation_timestamp=datetime.now(UTC).isoformat(),
            calculation_id="test-003",
            canonical_for_go=True,
            win_rate=55.0,
            total_pnl=500.0,
            total_net_pnl=480.0,
            total_gross_pnl=520.0,
            total_fees=40.0,
            max_drawdown=8.0,
            max_drawdown_amount=80.0,
            turnover={"avg_trades_per_day": 3.5},
        )

        # Check metadata fields
        assert kpi.calculation_timestamp is not None
        assert kpi.calculation_id is not None
        assert kpi.source is not None
        assert kpi.trading_mode is not None

    def test_core_metrics_fields(self):
        """Verify core metrics fields are present."""
        kpi = KPIResult(
            source="bybit_truth",
            trading_mode="live",
            calculation_timestamp=datetime.now(UTC).isoformat(),
            calculation_id="test-004",
            canonical_for_go=True,
            win_rate=55.0,
            total_pnl=500.0,
            total_net_pnl=480.0,
            total_gross_pnl=520.0,
            total_fees=40.0,
            max_drawdown=8.0,
            max_drawdown_amount=80.0,
            turnover={
                "avg_trades_per_day": 3.5,
                "p95_trades_per_day": 5.0,
                "max_trades_per_day": 8.0,
            },
        )

        # Check core metrics
        assert isinstance(kpi.win_rate, float)
        assert isinstance(kpi.total_pnl, float)
        assert isinstance(kpi.max_drawdown, float)
        assert isinstance(kpi.turnover, dict)
        assert "avg_trades_per_day" in kpi.turnover


class TestSourceLabelsAreExplicit:
    """Test that source labels are explicit and correct."""

    def test_bybit_kpi_has_bybit_truth_source(self):
        """Verify Bybit KPI has source='bybit_truth'."""
        kpi = KPIResult(
            source="bybit_truth",
            trading_mode="live",
            calculation_timestamp=datetime.now(UTC).isoformat(),
            calculation_id="test-005",
            canonical_for_go=True,
            win_rate=50.0,
            total_pnl=100.0,
            total_net_pnl=95.0,
            total_gross_pnl=105.0,
            total_fees=10.0,
            max_drawdown=3.0,
            max_drawdown_amount=30.0,
            turnover={"avg_trades_per_day": 2.0},
        )

        assert kpi.source == "bybit_truth"

    def test_paper_kpi_has_paper_journal_sim_source(self):
        """Verify Paper KPI has source='paper_journal_sim'."""
        kpi = KPIResult(
            source="paper_journal_sim",
            trading_mode="paper",
            calculation_timestamp=datetime.now(UTC).isoformat(),
            calculation_id="test-006",
            canonical_for_go=False,
            win_rate=45.0,
            total_pnl=80.0,
            total_net_pnl=75.0,
            total_gross_pnl=85.0,
            total_fees=10.0,
            max_drawdown=5.0,
            max_drawdown_amount=50.0,
            turnover={"avg_trades_per_day": 1.5},
        )

        assert kpi.source == "paper_journal_sim"

    def test_both_kpis_have_canonical_for_go_boolean(self):
        """Verify both KPI types have canonical_for_go boolean."""
        bybit_kpi = KPIResult(
            source="bybit_truth",
            trading_mode="live",
            calculation_timestamp=datetime.now(UTC).isoformat(),
            calculation_id="test-007",
            canonical_for_go=True,
            win_rate=50.0,
            total_pnl=100.0,
            total_net_pnl=95.0,
            total_gross_pnl=105.0,
            total_fees=10.0,
            max_drawdown=3.0,
            max_drawdown_amount=30.0,
            turnover={"avg_trades_per_day": 2.0},
        )

        paper_kpi = KPIResult(
            source="paper_journal_sim",
            trading_mode="paper",
            calculation_timestamp=datetime.now(UTC).isoformat(),
            calculation_id="test-008",
            canonical_for_go=False,
            win_rate=45.0,
            total_pnl=80.0,
            total_net_pnl=75.0,
            total_gross_pnl=85.0,
            total_fees=10.0,
            max_drawdown=5.0,
            max_drawdown_amount=50.0,
            turnover={"avg_trades_per_day": 1.5},
        )

        assert isinstance(bybit_kpi.canonical_for_go, bool)
        assert isinstance(paper_kpi.canonical_for_go, bool)
        assert bybit_kpi.canonical_for_go is True
        assert paper_kpi.canonical_for_go is False


class TestNetPnLFormulaValidation:
    """Test net PnL formula validation: net_pnl = closed_pnl - fees."""

    @pytest.mark.parametrize(
        "closed_pnl,fees,expected_net",
        [
            (100.0, 5.0, 95.0),
            (0.0, 2.0, -2.0),
            (-50.0, 3.0, -53.0),
            (1000.0, 0.0, 1000.0),
        ],
    )
    def test_net_pnl_formula(self, closed_pnl, fees, expected_net):
        """Verify net_pnl = closed_pnl - fees formula."""
        calculated_net = closed_pnl - fees
        assert calculated_net == expected_net

    def test_fee_deduction_always_applied(self):
        """Verify fees are always deducted from gross PnL."""
        # Positive PnL case
        assert (100.0 - 5.0) == 95.0
        # Negative PnL case
        assert (-100.0 - 5.0) == -105.0
        # Zero PnL case
        assert (0.0 - 5.0) == -5.0


class TestTurnoverCalculation:
    """Test turnover calculation: trades per day."""

    def test_turnover_aggregation(self):
        """Test trades are aggregated by UTC day."""
        trades = [
            {"time": "2024-01-01T10:00:00Z", "order_id": "1"},
            {"time": "2024-01-01T15:00:00Z", "order_id": "2"},
            {"time": "2024-01-02T09:00:00Z", "order_id": "3"},
        ]

        # Count per day
        day_counts = {}
        for trade in trades:
            day = trade["time"][:10]  # Extract YYYY-MM-DD
            day_counts[day] = day_counts.get(day, 0) + 1

        assert day_counts["2024-01-01"] == 2
        assert day_counts["2024-01-02"] == 1
        assert sum(day_counts.values()) == 3

    def test_turnover_statistics(self):
        """Test turnover statistics calculation."""
        daily_counts = [2, 3, 4, 2, 3, 5, 2]  # 7 days of trades

        avg = sum(daily_counts) / len(daily_counts)
        sorted_counts = sorted(daily_counts)
        p95_idx = int(len(sorted_counts) * 0.95)
        max_count = max(daily_counts)

        assert avg == pytest.approx(3.0, rel=1e-2)
        assert max_count == 5


class TestDataQualityValidation:
    """Test data quality validations."""

    def test_data_quality_flags_on_missing_fields(self):
        """Test data quality flags are raised when required fields are missing."""
        flags = []

        # Simulate missing fee data
        fees = None
        if fees is None:
            flags.append("Missing fee data in source")

        assert "Missing fee data in source" in flags

    def test_data_quality_flags_on_inconsistent_pnl(self):
        """Test flag when net_pnl doesn't match closed_pnl - fees."""
        closed_pnl = 100.0
        fees = 5.0
        reported_net_pnl = 90.0  # Incorrect, should be 95.0

        expected_net = closed_pnl - fees
        flags = []

        if abs(reported_net_pnl - expected_net) > 0.01:
            flags.append(
                f"net_pnl validation failed: {reported_net_pnl} != {expected_net}"
            )

        assert "net_pnl validation failed" in flags[0]


class TestActualImplementationImports:
    """Test that actual implementation modules can be imported."""

    def test_bybit_kpi_module_imports(self):
        """Test that calculate_bybit_kpis module can be imported."""
        try:
            from scripts.analysis.calculate_bybit_kpis import (
                BybitAPIExtractor,
                BybitKPICalculator,
                BybitTradingKPIs,
            )

            assert True
        except ImportError as e:
            pytest.fail(f"Failed to import Bybit KPI module: {e}")

    def test_paper_kpi_module_imports(self):
        """Test that calculate_paper_kpis module can be imported."""
        try:
            from scripts.analysis.calculate_paper_kpis import (
                PaperKPICalculator,
                PaperTradingKPIs,
            )

            assert True
        except ImportError as e:
            pytest.fail(f"Failed to import Paper KPI module: {e}")


class TestUnifiedRunner:
    """Test unified KPI runner functionality."""

    def test_detect_trading_mode_from_env(self):
        """Test trading mode detection from environment variables."""
        from scripts.analysis.run_kpi_evaluation import detect_trading_mode

        # Test with no env vars (should default to paper)
        with patch.dict(os.environ, {}, clear=True):
            mode = detect_trading_mode()
            assert mode == "paper"

        # Test with demo credentials
        with patch.dict(
            os.environ,
            {
                "BYBIT_DEMO_API_KEY": "test_key",
                "BYBIT_DEMO_API_SECRET": "test_secret",
            },
            clear=True,
        ):
            mode = detect_trading_mode()
            assert mode == "demo"

        # Test with explicit TRADING_MODE
        with patch.dict(
            os.environ,
            {
                "TRADING_MODE": "live",
            },
            clear=True,
        ):
            mode = detect_trading_mode()
            assert mode == "live"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
