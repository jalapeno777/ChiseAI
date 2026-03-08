---
name: "chise-iterloop-start"
description: "ChiseAI: start an iteration (MEM-SCAN, acceptance criteria lock, Redis iterlog start, Qdrant context query, metacognition prediction)"
disable-model-invocation: true
---

Follow these steps exactly (do not skip):

1. MEM-SCAN
   - Locate and read the nearest `AGENTS.md` that governs the files you will touch.
   - Do not edit any files until MEM-SCAN is complete.

2. Identify the story
   - Choose `story_id` (example: `CH-AGENTS-002`) and a short `story_title`.
   - Set `phase` to one of: `analysis`, `planning`, `solutioning`, `implementation`, `testing`.
   - Note the story priority (P0/P1/P2) if known.

3. Redis iterlog (DB 0)
   - Create/update: `bmad:chiseai:iterlog:story:<story_id>` with required fields:
     - `story_id`, `story_title`, `phase`, `status=in_progress`, `started_at`, `priority`
   - Set TTL: `EXPIRE 432000` (5 days)

4. Qdrant context query
   - Run a semantic find for relevant context (project conventions, prior decisions, related story ids).
   - If Qdrant is unavailable, create a fallback note under `docs/tempmemories/` with frontmatter for later import.

5. Acceptance criteria lock
   - Write explicit, testable acceptance criteria BEFORE implementation begins.
   - Store them in the Redis iterlog hash under `acceptance_criteria`.

6. Metacognition kickoff (REQUIRED for all stories)
   - Run `.opencode/command/chise-metacog-start.md` to create prediction card.
   
   **Prediction card must include:**
   - `story_id`
   - `owner_agent` (`aria|jarvis|worker`)
   - `predicted_outcome` (specific, testable claim)
   - `predicted_risks` (1-3 identified risks)
   - `confidence` (0.0-1.0)
   - `verification_plan` (how you will verify success)
   - `expected_metrics` (at least one measurable metric)
   
   **Redis persistence:**
   - Write to `bmad:chiseai:metacog:prediction:story:<story_id>`
   - Set TTL to 5 days (`EXPIRE 432000`)
   
   **Gate:** Do NOT proceed to implementation unless prediction card exists and is measurable.
   
   **Record in iterlog:** Add `## Metacognitive Predictions` section with the full prediction card.

7. Skills coverage snapshot (NON-BLOCKING)
   - Run `.opencode/command/chise-skill-autonomy-tick.md` with:
     - `story_id`
     - `task_class` (use `unclassified` if unknown)
     - `mode=start`
   - Missing recommended skills are warning-only:
     - continue execution
     - log KPI gap event for weekly reflection
   - Record in iterlog under `## Skill Coverage Snapshot`:
     - `recommended_skills`
     - `available_skills`
     - `missing_skills`
     - `coverage_status`
     - `fallback_used`

8. Thinking-partner status kickoff (REQUIRED for all Craig-facing sessions)
   - Emit and persist this status block:
   ```text
   THINKING_PARTNER_STATUS
   - tp_mode: ACTIVE | DEGRADED | OFF
   - tp_session_id: TPS-<utc_yyyymmddThhmmssZ>-<short_hash>
   - scope: <story_id>
   - assumptions_open: <count>
   - risk_items_open: <count>
   - last_insight_packet_id: <id|none>
   - last_aria_decision_id: <id|none>
   ```
   - Record in iterlog under `## Thinking Partner Status`.
   - Persist in Redis hash `bmad:chiseai:tp:session:<tp_session_id>` with 5-day TTL.
   - Example persistence:
   ```bash
   redis-cli -h host.docker.internal -p 6380 HSET "bmad:chiseai:tp:session:<tp_session_id>" \
     story_id "<story_id>" tp_mode "ACTIVE" scope "<story_id>" created_at "$(date -u +%FT%TZ)"
   redis-cli -h host.docker.internal -p 6380 EXPIRE "bmad:chiseai:tp:session:<tp_session_id>" 432000
   ```
   - Gate: do not proceed if `tp_session_id` is missing.
