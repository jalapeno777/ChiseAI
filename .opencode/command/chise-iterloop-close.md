---
name: "chise-iterloop-close"
description: "ChiseAI: close an iteration (evidence, learnings, Redis close, promote to Qdrant or docs/tempmemories fallback)"
disable-model-invocation: true
---

Follow these steps exactly (do not skip):

1. Evidence collection
   - Capture: files changed, commands run, test results, and any live validation checks.

2. Prepare Redis iterlog close payload (DB 0)
   - Update: `bmad:chiseai:iterlog:story:<story_id>`
     - `status=closing`
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

7. Metacognition close (REQUIRED for all stories)
   - Run `.opencode/command/chise-metacog-close.md` to create outcome and calibration cards.
   
   **Outcome card must include:**
   - `story_id`
   - `actual_outcome` (what actually happened)
   - `actual_metrics` (measured values)
   - `misses` (where prediction was wrong)
   - `wins` (where prediction was right)
   - `new_prevention_rules` (if any)
   
   **Calibration card must include:**
   - `predicted_confidence` (from step 6 of iterloop-start)
   - `observed_result` (`success|partial|failure`)
   - `calibration_delta` (absolute error)
   - `confidence_adjustment_recommendation`
   
   **Redis writes (DB 0):**
   - Outcome card to `bmad:chiseai:metacog:outcome:story:<story_id>`
   - Weekly agent calibration: `bmad:chiseai:metacog:calibration:agent:<agent>:weekly:<yyyy-Www>`
   - Prevention rules: `bmad:chiseai:metacog:prevention_rules`
   
   **Qdrant promotion:**
   - Promote durable lessons to `ChiseAI_metacognition` collection
   - Fallback to `docs/tempmemories/` with `needs_manual_qdrant_import: true`
   
   **Iterlog sections required:**
   - `## Metacognitive Predictions` (must still exist from iterloop-start; copy forward if missing)
   - `## Metacognitive Outcomes`
   - `## Metacognitive Calibration`

   **Validator-compatible section skeleton (required headings):**
   ```markdown
   ## Metacognitive Predictions
   - `predicted_outcome`:
   - `predicted_risks`:
   - `confidence`:
   - `verification_plan`:
   - `expected_metrics`:

   ## Metacognitive Outcomes
   - `actual_outcome`:
   - `actual_metrics`:
   - `wins`:
   - `misses`:
   - `new_prevention_rules`:

   ## Metacognitive Calibration
   - `predicted_confidence`:
   - `observed_result`:
   - `calibration_delta`:
   - `confidence_adjustment_recommendation`:
   ```

8. Skills effectiveness capture (NON-BLOCKING)
   - Run `.opencode/command/chise-skill-autonomy-tick.md` with:
     - `story_id`
     - `task_class`
     - `mode=close`
     - `quality_score` (if available)
     - `cycle_time_minutes` (if available)
     - `rework_flag` / `regression_flag` (if applicable)
     - `skill_name` / `skill_version` when attribution is known
   - Missing recommended skills are warning-only and must not block completion.
   - Record in iterlog under `## Skill Effectiveness Snapshot`.

9. Metacognition compliance validation (REQUIRED)
   - Run validation script:
     ```bash
     python3 scripts/validation/validate_metacog_compliance.py --story-id=<story_id> --strict
     ```
   - Gate FAILS if:
     - Prediction card missing
     - Outcome card missing
     - Calibration card missing
     - Metrics are not measurable
   - Fix all failures before proceeding to step 10.

10. Final completion mark
   - Only after steps 1-9 pass, update Redis iterlog:
     - `status=completed`
   - If any gate fails, keep status as `closing` (or `in_progress`) and remediate first.

11. Thinking-partner proof chain (REQUIRED)
   - Add these iterlog sections before completion:
     - `## Thinking Partner Status`
     - `## Insights Sent To Aria`
     - `## Aria Decisions`
   - Include at least one of:
     - `INSIGHT_PACKET` + `ARIA_DECISION`, or
     - `NO_ISSUES_PACKET` + `ARIA_DECISION`
   - Use validator-compatible fenced format under required sections, for example:
   ```text
   ## Insights Sent To Aria
   INSIGHT_PACKET
   - insight_packet_id: IP-...
   ...

   ## Aria Decisions
   ARIA_DECISION
   - aria_decision_id: AD-...
   ...
   ```
   - Include one summary line:
     - `Thinking Partner Proof: <tp_mode> | <story_id> | IP:<id|none> | AD:<id|none> | Risks:<count>`
   - If `decision=DEFER`, add decision debt fields:
     - `debt_id`, `owner`, `due_utc`, `impact_if_overdue`
