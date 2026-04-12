#!/usr/bin/env python3
"""Tests for paper_reconcile.py script."""

from unittest.mock import MagicMock, patch

from scripts.paper_reconcile import (
    ReconcileResult,
    check_orphaned_fills,
    reconcile,
)


class TestPaperReconcileScript:
    """Tests for the paper_reconcile.py script."""

    def test_script_exists(self):
        """Reconcile script module exists and can be imported."""
        import scripts.paper_reconcile

        assert hasattr(scripts.paper_reconcile, "reconcile")
        assert hasattr(scripts.paper_reconcile, "check_orphaned_fills")
        assert hasattr(scripts.paper_reconcile, "ReconcileResult")
        assert hasattr(
            scripts.paper_reconcile, "get_postgres_counts"
        )  # HIGH-2: combined function

    # -------------------------------------------------------------------------
    # Unit tests for check_orphaned_fills
    # -------------------------------------------------------------------------

    def test_check_orphaned_fills_none_orphaned(self):
        """check_orphaned_fills returns empty list when no orphaned fills."""
        mock_r = MagicMock()
        # check_orphaned_fills uses scan_iter, not keys
        mock_r.scan_iter.side_effect = lambda match, count: {
            "paper:order:*": [
                "paper:order:20260408120000:BTCUSDT:order-001",
                "paper:order:20260408120001:ETHUSDT:order-002",
            ],
            "paper:fill:*": [
                "paper:fill:20260408120000:BTCUSDT:order-001",
                "paper:fill:20260408120001:ETHUSDT:order-002",
            ],
        }.get(match, [])

        result = check_orphaned_fills(mock_r)
        assert result == []

    def test_check_orphaned_fills_with_orphaned(self):
        """check_orphaned_fills detects fills without matching orders."""
        mock_r = MagicMock()
        # check_orphaned_fills uses scan_iter, not keys
        mock_r.scan_iter.side_effect = lambda match, count: (
            [
                "paper:order:20260408120000:BTCUSDT:order-001",
            ]
            if "paper:order:*" in match
            else [
                "paper:fill:20260408120000:BTCUSDT:order-001",
                "paper:fill:20260408120002:ETHUSDT:order-orphaned",
            ]
        )

        result = check_orphaned_fills(mock_r)
        assert len(result) == 1
        assert "order-orphaned" in result[0]

    # -------------------------------------------------------------------------
    # Unit tests for ReconcileResult dataclass
    # -------------------------------------------------------------------------

    def test_reconcile_result_has_orphaned_fields(self):
        """ReconcileResult has new orphaned fill tracking fields."""
        result = ReconcileResult(
            redis_counts={"orders": 10, "fills": 12, "outcomes": 10},
            postgres_count=10,
            since="2026-04-08T00:00:00Z",
            orphaned_fills=[],
            divergence={},
            status="clean",
            exit_code=0,
            pg_orphaned_fills=5,
            pg_missing_signal_fills=0,
        )
        assert result.pg_orphaned_fills == 5
        assert result.pg_missing_signal_fills == 0

    def test_reconcile_result_clean(self):
        """ReconcileResult correctly represents clean state."""
        result = ReconcileResult(
            redis_counts={"orders": 10, "fills": 12, "outcomes": 10},
            postgres_count=10,
            since="2026-04-08T00:00:00Z",
            orphaned_fills=[],
            divergence={},
            status="clean",
            exit_code=0,
        )
        assert result.status == "clean"
        assert result.exit_code == 0
        assert result.divergence == {}

    def test_reconcile_result_divergence(self):
        """ReconcileResult correctly represents divergence state."""
        result = ReconcileResult(
            redis_counts={"orders": 10, "fills": 12, "outcomes": 10},
            postgres_count=10,
            since="2026-04-08T00:00:00Z",
            orphaned_fills=["paper:fill:20260408120002:ETHUSDT:order-003"],
            divergence={
                "orphaned_fills": {"count": 1, "severity": "WARNING"},
                "postgres_mismatch": {
                    "redis_outcomes": 10,
                    "postgres_outcomes": 8,
                    "gap": 2,
                },
            },
            status="divergence",
            exit_code=1,
        )
        assert result.status == "divergence"
        assert result.exit_code == 1
        assert len(result.orphaned_fills) == 1

    # -------------------------------------------------------------------------
    # PAPER-RECON-ORPHANED-POLICY tests
    # -------------------------------------------------------------------------

    def test_orphaned_fills_signal_id_null_non_blocking(self):
        """Orphaned fills (signal_id IS NULL) do NOT cause blocking divergence.

        Per PAPER-RECON-ORPHANED-POLICY: Orphaned fills are expected in paper mode
        and should be reported but NOT cause exit_code = 1.
        """
        mock_r = MagicMock()
        mock_r.zcard.return_value = 10
        mock_r.keys.return_value = []

        with (
            patch("scripts.paper_reconcile.get_redis_client", return_value=mock_r),
            patch("scripts.paper_reconcile.asyncio.run") as mock_asyncio_run,
        ):
            # HIGH-2: Single call returns (outcome_count, orphaned, missing)
            mock_asyncio_run.side_effect = [(10, 3, 0)]

            result = reconcile("2026-04-08T00:00:00Z")

        # Orphaned fills are reported but NOT blocking
        assert result.pg_orphaned_fills == 3
        assert result.pg_missing_signal_fills == 0
        assert result.status == "clean"
        assert result.exit_code == 0
        assert "pg_orphaned_fills" in result.divergence
        assert result.divergence["pg_orphaned_fills"]["severity"] == "INFO"

    def test_missing_signal_fills_blocking(self):
        """Missing signal fills (signal_id without signal) DO cause blocking divergence.

        Per PAPER-RECON-ORPHANED-POLICY: Missing signal fills indicate a data anomaly
        and MUST cause exit_code = 1.
        """
        mock_r = MagicMock()
        mock_r.zcard.return_value = 10
        mock_r.keys.return_value = []

        with (
            patch("scripts.paper_reconcile.get_redis_client", return_value=mock_r),
            patch("scripts.paper_reconcile.asyncio.run") as mock_asyncio_run,
        ):
            # HIGH-2: Single call returns (outcome_count, orphaned, missing)
            mock_asyncio_run.side_effect = [(10, 0, 2)]

            result = reconcile("2026-04-08T00:00:00Z")

        # Missing signal fills ARE blocking
        assert result.pg_orphaned_fills == 0
        assert result.pg_missing_signal_fills == 2
        assert result.status == "divergence"
        assert result.exit_code == 1
        assert "missing_signal_fills" in result.divergence
        assert result.divergence["missing_signal_fills"]["severity"] == "CRITICAL"

    def test_both_orphaned_and_missing_signal_fills(self):
        """Both orphaned and missing fills can coexist; only missing is blocking."""
        mock_r = MagicMock()
        mock_r.zcard.return_value = 10
        mock_r.keys.return_value = []

        with (
            patch("scripts.paper_reconcile.get_redis_client", return_value=mock_r),
            patch("scripts.paper_reconcile.asyncio.run") as mock_asyncio_run,
        ):
            # HIGH-2: Single call returns (outcome_count, orphaned, missing)
            mock_asyncio_run.side_effect = [(10, 4, 1)]

            result = reconcile("2026-04-08T00:00:00Z")

        assert result.pg_orphaned_fills == 4
        assert result.pg_missing_signal_fills == 1
        assert result.status == "divergence"
        assert result.exit_code == 1
        # Both are reported
        assert "pg_orphaned_fills" in result.divergence
        assert "missing_signal_fills" in result.divergence

    def test_redis_orphaned_fills_not_critical(self):
        """Redis orphaned fills (fills without orders) are WARNING, not CRITICAL.

        Redis-level orphaned fills indicate Redis data integrity issues, but
        are not the same as Postgres-level missing signal fills (anomaly).
        """
        mock_r = MagicMock()
        mock_r.zcard.return_value = 10
        mock_r.scan_iter.side_effect = lambda match, count: {
            "paper:order:*": ["paper:order:20260408120000:BTCUSDT:order-001"],
            "paper:fill:*": [
                "paper:fill:20260408120000:BTCUSDT:order-001",
                "paper:fill:20260408120002:ETHUSDT:order-orphaned",
            ],
        }.get(match, [])

        with (
            patch("scripts.paper_reconcile.get_redis_client", return_value=mock_r),
            patch("scripts.paper_reconcile.asyncio.run") as mock_asyncio_run,
        ):
            # HIGH-2: Single call returns (outcome_count, orphaned, missing)
            mock_asyncio_run.side_effect = [(10, 0, 0)]

            result = reconcile("2026-04-08T00:00:00Z")

        # Redis orphaned fills are WARNING (not blocking by themselves)
        assert result.status == "clean"
        assert result.exit_code == 0
        assert (
            result.has_warning == True
        )  # CRITICAL-1: orphaned fills trigger has_warning
        assert len(result.orphaned_fills) == 1
        assert result.divergence["orphaned_fills"]["severity"] == "WARNING"

    # -------------------------------------------------------------------------
    # Integration tests for reconcile (mocked dependencies)
    # -------------------------------------------------------------------------

    def test_reconcile_returns_clean_result(self):
        """reconcile returns clean result when Redis and Postgres match."""
        mock_r = MagicMock()
        mock_r.zcard.return_value = 10
        mock_r.scan_iter.return_value = []

        with (
            patch("scripts.paper_reconcile.get_redis_client", return_value=mock_r),
            patch("scripts.paper_reconcile.asyncio.run") as mock_asyncio_run,
        ):
            # HIGH-2: Single call returns (outcome_count, orphaned, missing)
            mock_asyncio_run.side_effect = [(10, 0, 0)]

            result = reconcile("2026-04-08T00:00:00Z")

        assert result.status == "clean"
        assert result.exit_code == 0

    def test_reconcile_returns_divergence_on_count_mismatch(self):
        """reconcile detects divergence when Redis and Postgres counts differ."""
        mock_r = MagicMock()
        mock_r.zcard.return_value = 10
        mock_r.scan_iter.return_value = []

        with (
            patch("scripts.paper_reconcile.get_redis_client", return_value=mock_r),
            patch("scripts.paper_reconcile.asyncio.run") as mock_asyncio_run,
        ):
            # HIGH-2: Single call returns (outcome_count, orphaned, missing)
            mock_asyncio_run.side_effect = [(8, 0, 0)]  # pg_count=8 (mismatch)

            result = reconcile("2026-04-08T00:00:00Z")

        assert result.status == "divergence"
        assert result.exit_code == 1
        assert "postgres_mismatch" in result.divergence

    def test_reconcile_returns_divergence_on_orphaned_fills(self):
        """reconcile detects orphaned fills as non-blocking divergence.

        NOTE: This test verifies Redis-level orphaned fills (fills without orders).
        These are WARNING severity and don't block by themselves.
        Postgres-level orphaned fills (signal_id IS NULL) are INFO and don't block.
        """
        mock_r = MagicMock()
        mock_r.zcard.return_value = 10
        mock_r.scan_iter.side_effect = lambda match, count: {
            "paper:order:*": ["paper:order:20260408120000:BTCUSDT:order-001"],
            "paper:fill:*": [
                "paper:fill:20260408120000:BTCUSDT:order-001",
                "paper:fill:20260408120002:ETHUSDT:order-orphaned",
            ],
        }.get(match, [])

        with (
            patch("scripts.paper_reconcile.get_redis_client", return_value=mock_r),
            patch("scripts.paper_reconcile.asyncio.run") as mock_asyncio_run,
        ):
            # HIGH-2: Single call returns (outcome_count, orphaned, missing)
            mock_asyncio_run.side_effect = [(10, 0, 0)]

            result = reconcile("2026-04-08T00:00:00Z")

        # Redis orphaned fills are reported as WARNING, not blocking
        assert "orphaned_fills" in result.divergence
        assert result.divergence["orphaned_fills"]["severity"] == "WARNING"
        # Status is clean because no blocking divergence
        assert result.status == "clean"
        assert result.exit_code == 0
        assert (
            result.has_warning == True
        )  # CRITICAL-1: orphaned fills trigger has_warning
