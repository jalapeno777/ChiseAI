# Local CI Unification Guide

This document describes the unified local CI workflow using `scripts/ci/pre_push_gate.py` and `scripts/local-ci-checks.sh`.

## Overview

The local CI system has two components:

| Component            | Purpose           | Speed  | When to Use                                  |
| -------------------- | ----------------- | ------ | -------------------------------------------- |
| `scripts/ci/pre_push_gate.py` | Fast quality gate | <30s   | Automatically via repo-managed `pre-push` hook and manually when needed |
| `local-ci-checks.sh` | Full CI suite     | 2-5min | Before opening PR, after significant changes |

## pre_push_gate.py

Fast pre-push validation gate designed to catch issues before pushing.

### Features

- **Docs-only short-circuit**: Skips code checks for docs/opencode-only changes
- **Black**: Changed-file formatting check
- **Ruff**: Changed-file lint check
- **Secret scan**: Changed-file secret scan
- **Remote alignment**: Mirrors the lightweight blocking checks from `.woodpecker/push.yaml`

### Usage

```bash
# Auto-detect changed files and run the canonical gate
python3 scripts/ci/pre_push_gate.py
```

### Enforcement

- `scripts/swarm/session.py start|verify` auto-configures `git config --local core.hooksPath .githooks`
- `.githooks/pre-push` runs `python3 scripts/ci/pre_push_gate.py` on every normal `git push`
- Merlin-only authorized bypass:
  - `git -c chise.prePushBypass=true -c chise.prePushAuthorizedBy="<approver>" -c chise.prePushJustification="<reason>" push origin <branch>`

### Example Output

```
ChiseAI Pre-Push Gate
============================================================

Changed Python files: 3
  - src/signal_generation/emitter.py
  - src/data/cache.py
  - src/api/routes.py

  [PASS] black: 234ms
  [PASS] ruff: 189ms
  [PASS] secret-scan: 121ms

------------------------------------------------------------
Total duration: 544ms
Checks failed: 0

All checks passed.
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

# Combine options
./scripts/local-ci-checks.sh --merged-only --parallel
```

### Command Line Options

| Option          | Description                            |
| --------------- | -------------------------------------- |
| `--merged-only` | Only test files changed vs origin/main |
| `--parallel`    | Enable parallel test execution         |

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
python3 scripts/ci/pre_push_gate.py
```

**Debugging**:

```bash
# Re-run the canonical gate directly
python3 scripts/ci/pre_push_gate.py

# Run specific tool directly
python3 -m black --check <changed-python-files>
python3 -m ruff check <changed-python-files>
python3 scripts/ci/secret_scan_changed.py
```

## Integration with Git Workflow

### Pre-push Hook

Use the repo-managed hook path:

```bash
git config --local core.hooksPath .githooks
```

### CI Integration

In Woodpecker CI, keep the fast gate separate from `local-ci-checks.sh`:

```yaml
steps:
  - name: pre-push-gate
    commands:
      - python3 scripts/ci/pre_push_gate.py
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

1. **Use the repo-managed pre-push hook before every push** - It runs `scripts/ci/pre_push_gate.py` automatically
2. **Use --merged-only for PRs** - Only tests changed files
3. **Use --parallel for full CI** - Faster test execution
4. **Keep tests fast** - Unit tests should be <5s each
5. **Skip unnecessary checks** - Use --skip-tests when appropriate
