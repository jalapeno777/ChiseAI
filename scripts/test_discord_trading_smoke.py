#!/usr/bin/env python3
"""Discord Trading Webhook Smoke Tests for DISCORD-TRADING-001.

Tests:
1. TEST Open Trade Notification with [TEST] prefix and 🧪 emoji
2. TEST Close Trade Notification with duration field
3. Development webhook fallback verification

Output: Message IDs, timestamps, and verification status.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

# Bootstrap environment first (must be before any env access)
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from config.bootstrap import bootstrap

bootstrap(load_env=True)

# Import after bootstrap
import aiohttp  # noqa: E402

# Import trade notifier components
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.discord_alerts.trade_notifier import TradeNotifier  # noqa: E402
from src.ml.models.signal_outcome import SignalOutcome, SignalOutcomeStatus, OutcomeType  # noqa: E402


class DiscordTradingSmokeTester:
    """Smoke test Discord trading webhook implementation."""

    def __init__(self) -> None:
        """Initialize with environment configuration."""
        self.trading_webhook_url = os.getenv("DISCORD_TRADING_WEBHOOK_URL")
        self.dev_webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
        self.test_results: list[dict[str, Any]] = []

    def verify_environment(self) -> dict[str, Any]:
        """Verify environment variables are configured.

        Returns:
            Dictionary with environment verification results
        """
        print("=" * 60)
        print("ENVIRONMENT VERIFICATION")
        print("=" * 60)

        result = {
            "trading_webhook_configured": bool(self.trading_webhook_url),
            "dev_webhook_configured": bool(self.dev_webhook_url),
            "trading_webhook_url": self.trading_webhook_url[:50] + "..."
            if self.trading_webhook_url
            else None,
            "dev_webhook_url": self.dev_webhook_url[:50] + "..."
            if self.dev_webhook_url
            else None,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        if self.trading_webhook_url:
            print(f"✓ DISCORD_TRADING_WEBHOOK_URL: {result['trading_webhook_url']}")
        else:
            print("✗ DISCORD_TRADING_WEBHOOK_URL: NOT SET")

        if self.dev_webhook_url:
            print(f"✓ DISCORD_WEBHOOK_URL: {result['dev_webhook_url']}")
        else:
            print("✗ DISCORD_WEBHOOK_URL: NOT SET")

        print()
        return result

    async def test_open_notification(self) -> dict[str, Any]:
        """Test 1: Send TEST open trade notification.

        Returns:
            Test result dictionary
        """
        print("=" * 60)
        print("TEST 1: TEST Open Trade Notification")
        print("=" * 60)

        result = {
            "test_name": "TEST Open Trade Notification",
            "message_id": None,
            "timestamp": None,
            "status": "failed",
            "error": None,
            "verification": {
                "test_prefix_in_title": False,
                "test_emoji_in_footer": False,
            },
        }

        if not self.trading_webhook_url:
            result["error"] = "DISCORD_TRADING_WEBHOOK_URL not configured"
            result["status"] = "skipped"
            print("Status: ⚠ SKIPPED (no trading webhook configured)")
            print()
            return result

        try:
            # Create notifier (will use DISCORD_TRADING_WEBHOOK_URL)
            notifier = TradeNotifier()

            # Create test trade outcome with is_test=True
            outcome = SignalOutcome(
                outcome_id=uuid.uuid4(),
                signal_id=uuid.uuid4(),
                order_id="test-order-smoke-open",
                symbol="BTCUSDT",
                token="BTC",
                side="Buy",
                direction="LONG",
                fill_price=Decimal("50000.00"),
                fill_quantity=Decimal("0.1"),
                fill_timestamp=datetime.now(UTC),
                outcome_type=OutcomeType.TP_HIT,
                pnl=Decimal("100.00"),
                fee=Decimal("5.00"),
                status=SignalOutcomeStatus.FILLED,
                entry_price=Decimal("49000.00"),
                exit_price=Decimal("50000.00"),
                entry_time=datetime.now(UTC) - timedelta(hours=2),
                exit_time=datetime.now(UTC),
                leverage=Decimal("2.0"),
                entry_reason="signal_trigger",
                position_size=Decimal("0.1"),
                is_test=True,  # Mark as test trade
            )

            # Send open notification
            open_result = await notifier.send_trade_open_notification(outcome)

            result["status"] = "delivered" if open_result.success else "failed"
            result["message_id"] = open_result.message_id
            result["timestamp"] = (
                open_result.timestamp.isoformat() if open_result.timestamp else None
            )
            result["error"] = open_result.error

            # Build embed to verify content
            embed = notifier._build_open_embed(outcome)
            result["verification"]["test_prefix_in_title"] = "[TEST]" in embed.get(
                "title", ""
            )
            result["verification"]["test_emoji_in_footer"] = "🧪" in embed.get(
                "footer", {}
            ).get("text", "")

            if open_result.success:
                print(f"✓ Notification delivered")
                print(f"  Message ID: {open_result.message_id}")
                print(f"  Timestamp: {result['timestamp']}")
                print(f"  Title: {embed.get('title')}")
                print(
                    f"  [TEST] prefix: {'✓' if result['verification']['test_prefix_in_title'] else '✗'}"
                )
                print(
                    f"  🧪 emoji in footer: {'✓' if result['verification']['test_emoji_in_footer'] else '✗'}"
                )
            else:
                print(f"✗ Notification failed: {open_result.error}")

            await notifier.close()

        except Exception as e:
            result["error"] = str(e)
            result["status"] = "error"
            print(f"✗ ERROR: {e}")
            import traceback

            traceback.print_exc()

        print()
        self.test_results.append(result)
        return result

    async def test_close_notification(self) -> dict[str, Any]:
        """Test 2: Send TEST close trade notification with duration.

        Returns:
            Test result dictionary
        """
        print("=" * 60)
        print("TEST 2: TEST Close Trade Notification")
        print("=" * 60)

        result = {
            "test_name": "TEST Close Trade Notification",
            "message_id": None,
            "timestamp": None,
            "status": "failed",
            "error": None,
            "verification": {
                "test_prefix_in_title": False,
                "test_emoji_in_footer": False,
                "duration_field_present": False,
            },
        }

        if not self.trading_webhook_url:
            result["error"] = "DISCORD_TRADING_WEBHOOK_URL not configured"
            result["status"] = "skipped"
            print("Status: ⚠ SKIPPED (no trading webhook configured)")
            print()
            return result

        try:
            # Create notifier (will use DISCORD_TRADING_WEBHOOK_URL)
            notifier = TradeNotifier()

            # Create test trade outcome with is_test=True
            entry_time = datetime.now(UTC) - timedelta(hours=2, minutes=15)
            exit_time = datetime.now(UTC)

            outcome = SignalOutcome(
                outcome_id=uuid.uuid4(),
                signal_id=uuid.uuid4(),
                order_id="test-order-smoke-close",
                symbol="ETHUSDT",
                token="ETH",
                side="Sell",
                direction="SHORT",
                fill_price=Decimal("3000.00"),
                fill_quantity=Decimal("1.5"),
                fill_timestamp=exit_time,
                outcome_type=OutcomeType.TP_HIT,
                pnl=Decimal("150.00"),
                fee=Decimal("7.50"),
                status=SignalOutcomeStatus.CLOSED,
                entry_price=Decimal("3100.00"),
                exit_price=Decimal("3000.00"),
                entry_time=entry_time,
                exit_time=exit_time,
                leverage=Decimal("3.0"),
                entry_reason="signal_trigger",
                position_size=Decimal("1.5"),
                is_test=True,  # Mark as test trade
            )

            # Send close notification
            close_result = await notifier.send_trade_close_notification(outcome)

            result["status"] = "delivered" if close_result.success else "failed"
            result["message_id"] = close_result.message_id
            result["timestamp"] = (
                close_result.timestamp.isoformat() if close_result.timestamp else None
            )
            result["error"] = close_result.error

            # Build embed to verify content
            embed = notifier._build_close_embed(outcome)
            result["verification"]["test_prefix_in_title"] = "[TEST]" in embed.get(
                "title", ""
            )
            result["verification"]["test_emoji_in_footer"] = "🧪" in embed.get(
                "footer", {}
            ).get("text", "")

            # Check for duration field
            fields = embed.get("fields", [])
            duration_field = next(
                (f for f in fields if f.get("name") == "⏱️ Duration"), None
            )
            result["verification"]["duration_field_present"] = (
                duration_field is not None
            )

            if close_result.success:
                print(f"✓ Notification delivered")
                print(f"  Message ID: {close_result.message_id}")
                print(f"  Timestamp: {result['timestamp']}")
                print(f"  Title: {embed.get('title')}")
                print(
                    f"  [TEST] prefix: {'✓' if result['verification']['test_prefix_in_title'] else '✗'}"
                )
                print(
                    f"  🧪 emoji in footer: {'✓' if result['verification']['test_emoji_in_footer'] else '✗'}"
                )
                print(
                    f"  Duration field: {'✓' if result['verification']['duration_field_present'] else '✗'}"
                )
                if duration_field:
                    print(f"    Value: {duration_field.get('value')}")
            else:
                print(f"✗ Notification failed: {close_result.error}")

            await notifier.close()

        except Exception as e:
            result["error"] = str(e)
            result["status"] = "error"
            print(f"✗ ERROR: {e}")
            import traceback

            traceback.print_exc()

        print()
        self.test_results.append(result)
        return result

    async def test_dev_webhook_fallback(self) -> dict[str, Any]:
        """Test 3: Verify development webhook fallback works.

        Returns:
            Test result dictionary
        """
        print("=" * 60)
        print("TEST 3: Development Webhook Fallback")
        print("=" * 60)

        result = {
            "test_name": "Development Webhook Fallback",
            "status": "failed",
            "error": None,
            "verification": {
                "fallback_works": False,
            },
        }

        if not self.dev_webhook_url:
            result["error"] = "DISCORD_WEBHOOK_URL not configured"
            result["status"] = "skipped"
            print("Status: ⚠ SKIPPED (no dev webhook configured)")
            print()
            return result

        try:
            # Create notifier with no trading webhook - should fall back to dev webhook
            notifier = TradeNotifier(webhook_url=None)

            # Verify it fell back to dev webhook
            if notifier.webhook_url == self.dev_webhook_url:
                result["verification"]["fallback_works"] = True
                result["status"] = "passed"
                print("✓ Fallback to DISCORD_WEBHOOK_URL works correctly")
                print(f"  Webhook URL: {notifier.webhook_url[:50]}...")
            else:
                result["error"] = (
                    f"Expected fallback to dev webhook, got: {notifier.webhook_url}"
                )
                print(f"✗ Fallback failed: {result['error']}")

            await notifier.close()

        except Exception as e:
            result["error"] = str(e)
            result["status"] = "error"
            print(f"✗ ERROR: {e}")
            import traceback

            traceback.print_exc()

        print()
        self.test_results.append(result)
        return result

    def print_results_table(self) -> None:
        """Print the test results table."""
        print("\n" + "=" * 60)
        print("DISCORD TRADING SMOKE TEST RESULTS")
        print("=" * 60)
        print()
        print("| Test                          | Status    | Message ID          |")
        print("|-------------------------------|-----------|---------------------|")

        for result in self.test_results:
            test_name = result["test_name"][:29]
            status = result["status"]
            message_id = result.get("message_id") or "N/A"
            if len(message_id) > 19:
                message_id = message_id[:16] + "..."

            status_symbol = (
                "✓"
                if status in ("delivered", "passed")
                else "✗"
                if status == "failed"
                else "⚠"
            )
            print(
                f"| {test_name:<29} | {status_symbol} {status:<7} | {message_id:<19} |"
            )

        print()

    def print_verification_summary(self) -> None:
        """Print detailed verification summary."""
        print("=" * 60)
        print("VERIFICATION SUMMARY")
        print("=" * 60)

        for result in self.test_results:
            test_name = result["test_name"]
            verification = result.get("verification", {})

            print(f"\n{test_name}:")
            for check, passed in verification.items():
                status = "✓" if passed else "✗"
                print(f"  {status} {check}")

        print()

    async def run_all_tests(self) -> dict[str, Any]:
        """Run all smoke tests.

        Returns:
            Complete test results
        """
        print("\n" + "=" * 60)
        print("DISCORD TRADING WEBHOOK SMOKE TESTS")
        print("Story: DISCORD-TRADING-001")
        print("=" * 60)
        print(f"Timestamp: {datetime.now(UTC).isoformat()}")
        print()

        # Verify environment
        env_result = self.verify_environment()

        # Run tests
        await self.test_open_notification()
        await self.test_close_notification()
        await self.test_dev_webhook_fallback()

        # Print summaries
        self.print_results_table()
        self.print_verification_summary()

        return {
            "story_id": "DISCORD-TRADING-001",
            "environment": env_result,
            "test_results": self.test_results,
            "timestamp": datetime.now(UTC).isoformat(),
        }


def main() -> None:
    """Run Discord trading smoke tests."""
    tester = DiscordTradingSmokeTester()

    try:
        results = asyncio.run(tester.run_all_tests())

        # Save results to file
        output_path = "_bmad-output/discord_trading_smoke_test_results.json"
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)

        print(f"Results saved to: {output_path}")

        # Exit with appropriate code
        all_passed = all(
            r["status"] in ("delivered", "passed") for r in results["test_results"]
        )

        if all_passed:
            print("\n✓ ALL TESTS PASSED")
            sys.exit(0)
        else:
            print("\n✗ SOME TESTS FAILED")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
