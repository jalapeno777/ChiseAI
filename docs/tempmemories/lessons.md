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
