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
4. [x] Sanitize repository (remove from current files and history)
5. [x] Update .gitignore to prevent future commits

## Files Sanitized
- .env (deleted from tracking)
- infrastructure/cron/chiseai-daily-reflection (webhook URL removed)
- docs/evidence/ST-OPS-DISCORD-WEBHOOK-001/* (regenerated with REDACTED values)

## Git History Rewrite
- Commits affected: All commits containing exposed tokens (2045 commits scanned)
- Method: git filter-repo --replace-text
- Status: COMPLETED
- Duration: 53.16 seconds
- Result: All exposed tokens replaced with REDACTED_* placeholders

## Verification
- [x] No exposed tokens found in current files
- [x] No exposed tokens found in git history
- [x] REDACTED placeholders verified in history
- [x] .gitignore contains .env entries
- [x] infrastructure/cron/chiseai-daily-reflection uses environment variable

## Next Steps
1. Delete compromised webhooks via Discord server settings
2. Create new webhooks to replace them
3. Rotate Discord bot token
4. Update environment variables with new webhook URLs
5. Test new webhooks
