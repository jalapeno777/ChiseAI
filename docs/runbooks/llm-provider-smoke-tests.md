# LLM Provider Smoke Tests

**Story ID**: LLM-PROVIDER-FIX-001-LOCKIN
**Phase**: C - Lock-in Reproducibility
**Last Updated**: 2026-03-12

---

## Overview

This runbook provides exact smoke test commands for validating LLM provider connectivity. Use these commands before E2E tests to ensure all providers are operational.

## Canonical Provider Configuration

| Provider | Endpoint | Default Model | API Key Env Var |
|----------|----------|---------------|-----------------|
| KIMI (Direct Coding) | `https://api.kimi.com/coding/v1` | `kimi-for-coding` | `KIMI_API_KEY` |
| KIMI (Adapter) | `http://chiseai-kimi-adapter:8002/v1` | `kimi-for-coding` | `KIMI_API_KEY` |
| Z.ai Coding | `https://api.z.ai/api/coding/paas/v4` | `glm-5` | `ZAI_API_KEY` |
| Zhipu | Alias of Z.ai in provider chain | `glm-5` | `ZHIPU_API_KEY` |

---

## Smoke Test Commands

### 1. KIMI Direct (Coding API)

```bash
# Test KIMI direct endpoint
curl -s -w "\nHTTP Status: %{http_code}\nLatency: %{time_total}s\n" \
  -X POST "https://api.kimi.com/coding/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $KIMI_API_KEY" \
  -H "User-Agent: claude-code/0.1.0" \
  -d '{
    "model": "kimi-for-coding",
    "messages": [{"role": "user", "content": "Reply with OK"}],
    "max_tokens": 64,
    "thinking": {"type": "disabled"}
  }'
```

**Expected Response (Success):**
```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "choices": [{
    "message": {"role": "assistant", "content": "OK"},
    "finish_reason": "stop"
  }],
  "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7}
}
HTTP Status: 200
Latency: 1.234s
```

**Error Responses:**
- `401 Invalid Authentication` - API key invalid or expired
- `403 Forbidden` - Access tier restriction (Coding Agent only)

### 2. KIMI via Adapter (Container Environment)

```bash
# Test KIMI adapter (from within container or same network)
curl -s -w "\nHTTP Status: %{http_code}\nLatency: %{time_total}s\n" \
  -X POST "http://chiseai-kimi-adapter:8002/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $KIMI_API_KEY" \
  -d '{
    "model": "kimi-for-coding",
    "messages": [{"role": "user", "content": "Reply with OK"}],
    "max_tokens": 10
  }'
```

**Note:** Use `host.docker.internal:8002` if testing from outside Docker but adapter is in container.

### 3. Z.ai Coding Endpoint

```bash
# Test Z.ai coding endpoint
curl -s -w "\nHTTP Status: %{http_code}\nLatency: %{time_total}s\n" \
  -X POST "https://api.z.ai/api/coding/paas/v4/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ZAI_API_KEY" \
  -d '{
    "model": "glm-5",
    "messages": [{"role": "user", "content": "Reply with OK"}],
    "max_tokens": 10
  }'
```

**Expected Response (Success):**
```json
{
  "id": "xxx",
  "choices": [{
    "message": {"content": "OK", "role": "assistant"},
    "finish_reason": "stop"
  }],
  "usage": {"total_tokens": 10}
}
HTTP Status: 200
Latency: 1.456s
```

**Error Responses:**
- `400 Unknown Model` - Invalid model name (use `glm-5`)
- `429 Insufficient Balance` - Account quota exhausted (code 1113)

### 4. Zhipu Alias (Provider-chain only)

```bash
# ZHIPU is treated as deprecated alias to ZAI in provider_chain.
# Use Z.ai smoke tests above for endpoint verification.
python - <<'PY'
from llm.provider_chain import LLMProviderChain
print("zhipu alias behavior: configured provider name maps to zai")
PY
```

**Note:** `zhipu` remains accepted as input for compatibility, but it is canonicalized to `zai`.

---

## Reassessment Procedure (If Failures Reappear)

Run this sequence in order and capture outputs in a dated evidence file under `docs/evidence/`.

1. Container health and routing
```bash
docker ps --filter name=chiseai-api-final --filter name=chiseai-kimi-adapter
docker exec chiseai-api-final env | grep -E '^(KIMI|ZAI|ZHIPU|MINIMAX)_'
```
2. Direct provider probes (must return HTTP 200 with non-empty `choices[0].message.content`)
```bash
docker exec chiseai-api-final bash -lc 'python - <<\"PY\"
import os, json, urllib.request
checks = [
  ("KIMI", os.getenv("KIMI_BASE_URL","").rstrip("/") + "/chat/completions",
   {"Content-Type":"application/json","Authorization":"Bearer "+os.getenv("KIMI_API_KEY",""),"User-Agent":"claude-code/0.1.0"},
   {"model":os.getenv("KIMI_MODEL","kimi-for-coding"),"messages":[{"role":"user","content":"Reply with OK"}],"max_tokens":64,"thinking":{"type":"disabled"}}),
  ("ZAI", "https://api.z.ai/api/coding/paas/v4/chat/completions",
   {"Content-Type":"application/json","Authorization":"Bearer "+(os.getenv("ZAI_API_KEY") or os.getenv("ZHIPU_API_KEY",""))},
   {"model":"glm-5","messages":[{"role":"user","content":"Reply with OK"}],"max_tokens":64,"thinking":{"type":"disabled"}}),
]
for name, url, headers, payload in checks:
  req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
  with urllib.request.urlopen(req, timeout=60) as r:
    data = json.loads(r.read().decode("utf-8","replace"))
    content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content","")
    print(name, r.status, bool(content.strip()), content[:100])
PY'
```
3. Chain probes (must return `success=true` with non-empty content)
```bash
docker exec chiseai-api-final bash -lc 'python - <<\"PY\"
import asyncio
from llm.provider_chain import LLMProviderChain
async def main():
    for order in (["kimi_compat"], ["zai"]):
        r = await LLMProviderChain(provider_order=order).query("One short sentence with kiwi.")
        print(order, r.success, r.provider, bool((r.content or "").strip()), r.error.message if r.error else None)
asyncio.run(main())
PY'
```
4. If KIMI returns empty `content` with 200, verify `thinking` is disabled through adapter and provider chain.
5. If adapter returns 403/401, ensure status code is preserved (not converted to 500), then fallback to `zai` should occur.

---

## Quick Preflight Check

Run the automated preflight script:

```bash
# From project root
./scripts/preflight/llm_provider_check.sh
```

Expected output:
```
=== LLM Provider Preflight Check ===
Timestamp: 2026-03-06T09:45:00Z

[1/4] Testing KIMI Direct    ... OK    (1.23s)
[2/4] KIMI Adapter           ... SKIP  (adapter not available)
[3/4] Z.ai Coding            ... FAIL  (401: Invalid API key)
[4/4] Zhipu                  ... FAIL  (429: Quota exhausted)

Summary: 1/4 working, 2 failed, 1 skipped
Exit Code: 1
```

---

## Troubleshooting

### KIMI 401 Invalid Authentication

1. Verify API key is set:
   ```bash
   echo "Key length: ${#KIMI_API_KEY}"
   ```

2. Check key validity at Moonshot console

3. Test key directly:
   ```bash
   curl -H "Authorization: Bearer $KIMI_API_KEY" \
        https://api.moonshot.cn/v1/models
   ```

### Z.ai/Zhipu 429 Quota Exhausted

1. Check account balance at https://open.bigmodel.cn/
2. Purchase credits or resource package
3. Wait for quota reset if daily limit reached

### Connection Timeout

1. Verify DNS resolution:
   ```bash
   nslookup api.moonshot.cn
   nslookup api.z.ai
   nslookup open.bigmodel.cn
   ```

2. Test connectivity:
   ```bash
   curl -v https://api.moonshot.cn/v1/models
   ```

---

## Related Documents

- [LLM Provider Mapping](./llm-provider-mapping.md)
- [LLM Provider Troubleshooting](./llm-provider-troubleshooting.md)

---

## Change History

| Date | Change | Author |
|------|--------|--------|
| 2026-03-06 | Initial creation for LLM-PROVIDER-FIX-001 Phase C | Dev Agent |
| 2026-03-12 | Updated to coding endpoints, zhipu alias behavior, and reassessment procedure after live fix validation | Codex |
