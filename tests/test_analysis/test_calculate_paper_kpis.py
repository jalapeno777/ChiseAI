#!/usr/bin/env python3
"""Tests for calculate_paper_kpis.py.

Tests cover:
- net_pnl validation logic
- gross vs net PnL calculations
- data quality flag detection
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

import pytest
from datetime import datetime, UTC
from unittest.mock import Mock

from scripts.analysis.calculate_paper_kpis import (
    PaperTradingKPIs,
    PaperKPICalculator,
    LatencyStats,
    calculate_max_drawdown,
    calculate_percentile,
)


def create_mock_calculator(entries):
    """Helper to create a calculator with properly mocked extractor."""
    mock_extractor = Mock()
    mock_extractor.fetch_journal_entries.return_value = entries
    mock_extractor.fetch_risk_gate_data.return_value = (
        len(entries),
        len(entries),
    )  # (passed, total)
    return PaperKPICalculator(mock_extractor)


class TestNetPnLValidation:
    """Test net_pnl validation logic."""

    def test_valid_net_pnl_calculation(self):
        """Test that valid net_pnl = realized_pnl - fees passes validation."""
        # Create entry with correct net_pnl
        entry = {
            "entry_id": "test-001",
            "is_closed": True,
            "realized_pnl": 100.0,
            "fees": 5.0,
            "net_pnl": 95.0,  # 100 - 5 = 95 ✓
            "entry_time": datetime.now(UTC).isoformat(),
            "exit_time": datetime.now(UTC).isoformat(),
        }

        calculator = create_mock_calculator([entry])
        kpis = calculator.calculate(lookback_days=7, story_id="TEST-001")

        assert kpis.net_pnl_validation_passed is True
        assert "net_pnl validation" not in " ".join(kpis.data_quality_flags)

    def test_invalid_net_pnl_calculation(self):
        """Test that incorrect net_pnl triggers validation failure."""
        # Create entry with incorrect net_pnl
        entry = {
            "entry_id": "test-002",
            "is_closed": True,
            "realized_pnl": 100.0,
            "fees": 5.0,
            "net_pnl": 90.0,  # Should be 95, but is 90 ✗
            "entry_time": datetime.now(UTC).isoformat(),
            "exit_time": datetime.now(UTC).isoformat(),
        }

        calculator = create_mock_calculator([entry])
        kpis = calculator.calculate(lookback_days=7, story_id="TEST-002")

        assert kpis.net_pnl_validation_passed is False
        assert any("net_pnl validation" in flag for flag in kpis.data_quality_flags)

    def test_missing_realized_pnl_skips_validation(self):
        """Test that missing realized_pnl skips formula validation."""
        entry = {
            "entry_id": "test-003",
            "is_closed": True,
            "realized_pnl": None,
            "fees": 5.0,
            "net_pnl": 95.0,
            "entry_time": datetime.now(UTC).isoformat(),
            "exit_time": datetime.now(UTC).isoformat(),
        }

        calculator = create_mock_calculator([entry])
        kpis = calculator.calculate(lookback_days=7, story_id="TEST-003")

        # Validation should pass because we can't verify without realized_pnl
        assert kpis.net_pnl_validation_passed is True


class TestGrossVsNetPnL:
    """Test gross vs net PnL tracking."""

    def test_gross_pnl_calculation(self):
        """Test that total_gross_pnl sums realized_pnl correctly."""
        entries = [
            {
                "entry_id": "test-001",
                "is_closed": True,
                "realized_pnl": 100.0,
                "fees": 5.0,
                "net_pnl": 95.0,
                "entry_time": datetime.now(UTC).isoformat(),
                "exit_time": datetime.now(UTC).isoformat(),
            },
            {
                "entry_id": "test-002",
                "is_closed": True,
                "realized_pnl": 200.0,
                "fees": 10.0,
                "net_pnl": 190.0,
                "entry_time": datetime.now(UTC).isoformat(),
                "exit_time": datetime.now(UTC).isoformat(),
            },
        ]

        calculator = create_mock_calculator(entries)
        kpis = calculator.calculate(lookback_days=7, story_id="TEST-001")

        # Gross should be sum of realized_pnl
        assert kpis.total_gross_pnl == 300.0  # 100 + 200
        # Net should be sum of net_pnl
        assert kpis.total_net_pnl == 285.0  # 95 + 190
        # Fees should be sum of fees
        assert kpis.total_fees == 15.0  # 5 + 10

    def test_fee_impact_calculation(self):
        """Test fee impact percentage calculation."""
        entries = [
            {
                "entry_id": "test-001",
                "is_closed": True,
                "realized_pnl": 100.0,
                "fees": 10.0,
                "net_pnl": 90.0,
                "entry_time": datetime.now(UTC).isoformat(),
                "exit_time": datetime.now(UTC).isoformat(),
            },
        ]

        calculator = create_mock_calculator(entries)
        kpis = calculator.calculate(lookback_days=7, story_id="TEST-001")

        # Fee impact = (fees / |gross|) * 100 = (10 / 100) * 100 = 10%
        assert kpis.fee_impact_percent == 10.0

    def test_fee_impact_with_negative_gross(self):
        """Test fee impact with losing trades."""
        entries = [
            {
                "entry_id": "test-001",
                "is_closed": True,
                "realized_pnl": -100.0,
                "fees": 10.0,
                "net_pnl": -110.0,
                "entry_time": datetime.now(UTC).isoformat(),
                "exit_time": datetime.now(UTC).isoformat(),
            },
        ]

        calculator = create_mock_calculator(entries)
        kpis = calculator.calculate(lookback_days=7, story_id="TEST-001")

        # Fee impact should use absolute value: (10 / 100) * 100 = 10%
        assert kpis.fee_impact_percent == 10.0

    def test_zero_gross_pnl_fee_impact(self):
        """Test fee impact when gross PnL is zero."""
        entries = [
            {
                "entry_id": "test-001",
                "is_closed": True,
                "realized_pnl": 0.0,
                "fees": 10.0,
                "net_pnl": -10.0,
                "entry_time": datetime.now(UTC).isoformat(),
                "exit_time": datetime.now(UTC).isoformat(),
            },
        ]

        calculator = create_mock_calculator(entries)
        kpis = calculator.calculate(lookback_days=7, story_id="TEST-001")

        # Should handle division by zero gracefully
        assert kpis.fee_impact_percent == 0.0


class TestDataQualityFlags:
    """Test data quality flag detection."""

    def test_fees_exceed_realized_pnl_flag(self):
        """Test flag when fees exceed realized_pnl."""
        entries = [
            {
                "entry_id": "test-001",
                "is_closed": True,
                "realized_pnl": 50.0,
                "fees": 60.0,  # Fees exceed realized PnL
                "net_pnl": -10.0,
                "entry_time": datetime.now(UTC).isoformat(),
                "exit_time": datetime.now(UTC).isoformat(),
            },
        ]

        calculator = create_mock_calculator(entries)
        kpis = calculator.calculate(lookback_days=7, story_id="TEST-001")

        assert any(
            "Fees" in flag and "exceed realized_pnl" in flag
            for flag in kpis.data_quality_flags
        )

    def test_missing_fee_data_flag(self):
        """Test flag when fee data is missing."""
        entries = [
            {
                "entry_id": "test-001",
                "is_closed": True,
                "realized_pnl": 100.0,
                "fees": None,  # Missing fee data
                "net_pnl": 100.0,
                "entry_time": datetime.now(UTC).isoformat(),
                "exit_time": datetime.now(UTC).isoformat(),
            },
        ]

        calculator = create_mock_calculator(entries)
        kpis = calculator.calculate(lookback_days=7, story_id="TEST-001")

        assert any("Missing fee data" in flag for flag in kpis.data_quality_flags)

    def test_no_data_quality_issues(self):
        """Test that clean data produces no flags."""
        entries = [
            {
                "entry_id": "test-001",
                "is_closed": True,
                "realized_pnl": 100.0,
                "fees": 5.0,
                "net_pnl": 95.0,
                "entry_time": datetime.now(UTC).isoformat(),
                "exit_time": datetime.now(UTC).isoformat(),
            },
        ]

        calculator = create_mock_calculator(entries)
        kpis = calculator.calculate(lookback_days=7, story_id="TEST-001")

        # Should have no quality flags except validation-related
        non_validation_flags = [
            f for f in kpis.data_quality_flags if "net_pnl validation" not in f
        ]
        assert len(non_validation_flags) == 0

    def test_empty_kpis_data_quality_flags(self):
        """Test that empty KPIs include appropriate data quality flag."""
        calculator = create_mock_calculator([])
        kpis = calculator.calculate(lookback_days=7, story_id="TEST-001")

        assert kpis.net_pnl_validation_passed is True
        assert "No data available" in " ".join(kpis.data_quality_flags)


class TestPaperTradingKPIsDataclass:
    """Test the PaperTradingKPIs dataclass."""

    def test_dataclass_creation(self):
        """Test that PaperTradingKPIs can be created with all required fields."""
        now = datetime.now(UTC)

        kpis = PaperTradingKPIs(
            calculation_id="TEST-001",
            story_id="ST-TEST-001",
            calculation_timestamp=now.isoformat(),
            data_start_time=now.isoformat(),
            data_end_time=now.isoformat(),
            lookback_days=7,
            total_trades=10,
            winning_trades=6,
            losing_trades=4,
            open_trades=0,
            win_rate=60.0,
            total_pnl=1000.0,
            total_net_pnl=1000.0,
            total_gross_pnl=1100.0,
            total_fees=100.0,
            fee_impact_percent=9.09,
            avg_pnl_per_trade=100.0,
            max_drawdown=5.0,
            max_drawdown_amount=50.0,
            turnover={"avg_trades_per_day": 1.0},
            latency_ms=LatencyStats(p50_ms=100, p95_ms=200, p99_ms=300, count=10),
            risk_gate_adherence=100.0,
            data_freshness_hours=1.0,
            is_data_fresh=True,
            net_pnl_validation_passed=True,
            data_quality_flags=[],
        )

        assert kpis.total_net_pnl == 1000.0
        assert kpis.total_gross_pnl == 1100.0
        assert kpis.total_fees == 100.0
        assert kpis.net_pnl_validation_passed is True


class TestHelperFunctions:
    """Test helper functions."""

    def test_calculate_percentile(self):
        """Test percentile calculation."""
        values = [1.0, 2.0, 3.0, 4.0, 5.0]

        assert calculate_percentile(values, 50) == 3.0  # median
        assert calculate_percentile(values, 0) == 1.0
        assert calculate_percentile(values, 100) == 5.0

    def test_calculate_max_drawdown(self):
        """Test max drawdown calculation."""
        # Series with a drawdown
        pnl_series = [100.0, 50.0, -30.0, 80.0]  # Peak at 100, trough at 120-30=90
        dd_pct, dd_amount = calculate_max_drawdown(pnl_series)

        assert dd_pct > 0
        assert dd_amount > 0

    def test_calculate_max_drawdown_empty(self):
        """Test max drawdown with empty series."""
        dd_pct, dd_amount = calculate_max_drawdown([])

        assert dd_pct == 0.0
        assert dd_amount == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
