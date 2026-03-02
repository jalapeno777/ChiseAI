# CI Remediation Plan (ST-CI-001)

**Generated:** 2026-03-02
**Assessor:** Dev
**Status:** Draft - Pending Merlin Review

---

## 1. Executive Summary

| Metric | Value |
|--------|-------|
| Total Issues | 31 |
| P0-Critical | 2 |
| P1-High | 6 |
| P2-Medium | 7 |
| P3-Low | 16 |
| Est. Total Effort | 4-6 days |

**Key Finding:** CI pipeline intentionally disabled via branch filter `__woodpecker_disabled__`, blocking all automated quality gates.

---

## 2. Issue Inventory by Severity

### P0-Critical (Block All Merges)

| ID | Issue | Root Cause | Files Affected | Est. Effort |
|----|-------|------------|----------------|-------------|
| CI-001 | CI pipeline disabled | `__woodpecker_disabled__` branch filter in .woodpecker/ci.yaml | .woodpecker/ci.yaml | 2 hours |
| CI-002 | Hardcoded INFLUXDB_TOKEN | Secrets in source code | scripts/continuous_paper_emitter.py, scripts/paper_trading_manager.sh, etc. | 4 hours |

### P1-High (Significant Impact)

| ID | Issue | Root Cause | Files Affected | Est. Effort |
|----|-------|------------|----------------|-------------|
| CI-003 | Circular import in ml module | Import cycle: __init__.py → signal_outcome.py → __init__.py | src/ml/__init__.py | 2 hours |
| CI-004 | Test collection errors | 24 test files fail import | tests/test_ml/* | 4 hours |
| CI-005 | Bandit security scan suppressed | `# nosec` annotations bypass security checks | Multiple scripts | 2 hours |
| CI-006 | Woodpecker-Gitea auth failure | Authentication token expired/misconfigured | .woodpecker/ci.yaml | 2 hours |
| CI-007 | Test timeout failures | Pytest timeout too short for integration tests | pyproject.toml, tests/ | 2 hours |
| CI-008 | PR title validation missing | No enforcement of story ID tokens in PR titles | .woodpecker/ci.yaml | 1 hour |

### P2-Medium (Degraded Experience)

| ID | Issue | Root Cause | Files Affected | Est. Effort |
|----|-------|------------|----------------|-------------|
| CI-009 | Status sync drift | Epic status doesn't match child story statuses | docs/bmm-workflow-status.yaml | 2 hours |
| CI-010 | Docker container labeling | Missing `project=chiseai` labels on containers | docker-compose files | 1 hour |
| CI-011 | Test isolation issues | Tests depend on external services without mocking | tests/integration/ | 3 hours |
| CI-012 | Missing validation coverage | Some validation scripts not included in CI | scripts/validate_*.py | 2 hours |
| CI-013 | Local CI script incomplete | local-ci-checks.sh doesn't cover all stages | scripts/local-ci-checks.sh | 1 hour |
| CI-014 | Documentation gaps | CI troubleshooting docs outdated | docs/ci/ | 2 hours |
| CI-015 | Grafana dashboard missing | No CI metrics visualization | infrastructure/terraform/ | 3 hours |

### P3-Low (Minor)

| ID | Issue | Root Cause | Files Affected | Est. Effort |
|----|-------|------------|----------------|-------------|
| CI-016 | Log verbosity | Excessive logging in CI output | scripts/ | 1 hour |
| CI-017 | Branch naming inconsistency | Some branches don't follow naming convention | N/A (process) | 1 hour |
| CI-018 | Pre-commit hook gaps | Some files bypass validation | .pre-commit-config.yaml | 1 hour |
| CI-019 | Tempmemory scheduler not in CI | Compass operations not automated | scripts/ops/ | 2 hours |
| CI-020 | Brain eval stage disabled | Performance regression tests not running | .woodpecker/ci.yaml | 1 hour |
| CI-021 | Coverage reporting gaps | Some modules not included in coverage | pyproject.toml | 1 hour |
| CI-022 | Notification missing | No Discord/Slack alerts for CI failures | .woodpecker/ci.yaml | 2 hours |
| CI-023 | Pipeline watchdog incomplete | Health checks not comprehensive | scripts/pipeline_watchdog.py | 2 hours |
| CI-024 | Compass gate non-blocking | Validation failures don't block merge | .woodpecker/ci.yaml | 1 hour |
| CI-025 | PR auto-flow disabled | Automated PR processing not running | scripts/pr_auto_flow.py | 2 hours |
| CI-026 | Container health monitoring | No health checks for CI containers | docker-compose files | 2 hours |
| CI-027 | Backup strategy missing | No CI configuration backups | infrastructure/ | 2 hours |
| CI-028 | Rollback procedures undocumented | No documented rollback steps | docs/ci/ | 1 hour |
| CI-029 | Secrets rotation process | No documented secrets rotation | docs/ci/ | 2 hours |
| CI-030 | Incident response gaps | No CI-specific incident response | docs/incident-response/ | 2 hours |
| CI-031 | Performance baseline missing | No CI performance metrics tracked | docs/ci/ | 1 hour |

---

## 3. Top-5 Root Causes with Evidence

### RC1: CI Infrastructure Disabled
**Evidence:** .woodpecker/ci.yaml line 45: `branch: [__woodpecker_disabled__]`
**Impact:** No automated testing, linting, or security scans on PRs
**Fix:** Re-enable CI after fixing authentication issues

### RC2: Import Cycle in ML Module
**Evidence:**
```
$ python3 -c "from src.ml import SignalOutcome"
ImportError: cannot import name 'SignalOutcome' from partially initialized module
```
**Impact:** 24 test files cannot be collected
**Fix:** Restructure imports (lazy loading or module reorganization)

### RC3: Secrets in Source Code
**Evidence:**
```bash
$ grep -r "xBJwtATdOa7Sig8v" scripts/ | wc -l
10
```
**Impact:** Security risk, token exposure in git history
**Fix:** Migrate to environment variables

### RC4: Test Isolation Issues
**Evidence:** Pytest timeout errors, Docker networking failures
**Impact:** Flaky tests, slow CI execution
**Fix:** Better test fixtures, mock external services

### RC5: Status Sync Drift
**Evidence:** Epic status doesn't match child story statuses
**Impact:** Inaccurate project tracking
**Fix:** Update validation scripts to enforce consistency

---

## 4. Phased Remediation Sequence

### Phase 1: Critical Fixes (Days 1-2)
**Goal:** Unblock CI pipeline

| Day | Task | Owner | Deliverable |
|-----|------|-------|-------------|
| 1 | Fix Woodpecker-Gitea auth | merlin | CI pipeline running |
| 1 | Remove __woodpecker_disabled__ filter | dev | .woodpecker/ci.yaml updated |
| 2 | Fix circular import | dev | src/ml/__init__.py restructured |
| 2 | Remove hardcoded tokens | dev | Secrets migrated to env vars |

**Dependencies:** None
**Rollback:** Revert .woodpecker/ci.yaml changes

### Phase 2: Test Stability (Days 3-4)
**Goal:** Fix test collection and execution

| Day | Task | Owner | Deliverable |
|-----|------|-------|-------------|
| 3 | Fix test collection errors | dev | All 24 test files importable |
| 3 | Address pytest timeouts | dev | Test execution < 5 minutes |
| 4 | Improve test isolation | dev | Mock external services |

**Dependencies:** Phase 1 complete
**Rollback:** Revert test file changes

### Phase 3: CI Enhancements (Days 5-6)
**Goal:** Re-enable quality gates

| Day | Task | Owner | Deliverable |
|-----|------|-------|-------------|
| 5 | Re-enable linting blockers | dev | Black, ruff, mypy blocking |
| 5 | Fix status sync validation | dev | validate_status_sync.py passes |
| 6 | Update documentation | dev | docs/ci/ updated |

**Dependencies:** Phase 2 complete
**Rollback:** Disable blocking stages

---

## 5. Risk and Rollback Notes

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Woodpecker auth fails | Medium | High | Have Gitea admin credentials ready |
| Tests still flaky after fixes | Medium | Medium | Make tests non-blocking initially |
| Secrets rotation breaks prod | Low | High | Test in dev environment first |

**Rollback Procedures:**
- CI changes: `git revert <commit>` on .woodpecker/ci.yaml
- Test changes: `git checkout main -- tests/`
- Secrets: Restore from backup if env vars not set

---

## 6. Owner + ETA Table

| Phase | Owner | Start Date | ETA | Status |
|-------|-------|------------|-----|--------|
| Phase 1: Critical | merlin + dev | TBD | 2 days | Not started |
| Phase 2: Test Stability | dev | TBD | 2 days | Not started |
| Phase 3: Enhancements | dev | TBD | 2 days | Not started |

---

## 7. Next-Command Checklist

**Immediate Actions (This Week):**
- [ ] Review this plan with merlin
- [ ] Schedule Phase 1 execution
- [ ] Obtain Gitea admin credentials
- [ ] Create feature branch for CI fixes

**Before Phase 1:**
- [ ] Backup current .woodpecker/ci.yaml
- [ ] Verify Woodpecker server health
- [ ] Test authentication in dev environment

**Before Phase 2:**
- [ ] Verify Phase 1 complete
- [ ] Run test collection audit
- [ ] Identify test dependencies on external services

**Before Phase 3:**
- [ ] All tests passing
- [ ] Security scan clean
- [ ] Documentation updated

---

## Appendix A: Evidence References

- CI Configuration: `.woodpecker/ci.yaml`
- Test Collection Log: `_bmad-output/ci/test-collection.log`
- Security Scan: `bandit -r src/ scripts/`
- Import Cycle: `python3 -c "from src.ml import SignalOutcome"`

## Appendix B: Related Documentation

- AGENTS.md - Merge authority and CI policies
- docs/bmm-workflow-status.yaml - Story tracking
- .woodpecker/ci.yaml - CI pipeline definition
