# Local CI Speed Optimization Runbook

> **ST-LOCAL-003**: Intelligent test selection and parallel execution for faster local CI feedback

## Overview

This runbook documents the local CI speed optimization strategies implemented to reduce feedback time during development while maintaining test coverage quality.

## Problem Statement

The existing `local-ci-checks.sh` runs the full test suite on every change, which can be slow for typical development cycles where only a few files are modified.

## Solution Architecture

### Components

1. **`scripts/ci/test_selector.py`** - Intelligent test selection module
2. **`scripts/local_ci_speed_optimizations.py`** - Orchestration layer with caching and benchmarking
3. **`scripts/local-ci-checks.sh`** - Updated to use new selective testing

### Key Features

- **Intelligent Test Selection**: Maps changed source files to relevant tests using configurable patterns
- **Parallel Execution**: Improved pytest parallelization with auto-detected worker counts
- **Caching**: Persistent mapping cache to avoid recomputing test mappings
- **Benchmarking**: Built-in timing and comparison tools

## Usage

### Basic Usage

```bash
# Run selective tests (default - only tests for changed files)
python scripts/local_ci_speed_optimizations.py

# Run full test suite
python scripts/local_ci_speed_optimizations.py --full

# Run with parallel execution
python scripts/local_ci_speed_optimizations.py --parallel

# Run benchmark comparison
python scripts/local_ci_speed_optimizations.py --benchmark
```

### Test Selector CLI

```bash
# Get list of tests for changed files
python scripts/ci/test_selector.py

# Run with verbose output
python scripts/ci/test_selector.py --verbose

# Get tests as JSON for scripting
python scripts/ci/test_selector.py --json

# Force full suite
python scripts/ci/test_selector.py --full
```

### Benchmarking

```bash
# Compare selective vs full suite
python scripts/local_ci_speed_optimizations.py --compare

# Run with specific workers
python scripts/local_ci_speed_optimizations.py --parallel --workers 8
```

## Test Selection Strategy

### File Mapping Patterns

The test selector uses these patterns to find tests for changed source files:

| Source File                   | Matching Test Patterns                                        |
| ----------------------------- | ------------------------------------------------------------- |
| `src/foo/bar.py`              | `tests/test_bar.py`, `tests/foo/test_bar.py`                  |
| `src/strategy/dsl/grammar.py` | `tests/test_strong_system/test_program_synthesis/test_dsl.py` |

### Pattern Priority

1. Direct module test: `test_{stem}.py`
2. Parent module test: `{stem}_test.py`
3. Nested test: `test_{parent}/{stem}.py`
4. Parallel structure: `{parent}/test_{stem}.py`

### Fallback Behavior

When no matching tests are found:

- If Python files changed: Run syntax check only
- If no Python files changed: Exit successfully (nothing to test)

## Benchmarking Results

### Expected Performance

| Scenario          | Typical Improvement  |
| ----------------- | -------------------- |
| 1-5 file changes  | 50-80% faster        |
| 6-20 file changes | 30-50% faster        |
| 20+ file changes  | 10-30% faster        |
| Full suite        | Baseline (no change) |

### Running Benchmarks

```bash
# Full comparison
python scripts/local_ci_speed_optimizations.py --compare --parallel

# Output saved to
# _bmad-output/ci/benchmark.json
# _bmad-output/ci/benchmark-selective.json
```

### Interpreting Results

The benchmark output includes:

- `duration_seconds`: Total execution time
- `speedup_factor`: Ratio vs full suite
- `test_reduction_percent`: % fewer tests run
- `cache_used`: Whether mapping cache was used

## When to Use Full vs Selective

### Use Selective Testing When:

- ✅ Making small, targeted changes
- ✅ Working on a single module
- ✅ Running pre-commit checks locally
- ✅ Iterating rapidly during development

### Use Full Suite When:

- ✅ Making architectural changes
- ✅ Changes span multiple modules
- ✅ Running final CI before merge
- ✅ After merging main into feature branch

## Integration with local-ci-checks.sh

The `local-ci-checks.sh` script has been enhanced to support selective testing:

```bash
# Existing behavior (full suite)
./scripts/local-ci-checks.sh

# Merged-only mode (selective)
./scripts/local-ci-checks.sh --merged-only

# With parallel execution
./scripts/local-ci-checks.sh --merged-only --parallel
```

## Caching

### Cache Location

Default: `.bmad-test-cache.json` (gitignored)

### Cache Invalidation

Cache is invalidated when:

- Cache older than 1 hour
- Dependency files change (`requirements*.txt`, `pyproject.toml`, `setup.py`)
- No cached mappings exist

### Manual Cache Control

```bash
# Clear cache
rm .bmad-test-cache.json

# Use specific cache file
python scripts/local_ci_speed_optimizations.py --cache-file /tmp/test-cache.json
```

## Configuration

### Environment Variables

| Variable             | Default | Description                   |
| -------------------- | ------- | ----------------------------- |
| `PYTEST_WORKERS`     | `auto`  | Number of parallel workers    |
| `PYTEST_MAX_WORKERS` | `4`     | Maximum worker count          |
| `MAX_MERGED_TARGETS` | `40`    | Max tests in merged-only mode |

### Parallel Execution

```bash
# Auto-detect optimal workers
PYTEST_WORKERS=auto python scripts/local_ci_speed_optimizations.py --parallel

# Manual worker count
PYTEST_WORKERS=8 python scripts/local_ci_speed_optimizations.py --parallel
```

## Troubleshooting

### No Tests Found

```
$ python scripts/ci/test_selector.py
# (no output)

Reason: Changed files don't map to existing tests
Fix: Use --full flag to run complete suite
```

### Cache Miss Every Run

```
Reason: Cache file deleted or expired
Fix: Normal behavior - cache auto-regenerates
```

### Parallel Mode Errors

```
Error: pytest-xdist not installed
Fix: pip install pytest-xdist
```

## Metrics

### Quality Gates

- ✅ No reduction in test coverage
- ✅ All existing tests still run when affected
- ✅ Selective mode passes for isolated changes

### Success Criteria

- [ ] Test selector correctly maps changed files to tests
- [ ] Local CI runs 50%+ faster for typical changes (<5 files)
- [ ] Parallel execution improvements measurable
- [ ] Full suite still available via --full flag
- [ ] No reduction in test coverage or quality

## Related Documentation

- `scripts/local-ci-checks.sh` - Main CI script
- `scripts/ci/ci_change_scope.py` - Change detection
- `scripts/ci/test_selector.py` - Test selection module
- `scripts/local_ci_speed_optimizations.py` - Orchestration

## Change Log

| Date       | Change                                |
| ---------- | ------------------------------------- |
| 2026-03-26 | Initial implementation (ST-LOCAL-003) |
