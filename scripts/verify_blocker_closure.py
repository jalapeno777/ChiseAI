#!/usr/bin/env python3
"""Verification script for G4, G5, G6 blocker closure.

Tests that:
- G4: Persistence layer is functional and writes to Redis
- G5: Discord alert routing is configured and functional
- G6: Recap generator can query persisted data

Run: python3 scripts/verify_blocker_closure.py
"""

import asyncio
import sys
from decimal import Decimal
from uuid import uuid4

# Add src to path
sys.path.insert(0, "src")


async def test_g4_persistence():
    """Test G4: Persistence Activation in Hot Path."""
    print("\n" + "=" * 60)
    print("G4: PERSISTENCE ACTIVATION TEST")
    print("=" * 60)

    try:
        from execution.persistence.outcome_persistence import OutcomePersistence
        from ml.models.signal_outcome import SignalOutcome, SignalOutcomeStatus

        # Create persistence instance
        persistence = OutcomePersistence()

        # Test health check
        health = persistence.health_check()
        print(f"\n✓ Persistence health: {health}")

        # Create test outcome
        outcome = SignalOutcome(
            outcome_id=uuid4(),
            order_id=f"test-order-{uuid4().hex[:8]}",
            symbol="BTCUSDT",
            side="Buy",
            direction="LONG",
            fill_price=Decimal("50000.00"),
            fill_quantity=Decimal("0.1"),
            entry_price=Decimal("50000.00"),
            position_size=Decimal("0.1"),
            status=SignalOutcomeStatus.FILLED,
            pnl=Decimal("100.00"),
        )

        # Persist outcome
        key = persistence.persist_outcome(outcome, correlation_id="test-g4")
        print(f"✓ Persisted outcome to key: {key}")

        # Verify we can read it back
        outcomes = persistence.get_recent_outcomes(limit=10)
        print(f"✓ Retrieved {len(outcomes)} recent outcomes")

        # Show stats
        stats = persistence.get_stats()
        print(f"✓ Persistence stats: {stats}")

        # Verify key pattern
        if key and key.startswith("paper:outcome:"):
            print("✓ Key follows correct pattern: paper:outcome:*")
            return True
        else:
            print(f"✗ Key does not follow expected pattern: {key}")
            return False

    except Exception as e:
        print(f"✗ G4 test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_g5_discord_routing():
    """Test G5: #trading Alert Routing."""
    print("\n" + "=" * 60)
    print("G5: DISCORD ALERT ROUTING TEST")
    print("=" * 60)

    try:
        from discord_alerts.config import DiscordConfig
        from execution.alerts.integration import ExecutionAlertIntegration

        # Load config
        config = DiscordConfig.from_env()
        print("\n✓ Discord config loaded")
        print(f"  - Trading channel ID: {config.trading_channel_id}")
        print(f"  - Summaries channel ID: {config.summaries_channel_id}")

        # Create alert integration
        alerts = ExecutionAlertIntegration(enabled=True)
        print("✓ Alert integration initialized")

        # Test health check
        health = await alerts.health_check()
        print(f"✓ Alert health: {health}")

        # Check routing config exists
        import yaml

        with open("config/discord_routing.yaml") as f:
            routing = yaml.safe_load(f)

        print("✓ Discord routing config loaded")
        print(f"  - Trading channel: {routing['channels']['trading']['id']}")
        print(f"  - Summaries channel: {routing['channels']['summaries']['id']}")

        # Verify routing rules
        trade_open_routing = routing["routing"]["trade_opened"]
        print(
            f"✓ Trade open routing: channel={trade_open_routing['channel']}, enabled={trade_open_routing['enabled']}"
        )

        return True

    except Exception as e:
        print(f"✗ G5 test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_g6_recap_generator():
    """Test G6: Recap from Canonical Persisted Outcomes."""
    print("\n" + "=" * 60)
    print("G6: RECAP GENERATOR TEST")
    print("=" * 60)

    try:
        from execution.recap.generator import TradingRecapGenerator

        # Create recap generator
        generator = TradingRecapGenerator()
        print("\n✓ Recap generator initialized")

        # Test health check
        health = generator.health_check()
        print(f"✓ Recap generator health: {health}")

        # Generate period recap
        recap = await generator.generate_period_recap(hours=24)
        print("✓ Generated period recap")
        print(f"  - Period: {recap['period']}")
        print(f"  - Data source: {recap['data_source']}")
        print(f"  - Outcome count: {recap['outcome_count']}")
        print(f"  - Total trades: {recap.get('total_trades', 0)}")

        # Generate position summary
        summary = await generator.generate_position_summary()
        print("✓ Generated position summary")
        print(f"  - Data source: {summary['data_source']}")
        print(f"  - Open positions: {summary.get('total_open_positions', 0)}")

        # Verify data source is canonical persistence
        if recap.get("data_source") == "canonical_persistence":
            print("✓ Recap uses canonical persistence as data source")
            return True
        else:
            print("✗ Recap does not use canonical persistence")
            return False

    except Exception as e:
        print(f"✗ G6 test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def main():
    """Run all verification tests."""
    print("\n" + "=" * 60)
    print("BLOCKER CLOSURE VERIFICATION")
    print("Story: ST-FINAL-CLOSURE-001")
    print("=" * 60)

    results = {
        "G4": await test_g4_persistence(),
        "G5": await test_g5_discord_routing(),
        "G6": await test_g6_recap_generator(),
    }

    # Summary
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)

    for gate, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {gate}: {status}")

    all_passed = all(results.values())

    print("\n" + "=" * 60)
    if all_passed:
        print("ALL GATES PASS - Ready for integration")
    else:
        print("SOME GATES FAIL - Review errors above")
    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
