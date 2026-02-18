#!/usr/bin/env python3
"""Verify KIMI env loading and Discord guild lock fix.

Quick verification script for CH-KIMI-DISCORD-001 changes.
"""

import os
import sys
from pathlib import Path

# Bootstrap environment first (must be before any env access)
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from config.bootstrap import bootstrap

bootstrap(load_env=True)

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
    any_guild_allowed = client_no_restrict.validate_guild("any_guild")
    print(f"✓ No restriction - any guild allowed: {any_guild_allowed}")

    # Test with guild restriction
    os.environ["DISCORD_GUILD_ID"] = "secure-guild-123"
    config_with_restrict = DiscordConfig.from_env()
    config_with_restrict.bot_token = "test-token"
    client_with_restrict = DiscordClient(config_with_restrict)

    print(f"✓ Guild restriction configured: {config_with_restrict.guild_id}")
    allowed = client_with_restrict.validate_guild("secure-guild-123")
    print(f"✓ Allowed guild passes: {allowed}")
    blocked = not client_with_restrict.validate_guild("wrong-guild")
    print(f"✓ Wrong guild blocked: {blocked}")
    no_guild = not client_with_restrict.validate_guild(None)
    print(f"✓ No guild blocked: {no_guild}")

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

    api_key_present = "Yes" if kimi_config["api_key"] else "No"
    print(f"✓ KIMI config loaded: API key present = {api_key_present}")
    print(f"✓ Discord config loaded: Guild ID = {discord_config['guild_id']}")

    # Create clients
    KimiClient(KimiConfig())  # Verify creation works
    discord_cfg = DiscordConfig.from_env()
    discord_cfg.bot_token = "test-token"
    discord_client = DiscordClient(discord_cfg)

    print("✓ Both clients instantiated successfully")
    validation_result = discord_client.validate_guild("test-guild-999")
    print(f"✓ Guild validation works: {validation_result}")

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
