#!/usr/bin/env python3
"""Verify Discord trading notifications are working correctly.

This script tests that trade notifications are sent to the correct Discord channel.
Run this after updating DISCORD_TRADING_WEBHOOK_URL to point to #trading channel.

Usage:
    source .envrc
    python3 scripts/verify_discord_trading.py

Returns:
    Exit code 0 if all notifications sent successfully
    Exit code 1 if any notification failed
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

# Add src to path
sys.path.insert(0, "/home/tacopants/projects/ChiseAI")
sys.path.insert(0, "/home/tacopants/projects/ChiseAI/src")

from discord_alerts.trade_notifier import TradeNotifier
from execution.alerts.integration import ExecutionAlertIntegration
from ml.models.signal_outcome import SignalOutcome, SignalOutcomeStatus


async def verify_discord_trading() -> dict:
    """Verify Discord trading notifications are working.

    Returns:
        Dictionary with test results and message IDs
    """
    print("=" * 60)
    print("Discord Trading Notifications Verification")
    print("=" * 60)

    results: dict[str, dict[str, Any]] = {
        "open": {"success": False, "message_id": None, "error": None},
        "close": {"success": False, "message_id": None, "error": None},
        "recap": {"success": False, "message_id": None, "error": None},
    }

    # Create the alert integration
    alerts = ExecutionAlertIntegration()

    # Test TradeNotifier directly first
    print("\n1. Checking configuration...")
    notifier = TradeNotifier()
    print(f"   Webhook URL configured: {notifier.webhook_url is not None}")
    print(f"   Trading channel ID: {notifier.trading_channel_id}")
    print("   Expected channel ID: 1444447985378398459 (#trading)")

    if notifier.trading_channel_id != "1444447985378398459":
        print("   ⚠️  WARNING: Trading channel ID doesn't match #trading!")

    # Health check
    print("\n2. Running health check...")
    health = await alerts.health_check()
    print(f"   Alerts enabled: {health['enabled']}")
    print(f"   Current stats: {health['stats']}")

    # Create test SignalOutcome for OPEN
    print("\n3. Sending OPEN notification...")
    outcome_open = SignalOutcome(
        outcome_id=uuid4(),
        signal_id=uuid4(),
        order_id=f"verify-open-{datetime.now(UTC).strftime('%H%M%S')}",
        symbol="BTCUSDT",
        side="Buy",
        direction="LONG",
        fill_price=Decimal("65000.00"),
        fill_quantity=Decimal("0.1"),
        entry_price=Decimal("65000.00"),
        position_size=Decimal("0.1"),
        status=SignalOutcomeStatus.FILLED,
        entry_time=datetime.now(UTC),
        is_test=True,
        metadata={"verification_test": True, "confidence": 0.85},
    )

    try:
        open_result = await alerts.on_trade_opened(outcome_open)
        results["open"]["success"] = open_result.get("sent", False)
        results["open"]["message_id"] = open_result.get("message_id")
        results["open"]["error"] = open_result.get("error")

        if results["open"]["success"]:
            print(f"   ✅ OPEN sent: message_id={results['open']['message_id']}")
        else:
            print(f"   ❌ OPEN failed: {results['open']['error']}")
    except Exception as e:
        print(f"   ❌ OPEN error: {e}")
        results["open"]["error"] = str(e)

    # Wait between messages
    await asyncio.sleep(2)

    # Create test SignalOutcome for CLOSE
    print("\n4. Sending CLOSE notification...")
    outcome_close = SignalOutcome(
        outcome_id=uuid4(),
        signal_id=uuid4(),
        order_id=f"verify-close-{datetime.now(UTC).strftime('%H%M%S')}",
        symbol="BTCUSDT",
        side="Sell",
        direction="LONG",
        fill_price=Decimal("65500.00"),
        fill_quantity=Decimal("0.1"),
        entry_price=Decimal("65000.00"),
        position_size=Decimal("0.1"),
        status=SignalOutcomeStatus.CLOSED,
        pnl=Decimal("50.00"),
        exit_price=Decimal("65500.00"),
        entry_time=datetime.now(UTC),
        exit_time=datetime.now(UTC),
        is_test=True,
        metadata={"verification_test": True, "confidence": 0.85},
    )

    try:
        close_result = await alerts.on_trade_closed(outcome_close, 50.0)
        results["close"]["success"] = close_result.get("sent", False)
        results["close"]["message_id"] = close_result.get("message_id")
        results["close"]["error"] = close_result.get("error")

        if results["close"]["success"]:
            print(f"   ✅ CLOSE sent: message_id={results['close']['message_id']}")
        else:
            print(f"   ❌ CLOSE failed: {results['close']['error']}")
    except Exception as e:
        print(f"   ❌ CLOSE error: {e}")
        results["close"]["error"] = str(e)

    # Wait between messages
    await asyncio.sleep(2)

    # Test RECAP notification
    print("\n5. Sending RECAP notification...")
    try:
        summary = {
            "total_trades": 3,
            "winning_trades": 2,
            "losing_trades": 1,
            "total_pnl": 125.50,
            "win_rate": 66.7,
        }
        recap_result = await alerts.send_recap("Verification", summary)
        results["recap"]["success"] = recap_result.get("sent", False)
        results["recap"]["message_id"] = recap_result.get("message_id")
        results["recap"]["error"] = recap_result.get("error")

        if results["recap"]["success"]:
            print(f"   ✅ RECAP sent: message_id={results['recap']['message_id']}")
        else:
            print(f"   ❌ RECAP failed: {results['recap']['error']}")
    except Exception as e:
        print(f"   ❌ RECAP error: {e}")
        results["recap"]["error"] = str(e)

    # Summary
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)

    all_passed = all(r["success"] for r in results.values())

    for msg_type, result in results.items():
        status = "✅ PASS" if result["success"] else "❌ FAIL"
        print(f"\n{msg_type.upper()}: {status}")
        if result["message_id"]:
            print(f"  Message ID: {result['message_id']}")
        if result["error"]:
            print(f"  Error: {result['error']}")

    print("\n" + "=" * 60)
    if all_passed:
        print("✅ ALL TESTS PASSED")
        print("\nNext steps:")
        print("1. Check #trading channel for the test messages")
        print("2. Verify message IDs match those shown above")
        print("3. Confirm embeds display correctly")
    else:
        print("❌ SOME TESTS FAILED")
        print("\nTroubleshooting:")
        print("1. Verify DISCORD_TRADING_WEBHOOK_URL is set correctly")
        print("2. Check webhook points to #trading channel (ID: 1444447985378398459)")
        print("3. See docs/discord-g5-fix.md for detailed fix instructions")
    print("=" * 60)

    return results


def main():
    """Main entry point."""
    results = asyncio.run(verify_discord_trading())

    # Exit with appropriate code
    all_passed = all(r["success"] for r in results.values())
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
