#!/usr/bin/env python3
"""Test script for Discord #trading channel webhook configuration.

Validates webhook URL format, tests connectivity, and sends a test message
to verify the configuration is working correctly.

Usage:
    python scripts/test_discord_trading_webhook.py [--webhook-url URL] [--verbose]

Exit codes:
    0 - Success (webhook configured and working)
    1 - Configuration error (webhook URL not set or invalid)
    2 - Connection error (webhook URL valid but connection failed)

For PAPER-DIAG-001: Discord Trading Webhook Configuration Fix
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Try to import bootstrap, but don't fail if it's not available
try:
    from config.bootstrap import bootstrap  # noqa: E402
except ImportError:
    bootstrap = None

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class WebhookValidator:
    """Validates Discord webhook configuration and connectivity."""

    # Discord webhook URL pattern
    WEBHOOK_PATTERN = re.compile(
        r"^https://discord\.com/api/webhooks/\d+/[a-zA-Z0-9_-]+$"
    )

    def __init__(self) -> None:
        """Initialize validator."""
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.info: list[str] = []

    def validate_url_format(self, url: str | None) -> bool:
        """Validate webhook URL format.

        Args:
            url: Webhook URL to validate

        Returns:
            True if format is valid, False otherwise
        """
        if not url:
            self.errors.append("Webhook URL is not set")
            return False

        if not isinstance(url, str):
            self.errors.append(
                f"Webhook URL must be a string, got {type(url).__name__}"
            )
            return False

        url = url.strip()

        if not url:
            self.errors.append("Webhook URL is empty or whitespace only")
            return False

        if not url.startswith("https://"):
            self.errors.append(f"Webhook URL must use HTTPS: {url[:50]}...")
            return False

        if not self.WEBHOOK_PATTERN.match(url):
            self.errors.append(
                "Webhook URL format is invalid. Expected: "
                "https://discord.com/api/webhooks/<id>/<token>"
            )
            return False

        return True

    def check_environment_variables(self) -> dict[str, str | None]:
        """Check all relevant environment variables.

        Returns:
            Dictionary of env var names to their values
        """
        env_vars = {
            "DISCORD_TRADING_WEBHOOK_URL": os.getenv("DISCORD_TRADING_WEBHOOK_URL"),
            "DISCORD_WEBHOOK_URL": os.getenv("DISCORD_WEBHOOK_URL"),
        }

        # Check for other Discord-related env vars for context
        other_vars = [
            "DISCORD_BOT_TOKEN",
            "DISCORD_GUILD_ID",
            "DISCORD_TRADING_CHANNEL_ID",
            "DISCORD_SUMMARIES_WEBHOOK_URL",
            "DISCORD_TEST_WEBHOOK_URL",
        ]

        for var in other_vars:
            value = os.getenv(var)
            if value:
                env_vars[var] = value[:20] + "..." if len(value) > 20 else value

        return env_vars


def get_webhook_url() -> str | None:
    """Get webhook URL from environment or config.

    Priority:
    1. DISCORD_TRADING_WEBHOOK_URL environment variable
    2. DISCORD_WEBHOOK_URL environment variable
    3. config/scheduler.yaml (if readable)

    Returns:
        Webhook URL or None if not configured
    """
    # Check environment variables first
    url = os.getenv("DISCORD_TRADING_WEBHOOK_URL")
    if url:
        logger.debug("Using DISCORD_TRADING_WEBHOOK_URL from environment")
        return url

    url = os.getenv("DISCORD_WEBHOOK_URL")
    if url:
        logger.debug("Using DISCORD_WEBHOOK_URL from environment (fallback)")
        return url

    # Try to read from config file
    config_path = Path(project_root) / "config" / "scheduler.yaml"
    if config_path.exists():
        try:
            import yaml

            with open(config_path) as f:
                config = yaml.safe_load(f)

            if config and "trade_history_recap" in config:
                recap_config = config["trade_history_recap"]
                if "discord" in recap_config:
                    url = recap_config["discord"].get("webhook_url")
                    if url:
                        logger.debug("Using webhook_url from config/scheduler.yaml")
                        return url
        except Exception as e:
            logger.debug(f"Could not read config file: {e}")

    return None


async def test_webhook_connectivity(url: str) -> dict[str, Any]:
    """Test webhook connectivity by sending a test message.

    Args:
        url: Webhook URL to test

    Returns:
        Dictionary with test results
    """
    result = {
        "success": False,
        "url": url[:50] + "..." if len(url) > 50 else url,
        "timestamp": datetime.now(UTC).isoformat(),
        "error": None,
        "response_status": None,
        "response_body": None,
    }

    try:
        import aiohttp

        timeout = aiohttp.ClientTimeout(total=30.0)

        # Build test message
        test_message = {
            "content": "🧪 **Discord Trading Webhook Test**",
            "embeds": [
                {
                    "title": "Configuration Test",
                    "description": (
                        "This is a test message to verify the Discord webhook "
                        "configuration for the #trading channel.\n\n"
                        "✓ Webhook URL is configured\n"
                        "✓ Connection successful\n"
                        "✓ Message delivery working"
                    ),
                    "color": 0x00FF00,  # Green
                    "timestamp": datetime.now(UTC).isoformat(),
                    "footer": {"text": "ChiseAI Trading Webhook Test"},
                }
            ],
        }

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=test_message) as response:
                result["response_status"] = response.status

                if response.status == 204:
                    # Success - Discord returns 204 No Content
                    result["success"] = True
                    logger.info("✓ Test message sent successfully")
                elif response.status == 429:
                    # Rate limited
                    retry_after = response.headers.get("Retry-After", "unknown")
                    result["error"] = f"Rate limited. Retry after {retry_after}s"
                    logger.warning(f"Rate limited (retry after: {retry_after}s)")
                else:
                    body = await response.text()
                    result["error"] = f"HTTP {response.status}: {body[:200]}"
                    result["response_body"] = body[:500]
                    logger.error(f"Webhook returned HTTP {response.status}")

    except ImportError:
        result["error"] = "aiohttp not installed. Run: pip install aiohttp"
        logger.error("aiohttp is required for webhook testing")
    except Exception as e:
        result["error"] = str(e)
        logger.error(f"Connection error: {e}")

    return result


def print_diagnostics(
    validator: WebhookValidator, env_vars: dict[str, str | None]
) -> None:
    """Print diagnostic information.

    Args:
        validator: Validator instance with errors/warnings
        env_vars: Environment variables dictionary
    """
    print("\n" + "=" * 60)
    print("DISCORD TRADING WEBHOOK DIAGNOSTICS")
    print("=" * 60)

    # Environment variables
    print("\n📋 Environment Variables:")
    print("-" * 40)

    primary_vars = ["DISCORD_TRADING_WEBHOOK_URL", "DISCORD_WEBHOOK_URL"]
    for var in primary_vars:
        value = env_vars.get(var)
        if value:
            # Mask the actual webhook token for security
            if "/" in value and len(value) > 50:
                masked = value[:50] + "..."
                print(f"  ✓ {var}: {masked}")
            else:
                print(f"  ✓ {var}: {value}")
        else:
            print(f"  ✗ {var}: not set")

    # Other Discord vars
    other_vars = {k: v for k, v in env_vars.items() if k not in primary_vars}
    if other_vars:
        print("\n  Other Discord variables:")
        for var, value in other_vars.items():
            print(f"    • {var}: {value}")

    # Errors
    if validator.errors:
        print("\n❌ Errors:")
        print("-" * 40)
        for error in validator.errors:
            print(f"  • {error}")

    # Warnings
    if validator.warnings:
        print("\n⚠️  Warnings:")
        print("-" * 40)
        for warning in validator.warnings:
            print(f"  • {warning}")

    # Info
    if validator.info:
        print("\nℹ️  Info:")
        print("-" * 40)
        for info in validator.info:
            print(f"  • {info}")

    print("\n" + "=" * 60)


def print_setup_instructions() -> None:
    """Print setup instructions for configuring the webhook."""
    print("\n📖 Setup Instructions:")
    print("-" * 60)
    print("""
1. Get the Webhook URL from Discord:
   a. Open Discord and go to the #trading channel
   b. Click the gear icon (Channel Settings)
   c. Go to Integrations → Webhooks
   d. Click "New Webhook"
   e. Name it "ChiseAI Trading Bot"
   f. Copy the Webhook URL

2. Set the Environment Variable:
   
   Option A - Export in shell:
   export DISCORD_TRADING_WEBHOOK_URL="https://discord.com/api/webhooks/..."
   
   Option B - Add to .env file:
   echo 'DISCORD_TRADING_WEBHOOK_URL="https://discord.com/api/webhooks/..."' >> .env
   
   Option C - Add to shell profile (~/.bashrc, ~/.zshrc, etc.):
   echo 'export DISCORD_TRADING_WEBHOOK_URL="https://discord.com/api/webhooks/..."' >> ~/.bashrc

3. Test the configuration:
   python scripts/test_discord_trading_webhook.py

4. Verify the test message appears in #trading channel

For more details, see: docs/runbooks/discord-trading-setup.md
""")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description="Test Discord #trading channel webhook configuration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Test with environment variable configuration
    python scripts/test_discord_trading_webhook.py

    # Test with explicit webhook URL
    python scripts/test_discord_trading_webhook.py --webhook-url "https://..."

    # Verbose output with diagnostics
    python scripts/test_discord_trading_webhook.py --verbose

    # JSON output for automation
    python scripts/test_discord_trading_webhook.py --json

Exit codes:
    0 - Success (webhook configured and working)
    1 - Configuration error (webhook URL not set or invalid)
    2 - Connection error (webhook URL valid but connection failed)
        """,
    )

    parser.add_argument(
        "--webhook-url",
        type=str,
        help="Override webhook URL (default: from env var)",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output result as JSON",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration without sending test message",
    )

    return parser.parse_args()


async def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 on success, 1 on config error, 2 on connection error)
    """
    if bootstrap is not None:
        try:
            bootstrap(load_env=True)
        except Exception as e:
            logger.debug(f"Bootstrap failed (non-fatal): {e}")

    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    validator = WebhookValidator()

    # Get webhook URL
    webhook_url = args.webhook_url or get_webhook_url()

    # Check environment variables
    env_vars = validator.check_environment_variables()

    # Validate URL format
    url_valid = validator.validate_url_format(webhook_url)

    if not url_valid:
        print_diagnostics(validator, env_vars)
        print_setup_instructions()

        if args.json:
            print(
                json.dumps(
                    {
                        "success": False,
                        "configured": False,
                        "valid": False,
                        "errors": validator.errors,
                        "warnings": validator.warnings,
                        "env_vars": {k: v is not None for k, v in env_vars.items()},
                    },
                    indent=2,
                )
            )

        return 1

    # URL format is valid
    webhook_url = webhook_url.strip()  # type: ignore[union-attr]

    if args.dry_run:
        validator.info.append("Dry run mode - not sending test message")
        print_diagnostics(validator, env_vars)
        print(f"\n✓ Webhook URL format is valid: {webhook_url[:50]}...")

        if args.json:
            print(
                json.dumps(
                    {
                        "success": True,
                        "configured": True,
                        "valid": True,
                        "dry_run": True,
                        "url_preview": webhook_url[:50] + "...",
                    },
                    indent=2,
                )
            )

        return 0

    # Test connectivity
    print_diagnostics(validator, env_vars)
    print("\n🔄 Testing webhook connectivity...")
    print(f"   URL: {webhook_url[:50]}...")

    test_result = await test_webhook_connectivity(webhook_url)

    if test_result["success"]:
        print("\n✅ SUCCESS: Webhook is configured and working!")
        print("   Check the #trading channel for the test message.")

        if args.json:
            print(json.dumps(test_result, indent=2, default=str))

        return 0
    else:
        print(f"\n❌ FAILED: {test_result['error']}")

        if args.json:
            print(json.dumps(test_result, indent=2, default=str))

        return 2


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.exception("Fatal error")
        print(f"\n💥 Fatal error: {e}", file=sys.stderr)
        sys.exit(1)
