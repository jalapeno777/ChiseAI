"""Tests for signal_generation/priority_resolver.py.

Tests cover:
- Single detection: only one signal in, that signal comes out
- Multiple different priority: highest priority wins
- Multiple same priority: tie-breaking returns one (by timestamp or confidence)
- Custom priority order: overrides default
- Empty list: returns None
- Missing optional fields: handles gracefully
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from signal_generation.priority_resolver import (
    DEFAULT_PRIORITY_ORDER,
    resolve_highest_priority_signal,
)


class TestResolveHighestPrioritySignal:
    """Test suite for resolve_highest_priority_signal."""

    # ========================================================================
    # Single detection tests
    # ========================================================================

    def test_single_detection_returns_that_signal(self):
        """Single signal in list returns that signal."""
        signals = [{"signal_type": "fvg", "confidence": 0.8}]
        result = resolve_highest_priority_signal(signals)
        assert result == {"signal_type": "fvg", "confidence": 0.8}

    def test_single_detection_with_minimal_signal(self):
        """Single signal with only required field returns that signal."""
        signals = [{"signal_type": "order_block"}]
        result = resolve_highest_priority_signal(signals)
        assert result == {"signal_type": "order_block"}

    # ========================================================================
    # Empty list tests
    # ========================================================================

    def test_empty_list_returns_none(self):
        """Empty list returns None."""
        result = resolve_highest_priority_signal([])
        assert result is None

    def test_none_list_returns_none(self):
        """None list returns None."""
        result = resolve_highest_priority_signal(None)
        assert result is None

    # ========================================================================
    # Multiple different priority tests
    # ========================================================================

    def test_order_block_wins_over_fvg(self):
        """Order Block (priority 2) wins over FVG (priority 3)."""
        signals = [
            {"signal_type": "fvg", "timestamp": 1000, "confidence": 0.9},
            {"signal_type": "order_block", "timestamp": 1000, "confidence": 0.7},
        ]
        result = resolve_highest_priority_signal(signals)
        assert result["signal_type"] == "order_block"

    def test_fvg_wins_over_liquidity_sweep(self):
        """FVG (priority 3) wins over Liquidity Sweep (priority 4)."""
        signals = [
            {"signal_type": "liquidity_sweep", "timestamp": 500, "confidence": 0.9},
            {"signal_type": "fvg", "timestamp": 1000, "confidence": 0.7},
        ]
        result = resolve_highest_priority_signal(signals)
        assert result["signal_type"] == "fvg"

    def test_bos_choch_wins_over_all(self):
        """BOS/CHoCH (priority 1) wins over all other signals."""
        signals = [
            {"signal_type": "fvg", "timestamp": 500, "confidence": 0.9},
            {"signal_type": "order_block", "timestamp": 500, "confidence": 0.7},
            {"signal_type": "bos_choch", "timestamp": 1000, "confidence": 0.5},
        ]
        result = resolve_highest_priority_signal(signals)
        assert result["signal_type"] == "bos_choch"

    def test_cvd_treated_as_liquidity_sweep(self):
        """CVD is treated as liquidity sweep (priority 4)."""
        signals = [
            {"signal_type": "cvd", "timestamp": 500, "confidence": 0.9},
            {"signal_type": "fvg", "timestamp": 500, "confidence": 0.7},
        ]
        result = resolve_highest_priority_signal(signals)
        assert result["signal_type"] == "fvg"

    def test_unknown_signal_type_gets_lowest_priority(self):
        """Unknown signal types get lowest priority (fallback to 99)."""
        signals = [
            {"signal_type": "unknown_type", "timestamp": 500, "confidence": 0.9},
            {"signal_type": "fvg", "timestamp": 500, "confidence": 0.7},
        ]
        result = resolve_highest_priority_signal(signals)
        assert result["signal_type"] == "fvg"

    # ========================================================================
    # Tie-breaking tests (same priority)
    # ========================================================================

    def test_same_priority_older_timestamp_wins(self):
        """When same priority, older timestamp wins."""
        signals = [
            {"signal_type": "fvg", "timestamp": 1000, "confidence": 0.7},
            {
                "signal_type": "fvg",
                "timestamp": 500,
                "confidence": 0.9,
            },  # older but lower confidence
        ]
        result = resolve_highest_priority_signal(signals)
        assert result["timestamp"] == 500

    def test_same_priority_higher_confidence_wins_when_timestamps_equal(self):
        """When same priority and timestamps equal, higher confidence wins."""
        signals = [
            {"signal_type": "fvg", "timestamp": 1000, "confidence": 0.7},
            {
                "signal_type": "fvg",
                "timestamp": 1000,
                "confidence": 0.9,
            },  # same time, higher confidence
        ]
        result = resolve_highest_priority_signal(signals)
        assert result["confidence"] == 0.9

    def test_same_priority_timestamp_takes_precedence_over_confidence(self):
        """Timestamp takes precedence over confidence for tie-breaking."""
        signals = [
            {
                "signal_type": "fvg",
                "timestamp": 2000,
                "confidence": 1.0,
            },  # newer, highest confidence
            {
                "signal_type": "fvg",
                "timestamp": 500,
                "confidence": 0.5,
            },  # older, lower confidence
        ]
        result = resolve_highest_priority_signal(signals)
        assert result["timestamp"] == 500

    # ========================================================================
    # Custom priority order tests
    # ========================================================================

    def test_custom_priority_order_overrides_default(self):
        """Custom priority order overrides default priority."""
        # Custom order: fvg > order_block (reversed from default)
        custom_order = ["fvg", "order_block", "bos_choch", "liquidity_sweep"]
        signals = [
            {"signal_type": "order_block", "timestamp": 1000, "confidence": 0.9},
            {"signal_type": "fvg", "timestamp": 1000, "confidence": 0.7},
        ]
        result = resolve_highest_priority_signal(signals, priority_order=custom_order)
        assert result["signal_type"] == "fvg"

    def test_custom_priority_with_three_signals(self):
        """Custom priority correctly orders three signals."""
        custom_order = ["liquidity_sweep", "fvg", "order_block"]
        signals = [
            {"signal_type": "order_block", "timestamp": 1000, "confidence": 0.9},
            {"signal_type": "fvg", "timestamp": 1000, "confidence": 0.7},
            {"signal_type": "liquidity_sweep", "timestamp": 1000, "confidence": 0.5},
        ]
        result = resolve_highest_priority_signal(signals, priority_order=custom_order)
        assert result["signal_type"] == "liquidity_sweep"

    def test_custom_priority_order_none_uses_default(self):
        """When priority_order is None, uses default order."""
        assert resolve_highest_priority_signal(None, priority_order=None) is None
        signals = [{"signal_type": "order_block"}]
        result = resolve_highest_priority_signal(signals, priority_order=None)
        assert result["signal_type"] == "order_block"

    # ========================================================================
    # Timestamp handling tests
    # ========================================================================

    def test_datetime_timestamp_handled(self):
        """Datetime objects in timestamp are handled correctly."""
        old_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        new_time = datetime(2024, 1, 1, 13, 0, 0, tzinfo=UTC)
        signals = [
            {"signal_type": "fvg", "timestamp": new_time, "confidence": 0.9},
            {"signal_type": "fvg", "timestamp": old_time, "confidence": 0.5},  # older
        ]
        result = resolve_highest_priority_signal(signals)
        assert result["timestamp"] == old_time

    def test_missing_timestamp_gets_lowest_priority_in_tie(self):
        """Missing timestamp treated as infinitely new (lowest priority in tie)."""
        signals = [
            {"signal_type": "fvg", "timestamp": 1000, "confidence": 0.5},
            {"signal_type": "fvg", "confidence": 0.9},  # no timestamp
        ]
        result = resolve_highest_priority_signal(signals)
        assert result.get("timestamp") == 1000

    def test_timestamp_in_milliseconds(self):
        """Timestamp in milliseconds (Unix ms) handled correctly."""
        signals = [
            {
                "signal_type": "fvg",
                "timestamp": 1704067200000,
                "confidence": 0.5,
            },  # 2024-01-01 00:00:00 UTC ms
            {
                "signal_type": "fvg",
                "timestamp": 1704063600000,
                "confidence": 0.9,
            },  # 2024-01-01 00:00:00 UTC ms - 1 hour earlier
        ]
        result = resolve_highest_priority_signal(signals)
        # Older timestamp (smaller value) should win
        assert result["timestamp"] == 1704063600000

    # ========================================================================
    # Confidence handling tests
    # ========================================================================

    def test_missing_confidence_gets_zero(self):
        """Missing confidence is treated as 0.0 for tie-breaking."""
        signals = [
            {"signal_type": "fvg", "timestamp": 1000},  # no confidence
            {"signal_type": "fvg", "timestamp": 1000, "confidence": 0.9},
        ]
        result = resolve_highest_priority_signal(signals)
        assert result["confidence"] == 0.9

    def test_confidence_percentage_format(self):
        """Confidence values > 1.0 are treated as percentages (e.g., 75 -> 0.75)."""
        signals = [
            {
                "signal_type": "fvg",
                "timestamp": 1000,
                "confidence": 75,
            },  # percentage format
            {
                "signal_type": "fvg",
                "timestamp": 1000,
                "confidence": 0.7,
            },  # decimal format
        ]
        result = resolve_highest_priority_signal(signals)
        # Both should normalize to same value, but 0.7 decimal comes first in stable sort
        assert result["confidence"] == 0.7

    # ========================================================================
    # Default priority order verification
    # ========================================================================

    def test_default_priority_order_is_correct(self):
        """Verify default priority order matches AC."""
        expected = ["bos_choch", "order_block", "fvg", "liquidity_sweep"]
        assert DEFAULT_PRIORITY_ORDER == expected

    def test_full_integration_multiple_signals(self):
        """Integration test with multiple signals of different priorities."""
        signals = [
            {"signal_type": "liquidity_sweep", "timestamp": 500, "confidence": 0.9},
            {"signal_type": "order_block", "timestamp": 1000, "confidence": 0.6},
            {"signal_type": "fvg", "timestamp": 800, "confidence": 0.8},
            {"signal_type": "bos_choch", "timestamp": 2000, "confidence": 0.4},
        ]
        result = resolve_highest_priority_signal(signals)
        # BOS/CHoCH wins despite being newest (highest priority)
        assert result["signal_type"] == "bos_choch"
        assert result["timestamp"] == 2000
