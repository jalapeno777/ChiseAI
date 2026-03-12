# LLM Provider Resolution Evidence - 2026-03-12

## Summary

LLM connectivity regressions were resolved for both KIMI and Z.AI in deployed containers.

Validated on 2026-03-12 in runtime containers:
- `chiseai-api-final`
- `chiseai-kimi-adapter`

## What Was Fixed

1. Provider chain defaults and wiring
- Canonical order: `kimi_compat -> kimi -> zai`
- Deprecated `zhipu` provider name normalized to `zai`
- Fixed wrong constructor arg in trading mode loader (`provider_priority` -> `provider_order`)

2. KIMI adapter behavior
- Added support for passing `thinking` through request body
- Defaulted adapter-forwarded calls to `{"thinking":{"type":"disabled"}}` for non-empty final answer content
- Preserved upstream `HTTPException` status codes (avoid accidental 500 wrapping)
- Added content fallback from `reasoning_content` when upstream content is empty
- Fixed adapter package import path (`from .main import app`)
- Fixed adapter image build to copy adapter source into container

3. Z.AI client behavior
- Explicitly sets thinking mode:
  - enabled -> `{"thinking":{"type":"enabled"}`
  - disabled -> `{"thinking":{"type":"disabled"}`
- Provider chain now invokes Z.AI with `thinking=False` to get final answer content

4. KIMI model fallback
- Primary model: `KIMI_MODEL` (default `kimi-for-coding`)
- Fallback model: `KIMI_FALLBACK_MODEL` (default `kimi-k2.5`) on model-related failures

## Runtime Validation Results

Direct HTTP probes from `chiseai-api-final`:
- KIMI direct coding endpoint: HTTP 200, non-empty answer content
- Z.AI coding endpoint: HTTP 200, non-empty answer content

Provider-chain probes from `chiseai-api-final`:
- `provider_order=["kimi_compat"]`: success via `KIMI Compat (Adapter)`, non-empty content
- `provider_order=["zai"]`: success via `GLM-5 (Z.ai)`, non-empty content

Representative outputs:
- KIMI: "KIMI is operational and ready to process your pineapple-related inquiries."
- Z.AI: "ZAI is operational and the mango is ready."
- Chain/KIMI: "KIMI chain path works perfectly with pineapple."
- Chain/Z.AI: "The ZAI chain path works perfectly with mango integration."

## Reassessment Workflow (Future Incidents)

1. Verify container health
```bash
docker ps --filter name=chiseai-api-final --filter name=chiseai-kimi-adapter
```

2. Verify runtime env in API container
```bash
docker exec chiseai-api-final env | grep -E '^(KIMI|ZAI|ZHIPU|MINIMAX)_'
```

3. Run direct endpoint probes (KIMI and Z.AI)
- Expect HTTP 200 and non-empty `choices[0].message.content`

4. Run chain probes (`["kimi_compat"]`, `["zai"]`)
- Expect `success=true` and non-empty `LLMResponse.content`

5. If KIMI returns reasoning-only content
- Confirm `thinking` is explicitly disabled in adapter and provider chain payload

6. If adapter returns unexpected 500
- Confirm HTTPException propagation is not wrapped by generic exception handler

## Ownership Notes

- ZHIPU is retained only as compatibility alias and should not be treated as separate active provider.
- MiniMax remains disabled by policy (`MINIMAX_ENABLED=false`).

