# Discord Notifications Operations Runbook

> **Story**: ST-DISCORD-NOTIFY-001
> **Last Updated**: 2026-03-03
> **Owner**: ChiseAI Infrastructure Team

## Overview

This runbook documents the operations for the Discord notifications feature, which automatically posts summaries of reflection and decision events to the development Discord channel. The feature provides real-time visibility into governance activities and decision-making processes.

## Table of Contents

1. [Enablement Steps](#enablement-steps)
2. [Environment Variables](#environment-variables)
3. [Feature Flag Control](#feature-flag-control)
4. [Event Types](#event-types)
5. [Troubleshooting](#troubleshooting)
6. [Verification Commands](#verification-commands)
7. [Related Documentation](#related-documentation)

---

## Enablement Steps

### Prerequisites

- Discord bot or webhook configured for ChiseAI
- Development Discord channel ID available
- Redis accessible at `chiseai-redis:6380`
- Application environment variables set

### Step 1: Configure Environment Variables

Set the required Discord environment variables in your application configuration:

```bash
# Required environment variables
export DISCORD_DEVELOPMENT_CHANNEL_ID="<your-channel-id>"

# Choose one authentication method:
export DISCORD_BOT_TOKEN="<your-bot-token>"
# OR
export DISCORD_WEBHOOK_URL="<your-webhook-url>"
```

To get the Discord channel ID:
1. Enable Developer Mode in Discord (User Settings → Advanced)
2. Right-click on the #development channel
3. Select "Copy ID"

### Step 2: Enable Feature Flag

Enable the Discord notifications feature flag in Redis:

```bash
# Using redis-cli from host
redis-cli -h host.docker.internal -p 6380 HSET chise:feature_flags:governance discord_notifications_enabled true

# Verify it's enabled
redis-cli -h host.docker.internal -p 6380 HGET chise:feature_flags:governance discord_notifications_enabled
```

Expected output: `true`

### Step 3: Verify Discord Configuration

Test that the Discord bot/webhook can post messages:

```bash
# Test webhook (if using webhook URL)
curl -X POST $DISCORD_WEBHOOK_URL \
  -H "Content-Type: application/json" \
  -d '{"content": "✅ Discord notifications feature enabled - test message"}'

# Or trigger a test event from the application
python3 -c "
from src.governance.notifications.discord_client import DiscordNotificationClient
client = DiscordNotificationClient()
client.send_message('✅ Discord notifications feature enabled - test message')
"
```

### Step 4: Verify Feature Integration

Check that the notifications module is properly integrated:

```bash
# Check for deduplication key pattern in Redis
redis-cli -h host.docker.internal -p 6380 KEYS 'bmad:chiseai:notifications:sent:*'

# Check application logs for Discord initialization
tail -f /var/log/chiseai/application.log | grep -i "discord"
```

---

## Environment Variables

### Required Variables

| Variable | Description | Example | Required |
|----------|-------------|---------|----------|
| `DISCORD_DEVELOPMENT_CHANNEL_ID` | Target Discord channel ID for notifications | `123456789012345678` | Yes |
| `DISCORD_BOT_TOKEN` | Discord bot token for authentication | `MTIz...` | One of* |
| `DISCORD_WEBHOOK_URL` | Discord webhook URL for authentication | `https://discord.com/api/webhooks/...` | One of* |

*One of `DISCORD_BOT_TOKEN` or `DISCORD_WEBHOOK_URL` is required.

### Optional Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DISCORD_NOTIFICATION_TIMEOUT` | Timeout for Discord API calls in seconds | `30` |
| `DISCORD_RETRY_ATTEMPTS` | Number of retry attempts for failed sends | `3` |
| `DISCORD_RETRY_DELAY` | Delay between retry attempts in seconds | `5` |

### Getting Discord Credentials

#### Bot Token (Recommended)

1. Create a Discord application at https://discord.com/developers/applications
2. Create a bot user for the application
3. Enable bot permissions:
   - Send Messages
   - Embed Links
   - Read Message History
   - Read Messages/View Channels
4. Invite bot to server with OAuth2 URL
5. Copy bot token from the "Bot" tab

#### Webhook URL (Alternative)

1. Go to channel settings in Discord
2. Integrations → Webhooks → Create Webhook
3. Copy the webhook URL

---

## Feature Flag Control

### Feature Flag Location

Discord notifications feature flag is stored in Redis:

```
chise:feature_flags:governance:discord_notifications_enabled
```

### Enable Notifications

```bash
# Using redis-cli from host
redis-cli -h host.docker.internal -p 6380 HSET chise:feature_flags:governance discord_notifications_enabled true

# Verify
redis-cli -h host.docker.internal -p 6380 HGET chise:feature_flags:governance discord_notifications_enabled
```

### Disable Notifications

```bash
# Disable feature flag
redis-cli -h host.docker.internal -p 6380 HSET chise:feature_flags:governance discord_notifications_enabled false

# Verify
redis-cli -h host.docker.internal -p 6380 HGET chise:feature_flags:governance discord_notifications_enabled
```

### Check Current Status

```bash
# Get value
redis-cli -h host.docker.internal -p 6380 HGET chise:feature_flags:governance discord_notifications_enabled

# List all governance feature flags
redis-cli -h host.docker.internal -p 6380 HGETALL chise:feature_flags:governance
```

### Feature Flag Behavior

| Value | Behavior |
|-------|----------|
| `true` | Discord notifications are sent for all enabled event types |
| `false` | Discord notifications are suppressed (events still occur, just not posted) |
| (not set) | Defaults to `false` (notifications disabled) |

---

## Event Types

### Reflection Events

Reflection events are posted when reflection artifacts are generated.

**Types:**
- Daily reflections (6-hour cycles)
- Weekly reflections
- Monthly reflections (if configured)

**Trigger Conditions:**
- Reflection artifact successfully written to storage
- Feature flag `discord_notifications_enabled` is `true`
- Notification not already sent (deduplication check)

**Example Content:**

```
📊 Daily Reflection Generated
──────────────────────────────
Story: ST-REFLECT-RUNTIME-001
Type: 6-hour cycle
Timestamp: 2026-03-03T18:00:00Z
KPIs Analyzed: 15
Artifacts: _bmad-output/brain-eval/reflections/daily-2026-03-03.json
```

### Decision Events

Decision events are posted when decisions are written to memory.

**Trigger Conditions:**
- Decision entry created in memory system
- Feature flag `discord_notifications_enabled` is `true`
- Notification not already sent (deduplication check)

**Example Content:**

```
🎯 Decision Logged
──────────────────
Decision: Enable new risk assessment model
Story: ST-RISK-042
Timestamp: 2026-03-03T14:30:00Z
Impact: Medium
Confidence: 0.85
```

### Event Deduplication

To prevent duplicate notifications, each event is tracked in Redis:

```bash
# Check sent notifications
redis-cli -h host.docker.internal -p 6380 KEYS 'bmad:chiseai:notifications:sent:*'

# View specific notification entry
redis-cli -h host.docker.internal -p 6380 GET bmad:chiseai:notifications:sent:reflection:daily:2026-03-03
```

Deduplication keys follow the pattern:
- `bmad:chiseai:notifications:sent:<event_type>:<unique_identifier>`

---

## Troubleshooting

### Notifications Not Appearing in Discord

**Symptom:** Reflection or decision events occur, but no Discord posts appear.

**Diagnosis:**

```bash
# 1. Check feature flag
redis-cli -h host.docker.internal -p 6380 HGET chise:feature_flags:governance discord_notifications_enabled

# 2. Check environment variables are set
env | grep DISCORD

# 3. Check application logs for errors
tail -f /var/log/chiseai/application.log | grep -i "discord"

# 4. Verify Discord credentials are valid
curl -X POST $DISCORD_WEBHOOK_URL \
  -H "Content-Type: application/json" \
  -d '{"content": "Test message"}'
```

**Resolution:**

1. Ensure `discord_notifications_enabled` is set to `true`
2. Verify `DISCORD_DEVELOPMENT_CHANNEL_ID` is correct
3. Check bot has proper permissions:
   - Send Messages
   - Embed Links
   - Read Message History
4. Verify bot is invited to the correct server
5. Check application logs for authentication errors

### Duplicate Notifications

**Symptom:** Same event posted multiple times to Discord.

**Diagnosis:**

```bash
# Check for multiple deduplication keys
redis-cli -h host.docker.internal -p 6380 KEYS 'bmad:chiseai:notifications:sent:*' | wc -l

# Check notification timestamps
redis-cli -h host.docker.internal -p 6380 TTL bmad:chiseai:notifications:sent:reflection:daily:2026-03-03
```

**Resolution:**

1. Check Redis deduplication keys are being set correctly
2. Verify TTL (time-to-live) on deduplication keys (should be at least 24 hours)
3. Check application logs for race conditions or multiple event triggers
4. Consider increasing deduplication key TTL if events are being re-processed

### Missing Notifications

**Symptom:** Some events are posted to Discord, others are missing.

**Diagnosis:**

```bash
# Check for non-blocking errors in logs
tail -f /var/log/chiseai/application.log | grep -i "discord" | grep -i "error\|warning"

# Check Redis connection
redis-cli -h host.docker.internal -p 6380 ping

# Check notification queue (if using queue system)
redis-cli -h host.docker.internal -p 6380 KEYS 'bmad:chiseai:notifications:queue:*'
```

**Resolution:**

1. Discord notifications are non-blocking by design - errors won't stop the main workflow
2. Check application logs for specific error messages
3. Verify network connectivity to Discord API
4. Check if Discord rate limits are being hit ( Discord allows 50 requests/second per bot)
5. Verify event-specific conditions (e.g., some events may be filtered out)

### Discord Rate Limit Errors

**Symptom:** Notifications fail with rate limit errors.

**Diagnosis:**

```bash
# Check for rate limit errors in logs
tail -f /var/log/chiseai/application.log | grep -i "rate limit"

# Check notification frequency
redis-cli -h host.docker.internal -p 6380 KEYS 'bmad:chiseai:notifications:sent:*' | head -10 | xargs -I {} redis-cli -h host.docker.internal -p 6380 GET {}
```

**Resolution:**

1. Discord allows 50 requests/second per bot - you should not hit this limit
2. If hitting limits, check for infinite loops or cascading events
3. Verify `DISCORD_RETRY_DELAY` is configured appropriately (default: 5 seconds)
4. Consider adding additional rate limiting at application level

### Bot/Webhook Authentication Failures

**Symptom:** All notifications fail with authentication errors.

**Diagnosis:**

```bash
# Test authentication
curl -X POST $DISCORD_WEBHOOK_URL \
  -H "Content-Type: application/json" \
  -d '{"content": "Test"}'

# Or test bot token
curl -H "Authorization: Bot $DISCORD_BOT_TOKEN" \
  https://discord.com/api/v10/users/@me
```

**Resolution:**

1. Regenerate bot token or webhook URL
2. Verify token hasn't expired or been revoked
3. Check bot is still a member of the server
4. Ensure bot has not been removed from the specific channel

---

## Verification Commands

### Test Discord Notification

Test that the Discord notification system is working by sending a test message:

```bash
# Method 1: Using webhook directly
curl -X POST $DISCORD_WEBHOOK_URL \
  -H "Content-Type: application/json" \
  -d '{"content": "✅ Discord notifications test - verified at '"$(date)"'"}'

# Method 2: Using Python script
python3 -c "
from src.governance.notifications.discord_client import DiscordNotificationClient
client = DiscordNotificationClient()
result = client.send_message('✅ Discord notifications test - verified at '"$(date)"'')
print(f'Status: {result}')
"

# Method 3: Trigger a reflection event
cd /home/tacopants/projects/ChiseAI
python3 scripts/evaluation/run_weekly_reflection.py --week $(date +%Y-W%V) --dry-run
```

### Check Redis Deduplication Keys

Verify that notifications are being tracked correctly in Redis:

```bash
# List all sent notification keys
redis-cli -h host.docker.internal -p 6380 KEYS 'bmad:chiseai:notifications:sent:*'

# Count notifications
redis-cli -h host.docker.internal -p 6380 KEYS 'bmad:chiseai:notifications:sent:*' | wc -l

# Check specific notification
redis-cli -h host.docker.internal -p 6380 GET bmad:chiseai:notifications:sent:reflection:daily:2026-03-03

# Check TTL (time until key expires)
redis-cli -h host.docker.internal -p 6380 TTL bmad:chiseai:notifications:sent:reflection:daily:2026-03-03
```

### View Application Logs

Check application logs for Discord notification activity and errors:

```bash
# View all Discord-related logs
tail -f /var/log/chiseai/application.log | grep -i "discord"

# View only errors
tail -f /var/log/chiseai/application.log | grep -i "discord" | grep -i "error"

# View last 50 lines
tail -n 50 /var/log/chiseai/application.log | grep -i "discord"

# Search for specific event
grep "Discord notification" /var/log/chiseai/application.log | tail -20
```

### Verify Feature Flag Status

```bash
# Check if Discord notifications are enabled
redis-cli -h host.docker.internal -p 6380 HGET chise:feature_flags:governance discord_notifications_enabled

# List all governance feature flags
redis-cli -h host.docker.internal -p 6380 HGETALL chise:feature_flags:governance
```

### Trigger Test Event

Trigger a real event to verify end-to-end notification flow:

```bash
# Trigger a daily reflection (creates notification if enabled)
cd /home/tacopants/projects/ChiseAI
python3 scripts/evaluation/run_mini_eval.py

# Trigger a weekly reflection
python3 scripts/evaluation/run_weekly_reflection.py --week $(date +%Y-W%V)

# Check logs for notification
tail -f /var/log/chiseai/application.log | grep -i "discord.*reflection"
```

### Manual Verification Checklist

- [ ] Feature flag `discord_notifications_enabled` is set to `true`
- [ ] `DISCORD_DEVELOPMENT_CHANNEL_ID` environment variable is set
- [ ] Bot token or webhook URL is configured
- [ ] Bot has proper permissions in Discord
- [ ] Test message successfully posted to Discord
- [ ] Redis deduplication keys are being created
- [ ] No errors in application logs
- [ ] Notifications appear for reflection events
- [ ] Notifications appear for decision events

---

## Related Documentation

- [Reflection Scheduler Operations Runbook](reflection-scheduler-ops.md) - Details on reflection event generation
- [Temp Memory Migration Runbook](tempmemory-migration.md) - Details on decision event tracking
- [Discord Trading Setup Runbook](discord-trading-setup.md) - Details on Discord bot configuration for ChiseAI

---

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2026-03-03 | Initial runbook creation | ST-DISCORD-NOTIFY-001 |
