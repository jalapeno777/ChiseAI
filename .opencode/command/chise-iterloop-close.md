---
name: "chise-iterloop-close"
description: "ChiseAI: close an iteration (evidence, learnings, Redis close, promote to Qdrant or docs/tempmemories fallback)"
disable-model-invocation: true
---

Follow these steps exactly (do not skip):

1. Evidence collection
   - Capture: files changed, commands run, test results, and any live validation checks.

2. Redis iterlog close (DB 0)
   - Update: `bmad:chiseai:iterlog:story:<story_id>`
     - `status=completed`
     - `completed_at`
     - `key_decisions` (compact JSON-like string)
     - `learnings` (compact JSON-like string)
   - Refresh TTL to 5 days for the story hash and any `:decisions`/`:learnings` lists.

3. Promote learnings
   - Promote durable decisions/patterns to Qdrant `ChiseAI` collection.
   - If Qdrant is unavailable, write to `docs/tempmemories/` with the same metadata you would store in Qdrant.

4. Cleanup gate
   - Ensure working tree is clean (or explicitly approved to remain dirty).
   - Ensure no untracked secret files (for example `.env`) are present.

5. Worker Completion Handoff Report (workers must provide before marking completed)
   Required fields:
   - `story_id`: Story identifier (e.g., ST-001)
   - `branch`: Feature branch name (e.g., feature/ST-001-description)
   - `head_sha`: Current commit SHA of branch tip
   - `test_summary`: Test results summary (e.g., "pytest: 15 passed, 0 failed")
   - `status_sync_proof`: Output of `python3 scripts/validate_status_sync.py --pr <number>`
   - `blockers`: Any blocking issues or "None"
   
   Before marking `status=completed`, you MUST:
   - Call `chise-release-ownership` to release scope locks
   - Verify all EVIDENCE_REQUIRED from worker contract is documented

6. Structured Issue Report (MANDATORY for all completions)
   Every iterlog MUST include a `## Structured Issues` section before marking completed.
   
   **Required schema for each issue entry:**
   - `issue_type` (string): Category of issue (e.g., "ci_failure", "merge_conflict", "scope_conflict")
   - `root_cause` (string): What caused the issue
   - `fix_applied` (string): How the issue was resolved
   - `time_lost_minutes` (integer): Approximate time spent resolving this issue
   - `recurrence_hint` (string): What to check/do to prevent this in the future
   - `impact_area` (enum: throughput|efficiency|accuracy|reliability): Which area was impacted
   - `resolved` (bool): Whether the issue is fully resolved
   
   **If no issues occurred during the iteration, use the empty sentinel:**
   ```yaml
   ## Structured Issues
   
   issues: []
   ```
   
   **Example with issues:**
   ```yaml
   ## Structured Issues
   
   issues:
     - issue_type: "ci_failure"
       root_cause: "missing dependency in requirements.txt"
       fix_applied: "added pytest-asyncio>=0.21.0 to requirements.txt"
       time_lost_minutes: 45
       recurrence_hint: "check all new test dependencies"
       impact_area: "efficiency"
       resolved: true
     - issue_type: "merge_conflict"
       root_cause: "parallel work on same file without ownership check"
       fix_applied: "rebased branch and resolved conflicts manually"
       time_lost_minutes: 30
       recurrence_hint: "always claim ownership before editing shared files"
       impact_area: "throughput"
       resolved: true
   ```
   
   **Validation:**
   - Run `python3 scripts/validate_iterloop_compliance.py --require-structured-issues`
   - This check is enforced by CI for all completions
   - Missing or incomplete structured issues will block the completion gate

7. Metacognition close (required)
   - Run `.opencode/command/chise-metacog-close.md`.
   - Iterlog must include:
     - `## Metacognitive Outcomes`
     - `## Metacognitive Calibration`
   - Validate:
     - `python3 scripts/validation/validate_metacog_compliance.py --story-id=<story_id> --strict`
