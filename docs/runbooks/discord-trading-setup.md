# Discord #trading Channel Webhook Setup

> **Story**: PAPER-DIAG-001  
> **Purpose**: Configure Discord webhook for trade notifications to the #trading channel  
> **Last Updated**: 2026-02-27

---

## Overview

The #trading Discord channel receives real-time trade notifications from the ChiseAI paper trading system. This runbook covers how to configure and test the webhook integration.

### What Gets Posted

- **Trade Open Notifications**: When a new position is opened
- **Trade Close Notifications**: When a position is closed with PnL
- **Daily Trade Recaps**: Nightly summary of all trading activity

---

## Prerequisites

- Access to the ChiseAI Discord server
- Admin or webhook management permissions in the #trading channel
- Shell access to the ChiseAI environment (for setting environment variables)

---

## Step 1: Get the Webhook URL from Discord

### Method A: Discord Web Interface

1. Open Discord and navigate to the ChiseAI server
2. Find the **#trading** channel (ID: `1444447985378398459`)
3. Click the **gear icon** next to the channel name (Channel Settings)
4. Go to **Integrations** → **Webhooks**
5. Click **"New Webhook"**
6. Configure the webhook:
   - **Name**: `ChiseAI Trading Bot`
   - **Channel**: #trading
   - **Avatar**: (Optional) Upload a bot avatar
7. Click **"Copy Webhook URL"**

### Method B: Discord Mobile App

1. Long-press the #trading channel
2. Tap **Edit Channel**
3. Go to **Integrations** → **Webhooks**
4. Tap **"Create Webhook"**
5. Set name to `ChiseAI Trading Bot`
6. Tap **"Copy URL"**

The webhook URL will look like:
```
https://discord.com/api/webhooks/1234567890123456789/abcdefghijklmnopqrstuvwxyz
```

**⚠️ Security Warning**: Treat this URL like a password. Anyone with this URL can post to your channel.

---

## Step 2: Set the Environment Variable

Choose one of the following methods:

### Option A: Export in Current Shell (Temporary)

```bash
export DISCORD_TRADING_WEBHOOK_URL="https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN"
```

**Note**: This only lasts for the current shell session.

### Option B: Add to .env File (Recommended for Development)

```bash
# Create or edit .env file
echo 'DISCORD_TRADING_WEBHOOK_URL="https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN"' >> .env
```

The `.env` file is gitignored by default, so it won't be committed.

### Option C: Add to Shell Profile (Persistent)

For Bash:
```bash
echo 'export DISCORD_TRADING_WEBHOOK_URL="https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN"' >> ~/.bashrc
source ~/.bashrc
```

For Zsh:
```bash
echo 'export DISCORD_TRADING_WEBHOOK_URL="https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN"' >> ~/.zshrc
source ~/.zshrc
```

### Option D: Docker Compose Environment

If running in Docker, add to your `docker-compose.yml`:

```yaml
services:
  chiseai-api:
    environment:
      - DISCORD_TRADING_WEBHOOK_URL=${DISCORD_TRADING_WEBHOOK_URL}
```

### Option E: Systemd Service Environment

If running as a systemd service, edit the service file:

```bash
sudo systemctl edit chiseai-api
```

Add:
```ini
[Service]
Environment="DISCORD_TRADING_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN"
```

Then reload and restart:
```bash
sudo systemctl daemon-reload
sudo systemctl restart chiseai-api
```

---

## Step 3: Test the Configuration

Run the test script to verify everything is working:

```bash
python scripts/test_discord_trading_webhook.py
```

### Expected Output

```
============================================================
DISCORD TRADING WEBHOOK DIAGNOSTICS
============================================================

📋 Environment Variables:
----------------------------------------
  ✓ DISCORD_TRADING_WEBHOOK_URL: https://discord.com/api/webhooks/...
  ✗ DISCORD_WEBHOOK_URL: not set

🔄 Testing webhook connectivity...
   URL: https://discord.com/api/webhooks/...

✅ SUCCESS: Webhook is configured and working!
   Check the #trading channel for the test message.
```

You should see a test message appear in the #trading channel:

> 🧪 **Discord Trading Webhook Test**
>
> **Configuration Test**
> This is a test message to verify the Discord webhook configuration for the #trading channel.
>
> ✓ Webhook URL is configured  
> ✓ Connection successful  
> ✓ Message delivery working

---

## Configuration Priority

The system checks for webhook URLs in this order (first match wins):

1. **`DISCORD_TRADING_WEBHOOK_URL`** environment variable (recommended)
2. **`DISCORD_WEBHOOK_URL`** environment variable (fallback)
3. **`webhook_url`** field in `config/scheduler.yaml` (not recommended)

### Why Environment Variables?

- **Security**: Webhook URLs contain authentication tokens
- **Flexibility**: Different environments (dev/staging/prod) can use different channels
- **Git Safety**: Prevents accidental commits of sensitive URLs

---

## Troubleshooting

### Issue: "Webhook URL is not set"

**Symptoms**:
```
❌ Errors:
  • Webhook URL is not set
```

**Solutions**:
1. Verify the environment variable is set:
   ```bash
   echo $DISCORD_TRADING_WEBHOOK_URL
   ```
2. If empty, set it following Step 2 above
3. If using `.env` file, ensure it's being loaded:
   ```bash
   source .env
   ```

### Issue: "Webhook URL format is invalid"

**Symptoms**:
```
❌ Errors:
  • Webhook URL format is invalid. Expected: https://discord.com/api/webhooks/<id>/<token>
```

**Solutions**:
1. Check you copied the full URL from Discord
2. Ensure there are no extra spaces or quotes
3. The URL should match this pattern:
   ```
   https://discord.com/api/webhooks/1234567890123456789/abcdefghijklmnopqrstuvwxyz
   ```

### Issue: "Rate limited"

**Symptoms**:
```
⚠️  Rate limited. Retry after 5s
```

**Solutions**:
1. Wait a few seconds and try again
2. Discord has rate limits on webhooks (5 requests per 2 seconds per webhook)
3. If consistently rate limited, check for other services using the same webhook

### Issue: "HTTP 401 Unauthorized"

**Symptoms**:
```
❌ HTTP 401: {"message": "Invalid Webhook Token"}
```

**Solutions**:
1. The webhook token may have been regenerated
2. Go back to Discord and copy the webhook URL again
3. Update the environment variable with the new URL

### Issue: "HTTP 404 Not Found"

**Symptoms**:
```
❌ HTTP 404: {"message": "Unknown Webhook"}
```

**Solutions**:
1. The webhook may have been deleted
2. Create a new webhook in Discord (Step 1)
3. Update the environment variable (Step 2)

### Issue: Test succeeds but no messages appear

**Solutions**:
1. Check the #trading channel permissions
2. Verify the webhook is assigned to the correct channel
3. Check Discord channel notification settings
4. Look for the message in the channel history (it may be buried)

---

## Manual Testing Commands

### Send a Test Message with curl

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"content": "🧪 Manual test from curl"}' \
  "$DISCORD_TRADING_WEBHOOK_URL"
```

### Test with Python

```python
import os
import requests

webhook_url = os.getenv("DISCORD_TRADING_WEBHOOK_URL")
response = requests.post(webhook_url, json={"content": "🧪 Test message"})
print(f"Status: {response.status_code}")
```

### Test the Trade Recap Script

```bash
# Dry run (no actual message sent)
python scripts/run_trade_history_recap.py --dry-run

# Send test message
python scripts/run_trade_history_recap.py --test

# Generate recap for yesterday
python scripts/run_trade_history_recap.py
```

---

## Related Components

| Component | Description | Path |
|-----------|-------------|------|
| Test Script | Validates webhook configuration | `scripts/test_discord_trading_webhook.py` |
| Trade Recap | Sends nightly trade summaries | `scripts/run_trade_history_recap.py` |
| Trade Notifier | Real-time trade notifications | `src/discord_alerts/trade_notifier.py` |
| Config File | Scheduler configuration | `config/scheduler.yaml` |
| Example Env | Environment variable template | `.env.example` |

---

## Environment Variables Reference

| Variable | Purpose | Required |
|----------|---------|----------|
| `DISCORD_TRADING_WEBHOOK_URL` | Webhook for #trading channel | **Yes** |
| `DISCORD_WEBHOOK_URL` | Fallback webhook URL | No |
| `DISCORD_TRADING_CHANNEL_ID` | Channel ID (default: 1444447985378398459) | No |

---

## Security Best Practices

1. **Never commit webhook URLs to git**
   - Use `.env` files (gitignored)
   - Use environment variables
   - Use secret management systems

2. **Rotate webhooks periodically**
   - Regenerate webhook URLs every 90 days
   - Update environment variables immediately

3. **Limit webhook permissions**
   - Only grant necessary channel access
   - Use separate webhooks for different environments

4. **Monitor webhook usage**
   - Check for unexpected messages
   - Review Discord audit logs

---

## Verification Checklist

- [ ] Webhook created in Discord #trading channel
- [ ] Webhook URL copied correctly
- [ ] Environment variable set (`DISCORD_TRADING_WEBHOOK_URL`)
- [ ] Test script passes (`python scripts/test_discord_trading_webhook.py`)
- [ ] Test message appears in #trading channel
- [ ] `.env` file added to `.gitignore` (if using)
- [ ] Documentation updated (if changing channel)

---

## Quick Reference

```bash
# 1. Set webhook URL
export DISCORD_TRADING_WEBHOOK_URL="https://discord.com/api/webhooks/..."

# 2. Test configuration
python scripts/test_discord_trading_webhook.py

# 3. Send test trade recap
python scripts/run_trade_history_recap.py --test

# 4. Run actual recap (for yesterday)
python scripts/run_trade_history_recap.py
```

---

## See Also

- [Trade History Recap Runbook](./trade-history-recap.md)
- [Paper Trading Operations](./paper-trading-operations.md)
- [Discord Alerts Documentation](../architecture/discord-alerts.md)

---

## Support

If you encounter issues not covered in this runbook:

1. Check the [Troubleshooting](#troubleshooting) section
2. Run the test script with verbose output: `python scripts/test_discord_trading_webhook.py --verbose`
3. Check application logs: `logs/trade_history_recap.log`
4. Escalate to the infrastructure team with the test script output
