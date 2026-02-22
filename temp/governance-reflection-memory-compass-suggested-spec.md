### Suggested Spec: Governance Gates + Reflection/Memory/Compass (ChiseAI / Chise)

> **Important:** This document is a **suggested spec** intended to help Craig’s AI swarm produce the **canonical spec**.  
> Treat it as a strong starting point, not ground truth.

**Owner:** Craig  
**Status:** Suggested → swarm refines into canonical spec → implement via PRs (autonomous-by-default)  
**Target stack:** OpenCode 1.2.6+, BMAD v6 beta, Gitea + Woodpecker, WSL2-in-Docker (Windows 11)  
**Orchestrator:** Aria (`openai/gpt-5.3-codex`)  
**Key policy:** Auto-merge when CI is green **except** where explicitly gated by labels / compass veto

---

## 1) Purpose

Upgrade the autonomous development system (“Chise”) to:

1) Preserve **autonomous-by-default** development while introducing **selective human-approval** for sensitive changes.  
2) Add a **Soul-guided Compass** that can veto risky/value-misaligned work (`COMPASS-VETO`) with an **appeal workflow** triggered only by **3-agent consensus** (Critic + SeniorDev + Merlin), but still requiring human approval to override.  
3) Add **continuous reflection loops** tied to dev KPIs and trading invariants.  
4) Add **automatic memory stewardship** (Redis + Qdrant, project-scoped) including deterministic promotion/retention rules.  
5) Improve agent reliability using modern best-practice patterns for **planning, self-correction, and retention** (see Section 5).

---

## 2) High-Level Goals

### G1 — Autonomy preserved
- Normal changes flow **autonomously**: PR → CI green → auto-merge.

### G2 — Human approval only when it matters
- Sensitive scopes require `HUMAN-APPROVED` label before merge.

### G3 — Compass veto + appeal
- Compass can veto (label + CI block), with an appeal packet created only on **3-agent consensus**, then handed to Craig.

### G4 — Continuous evolution
- Reflection + memory stewardship run continuously and feed improvements into future stories.

### G5 — Evidence-based decisions
- Changes to risky surfaces must be backed by tests, diffs, metrics, and (where applicable) simulation results.

---

## 3) Scope

### In scope
- New CI steps: `approval-gate` and `compass-gate`.
- New policy files:
  - `docs/policy/human_approval.yaml`
  - `docs/policy/compass.yaml`
  - `docs/policy/memory_policy.yaml` (new)
  - `docs/policy/reflection_policy.yaml` (new)
- New/updated scripts:
  - `scripts/ci/human_approval_gate.py`
  - `scripts/ci/compass_gate.py`
  - `scripts/ops/compass_apply.py` (auto-labeling)
  - `scripts/ops/memory_sweep.py` (new)
  - `scripts/ops/reflection_runner.py` (new)
  - Updates to merge automation scripts to respect gates
- New commands/skills for:
  - Reflection loops
  - Memory stewardship
  - Compass appeals workflow
  - “High-impact deliberation” workflow (multi-path planning + evaluation)

### Not in scope (for this implementation)
- Live trading enablement changes (still paper trading; live **data** allowed).
- Major repo restructuring unless required to implement gates cleanly.
- Switching core governance authority away from Aria.

---

## 4) Constraints & Non-Negotiables

1) **Aria model pinned:** `openai/gpt-5.3-codex`  
   - Any model changes (any agent) are considered sensitive and require `HUMAN-APPROVED`.

2) **Autonomous-by-default** remains the operating model:
   - Human intervention is required only for:
     - Major scope changes
     - Any LLM model changes for agents
     - Governance changes for Aria
     - Compass veto overrides (label-based)

3) **Paper trading only**, but analysis/confidence scoring uses **live market data**.

4) **Project-scoped memory only** (Redis + Qdrant). No storing secrets (API keys, tokens, credentials).

5) **Consensus rule (“system insists”):** unanimous agreement across **Critic + SeniorDev + Merlin** counts as “insistence” and can trigger an appeal packet.

---

## 5) Best-Practice / Cutting-Edge Mechanics to Integrate

This section is written to give the swarm modern patterns to bake into the canonical spec and implementations.

### 5.1 Memory architecture (hierarchical + policy-driven)
Adopt a tiered memory system inspired by hierarchical memory / “virtual context” approaches:
- **Working Memory (WM):** what fits in the active context window (short-lived)
- **Episodic Memory (EM):** event streams + reflections, time-ordered (Redis primary; rolling window)
- **Semantic Memory (SM):** stable concepts, decisions, invariants, runbooks (Qdrant primary; canonical)
- **Policy Memory:** explicit “constitution/values”, governance rules, veto definitions (versioned in repo)

Core patterns:
- **Paging/compaction:** keep WM small; “page out” older context to EM/SM with summaries rather than raw logs.
- **Retention by value:** store *why something matters* (impact, recurrence, risk), not just the text.

### 5.2 Retrieval (relevance × recency × importance × risk)
Use a deterministic retrieval scoring model like:

`score = wR*relevance + wT*recency + wI*importance + wK*risk + wC*cost_to_rediscover - wN*noise`

Recommended signals:
- **Relevance:** embedding similarity (Qdrant) + keyword matches
- **Recency:** exponential decay for episodic items
- **Importance:** explicit importance scoring at write time (e.g., “would this prevent future failures?”)
- **Risk:** any memory tied to execution safety, kill-switch, canary, risk models
- **Cost to rediscover:** how hard it is to reconstruct (design decisions > transient chat)

### 5.3 Promotion rules (automatic, auditable, reversible)
Implement promotion from Redis → Qdrant using deterministic triggers:
- Repeated ≥2 times (duplicate clustering)
- Caused CI failure/regression or prevented one
- Updates an invariant/policy
- Touches execution safety: kill-switch/canary/risk limits

Add *reversibility*:
- Any canonical memory must have:
  - source links (PRs/commits/issues)
  - a version/epoch
  - a “supersedes/superseded_by” chain
- Allow “memory corrections” via PRs (governance applies).

### 5.4 Reflection loops (trial-and-error learning without weight updates)
Use layered reflection loops:
- **Micro:** after each tool/action (did it work? what changed?)
- **Meso:** per PR / per story closure (what failed, what to fix next time)
- **Macro:** daily/weekly retro (trend analysis + prioritized improvements)

Recommended mechanism:
- “Verbal reinforcement” style reflection where the agent summarizes feedback signals into reusable guidance stored in episodic memory and used in future attempts.
- Add “self-critique → refine” loops on key outputs (plans, PR descriptions, risky code changes).

### 5.5 Deliberation for high-impact decisions
For changes in risky surfaces (execution, risk, governance):
- Use reason+act tooling patterns (tool grounded reasoning) to reduce hallucinations and improve reliability.
- For architecture/trade-off decisions, run multi-path planning (generate multiple plans, evaluate, pick best) to avoid single-track reasoning failures.

### 5.6 Soul-guided Compass as a “constitutional layer”
Treat the Compass as an explicit “constitution”:
- principles/values → classification rules → veto/allow/require-human
- enforced by CI + labels
- all veto decisions produce an audit artifact (what principle triggered, what evidence)

### 5.7 Memory hygiene + drift control
Add safeguards against memory bloat and drift:
- **Deduplication:** cluster near-duplicates; keep one canonical
- **Contradiction detection:** flag conflicting memories for review (auto-create a “memory conflict” issue)
- **Staleness decay:** episodic TTL; semantic remains but can be superseded
- **Traceability:** canonical memories must link to code/PR evidence

---

## 6) Governance gates (mechanics)

Two independent mechanisms:

### A) Human approval gate (`HUMAN-APPROVED`)
- Blocks merges only when PR touches sensitive paths.
- Implemented as CI status check `approval-gate`.

### B) Compass veto (`COMPASS-VETO`)
- Tooling auto-applies label when PR touches veto scope.
- CI status check `compass-gate` blocks merges while `COMPASS-VETO` is present unless `HUMAN-APPROVED` is also present.

### C) Appeal workflow (3-agent consensus)
- If Compass vetoes but the system believes the change is necessary:
  - Run a vote by **Critic + SeniorDev + Merlin**
  - Only if **all 3** recommend proceed:
    - Create an **Appeal Packet** (comment + artifact)
    - Optionally add label `COMPASS-APPEAL`
  - Merge remains blocked until Craig applies `HUMAN-APPROVED`

---

## 7) Implementation Requirements

### 7.1 Repo / config changes
1) Treat OpenCode config as JSONC:
   - Rename `opencode.json` → `opencode.jsonc` (or remove trailing commas).

2) Ensure Aria model is correct in both:
   - `Aria.md` and `opencode.jsonc` (Aria entry)

### 7.2 New labels in Gitea
- `HUMAN-APPROVED`
- `COMPASS-VETO`
- (Optional) `COMPASS-APPEAL`

### 7.3 Policy files
#### `docs/policy/human_approval.yaml`
Defines:
- required label: `HUMAN-APPROVED`
- sensitive paths glob list (initially broad until “live execution location” is finalized)

#### `docs/policy/compass.yaml`
Defines:
- veto label: `COMPASS-VETO`
- override label: `HUMAN-APPROVED`
- veto paths glob list

#### `docs/policy/memory_policy.yaml` (new)
Defines:
- tiers (WM/EM/SM), stores (Redis/Qdrant), TTLs, promotion criteria
- dedupe + contradiction rules
- traceability requirements for canonical memories

#### `docs/policy/reflection_policy.yaml` (new)
Defines:
- micro/meso/macro loop triggers
- required output schema (JSON) for artifacts
- how reflections feed into next tasks (automatic story creation or backlog entries)

### 7.4 Woodpecker CI updates
Add steps (must run on PR pipelines):
- `approval-gate` (before final CI gate)
- `compass-gate` (before final CI gate)

Ensure branch protection requires:
- existing CI checks
- `approval-gate`
- `compass-gate`

### 7.5 Gitea API integration (for auto-labeling + file diff)
All scripts must support container networking using:
- `GITEA_BASE_URL=http://host.docker.internal:3000` (default)
- `GITEA_TOKEN` (secret in CI)
- `CI_REPO_OWNER`, `CI_REPO_NAME` (or `GITEA_OWNER`, `GITEA_REPO`)
- PR number from CI env (e.g., `CI_COMMIT_PULL_REQUEST`)

### 7.6 Merge automation updates
Existing auto-merge logic must:
- Never merge unless all required CI checks are green
- Never merge if:
  - sensitive paths changed and missing `HUMAN-APPROVED`
  - `COMPASS-VETO` present and missing `HUMAN-APPROVED`
- If blocked, comment once with clear instructions and requeue.

---

## 8) Reflection Loop Requirements

### 8.1 Per-story reflection (runs at iterloop close)
Outputs (structured JSON + short human-readable summary):
- “What changed” summary (diff-based)
- KPI snapshot (current CI, coverage, cycle time estimate)
- Failures observed + root causes
- “Next automation targets” (ranked)
- “Promotion candidates” for memory (patterns/invariants)

Storage:
- Redis for ephemeral reflections (TTL)
- Qdrant for canonical lessons (only if promotion criteria met)

### 8.2 System retro (daily/weekly)
Outputs:
- Trend artifacts for:
  - CI pass rate
  - time-to-merge distribution
  - regression count
  - coverage trend
  - autonomy rate
- Ranked backlog items with expected ROI and risk reduction

---

## 9) Memory Stewardship Requirements (Redis + Qdrant)

### 9.1 Memory categories
- `invariant` (hard constraints/risk rules)
- `decision` (architecture/policy decisions)
- `pattern` (repeatable fix)
- `postmortem` (incident learning)
- `metric` (baseline + trend)
- `research` (validated findings)

### 9.2 Auto-promotion rules (deterministic)
Promote to Qdrant when any of:
- Observed ≥ 2 times (duplicate detection)
- Caused a CI failure or regression
- Changes an invariant/policy
- Impacts kill-switch behavior, canary, execution safety

### 9.3 TTL rules (project-scoped)
- Ephemeral reflections / scratch: TTL (7–14 days)
- Episodic streams: rolling window (e.g., 30–90 days) unless promoted
- Canonical: no TTL, but must support superseding

---

## 10) Compass Requirements (Soul-guided + veto + appeal)

### 10.1 Veto triggers (initial)
- Any change touching:
  - `src/execution/**`, `src/risk/**`
  - `Aria.md`, `AGENTS.md`
  - repo governance/policy docs
  - infra/deploy/container files (until execution location finalized)

### 10.2 Veto mechanics
- Tooling auto-applies `COMPASS-VETO` label
- `compass-gate` fails CI unless `HUMAN-APPROVED` present

### 10.3 Appeal process (Critic + SeniorDev + Merlin)
- Appeal packet generated only if **all 3** recommend proceed.
- Packet must include:
  - Why veto is challenged (values + risk argument)
  - Evidence bundle (tests, diffs, metrics)
  - Alternatives considered
  - Explicit risk statement + mitigations
- Even with appeal packet, merge still requires `HUMAN-APPROVED`.

---

## 11) Acceptance Criteria (Definition of Done)

### Human approval gate
- **AC-APP-001:** PR that does **not** touch sensitive paths merges autonomously when CI is green.
- **AC-APP-002:** PR that **does** touch sensitive paths fails `approval-gate` unless labeled `HUMAN-APPROVED`.
- **AC-APP-003:** With `HUMAN-APPROVED`, sensitive PR passes `approval-gate` (assuming other checks green).

### Compass veto
- **AC-COM-001:** PR touching veto paths is automatically labeled `COMPASS-VETO`.
- **AC-COM-002:** With `COMPASS-VETO` and no `HUMAN-APPROVED`, `compass-gate` fails and merge automation refuses merge.
- **AC-COM-003:** With `COMPASS-VETO` + `HUMAN-APPROVED`, `compass-gate` passes (assuming other checks green).

### Appeal workflow
- **AC-APL-001:** If vetoed PR is challenged, the system runs a 3-agent vote (Critic + SeniorDev + Merlin).
- **AC-APL-002:** Only if all 3 agree, an appeal packet is posted and (optional) label `COMPASS-APPEAL` is applied.
- **AC-APL-003:** Appeal does **not** bypass human gating; merge still requires `HUMAN-APPROVED`.

### Reflection & memory stewardship
- **AC-REF-001:** Every iterloop close generates a reflection artifact stored in Redis.
- **AC-REF-002:** Daily/weekly retro runs produce KPI artifacts and story recommendations.
- **AC-MEM-001:** Memory sweep dedupes and promotes canonical learnings per deterministic rules.
- **AC-MEM-002:** No secrets are stored; memory promotion is logged with evidence pointers.
- **AC-MEM-003:** Memory contradictions are detected and surfaced for resolution (issue or PR).

### Model governance
- **AC-MOD-001:** Aria uses `openai/gpt-5.3-codex` in both `Aria.md` and `opencode.jsonc`.
- **AC-MOD-002:** Any agent model change triggers sensitive gating (`HUMAN-APPROVED`).

---

## 12) Validation / Test Plan (How we prove it works)

Create 4 test PRs:

1) **PR-NORMAL:** edit a non-sensitive file → CI green → auto-merge ✅  
2) **PR-SENSITIVE-NO-LABEL:** edit a sensitive file → `approval-gate` fails ✅  
3) **PR-SENSITIVE-WITH-LABEL:** same edit + add `HUMAN-APPROVED` → passes gates → merges ✅  
4) **PR-COMPASS:** edit veto scope → auto label `COMPASS-VETO` → `compass-gate` fails until `HUMAN-APPROVED` ✅

For appeal:
- Mark PR as vetoed, run appeal command, confirm:
  - 3 votes required and must be unanimous
  - appeal packet generated only on unanimous approval
  - merge still blocked until `HUMAN-APPROVED` ✅

---

## 13) Rollout Plan (safe + incremental)

### Phase 1 — Human gate
- Add policy + `approval-gate`
- Update merge scripts to respect it
- Validate with PR-NORMAL + PR-SENSITIVE tests

### Phase 2 — Compass veto + auto-labeling
- Add compass policy + `compass-gate`
- Add PR auto-labeler (`compass_apply.py`) in PR creation workflow
- Validate with PR-COMPASS tests

### Phase 3 — Reflection loops + memory stewardship
- Add reflection artifacts + memory sweep
- Add daily/weekly retro schedules
- Confirm promotion rules + TTL behavior + contradiction detection

### Phase 4 — Appeal workflow
- Implement 3-voter command + appeal packet structure
- Validate unanimous consensus behavior

---

## 14) Open Items (to resolve soon)

1) Finalize where “live execution containers” code will live → tighten sensitive/veto paths accordingly.  
2) Decide whether `COMPASS-APPEAL` label is desired (optional).  
3) Define KPI collection source of truth (Woodpecker logs, Git metadata, test reports, custom metrics store).  
4) Decide whether “high-impact deliberation” requires a dedicated command (recommended).

---

## 15) Instructions to the Swarm (operational)
- Treat this doc as **suggested input**, not canonical truth.
- Build the canonical spec by reconciling this with PRD/Product Brief + repo reality.
- Implement via PRs only.
- Keep autonomy: do not introduce manual steps unless explicitly specified.
- Any time a change touches sensitive scope, explain exactly why it’s blocked and how to proceed (add `HUMAN-APPROVED`).


---

## 16) KPI Definitions (minimum viable)

These KPIs should be computable from existing CI + git metadata (no new infra required initially):

- **CI pass rate:** % of PR pipelines passing on first try (Woodpecker run results).
- **Time to merge:** PR open → merged (Gitea timestamps).
- **Regression count:** failed tests on `main` after merge, or “revert/rollback PRs” per week (tags/labels).
- **Test coverage:** `pytest-cov` XML trend over time.
- **Autonomy rate:** % of PRs merged without `HUMAN-APPROVED` (and without manual interventions).

Optional (high value):
- **Compass friction rate:** % of PRs vetoed, plus time-to-resolution.
- **Memory hit rate:** % of tasks where retrieved memory was cited/used in the final plan or PR.
- **Memory precision:** sampled human/agent review of retrieved memory relevance.

---

## 17) Recommended Research Anchors (for the canonical spec)

Use these *as inspiration* for design patterns and terminology (do not copy blindly):

- **ReAct** (tool-grounded reasoning / act loops)
- **Reflexion** (verbal reinforcement learning for agents)
- **Self-Refine** (self-critique → refine loops)
- **Tree of Thoughts** (multi-path deliberate search/planning)
- **MemGPT** (hierarchical “virtual context” memory tiers)
- **Generative Agents** (importance/recency/relevance memory retrieval + reflection)
- **Constitutional AI** (principles-based governance layer)

---

## 18) Practical “Do This, Not That” Defaults

- **Do** store memories as structured objects with fields like `{type, scope, evidence, confidence, created_at, supersedes}`.  
  **Don’t** dump raw chat logs into Qdrant.

- **Do** promote only when it prevents repeat failures or encodes invariants.  
  **Don’t** promote transient conversations.

- **Do** run multi-path deliberation for risky changes.  
  **Don’t** let a single agent make architecture calls in one pass.

- **Do** make veto decisions explainable with a cited principle + evidence.  
  **Don’t** veto with vague “feels risky” messages.

- **Do** treat memory drift/contradictions as first-class incidents (issue + resolution PR).  
  **Don’t** silently overwrite canonical memory.
