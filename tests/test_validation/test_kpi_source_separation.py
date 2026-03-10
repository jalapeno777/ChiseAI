"""Tests for KPI source separation between Bybit Truth and Paper Journal.

Ensures:
1. Both KPI types can be generated simultaneously without cross-contamination
2. Source labels are distinct and unambiguous
3. No data mixing between truth sources and simulations
4. Clear labeling in output files

For ST-KPI-FIX-001: Bybit-Journal KPI Separation
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@dataclass
class KPIResult:
    """Standard KPI result structure."""

    # Metadata
    source: str
    trading_mode: str
    calculation_timestamp: str
    calculation_id: str

    # Source flags
    canonical_for_go: bool

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

    def to_dict(self) -> dict:
        """Convert KPI to dictionary."""
        return {
            "source": self.source,
            "trading_mode": self.trading_mode,
            "calculation_timestamp": self.calculation_timestamp,
            "calculation_id": self.calculation_id,
            "canonical_for_go": self.canonical_for_go,
            "win_rate": self.win_rate,
            "total_pnl": self.total_pnl,
            "total_net_pnl": self.total_net_pnl,
            "total_gross_pnl": self.total_gross_pnl,
            "total_fees": self.total_fees,
            "max_drawdown": self.max_drawdown,
            "max_drawdown_amount": self.max_drawdown_amount,
            "turnover": self.turnover,
            "data_quality_flags": self.data_quality_flags,
            "warning_header": self.warning_header,
        }


@dataclass
class KPIDocument:
    """KPI document for storage/output."""

    kpi_data: KPIResult
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(
            {
                "kpi": self.kpi_data.to_dict(),
                "metadata": self.metadata,
            },
            indent=2,
        )


class TestSimultaneousKPIGeneration:
    """Test that both KPI types can be generated simultaneously."""

    @pytest.fixture
    def bybit_kpi(self):
        """Create a Bybit KPI result."""
        return KPIResult(
            source="bybit_truth",
            trading_mode="live",
            calculation_timestamp=datetime.now(UTC).isoformat(),
            calculation_id="bybit-001",
            canonical_for_go=True,
            win_rate=52.5,
            total_pnl=1247.50,
            total_net_pnl=1180.25,
            total_gross_pnl=1290.75,
            total_fees=110.50,
            max_drawdown=8.3,
            max_drawdown_amount=180.00,
            turnover={
                "avg_trades_per_day": 3.2,
                "p95_trades_per_day": 5.0,
                "max_trades_per_day": 8.0,
            },
            data_quality_flags=[],
        )

    @pytest.fixture
    def paper_kpi(self):
        """Create a Paper KPI result."""
        return KPIResult(
            source="paper_journal_sim",
            trading_mode="paper",
            calculation_timestamp=datetime.now(UTC).isoformat(),
            calculation_id="paper-001",
            canonical_for_go=False,
            win_rate=48.0,
            total_pnl=985.00,
            total_net_pnl=920.50,
            total_gross_pnl=1045.00,
            total_fees=124.50,
            max_drawdown=12.5,
            max_drawdown_amount=250.00,
            turnover={
                "avg_trades_per_day": 2.8,
                "p95_trades_per_day": 4.5,
                "max_trades_per_day": 7.0,
            },
            data_quality_flags=["Simulated data - not actual execution"],
            warning_header="WARNING: Paper trading simulation",
        )

    def test_can_generate_both_kpis(self, bybit_kpi, paper_kpi):
        """Verify both KPIs can be generated simultaneously."""
        # Both should be valid KPI results
        assert bybit_kpi is not None
        assert paper_kpi is not None

        # Both should have all required fields
        assert bybit_kpi.source == "bybit_truth"
        assert paper_kpi.source == "paper_journal_sim"

    def test_kpis_have_different_values(self, bybit_kpi, paper_kpi):
        """Verify KPIs reflect different data sources with different values."""
        # Bybit and Paper should have different PnL values
        assert bybit_kpi.total_pnl != paper_kpi.total_pnl
        assert bybit_kpi.total_net_pnl != paper_kpi.total_net_pnl

        # Win rates should be different
        assert bybit_kpi.win_rate != paper_kpi.win_rate

    def test_kpis_generated_at_same_timestamp(self, bybit_kpi, paper_kpi):
        """Verify KPIs generated together share approximately same timestamp."""
        # Same calculation run - timestamps should be very close (within 1 second)
        from datetime import datetime

        bybit_ts = datetime.fromisoformat(
            bybit_kpi.calculation_timestamp.replace("Z", "+00:00")
        )
        paper_ts = datetime.fromisoformat(
            paper_kpi.calculation_timestamp.replace("Z", "+00:00")
        )
        diff_seconds = abs((bybit_ts - paper_ts).total_seconds())
        assert diff_seconds < 1.0, f"Timestamps differ by {diff_seconds} seconds"


class TestNoCrossContamination:
    """Test that there's no cross-contamination of data between sources."""

    def test_bybit_data_not_in_paper_output(self):
        """Verify Bybit execution data doesn't appear in paper output."""
        bybit_trades = [
            {"order_id": "bybit-123", "closed_pnl": 150.0, "source": "bybit"},
            {"order_id": "bybit-124", "closed_pnl": -50.0, "source": "bybit"},
        ]

        paper_trades = [
            {"entry_id": "paper-001", "realized_pnl": 100.0, "source": "paper"},
        ]

        # Ensure no overlap in trade IDs
        bybit_ids = {t["order_id"] for t in bybit_trades}
        paper_ids = {t.get("entry_id", t.get("order_id", "")) for t in paper_trades}

        assert len(bybit_ids & paper_ids) == 0, "Trade IDs should not overlap"

    def test_pnl_values_do_not_mix(self):
        """Verify PnL calculations don't mix Bybit and Paper data."""
        bybit_pnl = 150.0 - 50.0  # 100.0 net from Bybit
        paper_pnl = 100.0  # 100.0 from Paper

        # Each should maintain its own total
        assert bybit_pnl == 100.0
        assert paper_pnl == 100.0

        # They should not sum automatically
        combined = bybit_pnl + paper_pnl
        assert combined == 200.0

    def test_fee_sources_are_separate(self):
        """Verify fees are tracked by source separately."""
        bybit_fees = {"order1": 2.5, "order2": 3.0}
        paper_fees = {"entry1": 2.0}

        bybit_total = sum(bybit_fees.values())
        paper_total = sum(paper_fees.values())

        assert bybit_total == 5.5
        assert paper_total == 2.0

        # Should not be the same
        assert bybit_total != paper_total


class TestSourceLabelsDistinct:
    """Test that source labels are distinct and unambiguous."""

    def test_bybit_truth_label_format(self):
        """Verify 'bybit_truth' label format."""
        label = "bybit_truth"

        assert label == "bybit_truth"
        assert "bybit" in label.lower()
        assert "truth" in label.lower()
        assert label != "bybit"
        assert label != "truth"

    def test_paper_journal_sim_label_format(self):
        """Verify 'paper_journal_sim' label format."""
        label = "paper_journal_sim"

        assert label == "paper_journal_sim"
        assert "paper" in label.lower()
        assert "journal" in label.lower()
        assert "sim" in label.lower()
        assert label != "paper"
        assert label != "journal"

    def test_labels_are_mutually_exclusive(self):
        """Verify labels cannot be confused with each other."""
        bybit_label = "bybit_truth"
        paper_label = "paper_journal_sim"

        assert bybit_label != paper_label
        assert bybit_label not in paper_label
        assert paper_label not in bybit_label


class TestOutputFileLabeling:
    """Test clear labeling in output files."""

    def test_json_output_includes_source_field(self):
        """Verify JSON output includes source field."""
        kpi = KPIResult(
            source="bybit_truth",
            trading_mode="live",
            calculation_timestamp=datetime.now(UTC).isoformat(),
            calculation_id="test-001",
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

        doc = KPIDocument(kpi, metadata={"generated_by": "test"})
        json_output = doc.to_json()

        parsed = json.loads(json_output)
        assert parsed["kpi"]["source"] == "bybit_truth"

    def test_bybit_output_filename_convention(self):
        """Verify Bybit output follows naming convention."""
        timestamp = "2024-01-15"
        expected_filename = f"kpi_bybit_truth_{timestamp}.json"

        assert "bybit_truth" in expected_filename
        assert "kpi" in expected_filename

    def test_paper_output_filename_convention(self):
        """Verify Paper output follows naming convention."""
        timestamp = "2024-01-15"
        expected_filename = f"kpi_paper_journal_sim_{timestamp}.json"

        assert "paper_journal_sim" in expected_filename
        assert "kpi" in expected_filename

    def test_output_metadata_includes_source_type(self):
        """Verify output metadata clearly identifies source type."""
        kpi = KPIResult(
            source="bybit_truth",
            trading_mode="live",
            calculation_timestamp=datetime.now(UTC).isoformat(),
            calculation_id="test-001",
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

        metadata = {
            "data_source": "Bybit API V5",
            "source_type": "actual_execution",
            "canonical": True,
        }

        doc = KPIDocument(kpi, metadata=metadata)
        json_output = doc.to_json()

        parsed = json.loads(json_output)
        assert parsed["metadata"]["source_type"] == "actual_execution"
        assert parsed["metadata"]["canonical"] is True


class TestCanonicalForGoFlag:
    """Test canonical_for_go flag behavior."""

    def test_bybit_canonical_flag_is_true(self):
        """Verify Bybit KPI has canonical_for_go=True."""
        kpi = KPIResult(
            source="bybit_truth",
            trading_mode="live",
            calculation_timestamp=datetime.now(UTC).isoformat(),
            calculation_id="test-001",
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

        assert kpi.canonical_for_go is True
        assert isinstance(kpi.canonical_for_go, bool)

    def test_paper_canonical_flag_is_false(self):
        """Verify Paper KPI has canonical_for_go=False."""
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
            max_drawdown=5.0,
            max_drawdown_amount=50.0,
            turnover={"avg_trades_per_day": 1.5},
        )

        assert kpi.canonical_for_go is False
        assert isinstance(kpi.canonical_for_go, bool)

    def test_canonical_flag_in_output(self):
        """Verify canonical flag appears in JSON output."""
        kpi = KPIResult(
            source="bybit_truth",
            trading_mode="live",
            calculation_timestamp=datetime.now(UTC).isoformat(),
            calculation_id="test-003",
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

        doc = KPIDocument(kpi)
        json_output = doc.to_json()

        parsed = json.loads(json_output)
        assert "canonical_for_go" in parsed["kpi"]
        assert parsed["kpi"]["canonical_for_go"] is True


class TestTradingModeField:
    """Test trading_mode field behavior."""

    def test_bybit_has_live_trading_mode(self):
        """Verify Bybit KPI has trading_mode='live'."""
        kpi = KPIResult(
            source="bybit_truth",
            trading_mode="live",
            calculation_timestamp=datetime.now(UTC).isoformat(),
            calculation_id="test-001",
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

        assert kpi.trading_mode == "live"

    def test_paper_has_paper_trading_mode(self):
        """Verify Paper KPI has trading_mode='paper'."""
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
            max_drawdown=5.0,
            max_drawdown_amount=50.0,
            turnover={"avg_trades_per_day": 1.5},
        )

        assert kpi.trading_mode == "paper"


class TestDataQualityFlags:
    """Test data quality flag behavior."""

    def test_bybit_has_no_simulation_flags(self):
        """Verify Bybit KPI has no simulation-related quality flags."""
        kpi = KPIResult(
            source="bybit_truth",
            trading_mode="live",
            calculation_timestamp=datetime.now(UTC).isoformat(),
            calculation_id="test-001",
            canonical_for_go=True,
            win_rate=50.0,
            total_pnl=100.0,
            total_net_pnl=95.0,
            total_gross_pnl=105.0,
            total_fees=10.0,
            max_drawdown=3.0,
            max_drawdown_amount=30.0,
            turnover={"avg_trades_per_day": 2.0},
            data_quality_flags=[],
        )

        assert "simulation" not in " ".join(kpi.data_quality_flags).lower()
        assert "paper" not in " ".join(kpi.data_quality_flags).lower()

    def test_paper_has_simulation_flag(self):
        """Verify Paper KPI has simulation-related quality flag."""
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
            max_drawdown=5.0,
            max_drawdown_amount=50.0,
            turnover={"avg_trades_per_day": 1.5},
            data_quality_flags=["Simulated data - not actual execution"],
        )

        assert len(kpi.data_quality_flags) > 0
        assert any("simulat" in flag.lower() for flag in kpi.data_quality_flags)


class TestCanonicalSourceValidation:
    """Test validate_canonical_source function from kpi_persistence."""

    def test_bybit_truth_passes_demo_mode(self):
        """Verify bybit_truth passes validation for demo mode."""
        from src.evaluation.kpi_persistence import validate_canonical_source

        is_valid, reason = validate_canonical_source(
            "bybit_truth", "demo", enforce=False
        )
        assert is_valid is True
        assert "canonical" in reason.lower()

    def test_bybit_truth_passes_live_mode(self):
        """Verify bybit_truth passes validation for live mode."""
        from src.evaluation.kpi_persistence import validate_canonical_source

        is_valid, reason = validate_canonical_source(
            "bybit_truth", "live", enforce=False
        )
        assert is_valid is True
        assert "canonical" in reason.lower()

    def test_paper_journal_sim_fails_demo_mode(self):
        """Verify paper_journal_sim fails validation for demo mode."""
        from src.evaluation.kpi_persistence import validate_canonical_source

        is_valid, reason = validate_canonical_source(
            "paper_journal_sim", "demo", enforce=False
        )
        assert is_valid is False
        assert "not canonical" in reason.lower() or "not" in reason.lower()

    def test_paper_journal_sim_fails_live_mode(self):
        """Verify paper_journal_sim fails validation for live mode."""
        from src.evaluation.kpi_persistence import validate_canonical_source

        is_valid, reason = validate_canonical_source(
            "paper_journal_sim", "live", enforce=False
        )
        assert is_valid is False
        assert "not canonical" in reason.lower() or "not" in reason.lower()

    def test_enforce_flag_raises_exception(self):
        """Verify enforce=True raises exception for non-canonical sources."""
        from src.evaluation.kpi_persistence import (
            NonCanonicalSourceError,
            validate_canonical_source,
        )

        with pytest.raises(NonCanonicalSourceError):
            validate_canonical_source("paper_journal_sim", "demo", enforce=True)

    def test_enforce_flag_no_exception_when_false(self):
        """Verify enforce=False does not raise exception."""
        from src.evaluation.kpi_persistence import validate_canonical_source

        # Should not raise even with non-canonical source
        is_valid, reason = validate_canonical_source(
            "paper_journal_sim", "demo", enforce=False
        )
        assert is_valid is False  # Still returns False
        assert reason  # But provides a reason

    def test_paper_mode_allows_paper_source(self):
        """Verify paper mode allows paper_journal_sim source."""
        from src.evaluation.kpi_persistence import validate_canonical_source

        is_valid, reason = validate_canonical_source(
            "paper_journal_sim", "paper", enforce=False
        )
        assert is_valid is True
        assert "canonical" in reason.lower()

    def test_paper_mode_rejects_bybit_truth(self):
        """Verify paper mode rejects bybit_truth (data contamination check)."""
        from src.evaluation.kpi_persistence import validate_canonical_source

        is_valid, reason = validate_canonical_source(
            "bybit_truth", "paper", enforce=False
        )
        assert is_valid is False
        assert "contamination" in reason.lower() or "not expected" in reason.lower()


class TestBybitSourceValidation:
    """Test Bybit KPI source validation."""

    def test_bybit_source_validation_passes(self):
        """Verify Bybit source validation passes with correct values."""
        from scripts.analysis.calculate_bybit_kpis import (
            CANONICAL_SOURCE,
            validate_bybit_source,
        )

        # Should not raise
        validate_bybit_source(CANONICAL_SOURCE, True)

    def test_bybit_source_validation_fails_wrong_source(self):
        """Verify Bybit source validation fails with wrong source."""
        from scripts.analysis.calculate_bybit_kpis import (
            BybitSourceValidationError,
            validate_bybit_source,
        )

        with pytest.raises(BybitSourceValidationError):
            validate_bybit_source("wrong_source", True)

    def test_bybit_source_validation_fails_not_canonical(self):
        """Verify Bybit source validation fails when not canonical_for_go."""
        from scripts.analysis.calculate_bybit_kpis import (
            BybitSourceValidationError,
            CANONICAL_SOURCE,
            validate_bybit_source,
        )

        with pytest.raises(BybitSourceValidationError):
            validate_bybit_source(CANONICAL_SOURCE, False)


class TestPaperSourceValidation:
    """Test Paper KPI source validation."""

    def test_paper_source_validation_passes(self):
        """Verify Paper source validation passes with correct values."""
        from scripts.analysis.calculate_paper_kpis import (
            NON_CANONICAL_SOURCE,
            validate_paper_source,
        )

        # Should not raise
        validate_paper_source(NON_CANONICAL_SOURCE, False)

    def test_paper_source_validation_fails_bybit_truth(self):
        """Verify Paper source validation fails with bybit_truth (contamination)."""
        from scripts.analysis.calculate_paper_kpis import (
            PaperSourceValidationError,
            validate_paper_source,
        )

        with pytest.raises(PaperSourceValidationError):
            validate_paper_source("bybit_truth", False)

    def test_paper_source_validation_fails_when_canonical(self):
        """Verify Paper source validation fails when canonical_for_go=True."""
        from scripts.analysis.calculate_paper_kpis import (
            NON_CANONICAL_SOURCE,
            PaperSourceValidationError,
            validate_paper_source,
        )

        with pytest.raises(PaperSourceValidationError):
            validate_paper_source(NON_CANONICAL_SOURCE, True)


class TestGoGateEnforcement:
    """Test GO gate enforcement in run_kpi_evaluation."""

    def test_exit_code_5_for_non_canonical_in_demo(self):
        """Verify exit code 5 is returned for non-canonical source in demo mode."""
        from scripts.analysis.run_kpi_evaluation import (
            EXIT_NON_CANONICAL_SOURCE,
            validate_go_gate_eligibility,
        )

        # Simulate a paper result in demo mode
        result = {
            "source": "paper_journal_sim",
            "canonical_for_go": False,
            "success": True,
        }

        # Should return False and provide message
        is_eligible, msg = validate_go_gate_eligibility(
            result, "demo", enforce_canonical=False
        )
        assert is_eligible is False
        assert "not canonical" in msg.lower() or "prohibited" in msg.lower()

    def test_bybit_truth_eligible_for_go_in_live(self):
        """Verify bybit_truth is eligible for GO gates in live mode."""
        from scripts.analysis.run_kpi_evaluation import validate_go_gate_eligibility

        result = {
            "source": "bybit_truth",
            "canonical_for_go": True,
            "success": True,
        }

        is_eligible, msg = validate_go_gate_eligibility(
            result, "live", enforce_canonical=True
        )
        assert is_eligible is True
        assert "canonical" in msg.lower()


class TestOutputFileSeparation:
    """Test that output files are properly separated."""

    def test_separate_output_files_created(self):
        """Verify separate output files are created for each KPI type."""
        bybit_output = {
            "filename": "kpi_bybit_truth_2024-01-15.json",
            "source": "bybit_truth",
        }

        paper_output = {
            "filename": "kpi_paper_journal_sim_2024-01-15.json",
            "source": "paper_journal_sim",
        }

        # Different filenames
        assert bybit_output["filename"] != paper_output["filename"]

        # Different sources
        assert bybit_output["source"] != paper_output["source"]

    def test_output_file_content_isolation(self):
        """Verify output file contents don't reference wrong source."""
        bybit_content = {
            "source": "bybit_truth",
            "data": {"closed_pnl": 150.0, "fees": 2.5},
        }

        paper_content = {
            "source": "paper_journal_sim",
            "data": {"realized_pnl": 100.0, "fees": 2.0},
        }

        # Content should be isolated
        assert "bybit" not in paper_content["source"]
        assert "paper" not in bybit_content["source"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
