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

    # -------------------------------------------------------------------------
    # Unit tests for check_orphaned_fills
    # -------------------------------------------------------------------------

    def test_check_orphaned_fills_none_orphaned(self):
        """check_orphaned_fills returns empty list when no orphaned fills."""
        mock_r = MagicMock()
        mock_r.keys.side_effect = lambda pattern: {
            "paper:order:*": [
                "paper:order:20260408120000:BTCUSDT:order-001",
                "paper:order:20260408120001:ETHUSDT:order-002",
            ],
            "paper:fill:*": [
                "paper:fill:20260408120000:BTCUSDT:order-001",
                "paper:fill:20260408120001:ETHUSDT:order-002",
            ],
        }.get(pattern, [])

        result = check_orphaned_fills(mock_r)
        assert result == []

    def test_check_orphaned_fills_with_orphaned(self):
        """check_orphaned_fills detects fills without matching orders."""
        mock_r = MagicMock()
        mock_r.keys.side_effect = lambda pattern: {
            "paper:order:*": [
                "paper:order:20260408120000:BTCUSDT:order-001",
            ],
            "paper:fill:*": [
                "paper:fill:20260408120000:BTCUSDT:order-001",
                "paper:fill:20260408120002:ETHUSDT:order-orphaned",
            ],
        }.get(pattern, [])

        result = check_orphaned_fills(mock_r)
        assert len(result) == 1
        assert "order-orphaned" in result[0]

    # -------------------------------------------------------------------------
    # Unit tests for ReconcileResult dataclass
    # -------------------------------------------------------------------------

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
            redis_counts={"orders": 10, "fills": 12, "outcomes": 8},
            postgres_count=8,
            since="2026-04-08T00:00:00Z",
            orphaned_fills=["paper:fill:20260408120002:ETHUSDT:order-003"],
            divergence={
                "orphaned_fills": {"count": 1, "severity": "CRITICAL"},
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
    # Integration tests for reconcile (mocked dependencies)
    # -------------------------------------------------------------------------

    def test_reconcile_returns_clean_result(self):
        """reconcile returns clean result when Redis and Postgres match."""
        mock_r = MagicMock()
        mock_r.zcard.return_value = 10
        mock_r.keys.return_value = []

        with (
            patch("scripts.paper_reconcile.get_redis_client", return_value=mock_r),
            patch("scripts.paper_reconcile.get_postgres_count") as mock_pg_count,
            patch("scripts.paper_reconcile.asyncio.run") as mock_asyncio_run,
        ):
            mock_asyncio_run.return_value = 10  # Postgres count matches Redis

            result = reconcile("2026-04-08T00:00:00Z")

        assert result.status == "clean"
        assert result.exit_code == 0

    def test_reconcile_returns_divergence_on_count_mismatch(self):
        """reconcile detects divergence when Redis and Postgres counts differ."""
        mock_r = MagicMock()
        mock_r.zcard.return_value = 10
        mock_r.keys.return_value = []

        with (
            patch("scripts.paper_reconcile.get_redis_client", return_value=mock_r),
            patch("scripts.paper_reconcile.get_postgres_count") as mock_pg_count,
            patch("scripts.paper_reconcile.asyncio.run") as mock_asyncio_run,
        ):
            mock_asyncio_run.return_value = 8  # Postgres count differs

            result = reconcile("2026-04-08T00:00:00Z")

        assert result.status == "divergence"
        assert result.exit_code == 1
        assert "postgres_mismatch" in result.divergence

    def test_reconcile_returns_divergence_on_orphaned_fills(self):
        """reconcile detects orphaned fills as critical divergence."""
        mock_r = MagicMock()
        mock_r.zcard.return_value = 10
        mock_r.keys.side_effect = lambda pattern: {
            "paper:order:*": ["paper:order:20260408120000:BTCUSDT:order-001"],
            "paper:fill:*": [
                "paper:fill:20260408120000:BTCUSDT:order-001",
                "paper:fill:20260408120002:ETHUSDT:order-orphaned",
            ],
        }.get(pattern, [])

        with (
            patch("scripts.paper_reconcile.get_redis_client", return_value=mock_r),
            patch("scripts.paper_reconcile.get_postgres_count") as mock_pg_count,
            patch("scripts.paper_reconcile.asyncio.run") as mock_asyncio_run,
        ):
            mock_asyncio_run.return_value = 10

            result = reconcile("2026-04-08T00:00:00Z")

        assert result.status == "divergence"
        assert result.exit_code == 1
        assert "orphaned_fills" in result.divergence
        assert result.divergence["orphaned_fills"]["severity"] == "CRITICAL"
