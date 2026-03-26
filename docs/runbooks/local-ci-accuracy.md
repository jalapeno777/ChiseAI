# Local CI Accuracy Runbook

> **Purpose**: Reduce false positives/negatives in local CI, improve error diagnostics, and provide actionable troubleshooting steps.

## Overview

The Local CI Accuracy system consists of three integrated components:

1. **Error Classifier** (`scripts/ci/error_classifier.py`) - Categorizes failures into types
2. **Diagnostics** (`scripts/ci/diagnostics.py`) - Collects system info and detects misconfigs
3. **Accuracy Improvements** (`scripts/local_ci_accuracy_improvements.py`) - Integrates the above with false positive detection

## Error Classification

### Categories

| Category     | Description            | Common Causes                       |
| ------------ | ---------------------- | ----------------------------------- |
| `SYNTAX`     | Python syntax errors   | Missing colons, indentation issues  |
| `IMPORT`     | Module import failures | Missing dependencies, typos         |
| `TEST`       | Test failures          | Assertion errors, fixture issues    |
| `LINT`       | Code style issues      | black/ruff violations               |
| `TYPE`       | Type checking errors   | mypy violations                     |
| `CONFIG`     | Configuration problems | Invalid config files                |
| `DEPENDENCY` | Dependency issues      | Version conflicts, missing packages |
| `UNKNOWN`    | Unclassified           | Requires manual investigation       |

### Interpreting Error Output

```bash
# Run error classifier on CI output
python scripts/ci/error_classifier.py

# Or pipe CI output through it
python scripts/ci/ci_gate.py 2>&1 | python scripts/ci/error_classifier.py
```

Example output:

```
============================================================
CI ERROR CLASSIFICATION REPORT
============================================================

## SYNTAX (2 errors)
----------------------------------------
  Message: SyntaxError: invalid syntax
  Location: src/module.py:42
  Confidence: 95%
  Fix suggestions:
    - Check for consistent indentation
    - Run: python -m py_compile <file.py>

## IMPORT (1 errors)
----------------------------------------
  Message: ModuleNotFoundError: No module named 'pytest'
  Confidence: 95%
  Fix suggestions:
    - Run: pip install pytest
```

## Common False Positives

### Timing Flakiness

**Pattern**: Timeouts, connection refused, temporary failures

**Detection**: Matches `timeout`, `ECONNREFUSED`, `ETIMEDOUT`, `ConnectionRefusedError`

**Resolution**:

```bash
# Retry the CI job
python scripts/local_ci_accuracy_improvements.py --run-ci

# If persistent, check test timeouts
grep -r "timeout" tests/
```

### Network Issues

**Pattern**: DNS failures, network unreachable, remote closed

**Detection**: Matches `network error`, `DNS`, `Could not resolve`

**Resolution**:

```bash
# Check network connectivity
ping google.com

# Verify DNS
nslookup github.com

# Retry CI
python scripts/local_ci_accuracy_improvements.py --run-ci
```

### Environment-Specific Issues

**Pattern**: Platform-specific failures, PATH issues

**Detection**: Matches `CI only`, `Windows/Linux/macOS specific`, `PYTHONPATH`

**Resolution**:

```bash
# Run diagnostics
python scripts/ci/diagnostics.py

# Check environment
echo $PYTHONPATH
echo $PATH
```

## Diagnostic Tools

### Running Full Diagnostics

```bash
# Text output (default)
python scripts/ci/diagnostics.py

# JSON output
python scripts/ci/diagnostics.py --format json

# Specific check only
python scripts/ci/diagnostics.py --check dependencies
```

### Available Checks

| Check                 | Description                        |
| --------------------- | ---------------------------------- |
| `python_path`         | Python environment and venv status |
| `git_state`           | Branch and dirty state             |
| `dependencies`        | Critical dependency presence       |
| `file_permissions`    | Script executability               |
| `docker_connectivity` | Docker daemon access               |
| `environment_vars`    | Required env vars                  |
| `woodpecker_config`   | CI configuration presence          |
| `local_ci_files`      | Local CI script presence           |

### Sample Diagnostic Output

```
============================================================
CI DIAGNOSTIC REPORT
============================================================
Timestamp: 2026-03-26T12:00:00
Python: 3.11.8
Platform: Linux 6.8.0-49-generic (x86_64)
Directory: /home/tacopants/projects/ChiseAI
Git: feature/ST-LOCAL-007 (dirty=False)

Checks: 7 passed, 1 failed

------------------------------------------------------------
CHECK RESULTS
------------------------------------------------------------

✓ PASS - python_path
       Virtual environment: /home/tacopants/projects/ChiseAI/.venv/bin/python

✓ PASS - git_state
       On branch 'feature/ST-LOCAL-007'

✗ FAIL - dependencies
       Found 4/5 critical dependencies
       → Install missing: pip install bandit

✓ PASS - file_permissions
       All scripts executable

...
```

## Integrated Analysis

### Running Full Analysis

```bash
# Run local CI with full analysis
python scripts/local_ci_accuracy_improvements.py --run-ci

# Analyze existing CI log
python scripts/local_ci_accuracy_improvements.py --input /path/to/ci.log

# Environment diagnostics only
python scripts/local_ci_accuracy_improvements.py --check-env
```

### Output Format

The integrated report shows:

1. Environment diagnostics context
2. Error analysis grouped by category
3. False positive detection
4. Actionable next steps per error

```
============================================================
LOCAL CI ACCURACY IMPROVEMENTS REPORT
============================================================

ENVIRONMENT DIAGNOSTICS
------------------------------------------------------------
Python: 3.11.8
Platform: Linux 6.8.0-49-generic (x86_64)
Git: feature/ST-LOCAL-007 (dirty=False)
Checks: 7 passed, 1 failed

ERROR ANALYSIS
------------------------------------------------------------
Total errors: 2
  - Likely false positives: 0
  - Real failures: 2

## SYNTAX (1 errors)
  Message: [SYNTAX] IndentationError: unexpected indent
  ✗ FAILURE
  Next steps:
    → Check for consistent indentation
    → Run: python -m py_compile <file.py>

## IMPORT (1 errors)
  Message: [IMPORT] ModuleNotFoundError: No module named 'requests'
  ✗ FAILURE
  Next steps:
    → Run: pip install requests

SUMMARY
------------------------------------------------------------
✗ 2 real failures detected
  Fix the failures above and re-run CI
```

## Accuracy Best Practices

### 1. Before Running CI

```bash
# Always run diagnostics first
python scripts/ci/diagnostics.py

# Fix any reported issues before proceeding
```

### 2. After CI Failure

```bash
# Run full accuracy analysis
python scripts/local_ci_accuracy_improvements.py --run-ci

# Review the categorized errors
# Follow the suggested next steps
```

### 3. Known Problem Patterns

| Problem               | Quick Fix                                            |
| --------------------- | ---------------------------------------------------- |
| `ModuleNotFoundError` | `pip install <module>`                               |
| `SyntaxError`         | Check indentation with `python -m py_compile <file>` |
| `TIMING_FLAKY`        | Retry CI - likely transient                          |
| `NETWORK_FLAKY`       | Check connectivity, retry CI                         |
| `E501 line too long`  | Run `black <file>`                                   |

### 4. Reducing False Positives

1. **Use virtual environments**: Always work in a venv

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

2. **Keep dependencies updated**:

   ```bash
   pip install --upgrade pytest black ruff mypy
   ```

3. **Run pre-push gate**:

   ```bash
   python scripts/ci/pre_push_gate.py  # Before every push
   ```

4. **Run diagnostics periodically**:
   ```bash
   python scripts/ci/diagnostics.py --check dependencies
   ```

## Troubleshooting Common Issues

### CI Fails but Local Passes

1. Run diagnostics on both environments
2. Compare Python versions: `python --version`
3. Check for dependency version differences: `pip freeze`
4. Look for environment-specific errors (marked as `ENV_SPECIFIC`)

### Intermittent Failures

1. Check for timing-related false positives (marked `TIMING_FLAKY`)
2. Verify network stability
3. Check if services are available
4. Retry CI - transient issues often resolve on retry

### Import Errors in CI but Not Locally

1. Verify all dependencies are in `requirements.txt` or `pyproject.toml`
2. Check for conditional imports that work locally but not in CI
3. Run: `pip check` to verify no dependency conflicts

## Files Reference

| File                                        | Purpose                                  |
| ------------------------------------------- | ---------------------------------------- |
| `scripts/ci/error_classifier.py`            | Error categorization engine              |
| `scripts/ci/diagnostics.py`                 | System info and misconfig detection      |
| `scripts/local_ci_accuracy_improvements.py` | Integration and false positive detection |
| `scripts/ci/pre_push_gate.py`               | Fast pre-push validation gate            |

## See Also

- [CI Gate Runbook](./ci-gates.md)
- [Pre-push Gate](./pre-push-gate.md)
- [Dependency Audit](./dependency-audit.md)
