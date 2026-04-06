---
type: investigation
story_id: PAPER-HEALTH-2026-04-06
date: 2026-04-06
managed_by: jarvis
priority: critical
needs_manual_qdrant_import: false
---

# Fill Tracking Issues — Paper Trading Health Check (2026-04-06)

## Executive Summary

During paper trading health check, discovered that 35 fills occurred on Bybit demo but **zero** fills were recorded locally in Redis/Postgres. Root cause analysis identified three distinct bugs that must all be fixed.

---

## Issue FT-001: No Fill Polling Loop (CRITICAL — PRIMARY ROOT CAUSE)

**File**: `src/data/exchange/bybit_demo_connector.py`

**Problem**: When Bybit returns `status: "Created"` (pending order), the connector never checks back for fills. There is no polling loop, no WebSocket subscription, and no reconciliation mechanism to detect when orders are filled.

**Impact**: Orders placed and filled on Bybit are never detected locally. This is the **PRIMARY** reason 35 fills existed on Bybit but 0 were recorded in Redis/Postgres.

**Evidence**:

- Bybit demo API shows 35 fills on 2026-04-06
- Redis has zero `paper:outcomes*`, `paper:fill*`, `paper:order*`, or `paper:position*` keys
- Signal tracking (`paper:signals:processed`) works fine — only fill recording is broken

**Fix Required** (choose one):

1. Polling loop that checks order status every N seconds until filled/cancelled
2. WebSocket subscription to Bybit's order/fill stream
3. Reconciliation daemon that periodically queries Bybit and reconciles with local state (see BL-RECONCILIATION-MONITOR-001)

---

## Issue FT-002: LLM Enhancer Dead Code Blocks Enhanced Trades (HIGH)

**File**: `src/trading/paper/orchestrator.py` (around line 865-871)

**Problem**: A `return PaperTradeResult()` statement executes regardless of the `go_no_go` decision value, blocking all enhanced trades from reaching the execution path properly.

**Impact**: Even when the LLM enhancer approves a trade, the dead code return prevents the trade from proceeding through the normal execution path. Only 1 actionable signal in ~12 hours resulted in an order, and that order stayed pending.

**Evidence**: Only 1 actionable signal in ~12 hours resulted in an order, and that order stayed pending. The dead code path may be routing trades through a non-standard path that bypasses fill tracking.

**Fix Required**: Fix the conditional logic so that:

- `go_no_go=True` → proceeds to execution
- `go_no_go=False` → returns the no-trade result

---

## Issue FT-003: OutcomeCaptureService Never Started (HIGH — CONTRIBUTING)

**File**: `scripts/run_trading_activity.py` (around line 343)

**Problem**: The code uses `OutcomeCaptureIntegration` to bridge signals to outcomes, but the WebSocket-based `BybitFillListener` that could detect fills is instantiated but never started.

**Impact**: Even if fills were happening, the service that would record them is not running.

**Evidence**: `OutcomeCaptureIntegration initialized: enabled=True` appears in logs, but no fill events are ever captured.

**Fix Required** (choose one):

1. Start the `BybitFillListener` WebSocket connection
2. Implement the polling-based alternative from FT-001
3. Rely on reconciliation daemon (BL-RECONCILIATION-MONITOR-001) as safety net

---

## Critical Backlog Items

All three issues have been entered into Redis critical backlog:

- `bmad:chiseai:backlog:critical:BL-FILL-TRACKING-001` — FT-001 fill polling loop
- `bmad:chiseai:backlog:critical:BL-FILL-TRACKING-002` — FT-002 dead code fix
- `bmad:chiseai:backlog:critical:BL-FILL-TRACKING-003` — FT-003 start fill listener
- `bmad:chiseai:backlog:critical:BL-RECONCILIATION-MONITOR-001` — Reconciliation monitor (safety net)

## Related Documentation

- Design: `docs/tempmemories/reconciliation-monitor-design.md`
- Bybit connection: `docs/tempmemories/bybit-demo-connection-guide.md`
- Session close: `docs/tempmemories/session-close-2026-04-06-normalization.md`
