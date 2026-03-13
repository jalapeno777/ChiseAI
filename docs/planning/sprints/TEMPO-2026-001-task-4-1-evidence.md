# TEMPO-2026-001 Task 4.1 Evidence

**Task:** 4.1 - Instrument API endpoints
**Story ID:** TEMPO-2026-001
**Phase:** 4 (Service Coverage)
**Date:** 2026-03-13
**Status:** Complete

## Changes Made

### src/api/main.py
- Added tracing initialization with `init_tracing("chiseai-api")`
- Instrumented FastAPI app with `instrument_fastapi(app)`
- Added lifespan context manager with startup/shutdown spans
- Added health and readiness endpoints with custom spans
- Included trades router

### src/api/routes/trades.py
- Created trades router with CRUD endpoints
- Added custom spans to all endpoints:
  - `create_trade` span with trade attributes (symbol, side, quantity, user_id)
  - `get_trade` span with trade_id attribute
  - `list_trades` span with filter attributes
  - `cancel_trade` span with action attribute
- All spans include ChiseAI-specific attributes:
  - `chiseai.trade.*` for trade-related data
  - `chiseai.user.id` for user identification
  - `chiseai.endpoint` for endpoint tracking

### src/api/routes/__init__.py
- Created routes module with trades router export

### tests/test_api/test_tracing.py
- Created comprehensive tracing tests
- Tests for all endpoints:
  - Health endpoint
  - Readiness endpoint
  - Trade creation
  - Trade retrieval
  - Trade listing
  - Trade cancellation
- All tests verify HTTP responses
- Note: Actual span verification requires Tempo integration

## Verification

- FastAPI auto-instrumentation: ✅ Configured
- Custom spans: ✅ Added to trade endpoints
- Tests: ✅ Created and passing

## Result

API service ready to emit traces to Tempo.

## Files Modified

1. `src/api/main.py` - Main FastAPI application with tracing
2. `src/api/routes/trades.py` - Trades router with custom spans
3. `src/api/routes/__init__.py` - Routes module initialization
4. `tests/test_api/test_tracing.py` - Tracing tests

## Next Steps

Ready for Task 4.2: Instrument strategy engine with OpenTelemetry tracing.
