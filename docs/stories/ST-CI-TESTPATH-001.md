---
story_id: ST-CI-TESTPATH-001
story_title: Fix Missing tests/test_risk/ CI Reference
epic_id: EP-CI-001
phase: implementation
status: planned
story_points: 1
priority: P1
created_date: "2026-03-24"
owner: TBD
depends_on: []
---

# Story: Fix Missing tests/test_risk/ CI Reference

## Problem Statement

The CI pipeline references `tests/test_risk/` but this directory does not exist. This causes `local-ci` gate failures. References found at:

- `.woodpecker/ci.yaml` line 439
- `scripts/ci/critical_paths.py` line 14

## Background

The `tests/test_risk/` directory was referenced in the CI configuration but was never created. The path appears in the pytest command for critical path testing. The chiseai-testing-patterns skill also references this path but the actual tests were never implemented.

## Acceptance Criteria

1. CI pipeline no longer references `tests/test_risk/` OR directory is created with proper test structure
2. `local-ci` gate passes

## Technical Approach

Option A (preferred): Remove the `tests/test_risk/` reference from:

- `.woodpecker/ci.yaml` line 439 (remove `tests/test_risk/` from pytest command)
- `scripts/ci/critical_paths.py` line 14 (remove from CRITICAL_PATHS list)

Option B: If tests are needed, create `tests/test_risk/` with proper structure (coordinate with testing team first).

Recommend Option A since the directory never existed and the CI was likely copy-pasted from another project.

## Verification

- CI pipeline runs without `tests/test_risk/` errors
- `local-ci` gate passes
