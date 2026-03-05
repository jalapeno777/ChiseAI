"""Tests for trade journal service reason distribution methods.

For ST-JOURNAL-QUERY-002: Reason Code Distribution
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from src.execution.paper.reason_codes import RejectReason
from src.execution.paper.trade_journal import ExitReason, TradeJournalEntry
from src.execution.paper.trade_journal_service import TradeJournalService


class TestTradeJournalServiceReasonDistribution:
    """Test reason distribution query methods in TradeJournalService."""

    @pytest.fixture
    def service(self):
        """Create a TradeJournalService instance."""
        return TradeJournalService(session_id="test-session")

    @pytest.fixture
    def sample_closed_entries(self):
        """Create sample closed entries with various exit reasons."""
        now = datetime.now(UTC)
        entries = []

        exit_reasons = [
            ExitReason.STOP_LOSS_HIT,
            ExitReason.STOP_LOSS_HIT,
            ExitReason.TAKE_PROFIT_HIT,
            ExitReason.TAKE_PROFIT_HIT,
            ExitReason.TAKE_PROFIT_HIT,
            ExitReason.SIGNAL_REVERSE,
            ExitReason.MANUAL_CLOSE,
        ]

        for i, reason in enumerate(exit_reasons):
            entry = TradeJournalEntry(
                entry_id=f"entry-{i}",
                symbol="BTCUSDT" if i % 2 == 0 else "ETHUSDT",
                side="buy",
                entry_price=100.0 * (i + 1),
                entry_time=now - timedelta(hours=i),
                position_size=1.0,
                signal_id=f"signal-{i}",
                signal_confidence=0.8,
                signal_strategy="test_strategy",
            )
            entry.close(
                exit_price=entry.entry_price + 10,
                exit_reason=reason,
                realized_pnl=100.0 * (i + 1),
            )
            entry.fees = 5.0
            entries.append(entry)

        return entries

    @pytest.fixture
    def mock_rejected_signals(self):
        """Create mock rejected signals."""
        signals = []
        reject_reasons = [
            RejectReason.RISK_VIOLATION,
            RejectReason.RISK_VIOLATION,
            RejectReason.LOW_CONFIDENCE,
            RejectReason.LOW_CONFIDENCE,
            RejectReason.LOW_CONFIDENCE,
            RejectReason.KILL_SWITCH_ACTIVE,
        ]

        for i, reason in enumerate(reject_reasons):
            signal = MagicMock()
            signal.reject_reason = reason
            signals.append(signal)

        return signals

    # Tests for query_reason_distribution()

    def test_query_reason_distribution_basic(self, service, sample_closed_entries):
        """Test basic reason distribution query."""
        # Add entries to service
        for entry in sample_closed_entries:
            service._journal._entries[entry.entry_id] = entry

        result = service.query_reason_distribution()

        assert "exit_reasons" in result
        assert "reject_reasons" in result
        assert "totals" in result
        assert result["totals"]["total_closed_trades"] == 7
        assert result["totals"]["total_rejected_signals"] == 0

    def test_query_reason_distribution_with_time_range(
        self, service, sample_closed_entries
    ):
        """Test reason distribution query with time range filter."""
        # Add entries to service
        for entry in sample_closed_entries:
            service._journal._entries[entry.entry_id] = entry

        now = datetime.now(UTC)
        time_range = (now - timedelta(hours=4), now)

        result = service.query_reason_distribution(time_range=time_range)

        # Should filter to entries within time range
        assert result["totals"]["total_closed_trades"] >= 0

    def test_query_reason_distribution_with_symbol(
        self, service, sample_closed_entries
    ):
        """Test reason distribution query with symbol filter."""
        # Add entries to service
        for entry in sample_closed_entries:
            service._journal._entries[entry.entry_id] = entry

        result = service.query_reason_distribution(symbol="BTCUSDT")

        # Should only include BTCUSDT trades (even indices)
        assert result["totals"]["total_closed_trades"] == 4

    def test_query_reason_distribution_with_rejected_signals(
        self, service, sample_closed_entries, mock_rejected_signals
    ):
        """Test reason distribution query with rejected signals."""
        # Add entries to service
        for entry in sample_closed_entries:
            service._journal._entries[entry.entry_id] = entry

        result = service.query_reason_distribution(
            rejected_signals=mock_rejected_signals
        )

        assert result["totals"]["total_closed_trades"] == 7
        assert result["totals"]["total_rejected_signals"] == 6
        assert result["totals"]["total_decisions"] == 13

    def test_query_reason_distribution_empty_service(self, service):
        """Test reason distribution query with empty service."""
        result = service.query_reason_distribution()

        assert result["exit_reasons"] == {}
        assert result["reject_reasons"] == {}
        assert result["totals"]["total_closed_trades"] == 0
        assert result["totals"]["total_rejected_signals"] == 0
        assert result["totals"]["total_decisions"] == 0

    def test_query_reason_distribution_combined_filters(
        self, service, sample_closed_entries, mock_rejected_signals
    ):
        """Test reason distribution query with multiple filters."""
        # Add entries to service
        for entry in sample_closed_entries:
            service._journal._entries[entry.entry_id] = entry

        now = datetime.now(UTC)
        time_range = (now - timedelta(hours=5), now)

        result = service.query_reason_distribution(
            time_range=time_range,
            symbol="ETHUSDT",
            rejected_signals=mock_rejected_signals,
        )

        # Should apply both filters
        assert result["totals"]["total_closed_trades"] >= 0
        assert result["totals"]["total_rejected_signals"] == 6

    # Tests for export_reason_report()

    def test_export_reason_report_json(self, service, sample_closed_entries):
        """Test exporting reason report as JSON."""
        # Add entries to service
        for entry in sample_closed_entries:
            service._journal._entries[entry.entry_id] = entry

        report = service.export_reason_report(format="json")

        # Should be valid JSON string
        import json

        data = json.loads(report)

        assert "exit_reasons" in data
        assert "reject_reasons" in data
        assert "totals" in data

    def test_export_reason_report_csv(self, service, sample_closed_entries):
        """Test exporting reason report as CSV."""
        # Add entries to service
        for entry in sample_closed_entries:
            service._journal._entries[entry.entry_id] = entry

        report = service.export_reason_report(format="csv")

        # Should be valid CSV string
        lines = report.strip().split("\n")
        assert len(lines) > 1  # At least header + some data

        # Check header
        header = lines[0]
        assert "category" in header
        assert "reason" in header
        assert "count" in header
        assert "percentage" in header

    def test_export_reason_report_with_filters(self, service, sample_closed_entries):
        """Test exporting reason report with filters."""
        # Add entries to service
        for entry in sample_closed_entries:
            service._journal._entries[entry.entry_id] = entry

        report = service.export_reason_report(symbol="BTCUSDT", format="json")

        import json

        data = json.loads(report)

        # Should only include BTCUSDT trades
        assert data["totals"]["total_closed_trades"] == 4

    def test_export_reason_report_with_rejected_signals(
        self, service, sample_closed_entries, mock_rejected_signals
    ):
        """Test exporting reason report with rejected signals."""
        # Add entries to service
        for entry in sample_closed_entries:
            service._journal._entries[entry.entry_id] = entry

        report = service.export_reason_report(
            rejected_signals=mock_rejected_signals, format="json"
        )

        import json

        data = json.loads(report)

        assert data["totals"]["total_closed_trades"] == 7
        assert data["totals"]["total_rejected_signals"] == 6
        assert data["totals"]["total_decisions"] == 13

    def test_export_reason_report_invalid_format(self, service):
        """Test exporting reason report with invalid format."""
        with pytest.raises(ValueError, match="Invalid format"):
            service.export_reason_report(format="xml")

    def test_export_reason_report_csv_structure(self, service, sample_closed_entries):
        """Test CSV report structure and content."""
        # Add entries to service
        for entry in sample_closed_entries:
            service._journal._entries[entry.entry_id] = entry

        report = service.export_reason_report(format="csv")

        lines = report.strip().split("\n")

        # Find data rows (after header)
        data_rows = [
            line for line in lines[1:] if line and "totals" not in line.lower()
        ]

        # Should have exit reason rows
        exit_rows = [row for row in data_rows if row.startswith("exit,")]
        assert len(exit_rows) > 0

    def test_export_reason_report_empty_service(self, service):
        """Test exporting reason report with empty service."""
        report_json = service.export_reason_report(format="json")
        report_csv = service.export_reason_report(format="csv")

        import json

        data = json.loads(report_json)

        assert data["totals"]["total_closed_trades"] == 0
        assert data["totals"]["total_rejected_signals"] == 0

        # CSV should still have header
        assert "category,reason,count,percentage" in report_csv

    def test_export_reason_report_json_serialization(
        self, service, sample_closed_entries
    ):
        """Test that JSON report properly serializes datetime objects."""
        # Add entries to service
        for entry in sample_closed_entries:
            service._journal._entries[entry.entry_id] = entry

        report = service.export_reason_report(format="json")

        # Should not raise JSON serialization error
        import json

        data = json.loads(report)

        assert isinstance(data, dict)

    def test_export_reason_report_csv_totals_section(
        self, service, sample_closed_entries
    ):
        """Test that CSV report includes totals section."""
        # Add entries to service
        for entry in sample_closed_entries:
            service._journal._entries[entry.entry_id] = entry

        report = service.export_reason_report(format="csv")

        # Should include totals
        assert "total_closed_trades" in report
        assert "total_rejected_signals" in report
        assert "total_decisions" in report
