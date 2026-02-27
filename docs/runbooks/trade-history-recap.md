# Trade History Recap Runbook

> **Story:** ST-TRADING-001 - Nightly Trade History Recap  
> **Purpose:** Daily trade history summary posted to Discord #trading channel

---

## Overview

The Trade History Recap system generates and sends a nightly summary of trading activity to the Discord #trading channel. It complements the daily summary sent to #summaries by providing a focused view of individual trades.

### What It Does

- Queries trade outcomes from the database for the previous day
- Calculates key metrics (total trades, win rate, PnL)
- Identifies best and worst trades
- Posts a formatted summary to Discord #trading channel

### Schedule

- **Frequency:** Daily at 00:00 UTC (midnight)
- **Channel:** Discord #trading (ID: `1444447985378398459`)
- **Trigger:** Cron job or manual execution

---

## Manual Trigger

### Send Test Post Immediately

To verify Discord connectivity and formatting:

```bash
python3 scripts/run_trade_history_recap.py --test
```

This sends a test message to the configured Discord webhook without querying trade data.

### Generate Recap for Specific Date

```bash
# For yesterday (default)
python3 scripts/run_trade_history_recap.py

# For a specific date
python3 scripts/run_trade_history_recap.py --date 2024-01-15

# Dry run (generate but don't send)
python3 scripts/run_trade_history_recap.py --date 2024-01-15 --dry-run
```

### Using the Shell Script

```bash
# Normal execution (sends to #trading)
./scripts/cron/trade_history_recap.sh

# Test execution
./scripts/cron/trade_history_recap.sh --test

# Dry run
./scripts/cron/trade_history_recap.sh --dry-run
```

---

## Check if Scheduled

### Verify Cron Job Installation

```bash
# Check if cron job is installed
crontab -l | grep trade_history_recap

# Expected output:
# 0 0 * * * /home/tacopants/projects/ChiseAI/scripts/cron/trade_history_recap.sh >> /home/tacopants/projects/ChiseAI/logs/trade_history_recap.log 2>&1
```

### Install Cron Job

```bash
# Add to crontab (idempotent - safe to run multiple times)
(crontab -l 2>/dev/null; echo "0 0 * * * /home/tacopants/projects/ChiseAI/scripts/cron/trade_history_recap.sh >> /home/tacopants/projects/ChiseAI/logs/trade_history_recap.log 2>&1") | crontab -

# Verify installation
crontab -l | grep trade_history_recap
```

### Remove Cron Job

```bash
# Remove from crontab
crontab -l | grep -v trade_history_recap | crontab -
```

---

## Troubleshooting

### Script Fails to Run

**Check 1: Python Environment**
```bash
# Verify Python is available
python3 --version

# Check if virtual environment is activated
which python3

# If using venv:
source venv/bin/activate  # or .venv/bin/activate
```

**Check 2: Dependencies**
```bash
# Verify required packages are installed
python3 -c "import aiohttp; print('aiohttp OK')"
python3 -c "from src.reporting.trade_history_recap import TradeHistoryRecap; print('Import OK')"
```

### Discord Message Not Received

**Check 1: Webhook URL**
```bash
# Verify environment variable is set
echo $DISCORD_TRADING_WEBHOOK_URL

# Or fallback variable
echo $DISCORD_WEBHOOK_URL

# If not set, check .env file
grep DISCORD .env
```

**Check 2: Test Webhook**
```bash
# Send test post to verify connectivity
python3 scripts/run_trade_history_recap.py --test --verbose
```

**Check 3: Webhook URL Format**
- Must be a valid Discord webhook URL: `https://discord.com/api/webhooks/{webhook_id}/{token}`
- The webhook must have permission to post to the #trading channel

### Database Connection Issues

**Check 1: Database Environment Variables**
```bash
# Required variables
echo $DB_HOST        # Default: host.docker.internal
echo $DB_PORT        # Default: 5434
echo $DB_NAME        # Default: chiseai
echo $DB_USER        # Default: chiseai
echo $DB_PASSWORD    # Default: chiseai
```

**Check 2: Database Connectivity**
```bash
# Test PostgreSQL connection
psql -h ${DB_HOST:-host.docker.internal} -p ${DB_PORT:-5434} -U ${DB_USER:-chiseai} -d ${DB_NAME:-chiseai} -c "SELECT COUNT(*) FROM signal_outcomes;"
```

### No Trades Found

If the script runs successfully but reports "No trades to report":

1. **Check date range** - The script queries for the previous day by default
2. **Verify data exists** - Query the database directly:
   ```bash
   psql -h host.docker.internal -p 5434 -U chiseai -d chiseai -c "SELECT DATE(entry_time), COUNT(*) FROM signal_outcomes GROUP BY DATE(entry_time) ORDER BY DATE(entry_time) DESC LIMIT 5;"
   ```
3. **Check timezone** - The script uses UTC; ensure trade timestamps are in UTC

---

## Log File Locations

### Main Log File

```
logs/trade_history_recap.log
```

Contains:
- Timestamped execution logs
- Success/failure status
- Error messages
- Duration metrics

### Viewing Logs

```bash
# View last 50 lines
tail -n 50 logs/trade_history_recap.log

# Follow log in real-time
tail -f logs/trade_history_recap.log

# Search for errors
grep -i error logs/trade_history_recap.log

# View today's entries
grep "$(date '+%Y-%m-%d')" logs/trade_history_recap.log
```

### Log Rotation

Logs are appended and not automatically rotated. To prevent excessive log growth:

```bash
# Manual rotation
mv logs/trade_history_recap.log logs/trade_history_recap.log.$(date '+%Y%m%d')
touch logs/trade_history_recap.log

# Or use logrotate (add to /etc/logrotate.d/chiseai)
# /home/tacopants/projects/ChiseAI/logs/trade_history_recap.log {
#     daily
#     rotate 7
#     compress
#     delaycompress
#     missingok
#     notifempty
# }
```

---

## Configuration Reference

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DISCORD_TRADING_WEBHOOK_URL` | Yes* | - | Webhook URL for #trading channel |
| `DISCORD_WEBHOOK_URL` | Fallback | - | Fallback webhook URL |
| `DB_HOST` | No | `host.docker.internal` | PostgreSQL host |
| `DB_PORT` | No | `5434` | PostgreSQL port |
| `DB_NAME` | No | `chiseai` | Database name |
| `DB_USER` | No | `chiseai` | Database user |
| `DB_PASSWORD` | No | `chiseai` | Database password |

*Either `DISCORD_TRADING_WEBHOOK_URL` or `DISCORD_WEBHOOK_URL` must be set.

### Configuration File

Location: `config/scheduler.yaml`

```yaml
trade_history_recap:
  schedule: "0 0 * * *"
  timezone: "UTC"
  discord:
    webhook_url: null  # Use env var
    channel_id: "1444447985378398459"
  script:
    python: "scripts/run_trade_history_recap.py"
    shell: "scripts/cron/trade_history_recap.sh"
    log_file: "logs/trade_history_recap.log"
```

---

## Exit Codes

| Code | Meaning | Action |
|------|---------|--------|
| `0` | Success | None required |
| `1` | Error | Check logs for details |
| `2` | Configuration error | Verify env vars and config |
| `130` | Interrupted | User cancelled (Ctrl+C) |

---

## Related Documentation

- [Daily Summary Scheduler](./daily-summary-scheduler.md) - Similar system for #summaries channel
- [Discord Integration](../discord/integration.md) - Discord webhook setup guide
- [Database Schema](../database/signal_outcomes.md) - Signal outcomes table documentation

---

## Quick Reference Card

```bash
# Test
python3 scripts/run_trade_history_recap.py --test

# Dry run for yesterday
python3 scripts/run_trade_history_recap.py --dry-run

# Run for specific date
python3 scripts/run_trade_history_recap.py --date 2024-01-15

# Check cron
crontab -l | grep trade_history_recap

# View logs
tail -f logs/trade_history_recap.log

# Check env
echo $DISCORD_TRADING_WEBHOOK_URL
```

---

*Last updated: 2026-02-26*  
*Story: ST-TRADING-001*
