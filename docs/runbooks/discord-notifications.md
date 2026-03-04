# Discord Notifications Runbook

## Overview

This runbook covers Discord notification configuration, validation, and troubleshooting for the ChiseAI system.

## Quick Verification Command

To verify your Discord channel configuration is correct:

```bash
# Run the Discord validation tests
pytest tests/test_discord/test_channel_validation.py -v

# Or run all Discord tests
pytest tests/test_discord/ -v
```

## Environment Variables

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `DISCORD_BOT_TOKEN` | Bot token for Discord API access | `MTAxMD...` |
| `DISCORD_DEVELOPMENT_CHANNEL_ID` | Channel ID for development/governance alerts | `1445752426563899492` |

### Optional Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DISCORD_STRICT_VALIDATION` | Fail fast on invalid config (true/false) | `true` |
| `DISCORD_WEBHOOK_URL` | Webhook URL for fallback sending | `None` |
| `DISCORD_GUILD_ID` | Guild restriction for security | `None` |

## Channel ID vs Guild ID

### The Problem

Discord IDs are "snowflakes" - 17-19 digit numeric strings. Both **Guild IDs** (server IDs) and **Channel IDs** use the same format, making them easy to confuse.

**Common Mistake**: Copying the Guild ID instead of the Channel ID.

### How to Find the Correct Channel ID

1. **Enable Developer Mode**:
   - Open Discord User Settings (gear icon)
   - Go to **Advanced** → Enable **Developer Mode**

2. **Copy Channel ID**:
   - Right-click on the **TEXT CHANNEL** (not the server name)
   - Select **Copy Channel ID**
   - The ID should be 17-19 digits

3. **Verify It's Not a Guild ID**:
   - Guild IDs are obtained by right-clicking the **server name**
   - Channel IDs are obtained by right-clicking a **text channel**

## Validation Behavior

### Strict Mode (Default)

When `DISCORD_STRICT_VALIDATION=true` (default):

- Configuration is validated at startup
- Invalid channel IDs cause **immediate failure** with clear error message
- Application will not start until fixed

**Example Error (Guild ID used as Channel ID)**:
```
DISCORD_DEVELOPMENT_CHANNEL_ID (1413522994810327134) appears to be
a Guild/Server ID, not a Channel ID. Guild name: 'ChiseAI Server'.

COMMON MISTAKE: You may have copied the Guild ID instead of
the Channel ID.

To find the correct Channel ID:
1. Enable Developer Mode in Discord (User Settings > Advanced)
2. Right-click on the TEXT CHANNEL (not the server)
3. Select 'Copy Channel ID'

Expected format: 17-19 digit numeric string
Guild IDs and Channel IDs look similar but serve different purposes.
```

### Non-Strict Mode

When `DISCORD_STRICT_VALIDATION=false`:

- Configuration is still validated
- Invalid channel IDs **log an error** but don't fail
- Notifications are **disabled** for the invalid channel
- Application continues running

Use this mode for:
- Development environments
- Graceful degradation scenarios
- Testing without valid Discord credentials

## Troubleshooting Guide

### "Channel ID appears to be a Guild/Server ID"

**Symptom**: Error message indicating the configured ID is a guild, not a channel.

**Solution**:
1. Follow the steps in [How to Find the Correct Channel ID](#how-to-find-the-correct-channel-id)
2. Update `DISCORD_DEVELOPMENT_CHANNEL_ID` with the correct channel ID
3. Restart the application

### "Channel ID not found (404)"

**Symptom**: Discord API returns 404 when validating the channel.

**Possible Causes**:
- Channel doesn't exist
- Bot doesn't have access to the channel
- Wrong guild configured

**Solution**:
1. Verify the channel ID is correct
2. Ensure the bot is invited to the server
3. Check bot permissions in the channel

### "Authentication failed (401)"

**Symptom**: Discord API returns 401 when validating.

**Solution**:
1. Verify `DISCORD_BOT_TOKEN` is set correctly
2. Regenerate the bot token in Discord Developer Portal if needed
3. Ensure the token hasn't expired

### "Access denied (403)"

**Symptom**: Discord API returns 403 when validating.

**Solution**:
1. Check bot permissions in the Discord channel
2. Ensure bot has "View Channel" and "Send Messages" permissions
3. Verify the bot is in the correct guild

### Notifications Not Sending

**Checklist**:
1. Verify `DISCORD_DEVELOPMENT_CHANNEL_ID` is set
2. Check logs for validation errors
3. Confirm `notifications_enabled` is True in config
4. Check if `DISCORD_STRICT_VALIDATION` caused disabling

## Code Example: Manual Validation

```python
import asyncio
from discord_alerts.config import DiscordConfig
from discord_alerts.discord_client import DiscordClient

async def validate_config():
    config = DiscordConfig.from_env()
    client = DiscordClient(config)
    
    # Validate the development channel
    success, errors = await client.validate_development_channel()
    
    if success:
        print("✓ Channel configuration valid")
        print(f"  Notifications enabled: {config.notifications_enabled}")
    else:
        print("✗ Channel configuration invalid:")
        for error in errors:
            print(f"  - {error}")
    
    return success

if __name__ == "__main__":
    asyncio.run(validate_config())
```

## Related Documentation

- [Discord Developer Portal](https://discord.com/developers/applications)
- [Discord API Documentation](https://discord.com/developers/docs/reference)
- [Discord Snowflake Format](https://discord.com/developers/docs/reference#snowflakes)

## Story Reference

- **Story ID**: ST-DISCORD-VALIDATION-001
- **Description**: Discord channel configuration validation hardening
- **Implemented**: 2026-03-03
