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
chmod +x scripts/monitoring/scheduler_heartbeat.py
chmod +x scripts/monitoring/trading_scheduler.py
```

### 2. Install Python dependencies
```bash
pip install redis aiohttp websockets
```

### 3. Scheduler Heartbeat Setup

The scheduler heartbeat recorder ensures the trading scheduler is properly tracked in Redis for monitoring gates.

#### Option A: Cron-based (Recommended)
Run the heartbeat once per minute via cron:

```bash
# Edit crontab
crontab -e

# Add this line (runs every minute):
* * * * * cd /home/tacopants/projects/ChiseAI && python3 scripts/monitoring/scheduler_heartbeat.py >> logs/monitoring/scheduler_heartbeat.log 2>&1
```

#### Option B: Daemon Mode
Run as a background daemon with 30-second intervals:

```bash
# Start daemon
python3 scripts/monitoring/trading_scheduler.py start

# Check status
python3 scripts/monitoring/trading_scheduler.py status

# Stop daemon
python3 scripts/monitoring/trading_scheduler.py stop
```

#### Option C: Systemd Service
Create `/etc/systemd/system/chiseai-scheduler.service`:

```ini
[Unit]
Description=ChiseAI Trading Scheduler Heartbeat
After=network.target

[Service]
Type=simple
User=chiseai
WorkingDirectory=/home/tacopants/projects/ChiseAI
ExecStart=/usr/bin/python3 scripts/monitoring/trading_scheduler.py --foreground
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable chiseai-scheduler
sudo systemctl start chiseai-scheduler
sudo systemctl status chiseai-scheduler
```

#### Verification
Check that heartbeat is being recorded:
```bash
# Check heartbeat hash
redis-cli -h host.docker.internal -p 6380 HGETALL bmad:chiseai:scheduler:heartbeat

# Check last seen timestamp
redis-cli -h host.docker.internal -p 6380 GET bmad:chiseai:scheduler:last_seen
```

Expected output:
```
1) "timestamp"
2) "2026-02-26T12:34:56.789012+00:00"
3) "status"
4) "running"
5) "pid"
6) "12345"
7) "hostname"
8) "your-hostname"
```

### 3. Configure cron (scheduler + hourly + 6-hourly)
```bash
# Edit crontab
crontab -e

# Add these lines:
# Scheduler heartbeat (every minute)
* * * * * cd /home/tacopants/projects/ChiseAI && python3 scripts/monitoring/scheduler_heartbeat.py >> logs/monitoring/scheduler_heartbeat.log 2>&1

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
# Test scheduler heartbeat
python3 scripts/monitoring/scheduler_heartbeat.py

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
