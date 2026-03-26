# Local CI Unification Guide

This document describes the unified local CI workflow using `scripts/pre_push_gate.py` and `scripts/local-ci-checks.sh`.

## Overview

The local CI system has two components:

| Component            | Purpose           | Speed  | When to Use                                  |
| -------------------- | ----------------- | ------ | -------------------------------------------- |
| `pre_push_gate.py`   | Fast quality gate | <30s   | Before every `git push`                      |
| `local-ci-checks.sh` | Full CI suite     | 2-5min | Before opening PR, after significant changes |

## pre_push_gate.py

Fast pre-push validation gate designed to catch issues before pushing.

### Features

- **Syntax check**: Python compile validation
- **Black**: Code formatting check
- **Ruff**: Lint check (E, F, I, B, UP, SIM rules)
- **Mypy**: Type checking (if configured)
- **Pytest**: Fast test on related files
- **Timing metrics**: Shows duration for each check phase

### Usage

```bash
# Auto-detect changed files and run quality gate
python3 scripts/pre_push_gate.py

# Check specific files
python3 scripts/pre_push_gate.py --files src/foo/bar.py

# Verbose output showing all check results
python3 scripts/pre_push_gate.py --verbose

# Skip pytest (when tests are run separately)
python3 scripts/pre_push_gate.py --skip-tests
```

### Exit Codes

- `0`: All checks passed
- `1`: One or more checks failed
- `2`: Setup/error

### Example Output

```
ChiseAI Pre-Push Gate
============================================================

Changed source files: 3
  - src/signal_generation/emitter.py
  - src/data/cache.py
  - src/api/routes.py

Related test files: 2
  - tests/test_signal_emitter.py
  - tests/test_cache.py

  [✓ PASS] syntax: 45ms
  [✓ PASS] black: 234ms
  [✓ PASS] ruff: 189ms
  [✓ PASS] mypy: 1234ms
  [✓ PASS] pytest: 4521ms

------------------------------------------------------------
Total duration: 6233ms
Checks: 5 passed, 0 failed

✓ All checks passed! Ready to push.
============================================================
```

## local-ci-checks.sh

Full local CI suite with test discovery and parallel execution.

### Features

- Policy consistency validation
- Swarm context verification
- Parallel test execution
- Batch test execution (file descriptor management)
- Coverage reporting
- JUnit XML output

### Usage

```bash
# Full test suite (all test directories)
./scripts/local-ci-checks.sh

# Merged-only mode (changed files from origin/main)
./scripts/local-ci-checks.sh --merged-only

# With parallel test execution
./scripts/local-ci-checks.sh --parallel

# With pre-push gate (run fast quality check first)
./scripts/local-ci-checks.sh --gate

# Combine options
./scripts/local-ci-checks.sh --merged-only --parallel --gate
```

### Command Line Options

| Option          | Description                            |
| --------------- | -------------------------------------- |
| `--merged-only` | Only test files changed vs origin/main |
| `--parallel`    | Enable parallel test execution         |
| `--gate`        | Run pre-push gate before CI checks     |
| `--no-gate`     | Skip pre-push gate (even if default)   |

## Timing Benchmarks

### pre_push_gate.py

| Check     | Typical Duration | Notes                      |
| --------- | ---------------- | -------------------------- |
| syntax    | 50-150ms         | Per-file Python compile    |
| black     | 200-500ms        | Scales with file count     |
| ruff      | 100-300ms        | Very fast linting          |
| mypy      | 1-3s             | Type checking overhead     |
| pytest    | 2-10s            | Depends on test complexity |
| **Total** | **<30s typical** | For <10 changed files      |

### local-ci-checks.sh (full suite)

| Phase              | Typical Duration | Notes        |
| ------------------ | ---------------- | ------------ |
| Context validation | 1-2s             |              |
| Policy checks      | 2-5s             |              |
| Test discovery     | <1s              |              |
| Pytest (parallel)  | 30-90s           | With -n auto |
| Coverage report    | 5-15s            |              |
| **Total**          | **2-5 min**      | Full suite   |

## Troubleshooting

### pre_push_gate.py Issues

**"mypy not available, skipping"**

- Solution: `pip install mypy` if you want type checking

**"No test files found"**

- Solution: Ensure tests are named `test_*.py` or `*_test.py`

**Black formatting failures**

- Solution: Run `python3 -m black <file>` to auto-format

**Ruff lint failures**

- Solution: Run `python3 -m ruff check --fix <file>` for auto-fixes

### local-ci-checks.sh Issues

**"File descriptor exhaustion"**

- Solution: Use `--parallel` flag which limits workers
- Or set `CI_FD_CONSTRAINTS=1` for forked mode

**"No matching test files found"**

- This is normal when only non-Python files changed
- Switch to full mode: `./scripts/local-ci-checks.sh`

**"Permission denied" on script execution**

- Solution: `chmod +x scripts/local-ci-checks.sh`

**Timeout errors**

- Default pytest timeout is 120s per test
- Increase via `PYTEST_TIMEOUT=300` environment variable

### Common Solutions

**Clean start**:

```bash
# Remove cached outputs
rm -rf _bmad-output/

# Re-run
python3 scripts/pre_push_gate.py
```

**Verbose debugging**:

```bash
# Run with verbose output
python3 scripts/pre_push_gate.py --verbose

# Run specific tool directly
python3 -m black --check src/
python3 -m ruff check src/
python3 -m mypy src/
```

## Integration with Git Workflow

### Pre-push Hook (Optional)

Add to `.git/hooks/pre-push`:

```bash
#!/bin/bash
python3 scripts/pre_push_gate.py
```

Make executable: `chmod +x .git/hooks/pre-push`

### CI Integration

In Woodpecker CI, use `--gate` to run pre-push gate:

```yaml
steps:
  - name: pre-push-gate
    commands:
      - ./scripts/local-ci-checks.sh --merged-only --gate
```

## Relationship Between Tools

```
┌─────────────────────────────────────────────────────────────┐
│                      git push                               │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│              pre_push_gate.py (< 30s)                       │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐          │
│  │ syntax  │ │  black  │ │  ruff   │ │  mypy   │  pytest  │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘          │
│                   FAST QUALITY GATE                         │
└─────────────────────────────────────────────────────────────┘
                            │
                     (if gate passes)
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                  local-ci-checks.sh                         │
│  ┌──────────────────┐  ┌──────────────────────────────────┐│
│  │ Policy Validation│  │     Pytest (batched/parallel)     ││
│  └──────────────────┘  └──────────────────────────────────┘│
│                    FULL CI SUITE                            │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
                      origin/main
```

## Exit Codes

| Code | Meaning         |
| ---- | --------------- |
| 0    | Success         |
| 1    | Check(s) failed |
| 2    | Setup error     |

## Performance Tips

1. **Use pre_push_gate.py before every push** - Catches 90% of issues in <30s
2. **Use --merged-only for PRs** - Only tests changed files
3. **Use --parallel for full CI** - Faster test execution
4. **Keep tests fast** - Unit tests should be <5s each
5. **Skip unnecessary checks** - Use --skip-tests when appropriate
