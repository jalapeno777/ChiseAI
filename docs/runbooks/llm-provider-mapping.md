# LLM Provider Mapping

## Overview

This document provides the canonical mapping of LLM providers, endpoints, and configuration for the ChiseAI Neuro-Symbolic Brain System.

## Provider Configuration

| Provider | Endpoint | Model | API Key Env | Notes |
|----------|----------|-------|-------------|-------|
| KIMI (via adapter) | http://chiseai-kimi-adapter:8002/v1 | kimi-for-coding | KIMI_API_KEY | OpenAI-compatible adapter (preferred for local infra) |
| KIMI (direct) | https://api.moonshot.cn/v1 | kimi-k2.5 | KIMI_API_KEY | Direct API access |
| Z.ai/Zhipu | https://api.z.ai/api/coding/paas/v4 | glm-5 | ZAI_API_KEY or ZHIPU_API_KEY | Coding endpoint for NA |

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
