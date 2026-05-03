# R2a Signal Pipeline — 48h Monitoring Plan

## Status: ACTIVE

## Start Time: 2026-05-02T16:50:00Z (UTC)

## End Time: 2026-05-04T16:50:00Z (UTC)

---

## Root Cause Summary (from R2)

InfluxDB became unavailable at ~14:59 UTC due to fresh boot initialization. Signal generator crashed with "InfluxDB health check failed" (FATAL error). After R1 restored InfluxDB (~15:09 UTC), the generator continued crashing due to:

1. Supervisor in 5-minute backoff cycle (10 restarts in last hour, max 10 allowed)
2. Rate limit of 10 signals/hour/token already exhausted before the crash

**Resolution**: Natural recovery - supervisor backoff expired at ~16:15 UTC and generator resumed normal operation (confirmed via live log activity showing "Rate limit exceeded" but no FATAL errors).

---

## Baseline (T+0)

- Signal count in index at start: 9200
- Signals from today (May 2): 200
- Supervisor restarts (last 1h): 10 (at backoff limit)
- Last signal timestamp: 2026-05-02 16:03:03 UTC
- InfluxDB status: healthy (pass)
- Supervisor status: running but in backoff cycle
- Generator status: alive, generating but rate-limited

---

## Current System State (as of T+0 ~16:50 UTC)

### Container Status

| Container                 | Status | Uptime   |
| ------------------------- | ------ | -------- |
| chiseai-signal-supervisor | Up     | 47 hours |
| chiseai-influxdb          | Up     | 2 hours  |
| chiseai-redis             | Up     | 3 hours  |

### Signal Pipeline Status

- Signal generator process: RUNNING (PID visible in logs, no FATAL errors)
- Last new signals stored: 2026-05-02 16:03:03 UTC (~47 minutes ago at T+0)
- Signal index count: 9200 (stable, no new additions due to rate limit)
- Rate limit status: BTC/USDT and ETH/USDT at 10/hour limit

### Rate Limiting Configuration

- `max_signals_per_token_per_hour: 10` (configurable in SignalGenerationConfig)
- Current behavior: Generator continues running but signals are marked "rate-limited" and NOT written to Redis
- This is by design - the generator doesn't crash, it just throttles

---

## Monitoring Checks (every 6h for 48h)

| Metric                   | T+0 (16:50 UTC)  | T+6 | T+12 | T+24 | T+36 | T+48 |
| ------------------------ | ---------------- | --- | ---- | ---- | ---- | ---- |
| Signal count (index)     | 9200             | -   | -    | -    | -    | -    |
| New signals added?       | N (rate-limited) | -   | -    | -    | -    | -    |
| Crash-loop events        | 0                | -   | -    | -    | -    | -    |
| Supervisor restarts (1h) | 10 (at limit)    | -   | -    | -    | -    | -    |
| Last signal age          | ~47 min          | -   | -    | -    | -    | -    |
| InfluxDB health          | pass             | -   | -    | -    | -    | -    |
| FATAL/CRITICAL errors    | 0                | -   | -    | -    | -    | -    |

---

## Understanding Rate-Limited Operation

The signal generator is **not broken** - it's working as designed with rate limiting:

1. Generator runs continuously (no crash-loop)
2. For each symbol/timeframe combination, only 10 signals per hour are stored
3. When rate limit is hit, the signal is evaluated but NOT written to Redis
4. The log shows "Rate limit exceeded" but this is WARNING level, not ERROR

**This means signal count in Redis will not increase during the rate-limit period.**
**The 48h monitoring window is about proving STABILITY (no crashes), not signal growth.**

---

## Exit Criteria (for R8 readiness)

The pipeline is considered stable and ready for R8 promotion when:

1. **No crash-loop events**: Supervisor restarts < 5 in any 1-hour window
2. **No FATAL errors**: No InfluxDB health check failures or connection errors in supervisor logs
3. **Generator continuous uptime**: Signal generator process stays alive for entire 48h window
4. **InfluxDB healthy**: Health check passes consistently
5. **Rate limiting working as expected**: "Rate limit exceeded" warnings logged but no crashes

**Note**: Signal count growth is NOT an exit criterion because rate limiting caps it at 10/hour/symbol.

---

## Alarm Triggers

The following events should trigger immediate attention:

| Trigger          | Threshold                                             | Action                        |
| ---------------- | ----------------------------------------------------- | ----------------------------- |
| Crash-loop       | >3 restarts in 10 min                                 | Investigate generator process |
| Signal gap       | No new signals for >2h after rate limit window resets | Check generator is writing    |
| InfluxDB failure | Health check returns non-pass                         | Restart InfluxDB or escalate  |
| FATAL error      | Any FATAL in stderr log                               | Immediate investigation       |

---

## Rate Limit Reset Schedule

Rate limits reset on an hourly boundary. Expected times:

- ~17:00 UTC: BTC/USDT and ETH/USDT rate limits reset to 10/hour
- ~18:00 UTC: Next reset
- etc.

When rate limits reset, new signals should start appearing in Redis again.

---

## Evidence Collection Commands

For each check interval, run:

```bash
# Check supervisor status
docker logs chiseai-signal-supervisor --since 1h 2>&1 | grep -E "Starting signal|FATAL|ERROR|backing off"

# Check signal index
docker exec chiseai-signal-supervisor python3 -c "
import redis
r = redis.Redis(host='chiseai-redis', port=6380)
print('Signal index:', r.zcard('paper:index:signals'))
"

# Check InfluxDB health
curl -s -H "Authorization: Token <token>" http://host.docker.internal:18087/health

# Check latest signals
docker exec chiseai-signal-supervisor python3 -c "
import redis
from datetime import datetime
r = redis.Redis(host='chiseai-redis', port=6380)
keys = list(r.keys('paper:signal:*'))
today_keys = [k for k in keys if b'20260502' in k]
print(f'Signals from today: {len(today_keys)}')
"
```

---

## Next Steps

- T+6 check: 2026-05-02T22:50:00Z
- T+12 check: 2026-05-03T04:50:00Z
- T+24 check: 2026-05-03T16:50:00Z
- T+36 check: 2026-05-04T04:50:00Z
- T+48 check: 2026-05-04T16:50:00Z (END)

---

## Related Tasks

- R1: InfluxDB restoration (completed ~15:09 UTC)
- R2: Crash-loop diagnosis (completed)
- R3: Redis health verification (completed)
- R4: Signal generator stability verification (THIS TASK)
- R5: 48h monitoring plan (THIS TASK)
- R6-R8: TBD (pending R4/R5 completion)
