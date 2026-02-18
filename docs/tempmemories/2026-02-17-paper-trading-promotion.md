# PAPER-LOOP-001: Key Decisions and Patterns

## Durable Decisions

### 1. Paper Trading Architecture Pattern
**Decision**: Separate paper trading module from live execution
**Rationale**: Clean separation allows safe testing without risk of accidental live trades
**Implementation**: src/execution/paper/ module with explicit paper-only types

### 2. Redis Position State Persistence
**Decision**: Use Redis with 24h TTL for position state
**Rationale**: Fast access, auto-cleanup, survives process restarts
**Trade-off**: Requires Redis availability; graceful fallback to in-memory

### 3. Async Pipeline with Correlation IDs
**Decision**: All operations async with UUID correlation IDs
**Rationale**: End-to-end tracing for debugging and audit
**Pattern**: signal_id → order_id → position_id all linked via correlation_id

## Anti-Patterns Identified

### 1. Latency Budget Violations
**Issue**: Early designs exceeded 2s target
**Solution**: Async processing, caching, batch updates
**Result**: 27ms mean latency (134x better than target)

## Prevention Rules

1. **Always test with real data**: E2E tests use real signal generation
2. **Kill-switch on every path**: All execution paths must check kill-switch state
3. **Metrics before merging**: No PR without Grafana panel evidence
