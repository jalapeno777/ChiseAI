# Evidence Summary File Inventory

## Primary Evidence Document
| File | Description |
|------|-------------|
| `SESSION-EVIDENCE-SUMMARY-2026-02-11.md` | Main comprehensive evidence summary |

## CI Artifacts (`_bmad-output/ci/`)

### Test & Coverage Artifacts
- `pytest-junit.xml` (187 KB) - JUnit XML test results
- `pytest-check.log` (166 KB) - Pytest execution log
- `coverage.xml` (302 KB) - Cobertura coverage XML
- `test-coverage-report.md` (4.5 KB) - Coverage summary

### Lint Artifacts  
- `black-check.log` - Black format check output
- `ruff-check.log` - Ruff lint check output
- `mypy-check.log` - MyPy type check output
- `lint-findings.md` (3.4 KB) - Lint summary

### Security Artifacts
- `bandit-report.json` (28 KB) - Bandit security findings
- `security-scan-results.md` (4.9 KB) - Security scan summary
- `bandit-check.log` (20 KB) - Bandit execution log

### CI Execution Logs
- `local-ci.log` - Full CI execution log
- `ci-run-20260211-091208.log` - Specific run log
- `final-validation.log` - Final validation results
- `CI_FIX_REPORT.md` (6.2 KB) - CI corrections report

### Status & Migration Artifacts
- `ci-gate-status.md` (3.0 KB) - Gate status summary
- `tempmemories-migration-ledger.md` (4.9 KB) - Complete migration ledger
- `tempmemories-migration-final.md` (1.2 KB) - Migration completion report
- `pr-preparation-summary.md` (1.0 KB) - PR preparation summary

### Iteration Loop Artifacts
- `iterloop-*.log` (20 files) - Iteration loop execution logs
- `iterloop-*-exit.txt` (20 files) - Exit codes for iterations

## Status Files
| File | Description |
|------|-------------|
| `docs/bmm-workflow-status.yaml` | Authoritative BMAD state machine |
| `docs/validation/validation-registry.yaml` | Validation truth table |

## Git Commit History (Session)
| Commit | Message |
|--------|---------|
| fc3fae6 | Update status: Batch 1 (16 SP) completed |
| 81b980a | Implement ST-DATA-003: Continuous backtest runner |
| 2c783fe | Implement ST-DATA-002: Bybit/Bitget execution data |
| edeaa4d | Implement ST-SIG-001: Strategy DSL schema |
| 418df91 | Implement ST-SIG-002: Strategy registry |
| f7cfdea | Add sprint plan: paper-readiness-01 (32 SP) |
| 98821a4 | Reconcile status files to evidence-backed reality |
| 0a4c9f6 | Remove chiseai-api/dashboard from Terraform |
| 248e647 | fix: allow empty tempmemories validation |
| 40ae3b0 | chore: clean up old temp memory files |

## Container Inventory (14 Running)
| Container | Status | Ports |
|-----------|--------|-------|
| chiseai-influxdb | ✅ Up | 18087 |
| woodpecker-server | ✅ Up | 8012 |
| taiga-events | ✅ Up | 9003 |
| taiga-front | ✅ Up | 9001 |
| chiseai-postgres | ✅ Up | 5434 |
| woodpecker-agent | ✅ Up | 3000 |
| taiga-postgres | ✅ Up | 5432 |
| taiga-redis | ✅ Up | 6379 |
| chiseai-redis | ✅ Up | 6380 |
| taiga-rabbitmq | ✅ Up | Multiple |
| gitea | ✅ Up | 3000, 2222 |
| chiseai-qdrant | ✅ Up | 6334 |
| chiseai-grafana | ✅ Up | 3001 |
| taiga-back | ✅ Up | 9002 |

---

**Generated:** 2026-02-11  
**Location:** `_bmad-output/evidence-summary/`
