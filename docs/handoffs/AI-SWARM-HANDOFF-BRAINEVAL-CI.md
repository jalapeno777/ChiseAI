# AI Swarm Handoff: BrainEval KPI System

**Document Type:** Handoff Document  
**Created:** 2026-03-02  
**For:** Next AI Swarm  
**Scope:** BrainEval KPI System Validation & CI Integration  
**Status:** Code Complete, Needs Validation

---

## 1. Current State Snapshot

### What Was Just Merged
The following stories have been merged to `main` with these commit SHAs:

| Commit SHA | Story | Description |
|------------|-------|-------------|
| `71f9f3d` | ST-KPI-002 | Trend rollups with brain evaluators wired to CI |
| `b23fcc6` | ST-KPI-003 | Reflection output generator with bottleneck analysis |
| `68e6a1d` | ST-KPI-005 | BrainEval scheduler, KPI persistence, trend rollups, weekly reflection |
| `ec09051` | ST-KPI-005 | BrainEval scheduler, trend rollups, and reflection system |

### Files Added/Modified

**New Files (Core System):**
```
scripts/evaluation/kpi_scheduler.py       # Docker-safe scheduling
scripts/evaluation/run_daily_trends.py    # Daily trend rollups
scripts/evaluation/run_weekly_reflection.py  # Weekly deep reflection
scripts/evaluation/run_mini_eval.py       # Mini evaluation runner
src/evaluation/kpi_persistence.py         # KPI persistence layer
src/evaluation/trend_rollups.py           # Trend rollup engine
```

**New Files (Tests):**
```
tests/unit/evaluation/test_kpi_persistence.py
tests/unit/evaluation/test_trend_rollups.py
```

**Modified Files:**
```
.woodpecker/cron-eval.yaml                # CI cron configuration
src/evaluation/brain_eval_ci.py           # Wired to CI ingestion path
```

### System Status

| Component | Status | Notes |
|-----------|--------|-------|
| BrainEval KPI System | Code Complete | All modules implemented |
| Trend Rollups | Code Complete | Daily aggregation logic ready |
| Weekly Reflection | Code Complete | Bottleneck analysis ready |
| KPI Persistence | Code Complete | Redis-based storage ready |
| Scheduler | Code Complete | Docker-safe cron scheduling |
| CI Integration | Partial | Woodpecker config needs verification |
| Full CI Test Run | Not Executed | Needs validation |
| End-to-End Validation | Not Started | Critical gap |

---

## 2. What Was Shipped

### Core Features

#### 2.1 KPI Scheduler (`scripts/evaluation/kpi_scheduler.py`)
- Docker-safe scheduling system for BrainEval KPIs
- Handles daily trend rollup jobs
- Handles weekly reflection generation
- Manages job state and prevents duplicate runs
- Integrates with Redis for coordination

#### 2.2 Daily Trend Rollups (`scripts/evaluation/run_daily_trends.py`)
- Aggregates daily KPI metrics
- Computes trend indicators
- Stores results in persistence layer
- Triggered by scheduler or manual execution

#### 2.3 Weekly Reflection (`scripts/evaluation/run_weekly_reflection.py`)
- Generates deep reflection reports
- Performs bottleneck analysis
- Identifies performance patterns
- Produces actionable recommendations

#### 2.4 Mini Evaluation Runner (`scripts/evaluation/run_mini_eval.py`)
- Lightweight evaluation for quick checks
- Can be run ad-hoc or scheduled
- Useful for CI integration testing

#### 2.5 KPI Persistence Layer (`src/evaluation/kpi_persistence.py`)
- Redis-backed storage for KPI data
- Handles data serialization
- Provides query interface for historical data
- Manages TTL and cleanup

#### 2.6 Trend Rollup Engine (`src/evaluation/trend_rollups.py`)
- Core aggregation logic
- Computes moving averages, deltas, anomalies
- Supports multiple time windows
- Configurable rollup strategies

#### 2.7 CI Cron Configuration (`.woodpecker/cron-eval.yaml`)
- Woodpecker CI pipeline for scheduled evaluation
- Configured to run daily and weekly jobs
- Integrates with existing CI infrastructure

---

## 3. Known Issues / Risks

### Critical Risks (Must Address)

| Risk | Severity | Impact | Mitigation |
|------|----------|--------|------------|
| Woodpecker CI cron jobs not verified | High | Scheduled jobs may not run | Re-enable and test cron configuration |
| Full CI test run not executed | High | Undetected regressions possible | Run complete test suite |
| BrainEval system not E2E validated | High | System may have integration gaps | Execute full validation plan |
| Scheduler-CI pipeline integration untested | Medium | Jobs may fail silently | Test integration manually |

### Known Issues

1. **Woodpecker CI Status Unknown**
   - Cron jobs may be disabled or misconfigured
   - Pipeline definition needs validation
   - Woodpecker server health check needed

2. **Missing Test Coverage**
   - Integration tests not yet written
   - E2E validation scripts not created
   - Performance/load tests pending

3. **Documentation Gaps**
   - API documentation incomplete
   - Runbook for troubleshooting not written
   - Configuration reference missing

---

## 4. Mission Objectives for Next Swarm

### Objective 1: Run Full CI Check and Full CI Test Run
**Priority:** P0 (Critical)  
**Estimated Time:** 30-45 minutes  
**Success Criteria:** All quality gates pass

### Objective 2: Re-enable/Verify Woodpecker CI and Cron Jobs
**Priority:** P0 (Critical)  
**Estimated Time:** 20-30 minutes  
**Success Criteria:** Cron jobs execute successfully

### Objective 3: Validate BrainEval System End-to-End
**Priority:** P0 (Critical)  
**Estimated Time:** 45-60 minutes  
**Success Criteria:** All components work together correctly

### Objective 4: Identify and Document Remaining Gaps/Additions
**Priority:** P1 (High)  
**Estimated Time:** 20-30 minutes  
**Success Criteria:** Gap analysis document created

---

## 5. Step-by-Step Execution Plan

### Objective 1: Full CI Check

```bash
# Step 1.1: Navigate to project root
cd /home/tacopants/projects/ChiseAI

# Step 1.2: Verify Python environment
python3 --version
# Expected: Python 3.10+ (check pyproject.toml for exact version)

# Step 1.3: Install dependencies (if needed)
pip install -e ".[dev]" 2>/dev/null || pip install -r requirements-dev.txt

# Step 1.4: Run Black formatting check
black --check src/ scripts/
# Expected: "All done! ✨ 🍰 ✨" with no changes needed

# Step 1.5: Run Ruff linting
ruff check src/ scripts/
# Expected: "All checks passed!"

# Step 1.6: Run full test suite with coverage
pytest tests/ --cov=src --cov-report=term-missing --cov-report=html
# Expected: All tests pass, coverage > 80%

# Step 1.7: Run unit tests specifically for evaluation module
pytest tests/unit/evaluation/ -v
# Expected: All evaluation tests pass

# Step 1.8: Type checking (if mypy configured)
mypy src/evaluation/ --ignore-missing-imports 2>/dev/null || echo "mypy not configured, skipping"
```

### Objective 2: Woodpecker CI Verification

```bash
# Step 2.1: Check Woodpecker pipeline configuration
cat .woodpecker/cron-eval.yaml

# Step 2.2: Validate YAML syntax
python3 -c "import yaml; yaml.safe_load(open('.woodpecker/cron-eval.yaml'))"
# Expected: No errors (silent success)

# Step 2.3: Check if Woodpecker server is accessible
curl -s http://host.docker.internal:8012/health || curl -s http://localhost:8012/health
# Expected: HTTP 200 with health status

# Step 2.4: List Woodpecker repositories
woodpecker-cli repo list 2>/dev/null || echo "woodpecker-cli not available, check web UI"

# Step 2.5: Check cron job status in Woodpecker
# Navigate to: http://host.docker.internal:8012 or http://localhost:8012
# Go to: Repository Settings > Cron Jobs
# Verify: cron-eval jobs are enabled and scheduled

# Step 2.6: Manually trigger a cron job for testing
# In Woodpecker UI: Find cron-eval pipeline > Click "Run"
# Or via API if available

# Step 2.7: Check Woodpecker agent status
docker ps --filter name=woodpecker
# Expected: woodpecker-server and woodpecker-agent running

# Step 2.8: Review recent pipeline runs
# In Woodpecker UI: Check for recent cron-eval executions
# Look for: Success/failure status, execution logs
```

### Objective 3: BrainEval E2E Validation

```bash
# Step 3.1: Verify Redis is running
docker ps --filter name=chiseai-redis
# Expected: chiseai-redis container running

# Step 3.2: Test Redis connectivity
redis-cli -h host.docker.internal -p 6380 ping 2>/dev/null || \
  docker exec chiseai-redis redis-cli ping
# Expected: PONG

# Step 3.3: Run KPI scheduler in dry-run mode
python3 scripts/evaluation/kpi_scheduler.py --dry-run
# Expected: Shows scheduled jobs without executing

# Step 3.4: Run mini evaluation (quick smoke test)
python3 scripts/evaluation/run_mini_eval.py
# Expected: Completes without errors, outputs KPI summary

# Step 3.5: Test KPI persistence layer
python3 -c "
from src.evaluation.kpi_persistence import KPIPersistence
import redis
r = redis.Redis(host='host.docker.internal', port=6380, decode_responses=True)
kp = KPIPersistence(r)
print('KPIPersistence initialized successfully')
"
# Expected: "KPIPersistence initialized successfully"

# Step 3.6: Test trend rollups (manual trigger)
python3 scripts/evaluation/run_daily_trends.py --date $(date +%Y-%m-%d)
# Expected: Processes trends, stores results, exits cleanly

# Step 3.7: Test weekly reflection (manual trigger)
python3 scripts/evaluation/run_weekly_reflection.py --week $(date +%Y-W%V)
# Expected: Generates reflection report, outputs to stdout or file

# Step 3.8: Verify data in Redis
redis-cli -h host.docker.internal -p 6380 KEYS 'braineval:*' 2>/dev/null | head -20
# Expected: Lists BrainEval-related keys

# Step 3.9: Check trend rollup output
redis-cli -h host.docker.internal -p 6380 HGETALL 'braineval:trends:daily' 2>/dev/null | head -20
# Expected: Shows daily trend data

# Step 3.10: Validate scheduler state
redis-cli -h host.docker.internal -p 6380 HGETALL 'braineval:scheduler:state' 2>/dev/null
# Expected: Shows scheduler job states
```

### Objective 4: Gap Analysis

```bash
# Step 4.1: Review test coverage gaps
coverage report --omit='tests/*' | grep -E '(evaluation|kpi|brain)' || \
  pytest tests/ --cov=src --cov-report=term 2>&1 | grep -A 20 'evaluation'

# Step 4.2: Check for TODO/FIXME comments in new code
grep -r 'TODO\|FIXME\|XXX' scripts/evaluation/ src/evaluation/ || echo "No TODOs found"

# Step 4.3: Verify all new files have docstrings
python3 -c "
import ast
import os

def check_docstrings(path):
    for root, dirs, files in os.walk(path):
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                with open(filepath) as f:
                    try:
                        tree = ast.parse(f.read())
                        for node in ast.walk(tree):
                            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                                if not ast.get_docstring(node):
                                    print(f'Missing docstring: {filepath}:{node.lineno} {node.name}')
                    except SyntaxError:
                        pass

check_docstrings('src/evaluation')
check_docstrings('scripts/evaluation')
" 2>/dev/null

# Step 4.4: Check for configuration files
cat > /tmp/gap_check.sh << 'EOF'
#!/bin/bash
echo "=== Configuration Files Check ==="
echo ""
echo "1. Environment variables needed:"
grep -r 'os.environ\|os.getenv' scripts/evaluation/ src/evaluation/ | grep -v '.pyc' || echo "No env vars found"
echo ""
echo "2. Config files present:"
ls -la config/*.yaml 2>/dev/null || echo "No config/*.yaml files"
echo ""
echo "3. Documentation files:"
ls -la docs/*brain* docs/*kpi* docs/*eval* 2>/dev/null || echo "No BrainEval/KPI docs found"
EOF
bash /tmp/gap_check.sh

# Step 4.5: Create gap analysis document
cat > docs/handoffs/BrainEval-Gap-Analysis-$(date +%Y%m%d).md << 'EOF'
# BrainEval Gap Analysis

**Date:** $(date +%Y-%m-%d)
**Analyzed By:** Next AI Swarm

## Coverage Gaps

| Gap | Severity | Action Required |
|-----|----------|-----------------|
| <!-- Fill in --> | <!-- P0/P1/P2 --> | <!-- Description --> |

## Integration Gaps

| Gap | Severity | Action Required |
|-----|----------|-----------------|
| <!-- Fill in --> | <!-- P0/P1/P2 --> | <!-- Description --> |

## Documentation Gaps

| Gap | Severity | Action Required |
|-----|----------|-----------------|
| <!-- Fill in --> | <!-- P0/P1/P2 --> | <!-- Description --> |

## Recommended Next Steps

1. <!-- Step 1 -->
2. <!-- Step 2 -->
3. <!-- Step 3 -->
EOF
echo "Gap analysis template created at: docs/handoffs/BrainEval-Gap-Analysis-$(date +%Y%m%d).md"
```

---

## 6. Validation Checklist (PASS/FAIL Table)

### Code Quality Checks

| Check | Command | Expected Result | Status |
|-------|---------|-----------------|--------|
| Black formatting | `black --check src/ scripts/` | No changes needed | ⬜ |
| Ruff linting | `ruff check src/ scripts/` | No errors | ⬜ |
| Import sorting | `isort --check-only src/ scripts/` 2>/dev/null || echo "isort not configured" | No changes | ⬜ |
| Type checking | `mypy src/evaluation/ 2>/dev/null` || echo "mypy not configured" | No type errors | ⬜ |

### Unit Tests

| Check | Command | Expected Result | Status |
|-------|---------|-----------------|--------|
| All unit tests | `pytest tests/unit/ -v` | All pass | ⬜ |
| Evaluation tests | `pytest tests/unit/evaluation/ -v` | All pass | ⬜ |
| Coverage threshold | `pytest tests/ --cov=src --cov-fail-under=80` | Coverage ≥ 80% | ⬜ |
| KPI persistence tests | `pytest tests/unit/evaluation/test_kpi_persistence.py -v` | All pass | ⬜ |
| Trend rollup tests | `pytest tests/unit/evaluation/test_trend_rollups.py -v` | All pass | ⬜ |

### Integration & E2E

| Check | Command | Expected Result | Status |
|-------|---------|-----------------|--------|
| Redis connectivity | `redis-cli -h host.docker.internal -p 6380 ping` | PONG | ⬜ |
| KPI persistence init | Python import test (see Step 3.5) | Success | ⬜ |
| Mini eval run | `python3 scripts/evaluation/run_mini_eval.py` | Completes cleanly | ⬜ |
| Scheduler dry-run | `python3 scripts/evaluation/kpi_scheduler.py --dry-run` | Shows jobs | ⬜ |
| Daily trends | `python3 scripts/evaluation/run_daily_trends.py` | Processes data | ⬜ |
| Weekly reflection | `python3 scripts/evaluation/run_weekly_reflection.py` | Generates report | ⬜ |
| Data in Redis | `redis-cli KEYS 'braineval:*'` | Keys exist | ⬜ |

### CI/CD Verification

| Check | Command | Expected Result | Status |
|-------|---------|-----------------|--------|
| Woodpecker health | `curl http://host.docker.internal:8012/health` | HTTP 200 | ⬜ |
| Cron YAML valid | `python3 -c "import yaml; yaml.safe_load(open('.woodpecker/cron-eval.yaml'))"` | No errors | ⬜ |
| Cron jobs enabled | Check Woodpecker UI | Jobs active | ⬜ |
| Pipeline runs | Check Woodpecker UI recent runs | Recent executions | ⬜ |
| Container status | `docker ps --filter name=woodpecker` | Both running | ⬜ |

### Documentation

| Check | Verification Method | Expected Result | Status |
|-------|---------------------|-----------------|--------|
| Docstrings present | Code review | All public APIs documented | ⬜ |
| README updated | Check docs/ | BrainEval section exists | ⬜ |
| Configuration docs | Check docs/ | Config reference exists | ⬜ |
| Runbook exists | Check docs/runbooks/ | Troubleshooting guide exists | ⬜ |

---

## 7. Rollback/Recovery Notes

### If Issues Found During Validation

#### Option 1: Revert Specific Commits

```bash
# Revert all KPI-related commits (use with caution)
git revert --no-commit 71f9f3d
git revert --no-commit 68e6a1d
git revert --no-commit ec09051
git revert --no-commit b23fcc6

# Review changes
git status
git diff --cached

# Commit the revert
git commit -m "revert: rollback BrainEval KPI system due to validation failures"

# Push to main (requires appropriate permissions)
git push origin main
```

#### Option 2: Disable Cron Jobs Only

```bash
# Option A: Via Woodpecker UI
# Navigate to: http://host.docker.internal:8012
# Go to: Repository Settings > Cron Jobs
# Disable: cron-eval jobs

# Option B: Rename cron file to disable
git mv .woodpecker/cron-eval.yaml .woodpecker/cron-eval.yaml.disabled
git commit -m "chore(ci): disable BrainEval cron jobs pending validation"
git push origin main
```

#### Option 3: Feature Flag Approach

```bash
# Add feature flag to disable BrainEval at runtime
# Edit: src/evaluation/kpi_persistence.py or config file

export BRAINEVAL_ENABLED=false
# Or add to .env file
```

### Recovery Procedures

#### If Redis Data Corruption

```bash
# Backup current Redis data
docker exec chiseai-redis redis-cli BGSAVE
docker cp chiseai-redis:/data/dump.rdb /backup/redis-dump-$(date +%Y%m%d).rdb

# Clear BrainEval keys only (selective cleanup)
redis-cli -h host.docker.internal -p 6380 KEYS 'braineval:*' | xargs redis-cli DEL

# Or full flush (nuclear option - use with caution)
redis-cli -h host.docker.internal -p 6380 FLUSHDB
```

#### If Scheduler Stuck

```bash
# Clear scheduler state
redis-cli -h host.docker.internal -p 6380 DEL 'braineval:scheduler:state'

# Restart scheduler
python3 scripts/evaluation/kpi_scheduler.py --reset-state
```

---

## 8. Expected Deliverables

### Required Outputs

| Deliverable | Format | Location | Status |
|-------------|--------|----------|--------|
| CI Test Run Report | Markdown | `docs/handoffs/CI-Test-Report-$(date +%Y%m%d).md` | ⬜ |
| Woodpecker CI Status Report | Markdown | `docs/handoffs/Woodpecker-Status-$(date +%Y%m%d).md` | ⬜ |
| BrainEval Validation Report | Markdown | `docs/handoffs/BrainEval-Validation-$(date +%Y%m%d).md` | ⬜ |
| Gap Analysis Document | Markdown | `docs/handoffs/BrainEval-Gap-Analysis-$(date +%Y%m%d).md` | ⬜ |
| Updated Documentation | Markdown | `docs/brain/` or `docs/evaluation/` | ⬜ |

### Report Templates

#### CI Test Run Report Template

Create `docs/handoffs/CI-Test-Report-$(date +%Y%m%d).md`:

```markdown
# CI Test Run Report

**Date:** YYYY-MM-DD
**Executed By:** [Agent Name]
**Branch:** main
**Commit:** [SHA]

## Summary
- Tests Passed: X/Y
- Coverage: X%
- Quality Gates: Pass/Fail

## Detailed Results

### Black Formatting
```
[Paste output]
```

### Ruff Linting
```
[Paste output]
```

### Test Results
```
[Paste pytest output]
```

### Coverage Report
```
[Paste coverage output]
```

## Issues Found
- [ ] Issue 1
- [ ] Issue 2

## Recommendations
1. [Recommendation 1]
2. [Recommendation 2]
```

#### BrainEval Validation Report Template

Create `docs/handoffs/BrainEval-Validation-$(date +%Y%m%d).md`:

```markdown
# BrainEval Validation Report

**Date:** YYYY-MM-DD
**Executed By:** [Agent Name]
**Components Tested:** All

## Test Results

| Component | Test | Result | Notes |
|-----------|------|--------|-------|
| KPI Scheduler | Dry-run | Pass/Fail | |
| Trend Rollups | Daily execution | Pass/Fail | |
| Weekly Reflection | Weekly execution | Pass/Fail | |
| KPI Persistence | Redis storage | Pass/Fail | |
| Mini Eval | Quick run | Pass/Fail | |

## Data Verification

### Redis Keys Created
```
[Paste redis-cli output]
```

### Sample Data
```
[Paste sample KPI data]
```

## Issues Found
- [ ] Issue 1
- [ ] Issue 2

## Sign-off
- [ ] All critical tests pass
- [ ] Data integrity verified
- [ ] Ready for production
```

---

## 9. Quick Reference

### Key File Locations

| Component | Path |
|-----------|------|
| KPI Scheduler | `scripts/evaluation/kpi_scheduler.py` |
| Daily Trends | `scripts/evaluation/run_daily_trends.py` |
| Weekly Reflection | `scripts/evaluation/run_weekly_reflection.py` |
| Mini Eval | `scripts/evaluation/run_mini_eval.py` |
| KPI Persistence | `src/evaluation/kpi_persistence.py` |
| Trend Rollups | `src/evaluation/trend_rollups.py` |
| CI Config | `.woodpecker/cron-eval.yaml` |
| Unit Tests | `tests/unit/evaluation/` |

### Important Commands Cheat Sheet

```bash
# Quality checks
black --check src/ scripts/
ruff check src/ scripts/
pytest tests/ --cov=src

# Redis
redis-cli -h host.docker.internal -p 6380 ping
redis-cli -h host.docker.internal -p 6380 KEYS 'braineval:*'

# BrainEval scripts
python3 scripts/evaluation/kpi_scheduler.py --dry-run
python3 scripts/evaluation/run_mini_eval.py
python3 scripts/evaluation/run_daily_trends.py
python3 scripts/evaluation/run_weekly_reflection.py

# Docker
docker ps --filter name=chiseai
docker ps --filter name=woodpecker
docker logs chiseai-redis --tail 50

# Woodpecker
curl http://host.docker.internal:8012/health
# Or check web UI at http://localhost:8012
```

### Support Contacts

| Issue Type | Escalation Path |
|------------|-----------------|
| Redis connectivity | Check Docker network, container status |
| Woodpecker issues | Check container logs, verify config |
| Test failures | Review error output, check dependencies |
| Code issues | Review implementation, check imports |

---

## 10. Sign-off Checklist

Before considering this handoff complete, the next swarm should:

- [ ] All P0 objectives completed
- [ ] All validation checks pass (or issues documented)
- [ ] Deliverables created and saved to `docs/handoffs/`
- [ ] Gap analysis completed
- [ ] No critical blockers remaining
- [ ] Handoff document updated with findings
- [ ] Jarvis notified of completion

---

**End of Handoff Document**

*This document was created by the Senior Dev agent on 2026-03-02 as part of the BrainEval KPI system handoff process.*
