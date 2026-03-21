# LLM Provider Endpoint Fix Implementation Plan

> **Story ID:** ST-LLM-ENDPOINT-FIX-001  
> **Status:** Planning  
> **Created:** 2026-03-06  
> **Priority:** High  
> **Impact:** Critical - All LLM provider integrations affected

---

## Executive Summary

This document outlines the implementation plan to fix incorrect LLM provider endpoints and model identifiers across the ChiseAI codebase. Based on research findings, the current configurations use deprecated or incorrect endpoints that may cause API failures.

### Key Issues Identified

| Provider | Current (Wrong) | Correct (Official) | Impact |
|----------|-----------------|-------------------|--------|
| **KIMI** | `https://api.kimi.com/coding/v1` | `https://api.moonshot.cn/v1` | Complete API failure |
| **KIMI Model** | `k2p5` | `kimi-k2.5` | Model not found errors |
| **Z.ai/Zhipu** | `https://api.z.ai/api/paas/v4` | `https://open.bigmodel.cn/api/paas/v4` | Intermittent failures |

---

## 1. Root Cause Analysis

### 1.1 Why Current Endpoints Are Wrong

#### KIMI Endpoint Issue
- **Current endpoint** (`api.kimi.com/coding/v1`) appears to be an internal or deprecated endpoint
- **Official Moonshot AI documentation** specifies `api.moonshot.cn/v1` as the correct base URL
- The `kimi.com` domain may have been used during beta/early access but is not the production endpoint
- Model identifier `k2p5` is not recognized; official identifier is `kimi-k2.5`

#### Z.ai/Zhipu Endpoint Issue
- **Current endpoint** (`api.z.ai/api/paas/v4`) is the global/Z.ai-specific endpoint
- **Official Zhipu SDK** uses `open.bigmodel.cn/api/paas/v4` as the primary endpoint
- While `api.z.ai` may work, it's not the officially documented endpoint
- The `open.bigmodel.cn` endpoint is more reliable and better supported

### 1.2 System Impact

| Component | Impact Level | Description |
|-----------|--------------|-------------|
| LLM Provider Chain | **Critical** | Primary provider (KIMI) will fail without fallback |
| Agent Swarm | **High** | Agents depend on LLM for task execution |
| Trade Decision Enhancer | **High** | LLM-based trade decisions will fail |
| Kimi Adapter | **Critical** | Adapter forwards to wrong endpoint |
| Environment Bootstrap | **Medium** | Wrong defaults in discovery functions |
| Tests | **Medium** | Test assertions use wrong expected values |

### 1.3 Evidence from Research

1. **KIMI API Documentation**: Official Moonshot AI docs specify `https://api.moonshot.cn/v1`
2. **Model Registry**: `kimi-k2.5` is the official model ID, not `k2p5`
3. **Zhipu SDK**: Official Python SDK uses `open.bigmodel.cn` as base URL
4. **Terraform Variables**: Already correctly uses `https://api.moonshot.cn/v1` (line 136 in variables.tf)

---

## 2. Files to Modify

### 2.1 Core LLM Client Files

| File | Lines | Current Issue |
|------|-------|---------------|
| `src/llm/kimi_client.py` | 43, 44 | Wrong base_url and model defaults |
| `src/llm/zai_client.py` | 40 | Wrong base_url default |
| `src/llm/zhipu_client.py` | 5, 92 | Wrong endpoint in docstring and constant |

### 2.2 Configuration Files

| File | Lines | Current Issue |
|------|-------|---------------|
| `src/config/env_loader.py` | 185, 394, 446 | Wrong defaults in load_kimi_config, discover_kimi_config, discover_zhipu_config |
| `.env.example` | 24, 43, 34 | Wrong KIMI_MODEL, commented KIMI_BASE_URL, wrong Z.ai comment |

### 2.3 Adapter and Scripts

| File | Lines | Current Issue |
|------|-------|---------------|
| `src/adapter/kimi/main.py` | 29 | Wrong KIMI_BASE_URL default |
| `scripts/diagnostic_kimi_probe.py` | 57, 58 | Hardcoded wrong URLs |
| `scripts/probe_llm_providers.py` | 93-124 | Test probes use wrong endpoints |

### 2.4 Opencode Configuration

| File | Lines | Current Issue |
|------|-------|---------------|
| `opencode.jsonc` | 47 | Wrong baseURL for kimi-for-coding provider |

### 2.5 Documentation

| File | Lines | Current Issue |
|------|-------|---------------|
| `docs/llm-configuration.md` | 8, 14, 19 | Wrong endpoints documented |
| `docs/runbooks/env-bootstrap.md` | 390 | Wrong KIMI_BASE_URL default |

### 2.6 Test Files

| File | Lines | Current Issue |
|------|-------|---------------|
| `tests/test_llm/test_kimi_client.py` | 49 | Wrong expected base_url |
| `tests/test_llm/test_zhipu_client.py` | 43 | Wrong expected endpoint |
| `tests/test_config/test_env_bootstrap.py` | 144, 176, 185 | Wrong expected URLs |
| `tests/test_llm/test_env_loading.py` | 132 | Wrong expected base_url |
| `tests/integration/test_kimi_adapter_integration.py` | 135, 142 | Wrong expected base_url |
| `tests/test_adapter/test_kimi_adapter_smoke.py` | 55 | Wrong expected base_url |

---

## 3. Changes Required

### 3.1 KIMI Provider Changes

| File | Current Value | New Value | Reason |
|------|---------------|-----------|--------|
| `src/llm/kimi_client.py:43` | `https://api.kimi.com/coding/v1` | `https://api.moonshot.cn/v1` | Official Moonshot API endpoint |
| `src/llm/kimi_client.py:44` | `k2p5` | `kimi-k2.5` | Official model identifier |
| `src/config/env_loader.py:185` | `https://api.kimi.com/coding/v1` | `https://api.moonshot.cn/v1` | Correct default base URL |
| `src/config/env_loader.py:186` | `k2p5` | `kimi-k2.5` | Correct default model |
| `src/config/env_loader.py:394` | `https://api.kimi.com/coding/v1` | `https://api.moonshot.cn/v1` | Correct discovery default |
| `src/config/env_loader.py:395` | `k2p5` | `kimi-k2.5` | Correct discovery model |
| `src/adapter/kimi/main.py:29` | `https://api.kimi.com/coding/v1` | `https://api.moonshot.cn/v1` | Adapter must use correct endpoint |
| `.env.example:24` | `kimi-for-coding` | `kimi-k2.5` | Correct model in example |
| `.env.example:43` | `https://api.kimi.com/coding/v1` | `https://api.moonshot.cn/v1` | Correct commented default |
| `opencode.jsonc:47` | `https://api.kimi.com/coding/v1` | `https://api.moonshot.cn/v1` | Correct provider baseURL |

### 3.2 Z.ai/Zhipu Provider Changes

| File | Current Value | New Value | Reason |
|------|---------------|-----------|--------|
| `src/llm/zai_client.py:40` | `https://api.z.ai/api/paas/v4/chat/completions` | `https://open.bigmodel.cn/api/paas/v4/chat/completions` | Official Zhipu SDK endpoint |
| `src/llm/zhipu_client.py:5` | `https://api.z.ai/api/paas/v4/chat/completions` | `https://open.bigmodel.cn/api/paas/v4/chat/completions` | Correct docstring |
| `src/llm/zhipu_client.py:92` | `https://api.z.ai/api/paas/v4/chat/completions` | `https://open.bigmodel.cn/api/paas/v4/chat/completions` | Correct DEFAULT_ENDPOINT |
| `src/config/env_loader.py:418` | `https://api.z.ai/v1` | `https://open.bigmodel.cn/api/paas/v4` | Correct Z.ai base URL |
| `src/config/env_loader.py:446` | `https://api.z.ai/api/paas/v4` | `https://open.bigmodel.cn/api/paas/v4` | Correct Zhipu base URL |
| `.env.example:34` | `https://api.z.ai/api/paas/v4/chat/completions` | `https://open.bigmodel.cn/api/paas/v4/chat/completions` | Correct endpoint comment |

### 3.3 Script Updates

| File | Current Value | New Value | Reason |
|------|---------------|-----------|--------|
| `scripts/diagnostic_kimi_probe.py:57` | `https://api.kimi.com/coding/v1/models` | `https://api.moonshot.cn/v1/models` | Correct models endpoint |
| `scripts/diagnostic_kimi_probe.py:58` | `https://api.kimi.com/coding/v1/chat/completions` | `https://api.moonshot.cn/v1/chat/completions` | Correct completions endpoint |

### 3.4 Test Updates

| File | Current Value | New Value | Reason |
|------|---------------|-----------|--------|
| `tests/test_llm/test_kimi_client.py:49` | `https://api.kimi.com/coding/v1` | `https://api.moonshot.cn/v1` | Correct expected URL |
| `tests/test_llm/test_kimi_client.py:50` | `k2p5` | `kimi-k2.5` | Correct expected model |
| `tests/test_config/test_env_bootstrap.py:144` | `https://api.kimi.com/coding/v1` | `https://api.moonshot.cn/v1` | Correct expected URL |
| `tests/test_config/test_env_bootstrap.py:176` | `https://api.z.ai/v1` | `https://open.bigmodel.cn/api/paas/v4` | Correct expected URL |
| `tests/test_config/test_env_bootstrap.py:185` | `https://api.z.ai/api/paas/v4` | `https://open.bigmodel.cn/api/paas/v4` | Correct expected URL |

### 3.5 Documentation Updates

| File | Current Value | New Value | Reason |
|------|---------------|-----------|--------|
| `docs/llm-configuration.md:8` | `https://api.kimi.com/coding/v1` | `https://api.moonshot.cn/v1` | Correct KIMI endpoint |
| `docs/llm-configuration.md:14` | `https://api.z.ai/api/paas/v4/chat/completions` | `https://open.bigmodel.cn/api/paas/v4/chat/completions` | Correct Z.ai endpoint |
| `docs/llm-configuration.md:19` | `https://api.z.ai/api/paas/v4/chat/completions` | `https://open.bigmodel.cn/api/paas/v4/chat/completions` | Correct Zhipu endpoint |
| `docs/runbooks/env-bootstrap.md:390` | `https://api.kimi.com/coding/v1` | `https://api.moonshot.cn/v1` | Correct default value |

---

## 4. Backward Compatibility Strategy

### 4.1 Environment Variable Overrides

All changes use environment variables as the primary configuration mechanism. The fix maintains full backward compatibility through:

1. **KIMI_BASE_URL** - Users can override to use old endpoint if needed
2. **KIMI_MODEL** - Users can specify any model identifier
3. **ZAI_BASE_URL** - Users can override Z.ai endpoint
4. **ZHIPU_BASE_URL** - Users can override Zhipu endpoint

### 4.2 Fallback Chain Preservation

The provider fallback chain remains unchanged:
1. KIMI (primary)
2. Z.ai/GLM-5 (secondary)
3. Zhipu/GLM-4.7 (tertiary)
4. MiniMax (quaternary, disabled by default)

### 4.3 Migration Path for Existing Deployments

| Scenario | Action Required |
|----------|-----------------|
| **Using defaults** | No action - defaults will be corrected |
| **Explicitly set KIMI_BASE_URL** | No action - explicit setting preserved |
| **Using KIMI_MODEL=k2p5** | Will auto-migrate to kimi-k2.5 unless explicitly overridden |
| **Custom Z.ai endpoint** | No action - explicit setting preserved |

### 4.4 Feature Flags

No feature flags required. The changes are transparent configuration updates.

---

## 5. Testing Plan

### 5.1 Unit Tests to Update

| Test File | Tests to Update | Expected Changes |
|-----------|-----------------|------------------|
| `tests/test_llm/test_kimi_client.py` | `test_default_config` | Update base_url and model assertions |
| `tests/test_llm/test_zhipu_client.py` | `test_init_with_api_key` | Update DEFAULT_ENDPOINT assertion |
| `tests/test_config/test_env_bootstrap.py` | `test_discover_kimi_config_with_key`, `test_discover_zai_config_with_key`, `test_discover_zhipu_config_with_key` | Update expected URL assertions |
| `tests/test_llm/test_env_loading.py` | Test at line 132 | Update expected base_url |
| `tests/integration/test_kimi_adapter_integration.py` | Tests at lines 135, 142 | Update expected kimi_base_url |
| `tests/test_adapter/test_kimi_adapter_smoke.py` | Test at line 55 | Update expected KIMI_BASE_URL |

### 5.2 Integration Tests

| Test | Purpose | Success Criteria |
|------|---------|------------------|
| `test_kimi_client_live.py` | Verify KIMI client connects to correct endpoint | HTTP 200 response from api.moonshot.cn |
| `test_zai_client_live.py` | Verify Z.ai client connects to correct endpoint | HTTP 200 response from open.bigmodel.cn |
| `test_provider_chain_fallback.py` | Verify fallback chain works | Falls back correctly when primary fails |
| `test_kimi_adapter_integration.py` | Verify adapter uses correct endpoint | Health check returns correct base_url |

### 5.3 Live Validation Steps

```bash
# 1. Validate KIMI endpoint connectivity
python3 -c "
import os
os.environ['KIMI_API_KEY'] = 'your-key-here'
from src.llm.kimi_client import KimiClient, KimiConfig
config = KimiConfig()
print(f'Base URL: {config.base_url}')
print(f'Model: {config.model}')
assert config.base_url == 'https://api.moonshot.cn/v1'
assert config.model == 'kimi-k2.5'
print('✓ KIMI config validated')
"

# 2. Validate Z.ai endpoint connectivity
python3 -c "
import os
os.environ['ZAI_API_KEY'] = 'your-key-here'
from src.llm.zai_client import ZaiClient, ZaiConfig
config = ZaiConfig()
print(f'Base URL: {config.base_url}')
assert config.base_url == 'https://open.bigmodel.cn/api/paas/v4/chat/completions'
print('✓ Z.ai config validated')
"

# 3. Run diagnostic probe
python3 scripts/diagnostic_kimi_probe.py

# 4. Run provider probe
python3 scripts/probe_llm_providers.py

# 5. Run test suite
pytest tests/test_llm/ -v
pytest tests/test_config/ -v
```

### 5.4 Smoke Tests

| Test | Command | Expected Result |
|------|---------|-----------------|
| KIMI client instantiation | `python3 -c "from src.llm.kimi_client import KimiConfig; c = KimiConfig(); print(c.base_url, c.model)"` | `https://api.moonshot.cn/v1 kimi-k2.5` |
| Z.ai client instantiation | `python3 -c "from src.llm.zai_client import ZaiConfig; c = ZaiConfig(); print(c.base_url)"` | `https://open.bigmodel.cn/api/paas/v4/chat/completions` |
| Environment discovery | `python3 -c "from src.config.env_loader import discover_kimi_config; print(discover_kimi_config())"` | Correct base_url and model |

---

## 6. Risk Assessment

### 6.1 High Risk Items

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **Existing API keys don't work with new endpoint** | Medium | Critical | Test API key compatibility before deployment; keep old endpoint as fallback via env var |
| **Model identifier change breaks existing code** | Medium | High | Support both `k2p5` and `kimi-k2.5` in model discovery; update code to handle both |
| **Tests fail due to hardcoded assertions** | High | Medium | Update all test assertions as part of this fix |
| **Documentation becomes inconsistent** | Medium | Low | Update all docs in single PR; use search to find all references |

### 6.2 Medium Risk Items

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **Z.ai endpoint change affects existing integrations** | Low | Medium | Test Z.ai connectivity; provide env var override |
| **Kimi adapter fails with new endpoint** | Low | High | Test adapter thoroughly; verify health endpoint |
| **Terraform deployment affected** | Low | Medium | Terraform already uses correct endpoint; verify no conflicts |

### 6.3 Low Risk Items

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **Performance degradation** | Low | Low | Monitor latency after deployment; new endpoints should be faster |
| **Breaking change for external users** | Low | Medium | Document in CHANGELOG; provide migration guide |

### 6.4 Mitigation Strategies

1. **Staged Rollout**
   - Deploy to staging environment first
   - Run full integration test suite
   - Monitor for 24 hours before production

2. **Rollback Plan**
   - Keep old endpoint accessible via environment variable
   - Document rollback procedure
   - Have hotfix branch ready

3. **Monitoring**
   - Add metrics for provider health checks
   - Alert on increased error rates
   - Monitor fallback chain activation

---

## 7. Implementation Order

### Phase 1: Core Configuration (Priority: Critical)

**Files:**
1. `src/llm/kimi_client.py` - Update defaults (lines 43, 44)
2. `src/llm/zai_client.py` - Update base_url (line 40)
3. `src/llm/zhipu_client.py` - Update endpoint (lines 5, 92)
4. `src/config/env_loader.py` - Update all defaults (lines 185, 186, 394, 395, 418, 446)

**Verification:**
```bash
python3 -c "from src.llm.kimi_client import KimiConfig; c = KimiConfig(); assert c.base_url == 'https://api.moonshot.cn/v1'; assert c.model == 'kimi-k2.5'"
python3 -c "from src.llm.zai_client import ZaiConfig; c = ZaiConfig(); assert c.base_url == 'https://open.bigmodel.cn/api/paas/v4/chat/completions'"
```

### Phase 2: Adapter and Scripts (Priority: High)

**Files:**
1. `src/adapter/kimi/main.py` - Update KIMI_BASE_URL (line 29)
2. `scripts/diagnostic_kimi_probe.py` - Update URLs (lines 57, 58)
3. `scripts/probe_llm_providers.py` - Update test probes (lines 93-124)

**Verification:**
```bash
python3 -c "import os; os.environ['KIMI_BASE_URL'] = 'https://api.moonshot.cn/v1'; from src.adapter.kimi.main import KIMI_BASE_URL; assert KIMI_BASE_URL == 'https://api.moonshot.cn/v1'"
```

### Phase 3: Environment and Documentation (Priority: Medium)

**Files:**
1. `.env.example` - Update examples (lines 24, 34, 43)
2. `opencode.jsonc` - Update provider config (line 47)
3. `docs/llm-configuration.md` - Update docs (lines 8, 14, 19)
4. `docs/runbooks/env-bootstrap.md` - Update runbook (line 390)

**Verification:**
```bash
grep -n "api.moonshot.cn" .env.example docs/llm-configuration.md
```

### Phase 4: Test Updates (Priority: High)

**Files:**
1. `tests/test_llm/test_kimi_client.py` - Update assertions (lines 49, 50)
2. `tests/test_llm/test_zhipu_client.py` - Update assertions (line 43)
3. `tests/test_config/test_env_bootstrap.py` - Update assertions (lines 144, 176, 185)
4. `tests/test_llm/test_env_loading.py` - Update assertions (line 132)
5. `tests/integration/test_kimi_adapter_integration.py` - Update assertions (lines 135, 142)
6. `tests/test_adapter/test_kimi_adapter_smoke.py` - Update assertions (line 55)

**Verification:**
```bash
pytest tests/test_llm/test_kimi_client.py::TestKimiConfig::test_default_config -v
pytest tests/test_config/test_env_bootstrap.py::TestProviderDiscovery -v
```

### Phase 5: Integration Testing (Priority: Critical)

**Steps:**
1. Run full test suite: `pytest tests/ -v`
2. Run diagnostic scripts: `python3 scripts/diagnostic_kimi_probe.py`
3. Run provider probe: `python3 scripts/probe_llm_providers.py`
4. Test live connectivity with actual API keys
5. Verify fallback chain works

**Verification:**
```bash
pytest tests/ -xvs
python3 scripts/diagnostic_kimi_probe.py
python3 scripts/probe_llm_providers.py
```

### Phase 6: Deployment (Priority: Critical)

**Steps:**
1. Create PR with all changes
2. Run CI pipeline
3. Deploy to staging
4. Run smoke tests
5. Deploy to production
6. Monitor for 24 hours

---

## 8. File Change Summary

### Total Files to Modify: 17

| Category | Count | Files |
|----------|-------|-------|
| **Core LLM Clients** | 3 | `kimi_client.py`, `zai_client.py`, `zhipu_client.py` |
| **Configuration** | 2 | `env_loader.py`, `.env.example` |
| **Adapter/Scripts** | 3 | `main.py` (adapter), `diagnostic_kimi_probe.py`, `probe_llm_providers.py` |
| **Opencode Config** | 1 | `opencode.jsonc` |
| **Documentation** | 2 | `llm-configuration.md`, `env-bootstrap.md` |
| **Tests** | 6 | `test_kimi_client.py`, `test_zhipu_client.py`, `test_env_bootstrap.py`, `test_env_loading.py`, `test_kimi_adapter_integration.py`, `test_kimi_adapter_smoke.py` |

### Lines Changed Estimate

| Category | Estimated Lines Changed |
|----------|------------------------|
| Source code | ~25 lines |
| Configuration | ~15 lines |
| Scripts | ~10 lines |
| Documentation | ~10 lines |
| Tests | ~20 lines |
| **Total** | **~80 lines** |

---

## 9. Estimated Effort

### Story Points: **5**

### Breakdown

| Task | Hours | Complexity |
|------|-------|------------|
| Core client updates | 2h | Medium |
| Configuration updates | 1h | Low |
| Adapter and script updates | 1h | Low |
| Documentation updates | 1h | Low |
| Test updates | 2h | Medium |
| Integration testing | 2h | Medium |
| Code review and fixes | 1h | Low |
| **Total** | **10h** | - |

### Dependencies

- None - This is a self-contained configuration fix

### Parallelization

- Can be split into two parallel workstreams:
  1. **Core + Config** (Senior Dev)
  2. **Tests + Docs** (Dev)

---

## 10. Success Criteria

### Must Have (P0)

- [ ] All KIMI endpoints use `https://api.moonshot.cn/v1`
- [ ] All KIMI models use `kimi-k2.5`
- [ ] All Z.ai/Zhipu endpoints use `https://open.bigmodel.cn/api/paas/v4`
- [ ] All tests pass
- [ ] Diagnostic scripts report correct endpoints

### Should Have (P1)

- [ ] Documentation updated
- [ ] Environment example files updated
- [ ] Integration tests pass with live API keys

### Nice to Have (P2)

- [ ] Performance metrics show improvement
- [ ] Error rates decrease

---

## 11. Rollback Procedure

If issues are detected after deployment:

1. **Immediate Rollback (Hotfix)**
   ```bash
   # Set environment variables to use old endpoints
   export KIMI_BASE_URL=https://api.kimi.com/coding/v1
   export KIMI_MODEL=k2p5
   export ZAI_BASE_URL=https://api.z.ai/api/paas/v4
   export ZHIPU_BASE_URL=https://api.z.ai/api/paas/v4
   ```

2. **Code Rollback**
   ```bash
   git revert <commit-hash>
   git push origin main
   ```

3. **Verification**
   ```bash
   python3 scripts/diagnostic_kimi_probe.py
   pytest tests/test_llm/ -v
   ```

---

## 12. Post-Implementation Tasks

- [ ] Update CHANGELOG.md
- [ ] Notify team of endpoint changes
- [ ] Update any external documentation
- [ ] Monitor error rates for 48 hours
- [ ] Create follow-up story to remove old endpoint support (if desired)

---

## Appendix A: Reference Documentation

### Official API Documentation

- **Moonshot AI (KIMI)**: https://platform.moonshot.cn/docs
- **Zhipu AI**: https://open.bigmodel.cn/dev/howuse/introduction

### Related Files

- `infrastructure/terraform/variables.tf` - Already has correct KIMI endpoint
- `infrastructure/docker/docker-compose.kimi-adapter.yml` - Uses correct endpoint

### Related Stories

- ST-KIMI-ADAPTER-001: Kimi Adapter Wiring
- CH-KIMI-FIX-001: Model discovery and 403 handling
- SAFETY-LLM-001: LLM diagnostic findings

---

*Document generated by Senior Dev Agent*  
*Based on research findings from web-research agent*