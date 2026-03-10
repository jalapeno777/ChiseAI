# CI/CD Gate Coverage Matrix

> **Story**: ST-CI-001 - Real CI Gates (Phase 3 Enhanced)  
> **Last Updated**: 2026-03-09  
> **Purpose**: Map each CI gate to its runbook and remediation guidance

---

## Overview

This document provides a comprehensive mapping of all CI/CD pipeline gates defined in `.woodpecker/ci.yaml` to their respective runbooks, owners, and remediation procedures.

### Design Principle

The CI pipeline follows a **non-blocking steps with single fail point** design:
- Individual steps capture exit codes but always exit 0
- The `ci-gate` step (at the end) is the SINGLE authoritative failure point
- This ensures all validations run and provide feedback before failing

---

## Coverage Matrix

| CI Gate | Purpose | Owner | Runbook | Remediation Link |
|---------|---------|-------|---------|------------------|
| **swarm-context** | Repository context validation - verifies swarm session and branch context | senior-dev | [Swarm Session Command](.opencode/command/chise-swarm-session.md) | [Session Verification](#swarm-context-remediation) |
| **lint** | Code quality checks (black, ruff, mypy), status sync, iterlog governance, PR title validation, traceability drift | senior-dev | [Precommit Gates](.opencode/command/chise-precommit-gates.md) | [Lint Remediation](#lint-remediation) |
| **security-scan** | Bandit security analysis for changed Python files | senior-dev | TBD - Pending creation | [Bandit Docs](https://bandit.readthedocs.io/) |
| **dependency-audit** | pip-audit vulnerability scan for dependencies | senior-dev | TBD - Pending creation | [pip-audit Docs](https://github.com/pypa/pip-audit) |
| **secret-scan** | Hardcoded secret detection in changed files | senior-dev | TBD - Pending creation | [Secret Detection Guide](#secret-scan-remediation) |
| **risk-invariants** | Critical risk invariant tests (execution, kill switch, reconciliation) | senior-dev | [Kill Switch Runbook](docs/runbooks/kill-switch-trigger.md) | [Risk Invariant Remediation](#risk-invariants-remediation) |
| **brain-regression** | Brain evaluation regression tests | senior-dev | [Brain Eval Cadence](docs/runbooks/brain-eval-cadence.md) | [Brain Regression Remediation](#brain-regression-remediation) |
| **docs-pairing** | Documentation pairing validation | senior-dev | TBD - Pending creation | [Docs Pairing Remediation](#docs-pairing-remediation) |
| **docker-governance** | Docker container governance validation | senior-dev | [Docker Governance Skill](.opencode/skills/chiseai-docker-governance/SKILL.md) | [Docker Governance Remediation](#docker-governance-remediation) |
| **local-ci** | Full test suite execution with parallel processing | senior-dev | TBD - Pending creation | [Local CI Troubleshooting](#local-ci-remediation) |
| **changed-lines-coverage** | Coverage validation on changed lines (>80% threshold) | senior-dev | TBD - Pending creation | [Coverage Remediation](#changed-lines-coverage-remediation) |
| **pipeline-watchdog** | Monitors for stuck pipelines (>30 min timeout) | senior-dev | [Woodpecker Cron Runbook](docs/runbooks/Woodpecker-Cron-Setup-Runbook.md) | [Pipeline Watchdog Remediation](#pipeline-watchdog-remediation) |
| **pre-eval-ingestion** | Tempmemory ingestion before brain evaluation | senior-dev | [Brain Eval Ingestion](docs/runbooks/brain-eval-ingestion.md) | [Pre-eval Ingestion Remediation](#pre-eval-ingestion-remediation) |
| **brain-eval** | Brain evaluation with tempmemory context | senior-dev | [Brain Eval Cadence](docs/runbooks/brain-eval-cadence.md) | [Brain Eval Remediation](#brain-eval-remediation) |
| **tempmemory-scheduler** | Tempmemory migration dry-run | senior-dev | [TempMemory CI Scheduling](docs/runbooks/tempmemory-ci-scheduling.md) | [TempMemory Scheduler Remediation](#tempmemory-scheduler-remediation) |
| **mini-brain-eval** | Mini BrainEval with all sources (daily cadence) | senior-dev | [Mini BrainEval Runbook](docs/runbooks/mini-brain-eval.md) | [Mini BrainEval Remediation](#mini-brain-eval-remediation) |
| **tempmemory-reconcile** | Tempmemory reconciliation and archive | senior-dev | [TempMemory CI Scheduling](docs/runbooks/tempmemory-ci-scheduling.md) | [TempMemory Reconcile Remediation](#tempmemory-reconcile-remediation) |
| **tempmemory-drill** | Tempmemory reconciliation drill (cron/main only) | senior-dev | [TempMemory CI Scheduling](docs/runbooks/tempmemory-ci-scheduling.md) | [TempMemory Drill Remediation](#tempmemory-drill-remediation) |
| **flaky-detection** | Flaky test detection via repeated runs (cron/main only) | senior-dev | TBD - Pending creation | [Flaky Detection Remediation](#flaky-detection-remediation) |
| **compass-apply** | Auto-label PRs based on changed files | senior-dev | [Compass Operations](docs/runbooks/compass-operations-runbook.md) | [Compass Apply Remediation](#compass-apply-remediation) |
| **compass-gate** | Check for sensitive path changes requiring review | senior-dev | [Compass Operations](docs/runbooks/compass-operations-runbook.md) | [Compass Gate Remediation](#compass-gate-remediation) |
| **status-write-gate** | Workflow status file validation | senior-dev | [Workflow Archival Automation](docs/runbooks/workflow-archival-automation.md) | [Status Write Gate Remediation](#status-write-gate-remediation) |
| **status-evidence-gate** | Validate status evidence when workflow status changes | senior-dev | [Workflow Archival Automation](docs/runbooks/workflow-archival-automation.md) | [Status Evidence Remediation](#status-evidence-gate-remediation) |
| **completion-evidence-gate** | Validate completion evidence when workflow status changes | senior-dev | [Workflow Archival Automation](docs/runbooks/workflow-archival-automation.md) | [Completion Evidence Remediation](#completion-evidence-gate-remediation) |
| **workflow-transition-gate** | Validate workflow state transitions | senior-dev | [Workflow Archival Automation](docs/runbooks/workflow-archival-automation.md) | [Workflow Transition Remediation](#workflow-transition-gate-remediation) |
| **governance-drift-check** | Governance drift detection | senior-dev | [Validation Skill](.opencode/skills/chiseai-validation/SKILL.md) | [Governance Drift Remediation](#governance-drift-check-remediation) |
| **performance-gate** | Performance threshold validation (duration, memory) | senior-dev | TBD - Pending creation | [Performance Gate Remediation](#performance-gate-remediation) |
| **ci-gate** | Single authoritative failure point - aggregates all gate results | senior-dev | [CI Failure Bundle](.opencode/command/chise-ci-failure-bundle.md) | [CI Gate Remediation](#ci-gate-remediation) |

---

## Gate Categories

### Blocking Gates (FAST_REQUIRED)

These gates are always executed and can fail the pipeline:

| Gate | Description |
|------|-------------|
| swarm-context | Repository context validation |
| lint | Code quality and governance checks |
| security-scan | Security vulnerability scanning |
| dependency-audit | Dependency vulnerability audit |
| secret-scan | Secret detection |
| risk-invariants | Critical risk invariant tests |
| brain-regression | Brain evaluation regression |
| docs-pairing | Documentation pairing |
| docker-governance | Docker governance |
| changed-lines-coverage | Coverage on changed lines (>80%) |
| status-write-gate | Workflow status validation |
| performance-gate | Performance thresholds |

### Full-Only Gates (main/cron or FORCE_FULL_GATE=1)

These gates only run on main branch, cron events, or when forced:

| Gate | Description |
|------|-------------|
| local-ci | Full test suite |
| brain-eval | Brain evaluation |

### Cron-Only Gates (main cron or FORCE_CRON_GATE=1)

These gates only run on main branch cron events:

| Gate | Description |
|------|-------------|
| tempmemory-drill | Tempmemory reconciliation drill |
| flaky-detection | Flaky test detection |

### Supporting Gates

These gates provide supporting functionality:

| Gate | Description |
|------|-------------|
| pipeline-watchdog | Pipeline health monitoring |
| pre-eval-ingestion | Tempmemory pre-evaluation |
| tempmemory-scheduler | Tempmemory migration |
| mini-brain-eval | Mini brain evaluation |
| tempmemory-reconcile | Tempmemory reconciliation |
| compass-apply | Auto-labeling |
| compass-gate | Sensitive path detection |
| status-evidence-gate | Status evidence validation |
| completion-evidence-gate | Completion evidence validation |
| workflow-transition-gate | Workflow transition validation |
| governance-drift-check | Governance drift detection |

---

## Status File Locations

Each gate writes its results to:

```
/woodpecker/ci-status/${CI_PIPELINE_NUMBER}/
  ├── <gate-name>.log      # Full log output
  ├── <gate-name>.status   # Exit code (0 = success, non-zero = failure)
  └── <gate-name>.json     # Structured results (optional)
```

The `ci-gate` step aggregates all `.status` files to determine overall pipeline success.

---

## Remediation Guides

### Swarm Context Remediation

**Common Failures:**
- Missing `.swarm-session.json` file
- Invalid story ID format
- Branch mismatch with session

**Resolution Steps:**
1. Verify session exists: `python3 scripts/swarm/session.py verify --story-id=<id> --branch=<branch>`
2. Initialize session if missing: `python3 scripts/swarm/session.py start --story-id=<id> --branch=<branch>`
3. Check branch naming follows convention: `feature/<story-id>-<slug>`

**See Also:**
- [Swarm Session Command](.opencode/command/chise-swarm-session.md)
- [Git Workflow Skill](.opencode/skills/chiseai-git-workflow/SKILL.md)

### Lint Remediation

**Common Failures:**
- Black formatting violations
- Ruff linting errors
- mypy type checking failures
- Status sync validation failures
- PR title validation issues

**Resolution Steps:**
1. Run auto-format: `black src/`
2. Run auto-fix: `ruff check --fix src/`
3. Check status sync: `python3 scripts/validate_status_sync.py`
4. Validate PR title format follows conventional commits
5. Check traceability drift: `python3 scripts/validate_traceability_drift.py`

**See Also:**
- [Precommit Gates Command](.opencode/command/chise-precommit-gates.md)
- [Validation Skill](.opencode/skills/chiseai-validation/SKILL.md)

### Risk Invariants Remediation

**Common Failures:**
- Execution venue enforcement violations
- Kill switch test failures
- Reconciliation logic errors

**Resolution Steps:**
1. Review kill switch status: `./scripts/ops/kill_switch_check.sh`
2. Check execution logs: `docker logs chiseai-api --tail 100 | grep -i "kill\|emergency"`
3. Run risk tests locally: `pytest tests/test_execution/test_kill_switch/ -v`
4. Review [Kill Switch Runbook](docs/runbooks/kill-switch-trigger.md) for procedures

**Escalation Path:**
- P0/P1 issues: Escalate to Trading Lead immediately
- Contact: #trading-ops Slack channel

### Brain Regression Remediation

**Common Failures:**
- Brain evaluation test failures
- Neuro-symbolic logic regressions
- Governance tempmemory issues

**Resolution Steps:**
1. Run brain tests locally: `pytest tests/test_brain/ -v`
2. Check mini BrainEval results in `_bmad-output/brain-eval/`
3. Review [Mini BrainEval Runbook](docs/runbooks/mini-brain-eval.md) for troubleshooting
4. Validate brain changes are backward compatible

**See Also:**
- [Brain Eval Cadence](docs/runbooks/brain-eval-cadence.md)
- [Brain Eval Ingestion](docs/runbooks/brain-eval-ingestion.md)

### Docker Governance Remediation

**Common Failures:**
- Containers not on `chiseai` network
- Missing `project=chiseai` labels
- Protected container violations

**Resolution Steps:**
1. Check container network: `docker network inspect chiseai`
2. Verify labels: `docker inspect <container> --format='{{.Config.Labels}}'`
3. Run validation locally: `python3 scripts/ci/validate_docker_governance.py`
4. Review [Docker Governance Skill](.opencode/skills/chiseai-docker-governance/SKILL.md)

**Protected Containers (No Touch Without Approval):**
- `tradedev`
- `intelligent_ride` (MCP server)
- `aisetup-mcp-discord-1` (MCP server)
- `duckduckgo-mcp-server` (MCP server)

### CI Gate Remediation

**Common Failures:**
- Multiple gate failures aggregated
- Missing status files
- Pipeline timeout

**Resolution Steps:**
1. Generate failure bundle: `python3 scripts/ci/woodpecker_triage.py bundle --pipeline <number>`
2. Check individual gate logs in `/woodpecker/ci-status/<number>/`
3. Review [CI Failure Bundle Command](.opencode/command/chise-ci-failure-bundle.md)
4. Escalate to `merlin` if complex failures across multiple gates

**See Also:**
- [CI Root Cause Command](.opencode/command/chise-ci-root-cause.md)
- [Incident Response Skill](.opencode/skills/chiseai-incident-response/SKILL.md)

### TempMemory Gates Remediation

**Applies to:** tempmemory-scheduler, tempmemory-reconcile, tempmemory-drill, pre-eval-ingestion

**Common Failures:**
- Redis connectivity issues
- Missing tempmemory files
- Migration script errors

**Resolution Steps:**
1. Check Redis connectivity: `redis-cli -p 6380 ping`
2. Verify tempmemory files exist: `ls docs/tempmemories/*.md`
3. Run migration dry-run: `python3 scripts/ops/tempmemory_migration.py --dry-run`
4. Review [TempMemory CI Scheduling](docs/runbooks/tempmemory-ci-scheduling.md)
5. Check scheduler logs: `cat _bmad-output/ci/tempmemory-scheduler.log`

### Workflow Gates Remediation

**Applies to:** status-write-gate, status-evidence-gate, completion-evidence-gate, workflow-transition-gate

**Common Failures:**
- Invalid status transitions
- Missing evidence for status changes
- YAML syntax errors in workflow status

**Resolution Steps:**
1. Validate transitions: `python3 scripts/validation/validate_workflow_transitions.py`
2. Check evidence requirements: `python3 scripts/validation/validate_status_evidence.py`
3. Validate completion: `python3 scripts/validate_completion_evidence.py`
4. Review [Workflow Archival Automation](docs/runbooks/workflow-archival-automation.md)
5. Check YAML syntax: `yamllint docs/bmm-workflow-status.yaml`

### Governance Drift Remediation

**Common Failures:**
- Governance configuration drift
- Missing required files
- Policy violations

**Resolution Steps:**
1. Run drift check locally: `python3 scripts/validation/governance_drift_guard.py --verbose`
2. Review [Validation Skill](.opencode/skills/chiseai-validation/SKILL.md)
3. Check governance patterns in `docs/validation/validation-registry.yaml`

### Compass Gates Remediation

**Common Failures:**
- Label application errors
- Sensitive path detection issues

**Resolution Steps:**
1. Review [Compass Operations Runbook](docs/runbooks/compass-operations-runbook.md)
2. Check compass apply logs in CI artifacts
3. Run compass gate locally: `python3 scripts/ci/compass_gate.py --check`

---

## Notes

### Pending Runbook Creation

The following gates still need dedicated runbooks created:

1. **security-scan** - Bandit security scanning procedures
2. **dependency-audit** - pip-audit vulnerability remediation
3. **secret-scan** - Secret detection and rotation procedures
4. **docs-pairing** - Documentation pairing validation procedures
5. **local-ci** - Full test suite troubleshooting
6. **changed-lines-coverage** - Coverage threshold remediation
7. **flaky-detection** - Flaky test identification and fixing
8. **performance-gate** - Performance threshold tuning

When creating new runbooks:
1. Update the corresponding row in the matrix above
2. Follow the naming convention: `docs/runbooks/ci-<gate-name>.md`
3. Include: Purpose, Common Failures, Troubleshooting Steps, Escalation Path

### Contributing

To add a new runbook:
1. Create file at `docs/runbooks/ci-<gate-name>.md`
2. Update this matrix with the runbook link
3. Add remediation section in this document
4. Update the changelog below

### Related Documents

- [`.woodpecker/ci.yaml`](.woodpecker/ci.yaml) - Pipeline definition
- [`docs/bmm-workflow-status.yaml`](docs/bmm-workflow-status.yaml) - Workflow status tracking
- [`docs/validation/validation-registry.yaml`](docs/validation/validation-registry.yaml) - Validation registry
- [`.opencode/skills/chiseai-validation/SKILL.md`](.opencode/skills/chiseai-validation/SKILL.md) - Validation patterns
- [`.opencode/skills/chiseai-incident-response/SKILL.md`](.opencode/skills/chiseai-incident-response/SKILL.md) - Incident response

---

## Changelog

| Date | Change | Author |
|------|--------|--------|
| 2026-03-09 | Initial matrix creation | senior-dev |
| 2026-03-09 | Replaced TBD with concrete links where available | senior-dev |

---

## Quick Reference: CI Failure Response

When a CI gate fails:

1. **Check the gate log:**
   ```bash
   cat /woodpecker/ci-status/${CI_PIPELINE_NUMBER}/<gate-name>.log
   ```

2. **Generate failure bundle:**
   ```bash
   python3 scripts/ci/woodpecker_triage.py bundle --pipeline ${CI_PIPELINE_NUMBER}
   ```

3. **Find the remediation:**
   - Look up the gate in the matrix above
   - Follow the remediation link
   - Run local validation if available

4. **Escalation:**
   - P0/P1 failures: Escalate immediately
   - Multiple gate failures: Handoff to `merlin`
   - Complex issues: Schedule post-mortem
