# Aria Data Models and Runtime Flows

## 1. Identity contract model

```yaml
version: 1
craig_profile:
  name: Craig
  communication_preferences:
    style_with_craig: natural_conversational
    style_with_subagents: concise_professional_ai_oriented
  shared_across_everything: true

aria_identity:
  role: primary_orchestrator
  purpose: stable_thinking_partner_and_swarm_orchestrator
  core_personality: single_identity_with_light_mode_shifts

soul_invariants:
  - never_silently_override_hardlined_soul_items
  - never_silently_override_prd_objectives
  - evidence_before_assertion
  - challenge_not_blind_compliance

prd_invariants:
  approval_required_for_change: true
  items:
    - add_project_specific_items_here

approval_gates:
  protected_fields:
    - soul_invariants
    - prd_invariants
    - aria_identity.role
    - aria_identity.purpose
  require_immediate_alert: true

notification_policy:
  digest_time_local: "20:00"
  timezone: "America/Toronto"
  immediate_on:
    - high
    - critical
    - approval_request

memory_priority_order:
  - core_personality
  - personal_preferences
  - project_rules_architecture
  - current_task_details
  - old_lessons
  - old_conversations

evidence_resolution_policy:
  conflict_rule: strongest_evidence_wins
  fallback: ask_craig_when_not_properly_informed
```

## 2. Belief record model

```yaml
belief_id: belief-uuid
belief_type: preference|workflow|strategy|tooling|project_operating_belief
scope: shared|project|task
status: active|deprecated|pending_approval|rolled_back
content: "Aria prefers concise delegation prompts to Jarvis for execution tasks."
confidence: 0.86
severity: medium
approval_required: false
protected_conflict: false
evidence:
  - source_type: reflection
    source_id: daily-reflection-2026-03-31
    strength: 0.8
    summary: repeated improvement in task clarity
contradictions:
  - belief_id: older-belief-id
    resolution: stronger_evidence_wins
provenance:
  initiated_by: aria
  created_at: 2026-03-31T20:00:00-04:00
  updated_at: 2026-03-31T20:00:00-04:00
notification:
  digest_eligible: true
  immediate_alert_sent: false
  digest_id: null
```

## 3. Reflection artifact model

```yaml
reflection_id: daily-2026-03-31
reflection_type: micro|daily|weekly
summary:
  what_happened: []
  what_worked: []
  what_failed: []
  patterns_observed: []
  top_learnings: []
proposals:
  belief_promotions: []
  lesson_promotions: []
  lesson_deprecations: []
  approval_requests: []
metrics:
  confidence_calibration_score: 0.0
  lesson_effectiveness_delta: 0.0
  persona_drift_score: 0.0
```

## 4. Digest event model

```yaml
event_id: event-uuid
event_type: belief_added|belief_updated|lesson_promoted|lesson_deprecated|contradiction_detected|memory_archived|approval_request
severity: low|medium|high|critical
summary: "Aria updated a workflow belief about delegation brevity."
details:
  what_changed: "Delegation prompts should default to concise structured format."
  why: "Repeated evidence across successful tasks."
  evidence: []
  blocked: false
  approval_required: false
created_at: 2026-03-31T18:15:00-04:00
routing:
  digest_eligible: true
  immediate_alert: false
```

## 5. State flow for belief mutation
1. Observation captured.
2. Candidate belief generated.
3. Evidence attached.
4. Protected-field conflict check runs.
5. Contradiction resolution runs.
6. Severity is computed.
7. Approval requirement is computed.
8. Mutation is either blocked pending approval or committed.
9. Audit record is written.
10. Notification event is queued or sent.

## 6. Context assembly flow
1. Load identity contract.
2. Load protected invariants.
3. Load highest-confidence active personal preferences.
4. Load relevant project rules and architecture.
5. Load active task memory.
6. Load relevant lessons and reflection summaries.
7. Load minimal history reserve if budget allows.
8. Run budget enforcement.
9. Emit final context packet.

## 7. Context budget logic
When over budget:
1. Remove low-value history first.
2. Compress low-salience lesson details.
3. Compress active task artifacts into summaries.
4. Never evict protected invariants.
5. Never evict identity contract.

## 8. Promotion and deprecation guidance
Promote when:
- repeated evidence exists
- effect on outcomes is meaningful
- confidence is stable over multiple cycles

Deprecate when:
- evidence weakens materially
- contradiction remains unresolved in its favor
- measured effectiveness stays low over enough samples

## 9. Required auditability
At minimum, the system should be able to answer:
- what changed
- when it changed
- why it changed
- what evidence supported it
- what it contradicted
- whether Craig approval was required
- whether Craig was notified
- how to roll it back
