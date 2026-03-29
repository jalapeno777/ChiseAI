#!/usr/bin/env python3
"""Generate synthetic BOS/CHoCH test scenarios with 80-120 candles each.

Designs scenarios that produce valid structural patterns when processed by
the CORRECTED BOS/CHoCH algorithm (T-BOS-002 fix).

Corrected algorithm behavior (after fixing _is_level_broken AND _calculate_strength):
- Bullish BOS: swing_high price > previous swing_high price (higher high)
- Bearish BOS: swing_low price < previous swing_low price (lower low)
- Bullish CHoCH: swing_high price > previous swing_low price (reversal up)
- Bearish CHoCH: swing_low price < previous swing_high price (reversal down)

CRITICAL: The test evaluation checks has_bullish FIRST. If ANY bullish event is detected,
direction is "bullish" regardless of bearish events. So for bearish scenarios, we must
ensure ZERO bullish events occur (no swing_high breaks any previous swing_high or swing_low).

Swing pivot detection uses window_size=3. A swing pivot forms when a candle's high/low is
the highest/lowest among the window*2+1=7 surrounding candles. Swing pivots alternate
between swing_high and swing_low.

Key design principles:
- BEARISH scenarios: ALL swing highs must be strictly decreasing (no higher-high anywhere)
- NO-BREAK scenarios: No swing should break any previous swing level
- BULLISH scenarios: Natural uptrend with higher highs and higher lows
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

random.seed(42)


def make_candle(
    ts: int, o: float, h: float, l: float, c: float, v: float = 1000.0
) -> list:
    """Create a valid OHLCV candle array [ts, o, h, l, c, v]."""
    assert h >= o and h >= c, f"High must be >= open and close: h={h} o={o} c={c}"
    assert l <= o and l <= c, f"Low must be <= open and close: l={l} o={o} c={c}"
    assert h > l, f"High must be > low: h={h} l={l}"
    return [ts, round(o, 2), round(h, 2), round(l, 2), round(c, 2), round(v, 1)]


def make_swing_high_candles(
    center_ts: int,
    peak_price: float,
    approach_len: int = 3,
    decline_len: int = 3,
    approach_start: float = 0.0,
    decline_end: float = 0.0,
    noise: float = 0.1,
) -> list[list]:
    """Create candles forming a swing high pivot.

    Generates: approach up -> peak -> decline down
    The peak candle will be the highest among the surrounding candles.
    """
    candles = []
    ts = center_ts - approach_len * 60000

    # Approach: rise from approach_start to peak
    for j in range(approach_len):
        progress = (j + 1) / (approach_len + 1)
        mid = approach_start + (peak_price - approach_start) * progress
        o = mid - noise * random.uniform(0, 1)
        c = mid + noise * random.uniform(0, 1)
        h = max(o, c) + noise * random.uniform(0.5, 1)
        l = min(o, c) - noise * random.uniform(0.5, 1)
        candles.append(make_candle(ts, o, h, l, c, random.randint(800, 1500)))
        ts += 60000

    # Peak candle
    o = peak_price - noise * random.uniform(0, 0.5)
    c = peak_price + noise * random.uniform(0, 0.5)
    h = max(o, c) + noise * random.uniform(0.5, 1)
    l = min(o, c) - noise * random.uniform(0.5, 1)
    candles.append(make_candle(ts, o, h, l, c, random.randint(1200, 2000)))
    ts += 60000

    # Decline: drop from peak to decline_end
    for j in range(decline_len):
        progress = (j + 1) / (decline_len + 1)
        mid = peak_price + (decline_end - peak_price) * progress
        o = mid + noise * random.uniform(0, 1)
        c = mid - noise * random.uniform(0, 1)
        h = max(o, c) + noise * random.uniform(0.5, 1)
        l = min(o, c) - noise * random.uniform(0.5, 1)
        candles.append(make_candle(ts, o, h, l, c, random.randint(800, 1500)))
        ts += 60000

    return candles


def make_swing_low_candles(
    center_ts: int,
    trough_price: float,
    approach_len: int = 3,
    recover_len: int = 3,
    approach_start: float = 0.0,
    recover_end: float = 0.0,
    noise: float = 0.1,
) -> list[list]:
    """Create candles forming a swing low pivot.

    Generates: approach down -> trough -> recover up
    The trough candle will be the lowest among the surrounding candles.
    """
    candles = []
    ts = center_ts - approach_len * 60000

    # Approach: drop from approach_start to trough
    for j in range(approach_len):
        progress = (j + 1) / (approach_len + 1)
        mid = approach_start + (trough_price - approach_start) * progress
        o = mid + noise * random.uniform(0, 1)
        c = mid - noise * random.uniform(0, 1)
        h = max(o, c) + noise * random.uniform(0.5, 1)
        l = min(o, c) - noise * random.uniform(0.5, 1)
        candles.append(make_candle(ts, o, h, l, c, random.randint(800, 1500)))
        ts += 60000

    # Trough candle
    o = trough_price + noise * random.uniform(0, 0.5)
    c = trough_price - noise * random.uniform(0, 0.5)
    h = max(o, c) + noise * random.uniform(0.5, 1)
    l = min(o, c) - noise * random.uniform(0.5, 1)
    candles.append(make_candle(ts, o, h, l, c, random.randint(1200, 2000)))
    ts += 60000

    # Recovery: rise from trough to recover_end
    for j in range(recover_len):
        progress = (j + 1) / (recover_len + 1)
        mid = trough_price + (recover_end - trough_price) * progress
        o = mid - noise * random.uniform(0, 1)
        c = mid + noise * random.uniform(0, 1)
        h = max(o, c) + noise * random.uniform(0.5, 1)
        l = min(o, c) - noise * random.uniform(0.5, 1)
        candles.append(make_candle(ts, o, h, l, c, random.randint(800, 1500)))
        ts += 60000

    return candles


def generate_uptrend_bos(
    n_candles: int = 100, base_price: float = 100.0, swing_size: float = 3.0
) -> list[list]:
    """Generate uptrend with progressively higher swing highs and higher swing lows.

    Each swing_high > previous swing_high (bullish BOS)
    Each swing_low > previous swing_low (no bearish breaks)
    """
    candles = []
    n_swings = 6  # Generate 6 swing_high + 6 swing_low pairs

    swing_highs = [base_price + swing_size * (i + 1) for i in range(n_swings)]
    swing_lows = [
        base_price - swing_size * 0.3 + swing_size * 0.8 * i for i in range(n_swings)
    ]

    # First approach to first swing high
    approach_start = base_price - 2
    candles.extend(
        make_swing_high_candles(
            center_ts=1000000 + 3 * 60000,
            peak_price=swing_highs[0],
            approach_len=3,
            decline_len=3,
            approach_start=approach_start,
            decline_end=(swing_highs[0] + swing_lows[0]) / 2,
            noise=swing_size * 0.05,
        )
    )

    ts_offset = len(candles) * 60000 + 1000000

    for i in range(n_swings):
        # Swing low after swing high
        if i < n_swings:
            trough = swing_lows[i]
            high_before = swing_highs[i]
            low_after = (
                (swing_lows[i] + swing_highs[min(i + 1, n_swings - 1)]) / 2
                if i < n_swings - 1
                else trough + 2
            )

            candles.extend(
                make_swing_low_candles(
                    center_ts=ts_offset + 3 * 60000,
                    trough_price=trough,
                    approach_len=3,
                    recover_len=3,
                    approach_start=high_before - swing_size * 0.5,
                    recover_end=low_after,
                    noise=swing_size * 0.05,
                )
            )
            ts_offset = 1000000 + len(candles) * 60000

        # Next swing high
        if i < n_swings - 1:
            peak = swing_highs[i + 1]
            low_before = swing_lows[i]
            high_after = (swing_highs[i + 1] + swing_lows[min(i + 1, n_swings - 1)]) / 2

            candles.extend(
                make_swing_high_candles(
                    center_ts=ts_offset + 3 * 60000,
                    peak_price=peak,
                    approach_len=3,
                    decline_len=3,
                    approach_start=low_before + swing_size * 0.3,
                    decline_end=high_after,
                    noise=swing_size * 0.05,
                )
            )
            ts_offset = 1000000 + len(candles) * 60000

    # Fill remaining candles with continuation
    while len(candles) < n_candles:
        last_price = candles[-1][4]
        new_price = last_price + swing_size * 0.1
        o = new_price - swing_size * 0.02
        c = new_price + swing_size * 0.02
        h = max(o, c) + swing_size * 0.01
        l = min(o, c) - swing_size * 0.01
        candles.append(make_candle(ts_offset, o, h, l, c, random.randint(800, 1500)))
        ts_offset += 60000

    return candles[:n_candles]


def generate_downtrend_bos(
    n_candles: int = 100, base_price: float = 120.0, swing_size: float = 3.0
) -> list[list]:
    """Generate downtrend with progressively lower swing lows and lower swing highs.

    CRITICAL: swing highs must NEVER break previous swing highs (no bullish events).
    Each swing_low < previous swing_low (bearish BOS)
    Each swing_high < previous swing_high (prevents bullish BOS)
    """
    candles = []
    n_swings = 6

    # Strictly decreasing swing highs and swing lows
    swing_highs = [base_price - swing_size * (i + 1) for i in range(n_swings)]
    swing_lows = [
        base_price - swing_size * 2 - swing_size * (i + 1) for i in range(n_swings)
    ]

    # First approach to first swing high
    approach_start = base_price + 2
    candles.extend(
        make_swing_high_candles(
            center_ts=1000000 + 3 * 60000,
            peak_price=swing_highs[0],
            approach_len=3,
            decline_len=3,
            approach_start=approach_start,
            decline_end=(swing_highs[0] + swing_lows[0]) / 2,
            noise=swing_size * 0.05,
        )
    )

    ts_offset = len(candles) * 60000 + 1000000

    for i in range(n_swings):
        # Swing low after swing high
        if i < n_swings:
            trough = swing_lows[i]
            high_before = swing_highs[i]
            low_after = (
                (swing_lows[i] + swing_highs[min(i + 1, n_swings - 1)]) / 2
                if i < n_swings - 1
                else trough - 2
            )

            candles.extend(
                make_swing_low_candles(
                    center_ts=ts_offset + 3 * 60000,
                    trough_price=trough,
                    approach_len=3,
                    recover_len=3,
                    approach_start=high_before + swing_size * 0.3,
                    recover_end=low_after,
                    noise=swing_size * 0.05,
                )
            )
            ts_offset = 1000000 + len(candles) * 60000

        # Next swing high (must be LOWER than previous)
        if i < n_swings - 1:
            peak = swing_highs[i + 1]
            low_before = swing_lows[i]
            high_after = (swing_highs[i + 1] + swing_lows[min(i + 1, n_swings - 1)]) / 2

            candles.extend(
                make_swing_high_candles(
                    center_ts=ts_offset + 3 * 60000,
                    peak_price=peak,
                    approach_len=3,
                    decline_len=3,
                    approach_start=low_before + swing_size * 0.3,
                    decline_end=high_after,
                    noise=swing_size * 0.05,
                )
            )
            ts_offset = 1000000 + len(candles) * 60000

    # Fill remaining candles with continuation
    while len(candles) < n_candles:
        last_price = candles[-1][4]
        new_price = last_price - swing_size * 0.1
        o = new_price + swing_size * 0.02
        c = new_price - swing_size * 0.02
        h = max(o, c) + swing_size * 0.01
        l = min(o, c) - swing_size * 0.01
        candles.append(make_candle(ts_offset, o, h, l, c, random.randint(800, 1500)))
        ts_offset += 60000

    return candles[:n_candles]


def generate_bullish_choch(
    n_candles: int = 100, base_price: float = 110.0, swing_size: float = 3.0
) -> list[list]:
    """Generate downtrend that reverses to uptrend (bullish CHoCH).

    Phase 1: Downtrend with lower highs and lower lows
    Phase 2: Sharp reversal - swing high breaks ABOVE a previous swing low
    CRITICAL: Must not create any bearish events during reversal
    """
    candles = []
    n_downtrend_swings = 3

    # Downtrend swings (strictly decreasing)
    swing_highs_down = [base_price - swing_size * i for i in range(n_downtrend_swings)]
    swing_lows_down = [
        base_price - swing_size * 1.5 - swing_size * i
        for i in range(n_downtrend_swings)
    ]

    # First swing high
    approach_start = base_price + 2
    candles.extend(
        make_swing_high_candles(
            center_ts=1000000 + 3 * 60000,
            peak_price=swing_highs_down[0],
            approach_len=3,
            decline_len=3,
            approach_start=approach_start,
            decline_end=(swing_highs_down[0] + swing_lows_down[0]) / 2,
            noise=swing_size * 0.05,
        )
    )

    ts_offset = len(candles) * 60000 + 1000000

    for i in range(n_downtrend_swings):
        # Swing low
        trough = swing_lows_down[i]
        high_before = swing_highs_down[i]
        low_after = (
            (swing_lows_down[i] + swing_highs_down[min(i + 1, n_downtrend_swings - 1)])
            / 2
            if i < n_downtrend_swings - 1
            else trough - 2
        )

        candles.extend(
            make_swing_low_candles(
                center_ts=ts_offset + 3 * 60000,
                trough_price=trough,
                approach_len=3,
                recover_len=3,
                approach_start=high_before + swing_size * 0.3,
                recover_end=low_after,
                noise=swing_size * 0.05,
            )
        )
        ts_offset = 1000000 + len(candles) * 60000

        # Next swing high (lower than previous)
        if i < n_downtrend_swings - 1:
            peak = swing_highs_down[i + 1]
            low_before = swing_lows_down[i]
            high_after = (
                swing_highs_down[i + 1]
                + swing_lows_down[min(i + 1, n_downtrend_swings - 1)]
            ) / 2

            candles.extend(
                make_swing_high_candles(
                    center_ts=ts_offset + 3 * 60000,
                    peak_price=peak,
                    approach_len=3,
                    decline_len=3,
                    approach_start=low_before + swing_size * 0.3,
                    decline_end=high_after,
                    noise=swing_size * 0.05,
                )
            )
            ts_offset = 1000000 + len(candles) * 60000

    # Reversal phase: push up strongly
    # The last swing low was swing_lows_down[-1]
    # We need a swing high that goes ABOVE this swing low
    last_swing_low = swing_lows_down[-1]
    reversal_target = last_swing_low + swing_size * 4  # Well above

    # Add some filler candles first
    filler_count = max(5, (n_candles - len(candles) - 7) // 2)
    for _ in range(filler_count):
        price = candles[-1][4]
        o = price + swing_size * 0.05
        c = price + swing_size * 0.15
        h = max(o, c) + swing_size * 0.05
        l = min(o, c) - swing_size * 0.02
        candles.append(make_candle(ts_offset, o, h, l, c, random.randint(1000, 2500)))
        ts_offset += 60000

    # Create reversal swing high ABOVE the last swing low
    candles.extend(
        make_swing_high_candles(
            center_ts=ts_offset + 3 * 60000,
            peak_price=reversal_target,
            approach_len=3,
            decline_len=3,
            approach_start=candles[-1][4],
            decline_end=reversal_target - swing_size,
            noise=swing_size * 0.05,
        )
    )
    ts_offset = 1000000 + len(candles) * 60000

    # Continue uptrend
    while len(candles) < n_candles:
        last_price = candles[-1][4]
        new_price = last_price + swing_size * 0.15
        o = new_price - swing_size * 0.02
        c = new_price + swing_size * 0.02
        h = max(o, c) + swing_size * 0.01
        l = min(o, c) - swing_size * 0.01
        candles.append(make_candle(ts_offset, o, h, l, c, random.randint(800, 1500)))
        ts_offset += 60000

    return candles[:n_candles]


def generate_bearish_choch(
    n_candles: int = 100, base_price: float = 100.0, swing_size: float = 3.0
) -> list[list]:
    """Generate uptrend that reverses to downtrend (bearish CHoCH).

    Phase 1: Uptrend with higher highs and higher lows
    Phase 2: Sharp reversal - swing low breaks BELOW a previous swing high
    CRITICAL: Must not create any bullish events during reversal
    (reversal swing highs must NOT break any previous swing high)
    """
    candles = []
    n_uptrend_swings = 3

    # Uptrend swings (strictly increasing)
    swing_highs_up = [
        base_price + swing_size * (i + 1) for i in range(n_uptrend_swings)
    ]
    swing_lows_up = [
        base_price - swing_size * 0.3 + swing_size * 0.8 * i
        for i in range(n_uptrend_swings)
    ]

    # First swing high
    approach_start = base_price - 2
    candles.extend(
        make_swing_high_candles(
            center_ts=1000000 + 3 * 60000,
            peak_price=swing_highs_up[0],
            approach_len=3,
            decline_len=3,
            approach_start=approach_start,
            decline_end=(swing_highs_up[0] + swing_lows_up[0]) / 2,
            noise=swing_size * 0.05,
        )
    )

    ts_offset = len(candles) * 60000 + 1000000

    for i in range(n_uptrend_swings):
        # Swing low
        trough = swing_lows_up[i]
        high_before = swing_highs_up[i]
        low_after = (
            (swing_lows_up[i] + swing_highs_up[min(i + 1, n_uptrend_swings - 1)]) / 2
            if i < n_uptrend_swings - 1
            else trough + 2
        )

        candles.extend(
            make_swing_low_candles(
                center_ts=ts_offset + 3 * 60000,
                trough_price=trough,
                approach_len=3,
                recover_len=3,
                approach_start=high_before - swing_size * 0.5,
                recover_end=low_after,
                noise=swing_size * 0.05,
            )
        )
        ts_offset = 1000000 + len(candles) * 60000

        # Next swing high (higher than previous)
        if i < n_uptrend_swings - 1:
            peak = swing_highs_up[i + 1]
            low_before = swing_lows_up[i]
            high_after = (
                swing_highs_up[i + 1] + swing_lows_up[min(i + 1, n_uptrend_swings - 1)]
            ) / 2

            candles.extend(
                make_swing_high_candles(
                    center_ts=ts_offset + 3 * 60000,
                    peak_price=peak,
                    approach_len=3,
                    decline_len=3,
                    approach_start=low_before + swing_size * 0.3,
                    decline_end=high_after,
                    noise=swing_size * 0.05,
                )
            )
            ts_offset = 1000000 + len(candles) * 60000

    # Reversal phase: push down strongly
    # The last swing high was swing_highs_up[-1]
    # We need a swing low that goes BELOW this swing high
    last_swing_high = swing_highs_up[-1]
    reversal_target = last_swing_high - swing_size * 4  # Well below

    # Add some filler candles first
    filler_count = max(5, (n_candles - len(candles) - 7) // 2)
    for _ in range(filler_count):
        price = candles[-1][4]
        o = price + swing_size * 0.05
        c = price - swing_size * 0.15
        h = max(o, c) + swing_size * 0.02
        l = min(o, c) - swing_size * 0.05
        candles.append(make_candle(ts_offset, o, h, l, c, random.randint(1000, 2500)))
        ts_offset += 60000

    # Create reversal swing low BELOW the last swing high
    # CRITICAL: This swing low must not be accompanied by any swing high
    # that breaks a previous swing high
    candles.extend(
        make_swing_low_candles(
            center_ts=ts_offset + 3 * 60000,
            trough_price=reversal_target,
            approach_len=3,
            recover_len=3,
            approach_start=candles[-1][4],
            recover_end=reversal_target + swing_size,
            noise=swing_size * 0.05,
        )
    )
    ts_offset = 1000000 + len(candles) * 60000

    # Continue downtrend with LOWER swing highs (prevent bullish events)
    remaining = n_candles - len(candles)
    if remaining > 6:
        # Add a bounce (lower than previous swing high)
        max_prev_high = max(swing_highs_up)
        bounce_peak = max_prev_high - swing_size * 2  # Lower than all previous highs

        candles.extend(
            make_swing_high_candles(
                center_ts=ts_offset + 3 * 60000,
                peak_price=bounce_peak,
                approach_len=3,
                decline_len=3,
                approach_start=reversal_target + swing_size,
                decline_end=bounce_peak - swing_size,
                noise=swing_size * 0.05,
            )
        )
        ts_offset = 1000000 + len(candles) * 60000

    # Fill remaining
    while len(candles) < n_candles:
        last_price = candles[-1][4]
        new_price = last_price - swing_size * 0.1
        o = new_price + swing_size * 0.02
        c = new_price - swing_size * 0.02
        h = max(o, c) + swing_size * 0.01
        l = min(o, c) - swing_size * 0.01
        candles.append(make_candle(ts_offset, o, h, l, c, random.randint(800, 1500)))
        ts_offset += 60000

    return candles[:n_candles]


def generate_range_no_break(
    n_candles: int = 100, base_price: float = 100.0, half_range: float = 3.0
) -> list[list]:
    """Generate ranging market without ANY structural breaks.

    ALL swing highs must be lower than the FIRST swing high.
    ALL swing lows must be higher than the FIRST swing low.
    This ensures no breaks occur.
    """
    candles = []
    ts = 1000000

    ceiling = base_price + half_range
    floor = base_price - half_range

    # Generate oscillating price within range
    # Use a deterministic zigzag pattern
    direction = 1
    price = base_price

    for i in range(n_candles):
        # Bounce between ceiling and floor
        if price > ceiling - 0.5:
            direction = -1
        elif price < floor + 0.5:
            direction = 1

        step = direction * random.uniform(0.2, 0.6)
        price += step

        # Add tiny noise
        o = price + random.uniform(-0.1, 0.1)
        c = price + random.uniform(-0.1, 0.1)
        h = max(o, c) + random.uniform(0.05, 0.2)
        l = min(o, c) - random.uniform(0.05, 0.2)

        # Hard clamp to range with buffer
        h = min(h, ceiling - 0.1)
        l = max(l, floor + 0.1)
        # Ensure h > l after rounding (add spread if needed)
        if round(h, 2) <= round(l, 2):
            mid = (h + l) / 2
            h = mid + 0.05
            l = mid - 0.05
        # Now clamp o and c to be strictly between l and h
        o = min(max(o, l + 0.01), h - 0.01)
        c = min(max(c, l + 0.01), h - 0.01)

        candles.append(make_candle(ts, o, h, l, c, random.randint(500, 1200)))
        ts += 60000

    return candles[:n_candles]


# ---------------------------------------------------------------------------
# Scenario catalog
# ---------------------------------------------------------------------------


def build_scenario_catalog() -> list[dict]:
    """Build the full scenario catalog with 52+ scenarios."""
    scenarios = []
    sid = 1

    def add_scenario(name, gen_fn, kwargs, expected, tags):
        nonlocal sid
        ohlcv = gen_fn(**kwargs)
        scenarios.append(
            {
                "id": f"bos_choch_{sid:03d}",
                "name": name,
                "ohlcv": ohlcv,
                "expected": expected,
                "tags": tags,
            }
        )
        sid += 1

    # ---- Bullish BOS scenarios (12) ----
    bullish_bos_configs = [
        (
            "Bullish BOS - clean uptrend",
            dict(n_candles=95, base_price=100.0, swing_size=3.0),
        ),
        (
            "Bullish BOS - strong momentum",
            dict(n_candles=85, base_price=150.0, swing_size=5.0),
        ),
        (
            "Bullish BOS - gradual climb",
            dict(n_candles=110, base_price=80.0, swing_size=2.0),
        ),
        (
            "Bullish BOS - volatile breakout",
            dict(n_candles=100, base_price=200.0, swing_size=6.0),
        ),
        (
            "Bullish BOS - slow grind",
            dict(n_candles=120, base_price=50.0, swing_size=1.5),
        ),
        (
            "Bullish BOS - recovery from dip",
            dict(n_candles=90, base_price=120.0, swing_size=4.0),
        ),
        (
            "Bullish BOS - 5 wave impulse",
            dict(n_candles=100, base_price=60.0, swing_size=3.5),
        ),
        (
            "Bullish BOS - high volatility",
            dict(n_candles=88, base_price=90.0, swing_size=7.0),
        ),
        (
            "Bullish BOS - steady pullbacks",
            dict(n_candles=105, base_price=75.0, swing_size=2.5),
        ),
        (
            "Bullish BOS - sharp impulse",
            dict(n_candles=80, base_price=180.0, swing_size=8.0),
        ),
        (
            "Bullish BOS - mid-range",
            dict(n_candles=100, base_price=130.0, swing_size=4.5),
        ),
        (
            "Bullish BOS - tight range",
            dict(n_candles=95, base_price=45.0, swing_size=1.0),
        ),
    ]
    for name, kwargs in bullish_bos_configs:
        add_scenario(
            name,
            generate_uptrend_bos,
            kwargs,
            {"bos": True, "choch": False, "direction": "bullish"},
            ["bullish_bos", "uptrend"],
        )

    # ---- Bearish BOS scenarios (12) ----
    bearish_bos_configs = [
        (
            "Bearish BOS - clean downtrend",
            dict(n_candles=95, base_price=120.0, swing_size=3.0),
        ),
        (
            "Bearish BOS - strong momentum",
            dict(n_candles=85, base_price=150.0, swing_size=5.0),
        ),
        (
            "Bearish BOS - gradual decline",
            dict(n_candles=110, base_price=80.0, swing_size=2.0),
        ),
        (
            "Bearish BOS - volatile selloff",
            dict(n_candles=100, base_price=200.0, swing_size=6.0),
        ),
        (
            "Bearish BOS - slow grind down",
            dict(n_candles=120, base_price=50.0, swing_size=1.5),
        ),
        (
            "Bearish BOS - distribution top",
            dict(n_candles=90, base_price=180.0, swing_size=4.0),
        ),
        (
            "Bearish BOS - 5 wave drop",
            dict(n_candles=100, base_price=60.0, swing_size=3.5),
        ),
        (
            "Bearish BOS - high volatility",
            dict(n_candles=88, base_price=90.0, swing_size=7.0),
        ),
        (
            "Bearish BOS - steady bounces",
            dict(n_candles=105, base_price=75.0, swing_size=2.5),
        ),
        (
            "Bearish BOS - sharp drop",
            dict(n_candles=80, base_price=180.0, swing_size=8.0),
        ),
        (
            "Bearish BOS - mid-range",
            dict(n_candles=100, base_price=130.0, swing_size=4.5),
        ),
        (
            "Bearish BOS - tight range",
            dict(n_candles=95, base_price=45.0, swing_size=1.0),
        ),
    ]
    for name, kwargs in bearish_bos_configs:
        add_scenario(
            name,
            generate_downtrend_bos,
            kwargs,
            {"bos": True, "choch": False, "direction": "bearish"},
            ["bearish_bos", "downtrend"],
        )

    # ---- Bullish CHoCH scenarios (10) ----
    bullish_choch_configs = [
        (
            "Bullish CHoCH - downtrend reversal",
            dict(n_candles=100, base_price=110.0, swing_size=3.0),
        ),
        (
            "Bullish CHoCH - V-reversal",
            dict(n_candles=90, base_price=150.0, swing_size=5.0),
        ),
        (
            "Bullish CHoCH - slow base reversal",
            dict(n_candles=110, base_price=80.0, swing_size=2.0),
        ),
        (
            "Bullish CHoCH - volatile reversal",
            dict(n_candles=95, base_price=200.0, swing_size=6.0),
        ),
        (
            "Bullish CHoCH - double bottom",
            dict(n_candles=105, base_price=70.0, swing_size=3.5),
        ),
        (
            "Bullish CHoCH - capitulation",
            dict(n_candles=85, base_price=130.0, swing_size=4.5),
        ),
        (
            "Bullish CHoCH - extended reversal",
            dict(n_candles=115, base_price=90.0, swing_size=3.0),
        ),
        (
            "Bullish CHoCH - gradual shift",
            dict(n_candles=100, base_price=60.0, swing_size=2.5),
        ),
        (
            "Bullish CHoCH - crash recover",
            dict(n_candles=88, base_price=180.0, swing_size=5.5),
        ),
        (
            "Bullish CHoCH - tight reversal",
            dict(n_candles=95, base_price=45.0, swing_size=1.5),
        ),
    ]
    for name, kwargs in bullish_choch_configs:
        add_scenario(
            name,
            generate_bullish_choch,
            kwargs,
            {"bos": False, "choch": True, "direction": "bullish"},
            ["bullish_choch", "reversal"],
        )

    # ---- Bearish CHoCH scenarios (10) ----
    bearish_choch_configs = [
        (
            "Bearish CHoCH - uptrend reversal",
            dict(n_candles=100, base_price=100.0, swing_size=3.0),
        ),
        (
            "Bearish CHoCH - top reversal",
            dict(n_candles=90, base_price=150.0, swing_size=5.0),
        ),
        (
            "Bearish CHoCH - rolling top",
            dict(n_candles=110, base_price=80.0, swing_size=2.0),
        ),
        (
            "Bearish CHoCH - volatile reversal",
            dict(n_candles=95, base_price=200.0, swing_size=6.0),
        ),
        (
            "Bearish CHoCH - double top",
            dict(n_candles=105, base_price=70.0, swing_size=3.5),
        ),
        (
            "Bearish CHoCH - blow-off top",
            dict(n_candles=85, base_price=130.0, swing_size=4.5),
        ),
        (
            "Bearish CHoCH - extended reversal",
            dict(n_candles=115, base_price=90.0, swing_size=3.0),
        ),
        (
            "Bearish CHoCH - gradual shift",
            dict(n_candles=100, base_price=60.0, swing_size=2.5),
        ),
        (
            "Bearish CHoCH - pump dump",
            dict(n_candles=88, base_price=180.0, swing_size=5.5),
        ),
        (
            "Bearish CHoCH - tight reversal",
            dict(n_candles=95, base_price=45.0, swing_size=1.5),
        ),
    ]
    for name, kwargs in bearish_choch_configs:
        add_scenario(
            name,
            generate_bearish_choch,
            kwargs,
            {"bos": False, "choch": True, "direction": "bearish"},
            ["bearish_choch", "reversal"],
        )

    # ---- No-break / ranging scenarios (8) ----
    no_break_configs = [
        (
            "No break - tight range",
            dict(n_candles=100, base_price=100.0, half_range=2.0),
        ),
        (
            "No break - wide oscillation",
            dict(n_candles=90, base_price=150.0, half_range=4.0),
        ),
        ("No break - flat micro", dict(n_candles=110, base_price=80.0, half_range=1.0)),
        (
            "No break - fake breakouts",
            dict(n_candles=105, base_price=200.0, half_range=3.0),
        ),
        (
            "No break - narrow squeeze",
            dict(n_candles=85, base_price=130.0, half_range=1.5),
        ),
        (
            "No break - consolidation",
            dict(n_candles=120, base_price=90.0, half_range=2.5),
        ),
        (
            "No break - choppy whipsaw",
            dict(n_candles=95, base_price=60.0, half_range=3.5),
        ),
        ("No break - sideways", dict(n_candles=100, base_price=45.0, half_range=1.0)),
    ]
    for name, kwargs in no_break_configs:
        add_scenario(
            name,
            generate_range_no_break,
            kwargs,
            {"bos": False, "choch": False, "direction": "none"},
            ["no_break", "ranging"],
        )

    return scenarios


def validate_scenarios(scenarios: list[dict]) -> list[str]:
    """Validate scenarios and return list of issues."""
    issues = []
    for s in scenarios:
        sid = s["id"]
        ohlcv = s["ohlcv"]
        if len(ohlcv) < 80:
            issues.append(f"{sid}: Only {len(ohlcv)} candles (need 80-120)")
        elif len(ohlcv) > 120:
            issues.append(f"{sid}: {len(ohlcv)} candles (need 80-120)")
        for i, candle in enumerate(ohlcv):
            if len(candle) != 6:
                issues.append(f"{sid}: candle {i} has {len(candle)} values (need 6)")
                continue
            ts, o, h, l, c, v = candle
            if h <= l:
                issues.append(f"{sid}: candle {i} h={h} <= l={l}")
            if h < o or h < c:
                issues.append(f"{sid}: candle {i} h={h} < o={o} or c={c}")
            if l > o or l > c:
                issues.append(f"{sid}: candle {i} l={l} > o={o} or c={c}")
            if v <= 0:
                issues.append(f"{sid}: candle {i} volume={v} <= 0")
    return issues


def main():
    output_path = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else Path("tests/fixtures/ict/scenarios/bos_choch_scenarios.json")
    )

    print("Generating BOS/CHoCH scenarios...")
    scenarios = build_scenario_catalog()

    print(f"  Generated {len(scenarios)} scenarios")
    for s in scenarios:
        print(f"    {s['id']}: {s['name']} ({len(s['ohlcv'])} candles)")

    issues = validate_scenarios(scenarios)
    if issues:
        print("\nVALIDATION ISSUES:")
        for issue in issues:
            print(f"  - {issue}")
        return 1

    print("\nAll scenarios validated successfully.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = {"scenarios": scenarios}
    with output_path.open("w") as f:
        json.dump(data, f, indent=2)

    print(f"\nWritten to {output_path}")

    types = {}
    for s in scenarios:
        tags = s.get("tags", [])
        primary = tags[0] if tags else "unknown"
        types[primary] = types.get(primary, 0) + 1

    print("\nScenario type distribution:")
    for t, count in sorted(types.items()):
        print(f"  {t}: {count}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
