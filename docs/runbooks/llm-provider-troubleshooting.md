# LLM Provider Troubleshooting Runbook

**Last Updated**: 2026-03-06
**Related Stories**: LLM-PROVIDER-FIX-001, PAPER-LLM-DIAG-001

---

## Quick Reference

### Provider Health Check Command

```bash
# Standard health check with colored output
python3 scripts/provider_health_check.py

# JSON output for CI/monitoring
python3 scripts/provider_health_check.py --json

# Quiet mode (errors only)
python3 scripts/provider_health_check.py --quiet
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All configured providers healthy |
| 1 | One or more providers failed |

---

## Provider Configuration Reference

### Current Endpoints

| Provider | Endpoint | Default Model |
|----------|----------|---------------|
| KIMI | `https://api.moonshot.cn/v1` | `kimi-k2.5` |
| Z.ai | `https://open.bigmodel.cn/api/paas/v4` | `glm-5` |
| Zhipu | `https://open.bigmodel.cn/api/paas/v4` | `glm-5` |
| MiniMax | Disabled | N/A |

### Environment Variables

```bash
# KIMI
KIMI_API_KEY=required
KIMI_BASE_URL=https://api.moonshot.cn/v1
KIMI_MODEL=kimi-k2.5

# Z.ai (Zhipu alias)
Z_AI_API_KEY=required
ZAI_BASE_URL=https://open.bigmodel.cn/api/paas/v4
ZAI_MODEL=glm-5

# Zhipu
ZHIPU_API_KEY=required
ZHIPU_BASE_URL=https://open.bigmodel.cn/api/paas/v4
ZHIPU_MODEL=glm-5

# MiniMax (disabled)
MINIMAX_API_KEY=required
MINIMAX_ENABLED=false
```

---

## Common Errors and Remediation

### KIMI Errors

#### Error: 403 "Coding Agent" Restriction

```
Error: "Kimi For Coding is currently only available for Coding Agents 
such as Kimi CLI, Claude Code, Roo Code, Kilo Code, etc."
Status: 403 Forbidden
```

**Root Cause:** API key lacks Coding Agent access tier.

**Remediation:**
1. Use standard Moonshot API endpoint (`https://api.moonshot.cn/v1`)
2. Contact Moonshot support for Coding Agent access enrollment
3. Use Z.ai/Zhipu as fallback provider

**Verification:**
```bash
curl -H "Authorization: Bearer $KIMI_API_KEY" \
     https://api.moonshot.cn/v1/models
```

---

#### Error: 401 Invalid Authentication

```
Error: "Invalid Authentication"
Status: 401 Unauthorized
```

**Root Cause:** Invalid or expired API key.

**Remediation:**
1. Verify `KIMI_API_KEY` is set correctly
2. Check key has not expired at Moonshot console
3. Regenerate key if compromised

**Verification:**
```bash
echo $KIMI_API_KEY | head -c 10  # Check first 10 chars
python3 -c "from src.config.env_loader import discover_kimi_config; print(discover_kimi_config())"
```

---

### Z.ai/Zhipu Errors

#### Error: 429 "Insufficient Balance"

```
Error: "Insufficient balance or no resource package. Please recharge."
Error: "余额不足或无可用资源包,请充值。" (Chinese)
Status: 429 Too Many Requests
```

**Root Cause:** Account balance depleted or no resource package.

**Remediation:**
1. Add credits at https://open.bigmodel.cn/
2. Purchase a resource package
3. Use KIMI as primary provider temporarily

**Verification:**
```bash
# Check account balance via API (if endpoint available)
curl -H "Authorization: Bearer $ZHIPU_API_KEY" \
     https://open.bigmodel.cn/api/paas/v4/account/balance
```

---

#### Error: 400 "Unknown Model"

```
Error: "Unknown Model, please check the model code."
Error: "模型不存在,请检查模型代码。" (Chinese)
Status: 400 Bad Request
```

**Root Cause:** Using deprecated or incorrect model name.

**Remediation:**
1. Use valid models: `glm-4.5`, `glm-4.5-air`, `glm-4.6`, `glm-4.7`, `glm-5`
2. Avoid: `glm-4` (deprecated)

**Valid Models:**
```bash
# Check available models
curl -H "Authorization: Bearer $ZHIPU_API_KEY" \
     https://open.bigmodel.cn/api/paas/v4/models
```

---

### Network/Connection Errors

#### Error: Connection Timeout

```
Error: "Connection timed out" or "Request timed out"
```

**Root Cause:** Network issue or slow provider response.

**Remediation:**
1. Check internet connectivity
2. Verify firewall allows outbound HTTPS
3. Check DNS resolution
4. Increase timeout if needed (default: 60s)

**Verification:**
```bash
# Test DNS
nslookup api.moonshot.cn
nslookup open.bigmodel.cn

# Test connectivity
curl -v https://api.moonshot.cn/v1/models
curl -v https://open.bigmodel.cn/api/paas/v4/models
```

---

#### Error: SSL Certificate Error

```
Error: "SSL: CERTIFICATE_VERIFY_FAILED"
```

**Root Cause:** System CA certificates outdated or proxy interference.

**Remediation:**
1. Update CA certificates: `sudo update-ca-certificates`
2. Check for corporate proxy configuration
3. Verify system time is correct

---

### Provider Chain Errors

#### Error: "No providers available"

```
Error: "All LLM providers failed or unavailable"
```

**Root Cause:** All providers in chain are failing.

**Remediation:**
1. Run health check: `python3 scripts/provider_health_check.py`
2. Check at least one API key is configured
3. Review logs for specific errors
4. Check provider status pages

**Diagnostic Commands:**
```bash
# Check provider availability
python3 -c "
from src.config.env_loader import diagnose_provider_availability
import json
print(json.dumps(diagnose_provider_availability(), indent=2))
"

# Check provider chain status
python3 -c "
from src.llm.provider_chain import LLMProviderChain
chain = LLMProviderChain()
print(chain.get_provider_status())
"
```

---

#### Error: "Chain not initialized"

```
Error: "Chain not initialized but enabled"
```

**Root Cause:** Provider chain failed to initialize during startup.

**Remediation:**
1. Check logs for initialization errors
2. Verify at least one provider has valid credentials
3. Restart the application

**Debug Steps:**
```python
from src.llm.provider_chain import LLMProviderChain
from src.execution.llm.trade_decision_enhancer import TradeDecisionEnhancer

# Check chain
chain = LLMProviderChain(enable_metrics=True)
print(f"Providers: {chain.provider_order}")
print(f"Status: {chain.get_provider_status()}")

# Check enhancer
enhancer = TradeDecisionEnhancer(enabled=True)
print(f"Health: {enhancer.health_check()}")
```

---

## Diagnostic Procedures

### Full Provider Diagnostic

```bash
# 1. Environment check
python3 -c "
from src.config.env_loader import (
    discover_kimi_config,
    discover_zai_config,
    discover_zhipu_config,
    discover_minimax_config,
)
print('KIMI:', discover_kimi_config())
print('ZAI:', discover_zai_config())
print('ZHIPU:', discover_zhipu_config())
print('MINIMAX:', discover_minimax_config())
"

# 2. Health check
python3 scripts/provider_health_check.py

# 3. Provider chain status
python3 -c "
from src.llm.provider_chain import LLMProviderChain
chain = LLMProviderChain()
for provider, status in chain.get_provider_status().items():
    print(f'{provider}: {status}')
"

# 4. Connection test
python3 -c "
import asyncio
from src.llm.kimi_client import KimiClient, KimiConfig
from src.llm.zai_client import ZaiClient, ZaiConfig

async def test():
    # Test KIMI
    try:
        async with KimiClient(KimiConfig()) as client:
            result = await client.health_check()
            print(f'KIMI: {result}')
    except Exception as e:
        print(f'KIMI Error: {e}')
    
    # Test Z.ai
    try:
        async with ZaiClient(ZaiConfig()) as client:
            result = await client.health_check()
            print(f'ZAI: {result}')
    except Exception as e:
        print(f'ZAI Error: {e}')

asyncio.run(test())
"
```

### Log Analysis

```bash
# Check for LLM-related errors
grep -i "llm\|provider\|kimi\|zhipu" /var/log/chiseai/app.log | tail -100

# Check for provider chain issues
grep -i "chain\|fallback\|provider" /var/log/chiseai/app.log | tail -50

# Check for timeout issues
grep -i "timeout\|timed out" /var/log/chiseai/app.log | tail -50
```

---

## Escalation Path

### Level 1: Self-Service
1. Run health check script
2. Check environment variables
3. Review common errors above

### Level 2: Operations
1. Check provider status pages
2. Verify account balance/quotas
3. Review application logs
4. Test with curl directly

### Level 3: Engineering
1. Debug provider client code
2. Check for API changes
3. Review error classification logic
4. Consider fallback configuration

### Level 4: Vendor
1. Contact Moonshot support (KIMI)
2. Contact Zhipu support (Z.ai)
3. Check for service outages

---

## Related Documents

- **docs/fixes/LLM-PROVIDER-FIX-001-summary.md** - Implementation details
- **docs/fixes/PAPER-LLM-DIAG-001-fix-summary.md** - MiniMax disablement
- **docs/tempmemories/llm-provider-matrix.md** - Provider configuration matrix
- **docs/llm-configuration.md** - General LLM configuration guide

---

## Change History

| Date | Change | Author |
|------|--------|--------|
| 2026-03-06 | Initial creation for LLM-PROVIDER-FIX-001 | Dev Agent |

---

*Runbook Version: 1.0*
*Story: LLM-PROVIDER-FIX-001*
