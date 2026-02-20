---
project: ChiseAI
scope: iteration-log
type: iterlog
story_id: BURNIN-001
story_title: "TBD"
phase: implementation
status: completed
started_at: "2026-02-20T02:11:56Z"
needs_manual_qdrant_import: true
---

## Decisions

- Fixed symbol format mismatch in price cache population (BURNIN-001)
- Changed from "BTCUSDT" to "BTC/USDT" format to match signal.token used by orchestrator
- Price must be set BEFORE process_signal is called

## Learnings

- Root cause: Symbol format mismatch between price cache key ("BTCUSDT") and signal.token ("BTC/USDT")
- MarketDataProvider.get_price() uses exact key match with .upper() but doesn't normalize slashes
- The fix ensures consistent symbol format throughout the trading cycle

## Scope Ownership

- src:execution:paper:orchestrator.py: BURNIN-001/senior-dev/2026-02-20T02:11:56Z
- src:execution:paper:order_simulator.py: BURNIN-001/senior-dev/2026-02-20T02:11:56Z
- src:signal_generation:models.py: BURNIN-001/senior-dev/2026-02-20T02:11:56Z
- TBD

## Incidents

- TBD

## Evidence

- Fix applied in scripts/run_trading_activity.py (lines 617-627)
- Added regression test: test_price_cache_populated_before_trading
- All 24 tests in tests/test_trading_activity/ pass
- Smoke test passed: scripts/smoke_test_price_cache.py
- Symbol format now consistent: "BTC/USDT" matches signal.token format
