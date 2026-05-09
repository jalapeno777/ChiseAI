# G-Exit-24h Escalation Templates

## Canary Closed == 0 After 24h

**Story:** G-EXIT-24H
**Trigger:** `canary_closed == 0` after 24 hours from deployment
**Expected By:** 24-48h after initial deployment

### Escalation Packet

```
SUBJECT: [G-EXIT-24H] URGENT: Canary not closed within 24h - Intervention Required

STORY: G-EXIT-24H
PRIORITY: P1
GATE: G-Exit-24h (canary_closed == 0 after 24h)

EXPECTED BEHAVIOR:
- Paper trading orchestrator should have closed at least 1 canary position
- canary_metrics.get_canary_close_count(since_hours=24) should return >= 1
- Realized PnL path should be functional

ACTUAL BEHAVIOR:
- canary_metrics.get_canary_close_count(since_hours=24) = 0
- No position close events recorded in Redis sorted set
- Running realized PnL = $0.00

DIAGNOSTIC STEPS RUN:
1. python3 scripts/verify_g_exit_24h.py
   - Canary closes (24h): 0
   - Canary closes (48h): 0
   - Realized PnL (24h): $0.00

2. Check Redis keys:
   - bmad:chiseai:canary:closes (should have entries)
   - bmad:chiseai:canary:realized_pnl (should have value)

3. Check orchestrator logs for:
   - close_position() calls
   - [G-EXIT-24H] Canary close recorded messages

4. Check position tracker:
   - Are positions being opened?
   - Are positions being closed?

ROOT CAUSE HYPOTHESIS (ranked by likelihood):
1. Orchestrator not receiving signals to process
2. Positions opened but close_position() not being called
3. Redis connection issue preventing canary_metrics from recording
4. canary_metrics instrumentation not properly integrated in orchestrator

RECOMMENDED ACTIONS:
1. Verify signal pipeline is active and emitting signals
2. Check position_tracker for open positions
3. Verify Redis connectivity for canary_metrics
4. Review orchestrator close_position() integration
5. If no positions being opened, check signal generator and consumer

ESCALATED TO: Aria/Jarvis
TIMESTAMP: {timestamp}
```

---

## Realized PnL Path Broken

**Story:** G-EXIT-24H
**Trigger:** `canary_closed > 0` but realized PnL not recording correctly
**Expected By:** 24-48h after first canary close

### Escalation Packet

```
SUBJECT: [G-EXIT-24H] WARNING: Canary closes detected but Realized PnL path not functioning

STORY: G-EXIT-24H
PRIORITY: P2
GATE: G-Exit-24h (PnL path broken)

EXPECTED BEHAVIOR:
- When canary position closes, realized_pnl is recorded
- canary_metrics.record_canary_close() is called with position_id and realized_pnl
- Redis sorted set is populated with close event
- Running realized_pnl is incremented

ACTUAL BEHAVIOR:
- Canary closes detected (count > 0)
- Realized PnL (24h) = $0.00 or doesn't match expected value
- Running realized PnL may be inconsistent with individual close records

DIAGNOSTIC STEPS RUN:
1. python3 scripts/verify_g_exit_24h.py
   - Canary closes (24h): {count}
   - Realized PnL (24h): $0.00

2. Check Redis for individual close records:
   - KEYS bmad:chiseai:canary:close:*
   - HGETALL on each close record to verify realized_pnl stored

3. Check orchestrator close_position() integration:
   - Is record_canary_close() being called?
   - Are parameters (position_id, realized_pnl) correct?

ROOT CAUSE HYPOTHESIS (ranked by likelihood):
1. record_canary_close() not being called in orchestrator
2. realized_pnl parameter being passed as 0 or None
3. Redis hash set failing silently
4. Fallback file not being written correctly

RECOMMENDED ACTIONS:
1. Verify orchestrator code has canary_metrics.record_canary_close() call
2. Check that realized_pnl is being extracted correctly from position
3. Verify Redis write operations are not failing
4. Add debug logging to record_canary_close() to trace issues
5. Check fallback file path and write permissions

ESCALATED TO: Aria/Jarvis
TIMESTAMP: {timestamp}
```

---

## Diagnostic Command Reference

```bash
# Check G-Exit-24h status
python3 scripts/verify_g_exit_24h.py

# Check Redis keys
redis-cli ZCOUNT bmad:chiseai:canary:closes -inf +inf
redis-cli GET bmad:chiseai:canary:realized_pnl

# Check for individual close records
redis-cli KEYS bmad:chiseai:canary:close:*

# Check fallback file
cat data/canary_closes.json

# Check orchestrator logs for canary instrumentation
grep -i "G-EXIT-24H" /path/to/logs/orchestrator.log
grep -i "canary close recorded" /path/to/logs/orchestrator.log
```
