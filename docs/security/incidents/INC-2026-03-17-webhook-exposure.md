# Security Incident: Discord Webhook Exposure

## Incident ID: INC-2026-03-17-WEBHOOK-EXPOSURE

## Date: 2026-03-17

## Severity: CRITICAL

## Exposed Credentials

### Webhooks (ROTATION REQUIRED)
- Webhook ID: 1480639235827437600 - EXPOSED in .env (DISCORD_DEV_WEBHOOK_URL, DISCORD_AUTONOMY_WEBHOOK_URL)
- Webhook ID: 1476970020146778258 - EXPOSED in .env (DISCORD_TRADING_WEBHOOK_URL)  
- Webhook ID: 1448414669541736508 - EXPOSED in .env and infrastructure/cron/ (DISCORD_WEBHOOK_URL, CHISE_DISCORD_WEBHOOK_URL)

### Bot Token (ROTATION REQUIRED)
- Token: REDACTED_BOT_TOKEN

## Containment Actions Taken

1. [ ] Delete old webhooks via Discord server settings
2. [ ] Create new webhooks to replace compromised ones
3. [ ] Rotate Discord bot token
4. [ ] Sanitize repository (remove from current files and history)
5. [ ] Update .gitignore to prevent future commits

## Files Sanitized
- .env (deleted from tracking)
- infrastructure/cron/chiseai-daily-reflection (webhook URL removed)

## Git History Rewrite
- Commits affected: 18d6daceb, 5a842b9da, 4d3a6b152, b957f605a
- Method: git filter-repo --replace-text
- Status: [PENDING]
