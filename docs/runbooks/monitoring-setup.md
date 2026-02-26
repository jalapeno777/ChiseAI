# Monitoring Setup Runbook

## Overview
Automated monitoring for ACTIVATION-001 burn-in with Discord notifications.

## Environment Variables

```bash
# Required for Discord (optional - falls back to local logs)
export DISCORD_DEVELOPMENT_CHANNEL_ID="your-channel-id"
export DISCORD_BOT_TOKEN="your-bot-token"

# Redis connection (defaults shown)
export REDIS_HOST="host.docker.internal"
export REDIS_PORT="6380"
```

## Installation

### 1. Make scripts executable
```bash
chmod +x scripts/monitoring/hourly_health_check.py
chmod +x scripts/monitoring/checkpoint_gate_audit.py
```

### 2. Install Python dependencies
```bash
pip install redis aiohttp websockets
```

### 3. Configure cron (hourly + 6-hourly)
```bash
# Edit crontab
crontab -e

# Add these lines:
# Hourly health check (at minute 0)
0 * * * * cd /home/tacopants/projects/ChiseAI && python3 scripts/monitoring/hourly_health_check.py >> logs/monitoring/cron.log 2>&1

# 6-hour checkpoint (at 00:00, 06:00, 12:00, 18:00)
0 */6 * * * cd /home/tacopants/projects/ChiseAI && python3 scripts/monitoring/checkpoint_gate_audit.py >> logs/monitoring/cron.log 2>&1
```

### 4. Create log directory
```bash
mkdir -p logs/monitoring
```

### 5. Test scripts manually
```bash
# Test hourly check
python3 scripts/monitoring/hourly_health_check.py

# Test checkpoint
python3 scripts/monitoring/checkpoint_gate_audit.py
```

## Verification

### Check cron is installed
```bash
which cron
# or
systemctl status cron
```

### List cron jobs
```bash
crontab -l
```

### View monitoring logs
```bash
# Recent logs
ls -la logs/monitoring/

# Hourly logs
cat logs/monitoring/hourly-*.log

# Checkpoint logs
cat logs/monitoring/checkpoint-*.log
```

## Rollback / Disable

### Remove cron jobs
```bash
crontab -e
# Delete the monitoring lines
```

### Stop immediately
```bash
# Kill any running monitoring processes
pkill -f hourly_health_check
pkill -f checkpoint_gate_audit
```

### Clear logs (optional)
```bash
rm -rf logs/monitoring/*
```

## Troubleshooting

### "Discord not configured" warning
- Normal if DISCORD_CHANNEL_ID not set
- Check logs/monitoring/ for local output

### Redis connection failed
- Verify Redis running: `redis-cli -h host.docker.internal -p 6380 ping`
- Check REDIS_HOST/REDIS_PORT env vars

### Permission denied
- Run: `chmod +x scripts/monitoring/*.py`

## Message Formats

### Hourly Message
```
**🔥 Burn-in Hourly Check** | 2026-02-26 12:00 UTC

**Scheduler:** ✅ Process active
**Kill Switch:** ✅ Armed
**Daily Loss:** ✅ Limit: 2.0%

**Metrics:** Signals: 5 | Outcomes: 3 | Keys: 487

_Next check in 1 hour_
```

### Checkpoint Message
```
**📊 Burn-in Checkpoint (6h)** | 2026-02-26 12:00 UTC

**Gate Status:** 7 ✅ | 1 ⚠️ | 0 ❌

**G1:** ✅ PASS - Process running
**G2:** ⚠️ CHECK - No signal growth
...

_Next checkpoint in 6 hours_
```
