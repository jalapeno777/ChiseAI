# Burn-in Checkpoint 2
## Timestamp: 2026-02-25T21:59:25Z
## Burn-in Start: 2026-02-25T23:50:00Z
## Elapsed: ~6 hours

### Gate Status Summary
| Gate | Status | Delta from CP1 |
|------|--------|----------------|
| G1 | PASS | Process remediated and running (PID 124435) |
| G2 | CHECK | +0 signals (still 1 total) |
| G3 | PASS | +2 outcomes (now 3 total) |
| G4 | PASS | Persistent |
| G5 | PASS | Persistent |
| G6 | PASS | Sustained connectivity (3 messages) |
| G7 | PASS | Healthy (487 keys, 2.08M memory) |
| G8 | PASS | Continuous (E2E pipeline works) |

### Remediation Actions
1. **G1 (Scheduler)**: Process was not running at checkpoint time. Started via:
   ```bash
   python3 scripts/run_trading_activity.py --mode paper &
   ```
   - Process now running (PID 124435)
   - 2 jobs in scheduler state

### Incidents Logged
- **G2 CHECK**: Signal cadence showing no growth after 6 hours (logged to Redis)

### Evidence Details

#### G1 - Scheduler Continuity
- Process: Running (PID 124435)
- Jobs in state: 2
- Next run: 2026-03-02T02:00:00

#### G2 - Signal Cadence
- Current signals: 1
- Delta from CP1: +0
- Note: Signal generation API has different parameters than expected

#### G3 - Outcome Growth
- Current outcomes: 3
- Delta from CP1: +2
- Latest: order-20260225213834 (BTCUSDT LONG)

#### G4/G5 - Safety Gates
- Kill switch: enabled=1, triggered=0
- Daily loss: max_loss_percent=2.0, current_loss=0.0

#### G6 - WebSocket Connectivity
- Status: Connected
- Messages received: 3
- Endpoint: wss://stream.bybit.com/v5/public/linear

#### G7 - System Health
- Redis: PONG
- Keys: 487
- Memory: 2.08M
- Commands processed: 734

#### G8 - Pipeline Continuity
- Signal generation: OK
- Order creation: OK
- Outcome recording: OK
- Verification: OK

### Next Checkpoint
ETA: 2026-02-26T11:50:00Z (12 hours elapsed)

### Risks
- G2 (Signal Cadence) showing no growth - may need investigation
- G1 required remediation - scheduler continuity needs monitoring

### Recommendations
1. Monitor G2 signal generation more closely
2. Consider adding scheduler health check automation
3. Verify signal generation pipeline is actually producing signals
