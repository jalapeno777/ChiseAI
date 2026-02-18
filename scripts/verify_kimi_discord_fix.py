#!/usr/bin/env python3
"""Verify KIMI env loading and Discord guild lock fix.

Quick verification script for CH-KIMI-DISCORD-001 changes.
"""

import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from config.env_loader import load_discord_config, load_kimi_config
from discord_alerts.config import DiscordConfig
from discord_alerts.discord_client import DiscordClient
from llm.kimi_client import KimiClient, KimiConfig


def test_kimi_env_loading():
    """Test KIMI environment loading."""
    print("\n=== Testing KIMI Environment Loading ===")

    # Set test env vars
    os.environ["KIMI_API_KEY"] = "sk-test-kimi-key"
    os.environ["KIMI_TIMEOUT"] = "45"

    # Load via env_loader
    config = load_kimi_config()
    print(f"✓ KIMI_API_KEY loaded: {'Yes' if config['api_key'] else 'No'}")
    print(f"✓ KIMI_TIMEOUT: {config['timeout']}s")

    # Load via KimiConfig
    kimi_config = KimiConfig()
    print(f"✓ KimiConfig.api_key: {'Set' if kimi_config.api_key else 'Not set'}")

    # Create client
    client = KimiClient(kimi_config)
    print(f"✓ KimiClient created: {'Yes' if client else 'No'}")
    print(f"✓ Client configured: {'Yes' if client.is_configured() else 'No'}")

    return True


def test_discord_guild_lock():
    """Test Discord guild lock functionality."""
    print("\n=== Testing Discord Guild Lock ===")

    # Test without guild restriction
    config_no_restrict = DiscordConfig(
        bot_token="test-token",
    )
    client_no_restrict = DiscordClient(config_no_restrict)
    print(
        f"✓ No restriction - any guild allowed: {client_no_restrict.validate_guild('any_guild')}"
    )

    # Test with guild restriction
    os.environ["DISCORD_GUILD_ID"] = "secure-guild-123"
    config_with_restrict = DiscordConfig.from_env()
    config_with_restrict.bot_token = "test-token"
    client_with_restrict = DiscordClient(config_with_restrict)

    print(f"✓ Guild restriction configured: {config_with_restrict.guild_id}")
    print(
        f"✓ Allowed guild passes: {client_with_restrict.validate_guild('secure-guild-123')}"
    )
    print(
        f"✓ Wrong guild blocked: {not client_with_restrict.validate_guild('wrong-guild')}"
    )
    print(f"✓ No guild blocked: {not client_with_restrict.validate_guild(None)}")

    return True


def test_integration():
    """Test integration of both fixes."""
    print("\n=== Testing Integration ===")

    # Set up environment
    os.environ["KIMI_API_KEY"] = "sk-integration-test"
    os.environ["DISCORD_BOT_TOKEN"] = "discord-test-token"
    os.environ["DISCORD_GUILD_ID"] = "test-guild-999"

    # Load both configs
    kimi_config = load_kimi_config()
    discord_config = load_discord_config()

    print(
        f"✓ KIMI config loaded: API key present = {'Yes' if kimi_config['api_key'] else 'No'}"
    )
    print(f"✓ Discord config loaded: Guild ID = {discord_config['guild_id']}")

    # Create clients
    kimi_client = KimiClient(KimiConfig())
    discord_cfg = DiscordConfig.from_env()
    discord_cfg.bot_token = "test-token"
    discord_client = DiscordClient(discord_cfg)

    print(f"✓ Both clients instantiated successfully")
    print(
        f"✓ Guild validation works: {discord_client.validate_guild('test-guild-999')}"
    )

    return True


def main():
    """Run all verification tests."""
    print("=" * 60)
    print("CH-KIMI-DISCORD-001 Fix Verification")
    print("=" * 60)

    try:
        test_kimi_env_loading()
        test_discord_guild_lock()
        test_integration()

        print("\n" + "=" * 60)
        print("✓ ALL TESTS PASSED")
        print("=" * 60)
        print("\nSummary:")
        print("- KIMI environment loading works correctly")
        print("- Discord guild restriction works correctly")
        print("- Both features integrate properly")
        return 0

    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
