"""Priority resolver for ICT signal detections.

This module provides the `resolve_highest_priority_signal` function that determines
which signal to act on when multiple ICT detections fire simultaneously for the same token.

Priority rationale (ICT Smart Money Concepts):
    BOS/CHoCH > Order Blocks > FVG > Liquidity Sweeps

When multiple signals of the same priority fire simultaneously, tie-breaking:
    1. Timestamp: older signals (earlier timestamp) win first
    2. Confidence: higher confidence wins if timestamps are equal

Usage:
    from signal_generation.priority_resolver import resolve_highest_priority_signal

    signals = [
        {"signal_type": "fvg", "timestamp": 1234567890000, "confidence": 0.8},
        {"signal_type": "order_block", "timestamp": 1234567890000, "confidence": 0.75},
    ]
    result = resolve_highest_priority_signal(signals)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


# Default priority order (lower index = higher priority)
DEFAULT_PRIORITY_ORDER = ["bos_choch", "order_block", "fvg", "liquidity_sweep"]

# Mapping from signal_type string to SignalPriority value for fallback lookup
SIGNAL_TYPE_TO_PRIORITY: dict[str, int] = {
    "bos_choch": 1,
    "order_block": 2,
    "fvg": 3,
    "liquidity_sweep": 4,
    "cvd": 4,  # CVD treated as liquidity-sensitive per ICTSignalRegistry
    "price_structure": 5,
    # Price structure signal types
    "h": 5,
    "l": 5,
    "high_old": 5,
    "low_old": 5,
}


def _get_signal_priority_value(signal_type: str, priority_order: list[str]) -> int:
    """Get the priority value for a signal type.

    Args:
        signal_type: The signal type string
        priority_order: Custom priority order list

    Returns:
        Priority value (lower = higher priority). Returns 99 if signal type
        is not found in priority_order or SIGNAL_TYPE_TO_PRIORITY fallback.
    """
    # First try custom priority_order
    if signal_type in priority_order:
        return priority_order.index(signal_type)

    # Fallback to SIGNAL_TYPE_TO_PRIORITY mapping
    if signal_type in SIGNAL_TYPE_TO_PRIORITY:
        return SIGNAL_TYPE_TO_PRIORITY[signal_type]

    logger.warning(f"Unknown signal type for priority: {signal_type}")
    return 99  # Lowest priority for unknown types


def _get_timestamp_ms(signal: dict[str, Any]) -> float:
    """Extract timestamp in milliseconds from signal dict.

    Args:
        signal: Signal dictionary

    Returns:
        Timestamp in milliseconds, or float('inf') if not available
    """
    ts = signal.get("timestamp")
    if ts is None:
        return float("inf")

    # Handle datetime objects
    if isinstance(ts, datetime):
        return ts.timestamp() * 1000

    # Handle Unix timestamp in seconds
    if isinstance(ts, (int, float)):
        # If timestamp looks like seconds (before year 3000 in seconds)
        if ts < 32503680000:  # year 3000 in seconds
            return ts * 1000
        return ts

    return float("inf")


def _get_confidence(signal: dict[str, Any]) -> float:
    """Extract confidence score from signal dict.

    Args:
        signal: Signal dictionary

    Returns:
        Confidence score (0.0-1.0), or 0.0 if not available
    """
    confidence = signal.get("confidence")
    if confidence is None:
        return 0.0

    # Handle potential percentage format (e.g., 75 for 0.75)
    if isinstance(confidence, (int, float)):
        if confidence > 1.0:
            confidence = confidence / 100.0
        return float(confidence)

    return 0.0


def resolve_highest_priority_signal(
    signals: list[dict[str, Any]],
    priority_order: list[str] | None = None,
) -> dict[str, Any] | None:
    """Resolve the highest priority signal from a list of simultaneous detections.

    When multiple ICT detections fire simultaneously for the same token, this function
    determines which signal to act on based on configured priority order.

    Args:
        signals: List of signal dicts, each must have at least 'signal_type' key.
            Optional keys for tie-breaking:
            - timestamp: Unix timestamp in ms or datetime object (older = higher priority)
            - confidence: float 0.0-1.0 (higher = higher priority)
        priority_order: Custom priority order as list of signal type strings.
            Lower index = higher priority. Defaults to:
            ["bos_choch", "order_block", "fvg", "liquidity_sweep"]

    Returns:
        The highest priority signal dict, or None if the list is empty.

    Tie-breaking:
        When multiple signals have the same priority:
        1. Timestamp: signals with older timestamps win first
        2. Confidence: if timestamps are equal, higher confidence wins

    Example:
        >>> signals = [
        ...     {"signal_type": "fvg", "timestamp": 1000, "confidence": 0.8},
        ...     {"signal_type": "order_block", "timestamp": 500, "confidence": 0.7},
        ... ]
        >>> resolve_highest_priority_signal(signals)
        {'signal_type': 'order_block', 'timestamp': 500, 'confidence': 0.7}
    """
    if not signals:
        return None

    if priority_order is None:
        priority_order = DEFAULT_PRIORITY_ORDER.copy()

    # Sort signals by:
    # 1. Priority value (ascending = higher priority first)
    # 2. Timestamp (ascending = older first)
    # 3. Confidence (descending = higher first)
    sorted_signals = sorted(
        signals,
        key=lambda s: (
            _get_signal_priority_value(s.get("signal_type", ""), priority_order),
            _get_timestamp_ms(s),
            -_get_confidence(s),  # Negative for descending order
        ),
    )

    winner = sorted_signals[0]
    logger.debug(
        f"Resolved highest priority signal: {winner.get('signal_type')} "
        f"(priority={_get_signal_priority_value(winner.get('signal_type', ''), priority_order)})"
    )

    return winner
