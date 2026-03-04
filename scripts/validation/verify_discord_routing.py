#!/usr/bin/env python3
"""
Discord Routing Validation Script.

Validates that Discord routing is correctly configured for trade notifications:
- Verifies trading_channel_id is set to the correct value
- Verifies ExecutionAlertIntegration can send to #trading
- Performs dry-run validation (unless --live flag provided)

For PAPER-EXEC-001: Discord Routing Verification
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

# Setup path for imports - add project root to path for imports
script_dir = Path(__file__).parent
project_root = script_dir.parent.parent
sys.path.insert(0, str(project_root))

from datetime import UTC, datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Expected trading channel ID
EXPECTED_TRADING_CHANNEL_ID = "1444447985378398459"


def validate_discord_config() -> tuple[bool, list[str]]:
    """Validate DiscordConfig has correct trading_channel_id.

    Returns:
        Tuple of (success, list of error messages)
    """
    errors = []

    try:
        from src.discord_alerts.config import DiscordConfig

        # Test default config
        config = DiscordConfig()
        if config.trading_channel_id != EXPECTED_TRADING_CHANNEL_ID:
            errors.append(
                f"Default config trading_channel_id mismatch: "
                f"expected {EXPECTED_TRADING_CHANNEL_ID}, "
                f"got {config.trading_channel_id}"
            )
        else:
            logger.info(
                f"✓ Default DiscordConfig.trading_channel_id = {config.trading_channel_id}"
            )

        # Test from_env config
        env_config = DiscordConfig.from_env()
        if env_config.trading_channel_id != EXPECTED_TRADING_CHANNEL_ID:
            errors.append(
                f"from_env config trading_channel_id mismatch: "
                f"expected {EXPECTED_TRADING_CHANNEL_ID}, "
                f"got {env_config.trading_channel_id}"
            )
        else:
            logger.info(
                f"✓ DiscordConfig.from_env().trading_channel_id = {env_config.trading_channel_id}"
            )

        # Test get_channel_id_for_name routing
        routing_tests = [
            ("trading", EXPECTED_TRADING_CHANNEL_ID),
            ("trading_channel", EXPECTED_TRADING_CHANNEL_ID),
            ("trading-signals", EXPECTED_TRADING_CHANNEL_ID),
        ]

        for channel_name, expected_id in routing_tests:
            result = config.get_channel_id_for_name(channel_name)
            if result != expected_id:
                errors.append(
                    f"get_channel_id_for_name('{channel_name}') returned {result}, "
                    f"expected {expected_id}"
                )
            else:
                logger.info(f"✓ get_channel_id_for_name('{channel_name}') = {result}")

        return len(errors) == 0, errors

    except Exception as e:
        errors.append(f"Failed to validate DiscordConfig: {e}")
        return False, errors


def validate_trade_notifier() -> tuple[bool, list[str]]:
    """Validate TradeNotifier has correct trading_channel_id.

    Returns:
        Tuple of (success, list of error messages)
    """
    errors = []

    try:
        from src.discord_alerts.trade_notifier import TradeNotifier

        # Test default notifier
        notifier = TradeNotifier()
        if notifier.trading_channel_id != EXPECTED_TRADING_CHANNEL_ID:
            errors.append(
                f"TradeNotifier trading_channel_id mismatch: "
                f"expected {EXPECTED_TRADING_CHANNEL_ID}, "
                f"got {notifier.trading_channel_id}"
            )
        else:
            logger.info(
                f"✓ TradeNotifier.trading_channel_id = {notifier.trading_channel_id}"
            )

        # Verify methods exist
        if not hasattr(notifier, "send_trade_open_notification"):
            errors.append("TradeNotifier missing send_trade_open_notification method")
        else:
            logger.info("✓ TradeNotifier.send_trade_open_notification exists")

        if not hasattr(notifier, "send_trade_close_notification"):
            errors.append("TradeNotifier missing send_trade_close_notification method")
        else:
            logger.info("✓ TradeNotifier.send_trade_close_notification exists")

        return len(errors) == 0, errors

    except Exception as e:
        errors.append(f"Failed to validate TradeNotifier: {e}")
        return False, errors


def validate_execution_alert_integration() -> tuple[bool, list[str]]:
    """Validate ExecutionAlertIntegration has correct routing.

    Returns:
        Tuple of (success, list of error messages)
    """
    errors = []

    try:
        from src.execution.alerts.integration import ExecutionAlertIntegration

        # Test integration
        integration = ExecutionAlertIntegration()

        # Verify methods exist
        if not hasattr(integration, "on_trade_opened"):
            errors.append("ExecutionAlertIntegration missing on_trade_opened method")
        else:
            logger.info("✓ ExecutionAlertIntegration.on_trade_opened exists")

        if not hasattr(integration, "on_trade_closed"):
            errors.append("ExecutionAlertIntegration missing on_trade_closed method")
        else:
            logger.info("✓ ExecutionAlertIntegration.on_trade_closed exists")

        # Verify it creates TradeNotifier internally
        notifier = integration._get_trade_notifier()
        if notifier.trading_channel_id != EXPECTED_TRADING_CHANNEL_ID:
            errors.append(
                f"ExecutionAlertIntegration TradeNotifier channel mismatch: "
                f"expected {EXPECTED_TRADING_CHANNEL_ID}, "
                f"got {notifier.trading_channel_id}"
            )
        else:
            logger.info(
                f"✓ ExecutionAlertIntegration._get_trade_notifier().trading_channel_id = "
                f"{notifier.trading_channel_id}"
            )

        return len(errors) == 0, errors

    except Exception as e:
        errors.append(f"Failed to validate ExecutionAlertIntegration: {e}")
        return False, errors


async def test_dry_run_notification() -> tuple[bool, list[str]]:
    """Test dry-run notification without actually sending to Discord.

    Returns:
        Tuple of (success, list of error messages)
    """
    errors = []

    try:
        from src.discord_alerts.trade_notifier import TradeNotifier
        from src.ml.models.signal_outcome import SignalOutcome, SignalOutcomeStatus

        # Create test outcome
        test_outcome = SignalOutcome(
            outcome_id=uuid4(),
            signal_id=uuid4(),
            order_id="test-order-123",
            symbol="BTCUSDT",
            side="Buy",
            direction="LONG",
            fill_price=Decimal("50000.00"),
            fill_quantity=Decimal("0.001"),
            entry_price=Decimal("50000.00"),
            position_size=Decimal("0.001"),
            status=SignalOutcomeStatus.FILLED,
            metadata={"test": True},
        )

        # Create notifier with empty string to prevent env var fallback
        notifier = TradeNotifier(webhook_url="")

        # Test that it would route to correct channel
        if notifier.trading_channel_id != EXPECTED_TRADING_CHANNEL_ID:
            errors.append(
                f"Dry-run notifier channel mismatch: "
                f"expected {EXPECTED_TRADING_CHANNEL_ID}, "
                f"got {notifier.trading_channel_id}"
            )
        else:
            logger.info(
                f"✓ Dry-run notifier would route to channel {notifier.trading_channel_id}"
            )

        # Verify notifier has no webhook (dry-run mode)
        if notifier.webhook_url:
            logger.info(
                "ℹ️  Webhook URL detected in environment - skipping webhook failure test"
            )
            logger.info("✓ Dry-run mode: routing verified (webhook check skipped)")
        else:
            # Test open notification (should fail gracefully without webhook)
            result = await notifier.send_trade_open_notification(test_outcome)
            if result.success:
                errors.append(
                    "Dry-run open notification should fail without webhook URL, "
                    "but it succeeded"
                )
            elif result.error != "No webhook URL configured":
                errors.append(
                    f"Dry-run open notification failed with unexpected error: {result.error}"
                )
            else:
                logger.info(
                    "✓ Dry-run open notification correctly fails without webhook"
                )

            # Test close notification (should fail gracefully without webhook)
            result = await notifier.send_trade_close_notification(test_outcome)
            if result.success:
                errors.append(
                    "Dry-run close notification should fail without webhook URL, "
                    "but it succeeded"
                )
            elif result.error != "No webhook URL configured":
                errors.append(
                    f"Dry-run close notification failed with unexpected error: {result.error}"
                )
            else:
                logger.info(
                    "✓ Dry-run close notification correctly fails without webhook"
                )

        # Cleanup
        await notifier.close()

        return len(errors) == 0, errors

    except Exception as e:
        errors.append(f"Failed dry-run notification test: {e}")
        return False, errors


async def test_live_notification() -> tuple[bool, list[str]]:
    """Test live notification (sends actual message to Discord).

    WARNING: This will send real messages to Discord!

    Returns:
        Tuple of (success, list of error messages)
    """
    errors = []

    try:
        from src.discord_alerts.trade_notifier import TradeNotifier
        from src.ml.models.signal_outcome import SignalOutcome, SignalOutcomeStatus

        logger.warning("⚠️  SENDING LIVE NOTIFICATION TO DISCORD")

        # Create test outcome with test flag
        test_outcome = SignalOutcome(
            outcome_id=uuid4(),
            signal_id=uuid4(),
            order_id="test-live-order-123",
            symbol="TESTUSDT",
            side="Buy",
            direction="LONG",
            fill_price=Decimal("100.00"),
            fill_quantity=Decimal("1.0"),
            entry_price=Decimal("100.00"),
            position_size=Decimal("1.0"),
            status=SignalOutcomeStatus.FILLED,
            metadata={"test": True, "live_validation": True},
        )
        test_outcome.is_test = True  # Mark as test

        # Create notifier with webhook from env
        notifier = TradeNotifier()

        if not notifier.webhook_url:
            errors.append(
                "Cannot run live test: DISCORD_TRADING_WEBHOOK_URL or "
                "DISCORD_WEBHOOK_URL not set"
            )
            return False, errors

        # Verify channel ID
        if notifier.trading_channel_id != EXPECTED_TRADING_CHANNEL_ID:
            errors.append(
                f"Live notifier channel mismatch: "
                f"expected {EXPECTED_TRADING_CHANNEL_ID}, "
                f"got {notifier.trading_channel_id}"
            )
            return False, errors

        logger.info(f"✓ Live notifier routing to channel {notifier.trading_channel_id}")

        # Send open notification
        logger.info("Sending live trade open notification...")
        result = await notifier.send_trade_open_notification(test_outcome)

        if not result.success:
            errors.append(f"Live open notification failed: {result.error}")
        else:
            logger.info(
                f"✓ Live open notification sent successfully "
                f"(message_id={result.message_id})"
            )

        # Send close notification
        logger.info("Sending live trade close notification...")
        test_outcome.status = SignalOutcomeStatus.CLOSED
        test_outcome.pnl = Decimal("5.00")
        test_outcome.exit_price = Decimal("105.00")
        test_outcome.exit_time = datetime.now(UTC)

        result = await notifier.send_trade_close_notification(test_outcome)

        if not result.success:
            errors.append(f"Live close notification failed: {result.error}")
        else:
            logger.info(
                f"✓ Live close notification sent successfully "
                f"(message_id={result.message_id})"
            )

        # Cleanup
        await notifier.close()

        return len(errors) == 0, errors

    except Exception as e:
        errors.append(f"Failed live notification test: {e}")
        return False, errors


def main() -> int:
    """Run Discord routing validation.

    Returns:
        Exit code: 0 if all validations pass, non-zero otherwise
    """
    parser = argparse.ArgumentParser(
        description="Validate Discord routing for trade notifications"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Send actual Discord messages (WARNING: sends real messages)",
    )
    args = parser.parse_args()

    all_errors = []

    logger.info("=" * 70)
    logger.info("Discord Routing Validation")
    logger.info("=" * 70)

    # Validate DiscordConfig
    logger.info("\n[1/4] Validating DiscordConfig...")
    success, errors = validate_discord_config()
    all_errors.extend(errors)
    if not success:
        logger.error(f"❌ DiscordConfig validation failed: {errors}")
    else:
        logger.info("✅ DiscordConfig validation passed")

    # Validate TradeNotifier
    logger.info("\n[2/4] Validating TradeNotifier...")
    success, errors = validate_trade_notifier()
    all_errors.extend(errors)
    if not success:
        logger.error(f"❌ TradeNotifier validation failed: {errors}")
    else:
        logger.info("✅ TradeNotifier validation passed")

    # Validate ExecutionAlertIntegration
    logger.info("\n[3/4] Validating ExecutionAlertIntegration...")
    success, errors = validate_execution_alert_integration()
    all_errors.extend(errors)
    if not success:
        logger.error(f"❌ ExecutionAlertIntegration validation failed: {errors}")
    else:
        logger.info("✅ ExecutionAlertIntegration validation passed")

    # Test notifications
    logger.info("\n[4/4] Testing notifications...")
    if args.live:
        success, errors = asyncio.run(test_live_notification())
    else:
        success, errors = asyncio.run(test_dry_run_notification())
    all_errors.extend(errors)
    if not success:
        logger.error(f"❌ Notification test failed: {errors}")
    else:
        logger.info("✅ Notification test passed")

    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("Validation Summary")
    logger.info("=" * 70)

    if all_errors:
        logger.error(f"\n❌ VALIDATION FAILED with {len(all_errors)} error(s):")
        for i, error in enumerate(all_errors, 1):
            logger.error(f"  {i}. {error}")
        logger.error("\nExpected trading_channel_id: " + EXPECTED_TRADING_CHANNEL_ID)
        return 1
    else:
        logger.info("\n✅ ALL VALIDATIONS PASSED")
        logger.info(
            f"Trading notifications will route to Discord channel: {EXPECTED_TRADING_CHANNEL_ID}"
        )
        logger.info("\nRouting verified:")
        logger.info("  - DiscordConfig.trading_channel_id ✓")
        logger.info("  - TradeNotifier.trading_channel_id ✓")
        logger.info("  - ExecutionAlertIntegration routing ✓")
        logger.info("  - Notification methods exist ✓")
        return 0


if __name__ == "__main__":
    sys.exit(main())
