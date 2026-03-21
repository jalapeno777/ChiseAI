---
type: decision
story_id: REPO-E2E-POLICY-001
title: E2E Trade Tests Use Bybit Live-Service Path
date: 2026-03-06
status: active
author: senior-dev
---

# E2E Trade Tests Use Bybit Live-Service Path

## Decision

For E2E trade tests, use Bybit **live-service path** (`api.bybit.com`) for order placement while maintaining demo account credentials and all safety checks.

## Context

- **Previous State**: E2E tests used `BybitDemoConnector` which routed to `api-demo.bybit.com`
- **New Policy**: E2E tests use live-service API path (`api.bybit.com`) with demo credentials
- **Account Type**: Still demo/paper on Bybit side (this is about the API endpoint path, not the account type)

## Rationale

1. **Production-like validation**: Using live-service path validates that our code works against the same endpoints used in production
2. **Demo credentials work on both endpoints**: Bybit demo account credentials are valid on both `api-demo.bybit.com` and `api.bybit.com`
3. **No additional risk**: Account remains demo/paper; no real capital at risk
4. **Future-proofing**: Ensures E2E tests catch any endpoint-specific issues before production

## Implementation

### Code Changes

```python
# In scripts/testing/e2e_bybit_test.py

# Load demo credentials from environment
config = BybitConfig.from_env()
if not config.demo:
    raise SecurityException("Bybit connector is not in demo mode!")

# Override to use live-service path while keeping demo credentials
config.base_url = "https://api.bybit.com"
config.private_ws_url = "wss://stream.bybit.com/v5/private"
config.ws_url = "wss://stream.bybit.com/v5/public/linear"

connector = BybitConnector(config)
```

### Safety Checks Preserved

- [x] BYBIT_API_MODE=demo environment variable check
- [x] Kill switch status verification
- [x] Position size limits ($10 USD max)
- [x] Automatic position cleanup
- [x] Evidence recording (order IDs, timestamps, PnL)

## Files Modified

1. `scripts/testing/e2e_bybit_test.py` - Updated to use live-service path
2. `tests/test_discord_alerts/test_discord_llm_details.py` - Replaced Anthropic references with KIMI
3. `docs/runbooks/bybit-demo-routing.md` - Added E2E test configuration section

## Anthropic Removal

As part of this policy update, removed Anthropic/Claude assumptions:
- Replaced "claude-3-5-sonnet" with "kimi-k2.5" in test fixtures
- Updated assertions to check for available provider
- MiniMax remains disabled per PAPER-LLM-DIAG-001

## Current Provider Chain

1. **KIMI (K2.5)** - Primary
2. **Z.ai (GLM-5)** - Secondary
3. **Zhipu (GLM-4.7)** - Tertiary
4. **MiniMax** - Disabled

## Standard Invocation

```bash
# Set required environment variables
export BYBIT_API_MODE=demo
export BYBIT_DEMO_API_KEY="your_demo_key"
export BYBIT_DEMO_API_SECRET="your_demo_secret"
export DISCORD_TRADING_WEBHOOK_URL="your_webhook_url"

# Run E2E test
python scripts/testing/e2e_bybit_test.py
```

## Related

- Story: REPO-E2E-POLICY-001
- Previous Fix: PAPER-LLM-DIAG-001 (MiniMax disabled)
- Runbook: docs/runbooks/bybit-demo-routing.md
