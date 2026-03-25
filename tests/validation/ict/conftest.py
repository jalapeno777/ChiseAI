"""Shared fixtures and utilities for ICT component validation tests."""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

FIXTURES_DIR = (
    Path(__file__).resolve().parent.parent.parent / "fixtures" / "ict" / "scenarios"
)


def _load_scenarios(filename: str) -> list[dict[str, Any]]:
    """Load scenario list from a JSON fixture file."""
    path = FIXTURES_DIR / filename
    with path.open() as fh:
        data = json.load(fh)
    return data.get("scenarios", [])


# ---------------------------------------------------------------------------
# Accuracy helpers
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AccuracyResult:
    """Container for directional-accuracy statistics."""

    correct: int
    total: int
    accuracy_pct: float
    pass_rate: float  # test-level pass rate
    go_threshold: float = 60.0
    no_go_threshold: float = 40.0

    @property
    def decision(self) -> str:
        if self.accuracy_pct >= self.go_threshold:
            return "Go"
        if self.accuracy_pct <= self.no_go_threshold:
            return "No-Go"
        return "Partial"

    @property
    def passed(self) -> bool:
        return self.accuracy_pct >= self.go_threshold


def calculate_directional_accuracy(results: list[bool]) -> AccuracyResult:
    """Return an AccuracyResult from a list of per-scenario pass/fail booleans."""
    correct = sum(results)
    total = len(results)
    accuracy_pct = (correct / total * 100.0) if total else 0.0
    pass_rate = sum(results) / total if total else 0.0
    return AccuracyResult(
        correct=correct,
        total=total,
        accuracy_pct=round(accuracy_pct, 2),
        pass_rate=round(pass_rate, 4),
    )


def bootstrap_confidence_interval(
    values: list[bool],
    n_bootstrap: int = 10_000,
    confidence: float = 0.95,
) -> tuple[float, float, float]:
    """Return (lower, mean, upper) for accuracy using bootstrap resampling.

    Values should be bools (True = correct, False = incorrect).
    """
    import random

    n = len(values)
    if n == 0:
        return (0.0, 0.0, 0.0)

    accs: list[float] = []
    for _ in range(n_bootstrap):
        sample = [values[random.randint(0, n - 1)] for _ in range(n)]
        accs.append(sum(sample) / n * 100.0)

    accs.sort()
    lower_idx = int((1 - confidence) / 2 * n_bootstrap)
    upper_idx = int((1 + confidence) / 2 * n_bootstrap)
    return (
        accs[lower_idx],
        statistics.mean(accs),
        accs[min(upper_idx, n_bootstrap - 1)],
    )


# ---------------------------------------------------------------------------
# Data conversion helpers
# ---------------------------------------------------------------------------


def ohlcv_from_list(ohlcv_list: list[list]) -> list:
    """Convert a list of [ts, o, h, l, c, v] to OHLCVData objects."""
    from src.data_ingestion.ohlcv_fetcher import OHLCVData

    candles = []
    for row in ohlcv_list:
        candles.append(
            OHLCVData(
                timestamp=int(row[0]),
                open_price=float(row[1]),
                high_price=float(row[2]),
                low_price=float(row[3]),
                close_price=float(row[4]),
                volume=float(row[5]),
            )
        )
    return candles


def trades_from_list(trade_list: list[list]) -> list:
    """Convert a list of [id, price, qty, ts, is_buyer_maker] to Trade objects."""
    from datetime import UTC, datetime

    from src.market_analysis.cvd.cvd_calculator import Trade

    trades = []
    for row in trade_list:
        trades.append(
            Trade(
                trade_id=int(row[0]),
                price=float(row[1]),
                quantity=float(row[2]),
                timestamp=datetime.fromtimestamp(int(row[3]), tz=UTC),
                is_buyer_maker=bool(row[4]),
            )
        )
    return trades


def candle_objects_from_list(candle_list: list[list]) -> list:
    """Convert a list of [ts, o, h, l, c, v] to candle-like objects.

    Returns objects with close_price, open_price, high_price, low_price, timestamp
    attributes for FVG and Order Block detectors.
    """
    from src.data_ingestion.ohlcv_fetcher import OHLCVData

    candles = []
    for row in candle_list:
        candles.append(
            OHLCVData(
                timestamp=int(row[0]),
                open_price=float(row[1]),
                high_price=float(row[2]),
                low_price=float(row[3]),
                close_price=float(row[4]),
                volume=float(row[5]),
            )
        )
    return candles


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def bos_choch_scenarios() -> list[dict[str, Any]]:
    """Load BOS/CHoCH test scenarios."""
    return _load_scenarios("bos_choch_scenarios.json")


@pytest.fixture()
def cvd_scenarios() -> list[dict[str, Any]]:
    """Load CVD test scenarios."""
    return _load_scenarios("cvd_scenarios.json")


@pytest.fixture()
def fvg_scenarios() -> list[dict[str, Any]]:
    """Load FVG test scenarios."""
    return _load_scenarios("fvg_scenarios.json")


@pytest.fixture()
def order_block_scenarios() -> list[dict[str, Any]]:
    """Load Order Block test scenarios."""
    return _load_scenarios("order_block_scenarios.json")
