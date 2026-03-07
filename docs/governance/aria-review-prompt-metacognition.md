# Aria Review Prompt: Metacognition Integration

Use this exact prompt with Aria.

---

You are Aria, primary orchestrator for ChiseAI.

Review and critique the metacognition integration proposal and implemented workflow artifacts in this repo.

Primary context files:
- AGENTS.md
- .opencode/agent/Aria.md
- .opencode/agent/Jarvis.md
- docs/product-brief.md
- docs/prd.md
- docs/governance/metacognition-integration-blueprint.md

Implementation files to review:
- .opencode/skills/chiseai-metacognition-ops/SKILL.md
- .opencode/command/chise-metacog-start.md
- .opencode/command/chise-metacog-close.md
- .opencode/command/chise-metacog-weekly.md
- .opencode/command/chise-iterloop-start.md
- .opencode/command/chise-iterloop-close.md
- .opencode/command/chise-precommit-gates.md
- scripts/validation/validate_metacog_compliance.py
- docs/policy/reflection_policy.yaml

What I need from you:

1) Strategic fit assessment
- Is this aligned with PRD + Product Brief end goals (autonomy, safety invariants, measurable learning)?
- Where is it overbuilt or underpowered?

2) Process fit assessment (Aria/Jarvis operations)
- Does it fit your required phases and Jarvis delegation model?
- What should be changed in Aria/Jarvis protocol fields, if anything?

3) Risk assessment
- Identify top implementation/process risks (severity + impact).
- Include false-positive risk from strict gating and how to mitigate it.

4) Implementation plan
- Provide an execution plan in batches with:
  - scope_globs
  - locks_required
  - depends_on
  - owner_agent recommendation
  - validation evidence required

5) Governance recommendations
- Which parts should be hard-gate vs soft-gate initially?
- What decision thresholds should Craig own vs Aria vs Merlin?

6) Quantification framework
- Confirm or refine KPI set and thresholds.
- Propose weekly/monthly review cadence and decision triggers.

7) Final decision packet
Return:
- ARIA_DECISION style recommendation:
  - decision: ACCEPT | PARTIAL_ACCEPT | DEFER | REJECT | OVERRIDE
  - scope_impact
  - prd_scope_change
  - rationale
  - follow_up_actions
- 1-2 minimal-change alternatives if you reject or partially accept.

Constraints:
- Keep capital-safety invariants and PRD scope boundaries intact.
- Do not suggest bypassing test/live-validation gates.
- Prefer minimal viable process overhead while preserving measurable quality improvement.

---

