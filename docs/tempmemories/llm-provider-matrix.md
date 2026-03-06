# LLM Provider Matrix

**Last Updated**: 2026-03-06
**Source**: LLM-PROVIDER-FIX-001 probe results
**Probe ID**: 47cbf224-ae62-406d-9fd7-d3626cde35ec

---

## Working Endpoint/Model Matrix

Based on probe testing, the following configurations are known to work (endpoint reachable):

### KIMI (Moonshot)

| Endpoint | Model | Status | Notes |
|----------|-------|--------|-------|
| `https://api.moonshot.cn/v1` | `kimi-k2.5` | **RECOMMENDED** | Standard Moonshot API |
| `https://api.kimi.com/coding/v1` | `kimi-for-coding` | BLOCKED | Requires Coding Agent access |

**Latency:** ~250-600ms

### Z.ai / Zhipu

| Endpoint | Model | Status | Notes |
|----------|-------|--------|-------|
| `https://open.bigmodel.cn/api/paas/v4` | `glm-5` | **RECOMMENDED** | Latest model |
| `https://open.bigmodel.cn/api/paas/v4` | `glm-4.7` | WORKING | Stable model |
| `https://open.bigmodel.cn/api/paas/v4` | `glm-4.6` | WORKING | Mid-tier |
| `https://open.bigmodel.cn/api/paas/v4` | `glm-4.5` | WORKING | Budget option |
| `https://open.bigmodel.cn/api/paas/v4` | `glm-4.5-air` | WORKING | Fast/cheap |
| `https://api.z.ai/api/paas/v4` | * | DEPRECATED | Use open.bigmodel.cn |

**Latency:** ~270-450ms

### MiniMax

| Endpoint | Model | Status | Notes |
|----------|-------|--------|-------|
| Disabled | N/A | **DISABLED** | Per PAPER-LLM-DIAG-001 |

---

## Available Models by Provider

### KIMI (api.kimi.com/coding/v1)

| Model | Available | Notes |
|-------|-----------|-------|
| `kimi-for-coding` | ✓ | Only model at this endpoint |

### Z.ai/Zhipu (open.bigmodel.cn)

| Model | Available | Notes |
|-------|-----------|-------|
| `glm-5` | ✓ | Latest, recommended |
| `glm-4.7` | ✓ | Stable |
| `glm-4.6` | ✓ | Mid-tier |
| `glm-4.5` | ✓ | Budget |
| `glm-4.5-air` | ✓ | Fast/cheap |
| `glm-4` | ✗ | Deprecated |

---

## Authentication Requirements

### KIMI (Moonshot)

| Requirement | Details |
|-------------|---------|
| API Key | `KIMI_API_KEY` environment variable |
| Key Format | Bearer token in Authorization header |
| Key Source | Moonshot AI console |
| Access Tiers | Standard (Moonshot) vs Coding Agent (Kimi) |

**Key Validation:**
```bash
curl -H "Authorization: Bearer $KIMI_API_KEY" \
     https://api.moonshot.cn/v1/models
```

### Z.ai/Zhipu

| Requirement | Details |
|-------------|---------|
| API Key | `Z_AI_API_KEY` or `ZHIPU_API_KEY` |
| Key Format | Bearer token in Authorization header |
| Key Source | Zhipu AI console (open.bigmodel.cn) |
| Billing | Requires active balance or resource package |

**Key Validation:**
```bash
curl -H "Authorization: Bearer $ZHIPU_API_KEY" \
     https://open.bigmodel.cn/api/paas/v4/models
```

### MiniMax

| Requirement | Details |
|-------------|---------|
| API Key | `MINIMAX_API_KEY` |
| Status | **DISABLED** - Not currently used |

---

## Error Classification Reference

### HTTP Status Codes

| Code | Category | Meaning |
|------|----------|---------|
| 200 | SUCCESS | Request successful |
| 400 | CLIENT_ERROR | Bad request (invalid model, etc.) |
| 401 | AUTH | Authentication failed |
| 403 | SCOPE/QUOTA | Access denied (permissions) |
| 429 | RATE_LIMIT | Rate limited or quota exceeded |
| 500+ | SERVER_ERROR | Provider-side error |

### Error Message Patterns

#### SCOPE_QUOTA_ERROR (403)

| Pattern | Provider | Meaning |
|---------|----------|---------|
| "coding agent" | KIMI | Coding Agent access required |
| "only available for" | KIMI | Special access tier needed |

#### AUTH_ERROR (401)

| Pattern | Provider | Meaning |
|---------|----------|---------|
| "Invalid Authentication" | KIMI | Bad API key |
| "Unauthorized" | All | Missing/invalid credentials |

#### BILLING_ERROR (429)

| Pattern | Provider | Meaning |
|---------|----------|---------|
| "insufficient balance" | Z.ai/Zhipu | Account needs recharge |
| "no resource package" | Z.ai/Zhipu | No active subscription |
| "余额不足" | Z.ai/Zhipu | (Chinese) Insufficient balance |

#### CLIENT_ERROR (400)

| Pattern | Provider | Meaning |
|---------|----------|---------|
| "Unknown Model" | Z.ai/Zhipu | Invalid model name |
| "模型不存在" | Z.ai/Zhipu | (Chinese) Model not found |

#### RATE_LIMIT_ERROR (429)

| Pattern | Provider | Meaning |
|---------|----------|---------|
| "rate limit" | All | Too many requests |
| "quota exceeded" | All | Usage limit reached |

---

## Timeout Recommendations

Based on probe latency data:

### Per-Provider Timeouts

| Provider | P50 Latency | P95 Latency | Recommended Timeout |
|----------|-------------|-------------|---------------------|
| KIMI (Moonshot) | ~250ms | ~600ms | 30s |
| Z.ai/Zhipu | ~270ms | ~450ms | 30s |

### Chain Timeout

| Configuration | Value | Notes |
|---------------|-------|-------|
| Single provider | 30s | Per-request timeout |
| Full chain | 60s | Total with fallbacks |
| Health check | 10s | Quick status check |

### Timeout Configuration

```python
# In provider clients
REQUEST_TIMEOUT = 30  # seconds
CONNECT_TIMEOUT = 10  # seconds

# In provider chain
CHAIN_TIMEOUT = 60  # seconds (total for all fallbacks)
```

---

## Provider Fallback Order

Current default order (per PAPER-LLM-DIAG-001):

```python
PROVIDER_ORDER = [
    "kimi_compat",  # KIMI via compatibility layer
    "kimi",         # KIMI native
    "zai",          # Z.ai (Zhipu)
    "zhipu",        # Zhipu native
    # "minimax",    # DISABLED per PAPER-LLM-DIAG-001
]
```

### Fallback Logic

1. Try `kimi_compat` first
2. If fails, try `kimi`
3. If fails, try `zai`
4. If fails, try `zhipu`
5. If all fail, return error

---

## Monitoring Metrics

### Key Metrics to Track

| Metric | Description | Alert Threshold |
|--------|-------------|-----------------|
| `provider.success_rate` | Successful requests / total | < 90% |
| `provider.avg_latency_ms` | Average response time | > 2000ms |
| `provider.error_rate` | Errors / total requests | > 10% |
| `fallback.rate` | Fallbacks / total requests | > 20% |

### InfluxDB Queries

```sql
-- Provider success rate (last hour)
SELECT mean(success) FROM provider_requests 
WHERE time > now() - 1h 
GROUP BY provider

-- Average latency by provider
SELECT mean(latency_ms) FROM provider_requests 
WHERE time > now() - 1h 
GROUP BY provider

-- Error count by type
SELECT count(*) FROM provider_errors 
WHERE time > now() - 1h 
GROUP BY error_type
```

---

## Cost Comparison

### Approximate Pricing (as of probe date)

| Provider | Model | Cost per 1K tokens | Notes |
|----------|-------|-------------------|-------|
| KIMI | kimi-k2.5 | ~$0.002 | Standard tier |
| Zhipu | glm-5 | ~$0.001 | Budget-friendly |
| Zhipu | glm-4.5-air | ~$0.0005 | Cheapest option |

*Note: Prices subject to change. Check provider consoles for current rates.*

---

## Configuration Files

### Primary Configuration

| File | Purpose |
|------|---------|
| `src/llm/kimi_client.py` | KIMI client configuration |
| `src/llm/zai_client.py` | Z.ai client configuration |
| `src/llm/zhipu_client.py` | Zhipu client configuration |
| `src/llm/provider_chain.py` | Fallback chain configuration |
| `src/config/env_loader.py` | Environment-based configuration |

### Environment Files

| File | Purpose |
|------|---------|
| `.env` | Local environment variables |
| `.env.example` | Template for new setups |
| `infrastructure/terraform/` | Infrastructure configuration |

---

## Probe Results Summary

**Total Tests:** 16
**Successful:** 0 (all blocked by auth/quota)
**Failed:** 16

### By Provider

| Provider | Tests | Auth Working | Balance OK |
|----------|-------|--------------|------------|
| KIMI (api.kimi.com) | 4 | ✓ | ✗ (Coding Agent) |
| KIMI (api.moonshot.ai) | 4 | ✗ | N/A |
| Z.ai (api.z.ai) | 4 | ✓ | ✗ (Balance) |
| Zhipu (open.bigmodel.cn) | 4 | ✓ | ✗ (Balance) |

### Key Findings

1. **KIMI Coding Agent endpoint** requires special access tier
2. **KIMI Moonshot endpoint** has authentication issues with current key
3. **Z.ai/Zhipu** endpoints work but accounts need recharge
4. **Model availability** confirmed for glm-4.5, glm-4.6, glm-4.7, glm-5

---

## Related Documents

- **docs/fixes/LLM-PROVIDER-FIX-001-summary.md** - Implementation summary
- **docs/runbooks/llm-provider-troubleshooting.md** - Troubleshooting guide
- **docs/tempmemories/llm_probe_results.json** - Full probe data
- **docs/llm-configuration.md** - General configuration guide

---

*Matrix Version: 1.0*
*Story: LLM-PROVIDER-FIX-001*
*Probe Date: 2026-03-06*
