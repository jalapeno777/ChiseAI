# Phase 3 Live Validation Checklist

> **Story**: BL-CI-PHASE3  
> **Purpose**: Step-by-step validation for CI enhancements  
> **Created**: 2026-03-08  
> **Status**: Active

---

## Pre-Commit Validation

Run these checks before every commit:

### 1. Git Sanity Checks

```bash
# Check working tree is clean
git status -sb

# Verify on correct branch
git branch --show-current

# Check for unintended files
git diff --name-only --cached
```

**Expected**: Clean working tree, on feature branch, only intended files staged.

### 2. Code Quality Checks

```bash
# Formatting (black)
black --check src/ scripts/

# Linting (ruff)
ruff check src/ scripts/

# Type checking (mypy)
mypy src/ scripts/ci/
```

**Expected**: All checks pass with 0 errors.

**Auto-fix**:
```bash
black src/ scripts/
ruff check --fix src/ scripts/
```

### 3. Test Validation

```bash
# Run unit tests
pytest tests/unit/ -v --tb=short

# Run CI tests
pytest tests/test_ci/ -v --tb=short

# Check coverage
pytest tests/ --cov=src --cov-report=term-missing --cov-fail-under=80
```

**Expected**: All tests pass, coverage >80%.

### 4. Security Scans

```bash
# Bandit security scan
bandit -r src/ scripts/ -f json -o bandit-report.json || true

# Check for secrets
git-secrets --scan

# Dependency audit
pip-audit --requirement requirements.txt || true
```

**Expected**: No high/critical security findings.

### 5. Status Sync Validation

```bash
# Validate workflow status
python3 scripts/validate_status_sync.py

# Validate iterloop compliance (if story work)
python3 scripts/validate_iterloop_compliance.py --story-id BL-CI-PHASE3 || true
```

**Expected**: Status sync passes, iterlog compliance validated.

---

## CI Pipeline Verification

### 1. Local CI Gate

```bash
# Run the CI gate locally
python3 scripts/ci/ci_gate.py
```

**Expected**: Exit code 0, all status files present and passing.

### 2. Individual Gate Testing

Test each gate individually:

```bash
# Swarm context
python3 scripts/ci/validate_swarm_context.py

# Docs pairing
python3 scripts/ci/validate_docs_pairing.py

# Docker governance
python3 scripts/ci/validate_docker_governance.py

# Secret scan
python3 scripts/ci/secret_scan_changed.py
```

**Expected**: Each script exits 0.

### 3. Coverage Validation

```bash
# Generate coverage report
pytest tests/ --cov=src --cov-report=html --cov-report=term

# Validate changed lines coverage (if coverage.json exists)
python3 scripts/ci/coverage_changed_lines.py --coverage-json coverage.json --threshold 80
```

**Expected**: Coverage >80% for changed lines.

### 4. Performance Check

```bash
# Time the test suite
time pytest tests/unit/ -x

# Check memory usage (Linux)
/usr/bin/time -v pytest tests/unit/ -x 2>&1 | grep "Maximum resident"
```

**Expected**: Tests complete in <3 minutes, memory <1GB.

---

## Woodpecker CI Verification

### 1. Pipeline Structure Validation

```bash
# Validate Woodpecker configuration
woodpecker-cli lint .woodpecker/ci.yaml

# Or use yamllint
yamllint .woodpecker/ci.yaml
```

**Expected**: No syntax errors, valid YAML.

### 2. Required Gates Check

Verify all required gates are defined:

```bash
# List all gates in CI config
grep -E "^  [a-z-]+:" .woodpecker/ci.yaml | head -20
```

**Required Gates**:
- [ ] `swarm-context`
- [ ] `lint`
- [ ] `security-scan`
- [ ] `dependency-audit`
- [ ] `secret-scan`
- [ ] `risk-invariants`
- [ ] `brain-regression`
- [ ] `docs-pairing`
- [ ] `docker-governance`
- [ ] `changed-lines-coverage`
- [ ] `status-write-gate`
- [ ] `ci-gate`

### 3. Gate Dependencies

Verify `ci-gate` depends on all required gates:

```bash
# Check ci-gate dependencies
sed -n '/^  ci-gate:/,/^  [a-z-]*:/{/^    depends_on:/,/^    [a-z-]*:/p}' .woodpecker/ci.yaml
```

**Expected**: All FAST_REQUIRED gates listed in depends_on.

---

## Post-Merge Validation

After merging to main:

### 1. Main Branch CI Status

```bash
# Check main branch CI status
git checkout main
git pull origin main

# Verify last commit CI passed
# (Check Woodpecker dashboard or Gitea PR status)
```

### 2. Coverage Regression Check

```bash
# Compare coverage before/after
git diff HEAD~1 --name-only | grep -E '\.py$' | xargs -I {} coverage run -m pytest {}

# Generate diff coverage
python3 scripts/ci/coverage_changed_lines.py
```

**Expected**: No coverage regression, changed lines >80%.

### 3. Performance Baseline

```bash
# Record test execution time
time pytest tests/ -x --tb=line

# Record memory usage
# (Use /usr/bin/time -v on Linux)
```

**Expected**: Performance within 10% of baseline.

### 4. Status Sync Verification

```bash
# Validate main branch status
python3 scripts/validate_status_sync.py

# Check bmm-workflow-status.yaml
grep -A5 "BL-CI-PHASE3" docs/bmm-workflow-status.yaml
```

**Expected**: Story status reflects "merged" or "complete".

---

## Troubleshooting Guide

### CI Gate Failures

**Symptom**: `ci-gate` fails with missing status files

**Diagnosis**:
```bash
# Check CI status directory
ls -la _bmad-output/ci/

# Check individual gate logs
cat _bmad-output/ci/lint.log
cat _bmad-output/ci/security-scan.log
```

**Resolution**:
1. Run individual gates to generate status files
2. Fix underlying issues in failing gates
3. Re-run `ci-gate`

### Test Failures

**Symptom**: Tests fail in CI but pass locally

**Diagnosis**:
```bash
# Check for environment differences
env | grep -E "^(CI|WOODPECKER)"

# Run tests in isolated environment
docker run --rm -v $(pwd):/app -w /app python:3.11 pytest tests/ -x
```

**Common Causes**:
- Missing environment variables
- Different Python version
- File path differences
- Timing-dependent tests

### Coverage Failures

**Symptom**: Coverage below threshold

**Diagnosis**:
```bash
# Generate detailed coverage report
pytest tests/ --cov=src --cov-report=html

# Check uncovered lines
open htmlcov/index.html
```

**Resolution**:
1. Add tests for uncovered code paths
2. Mark intentionally uncovered code with `# pragma: no cover`
3. Request exemption with justification

### Security Scan Failures

**Symptom**: Bandit or secret scan fails

**Diagnosis**:
```bash
# Run bandit locally
bandit -r src/ -f json

# Check for secrets
git-secrets --scan
```

**Resolution**:
1. Fix security issues (remove hardcoded secrets)
2. Use environment variables for sensitive data
3. Add false positive markers if needed

---

## Quick Reference Commands

```bash
# Full pre-commit validation
black --check src/ scripts/ && \
ruff check src/ scripts/ && \
mypy src/ scripts/ci/ && \
pytest tests/unit/ tests/test_ci/ -v --tb=short && \
python3 scripts/validate_status_sync.py

# Quick CI gate check
python3 scripts/ci/ci_gate.py

# Coverage check
pytest tests/ --cov=src --cov-report=term-missing --cov-fail-under=80

# Security scan
bandit -r src/ scripts/ -ll

# Performance test
time pytest tests/unit/ -x
```

---

## Sign-Off

| Role | Name | Date | Status |
|------|------|------|--------|
| Implementer | senior-dev | 2026-03-08 | In Progress |
| Reviewer | TBD | | Pending |
| Approver | TBD | | Pending |
