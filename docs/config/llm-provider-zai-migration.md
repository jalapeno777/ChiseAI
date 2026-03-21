# LLM Provider Configuration Migration: Z.AI as Primary

**Story ID**: LLM-CONFIG-ZAI-PRIMARY-001  
**Date**: 2026-03-21  
**Author**: quickdev

## Summary

This document describes the required configuration changes to switch the primary LLM provider from KIMI to Z.AI (GLM-5).

## Required Changes

### 1. Update `.env` file

Make the following changes to your local `.env` file:

#### Change 1: Update ZHIPU_API_BASE endpoint

```diff
- ZHIPU_API_BASE=https://api.z.ai/api/paas/v4/chat/completions
+ ZHIPU_API_BASE=https://api.z.ai/api/coding/paas/v4/chat/completions
```

**Rationale**: The North American Coding Plan API endpoint provides better performance and is the recommended endpoint for Z.AI (GLM-5).

#### Change 2: Disable KIMI direct access

Add or update the following line:

```
KIMI_ENABLED=false
```

**Rationale**: Disables direct KIMI API calls to ensure all LLM traffic routes through Z.AI.

#### Change 3: Disable KIMI adapter

```diff
- KIMI_COMPAT_ENABLED=true
+ KIMI_COMPAT_ENABLED=false
```

**Rationale**: Disables the KIMI adapter to prevent fallback to KIMI infrastructure.

### 2. Verify Configuration

After making changes, verify:

1. **Z.AI endpoint is correct**:

   ```bash
   grep ZHIPU_API_BASE .env
   # Should output: ZHIPU_API_BASE=https://api.z.ai/api/coding/paas/v4/chat/completions
   ```

2. **KIMI is disabled**:

   ```bash
   grep KIMI_ENABLED .env
   # Should output: KIMI_ENABLED=false

   grep KIMI_COMPAT_ENABLED .env
   # Should output: KIMI_COMPAT_ENABLED=false
   ```

3. **Z.AI credentials are configured**:
   ```bash
   grep Z_AI_API_KEY .env
   grep Z_AI_MODEL .env
   # Should output: Z_AI_MODEL=glm-5
   ```

## Rollback

To rollback to KIMI:

1. Set `KIMI_ENABLED=true`
2. Set `KIMI_COMPAT_ENABLED=true`
3. Revert `ZHIPU_API_BASE` to previous value (if needed)

## References

- Z.AI North American Coding Plan API Documentation
- Story: LLM-CONFIG-ZAI-PRIMARY-001
- Decision: Craig's directive to disable KIMI and use Z.AI as primary
