# Phase 3 CI Acceptance Criteria

> **Story**: BL-CI-PHASE3  
> **Phase**: CI Enhancement and Remediation  
> **Created**: 2026-03-08  
> **Status**: Draft

## Overview

This document defines the explicit acceptance criteria for Phase 3 CI enhancements following the completion of ST-CI-001 Phase 2 (2026-03-03). The goal is to remediate the 31 issues identified in Phase 1 assessment (P0: 2, P1: 6, P2: 7) and harden the CI pipeline.

---

## 1. Test Coverage Targets

### 1.1 Module-Level Coverage Requirements

| Module | Target Coverage | Critical Paths | Notes |
|--------|----------------|----------------|-------|
| `src/governance/` | >85% | Risk audit, validation, tempmemory | All governance decisions must be tested |
| `src/execution/` | >85% | Kill switch, venue enforcement, reconciliation | Critical safety mechanisms |
| `src/brain/` | >85% | Evaluation, shadow testing, promotion | Brain quality gates |
| `src/strategy/` | >80% | DSL, evolution, validation | Strategy lifecycle |
| `src/ci/` | >85% | All CI scripts | CI self-validation |
| `scripts/ci/` | >80% | CI gates, validation | Pipeline integrity |
| `scripts/validation/` | >85% | Status sync, compliance | Governance validation |

### 1.2 Critical Path Coverage (Must Have >90%)

The following code paths are designated as **critical** and require >90% coverage:

1. **Risk Invariants** (`src/execution/risk/`)
   - Position limit enforcement
   - Kill switch activation
   - Drawdown circuit breakers

2. **Validation Gates** (`src/validation/`)
   - Status sync validation
   - Insight governance checks
   - Metacognition compliance

3. **CI Gates** (`scripts/ci/ci_gate.py`)
   - Status file aggregation
   - Failure detection logic
   - Root cause extraction

### 1.3 Changed Lines Coverage

- All PRs must maintain >80% coverage on changed lines
- CI gate `changed-lines-coverage` enforces this
- Exemptions require explicit approval with justification

---

## 2. Linting Standards

### 2.1 Code Formatting (Black)

```yaml
line-length: 100
target-version: ['py311', 'py312']
include: '\.pyi?$'
extend-exclude: '''
/(
  migrations
  | __pycache__
  | \.git
  | \.venv
  | _bmad-output
  | docs/_archive
)/
'''
```

**Enforcement**: CI gate `lint` runs `black --check` on changed Python files.

### 2.2 Linting (Ruff)

**Enabled Rules**:
- `E` - pycodestyle errors
- `F` - Pyflakes
- `I` - isort
- `N` - pep8-naming
- `W` - pycodestyle warnings
- `UP` - pyupgrade
- `B` - flake8-bugbear
- `C4` - flake8-comprehensions
- `SIM` - flake8-simplify

**Configuration** (in `pyproject.toml`):
```toml
[tool.ruff]
line-length = 100
target-version = "py311"
select = ["E", "F", "I", "N", "W", "UP", "B", "C4", "SIM"]
ignore = ["E501"]  # Line too long (handled by black)

[tool.ruff.pydocstyle]
convention = "google"
```

**Enforcement**: CI gate `lint` runs `ruff check` with zero tolerance for errors.

### 2.3 Type Checking (Mypy)

**Configuration**:
```yaml
python_version: "3.11"
strict: true
warn_return_any: true
warn_unused_configs: true
disallow_untyped_defs: true
disallow_incomplete_defs: true
check_untyped_defs: true
```

**Enforcement**: CI gate `lint` runs `mypy` on `src/` and `scripts/` directories.

---

## 3. Security Scan Gates

### 3.1 Static Analysis (Bandit)

**Configuration** (`.bandit`):
```yaml
skips: ["B101"]  # Skip assert_used in tests
severity: medium
confidence: medium
```

**Scan Targets**:
- `src/`
- `scripts/`

**Enforcement**: CI gate `security-scan` runs Bandit and fails on medium+ severity findings.

### 3.2 Dependency Audit (pip-audit)

**Scope**: All dependencies in `requirements.txt` and `pyproject.toml`

**Enforcement**: CI gate `dependency-audit` runs `pip-audit` and fails on known vulnerabilities.

### 3.3 Secret Scanning

**Tool**: Custom secret scanner (`scripts/ci/secret_scan_changed.py`)

**Detects**:
- Hardcoded API keys
- Passwords in code
- Private keys
- Tokens in configuration

**Enforcement**: CI gate `secret-scan` runs on all changed files.

---

## 4. Performance Thresholds

### 4.1 Test Execution Time

| Test Suite | Max Duration | Notes |
|------------|--------------|-------|
| Unit tests | <3 minutes | `pytest tests/unit/` |
| CI tests | <2 minutes | `pytest tests/test_ci/` |
| Integration tests | <5 minutes | `pytest tests/integration/` |
| Full test suite | <10 minutes | All tests combined |

**Enforcement**: CI gate `local-ci` monitors test execution time.

### 4.2 Memory Usage

| Context | Max Memory | Notes |
|---------|------------|-------|
| CI pipeline | <2GB | Per pipeline run |
| Test execution | <1GB | Peak during tests |
| Brain evaluation | <4GB | Memory-intensive analysis |

**Enforcement**: CI monitors memory usage via resource limits.

### 4.3 Pipeline Speed Targets

| Stage | Target Duration | Max Duration |
|-------|-----------------|--------------|
| `swarm-context` | <10s | 30s |
| `lint` | <60s | 3min |
| `security-scan` | <30s | 2min |
| `dependency-audit` | <30s | 2min |
| `secret-scan` | <15s | 1min |
| `risk-invariants` | <2min | 5min |
| `brain-regression` | <3min | 8min |
| `docs-pairing` | <15s | 1min |
| `docker-governance` | <15s | 1min |
| `changed-lines-coverage` | <10s | 1min |
| `status-write-gate` | <15s | 1min |
| `ci-gate` | <10s | 30s |

---

## 5. CI Gate Requirements

### 5.1 Fast Required Gates (All Builds)

These gates must pass on every build:

1. `swarm-context` - Repository context validation
2. `lint` - Code quality (black, ruff, mypy)
3. `security-scan` - Bandit security analysis
4. `dependency-audit` - pip-audit vulnerability scan
5. `secret-scan` - Hardcoded secret detection
6. `risk-invariants` - Critical risk invariant tests
7. `brain-regression` - Brain evaluation regression tests
8. `docs-pairing` - Documentation pairing validation
9. `docker-governance` - Docker container governance
10. `changed-lines-coverage` - Coverage on changed lines (>80%)
11. `status-write-gate` - Workflow status file validation

### 5.2 Full Required Gates (Main/Cron Only)

These gates run on main branch and cron builds:

1. `local-ci` - Full test suite
2. `brain-eval` - Brain evaluation

### 5.3 Cron-Only Gates

These gates run only on main branch cron builds:

1. `tempmemory-drill` - Tempmemory reconciliation drill
2. `flaky-detection` - Flaky test detection (3 runs)

---

## 6. Validation Checklist

### 6.1 Pre-Commit Validation

- [ ] `black --check src/` passes
- [ ] `ruff check src/` passes (0 errors)
- [ ] `mypy src/` passes (or documented exceptions)
- [ ] `pytest tests/unit/` passes
- [ ] Coverage maintained or improved
- [ ] No new security findings (bandit)
- [ ] No hardcoded secrets

### 6.2 CI Pipeline Validation

- [ ] All FAST_REQUIRED gates pass
- [ ] Changed lines coverage >80%
- [ ] Test execution time <5 minutes
- [ ] Memory usage <2GB
- [ ] No flaky tests detected

### 6.3 Post-Merge Validation

- [ ] Main branch CI passes
- [ ] No regression in test coverage
- [ ] Performance metrics within thresholds
- [ ] Status sync validated

---

## 7. Remediation Priorities

### 7.1 P0 Issues (Fix First)

1. **Add missing test coverage for critical paths**
   - Target: `src/execution/risk/`, `src/validation/`
   - Minimum: 90% coverage
   - Deadline: Phase 3 completion

2. **Harden CI gates to block on test failures**
   - Ensure `ci-gate` properly aggregates all status files
   - No bypass mechanisms without explicit override
   - Audit logging for all overrides

### 7.2 P1 Issues (High Priority)

1. **Optimize CI pipeline speed**
   - Target: <5 minutes for PR builds
   - Parallelize independent stages
   - Cache dependencies

2. **Add parallel test execution**
   - Use `pytest-xdist` for parallel test runs
   - Target: 2x speedup on multi-core runners

3. **Improve error reporting**
   - Structured root cause extraction
   - PR comments with failure details
   - Discord notifications for main branch failures

### 7.3 P2 Issues (Medium Priority)

1. **Documentation updates**
   - Update CI documentation
   - Add troubleshooting guides
   - Document bypass procedures

2. **Non-critical optimizations**
   - Dependency caching improvements
   - Test selection optimization
   - Log compression

---

## 8. Success Criteria

Phase 3 is considered complete when:

1. **All P0 issues resolved**
   - Critical path coverage >90%
   - CI gates hardened and verified

2. **All P1 issues addressed**
   - CI pipeline speed optimized
   - Parallel test execution enabled
   - Error reporting improved

3. **Documentation complete**
   - This acceptance criteria document approved
   - Live validation checklist created
   - Troubleshooting guides updated

4. **CI validation passes**
   - `python scripts/ci/ci_gate.py` passes locally
   - All gates pass on feature branch
   - No regressions in existing functionality

5. **Metrics achieved**
   - Test coverage >80% for all modules
   - CI execution time <5 minutes
   - Zero security findings (medium+)
   - Memory usage <2GB

---

## 9. References

- Story: ST-CI-001 (Phase 1 & 2)
- Iterlog: `docs/tempmemories/iterlog-ST-CI-001.md`
- CI Configuration: `.woodpecker/ci.yaml`
- CI Gate: `scripts/ci/ci_gate.py`
- Validation Registry: `docs/validation/validation-registry.yaml`
