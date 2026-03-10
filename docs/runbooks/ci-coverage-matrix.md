# CI/CD Gate Coverage Matrix

> **Story**: ST-CI-001 - Real CI Gates (Phase 3 Enhanced)  
> **Last Updated**: 2026-03-09 (REPO-001 update)  
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
| **swarm-context** | Repository context validation - verifies swarm session and branch context | ops-team | [agent-autonomous-workflow](agent-autonomous-workflow.md) | [incident_response](incident_response.md) |
| **lint** | Code quality checks (black, ruff, mypy), status sync, iterlog governance, PR title validation, traceability drift | devops-team | TBD¹ | [incident_response](incident_response.md) |
| **security-scan** | Bandit security analysis for changed Python files | security-team | [incident_response](incident_response.md) | [incident_response](incident_response.md) |
| **dependency-audit** | pip-audit vulnerability scan for dependencies | security-team | [incident_response](incident_response.md) | [incident_response](incident_response.md) |
| **secret-scan** | Hardcoded secret detection in changed files | security-team | [incident_response](incident_response.md) | [incident_response](incident_response.md) |
| **risk-invariants** | Critical risk invariant tests (execution, kill switch, reconciliation) | risk-team | [kill-switch-trigger](kill-switch-trigger.md), [paper-trading-operations](paper-trading-operations.md) | [incident_response](incident_response.md) |
| **brain-regression** | Brain evaluation regression tests | ml-team | [brain-eval-cadence](brain-eval-cadence.md), [mini-brain-eval](mini-brain-eval.md) | [incident_response](incident_response.md) |
| **docs-pairing** | Documentation pairing validation | qa-team | TBD² | TBD |
| **docker-governance** | Docker container governance validation | ops-team | [env-bootstrap](env-bootstrap.md) | [incident_response](incident_response.md) |
| **local-ci** | Full test suite execution with parallel processing | devops-team | TBD³ | [incident_response](incident_response.md) |
| **changed-lines-coverage** | Coverage validation on changed lines (>80% threshold) | devops-team | TBD⁴ | [incident_response](incident_response.md) |
| **pipeline-watchdog** | Monitors for stuck pipelines (>30 min timeout) | ops-team | [monitoring-setup](monitoring-setup.md) | [incident_response](incident_response.md) |
| **pre-eval-ingestion** | Tempmemory ingestion before brain evaluation | ml-team | [brain-eval-ingestion](brain-eval-ingestion.md) | [incident_response](incident_response.md) |
| **brain-eval** | Brain evaluation with tempmemory context | ml-team | [brain-eval-cadence](brain-eval-cadence.md), [mini-brain-eval](mini-brain-eval.md) | [incident_response](incident_response.md) |
| **tempmemory-scheduler** | Tempmemory migration dry-run | ops-team | [tempmemory-ci-scheduling](tempmemory-ci-scheduling.md) | [tempmemory-migration](tempmemory-migration.md) |
| **mini-brain-eval** | Mini BrainEval with all sources (daily cadence) | ml-team | [mini-brain-eval](mini-brain-eval.md) | [incident_response](incident_response.md) |
| **tempmemory-reconcile** | Tempmemory reconciliation and archive | ops-team | [tempmemory-migration](tempmemory-migration.md) | [tempmemory-migration](tempmemory-migration.md) |
| **tempmemory-drill** | Tempmemory reconciliation drill (cron/main only) | ops-team | [tempmemory-migration](tempmemory-migration.md) | [tempmemory-migration](tempmemory-migration.md) |
| **flaky-detection** | Flaky test detection via repeated runs (cron/main only) | qa-team | [repeated-issues](repeated-issues.md) | [incident_response](incident_response.md) |
| **compass-apply** | Auto-label PRs based on changed files | ops-team | [compass-operations-runbook](compass-operations-runbook.md) | [incident_response](incident_response.md) |
| **compass-gate** | Check for sensitive path changes requiring review | ops-team | [compass-operations-runbook](compass-operations-runbook.md) | [incident_response](incident_response.md) |
| **status-write-gate** | Workflow status file validation | ops-team | [workflow-archiving-runbook](workflow-archiving-runbook.md) | [incident_response](incident_response.md) |
| **status-evidence-gate** | Validate status evidence when workflow status changes | ops-team | [workflow-archiving-runbook](workflow-archiving-runbook.md) | [incident_response](incident_response.md) |
| **completion-evidence-gate** | Validate completion evidence when workflow status changes | ops-team | [workflow-archiving-runbook](workflow-archiving-runbook.md) | [incident_response](incident_response.md) |
| **workflow-transition-gate** | Validate workflow state transitions | ops-team | [workflow-archiving-runbook](workflow-archiving-runbook.md) | [incident_response](incident_response.md) |
| **governance-drift-check** | Governance drift detection | ops-team | [autonomy-cadence-controller](autonomy-cadence-controller.md) | [incident_response](incident_response.md) |
| **performance-gate** | Performance threshold validation (duration, memory) | devops-team | [monitoring-setup](monitoring-setup.md) | [incident_response](incident_response.md) |
| **ci-gate** | Single authoritative failure point - aggregates all gate results | devops-team | TBD⁵ | [incident_response](incident_response.md) |

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

Items marked as **TBD** in the matrix above are intentionally deferred:

1. **TBD¹ - lint**: No specific runbook exists for general lint failures. Remediation is typically self-evident from tool output (black/ruff/mypy errors).
2. **TBD² - docs-pairing**: Documentation pairing validation is a cross-cutting concern covered by multiple runbooks; no single runbook exists yet.
3. **TBD³ - local-ci**: Full test suite execution failures are diagnosed via pytest output; no dedicated runbook exists yet.
4. **TBD⁴ - changed-lines-coverage**: Coverage failures are typically addressed by adding tests; remediation guidance is in testing patterns documentation.
5. **TBD⁵ - ci-gate**: This is a meta-gate that aggregates all other gates; failures are diagnosed via individual gate logs.

**Filled Items**: 23 of 28 gates now have concrete runbook mappings (82% coverage).

**Remediation Standard**: All gates default to [incident_response.md](incident_response.md) for operational issues requiring human intervention.

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
| 2026-03-09 | Updated matrix with concrete runbook links and owner mappings (REPO-001) | senior-dev |
