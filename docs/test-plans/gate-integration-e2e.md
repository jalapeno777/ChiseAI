# E2E Test Plan: Gate Integration

**Document ID:** INTEG-001  
**Version:** 1.0  
**Date:** 2026-03-17  
**Author:** senior-dev  
**Status:** Draft

---

## 1. Overview

### 1.1 Purpose

This document outlines the end-to-end (E2E) test plan for the CI/CD gate integration system. It covers the testing strategy for blocking gates, evidence gates, and merge truth verification.

### 1.2 Scope

| In Scope | Out of Scope |
|----------|--------------|
| Blocking gates runner | External CI system configuration |
| Evidence gate runner | Woodpecker server configuration |
| Merge truth verifier | Third-party integrations |
| CI gate integration | Deployment automation |
| Integration test suite | Performance/load testing |

### 1.3 References

- `scripts/ci/blocking_gates_runner.py` - Blocking gates runner
- `scripts/ci/evidence_gate_runner.py` - Evidence gate runner
- `scripts/ci/merge_truth_verifier.py` - Merge truth verifier
- `scripts/ci/ci_gate.py` - CI gate integration
- `tests/integration/test_blocking_gates.py` - Integration tests

---

## 2. Test Strategy

### 2.1 Test Levels

```
┌─────────────────────────────────────────────────────────────┐
│                    E2E Test Pyramid                         │
├─────────────────────────────────────────────────────────────┤
│  Level 3: E2E Workflows    │ Full CI pipeline simulation    │
│  Level 2: Integration      │ Component interaction tests    │
│  Level 1: Unit Tests       │ Individual gate logic tests    │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Test Types

| Type | Description | Coverage Target |
|------|-------------|-----------------|
| Functional | Verify gate logic and behavior | 100% of gate types |
| Integration | Test component interactions | All gate combinations |
| Error Handling | Test failure scenarios | All error paths |
| CLI | Test command-line interfaces | All CLI options |

---

## 3. Test Scenarios

### 3.1 Blocking Gates Runner (INTEG-001-A)

#### Scenario 1: All Gates Pass
**Objective:** Verify that runner reports success when all gates pass

**Preconditions:**
- CI status directory exists
- All gate status files contain exit code 0

**Steps:**
1. Create temporary CI status directory
2. Create status files for all blocking gates with exit code 0
3. Run blocking_gates_runner.py
4. Verify exit code is 0
5. Verify report shows overall_passed=true

**Expected Result:** Runner exits with code 0, all gates marked as passed

#### Scenario 2: Blocking Gate Fails
**Objective:** Verify that runner blocks when a blocking gate fails

**Preconditions:**
- CI status directory exists
- One blocking gate has exit code 1

**Steps:**
1. Create temporary CI status directory
2. Create status files with one gate failing (exit code 1)
3. Run blocking_gates_runner.py
4. Verify exit code is 1
5. Verify report shows overall_passed=false

**Expected Result:** Runner exits with code 1, failed gate marked as blocking

#### Scenario 3: Full-Only Gate in PR Mode
**Objective:** Verify that full-only gates don't block in PR mode

**Preconditions:**
- CI status directory exists
- FORCE_FULL=0 (PR mode)
- Full-only gate has exit code 1

**Steps:**
1. Create temporary CI status directory
2. Create failing status for full-only gate
3. Run blocking_gates_runner.py without --force-full
4. Verify runner does not block on full-only gate

**Expected Result:** Full-only gate failure is reported but doesn't block

#### Scenario 4: Missing Status File
**Objective:** Verify handling of missing status files

**Preconditions:**
- CI status directory exists
- One gate status file is missing

**Steps:**
1. Create temporary CI status directory
2. Create status files for some gates only
3. Run blocking_gates_runner.py
4. Verify missing gates are marked as failed

**Expected Result:** Missing status files are treated as failures

### 3.2 Evidence Gate Runner (INTEG-001-A)

#### Scenario 5: Story Evidence Validation
**Objective:** Verify evidence validation for a specific story

**Preconditions:**
- Story ID is provided or auto-detected
- Validation script exists

**Steps:**
1. Run evidence_gate_runner.py --story-id ST-XXX
2. Verify validation script is called with correct story ID
3. Verify exit code matches validation result

**Expected Result:** Evidence validation runs and reports correctly

#### Scenario 6: Auto-Detect Story from CI
**Objective:** Verify story ID auto-detection from CI environment

**Preconditions:**
- CI environment variables are set
- PR title or branch contains story ID

**Steps:**
1. Set CI environment variables (CI_COMMIT_BRANCH, etc.)
2. Run evidence_gate_runner.py without --story-id
3. Verify story ID is extracted from environment

**Expected Result:** Story ID is auto-detected and validation runs

#### Scenario 7: No Story Detected
**Objective:** Verify graceful handling when no story is detected

**Preconditions:**
- No CI environment variables set
- No --story-id provided

**Steps:**
1. Clear CI environment variables
2. Run evidence_gate_runner.py without --story-id
3. Verify exit code is 0 (skipped)

**Expected Result:** Gate skips validation and exits successfully

### 3.3 Merge Truth Verifier (INTEG-001-A)

#### Scenario 8: Verify Commit in Main
**Objective:** Verify that a commit is present in main branch

**Preconditions:**
- Commit SHA exists in main branch

**Steps:**
1. Run merge_truth_verifier.py --commit-sha <sha>
2. Verify commit is found in main
3. Verify report shows verified=true

**Expected Result:** Commit is verified as present in main

#### Scenario 9: Detect False Merge Claim
**Objective:** Verify detection of commits not in main

**Preconditions:**
- Commit SHA does not exist in main branch

**Steps:**
1. Run merge_truth_verifier.py with invalid commit
2. Verify commit is not found
3. Verify report shows verified=false

**Expected Result:** False merge claim is detected and reported

### 3.4 CI Gate Integration (INTEG-001-B)

#### Scenario 10: Fast Gate Validation
**Objective:** Verify fast gate validation in PR mode

**Preconditions:**
- CI environment indicates PR build
- Fast required status files exist

**Steps:**
1. Set CI_COMMIT_PULL_REQUEST environment variable
2. Create status files for fast required gates
3. Run ci_gate.py
4. Verify only fast gates are checked

**Expected Result:** Only fast gates block the build

#### Scenario 11: Full Gate Validation
**Objective:** Verify full gate validation on main

**Preconditions:**
- CI environment indicates main branch push
- All required status files exist

**Steps:**
1. Set CI environment to main branch push
2. Create status files for all gates
3. Run ci_gate.py
4. Verify all gates are checked

**Expected Result:** All gates (fast + full) block the build

#### Scenario 12: Status File Inference
**Objective:** Verify inference of missing status files from logs

**Preconditions:**
- Status file is missing
- Log file exists with "skipping" message

**Steps:**
1. Create log file with skip message
2. Omit corresponding status file
3. Run ci_gate.py
4. Verify gate is treated as passed

**Expected Result:** Missing status is inferred from log content

---

## 4. Test Data

### 4.1 Mock Status Files

```bash
# Create mock CI status directory structure
/tmp/ci-status/
├── swarm-context.status          # Contains: 0
├── swarm-context.log             # Contains: "Gate passed"
├── lint.status                   # Contains: 0
├── lint.log                      # Contains: "No issues found"
├── security-scan.status          # Contains: 0
├── dependency-audit.status       # Contains: 0
├── secret-scan.status            # Contains: 0
├── risk-invariants.status        # Contains: 0
├── brain-regression.status       # Contains: 0
├── docs-pairing.status           # Contains: 0
├── docker-governance.status      # Contains: 0
├── changed-lines-coverage.status # Contains: 0
├── status-write-gate.status      # Contains: 0
├── performance-gate.status       # Contains: 0
├── evidence-gate.status          # Contains: 0
├── local-ci.status               # Contains: 0 (full-only)
└── brain-eval.status             # Contains: 0 (full-only)
```

### 4.2 Mock Evidence Files

```bash
# Create mock evidence directory structure
docs/evidence/
├── ST-TEST-001-evidence.json
├── ST-TEST-001-validation.md
└── ...
```

---

## 5. Test Environment

### 5.1 Requirements

| Component | Version | Purpose |
|-----------|---------|---------|
| Python | 3.11+ | Test execution |
| pytest | 8.0+ | Test framework |
| Git | 2.40+ | Merge verification |
| tempfile | Built-in | Isolated test directories |

### 5.2 Environment Variables

| Variable | Description | Test Usage |
|----------|-------------|------------|
| CI_STATUS_DIR | Path to CI status files | Mock gate results |
| CI_COMMIT_PULL_REQUEST | PR number if PR build | PR mode detection |
| CI | General CI indicator | CI environment detection |
| FORCE_FULL | Force full gate validation | Full mode testing |

---

## 6. Test Execution

### 6.1 Running Tests

```bash
# Run all integration tests
python3 -m pytest tests/integration/test_blocking_gates.py -v

# Run specific test class
python3 -m pytest tests/integration/test_blocking_gates.py::TestBlockingGatesRunner -v

# Run with coverage
python3 -m pytest tests/integration/test_blocking_gates.py --cov=scripts.ci -v

# Run slow E2E tests
python3 -m pytest tests/integration/test_blocking_gates.py -m slow -v
```

### 6.2 Expected Results

| Test Suite | Expected Pass Rate | Max Duration |
|------------|-------------------|--------------|
| TestBlockingGatesRunner | 100% | 30s |
| TestEvidenceGateRunner | 100% | 20s |
| TestMergeTruthVerifier | 100% | 15s |
| TestCIGateIntegration | 100% | 10s |
| TestEndToEndBlockingGates | 100% | 60s |

---

## 7. Success Criteria

### 7.1 Acceptance Criteria

- [ ] All blocking gates properly validate and report status
- [ ] Evidence gates correctly validate story evidence files
- [ ] Merge truth verifier accurately detects commits in main
- [ ] CI gate integration properly handles PR vs main builds
- [ ] All integration tests pass with 100% success rate
- [ ] CLI interfaces work correctly for all scripts

### 7.2 Quality Gates

| Gate | Threshold | Measurement |
|------|-----------|-------------|
| Test Pass Rate | 100% | pytest results |
| Code Coverage | >= 80% | coverage report |
| Lint | 0 errors | ruff check |
| Type Check | 0 errors | mypy |

---

## 8. Risks and Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Test flakiness | Medium | Low | Use temp directories, proper cleanup |
| CI environment differences | Medium | Medium | Mock CI variables, test locally |
| Git state dependencies | Low | Low | Use isolated test repos |
| Performance issues | Low | Low | Set timeouts, optimize tests |

---

## 9. Appendix

### 9.1 Test Matrix

| Component | Unit | Integration | E2E | Total |
|-----------|------|-------------|-----|-------|
| Blocking Gates Runner | 10 | 8 | 2 | 20 |
| Evidence Gate Runner | 5 | 4 | 2 | 11 |
| Merge Truth Verifier | 8 | 6 | 2 | 16 |
| CI Gate | 6 | 5 | 2 | 13 |
| **Total** | **29** | **23** | **8** | **60** |

### 9.2 Related Documents

- `docs/validation/validation-registry.yaml` - Validation requirements
- `docs/bmm-workflow-status.yaml` - Story tracking
- `.woodpecker/ci.yaml` - CI pipeline configuration

---

*Document Version History*

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-03-17 | senior-dev | Initial version |
