# Taiga <-> Repo Sync Policy (Strict Conflict)

## Canonical Source of Truth
- Repo is canonical for requirements, status, and acceptance criteria.
- Taiga is canonical for planning metadata (assignee, sprint, estimates, tags, comments).

## Repo-Canonical Fields (Taiga edits create PR)
- Story ID
- Story title
- Acceptance criteria
- Story status (`docs/bmm-workflow-status.yaml`)
- Validation status (`docs/validation/validation-registry.yaml`)

## Taiga-Canonical Fields (Repo accepts direct sync)
- Assignee(s)
- Sprint/Milestone
- Estimates/Story Points
- Tags/Labels
- Comments/Discussion

## Conflict Rules
- If both sides changed a repo-canonical field since last sync: **hard conflict**, no auto-merge.
- Conflicts require manual resolution and a PR that updates repo files.
- If Taiga changes repo-canonical fields: **create PR**, do not auto-apply to main.

## Sync Flow
1) Pull repo state and compute canonical fields.
2) Pull Taiga state and compare last sync checksum.
3) Apply Taiga-canonical updates to repo sync metadata (if any).
4) If repo-canonical changes detected in Taiga, create PR with updates.
5) If conflicts detected, log and halt.

## PR Requirements
- PR must reference story ID(s).
- Include acceptance criteria changes explicitly.
- Must pass status sync and CI gates before merge.
