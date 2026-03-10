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
| **swarm-context** | Repository context validation - verifies swarm session and branch context | senior-dev | TBD | TBD |
| **lint** | Code quality checks (black, ruff, mypy), status sync, iterlog governance, PR title validation, traceability drift | senior-dev | TBD | TBD |
| **security-scan** | Bandit security analysis for changed Python files | senior-dev | TBD | TBD |
| **dependency-audit** | pip-audit vulnerability scan for dependencies | senior-dev | TBD | TBD |
| **secret-scan** | Hardcoded secret detection in changed files | senior-dev | TBD | TBD |
| **risk-invariants** | Critical risk invariant tests (execution, kill switch, reconciliation) | senior-dev | TBD | TBD |
| **brain-regression** | Brain evaluation regression tests | senior-dev | TBD | TBD |
| **docs-pairing** | Documentation pairing validation | senior-dev | TBD | TBD |
| **docker-governance** | Docker container governance validation | senior-dev | TBD | TBD |
| **local-ci** | Full test suite execution with parallel processing | senior-dev | TBD | TBD |
| **changed-lines-coverage** | Coverage validation on changed lines (>80% threshold) | senior-dev | TBD | TBD |
| **pipeline-watchdog** | Monitors for stuck pipelines (>30 min timeout) | senior-dev | TBD | TBD |
| **pre-eval-ingestion** | Tempmemory ingestion before brain evaluation | senior-dev | TBD | TBD |
| **brain-eval** | Brain evaluation with tempmemory context | senior-dev | TBD | TBD |
| **tempmemory-scheduler** | Tempmemory migration dry-run | senior-dev | TBD | TBD |
| **mini-brain-eval** | Mini BrainEval with all sources (daily cadence) | senior-dev | TBD | TBD |
| **tempmemory-reconcile** | Tempmemory reconciliation and archive | senior-dev | TBD | TBD |
| **tempmemory-drill** | Tempmemory reconciliation drill (cron/main only) | senior-dev | TBD | TBD |
| **flaky-detection** | Flaky test detection via repeated runs (cron/main only) | senior-dev | TBD | TBD |
| **compass-apply** | Auto-label PRs based on changed files | senior-dev | TBD | TBD |
| **compass-gate** | Check for sensitive path changes requiring review | senior-dev | TBD | TBD |
| **status-write-gate** | Workflow status file validation | senior-dev | TBD | TBD |
| **status-evidence-gate** | Validate status evidence when workflow status changes | senior-dev | TBD | TBD |
| **completion-evidence-gate** | Validate completion evidence when workflow status changes | senior-dev | TBD | TBD |
| **workflow-transition-gate** | Validate workflow state transitions | senior-dev | TBD | TBD |
| **governance-drift-check** | Governance drift detection | senior-dev | TBD | TBD |
| **performance-gate** | Performance threshold validation (duration, memory) | senior-dev | TBD | TBD |
| **ci-gate** | Single authoritative failure point - aggregates all gate results | senior-dev | TBD | TBD |

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

## Notes

### TBD Items

Items marked as **TBD** in the matrix above will be filled as runbooks are created. This includes:

1. **Runbook Links**: Detailed step-by-step procedures for each gate
2. **Remediation Links**: Troubleshooting guides and common failure resolutions

### Contributing

When creating new runbooks:
1. Update the corresponding row in the matrix above
2. Follow the naming convention: `docs/runbooks/ci-<gate-name>.md`
3. Include: Purpose, Common Failures, Troubleshooting Steps, Escalation Path

### Related Documents

- `.woodpecker/ci.yaml` - Pipeline definition
- `docs/bmm-workflow-status.yaml` - Workflow status tracking
- `docs/validation/validation-registry.yaml` - Validation registry

---

## Changelog

| Date | Change | Author |
|------|--------|--------|
| 2026-03-09 | Initial matrix creation | senior-dev |
