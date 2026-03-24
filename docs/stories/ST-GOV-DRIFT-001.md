---
story_id: ST-GOV-DRIFT-001
story_title: Fix Governance Drift Check for EP-GOV-001
epic_id: EP-GOV-001
phase: implementation
status: planned
story_points: 2
priority: P1
created_date: "2026-03-24"
owner: TBD
depends_on: []
---

# Story: Fix Governance Drift Check for EP-GOV-001

## Problem Statement

The `governance-drift-check` CI gate fails because EP-GOV-001 shows 12 completed stories in `docs/bmm-workflow-status.yaml` but only 8 are documented in the evidence file `docs/evidence/GOVERNANCE_MERGE_EVIDENCE_2026-03-08.md`. The governance drift guard compares these two sources and finds a mismatch.

## Background

EP-GOV-001 (Agent Swarm Governance Enhancement) was completed on 2026-03-22 with 12 stories:

- ST-GOV-001 through ST-GOV-010 (10 stories)
- ST-GOV-MINI-001 (Week 1 Audit Snapshot)
- ST-GOV-MINI-002 (Week 2 Optimization Feedback Loop)

The evidence file `GOVERNANCE_MERGE_EVIDENCE_2026-03-08.md` documents only 8 stories (ST-GOV-002, ST-GOV-003, ST-GOV-005, ST-GOV-006, ST-GOV-007, ST-GOV-008, ST-GOV-009, ST-GOV-010). Missing are:

- ST-GOV-001 (Memory Deduplication Engine) - has merge_commit: 0ce77cf31d9fde4ae207fd755992ad67b5cb16e9, pr_number: 410
- ST-GOV-004 (Meta-KPI Dashboard) - merge commit and PR number need to be found

## Acceptance Criteria

1. Evidence file `docs/evidence/GOVERNANCE_MERGE_EVIDENCE_2026-03-08.md` documents all 12 completed stories for EP-GOV-001
2. `governance-drift-check` CI gate passes

## Technical Approach

1. Cross-reference workflow-status.yaml BL-GOV-COMPLETION entry with evidence file
2. Add ST-GOV-001 entry (already has merge_commit: 0ce77cf31d9fde4ae207fd755992ad67b5cb16e9, pr_number: 410 in workflow status)
3. Find and add ST-GOV-004 evidence (search git for merge commit)
4. Update the evidence file's "Cross-Branch Verification Summary" table

## Verification

- `python scripts/validation/governance_drift_guard.py --check`
- `governance-drift-check` CI gate passes
