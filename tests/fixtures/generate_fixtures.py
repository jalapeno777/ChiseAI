"""Script to generate market snapshot and indicator expectation JSON files.

Run this from the worktree root to create all fixture data files.
This script uses the actual indicator implementations to produce
validated expected outputs.
"""

import json
import sys
from pathlib import Path

import numpy as np

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from data_ingestion.ohlcv_fetcher import OHLCVData
from market_analysis.indicators.bollinger_bands import BollingerBands
from market_analysis.indicators.macd import MACD
from market_analysis.indicators.rsi import RSI
from market_analysis.indicators.volume_profile import VolumeProfile
from portfolio_risk.stop_loss.atr_indicator import ATR

# Snapshot configs: (symbol, timeframe, num_candles, base_price, seed)
SNAPSHOT_CONFIGS = [
    ("BTC/USDT", "1m", 100, 43250.0, 1001),
    ("BTC/USDT", "5m", 100, 43250.0, 1002),
    ("BTC/USDT", "1h", 100, 43250.0, 1003),
    ("ETH/USDT", "1m", 100, 3200.0, 2001),
    ("ETH/USDT", "5m", 100, 3200.0, 2002),
    ("ETH/USDT", "1h", 100, 3200.0, 2003),
]

# Interval mapping
INTERVAL_MS = {"1m": 60000, "5m": 300000, "1h": 3600000}


def _generate_candle_data(
    num_candles: int, base_price: float, seed: int, interval_ms: int
) -> list[list[float]]:
    """Generate realistic candle data as [o, h, l, c, v] arrays."""
    rng = np.random.default_rng(seed)
    price = base_price
    candles = []

    for _ in range(num_candles):
        # Trending up with noise
        drift = rng.normal(0.0003, 0.008) * price
        price = max(price * 0.8, price + drift)

        o = price * (1 + rng.normal(0, 0.001))
        c = price
        h = max(o, c) * (1 + abs(rng.normal(0, 0.003)))
        l = min(o, c) * (1 - abs(rng.normal(0, 0.003)))

        vol = rng.lognormal(3.0, 0.8)

        candles.append(
            [
                round(o, 2),
                round(h, 2),
                round(l, 2),
                round(c, 2),
                round(vol, 4),
            ]
        )

    return candles


def candles_to_ohlcv(
    candle_data: list[list[float]], start_ts: int, interval_ms: int
) -> list[OHLCVData]:
    """Convert candle arrays to OHLCVData."""
    result = []
    for i, candle in enumerate(candle_data):
        result.append(
            OHLCVData(
                timestamp=start_ts + i * interval_ms,
                open_price=candle[0],
                high_price=candle[1],
                low_price=candle[2],
                close_price=candle[3],
                volume=candle[4],
            )
        )
    return result


def generate_snapshots(output_dir: Path) -> dict[str, list[OHLCVData]]:
    """Generate all market snapshot JSON files."""
    all_data = {}
    for symbol, tf, num, base, seed in SNAPSHOT_CONFIGS:
        interval_ms = INTERVAL_MS[tf]
        candle_data = _generate_candle_data(num, base, seed, interval_ms)
        ohlcv = candles_to_ohlcv(candle_data, 1700000000000, interval_ms)

        # Build JSON snapshot
        symbol_slug = symbol.replace("/", "_").lower()
        filename = f"{symbol_slug}_{tf}.json"
        snapshot = {
            "symbol": symbol,
            "timeframe": tf,
            "generated_at": "2026-03-20T00:00:00Z",
            "description": (
                f"Synthetic {symbol} {tf} OHLCV snapshot. "
                f"Seed={seed}, {num} candles for indicator validation."
            ),
            "candles": candle_data,
        }

        filepath = output_dir / filename
        filepath.write_text(json.dumps(snapshot, indent=2))
        key = f"{symbol_slug}_{tf}"
        all_data[key] = ohlcv
        print(f"  Generated: {filepath.name}")

    return all_data


def _ndarray_to_list(arr: np.ndarray) -> list:
    """Convert numpy array to JSON-serializable list, handling NaN."""
    result = []
    for v in arr.flat:
        if isinstance(v, (np.floating, float)):
            if np.isnan(v):
                result.append(None)
            else:
                result.append(round(float(v), 8))
        elif isinstance(v, np.bool_):
            result.append(bool(v))
        else:
            result.append(v)
    return result


def _enum_to_str(val) -> str:
    """Convert enum to its string value."""
    if hasattr(val, "value"):
        return val.value
    return str(val)


def generate_expectations(
    all_data: dict[str, list[OHLCVData]], output_dir: Path
) -> None:
    """Generate indicator expectation JSON files for each snapshot."""
    rsi = RSI(period=14)
    macd = MACD(fast_period=12, slow_period=26, signal_period=9)
    bb = BollingerBands(period=20, num_std_dev=2.0)
    atr = ATR(period=14)
    vp = VolumeProfile(
        lookback_periods=24,
        volume_buckets=12,
        value_area_pct=0.7,
        use_feature_store=False,
    )

    for key, ohlcv in all_data.items():
        expectations = {"data_key": key, "num_candles": len(ohlcv)}

        # RSI (needs >= 15 candles)
        try:
            rsi_result = rsi.calculate(ohlcv)
            expectations["rsi"] = {
                "current": rsi_result.current,
                "is_overbought": rsi_result.is_overbought,
                "is_oversold": rsi_result.is_oversold,
                "last_5_values": _ndarray_to_list(rsi_result.values[-5:]),
            }
        except ValueError as e:
            expectations["rsi"] = {"error": str(e)}

        # MACD (needs >= 35 candles)
        try:
            macd_result = macd.calculate(ohlcv)
            expectations["macd"] = {
                "current_macd": macd_result.current_macd,
                "current_signal": macd_result.current_signal,
                "current_histogram": macd_result.current_histogram,
                "latest_crossover": (_enum_to_str(macd_result.latest_crossover)),
                "last_5_macd": _ndarray_to_list(macd_result.macd_line[-5:]),
                "last_5_signal": _ndarray_to_list(macd_result.signal_line[-5:]),
                "last_5_histogram": _ndarray_to_list(macd_result.histogram[-5:]),
            }
        except ValueError as e:
            expectations["macd"] = {"error": str(e)}

        # Bollinger Bands (needs >= 20 candles)
        try:
            bb_result = bb.calculate(ohlcv)
            expectations["bollinger_bands"] = {
                "current_middle": bb_result.current_middle,
                "current_upper": bb_result.current_upper,
                "current_lower": bb_result.current_lower,
                "current_band_width": bb_result.current_band_width,
                "current_percent_b": bb_result.current_percent_b,
                "last_5_middle": _ndarray_to_list(bb_result.middle_band[-5:]),
                "last_5_upper": _ndarray_to_list(bb_result.upper_band[-5:]),
                "last_5_lower": _ndarray_to_list(bb_result.lower_band[-5:]),
            }
        except ValueError as e:
            expectations["bollinger_bands"] = {"error": str(e)}

        # ATR (needs >= 15 candles)
        try:
            atr_result = atr.calculate(ohlcv)
            expectations["atr"] = {
                "current": atr_result.current,
                "period": atr_result.period,
                "last_5_values": _ndarray_to_list(atr_result.values[-5:]),
            }
        except ValueError as e:
            expectations["atr"] = {"error": str(e)}

        # Volume Profile (needs >= 24 candles)
        try:
            vp_result = vp.compute(ohlcv)
            expectations["volume_profile"] = {
                "poc": round(vp_result.poc, 2),
                "vah": round(vp_result.vah, 2),
                "val": round(vp_result.val, 2),
                "num_bins": len(vp_result.bins),
                "bin_volumes_rounded": _ndarray_to_list(
                    np.round(vp_result.bin_volumes, 4)
                ),
            }
        except ValueError as e:
            expectations["volume_profile"] = {"error": str(e)}

        filepath = output_dir / f"{key}_expectations.json"
        filepath.write_text(json.dumps(expectations, indent=2))
        print(f"  Generated: {filepath.name}")


def main() -> None:
    base_dir = Path(__file__).parent
    snapshots_dir = base_dir / "market_snapshots"
    expectations_dir = base_dir / "indicator_expectations"

    snapshots_dir.mkdir(parents=True, exist_ok=True)
    expectations_dir.mkdir(parents=True, exist_ok=True)

    print("Generating market snapshots...")
    all_data = generate_snapshots(snapshots_dir)

    print("Generating indicator expectations...")
    generate_expectations(all_data, expectations_dir)

    print("Done! All fixture files generated.")


if __name__ == "__main__":
    main()
