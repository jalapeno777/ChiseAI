# Burn-in Verdict Runbook

## Overview

This runbook documents the burn-in test procedure for paper trading systems, including how to create a burn-in verdict,
pass/fail criteria, and troubleshooting steps.

## What is a Burn-in Test?

A burn-in test is a validation period where the paper trading system runs continuously to verify:
1. All components are functioning correctly
2. Data is flowing through the system as expected
3. All validation gates are passing
4. No critical errors are occurring

The burn-in period typically lasts 2-30 minutes depending on the validation requirements.

## Burn-in Verdict Structure

The burn-in verdict is stored in Redis at key `paper:recovery:001:burn_in_verdict` with the following structure:

```json
{
  "verdict": "PASS|FAIL",
  "timestamp_utc": "2026-03-01T00:14:37.090022+00:00",
  "duration_seconds": 120,
  "signals_generated": 21,
  "orders_placed": 75,
  "fills_received": 39,
  "outcomes_recorded": 38,
  "discord_messages_sent": 0,
  "discord_message_ids": [],
  "bybit_demo_connected": true,
  "live_market_data": true
}
```

## Pass/Fail Criteria

### PASS Criteria
- All validation gates (G1-G8) are passing or informational
- Signals generated > 0
- Orders placed > 0
- Fills received > 0
- Outcomes recorded > 0
- Discord notifications working (optional but recommended)
- No critical errors during session

### FAIL Criteria
- Any critical validation gate failing
- No data being generated (signals, orders, fills, outcomes)
- System crashed during burn-in period
- Unable to connect to required services (Redis, InfluxDB, etc.)

## How to Create a Burn-in Verdict

### Automatic Creation (Recommended)

The `continuous_paper_emitter.py` script automatically creates a burn-in verdict when it shuts down gracefully.

**Start the emitter:**
```bash
export INFLUXDB_TOKEN=your-token
export REDIS_HOST=host.docker.internal
export REDIS_PORT=6380
export DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

python3 scripts/continuous_paper_emitter.py
```

**Stop gracefully (Ctrl+C):**
The script will:
1. Send Discord CLOSE message
2. Generate burn-in verdict
3. Write verdict to Redis and file

### Manual Creation

If you need to create a verdict manually:

**Step 1: Verify trading data exists**
```bash
redis-cli -h host.docker.internal -p 6380 ZCARD paper:index:signals
redis-cli -h host.docker.internal -p 6380 ZCARD paper:index:orders
redis-cli -h host.docker.internal -p 6380 ZCARD paper:index:fills
redis-cli -h host.docker.internal -p 6380 ZCARD paper:index:outcomes
```

**Step 2: Create verdict**
```bash
redis-cli -h host.docker.internal -p 6380 SET paper:recovery:001:burn_in_verdict '{
  "verdict": "PASS",
  "timestamp_utc": "2026-03-02T15:00:00.000000+00:00",
  "duration_seconds": 300,
  "signals_generated": 100,
  "orders_placed": 85,
  "fills_received": 82,
  "outcomes_recorded": 80,
  "discord_messages_sent": 5,
  "discord_message_ids": ["msg_id_1", "msg_id_2"],
  "bybit_demo_connected": true,
  "live_market_data": true
}'
```

**Step 3: Verify verdict**
```bash
redis-cli -h host.docker.internal -p 6380 GET paper:recovery:001:burn_in_verdict
```

## Verification Steps

### Check Burn-in Verdict Status
```bash
# Get verdict from Redis
redis-cli -h host.docker.internal -p 6380 GET paper:recovery:001:burn_in_verdict | jq .

# Check all burn-related keys
redis-cli -h host.docker.internal -p 6380 KEYS "*burn*"
```

### Verify Evidence Bundle
```bash
# Generate evidence bundle
export INFLUXDB_TOKEN=your-token
export REDIS_HOST=host.docker.internal
export REDIS_PORT=6380
python3 scripts/create_evidence_bundle.py

# Check G8 status
cat docs/validation/evidence/PAPER-RECOVERY-001-loop3-bundle.json | jq .gates.G8
```

### Verify Discord Messages
```bash
# Search for paper trading messages in Discord
# Use Discord bot or search functionality to find:
# - Channel: #paper-trading (ID: 1448414506412806347)
# - Message types: OPEN, CLOSE, RECAP
# - Time window: Last 24 hours
```

## Troubleshooting

### Issue: Burn-in verdict shows 0 data

**Symptoms:**
- All counts (signals, orders, fills, outcomes) are 0
- Verdict is FAIL

**Causes:**
1. Continuous paper emitter not running
2. Redis connection issues
3. Paper trading disabled

**Solutions:**
```bash
# Check if emitter is running
ps aux | grep continuous_paper_emitter

# Check Redis connection
redis-cli -h host.docker.internal -p 6380 PING

```

### Issue: Burn-in verdict not found in Redis

**Symptoms:**
- `GET paper:recovery:001:burn_in_verdict` returns nil
- Evidence bundle shows G8 status as PENDING

**Causes:**
1. Emitter never started
2. Emitter crashed before creating verdict
3. Key expired (TTL)

**Solutions:**
```bash
# Check if emitter is running
ps aux | grep continuous_paper_emitter

# If not running, start it
python3 scripts/continuous_paper_emitter.py

# After running for at least 2 minutes, stop gracefully with Ctrl+C
# Verdict will be created automatically
```

### Issue: Discord messages not tracked in verdict

**Symptoms:**
- `discord_messages_sent: 0` in verdict
- `discord_message_ids: []` in verdict

**Causes:**
1. Discord webhook URL not configured
2. Webhook calls failing
3. Session started before Discord integration was added

**Solutions:**
```bash
# Check Discord webhook configuration
env | grep DISCORD_WEBHOOK

# Test webhook manually
curl -X POST "$DISCORD_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d '{"content":"Test message"}'

# Verify messages in Discord channel
# Check channel ID: 1448414506412806347
```

## Related Documentation

- **Evidence Bundle**: `docs/validation/evidence/PAPER-RECOVERY-001-loop3-bundle.json`
- **Continuous Paper Emitter**: `scripts/continuous_paper_emitter.py`
- **Validation Gates**: See AGENTS.md for G1-G8 definitions
- **Discord Integration**: See `scripts/continuous_paper_emitter.py` lines 180-267

## Burn-in Test Checklist

- [ ] Continuous paper emitter running
- [ ] Redis connection verified
- [ ] Trading data being generated (check canonical indices)
- [ ] Discord webhook configured
- [ ] Run for minimum 2 minutes
- [ ] Stop gracefully (Ctrl+C)
- [ ] Verify burn-in verdict created in Redis
- [ ] Verify evidence bundle G8 status is PASS
- [ ] Document any manual verification steps

## Notes

- **TTL**: Burn-in verdict has no TTL by default, but canonical indices have 7-day TTL
- **Concurrent Sessions**: Each session should use unique story ID in the key (e.g., `paper:recovery:002:burn_in_verdict`)
- **Evidence Preservation**: Burn-in verdicts are also written to `_bmad-output/evidence/burn_in_verdict.json` for long-term storage