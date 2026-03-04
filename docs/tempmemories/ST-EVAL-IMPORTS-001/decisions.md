# Key Decisions - ST-EVAL-IMPORTS-001

## Decision 1: Relative Imports for Container Compatibility
**Decision**: Changed absolute imports to relative imports in src/evaluation/ modules
**Rationale**: Absolute imports (from evaluation.X) fail in Docker containers where PYTHONPATH doesn't include src/
**Impact**: All evaluation cycles (6h, daily, weekly) now execute successfully in Docker
**Date**: 2026-03-03

## Decision 2: Keep Both During Merge Conflict
**Decision**: During merge conflict with ST-REFLECT-RUNTIME-001, preserved both LLM integration and import fixes
**Rationale**: Both branches added valuable, non-conflicting functionality
**Impact**: Final codebase has both Docker compatibility AND LLM-powered insights
**Date**: 2026-03-03

## Learning: Import Path Conventions
**Pattern**: Use relative imports (from .X) within packages, absolute (from src.X) from outside
**Anti-pattern**: Bare package imports (from evaluation.X) break in containerized environments
**Prevention**: Add import path validation to CI

## Redis Storage
- Key: `bmad:chiseai:decisions:ST-EVAL-IMPORTS-001`
- Fields: decision, rationale, timestamp, impact
- Status: Successfully written to Redis
