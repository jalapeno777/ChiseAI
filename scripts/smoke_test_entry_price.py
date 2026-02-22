#!/usr/bin/env python3
"""Smoke test for entry_price fix (BURNIN-001).

Verifies that signal generation includes entry_price in metadata,
which is critical for risk enforcer position sizing.
"""

import sys
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

# Add src to path
sys.path.insert(0, "/home/tacopants/projects/ChiseAI/src")

from signal_generation.signal_generator import (
    SignalGenerationConfig,
    SignalGenerator,
)


def smoke_test_entry_price_fix():
    """Run smoke test for entry_price fix."""
    print("=" * 60)
    print("SMOKE TEST: BURNIN-001 Signal Entry Price Fix")
    print("=" * 60)

    # Mock dependencies
    with (
        patch(
            "signal_generation.signal_generator.SignalGenerator._get_freshness_checker"
        ) as mock_get_checker,
        patch(
            "signal_generation.signal_generator.SignalGenerator._get_scorer"
        ) as mock_get_scorer,
    ):
        # Setup mock freshness checker
        mock_checker = MagicMock()
        mock_checker.check_freshness.return_value = MagicMock(
            is_fresh=True,
            errors=[],
            data_age_seconds=0.0,
        )
        mock_get_checker.return_value = mock_checker

        # Setup mock confluence scorer
        mock_scorer = MagicMock()
        mock_confluence_score = MagicMock()
        mock_confluence_score.direction_str = "LONG"
        mock_confluence_score.confidence = 0.85
        mock_confluence_score.score = 80.0
        mock_confluence_score.contributing_factors = []
        mock_confluence_score.signal_breakdown = {}
        mock_confluence_score.metadata = {"test": "data"}
        mock_confluence_score.multiplier_applied = 1.0
        mock_confluence_score.multiplier_rationale = "test rationale"
        mock_scorer.calculate_score.return_value = mock_confluence_score
        mock_get_scorer.return_value = mock_scorer

        # Create generator
        config = SignalGenerationConfig(enable_freshness_checks=True)
        generator = SignalGenerator(config=config)

        # Create mock OHLCV data
        mock_ohlcv = [MagicMock(timestamp=1000, datetime_utc=datetime.now(UTC))]

        from data_ingestion.timeframe_config import Timeframe

        # Test with current_price provided
        test_price = 65000.50
        signal = generator.generate_signal(
            token="BTC/USDT",
            timeframe=Timeframe.HOUR_1,
            ohlcv_data=mock_ohlcv,
            current_price=test_price,
        )

        # Verify signal structure
        print("\n1. Signal Generated:")
        print(f"   Token: {signal.token}")
        print(f"   Direction: {signal.direction}")
        print(f"   Confidence: {signal.confidence:.2%}")
        print(f"   Status: {signal.status}")

        # Verify metadata contains entry_price
        print("\n2. Metadata Check:")
        if "entry_price" in signal.metadata:
            entry_price = signal.metadata["entry_price"]
            print(f"   ✓ entry_price FOUND: {entry_price}")

            if entry_price == test_price:
                print(f"   ✓ entry_price matches expected: {test_price}")
            else:
                print(
                    f"   ✗ entry_price mismatch! Expected {test_price}, got {entry_price}"
                )
                return False
        else:
            print("   ✗ entry_price MISSING from metadata!")
            print(f"   Available keys: {list(signal.metadata.keys())}")
            return False

        # Test without current_price (should be None)
        print("\n3. Test without current_price:")
        signal_no_price = generator.generate_signal(
            token="ETH/USDT",
            timeframe=Timeframe.HOUR_1,
            ohlcv_data=mock_ohlcv,
            # current_price not provided
        )

        if signal_no_price.metadata.get("entry_price") is None:
            print("   ✓ entry_price is None when not provided")
        else:
            print(
                f"   ✗ entry_price should be None, got: {signal_no_price.metadata.get('entry_price')}"
            )
            return False

        # Verify risk enforcer can read entry_price correctly
        print("\n4. Risk Enforcer Simulation:")
        entry_price_for_risk = signal.metadata.get("entry_price", 0.0)
        if entry_price_for_risk > 0:
            print(f"   ✓ Risk enforcer reads entry_price: {entry_price_for_risk}")
            print("   ✓ Position sizing can proceed correctly")
        else:
            print(
                "   ✗ Risk enforcer would default to 0.0 - position sizing would fail!"
            )
            return False

        print("\n" + "=" * 60)
        print("SMOKE TEST PASSED ✓")
        print("=" * 60)
        print("\nBURNIN-001 fix verified:")
        print("- Signal metadata now includes entry_price")
        print("- Risk enforcer can read entry_price correctly")
        print("- Position sizing will work as expected")
        return True


if __name__ == "__main__":
    success = smoke_test_entry_price_fix()
    sys.exit(0 if success else 1)
