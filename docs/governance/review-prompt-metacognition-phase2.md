# External Review Prompt: Metacognition Integration + CI Enforcement (Phase 2)

Use this prompt with another AI reviewer.

---

You are conducting a strict technical and process review of ChiseAI metacognition integration, including the CI hardening phase.

Review these commits in order:
1. `3661913` - initial metacognition integration
2. `e460f8a` - validator/protocol/governance hardening
3. `HEAD` - CI enforcement and triage integration (latest commit)

## Repository context

Primary goals and constraints:
- `docs/product-brief.md`
- `docs/prd.md`
- `AGENTS.md`

## Files to review

Metacognition design and prompts:
- `docs/governance/metacognition-integration-blueprint.md`
- `docs/governance/aria-review-prompt-metacognition.md`

Workflow/agent integration:
- `.opencode/agent/Aria.md`
- `.opencode/agent/Jarvis.md`
- `.opencode/command/chise-iterloop-start.md`
- `.opencode/command/chise-iterloop-close.md`
- `.opencode/command/chise-precommit-gates.md`
- `.opencode/command/chise-validate-iterloop-compliance.md`
- `.opencode/command/chise-metacog-start.md`
- `.opencode/command/chise-metacog-close.md`
- `.opencode/command/chise-metacog-weekly.md`
- `.opencode/skills/chiseai-metacognition-ops/SKILL.md`

Validation + CI wiring:
- `scripts/validation/validate_metacog_compliance.py`
- `tests/test_ci/test_validate_metacog_compliance.py`
- `.woodpecker/ci.yaml`
- `scripts/ci/swarm_triage.sh`
- `scripts/ci/woodpecker_triage.py`
- `scripts/README.md`

Policy/memory docs:
- `docs/policy/reflection_policy.yaml`
- `.opencode/skills/chiseai-memory-ops/SKILL.md`
- `.opencode/skills/chiseai-validation/SKILL.md`
- `.opencode/skills/chiseai-workflow-commands/SKILL.md`
- `docs/skills/operator-quick-reference.md`

## What to evaluate

1) Strategic alignment
- Does this directly support autonomous-by-default operation, safety invariants, and measurable learning?
- Any scope drift vs PRD/Product Brief?

2) Correctness and robustness
- Is `validate_metacog_compliance.py` reliable (low false pass/fail risk)?
- Any parser edge cases, status-handling issues, or story-id matching risks?

3) CI enforcement quality
- Is `.woodpecker/ci.yaml` integration appropriately strict?
- Does changed-iterlog strict validation strike the right balance between enforcement and throughput?
- Are root-cause extraction and reproduction commands sufficient for triage?

4) Process coherence
- Any contradictions across iterloop start/close, precommit gates, and agent instructions?
- Are required fields and templates consistent end-to-end?

5) Memory/retention design
- Redis key semantics, TTL values, dedupe model, and Qdrant payload usefulness.
- Any operational risk in fallback and manual import paths?

6) Quantification framework
- Are KPI formulas and thresholds actionable?
- Are ownership and cadence clear enough for real decisions?

## Required output format

- **Summary**
- **Findings (Ordered by Severity)**
- **CI-Specific Findings**
- **What Is Strong**
- **What Is Risky**
- **Recommended Adjustments**
- **Final Verdict** (`APPROVE` | `APPROVE_WITH_CHANGES` | `REJECT`)

For each finding, include:
- severity (`critical|high|medium|low`)
- exact file reference(s)
- why it matters
- concrete fix recommendation

Keep feedback concrete and implementation-oriented.

---

