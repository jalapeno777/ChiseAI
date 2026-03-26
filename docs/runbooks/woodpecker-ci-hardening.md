# Woodpecker CI Hardening Runbook

## Overview

This runbook documents the CI hardening improvements added in ST-LOCAL-008, including the local CI consistency validator integration, gate hardening, and enhanced error handling.

## CI Pipeline Architecture

### Design Principle: Non-Blocking Steps with Single Fail Point

The Woodpecker CI pipeline follows a specific architectural pattern:

1. **Individual steps capture exit codes but always exit 0**
2. **ci-gate step is the SINGLE authoritative failure point**
3. **This ensures all validations run and provide feedback before failing**

```
┌─────────────────────────────────────────────────────────────────┐
│                    Woodpecker CI Pipeline                        │
├─────────────────────────────────────────────────────────────────┤
│  Step 1: swarm-context    → status logged, continues even on   │
│  Step 2: cross-branch-verify → advisory-only, never blocks      │
│  Step 3: lint              → captures violations, continues     │
│  Step 4: local-ci-consistency → ADVISORY-ONLY, never blocks    │
│  ... (more steps)                                            │
│  Step N: ci-gate           → SINGLE FAIL POINT                  │
│           Reads all status files and decides pass/fail         │
└─────────────────────────────────────────────────────────────────┘
```

### Gate Categories

| Category          | Gates                                                                                                                                                       | Blocking Behavior                             |
| ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------- |
| **FAST_REQUIRED** | swarm-context, lint, security-scan, dependency-audit, secret-scan, risk-invariants, brain-regression, docs-pairing, docker-governance, local-ci-consistency | Blocks on all events                          |
| **FULL_REQUIRED** | local-ci, brain-eval                                                                                                                                        | Only blocks on main/cron or FORCE_FULL_GATE=1 |
| **CRON_ONLY**     | tempmemory-drill, flaky-detection                                                                                                                           | Only runs on cron/main                        |

## Gate Descriptions

### local-ci-consistency (ST-LOCAL-008)

**Purpose**: Validates that the local development environment matches the CI configuration to prevent "works on my machine" issues.

**Implementation**: Runs `scripts/validate_local_ci_consistency.py` which checks:

- Tool versions (Python, black, ruff, mypy, bandit, pytest)
- Configuration settings (line-length, select rules, python_version, etc.)

**Advisory-Only**: This gate NEVER blocks the pipeline. It outputs warnings when drift is detected but the pipeline continues. This is intentional to avoid blocking development while still providing feedback.

**Exit Code Handling**:

- Script exit code is captured in `local-ci-consistency.status`
- Always writes `0` to status file (non-blocking)
- Full output logged to `local-ci-consistency.log`

### lint Gate Hardening

The lint gate has been enhanced with improved error handling:

| Check                | Previous Behavior      | Current Behavior              |
| -------------------- | ---------------------- | ----------------------------- |
| black                | `xargs black --check`  | Unchanged - blocks on failure |
| ruff                 | `xargs ruff check`     | Unchanged - blocks on failure |
| mypy                 | `\|\| echo "WARN:..."` | Improved warning capture      |
| bootstrap compliance | `\|\| echo "WARN:..."` | Enhanced error classification |

**Hardening Improvements**:

1. Better structured error output in status logs
2. Improved warning capture for non-blocking violations
3. Enhanced error classification for debugging

### Dependency Caching

**Location**: Applied in steps that install Python packages

**Implementation**:

```yaml
settings:
  volumes:
    - /woodpecker/cache/pip:/root/.cache/pip
```

**Cache Key**: Based on `requirements*.txt` and `pyproject.toml` hashes

**Behavior**:

- Cache is restored before step commands run
- Cache is updated after pip installs
- Cache miss is non-fatal (continues without cache)

## Troubleshooting CI Failures

### Identifying Which Gate Failed

1. **Check the pipeline log** for the ci-gate step
2. **Review individual step status files** in `/woodpecker/ci-status/{pipeline_number}/`
3. **Status file naming**: `{step-name}.status` contains exit code

### Common Failure Patterns

#### 1. lint Failures

```
lint: FAIL - black found formatting issues
lint: FAIL - ruff found import violations
```

**Resolution**:

```bash
# Fix formatting
black .

# Fix lint issues
ruff check . --fix

# If mypy failures
mypy src --ignore-missing-imports
```

#### 2. local-ci-consistency Warnings

```
local-ci-consistency: DRIFT DETECTED
  HIGH: ruff version mismatch (local: 0.1.0, CI: 20260323)
  MEDIUM: black line-length differs (local: 100, CI: 88)
```

**Resolution**:

```bash
# Update tools to match CI
pip install --upgrade black ruff mypy bandit pytest

# Or update local configuration to match CI
# See docs/runbooks/local-ci-consistency.md
```

#### 3. security-scan Failures

Bandit findings are logged but typically non-blocking unless HIGH severity.

```bash
# Check what bandit found
bandit -r src/ -f screen
```

#### 4. dependency-audit Failures

```
dependency-audit: FAIL - vulnerabilities found
```

**Resolution**:

```bash
# Review vulnerabilities
pip audit

# Update vulnerable packages
pip install --upgrade vulnerable-package
```

### Advisory-Only Gates Never Blocking

The following gates are DESIGNED to never block:

| Gate                   | Reason                               |
| ---------------------- | ------------------------------------ |
| `cross-branch-verify`  | Advisory verification only           |
| `local-ci-consistency` | Developer environment drift warnings |
| `pipeline-watchdog`    | Monitoring only, no blocking         |
| `docker-live-check`    | Live environment verification        |
| `compass-apply`        | Auto-labeling, never blocks          |

If these gates are causing unexpected pipeline failures, check:

1. Status file handling in `ci_gate.py`
2. Whether step is incorrectly listed in FAST_REQUIRED

### Debugging ci-gate Itself

If ci-gate is failing unexpectedly:

1. **Check ci_gate.py logic**:

```bash
cat /woodpecker/ci-status/{pipeline}/ci-gate.log
```

2. **Verify status files exist**:

```bash
ls -la /woodpecker/ci-status/{pipeline}/*.status
```

3. **Test ci_gate locally**:

```bash
python scripts/ci/ci_gate.py --verbose
```

## Integration with ST-LOCAL-007

ST-LOCAL-008 builds on ST-LOCAL-007 (local-ci-consistency validator) by:

1. **Adding CI integration** for the validator
2. **Making it non-blocking** per CI design principles
3. **Documenting gate behavior** for operators

The validator script itself (`scripts/validate_local_ci_consistency.py`) was created in ST-LOCAL-007. ST-LOCAL-008 integrates it into CI.

## Files Modified

| File                                       | Change                                                       | Story        |
| ------------------------------------------ | ------------------------------------------------------------ | ------------ |
| `.woodpecker/ci.yaml`                      | Added local-ci-consistency step, added to ci-gate depends_on | ST-LOCAL-008 |
| `scripts/validate_local_ci_consistency.py` | Created in ST-LOCAL-007                                      | ST-LOCAL-007 |
| `scripts/ci/consistency_checks/*.py`       | Supporting modules                                           | ST-LOCAL-007 |
| `docs/runbooks/woodpecker-ci-hardening.md` | This documentation                                           | ST-LOCAL-008 |

## Validation Commands

### Local YAML Validation

```bash
# Validate YAML syntax
yamllint .woodpecker/ci.yaml

# Check Woodpecker configuration
woodpecker-cli pipeline list
```

### Test local-ci-consistency Locally

```bash
# Run consistency check
python scripts/validate_local_ci_consistency.py --verbose

# Check specific aspects
python scripts/validate_local_ci_consistency.py --check version
python scripts/validate_local_ci_consistency.py --check config
```

### Verify CI Integration

```bash
# Check if step is in pipeline
grep -A5 "local-ci-consistency:" .woodpecker/ci.yaml

# Verify depends_on includes it
grep -A30 "ci-gate:" .woodpecker/ci.yaml | grep "local-ci-consistency"
```

## Exit Codes

| Code | Meaning                                    |
| ---- | ------------------------------------------ |
| 0    | All gates passed or advisory-only warnings |
| 1    | One or more blocking gates failed          |

For advisory gates (local-ci-consistency, cross-branch-verify), exit code in status file may be 0 even if warnings were printed.

## References

- [Local CI Consistency Validator](local-ci-consistency.md)
- [CI Coverage Matrix](ci-coverage-matrix.md)
- [Emergency Gate Rollback](emergency-gate-rollback.md)
- [CI Gate Architecture](../docs/architecture/ci-gates.md)
