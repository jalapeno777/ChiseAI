#!/usr/bin/env python3
"""Tests for paper_backfill.py script."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from scripts.paper_backfill import (
    construct_outcome_from_order_fill,
    extract_order_id_from_key,
    parse_timestamp,
    run_backfill,
)


class TestPaperBackfillScript:
    """Tests for the paper_backfill.py script."""

    def test_script_exists(self):
        """Backfill script module exists and can be imported."""
        import scripts.paper_backfill

        assert hasattr(scripts.paper_backfill, "run_backfill")
        assert hasattr(scripts.paper_backfill, "parse_timestamp")
        assert hasattr(scripts.paper_backfill, "extract_order_id_from_key")

    # -------------------------------------------------------------------------
    # Unit tests for pure functions
    # -------------------------------------------------------------------------

    def test_parse_timestamp_valid_iso(self):
        """parse_timestamp handles valid ISO timestamps."""
        result = parse_timestamp("2026-04-08T12:00:00Z")
        assert result is not None
        assert result.year == 2026
        assert result.month == 4
        assert result.day == 8
        assert result.tzinfo is not None

    def test_parse_timestamp_with_timezone(self):
        """parse_timestamp handles ISO timestamps with timezone."""
        result = parse_timestamp("2026-04-08T12:00:00+00:00")
        assert result is not None
        assert result.year == 2026

    def test_parse_timestamp_none(self):
        """parse_timestamp returns None for None input."""
        assert parse_timestamp(None) is None

    def test_parse_timestamp_invalid(self):
        """parse_timestamp returns None for invalid input."""
        assert parse_timestamp("not-a-timestamp") is None
        assert parse_timestamp("") is None

    def test_extract_order_id_from_key_valid(self):
        """extract_order_id_from_key extracts order ID from valid key patterns."""
        key = "paper:order:20260408120000:BTCUSDT:abc123"
        assert extract_order_id_from_key(key) == "abc123"

    def test_extract_order_id_from_key_short(self):
        """extract_order_id_from_key returns None for short keys."""
        assert extract_order_id_from_key("paper:order:abc") is None
        assert extract_order_id_from_key("paper:order") is None

    def test_extract_order_id_from_key_empty(self):
        """extract_order_id_from_key returns None for empty key."""
        assert extract_order_id_from_key("") is None

    def test_construct_outcome_from_order_fill_with_fill(self):
        """construct_outcome_from_order_fill builds outcome with fill data."""
        order_data = {
            "order_id": "order-456",
            "symbol": "BTCUSDT",
            "signal_id": "sig-001",
            "state": "filled",
        }
        fill_data = {
            "avg_fill_price": "50000.00",
            "filled_quantity": "0.5",
            "filled_at": "2026-04-08T12:00:00Z",
            "pnl": "100.00",
            "fee": "10.00",
        }
        outcome = construct_outcome_from_order_fill(order_data, fill_data)

        assert outcome["order_id"] == "order-456"
        assert outcome["symbol"] == "BTCUSDT"
        assert outcome["signal_id"] == "sig-001"
        assert outcome["fill_price"] == "50000.00"
        assert outcome["fill_quantity"] == "0.5"
        assert outcome["fill_timestamp"] == "2026-04-08T12:00:00Z"
        assert outcome["pnl"] == "100.00"
        assert outcome["fee"] == "10.00"
        assert outcome["outcome_type"] == "fill"
        assert outcome["execution_source"] == "canary_backfill"

    def test_construct_outcome_from_order_fill_without_fill(self):
        """construct_outcome_from_order_fill builds outcome from order only."""
        order_data = {
            "order_id": "order-789",
            "symbol": "ETHUSDT",
            "price": "3000.00",
            "quantity": "1.0",
            "state": "filled",
        }
        outcome = construct_outcome_from_order_fill(order_data, None)

        assert outcome["order_id"] == "order-789"
        assert outcome["symbol"] == "ETHUSDT"
        assert outcome["fill_price"] == "3000.00"
        assert outcome["fill_quantity"] == "1.0"
        assert outcome["outcome_type"] == "order"

    # -------------------------------------------------------------------------
    # Integration tests for run_backfill (mocked dependencies)
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_run_backfill_dry_run(self):
        """run_backfill with dry_run=True returns expected structure."""
        mock_since = datetime(2026, 4, 8, 0, 0, 0, tzinfo=UTC)

        # Mock Redis client and its methods
        mock_r = MagicMock()
        mock_r.scan_iter.return_value = [
            "paper:order:20260408120000:BTCUSDT:order-001",
        ]
        mock_r.get.return_value = (
            '{"order_id": "order-001", "symbol": "BTCUSDT", "state": "filled"}'
        )
        mock_r.keys.return_value = []

        with patch("scripts.paper_backfill.get_redis_client", return_value=mock_r):
            result = await run_backfill(mock_since, dry_run=True)

        assert "outcomes_upserted" in result
        assert "orphaned_fills" in result
        assert result["dry_run"] is True
        assert isinstance(result["outcomes_upserted"], int)

    @pytest.mark.asyncio
    async def test_run_backfill_empty_window(self):
        """run_backfill returns zeros when no orders in window."""
        mock_since = datetime(2026, 4, 8, 0, 0, 0, tzinfo=UTC)

        mock_r = MagicMock()
        mock_r.scan_iter.return_value = []

        with patch("scripts.paper_backfill.get_redis_client", return_value=mock_r):
            result = await run_backfill(mock_since, dry_run=True)

        assert result["outcomes_upserted"] == 0
        assert result["orphaned_fills"] == 0
