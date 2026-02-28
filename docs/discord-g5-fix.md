# G5 Discord Notifications Fix

## Problem Identified
**Root Cause:** All Discord webhook URLs point to the **development** channel webhook (ID: 1448414669541736508) instead of the **#trading** channel (ID: 1444447985378398459).

**Evidence:**
- Webhook ID: `1448414669541736508` posts to channel `1448414506412806347` (#development)
- #trading channel ID: `1444447985378398459` receives no trade notifications
- Test messages sent successfully but appeared in #development instead of #trading:
  - OPEN: `1477192905952329880` 
  - CLOSE: `1477192914936532993`
  - RECAP: `1477192915787976829`

## Solution

### Step 1: Create Webhook in #trading Channel (Manual)

1. Open Discord and navigate to **Bunny's Private Server**
2. Go to **Server Settings** → **Integrations** → **Webhooks**
3. Click **"Create Webhook"**
4. Configure the webhook:
   - **Name:** `ChiseAI Trading Alerts`
   - **Channel:** `#trading` (ID: 1444447985378398459)
   - **Avatar:** (optional) Upload ChiseAI logo
5. Click **"Copy Webhook URL"**
6. The URL format should be: `https://discord.com/api/webhooks/{WEBHOOK_ID}/{WEBHOOK_TOKEN}`

### Step 2: Update Environment Configuration

Edit `/home/tacopants/projects/ChiseAI/.env` and update line 128:

```bash
# OLD (incorrect - points to #development):
DISCORD_TRADING_WEBHOOK_URL=https://discord.com/api/webhooks/1448414669541736508/UeaEhvF...

# NEW (correct - points to #trading):
DISCORD_TRADING_WEBHOOK_URL=https://discord.com/api/webhooks/{NEW_WEBHOOK_ID}/{NEW_WEBHOOK_TOKEN}
```

Also update these lines to maintain consistency:
- Line 130: `CHISE_DISCORD_WEBHOOK_URL` 
- Line 132: `DISCORD_WEBHOOK_URL` (if you want all notifications in #trading)

Or keep `DISCORD_DEV_WEBHOOK_URL` pointing to #development for non-trading notifications.

### Step 3: Verify the Fix

After updating the webhook URL, run the verification script:

```bash
cd /home/tacopants/projects/ChiseAI
source .env
python3 scripts/verify_discord_trading.py
```

## Configuration Reference

| Variable | Purpose | Current Value | Should Point To |
|----------|---------|---------------|-----------------|
| `DISCORD_TRADING_WEBHOOK_URL` | Trade notifications | `1448414669541736508` (dev) | #trading webhook |
| `DISCORD_DEV_WEBHOOK_URL` | SEP/development alerts | `1448414669541736508` (dev) | #development (keep) |
| `CHISE_DISCORD_WEBHOOK_URL` | Paper trading alerts | `1448414669541736508` (dev) | #trading webhook |
| `DISCORD_WEBHOOK_URL` | General fallback | `1448414669541736508` (dev) | #trading webhook |

## Channel Mapping

| Channel | Channel ID | Purpose |
|---------|------------|---------|
| #trading | 1444447985378398459 | Trade notifications (target) |
| #development | 1448414506412806347 | Dev/test messages (current) |
| #summaries | 1445752426563899492 | Daily/weekly recaps |

## Code Verification

The notification code is working correctly:
- ✅ `ExecutionAlertIntegration` properly sends notifications
- ✅ `TradeNotifier` successfully delivers to webhooks
- ✅ All three message types (OPEN, CLOSE, RECAP) are functional
- ❌ Webhook URL points to wrong channel

## Test Evidence (Before Fix)

```
OPEN notification:  sent=True, message_id=1477192905952329880
CLOSE notification: sent=True, message_id=1477192914936532993
RECAP notification: sent=True, message_id=1477192915787976829
```

All messages sent successfully but routed to #development instead of #trading.

## Post-Fix Success Criteria

G5 PASS requires:
- [ ] At least 1 OPEN message with ID in #trading
- [ ] At least 1 CLOSE message with ID in #trading
- [ ] At least 1 RECAP message with ID in #trading
- [ ] All messages have timestamps from current proof cycle
- [ ] Messages display proper embeds with trade details

## Prevention

To prevent this in the future:
1. Always verify webhook URLs point to correct channels
2. Include channel ID verification in health checks
3. Document webhook-to-channel mappings
4. Test notifications in target channel before deployment
