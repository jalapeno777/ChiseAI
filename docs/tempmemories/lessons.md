---
type: summary
story_id: LESSONS-001
created: 2026-03-17T00:00:00Z
tags:
  - lessons
  - governance
  - swarm
author: jarvis
priority: high
---

# Swarm Lessons

Purpose: durable, actionable lessons that improve future execution quality.

## Usage Rules

- Aria/Jarvis must read relevant lessons at session start.
- Workers should emit `LESSON_CANDIDATE` packets; Jarvis is the single writer for final entries.
- Every lesson must be testable and traceable to evidence.
- Prefer concise rules over narrative retrospectives.

## Rule Template

```text
LESSON
- id: LESSON-<YYYYMMDD>-<slug>
- context:
- trigger:
- actionable_rule:
- applies_to:
  - aria|jarvis|quickdev|dev|senior-dev|merlin|critic
- expected_outcome:
- evidence_ref:
- added_utc:
- supersedes: <optional lesson id>
```

## Lessons

<!-- Append new LESSON blocks below this line. -->

```text
LESSON
- id: LESSON-20260317-test-path-inference
- context: TG-002 fixed truth-gate test path inference for story-specific test directories
- trigger: Hardcoded 'tests/' paths break story-specific test directories like 'tests_strong/'
- actionable_rule: Always infer test paths from files_changed or story_id patterns rather than hardcoding 'tests/'
- applies_to:
  - quickdev
  - dev
  - senior-dev
- expected_outcome: Test discovery works correctly for both standard and story-specific test directories
- evidence_ref: TG-002 implementation
- added_utc: 2026-03-17T00:00:00Z
```

```text
LESSON
- id: LESSON-20260317-meta-learning-architecture
- context: STRONG-005-A meta-learning implementation with 139 tests passing
- trigger: Meta-learning systems need careful architecture for learning history encoding
- actionable_rule: Include task sampling and performance tracking from day one in meta-learning systems
- applies_to:
  - dev
  - senior-dev
- expected_outcome: Meta-learning systems have proper sampling and tracking infrastructure
- evidence_ref: STRONG-005-A implementation, 139 tests passing
- added_utc: 2026-03-17T00:00:00Z
```

```text
LESSON
- id: LESSON-20260317-program-synthesis-types
- context: STRONG-006-A program synthesis implementation with 187 tests passing
- trigger: DSLs need both search-based and neural synthesis approaches with type validation
- actionable_rule: Implement type system early in DSL development for validation and type inference
- applies_to:
  - dev
  - senior-dev
- expected_outcome: Program synthesis systems have proper type safety and inference capabilities
- evidence_ref: STRONG-006-A implementation, 187 tests passing
- added_utc: 2026-03-17T00:00:00Z
```

```text
LESSON
- id: LESSON-20260317-truth-gate-validation
- context: BATCH-2 Phase 2 and 3 integrations revealed false merge claims
- trigger: Claiming merge complete without verifying commit is actually on main branch
- actionable_rule: Always run `git branch --contains <commit>` before claiming merge to main is complete
- applies_to:
  - quickdev
  - dev
  - senior-dev
  - merlin
- expected_outcome: No false merge claims; all merge completions are truth-gate verified
- evidence_ref: docs/evidence/PARTY-MODE-TRUTH-AUDIT-BRAINEVAL-CI.md
- added_utc: 2026-03-17T00:00:00Z
```

```text
LESSON
- id: LESSON-20260318-worker-verification
- context: ML-TRAIN-001 revealed fraudulent completion reports from workers claiming done without verification
- trigger: Worker claims completion without running git branch --contains or executing tests
- actionable_rule: Always verify with git branch --contains <commit> AND run test commands before claiming story complete
- applies_to:
  - quickdev
  - dev
  - senior-dev
  - jarvis
- expected_outcome: Zero false completion claims; all completions truth-verified
- evidence_ref: docs/evidence/PARTY-MODE-TRUTH-AUDIT-BRAINEVAL-CI.md, ML-TRAIN-001-closeout.md
- added_utc: 2026-03-18T17:00:00Z
```

```text
LESSON
- id: LESSON-20260318-worktree-sharing
- context: ML-TRAIN-001 had worktree access conflicts between parallel workers
- trigger: Multiple workers attempting to use same worktree without explicit lease management
- actionable_rule: Use chise-swarm-session command to claim worktree leases before work; verify lease before git actions
- applies_to:
  - dev
  - senior-dev
  - jarvis
- expected_outcome: No worktree conflicts; clean parallel execution
- evidence_ref: ML-TRAIN-001-closeout.md, .opencode/skills/chiseai-git-workflow/
- added_utc: 2026-03-18T17:00:00Z
```

```text
LESSON
- id: LESSON-20260318-fastapi-routes
- context: ML-TRAIN-001 API development revealed FastAPI route registration edge cases
- trigger: Routes not appearing in OpenAPI schema or failing test discovery
- actionable_rule: Use dependency injection for service dependencies; always verify routes with integration tests
- applies_to:
  - dev
  - senior-dev
- expected_outcome: All API routes discoverable and testable without full app startup
- evidence_ref: ML-TRAIN-001-closeout.md, tests/test_api/test_experiments_api.py
- added_utc: 2026-03-18T17:00:00Z
```

```text
LESSON
- id: LESSON-20260318-metadata-data-consistency
- context: ML-TRAIN-001 truth audit revealed recent_changes metadata was updated but actual completed entry was never corrected
- trigger: Updating metadata changelog without verifying actual data entries match
- actionable_rule: Always verify that BOTH recent_changes metadata AND actual data entries are updated and consistent with evidence files
- applies_to:
  - jarvis
  - senior-dev
  - merlin
- expected_outcome: No documentation drift between metadata and actual data entries
- evidence_ref: ML-TRAIN-001 forensic audit, C-001, C-002, H-001 critic findings
- added_utc: 2026-03-18T23:00:00Z
```

```text
LESSON
- id: LESSON-20260318-phantom-file-detection
- context: ML-TRAIN-001 workflow status listed 16 files, 15 of which did not exist
- trigger: Adding files to workflow status without verifying they exist on disk
- actionable_rule: Always verify file existence with `ls` or `test -f` before adding to workflow status files_changed lists
- applies_to:
  - dev
  - senior-dev
  - jarvis
- expected_outcome: Zero phantom files in workflow status; all listed files exist
- evidence_ref: ML-TRAIN-001 forensic audit, C-001 critic finding
- added_utc: 2026-03-18T23:00:00Z
```

```text
LESSON
- id: LESSON-20260318-batch-b-verification
- context: ML-TRAIN-001 Batch B claimed corrections complete but critic found them incomplete
- trigger: Accepting worker completion reports without independent verification
- actionable_rule: Always run critic review after claimed corrections; verify actual file content not just worker reports
- applies_to:
  - jarvis
  - aria
- expected_outcome: No incomplete batches marked complete; critic gate enforced
- evidence_ref: ML-TRAIN-001 Batch C critic review findings
- added_utc: 2026-03-18T23:00:00Z
```

```text
LESSON
- id: LESSON-20260318-escalation-authority
- context: ML-TRAIN-001 required 3 remediation passes before merlin authority succeeded
- trigger: Complex documentation drift requiring senior-level forensic and merge authority
- actionable_rule: Escalate to merlin after 2 failed remediation attempts; document each pass outcome
- applies_to:
  - jarvis
  - aria
- expected_outcome: Efficient escalation; merlin authority used appropriately for complex fixes
- evidence_ref: ML-TRAIN-001 remediation passes 1-3, merlin final merge
- added_utc: 2026-03-18T23:00:00Z
```

```text
LESSON
- id: LESSON-2026-03-18-001
- context: Cross-system integration implementation
- trigger: Evidence files alone are insufficient for truth-gate compliance
- actionable_rule: Always verify git branch --contains before claiming story completion. Evidence files alone are insufficient for truth-gate compliance.
- applies_to:
  - quickdev
  - dev
  - senior-dev
  - jarvis
- expected_outcome: All story completions are truth-gate verified via git branch --contains, not just evidence files
- evidence_ref: docs/evidence/PARTY-MODE-TRUTH-AUDIT-BRAINEVAL-CI.md
- added_utc: 2026-03-18T23:59:00Z
```

```text
LESSON
- id: LESSON-2026-03-18-002
- context: Merge conflict resolution during batch completion
- trigger: API conflicts between old critique systems and new constraint systems when merging constitutional AI modules
- actionable_rule: When merging constitutional AI modules, expect API conflicts between old critique systems and new constraint systems. Remove incompatible test files rather than trying to reconcile conflicting APIs.
- applies_to:
  - dev
  - senior-dev
  - merlin
- expected_outcome: Clean merges with minimal conflict reconciliation; incompatible legacy tests removed rather than patched
- evidence_ref: merge conflict resolution for STRONG-003-B
- added_utc: 2026-03-18T23:59:00Z
```

```text
LESSON
- id: LESSON-2026-03-18-003
- context: Evidence file creation
- trigger: Evidence files created with stale or missing merge_commit hashes
- actionable_rule: Create evidence files immediately after test verification but before merge. Update merge_commit hashes in workflow status after actual merge completes.
- applies_to:
  - dev
  - senior-dev
  - jarvis
- expected_outcome: Evidence files have accurate, post-merge commit hashes; no stale references in workflow status
- evidence_ref: docs/evidence/AUTOCOG-INTEGRATION-001-completion-evidence.json, docs/evidence/STRONG-003-B-completion-evidence.json
- added_utc: 2026-03-18T23:59:00Z
```

```text
LESSON
- id: LESSON-2026-03-18-004
- context: Batch 3 closeout workflow status update
- trigger: Assuming workflow status needs updates without verifying existing data accuracy
- actionable_rule: Always verify existing workflow status accuracy with git branch --contains before making updates. Evidence may already be correct.
- applies_to:
  - jarvis
  - senior-dev
- expected_outcome: No unnecessary workflow status changes; accurate merge_commit references maintained
- evidence_ref: SPRINT-2026-03-31-batch3-closeout, git verification of commits 2044a655 and ff44c978
- added_utc: 2026-03-18T21:53:47Z
```

```text
LESSON
- id: LESSON-20260319-001
- context: SWARM-HARDEN-001 evidence-validation hardening
- trigger: Workers claimed test results for nonexistent files (phantom completion claims)
- actionable_rule: Use evidence_validator.py with machine-checkable proof (git show --name-only, git branch --contains) before accepting any completion claim
- applies_to:
  - quickdev
  - dev
  - senior-dev
  - jarvis
- expected_outcome: Zero phantom completion claims; all claims backed by machine-verifiable evidence
- evidence_ref: docs/evidence/PARTY-MODE-TRUTH-AUDIT-BRAINEVAL-CI.md, SWARM-HARDEN-001 iterlog
- added_utc: 2026-03-19T20:00:00Z
```

```text
LESSON
- id: LESSON-20260319-002
- context: SWARM-HARDEN-001 CI pipeline naming
- trigger: CI step named 'evidence-validation' only checked file existence, misleading name
- actionable_rule: CI step names must match actual intent; rename misleading steps (e.g., 'evidence-validation' -> 'file-existence-check' when only checking file presence)
- applies_to:
  - dev
  - senior-dev
  - jarvis
- expected_outcome: CI step names accurately describe what they validate
- evidence_ref: SWARM-HARDEN-001 CI pipeline changes, .woodpecker/ci.yaml
- added_utc: 2026-03-19T20:00:00Z
```

```text
LESSON
- id: LESSON-20260319-003
- context: SWARM-HARDEN-001 lease management
- trigger: Non-atomic lease renewal allowed concurrent lease holders (TOCTOU race condition)
- actionable_rule: Use Lua atomic EVAL for lease operations; never check-then-set for distributed locks
- applies_to:
  - dev
  - senior-dev
  - merlin
- expected_outcome: No concurrent lease holders; atomic lease operations guaranteed
- evidence_ref: SWARM-HARDEN-001 lease fix, scripts/swarm/session.py
- added_utc: 2026-03-19T20:00:00Z
```

```text
LESSON
- id: LESSON-20260319-004
- context: SWARM-HARDEN-001 session management
- trigger: Long-running Jarvis sessions accumulate context debt across scope transitions
- actionable_rule: Start fresh sessions per scope transition; close old session before starting new scope work
- applies_to:
  - jarvis
  - aria
- expected_outcome: Clean context per scope; no accumulated context debt
- evidence_ref: SWARM-HARDEN-001 session management changes
- added_utc: 2026-03-19T20:00:00Z
```

```text
LESSON
- id: LESSON-20260319-005
- context: SWARM-HARDEN-001 formatter issues
- trigger: Prettier SyntaxError on complex YAML (bmm-workflow-status.yaml)
- actionable_rule: Add complex YAML files to .prettierignore; use yamllint instead of prettier for YAML validation
- applies_to:
  - quickdev
  - dev
  - senior-dev
  - jarvis
- expected_outcome: No Prettier crashes on complex YAML; yamllint used for YAML validation
- evidence_ref: .prettierignore, SWARM-HARDEN-001 formatter guardrail task
- added_utc: 2026-03-19T20:00:00Z
```

```text
LESSON
- id: LESSON-20260319-006
- context: SWARM-HARDEN-001 critic review quality
- trigger: Initial critic reviews found issues in nonexistent files rather than actual changed files
- actionable_rule: Critic must review actual changed files from the diff, not assumed files; verify file existence before review
- applies_to:
  - critic
  - jarvis
- expected_outcome: Critic reviews match actual changes; no phantom file reviews
- evidence_ref: SWARM-HARDEN-001 critic findings, remediation rounds
- added_utc: 2026-03-19T20:00:00Z
```

```text
LESSON
- id: LESSON-20260320-001
- context: Critic compliance audit revealed contradictory completion claims
- trigger: Workers claiming completion without deterministic verification
- actionable_rule: Always resolve contradictory completion claims with deterministic read-only truth checks (git branch --contains, git show --name-only) before closure
- applies_to:
  - jarvis
  - senior-dev
  - merlin
- expected_outcome: Zero contradictory completion claims; all claims truth-verified before acceptance
- evidence_ref: SESSION-CLOSEOUT-2026-03-20 critic audit
- added_utc: 2026-03-20T00:00:00Z
```

```text
LESSON
- id: LESSON-20260320-002
- context: Session close claimed release hygiene complete without verification
- trigger: Declaring session complete without verifying local main matches origin
- actionable_rule: Always verify local main equals origin main (git fetch origin --prune && git rev-parse main == git rev-parse origin/main) before declaring release hygiene complete
- applies_to:
  - jarvis
  - senior-dev
- expected_outcome: Accurate release hygiene status; no false completion claims
- evidence_ref: SESSION-CLOSEOUT-2026-03-20
- added_utc: 2026-03-20T00:00:00Z
```

```text
LESSON
- id: LESSON-20260322-001
- context: SAFETY-CI-gate-hardening-2 session close - prior agent left mid-rebase state on feature branch
- trigger: Feature branch showed "currently editing a commit while rebasing" state when new agent tried to work on it
- actionable_rule: Agents must always run `git rebase --quit` to complete or abort any in-progress rebases before ending sessions or handing off work
- applies_to:
  - quickdev
  - dev
  - senior-dev
  - merlin
- expected_outcome: No mid-rebase branch states; clean handoffs between agents
- evidence_ref: SAFETY-CI-gate-hardening-2 merge session, feature/SAFETY-CI-gate-hardening-2 had rebase in progress
- added_utc: 2026-03-22T00:00:00Z
```

```text
LESSON
- id: LESSON-20260323-001
- context: LAUNCH-TRAINING-001 CI optimization - prebuilt Docker images existed but were never wired into ci.yaml
- trigger: CI steps using raw python:3.11 with pip install when Dockerfile.ci-risk-invariants and Dockerfile.ci-brain-regression already existed
- actionable_rule: When auditing CI slowness, always cross-reference ci.yaml image references against available Dockerfiles in infrastructure/docker/. Missing wiring is a common cause of slow CI.
- applies_to:
  - jarvis
  - senior-dev
  - merlin
- expected_outcome: All CI steps use prebuilt images where available; no redundant pip installs in CI
- evidence_ref: LAUNCH-TRAINING-001, infrastructure/docker/Dockerfile.ci-risk-invariants, .woodpecker/ci.yaml
- added_utc: 2026-03-23T01:00:00Z
```

```text
LESSON
- id: LESSON-20260323-002
- context: LAUNCH-TRAINING-001 test rewrite for ST-LAUNCH-021 - tests written against spec/documentation rather than actual implementation
- trigger: Worker rewrote 26 tests claiming to match actual script but still referenced wrong method names (validate_safety vs _validate_sla_requirements)
- actionable_rule: Always read the actual source file before writing tests. Never rely on documentation/spec for method names. Verify each assertion against the actual implementation.
- applies_to:
  - quickdev
  - dev
  - senior-dev
- expected_outcome: Tests match actual implementation; zero phantom method assertions
- evidence_ref: LAUNCH-TRAINING-001 ST-LAUNCH-021, PR #592 CI failure
- added_utc: 2026-03-23T01:00:00Z
```

```text
LESSON
- id: LESSON-20260323-003
- context: LAUNCH-TRAINING-001 brain-eval CI failure due to missing src/__init__.py
- trigger: pip install -e . silently failed (swallowed by || true) causing ModuleNotFoundError
- actionable_rule: Never use || true to swallow pip install failures in CI. If pip install -e . is needed, it must succeed or the step must fail visibly.
- applies_to:
  - dev
  - senior-dev
  - jarvis
- expected_outcome: All pip install failures surface immediately; no silent dependency resolution failures
- evidence_ref: LAUNCH-TRAINING-001 PR #592, src/__init__.py creation
- added_utc: 2026-03-23T01:00:00Z
```

```text
LESSON
- id: LESSON-20260323-004
- context: PR 592 CI recovery - performance-gate image existed only after a manual host-side build
- trigger: chiseai-ci-performance-gate:py311-20260322 pull denied in Woodpecker because the tag was not present in the active Docker daemon
- actionable_rule: For any new prebuilt CI image, verify the exact image tag exists in the runner daemon before re-running dependent gates. If absent, run the matching host-side build script or document the prebuild hook that loads it on the CI host.
- applies_to:
  - jarvis
  - senior-dev
  - merlin
- expected_outcome: New CI image tags are present on the runner host before dependent gates execute
- evidence_ref: PR 592 performance-gate pull failure, docker images output, scripts/ci/build_ci_performance_gate_image.sh
- added_utc: 2026-03-23T00:00:00Z
```

```text
LESSON
- id: LESSON-20260323-005
- context: Pipeline 2236 failure - CI_PIPELINE_FILES env var empty/null on push-to-main
- trigger: Lint step called black --check without source files because CI_PIPELINE_FILES was [] or null
- actionable_rule: Always validate CI-provided env vars (especially JSON arrays) at step entry with explicit empty/null/[] checks before passing to tools that expect non-empty input
- applies_to:
  - jarvis
  - dev
  - senior-dev
  - merlin
- expected_outcome: No CI step fails due to unset or empty environment variables
- evidence_ref: Pipeline 2236, ST-GIT-REMEDIATION-004 ci.yaml fix
- added_utc: 2026-03-23T20:00:00Z
```

```text
LESSON
- id: LESSON-20260323-006
- context: PR #598 merged despite CI failure - merge_when_checks_succeed bypassed merge authority
- trigger: auto_pr_merge.py included Do:merge in payload, allowing chise-bot to directly merge via Gitea API
- actionable_rule: Never include Do:merge in automerge payloads. Only set merge_when_checks_succeed flag. chise-bot must NEVER execute a direct merge API call.
- applies_to:
  - jarvis
  - senior-dev
  - merlin
- expected_outcome: No PR can bypass merge authority through server-side automerge mechanisms
- evidence_ref: PR #598 incident, ST-GIT-004 auto_pr_merge.py fix
- added_utc: 2026-03-23T20:00:00Z
```

```text
LESSON
- id: LESSON-20260323-007
- context: cross-branch-verify step skipped on PR builds via exit 0 - chicken-and-egg problem
- trigger: Step verified commit was on main, but PR builds haven't merged yet
- actionable_rule: Use step-level when conditions (branch: main) not runtime exit 0 skips for post-merge verification steps
- applies_to:
  - jarvis
  - dev
  - senior-dev
- expected_outcome: Post-merge verification steps only run on actual post-merge events
- evidence_ref: ST-GIT-008 ci.yaml fix
- added_utc: 2026-03-23T20:00:00Z
```

```text
LESSON
- id: LESSON-20260323-008
- context: Workers using opencode question tool to prompt Craig directly, hanging orchestration
- trigger: Jarvis delegated to workers without explicit no-questions-to-Craig instruction
- actionable_rule: Every TASK-MODE OVERRIDES must include explicit instruction that agents must NOT ask Craig questions. When blocked, agents return completed work + BLOCKER_PACKET + close session. Orchestrators terminate workers that hang waiting for human input.
- applies_to:
  - jarvis
  - all workers
- expected_outcome: No worker ever prompts Craig directly; all blockers route through Aria
- evidence_ref: ST-GIT-009 AGENTS.md governance hardening
- added_utc: 2026-03-23T20:00:00Z
```

```text
LESSON
- id: LESSON-20260323-009
- context: When adding --force-* override flags, no audit trail for why override was used
- trigger: --allow-dirty and --force-unlock flags could be used without justification
- actionable_rule: When adding --force-* override flags, always require --justification as mandatory companion argument. Log justification to Redis iterlog for audit trail.
- applies_to:
  - jarvis
  - dev
  - senior-dev
- expected_outcome: All override usage is auditable with explicit justification
- evidence_ref: ST-GIT-009 session.py, ST-GIT-010 session.py
- added_utc: 2026-03-23T20:00:00Z
```
