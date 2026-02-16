# Neuro-Symbolic AI Evolution Roadmap Index

This folder contains the living roadmap artifacts for ChiseAI's neuro-symbolic, self-evolving trading R&D system.

## Canonical V1 Artifacts

| Artifact | Description | Status |
|----------|-------------|--------|
| `agentic_neurosymbolic_trading_rd_v1_spec.md` | Core specification for the neuro-symbolic trading R&D system | Active |
| `architecture_diagram_outline.md` | High-level architecture diagram and component relationships | Active |
| `master-plan-summary.md` | Executive summary + phased roadmap for neuro-symbolic evolution | Active |

## Mapping Pointers (Traceability)

This section provides quick navigation to canonical status and traceability sources:

| What | Where | Purpose |
|------|-------|---------|
| **Story Status** | [`docs/bmm-workflow-status.yaml`](../../bmm-workflow-status.yaml) | Authoritative source for epic/story status, sprint assignments, and FR coverage |
| **Validation Status** | [`docs/validation/validation-registry.yaml`](../../validation/validation-registry.yaml) | Validation plans, test coverage, and acceptance criteria verification |
| **FR Definitions** | [`docs/prd.md`](../../prd.md) | Functional requirements definitions and traceability matrix (Section 3) |
| **Story-to-FR Mapping** | `fr_coverage` field in workflow status stories | Each story lists which FRs it covers |

## Artifact Inventory

### Planning & Architecture
- `agentic_neurosymbolic_trading_rd_v1_spec.md` - Core neuro-symbolic R&D specification
- `architecture_diagram_outline.md` - System architecture overview
- `master-plan-summary.md` - Executive roadmap summary

### Status & Traceability (Repo-Canonical)
- [`docs/bmm-workflow-status.yaml`](../../bmm-workflow-status.yaml) - BMAD workflow state (epics, stories, sprints)
- [`docs/validation/validation-registry.yaml`](../../validation/validation-registry.yaml) - Validation registry (test plans, AC verification)
- [`docs/prd.md`](../../prd.md) - Product requirements with FR/NFR/SC definitions

### CI Anti-Drift Enforcement
The following validation scripts ensure traceability integrity:

| Script | Purpose | CI Gate |
|--------|---------|---------|
| `scripts/validate_status_sync.py` | Validates workflow status YAML structure and cross-references | Blocking |
| `scripts/validate_fr_traceability.py` | Verifies all PRD FRs are covered by stories | Blocking |
| `scripts/validate_iterloop_compliance.py` | Checks iteration loop compliance per story | Blocking |
| `scripts/validate_pr_title.py` | Ensures PR titles contain story IDs | Blocking |
| `scripts/validate_traceability_drift.py` | **Comprehensive drift checker** - combines all traceability checks | Blocking |

### Related Documentation
- [`docs/architecture.md`](../../architecture.md) - System architecture details
- [`docs/product-brief.md`](../../product-brief.md) - Product brief and value proposition
- [`docs/epics.md`](../../epics.md) - Epic descriptions and breakdowns

---

**Last Updated:** 2026-02-15  
**Maintained by:** Chise Autonomous Development System  
**Validation:** Run `python scripts/validate_traceability_drift.py` to check all traceability
