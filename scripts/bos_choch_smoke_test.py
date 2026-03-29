#!/usr/bin/env python3
"""
BOS-CHoCH Smoke Test for all 4 ICT signal generators.

This smoke test exercises:
1. CVD (Cumulative Volume Delta) Calculator
2. FVG (Fair Value Gap) Detector
3. Order Block Detector
4. BOS/CHoCH Classifier

Using real market snapshot data from tests/fixtures/market_snapshots/
"""

import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

# Add project root and src to path
PROJECT_ROOT = Path("/home/tacopants/projects/ChiseAI")
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

from data_ingestion.ohlcv_fetcher import OHLCVData
from market_analysis.cvd.cvd_calculator import CVDCalculator, Trade, TradeDirection
from market_analysis.fvg.fvg_detector import FVGDetector
from market_analysis.order_block.ob_detector import OrderBlockConfig, OrderBlockDetector
from market_analysis.regime import MarketRegimeClassifier
from market_analysis.structure.bos_choch import BOSCHoCHClassifier
from market_analysis.structure.swing_pivot import SwingPivotDetector


def load_snapshot(data_key: str) -> list[OHLCVData]:
    """Load market snapshot from fixtures."""
    PROJECT_ROOT = Path("/home/tacopants/projects/ChiseAI")
    snapshot_path = (
        PROJECT_ROOT / "tests" / "fixtures" / "market_snapshots" / f"{data_key}.json"
    )

    if not snapshot_path.exists():
        raise FileNotFoundError(f"Snapshot not found: {snapshot_path}")

    with open(snapshot_path) as f:
        data = json.load(f)

    candles = data["candles"]
    ohlcv_list = [
        OHLCVData(
            timestamp=i * 60000,  # Sequential timestamps for synthetic data
            open_price=float(c[0]),
            high_price=float(c[1]),
            low_price=float(c[2]),
            close_price=float(c[3]),
            volume=float(c[4]),
        )
        for i, c in enumerate(candles)
    ]
    return ohlcv_list


def generate_synthetic_trades(candles: list[OHLCVData]) -> list[Trade]:
    """Generate synthetic trades from OHLCV candles for CVD testing."""
    trades = []
    trade_id = 0

    for i, candle in enumerate(candles):
        # Generate 2-3 trades per candle
        num_trades = 2 + (i % 2)

        for j in range(num_trades):
            # Alternate buyer/seller initiated based on price movement
            price_change = candle.close_price - candle.open_price
            if price_change > 0:
                # Price went up: mostly buyer-initiated (taker buy)
                is_buyer_maker = j % 3 != 0  # 2/3 buyer-initiated
            else:
                # Price went down: mostly seller-initiated (taker sell)
                is_buyer_maker = j % 3 == 0  # 1/3 buyer-initiated

            trade = Trade(
                trade_id=trade_id,
                price=candle.close_price,
                quantity=candle.volume / 3.0,
                timestamp=candle.datetime_utc,
                is_buyer_maker=is_buyer_maker,
            )
            trades.append(trade)
            trade_id += 1

    return trades


def test_cvd(candles: list[OHLCVData]) -> dict:
    """Test CVD Calculator."""
    print("\n" + "=" * 60)
    print("TESTING: CVD (Cumulative Volume Delta) Calculator")
    print("=" * 60)

    try:
        calculator = CVDCalculator()
        trades = generate_synthetic_trades(candles[:50])  # Use first 50 candles

        result = calculator.calculate_from_trades(trades)

        print("  ✓ CVD Calculator instantiated successfully")
        print(f"  ✓ Processed {result.trade_count} trades")
        print(f"  ✓ Buy Volume: {result.buy_volume:,.2f}")
        print(f"  ✓ Sell Volume: {result.sell_volume:,.2f}")
        print(f"  ✓ Net Volume: {result.net_volume:,.2f}")
        print(f"  ✓ CVD Values generated: {len(result.cvd_values)} points")

        return {
            "status": "PASS",
            "generator": "CVDCalculator",
            "trade_count": result.trade_count,
            "buy_volume": result.buy_volume,
            "sell_volume": result.sell_volume,
            "net_volume": result.net_volume,
            "cvd_points": len(result.cvd_values),
        }
    except Exception as e:
        print(f"  ✗ CVD Test FAILED: {e}")
        return {"status": "FAIL", "generator": "CVDCalculator", "error": str(e)}


def test_fvg(candles: list[OHLCVData]) -> dict:
    """Test FVG Detector."""
    print("\n" + "=" * 60)
    print("TESTING: FVG (Fair Value Gap) Detector")
    print("=" * 60)

    try:
        detector = FVGDetector()

        # Use enough candles for FVG detection (needs 3+ candles)
        _result = detector.detect(candles[:100])

        # Access detected FVGs via the property
        detected_fvgs = detector.detected_fvgs

        print("  ✓ FVG Detector instantiated successfully")
        print(f"  ✓ Detection completed on {len(candles[:100])} candles")
        print(f"  ✓ FVGs detected: {len(detected_fvgs)}")

        if detected_fvgs:
            for i, fvg in enumerate(detected_fvgs[:3]):  # Show first 3
                print(
                    f"    - FVG {i + 1}: {fvg.direction.value}, "
                    f"High={fvg.high:.2f}, Low={fvg.low:.2f}, "
                    f"Mitigation={fvg.mitigation.value}"
                )

        return {
            "status": "PASS",
            "generator": "FVGDetector",
            "candles_processed": len(candles[:100]),
            "fvgs_detected": len(detected_fvgs),
        }
    except Exception as e:
        print(f"  ✗ FVG Test FAILED: {e}")
        import traceback

        traceback.print_exc()
        return {"status": "FAIL", "generator": "FVGDetector", "error": str(e)}


def test_order_block(candles: list[OHLCVData]) -> dict:
    """Test Order Block Detector."""
    print("\n" + "=" * 60)
    print("TESTING: Order Block Detector")
    print("=" * 60)

    try:
        config = OrderBlockConfig()
        detector = OrderBlockDetector(config=config)

        # Get regime classification
        regime_classifier = MarketRegimeClassifier()
        regime = regime_classifier.classify(candles[:50])

        result = detector.detect(candles[:100], regime=regime)

        print("  ✓ Order Block Detector instantiated successfully")
        print(f"  ✓ Regime: {regime.regime.value if regime else 'None'}")
        print(f"  ✓ Detection completed on {len(candles[:100])} candles")
        print(f"  ✓ Order Blocks detected: {len(result)}")

        if result:
            for i, ob in enumerate(result[:3]):  # Show first 3
                print(
                    f"    - OB {i + 1}: {ob.polarity.value}, "
                    f"Zone=[{ob.zone.low:.2f}-{ob.zone.high:.2f}], "
                    f"Strength={ob.strength_score:.2f}"
                )

        return {
            "status": "PASS",
            "generator": "OrderBlockDetector",
            "regime": regime.regime.value if regime else "unknown",
            "candles_processed": len(candles[:100]),
            "obs_detected": len(result),
        }
    except Exception as e:
        print(f"  ✗ Order Block Test FAILED: {e}")
        return {"status": "FAIL", "generator": "OrderBlockDetector", "error": str(e)}


def test_bos_choch(candles: list[OHLCVData]) -> dict:
    """Test BOS/CHoCH Classifier."""
    print("\n" + "=" * 60)
    print("TESTING: BOS/CHoCH Classifier")
    print("=" * 60)

    try:
        # First detect swing pivots
        pivot_detector = SwingPivotDetector(window_size=5)
        pivot_result = pivot_detector.detect(candles[:100])

        print("  ✓ Swing Pivot Detector instantiated")
        print(f"  ✓ Pivots detected: {len(pivot_result.pivots)}")

        # Now classify BOS/CHoCH
        classifier = BOSCHoCHClassifier()
        result = classifier.classify(pivot_result, candles[:100])

        print("  ✓ BOSCHoCH Classifier instantiated successfully")
        print("  ✓ Classification completed")
        print(f"  ✓ Total Events: {len(result.events)}")
        print(f"  ✓ Bullish BOS: {len(result.bullish_bos_events)}")
        print(f"  ✓ Bearish BOS: {len(result.bearish_bos_events)}")
        print(f"  ✓ Bullish CHoCH: {len(result.bullish_choch_events)}")
        print(f"  ✓ Bearish CHoCH: {len(result.bearish_choch_events)}")
        print(f"  ✓ Last BOS Direction: {result.last_bos_direction}")

        if result.events:
            latest = result.events[-1]
            print(
                f"  ✓ Latest Event: {latest.event_type.value}, "
                f"Price={latest.break_price:.2f}"
            )

        return {
            "status": "PASS",
            "generator": "BOSCHoCHClassifier",
            "pivots_detected": len(pivot_result.pivots),
            "total_events": len(result.events),
            "bullish_bos": len(result.bullish_bos_events),
            "bearish_bos": len(result.bearish_bos_events),
            "bullish_choch": len(result.bullish_choch_events),
            "bearish_choch": len(result.bearish_choch_events),
            "last_bos_direction": result.last_bos_direction,
        }
    except Exception as e:
        print(f"  ✗ BOS/CHoCH Test FAILED: {e}")
        import traceback

        traceback.print_exc()
        return {"status": "FAIL", "generator": "BOSCHoCHClassifier", "error": str(e)}


def test_confluence_scoring() -> dict:
    """Test Confluence Scorer (bonus - tests integration)."""
    print("\n" + "=" * 60)
    print("TESTING: Confluence Scorer (Integration)")
    print("=" * 60)

    try:
        from data_ingestion.timeframe_config import Timeframe
        from market_analysis.confluence.scorer import ConfluenceScorer
        from market_analysis.confluence.signal_aggregator import SignalAggregator
        from market_analysis.indicators.calculator import IndicatorCalculator

        # Load test data
        candles = load_snapshot("btc_usdt_1h")

        # Calculate indicators - use Timeframe enum
        calc = IndicatorCalculator()
        timeframe = Timeframe.HOUR_1
        indicators = calc.calculate_all(candles, timeframe)

        # Aggregate signals
        aggregator = SignalAggregator()
        ts = int(datetime.now(UTC).timestamp() * 1000)

        signals_list = []
        if indicators.rsi is not None:
            rsi_signal = aggregator.from_rsi(indicators.rsi, timeframe, timestamp=ts)
            if rsi_signal:
                signals_list.append(rsi_signal)

        if indicators.macd is not None:
            macd_signal = aggregator.from_macd(indicators.macd, timeframe, timestamp=ts)
            if macd_signal:
                signals_list.append(macd_signal)

        aggregated = aggregator.aggregate(signals_list, timestamp=ts)

        # Calculate confluence score
        scorer = ConfluenceScorer()
        score = scorer.calculate_score(aggregated, ts)

        print("  ✓ ConfluenceScorer instantiated successfully")
        print(f"  ✓ Score calculated: {score.score:.4f}")
        print(f"  ✓ Direction: {score.direction_str}")
        print(f"  ✓ Confidence: {score.confidence:.2%}")
        print(f"  ✓ Contributing Factors: {len(score.contributing_factors)}")

        return {
            "status": "PASS",
            "generator": "ConfluenceScorer",
            "score": score.score,
            "direction": score.direction_str,
            "confidence": score.confidence,
            "factors": len(score.contributing_factors),
        }
    except Exception as e:
        print(f"  ✗ Confluence Scoring Test FAILED: {e}")
        import traceback

        traceback.print_exc()
        return {"status": "FAIL", "generator": "ConfluenceScorer", "error": str(e)}


def main():
    """Run all smoke tests."""
    print("=" * 60)
    print("ICT SIGNAL GENERATORS SMOKE TEST")
    print(f"Timestamp: {datetime.now(UTC).isoformat()}")
    print("=" * 60)

    # Load test data
    print("\n[SETUP] Loading market snapshot data...")
    try:
        candles = load_snapshot("btc_usdt_1h")
        print(f"  ✓ Loaded {len(candles)} candles from btc_usdt_1h.json")
    except Exception as e:
        print(f"  ✗ Failed to load snapshot: {e}")
        return 1

    results = []

    # Run all generator tests
    results.append(("CVD", test_cvd(candles)))
    results.append(("FVG", test_fvg(candles)))
    results.append(("OrderBlock", test_order_block(candles)))
    results.append(("BOS/CHoCH", test_bos_choch(candles)))
    results.append(("ConfluenceScorer", test_confluence_scoring()))

    # Summary
    print("\n" + "=" * 60)
    print("SMOKE TEST SUMMARY")
    print("=" * 60)

    all_passed = True
    for name, result in results:
        status = result.get("status", "UNKNOWN")
        status_symbol = "✓" if status == "PASS" else "✗"
        print(f"  {status_symbol} {name}: {status}")
        if status != "PASS":
            all_passed = False
            print(f"      Error: {result.get('error', 'Unknown error')}")

    print("\n" + "=" * 60)
    if all_passed:
        print("OVERALL RESULT: ALL TESTS PASSED ✓")
        print("=" * 60)
        return 0
    else:
        print("OVERALL RESULT: SOME TESTS FAILED ✗")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
