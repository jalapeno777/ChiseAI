# Local CI Consistency Validator

## Overview

The Local CI Consistency Validator (`scripts/validate_local_ci_consistency.py`) detects drift between your local development environment and the CI configuration. This prevents "works on my machine" issues by catching configuration mismatches early.

## Quick Start

```bash
# Run full consistency check
python scripts/validate_local_ci_consistency.py

# Run with detailed output
python scripts/validate_local_ci_consistency.py --verbose

# Output in JSON format
python scripts/validate_local_ci_consistency.py --json

# Write report to file
python scripts/validate_local_ci_consistency.py --output drift-report.txt

# Run specific checks only
python scripts/validate_local_ci_consistency.py --check version   # Tool versions only
python scripts/validate_local_ci_consistency.py --check config    # Configuration only
```

## What Gets Checked

### Tool Versions

| Tool   | CI Image                          | What to Check       |
| ------ | --------------------------------- | ------------------- |
| Python | `chiseai-ci-tools:py311-YYYYMMDD` | Major.minor version |
| black  | `chiseai-ci-lint:py311-YYYYMMDD`  | Exact version       |
| ruff   | `chiseai-ci-lint:py311-YYYYMMDD`  | Exact version       |
| mypy   | `chiseai-ci-lint:py311-YYYYMMDD`  | Exact version       |
| bandit | `chiseai-ci-tools:py311-YYYYMMDD` | Exact version       |
| pytest | `chiseai-ci-tools:py311-YYYYMMDD` | Exact version       |

### Configuration Settings

| Tool   | Setting          | CI Default                            |
| ------ | ---------------- | ------------------------------------- |
| black  | `line-length`    | 88                                    |
| black  | `target-version` | py311                                 |
| ruff   | `line-length`    | 88                                    |
| ruff   | `select`         | E, F, I, B, UP, SIM                   |
| mypy   | `python_version` | 3.11                                  |
| pytest | `testpaths`      | tests                                 |
| pytest | `addopts`        | -v --tb=short --import-mode=importlib |

## Interpreting Drift Reports

### Exit Codes

- `0` - No drift detected (local matches CI)
- `1` - Drift detected (inconsistencies found)

### Severity Levels

| Severity   | Meaning                    | Action Required          |
| ---------- | -------------------------- | ------------------------ |
| **HIGH**   | Likely to cause CI failure | Fix before submitting PR |
| **MEDIUM** | May cause CI warnings      | Review and fix if needed |
| **LOW**    | Minor differences          | Optional to fix          |

### Example Output

```
======================================================================
LOCAL CI CONSISTENCY DRIFT REPORT
======================================================================
Generated: 2026-03-26T10:00:00Z

✗ DRIFT DETECTED: 2 issue(s)

SUMMARY:
  ✗ HIGH: 1
  ⚠ MEDIUM: 1

VERSION DRIFTS:
----------------------------------------------------------------------
  [MEDIUM] tool: ruff
    Local: 0.1.0
    CI:    20260323
    Note:  Version mismatch in chiseai-ci-lint:py311-20260323

CONFIGURATION DRIFTS:
----------------------------------------------------------------------
  [HIGH] ruff.line-length
    Local: 100
    CI:    88
    Note:  Configuration value differs from CI

======================================================================
STATUS: FAIL
======================================================================

======================================================================
REMEDIATION STEPS
======================================================================

  1. ruff version drift: Run `pip install --upgrade ruff` to match CI version
  2. Ruff line-length: Update pyproject.toml to use line-length=88

After applying fixes, re-run:
  python scripts/validate_local_ci_consistency.py
```

## Remediation Steps

### Version Mismatches

**Python version differs:**

```bash
# Install specific Python version (use pyenv, conda, or your package manager)
pyenv install 3.11
pyenv local 3.11
```

**Tool version differs:**

```bash
# Upgrade to match CI
pip install --upgrade black ruff mypy bandit pytest
```

### Configuration Drift

**Update pyproject.toml:**

```toml
[tool.black]
line-length = 88
target-version = ["py311"]

[tool.ruff]
line-length = 88

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM"]

[tool.mypy]
python_version = "3.11"
```

## Integration with CI

### Pre-push Hook

Use the repo-managed hook path instead of a hand-written `.git/hooks/pre-push`:

```bash
git config --local core.hooksPath .githooks
```

### Makefile Integration

```makefile
.PHONY: ci-check
ci-check:
	python scripts/validate_local_ci_consistency.py

.PHONY: pre-push
pre-push: ci-check
	@echo "CI consistency verified"
```

## CI Integration

The validator is automatically run as part of Woodpecker CI in the `lint` step via the bootstrap compliance checks. Running it locally helps catch issues before CI.

## Troubleshooting

### "NOT INSTALLED" for a tool

```bash
pip install black ruff mypy bandit pytest pytest-xdist pytest-asyncio
```

### Version shows "UNKNOWN"

The tool's version couldn't be extracted from the CI configuration. Check if `.woodpecker/ci.yaml` exists and is properly formatted.

### JSON output for automation

```bash
python scripts/validate_local_ci_consistency.py --json --output drift.json
```

Then parse in scripts:

```python
import json
with open("drift.json") as f:
    report = json.load(f)
    if not report["passed"]:
        # Handle drift
```

## Files

- `scripts/validate_local_ci_consistency.py` - Main validator
- `scripts/ci/consistency_checks/version_checker.py` - Tool version checking
- `scripts/ci/consistency_checks/config_comparator.py` - Configuration comparison
- `scripts/ci/consistency_checks/drift_reporter.py` - Report generation
