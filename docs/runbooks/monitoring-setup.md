# Monitoring Setup Guide

This guide covers the setup and configuration of monitoring for the ChiseAI trading system.

## Overview

The monitoring system provides:
- Real-time alerts for critical conditions
- Daily executive summaries
- Signal growth detection
- Burn-in completion tracking

## Prerequisites

- Redis server running (default: host.docker.internal:6380)
- Discord bot token configured in `.env`
- Discord channel ID for notifications

## Environment Variables

Add these to your `.env` file:

```bash
# Discord Bot Token (for sending notifications)
DISCORD_BOT_TOKEN=your_bot_token_here

# Discord Channel ID (for monitoring alerts)
DISCORD_DEVELOPMENT_CHANNEL_ID=your_channel_id_here

# Redis Connection (defaults shown)
REDIS_HOST=host.docker.internal
REDIS_PORT=6380
```

## Enhanced Monitoring (New for ACTIVATION-001)

### Pager Alerts (Every 5 minutes)

Monitors for critical conditions and sends immediate alerts:

```bash
*/5 * * * * cd /home/tacopants/projects/ChiseAI && python3 scripts/monitoring/pager_alerts.py >> logs/monitoring/cron.log 2>&1
```

**Alerts for:**
- Kill switch triggered
- Scheduler down >5 min

**Example Alert:**
```
@here 🚨 **CRITICAL: KILL SWITCH TRIGGERED** 🚨
Trading has been halted. Immediate investigation required.
```

### Daily Executive Summary (09:00 daily)

Posts daily summary to Discord:

```bash
0 9 * * * cd /home/tacopants/projects/ChiseAI && python3 scripts/monitoring/daily_executive_summary.py >> logs/monitoring/cron.log 2>&1
```

**Posts:**
- PnL summary
- Drawdown
- Win rate
- ECE drift
- Incidents (24h)

**Example Summary:**
```
**📈 Daily Executive Summary** | 2026-02-25 09:00 UTC

**Performance:**
• PnL: $1,234.56
• Win Rate: 65.3% (42W / 22L)
• Total Trades: 64

**Risk Metrics:**
• Drawdown: $123.45
• ECE Drift: Within bounds

**Operations:**
• Incidents (24h): 0

_Next summary tomorrow_
```

### Signal Growth Detector (Every 30 minutes)

Warns if no signal growth for 2+ hours:

```bash
*/30 * * * * cd /home/tacopants/projects/ChiseAI && python3 scripts/monitoring/signal_growth_detector.py >> logs/monitoring/cron.log 2>&1
```

**Example Warning:**
```
⚠️ **WARNING: No signal growth for 2+ hours**
Signal count stuck at 15. Check signal generation pipeline.
```

### Burn-in Completion (One-time at 24h)

Auto-posts burn-in completion at the 24-hour mark:

```bash
# Run once at burn-in end time (2026-02-26T23:50:00Z)
50 23 26 2 * cd /home/tacopants/projects/ChiseAI && python3 scripts/monitoring/burnin_completion.py >> logs/monitoring/cron.log 2>&1
```

**Example Completion Message:**
```
**🎉 BURN-IN COMPLETE** | 2026-02-26 23:50 UTC

**24-Hour Burn-in Finished Successfully**

**Final Status:** All gates validated
**System:** Ready for Bybit demo trading

**Next Steps:**
• Review final checkpoint report
• Confirm demo trading readiness
• Schedule production deployment review

_Monitoring will continue in operational mode_
```

## Complete Cron Schedule

Add this to your crontab (`crontab -e`):

```
# Pager alerts (every 5 min)
*/5 * * * * cd /home/tacopants/projects/ChiseAI && python3 scripts/monitoring/pager_alerts.py >> logs/monitoring/cron.log 2>&1

# Hourly health check (if exists)
0 * * * * cd /home/tacopants/projects/ChiseAI && python3 scripts/monitoring/hourly_health_check.py >> logs/monitoring/cron.log 2>&1

# Signal growth detector (every 30 min)
*/30 * * * * cd /home/tacopants/projects/ChiseAI && python3 scripts/monitoring/signal_growth_detector.py >> logs/monitoring/cron.log 2>&1

# 6-hour checkpoint (if exists)
0 */6 * * * cd /home/tacopants/projects/ChiseAI && python3 scripts/monitoring/checkpoint_gate_audit.py >> logs/monitoring/cron.log 2>&1

# Daily executive summary (9 AM UTC)
0 9 * * * cd /home/tacopants/projects/ChiseAI && python3 scripts/monitoring/daily_executive_summary.py >> logs/monitoring/cron.log 2>&1

# Burn-in completion (one-time at 24h mark - adjust date as needed)
50 23 26 2 * cd /home/tacopants/projects/ChiseAI && python3 scripts/monitoring/burnin_completion.py >> logs/monitoring/cron.log 2>&1
```

## Manual Testing

Test each script manually before enabling cron:

```bash
# Test pager alerts
python3 scripts/monitoring/pager_alerts.py

# Test daily summary
python3 scripts/monitoring/daily_executive_summary.py

# Test signal growth detector
python3 scripts/monitoring/signal_growth_detector.py

# Test burn-in completion
python3 scripts/monitoring/burnin_completion.py
```

## Log Files

All monitoring logs are stored in:
- `logs/monitoring/cron.log` - Cron execution logs
- `logs/monitoring/ALERT-*.log` - Alert fallback logs
- `logs/monitoring/daily-summary-*.log` - Daily summary fallback logs
- `logs/monitoring/WARNING-*.log` - Warning fallback logs
- `logs/monitoring/BURNIN-COMPLETE.log` - Burn-in completion fallback log

## Troubleshooting

### Discord notifications not working

1. Verify `DISCORD_BOT_TOKEN` is set correctly
2. Verify `DISCORD_DEVELOPMENT_CHANNEL_ID` is correct
3. Check bot has permission to post in the channel
4. Check `logs/monitoring/` for fallback logs

### Redis connection errors

1. Verify Redis is running: `redis-cli -h host.docker.internal -p 6380 ping`
2. Check `REDIS_HOST` and `REDIS_PORT` in `.env`
3. For container context, use `host.docker.internal` not `localhost`

### Scripts return non-zero exit codes

- Exit code 0: Success, no alerts
- Exit code 1: Alert/warning condition detected (expected for pager alerts and signal growth)

## Related Documentation

- [Checkpoint Gate Audit](./checkpoint-gate-audit.md) - G1-G8 validation
- [Health Checks](./health-checks.md) - System health monitoring
- [Incident Response](../../AGENTS.md) - Incident logging procedures
