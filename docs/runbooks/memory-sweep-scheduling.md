# Memory Sweep Scheduling Runbook

> **Story**: ST-HARDEN-001  
> **Purpose**: Document scheduling procedures for automated memory sweep operations  
> **Last Updated**: 2026-02-25

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Scheduling Options](#scheduling-options)
4. [Configuration](#configuration)
5. [Monitoring and Alerting](#monitoring-and-alerting)
6. [Troubleshooting](#troubleshooting)
7. [Security Considerations](#security-considerations)
8. [Related Resources](#related-resources)

---

## Overview

The memory sweep is a critical maintenance operation for the ChiseAI system that performs the following tasks:

- **Deduplication**: Identifies and removes duplicate memory entries across Redis and Qdrant
- **Promotion**: Moves high-value memories from Redis (short-term) to Qdrant (long-term)
- **Contradiction Detection**: Scans for conflicting memory entries and flags them for review
- **TTL Management**: Enforces time-to-live policies on transient memory entries

### Why Scheduling Matters

Without regular sweeps:
- Memory storage grows unbounded
- Query performance degrades
- Contradictions accumulate unchecked
- Short-term memories never graduate to long-term storage

### Recommended Schedule

| Environment | Frequency | Recommended Time |
|-------------|-----------|------------------|
| Production | Daily | 02:00 UTC (low traffic) |
| Staging | Daily | 03:00 UTC |
| Development | Weekly | Sunday 04:00 UTC |

---

## Prerequisites

### Required Infrastructure

1. **Redis Server**
   - Host: `host.docker.internal` (or configured Redis host)
   - Port: `6380`
   - Must have iterlog entries (`bmad:chiseai:iterlog:story:*`)

2. **Qdrant Vector Database**
   - Host: `host.docker.internal` (or configured Qdrant host)
   - Port: `6334`
   - Collection: `ChiseAI` must exist

3. **Python Environment**
   - Python 3.11+
   - Dependencies installed: `redis`, `qdrant-client`
   - Project root accessible at `/path/to/chiseai`

### Verification

Run the validation script to verify prerequisites:

```bash
bash scripts/ops/validate_memory_sweep_schedule.sh
```

Expected output:
```
[PASS] Redis connectivity
[PASS] Qdrant connectivity
[PASS] Memory sweep script exists
[PASS] Feature flags configured
```

---

## Scheduling Options

### Option 1: Cron Job (Recommended for Simple Setups)

Cron is the simplest scheduling option for single-server deployments.

#### Setup Steps

1. **Create log directory**:
```bash
sudo mkdir -p /var/log/chiseai
sudo chown $USER:$USER /var/log/chiseai
```

2. **Edit crontab**:
```bash
# Edit user crontab (recommended)
crontab -e

# Or edit system crontab (requires root)
sudo crontab -e
```

3. **Add cron entry**:
```bash
# Daily at 2:00 AM UTC
0 2 * * * cd /path/to/chiseai && python3 scripts/ops/memory_sweep.py --full-sweep >> /var/log/chiseai/memory_sweep.log 2>&1
```

4. **Verify cron job**:
```bash
# List current cron jobs
crontab -l | grep memory_sweep

# Expected output:
# 0 2 * * * cd /path/to/chiseai && python3 scripts/ops/memory_sweep.py --full-sweep >> /var/log/chiseai/memory_sweep.log 2>&1
```

#### Cron Schedule Reference

| Schedule | Cron Expression | Use Case |
|----------|-----------------|----------|
| Every hour | `0 * * * *` | High-frequency testing |
| Daily at 2 AM | `0 2 * * *` | Production standard |
| Every 6 hours | `0 */6 * * *` | Aggressive cleanup |
| Weekly (Sunday) | `0 2 * * 0` | Development environments |
| Twice daily | `0 2,14 * * *` | Heavy usage periods |

#### Log Rotation for Cron

Create `/etc/logrotate.d/chiseai-memory-sweep`:

```
/var/log/chiseai/memory_sweep.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 0644 $USER $USER
    postrotate
        # Optional: Send notification on rotation
        echo "Memory sweep logs rotated" | logger -t chiseai-memory-sweep
    endscript
}
```

---

### Option 2: Systemd Timer (Recommended for Production)

Systemd timers provide better logging, dependency management, and failure handling than cron.

#### Setup Steps

1. **Create service file** `/etc/systemd/system/chiseai-memory-sweep.service`:

```ini
[Unit]
Description=ChiseAI Memory Sweep
After=network.target redis.service qdrant.service
Wants=redis.service qdrant.service

[Service]
Type=oneshot
User=chiseai
Group=chiseai
WorkingDirectory=/path/to/chiseai
Environment=PYTHONPATH=/path/to/chiseai/src
Environment=REDIS_HOST=host.docker.internal
Environment=REDIS_PORT=6380
Environment=QDRANT_HOST=host.docker.internal
Environment=QDRANT_PORT=6334
ExecStart=/usr/bin/python3 scripts/ops/memory_sweep.py --full-sweep
StandardOutput=journal
StandardError=journal
SyslogIdentifier=chiseai-memory-sweep

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/path/to/chiseai/logs
```

2. **Create timer file** `/etc/systemd/system/chiseai-memory-sweep.timer`:

```ini
[Unit]
Description=Run ChiseAI Memory Sweep daily

[Timer]
OnCalendar=daily
OnCalendar=*-*-* 02:00:00
Persistent=true

# Optional: Add random delay to prevent thundering herd
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
```

3. **Enable and start the timer**:

```bash
# Reload systemd configuration
sudo systemctl daemon-reload

# Enable timer (starts on boot)
sudo systemctl enable chiseai-memory-sweep.timer

# Start timer now
sudo systemctl start chiseai-memory-sweep.timer

# Verify timer status
sudo systemctl list-timers | grep chiseai-memory-sweep
```

4. **Check service logs**:

```bash
# View recent logs
sudo journalctl -u chiseai-memory-sweep -n 50

# Follow logs in real-time
sudo journalctl -u chiseai-memory-sweep -f

# View logs since last boot
sudo journalctl -u chiseai-memory-sweep --since today
```

#### Systemd Timer Reference

| Schedule | OnCalendar Value | Description |
|----------|------------------|-------------|
| Daily at 2 AM | `*-*-* 02:00:00` | Standard production |
| Every 6 hours | `*-*-* 00/6:00:00` | Frequent sweeps |
| Weekly Sunday | `Sun *-*-* 02:00:00` | Weekly maintenance |
| Every Monday | `Mon *-*-* 02:00:00` | Start of week |
| Hourly | `*-*-* *:00:00` | Every hour |

#### Managing Systemd Timer

```bash
# Check timer status
sudo systemctl status chiseai-memory-sweep.timer

# List all timers
sudo systemctl list-timers --all

# Trigger service manually (for testing)
sudo systemctl start chiseai-memory-sweep.service

# Stop timer
sudo systemctl stop chiseai-memory-sweep.timer

# Disable timer (won't start on boot)
sudo systemctl disable chiseai-memory-sweep.timer
```

---

## Configuration

### Environment Variables

The memory sweep script respects the following environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_HOST` | `host.docker.internal` | Redis server hostname |
| `REDIS_PORT` | `6380` | Redis server port |
| `QDRANT_HOST` | `host.docker.internal` | Qdrant server hostname |
| `QDRANT_PORT` | `6334` | Qdrant server port |
| `CHISEAI_LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |

### Feature Flags

Feature flags control which sweep components are active. Set in Redis:

```bash
# Enable full memory sweep
redis-cli -h host.docker.internal -p 6380 SET chise:feature_flags:governance:memory_sweep_enabled true

# Enable specific components
redis-cli -h host.docker.internal -p 6380 SET chise:feature_flags:governance:memory_promotion_enabled true
redis-cli -h host.docker.internal -p 6380 SET chise:feature_flags:governance:memory_dedup_enabled true
redis-cli -h host.docker.internal -p 6380 SET chise:feature_flags:governance:contradiction_detection_enabled true
```

Check current feature flag status:

```bash
python3 scripts/ops/memory_sweep.py --status
```

### Script Arguments

| Argument | Description |
|----------|-------------|
| `--dry-run` | Run without making changes (default if no args) |
| `--full-sweep` | Run complete sweep with all components |
| `--promote` | Run promotion only |
| `--deduplicate` | Run deduplication only |
| `--check-contradictions` | Check for contradictions only |
| `--enable` | Enable the engine before running |
| `--status` | Check system status |
| `-v, --verbose` | Enable verbose logging |

---

## Monitoring and Alerting

### Health Checks

Run the validation script as a health check:

```bash
# Manual check
bash scripts/ops/validate_memory_sweep_schedule.sh

# As part of monitoring (exit code 0 = healthy)
bash scripts/ops/validate_memory_sweep_schedule.sh || echo "ALERT: Memory sweep check failed"
```

### Log Monitoring

**For Cron:**
```bash
# Check for errors in last run
tail -100 /var/log/chiseai/memory_sweep.log | grep -i error

# Check if sweep ran today
grep "$(date +%Y-%m-%d)" /var/log/chiseai/memory_sweep.log | tail -5
```

**For Systemd:**
```bash
# Check for errors
sudo journalctl -u chiseai-memory-sweep --since today | grep -i error

# Check last run status
sudo journalctl -u chiseai-memory-sweep -n 1 --output=json | jq '.MESSAGE'
```

### Alerting Rules

**Example: Prometheus Alertmanager**

```yaml
groups:
  - name: chiseai-memory-sweep
    rules:
      - alert: MemorySweepNotRunning
        expr: time() - chiseai_memory_sweep_last_success > 90000  # 25 hours
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Memory sweep has not run in 25 hours"
          
      - alert: MemorySweepFailed
        expr: chiseai_memory_sweep_last_status != 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Memory sweep failed"
```

**Example: Simple Shell Alert**

```bash
#!/bin/bash
# Add to cron: */30 * * * * /path/to/chiseai/scripts/ops/check_sweep_health.sh

if ! bash /path/to/chiseai/scripts/ops/validate_memory_sweep_schedule.sh > /dev/null 2>&1; then
    echo "Memory sweep health check failed at $(date)" | \
        mail -s "ChiseAI Alert: Memory Sweep Issue" ops@example.com
fi
```

### Metrics to Monitor

Track these metrics for operational visibility:

| Metric | Source | Alert Threshold |
|--------|--------|-----------------|
| Last sweep timestamp | Log/journal | > 25 hours ago |
| Sweep duration | Log output | > 30 minutes |
| Duplicates found | Sweep stats | Sudden spike |
| Contradictions detected | Sweep stats | > 10 new |
| Redis memory usage | Redis INFO | > 80% |
| Qdrant collection size | Qdrant API | Unusual growth |

---

## Troubleshooting

### Common Issues

#### Issue: Sweep fails with "Redis not available"

**Symptoms:**
```
WARNING - Redis not available: Error 111 connecting to host.docker.internal:6380. Connection refused.
```

**Diagnosis:**
```bash
# Test Redis connectivity
redis-cli -h host.docker.internal -p 6380 ping

# Check if Redis container is running
docker ps --filter name=redis

# Check Redis logs
docker logs chiseai-redis
```

**Resolution:**
1. Ensure Redis container is running: `docker start chiseai-redis`
2. Check network connectivity from host to container
3. Verify correct host/port in environment variables

---

#### Issue: Sweep fails with "Qdrant not available"

**Symptoms:**
```
WARNING - Qdrant not available: Connection refused
```

**Diagnosis:**
```bash
# Test Qdrant connectivity
curl http://host.docker.internal:6334/collections/ChiseAI

# Check Qdrant container
docker ps --filter name=qdrant
```

**Resolution:**
1. Start Qdrant container: `docker start chiseai-qdrant`
2. Verify collection exists: Check Qdrant dashboard

---

#### Issue: "Sweep engine is disabled"

**Symptoms:**
```
ERROR - Sweep engine is disabled. Use --enable or --dry-run
```

**Resolution:**
```bash
# Option 1: Enable via Redis
redis-cli -h host.docker.internal -p 6380 SET chise:feature_flags:governance:memory_sweep_enabled true

# Option 2: Use --enable flag
python3 scripts/ops/memory_sweep.py --full-sweep --enable

# Option 3: Run in dry-run mode for testing
python3 scripts/ops/memory_sweep.py --dry-run
```

---

#### Issue: Cron job not running

**Symptoms:**
- No log entries in `/var/log/chiseai/memory_sweep.log`
- `crontab -l` shows job but no output

**Diagnosis:**
```bash
# Check cron service status
sudo systemctl status cron

# Check cron logs
grep CRON /var/log/syslog | tail -20

# Test command manually
cd /path/to/chiseai && python3 scripts/ops/memory_sweep.py --dry-run
```

**Resolution:**
1. Ensure cron service is running: `sudo systemctl start cron`
2. Check log directory permissions
3. Verify Python path and script location
4. Add `2>&1` to redirect stderr to log file

---

#### Issue: Systemd timer not triggering

**Symptoms:**
- `systemctl list-timers` shows timer but service never runs
- No journal entries for the service

**Diagnosis:**
```bash
# Check timer status
sudo systemctl status chiseai-memory-sweep.timer

# Check for syntax errors
sudo systemd-analyze verify /etc/systemd/system/chiseai-memory-sweep.*

# Test service manually
sudo systemctl start chiseai-memory-sweep.service
sudo journalctl -u chiseai-memory-sweep -n 50
```

**Resolution:**
1. Reload systemd: `sudo systemctl daemon-reload`
2. Check timer is enabled: `sudo systemctl enable chiseai-memory-sweep.timer`
3. Verify `OnCalendar` syntax is correct
4. Check for unit file syntax errors

---

#### Issue: High memory usage during sweep

**Symptoms:**
- System becomes unresponsive during sweep
- OOM killer terminates sweep process

**Resolution:**
1. Run sweep with smaller batches (if supported)
2. Schedule during low-traffic periods
3. Add resource limits to systemd service:
   ```ini
   [Service]
   MemoryMax=2G
   CPUQuota=50%
   ```
4. Consider running on dedicated maintenance node

---

### Debug Mode

Enable verbose logging for troubleshooting:

```bash
# Verbose output
python3 scripts/ops/memory_sweep.py --full-sweep -v

# With environment debug
CHISEAI_LOG_LEVEL=DEBUG python3 scripts/ops/memory_sweep.py --dry-run
```

### Getting Help

If issues persist:

1. Run validation script: `bash scripts/ops/validate_memory_sweep_schedule.sh`
2. Check system status: `python3 scripts/ops/memory_sweep.py --status`
3. Review logs for error patterns
4. Report to Jarvis with:
   - Validation script output
   - Last 50 lines of relevant logs
   - System status output

---

## Security Considerations

### Access Control

- **Cron jobs**: Run as non-root user when possible
- **Systemd**: Use `User=` and `Group=` directives
- **File permissions**: Ensure log files are readable only by authorized users

### Secrets Management

Do not hardcode credentials in:
- Cron entries
- Systemd unit files
- Shell scripts

Use environment files instead:

```bash
# /etc/chiseai/memory-sweep.env
REDIS_HOST=host.docker.internal
REDIS_PORT=6380
QDRANT_HOST=host.docker.internal
QDRANT_PORT=6334
```

Reference in systemd:
```ini
[Service]
EnvironmentFile=/etc/chiseai/memory-sweep.env
```

### Network Security

- Use internal Docker networks when possible
- Restrict Redis and Qdrant ports with firewall rules
- Consider VPN or TLS for remote connections

### Audit Logging

Enable audit logging for compliance:

```bash
# Add to sweep command for audit trail
python3 scripts/ops/memory_sweep.py --full-sweep 2>&1 | \
    tee -a /var/log/chiseai/memory_sweep.log | \
    logger -t chiseai-memory-sweep -p local0.info
```

---

## Related Resources

- **Memory Sweep Script**: `scripts/ops/memory_sweep.py`
- **Validation Script**: `scripts/ops/validate_memory_sweep_schedule.sh`
- **Source Code**: `src/governance/memory/`
- **Story**: ST-MEMORY-002 (memory sweep implementation)
- **Story**: ST-HARDEN-001 (this runbook)

### Quick Commands Reference

```bash
# Check status
python3 scripts/ops/memory_sweep.py --status

# Dry run
python3 scripts/ops/memory_sweep.py --dry-run

# Full sweep with enable
python3 scripts/ops/memory_sweep.py --full-sweep --enable

# Validate schedule
bash scripts/ops/validate_memory_sweep_schedule.sh

# View cron jobs
crontab -l | grep memory_sweep

# View systemd timer
sudo systemctl list-timers | grep chiseai-memory-sweep
```

---

**End of Runbook**
