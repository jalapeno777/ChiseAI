# LLM Provider Mapping

## Overview

This document provides the canonical mapping of LLM providers, endpoints, and configuration for the ChiseAI Neuro-Symbolic Brain System.

## ⚠️ CRITICAL: Mandatory Bridge Route for KIMI

**KIMI MUST route through the `chiseai-kimi-adapter` container.**

This is not optional. All Kimi API calls must go through the OpenAI-compatible adapter at `http://chiseai-kimi-adapter:8002/v1`.

### Why Mandatory?

- **Infrastructure Consistency**: Ensures all Kimi traffic routes through a controlled, observable endpoint
- **Error Handling**: Adapter provides standardized error responses and retry logic
- **Security**: Centralizes API key management and request validation
- **Observability**: Enables unified logging and metrics collection

### Configuration Requirement

```bash
KIMI_COMPAT_ENABLED=true  # MUST be true
KIMI_COMPAT_BASE_URL=http://chiseai-kimi-adapter:8002/v1
```

Direct API calls to `https://api.moonshot.cn/v1` are deprecated and may be disabled in future releases.

## Provider Configuration

| Provider | Endpoint | Model | API Key Env | Status | Notes |
|----------|----------|-------|-------------|--------|-------|
| **KIMI (via adapter)** | http://chiseai-kimi-adapter:8002/v1 | kimi-for-coding | KIMI_API_KEY | **MANDATORY** | OpenAI-compatible adapter - REQUIRED route |
| KIMI (direct) | https://api.moonshot.cn/v1 | kimi-k2.5 | KIMI_API_KEY | Deprecated | Direct API access - DO NOT USE |
| Z.ai/Zhipu Group | https://api.z.ai/api/paas/v4 | glm-5 | ZAI_API_KEY or ZHIPU_API_KEY | Active | Usage-equivalent providers (see grouping below) |
| MiniMax | N/A | N/A | MINIMAX_API_KEY | **DISABLED** | Removed from provider chain - DO NOT USE |

## Endpoint Details

### KIMI (via Adapter)

**Endpoint:** `http://chiseai-kimi-adapter:8002/v1`

**Model:** `kimi-for-coding`

**API Key:** `KIMI_API_KEY`

**Description:**
- OpenAI-compatible adapter service running on ChiseAI infrastructure
- Preferred for local development and containerized deployments
- Provides transparent compatibility with OpenAI SDK patterns
- Adapter service handles Kimi-specific request/response mapping

**When to Use:**
- Development environments with chiseai-kimi-adapter available
- Container-based deployments (docker-compose, k8s)
- When OpenAI SDK compatibility is required

### KIMI (Direct)

**Endpoint:** `https://api.moonshot.cn/v1`

**Model:** `kimi-k2.5`

**API Key:** `KIMI_API_KEY`

**Description:**
- Direct access to Moonshot AI's API
- No intermediate adapter layer
- Lower latency for production workloads

**When to Use:**
- Production deployments without local adapter
- When direct API access is required
- High-throughput scenarios where adapter overhead is not acceptable

### Z.ai/Zhipu

**Endpoint:** `https://api.z.ai/api/coding/paas/v4`

**Model:** `glm-5`

**API Key:** `ZAI_API_KEY` or `ZHIPU_API_KEY`

**Description:**
- Zhipu AI's coding-optimized endpoint
- GLM-5 model with reasoning capabilities
- Provides `reasoning_content` field for chain-of-thought output

**When to Use:**
- When reasoning traces are required for debugging/analysis
- Alternative to KIMI for neuro-symbolic reasoning tasks
- When explicit chain-of-thought is beneficial

**Important Notes:**
- This is the coding-specific endpoint (NOT `https://open.bigmodel.cn`)
- The endpoint supports the `thinking` parameter to enable reasoning content
- Response structure differs from OpenAI-compatible format

## Z.AI / Zhipu Provider Group

**Zhipu and Z.AI are usage-equivalent providers that both use the `api.z.ai` endpoint.**

### What This Means

- Both providers offer the same GLM-5 model with identical capabilities
- They share the same endpoint: `https://api.z.ai/api/paas/v4/chat/completions`
- Either `ZAI_API_KEY` or `ZHIPU_API_KEY` can be used interchangeably
- The provider chain treats them as alternatives within the same group

### Provider Chain Behavior

In `src/llm/provider_chain.py`:
- `zai` provider: Uses `ZAI_API_KEY` (or falls back to `Z_AI_API_KEY`)
- `zhipu` provider: Uses `ZHIPU_API_KEY` (or falls back to `ZAI_API_KEY`)

Both route to the same endpoint and can use either API key due to automatic fallback logic.

### Configuration

```bash
# Option 1: Use ZAI_API_KEY
ZAI_API_KEY=your_api_key_here
ZAI_ENABLED=true

# Option 2: Use ZHIPU_API_KEY
ZHIPU_API_KEY=your_api_key_here
ZHIPU_ENABLED=true

# Option 3: Use either key for either provider (fallback works both ways)
ZAI_API_KEY=your_api_key_here
ZHIPU_ENABLED=true  # Will use ZAI_API_KEY as fallback
```

### When to Use

- Use Z.AI/Zhipu as the secondary provider when KIMI (via adapter) is unavailable
- Both providers are functionally equivalent - choose based on which API key you have
- The provider chain will try `zai` first, then fall back to `zhipu`

## MiniMax - DISABLED

**MiniMax has been permanently disabled and removed from the provider fallback chain.**

### Status

- **Enabled by default**: `false` (in `PROVIDER_CONFIGS`)
- **In provider_order**: Commented out
- **Reason for removal**: Insufficient API balance and unreliable service

### Do Not Enable

```python
# In src/llm/provider_chain.py, MiniMax is commented out:
self.provider_order = [
    "kimi_compat",  # MANDATORY - Kimi via adapter
    "kimi",         # Direct Kimi (fallback)
    "zai",          # Z.AI (GLM-5)
    "zhipu",        # Zhipu (GLM-4.7)
    # "minimax",    # DISABLED - Removed per PAPER-LLM-DIAG-001
]
```

### Historical Context

MiniMax was disabled per `PAPER-LLM-DIAG-001` due to:
- API balance issues (status_code: 1008 - Insufficient balance)
- Unreliable service availability
- Better alternatives available (KIMI adapter, Z.AI/Zhipu)

To re-enable (not recommended):
1. Uncomment `"minimax"` from `provider_order`
2. Set `MINIMAX_ENABLED=true`
3. Verify `MINIMAX_API_KEY` is valid with sufficient balance
4. Test with: `python -m pytest tests/test_llm/test_provider_chain.py -v -k minimax`

## Reasoning Field Contract

### Z.ai/GLM-5

**Field Location:** `choices[0].message.reasoning_content`

**When Present:**
- Only when the `thinking` parameter is enabled in the request
- Contains the chain-of-thought reasoning trace
- Separate from the main response content

**Example:**
```json
{
  "choices": [
    {
      "message": {
        "content": "Final answer here",
        "reasoning_content": "Chain of thought reasoning...",
        "role": "assistant"
      }
    }
  ]
}
```

### KIMI

**Field Location:** Check for `reasoning_content` field in message

**When Present:**
- Depends on model capabilities and request parameters
- May be present in responses that include reasoning

**Example:**
```json
{
  "choices": [
    {
      "message": {
        "content": "Final answer here",
        "reasoning_content": "Reasoning trace if available",
        "role": "assistant"
      }
    }
  ]
}
```

### TradeDecision Integration

**Field:** `reasoning_content`

**Description:**
- The `TradeDecision` object includes a `reasoning_content` field
- This field stores the raw reasoning from the LLM provider
- Used for debugging, audit trails, and neuro-symbolic analysis

**Usage:**
```python
trade_decision = TradeDecision(
    action="BUY",
    symbol="BTCUSDT",
    reasoning_content=llm_response["choices"][0]["message"].get("reasoning_content", ""),
    # ... other fields
)
```

## Configuration Examples

### Using KIMI Adapter (Preferred)

```bash
# .env
KIMI_API_KEY=your_kimi_api_key_here
KIMI_ENABLED=true
KIMI_COMPAT_ENABLED=true
KIMI_COMPAT_BASE_URL=http://chiseai-kimi-adapter:8002/v1
```

### Using KIMI Direct

```bash
# .env
KIMI_API_KEY=your_kimi_api_key_here
KIMI_ENABLED=true
KIMI_COMPAT_ENABLED=false
KIMI_BASE_URL=https://api.moonshot.cn/v1
```

### Using Z.ai/GLM-5

```bash
# .env
ZAI_API_KEY=your_zai_api_key_here
# or
ZHIPU_API_KEY=your_zhipu_api_key_here

# Enable Z.ai
ZAI_ENABLED=true
# or
ZHIPU_ENABLED=true

# Note: Endpoint is configured in the brain/LLM client code
# https://api.z.ai/api/coding/paas/v4
```

## Adapter vs Direct API Decision Tree

```
Start
  │
  ├─→ Is chiseai-kimi-adapter available?
  │     ├─→ Yes → Use KIMI adapter (preferred)
  │     │          - http://chiseai-kimi-adapter:8002/v1
  │     │          - OpenAI-compatible
  │     │
  │     └─→ No → Can you use direct API?
  │                ├─→ Yes → Use KIMI direct
  │                │          - https://api.moonshot.cn/v1
  │                │          - Direct access
  │                │
  │                └─→ No → Use Z.ai/Zhipu
  │                           - https://api.z.ai/api/coding/paas/v4
  │                           - With reasoning support
```

## Troubleshooting

### KIMI Adapter Issues

1. **Check adapter is running:**
   ```bash
   docker ps | grep chiseai-kimi-adapter
   ```

2. **Check adapter health:**
   ```bash
   curl http://chiseai-kimi-adapter:8002/health
   ```

3. **Verify network connectivity:**
   - Ensure containers are on `chiseai` network
   - Check DNS resolution of `chiseai-kimi-adapter`

### Z.ai Endpoint Issues

1. **Verify correct endpoint:**
   - Must use `https://api.z.ai/api/coding/paas/v4`
   - NOT `https://open.bigmodel.cn` (incorrect)

2. **Check API key:**
   - Ensure `ZAI_API_KEY` or `ZHIPU_API_KEY` is set
   - Verify key is valid and active

3. **Test with thinking parameter:**
   ```bash
   curl -X POST https://api.z.ai/api/coding/paas/v4/chat/completions \
     -H "Authorization: Bearer $ZAI_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{
       "model": "glm-5",
       "messages": [{"role": "user", "content": "Hello"}],
       "thinking": true
     }'
   ```

## Related Documentation

- [LLM Provider Troubleshooting](./llm-provider-troubleshooting.md)
- [Environment Bootstrap](./env-bootstrap.md)
- [API Disconnect Handling](./api-disconnect.md)

## Changelog

### 2026-03-06 - LLM-PROVIDER-FIX-002
- Corrected Z.ai endpoint from `https://open.bigmodel.cn` to `https://api.z.ai/api/coding/paas/v4`
- Documented reasoning field contract for Z.ai/GLM-5 (`reasoning_content`)
- Added KIMI adapter vs direct API decision tree
- Created canonical endpoint mapping table
