# LLM Provider Configuration

**Story ID**: LLM-PROVIDER-FIX-001-LOCKIN
**Phase**: C - Lock-in Reproducibility
**Last Updated**: 2026-03-12

---

## Overview

This document provides the canonical provider mapping and configuration defaults for all LLM providers used in the ChiseAI system. This is the single source of truth for endpoint URLs, model names, and environment variables.

---

## Canonical Provider Configuration

### Provider Endpoint Reference Table

| Provider | Canonical Endpoint | Default Model | API Key Env Var | Status |
|----------|-------------------|---------------|-----------------|--------|
| **KIMI Direct** | `https://api.kimi.com/coding/v1` | `kimi-for-coding` | `KIMI_API_KEY` | Operational |
| **KIMI Adapter** | `http://chiseai-kimi-adapter:8002/v1` | `kimi-for-coding` | `KIMI_API_KEY` | Infrastructure OK |
| **Z.ai Coding** | `https://api.z.ai/api/coding/paas/v4` | `glm-5` | `ZAI_API_KEY` | Operational |
| **Zhipu** | Alias of Z.ai in provider chain | `glm-5` | `ZHIPU_API_KEY` | Deprecated alias |

---

## Environment Variable Reference

### Required Variables

| Variable | Provider | Required For | Example Value |
|----------|----------|--------------|---------------|
| `KIMI_API_KEY` | KIMI (Direct + Adapter) | Production inference | `sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` |
| `ZAI_API_KEY` | Z.ai Coding | Alternative provider | `xxxxxxxx.xxxxxxxxxxxxxxxxxxxxxxxx` |
| `ZHIPU_API_KEY` | Zhipu | Alternative provider | `xxxxxxxx.xxxxxxxxxxxxxxxxxxxxxxxx` |

### Optional Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KIMI_ENABLED` | `true` | Enable KIMI provider |
| `KIMI_COMPAT_ENABLED` | `true` | Use OpenAI-compatible adapter |
| `KIMI_COMPAT_BASE_URL` | `http://chiseai-kimi-adapter:8002/v1` | Adapter endpoint URL |
| `KIMI_BASE_URL` | `https://api.kimi.com/coding/v1` | Direct coding API endpoint URL |
| `KIMI_FALLBACK_MODEL` | `kimi-k2.5` | Fallback model when primary model is rejected |
| `ZAI_ENABLED` | `false` | Enable Z.ai provider |
| `ZHIPU_ENABLED` | `false` | Deprecated alias; canonical provider is `zai` |

---

## Model Defaults

### Primary Models

| Provider | Model | Context Window | Best For |
|----------|-------|----------------|----------|
| KIMI | `kimi-for-coding` | 256K tokens | Coding-agent optimized calls |
| KIMI (Adapter) | `kimi-for-coding` | 256K tokens | Containerized deployments |
| Z.ai | `glm-5` | 128K tokens | Reasoning with chain-of-thought |
| Zhipu | `glm-4.7` | 128K tokens | Alternative reasoning |

### Model Capabilities

| Model | Reasoning Content | Function Calling | Streaming |
|-------|------------------|------------------|-----------|
| `kimi-k2.5` | Limited | Yes | Yes |
| `kimi-for-coding` | Limited | Yes | Yes |
| `glm-5` | Yes (with `thinking` param) | Yes | Yes |
| `glm-4.7` | Yes (with `thinking` param) | Yes | Yes |

---

## Configuration Examples

### Minimal Configuration (KIMI Only)

```bash
# .env
KIMI_API_KEY=your_kimi_api_key_here
KIMI_ENABLED=true
KIMI_BASE_URL=https://api.kimi.com/coding/v1
KIMI_MODEL=kimi-for-coding
KIMI_COMPAT_ENABLED=true
```

### Full Configuration (All Providers)

```bash
# .env - Complete provider configuration

# KIMI (Primary)
KIMI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
KIMI_ENABLED=true
KIMI_COMPAT_ENABLED=true
KIMI_COMPAT_BASE_URL=http://chiseai-kimi-adapter:8002/v1
KIMI_BASE_URL=https://api.kimi.com/coding/v1
KIMI_MODEL=kimi-for-coding
KIMI_FALLBACK_MODEL=kimi-k2.5

# Z.ai (Alternative)
ZAI_API_KEY=xxxxxxxx.xxxxxxxxxxxxxxxxxxxxxxxx
ZAI_ENABLED=true

# Zhipu (deprecated alias, optional for compatibility only)
ZHIPU_API_KEY=xxxxxxxx.xxxxxxxxxxxxxxxxxxxxxxxx
ZHIPU_ENABLED=false

# MiniMax (disabled)
MINIMAX_ENABLED=false
```

### Docker Compose Environment

```yaml
services:
  chiseai-api:
    environment:
      - KIMI_API_KEY=${KIMI_API_KEY}
      - KIMI_ENABLED=true
      - KIMI_COMPAT_ENABLED=true
      - KIMI_COMPAT_BASE_URL=http://chiseai-kimi-adapter:8002/v1
      - ZAI_API_KEY=${ZAI_API_KEY:-}
      - ZHIPU_API_KEY=${ZHIPU_API_KEY:-}
```

---

## Endpoint Validation

### Quick Endpoint Tests

```bash
# Test KIMI Direct
curl -s -o /dev/null -w "%{http_code}" \
  https://api.kimi.com/coding/v1/models \
  -H "Authorization: Bearer $KIMI_API_KEY"

# Test KIMI Adapter
curl -s -o /dev/null -w "%{http_code}" \
  http://chiseai-kimi-adapter:8002/health

# Test Z.ai
curl -s -o /dev/null -w "%{http_code}" \
  https://api.z.ai/api/coding/paas/v4/models \
  -H "Authorization: Bearer $ZAI_API_KEY"

# Zhipu alias behavior is verified through provider-chain normalization tests.
```

### Expected Response Codes

| Endpoint | Valid Key | Invalid Key | No Key |
|----------|-----------|-------------|--------|
| KIMI Direct | 200 | 401 | 401 |
| KIMI Adapter | 200 | 500 (adapter error) | 500 |
| Z.ai | 200 | 401 | 401 |
| Zhipu | 200 | 401 | 401 |

---

## Current Status (Phase C)

### Credential Status

| Provider | API Key Status | Issue |
|----------|---------------|-------|
| KIMI | Valid | Direct + adapter verified (HTTP 200) |
| Z.ai | Valid | Direct verified (HTTP 200) |
| Zhipu | Deprecated alias | Canonicalized to Z.ai in provider chain |

### Infrastructure Status

| Component | Status | Notes |
|-----------|--------|-------|
| KIMI Adapter | Operational | Container running, health endpoint OK, thinking-disabled pass-through enabled |
| Network | OK | chiseai network configured |
| DNS | OK | Adapter service name resolvable in chiseai network |

---

## Runbook References

- [LLM Provider Smoke Tests](./llm-provider-smoke-tests.md) - Exact smoke test commands
- [LLM Provider Mapping](./llm-provider-mapping.md) - Detailed provider mapping
- [LLM Provider Troubleshooting](./llm-provider-troubleshooting.md) - Error resolution

---

## Change History

| Date | Change | Author |
|------|--------|--------|
| 2026-03-06 | Initial creation for LLM-PROVIDER-FIX-001 Phase C | senior-dev |
| 2026-03-06 | Documented canonical endpoints and models | senior-dev |
| 2026-03-06 | Added credential status from smoke matrix | senior-dev |
| 2026-03-12 | Updated resolved state, coding endpoint defaults, zhipu deprecation, and minimax disabled status | Codex |
