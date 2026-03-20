# AGENTS - Quick Reference for Opencode Swarm

> **Critical**: Load skills and run commands rather than reading full docs.

## 🚀 Quick Start for Agents

### Before Any Work
1. **MEM-SCAN**: Read nearest AGENTS.md for your scope
2. **Load Skill**: Identify task type → Load relevant skill (see "When to Use What" below)
3. **Start Iteration**: `.opencode/command/chise-iterloop-start.md`
4. **Start Swarm Session**: `.opencode/command/chise-swarm-session.md` (`start`)
5. **Verify Session Before Git Actions**: `.opencode/command/chise-swarm-session.md` (`verify`)
6. **Claim Ownership**: `.opencode/command/chise-claim-ownership.md` (if parallel work)

### Standard Workflow
```
skill(name="chiseai-git-workflow")          # Load git workflow skill
→ chise-iterloop-start                      # Start iteration
→ chise-swarm-session (start)               # Create isolated worktree session
→ chise-swarm-session (verify)              # Verify session before git actions
→ chise-metacog-start                       # Capture prediction card + confidence
→ chise-claim-ownership                     # Claim scope (if parallel)
→ [Do work following skill guidance]
→ chise-precommit-gates                     # Validate before PR
→ chise-metacog-close                       # Capture outcome + calibration
→ chise-swarm-session (close)               # Close session and release leases
→ chise-iterloop-close                      # Close and promote learnings
```

## 🎯 When to Use What Skills (Decision Guide)

### "I'm starting a new story..."
**Load:** `chiseai-git-workflow`
**Then run:** `chise-iterloop-start` then `chise-swarm-session` (`start` + `verify`)
**Why:** Sets up proper branch/worktree isolation and iteration tracking from the start

### "I need to delegate work to multiple agents..." (Jarvis only)
**Load:** `chiseai-worker-contracts` + `chiseai-parallel-safety`
**Then run:** `chise-claim-ownership` command
**Must include:** Complete worker contract in delegation
**Why:** Prevents scope conflicts and ensures safety guards

### "I'm about to edit files..."
**Load:** `chiseai-git-workflow`
**Then run:** `chise-swarm-session` (`start` if no active session, then `verify`)
**Why:** Ensures you're in the right branch/worktree with a valid lease before git actions

### "I'm working with Redis or Qdrant..."
**Load:** `chiseai-memory-ops`
**Why:** Provides correct key patterns, TTL settings, and fallback strategies

### "I'm preparing to create a PR..."
**Load:** `chiseai-validation`
**Then run:** `chise-precommit-gates` command
**Why:** Ensures all validation layers pass before handoff

### "CI failed on my PR..."
**Load:** `chiseai-validation`
**Then run:** `chise-ci-root-cause` → `chise-ci-failure-bundle` commands
**Why:** Systematic diagnosis with proper evidence collection

### "There's a merge conflict or incident..."
**Load:** `chiseai-incident-response`
**Then run:** `chise-incident-log` command
**For P0/P1:** Schedule post-mortem with `chise-postmortem-create`
**Why:** Structured logging and learning from failures

### "I need to clean up branches..."
**Load:** `chiseai-branch-hygiene`
**Then run:** `chise-branch-hygiene-check` command
**Why:** Systematic cleanup with Redis tracking

### "I'm creating Docker containers..."
**Load:** `chiseai-docker-governance`
**Why:** Ensures correct network, labels, and protected container awareness

### "I'm doing BMAD workflow tasks..."
**Load:** `chiseai-workflow-commands`
**Then run:** Relevant BMAD command (e.g., `bmad-bmm-create-prd`)
**Why:** Routes you to the correct workflow command for your task

### "I'm writing Python code..."
**Load:** `python-quality`
**Why:** Ensures code passes repo-configured quality checks (black, ruff, pytest)

### "I need to merge in an emergency..."
**Load:** `chiseai-git-workflow` (for context)
**Then run:** `chise-emergency-merge-override` command
**Why:** Documents the bypass procedure with required approvals

### "I need to validate skill structure..."
**Load:** `chiseai-skill-validation`
**Why:** Ensures skills have proper structure before submission

### "I need to check Grafana dashboards..."
**Load:** `chiseai-metrics-dashboard`
**Why:** Provides dashboard interaction patterns and metrics guidance

### "I'm writing tests..."
**Load:** `chiseai-testing-patterns`
**Why:** Ensures tests meet coverage requirements and follow patterns

### "I want better learning/calibration from Aria/Jarvis decisions..."
**Load:** `chiseai-metacognition-ops`
**Then run:** `chise-metacog-start` at iteration start and `chise-metacog-close` at iteration close
**Why:** Adds prediction→outcome→calibration loops with Redis/Qdrant memory promotion and measurable quality impact

### "I want autonomous skill usage without blocking execution when skills are missing..."
**Load:** `chiseai-skill-autonomy`
**Then run:** `chise-skill-autonomy-tick` (`mode=start|close|weekly`)
**Why:** Captures missing-skill gaps as KPI/reflection data while allowing execution to continue

### "I want Aria to run autonomous cognition oversight and auto-fix low/medium issues..."
**Load:** `chiseai-autocog-orchestration`
**Then run:** `chise-autocog-daily-run` → `chise-autocog-review` → `chise-autocog-action`
**Why:** Adds backend+Aria dual-layer review, severity-based routing, and Discord-observable actions.

## 📋 Quick Skill Reference Table

| Skill | Primary Use | Key Commands |
|-------|-------------|--------------|
| `chiseai-git-workflow` | Git operations, branching, PRs | `chise-swarm-session`, `chise-precommit-gates` |
| `chiseai-memory-ops` | Redis/Qdrant operations | `chise-iterloop-start`, `chise-iterloop-close` |
| `chiseai-parallel-safety` | Parallel work delegation | `chise-claim-ownership`, `chise-check-ownership` |
| `chiseai-validation` | Quality gates, CI diagnosis | `chise-ci-root-cause`, `chise-ci-failure-bundle` |
| `chiseai-worker-contracts` | Jarvis-to-worker delegation | Every delegation must use |
| `chiseai-branch-hygiene` | Branch lifecycle management | `chise-branch-hygiene-check` |
| `chiseai-incident-response` | Incident logging, post-mortems | `chise-incident-log`, `chise-postmortem-create` |
| `chiseai-docker-governance` | Container/network config | N/A |
| `chiseai-workflow-commands` | BMAD planning/implementation | All `bmad-*` commands |
| `chiseai-skill-validation` | Skill structure validation | N/A |
| `chiseai-metrics-dashboard` | Grafana dashboard interaction | N/A |
| `chiseai-testing-patterns` | Testing patterns and coverage | N/A |
| `chiseai-metacognition-ops` | Decision quality calibration and reflection loops | `chise-metacog-start`, `chise-metacog-close`, `chise-metacog-weekly` |
| `chiseai-skill-autonomy` | Autonomous skill routing/coverage/effectiveness with non-blocking fallback | `chise-skill-autonomy-tick`, `chise-skill-backlog-ingest`, `chise-skill-promote`, `chise-skill-rollback` |
| `chiseai-autocog-orchestration` | Autonomous cognition oversight, Aria review, and severity-based auto-action | `chise-autocog-daily-run`, `chise-autocog-review`, `chise-autocog-action` |
| `python-quality` | Python code quality | N/A |

## 🔧 Skill Loading Pattern

```markdown
When starting work:
1. Identify your task type from "When to Use What" above
2. Load the relevant skill: skill(name="skill-name")
3. Follow the skill's guidance
4. Run associated commands as needed
5. Close with `chise-iterloop-close` when done
```

## 🆘 Emergency Procedures

- **Emergency merge override**: `.opencode/command/chise-emergency-merge-override.md`
- **CI failure diagnosis**: `chise-ci-root-cause.md` → `chise-ci-failure-bundle.md`
- **Incident logging**: `chise-incident-log.md`
- **Post-mortem creation**: `chise-postmortem-create.md`

## 📚 Full Documentation

- **Workflow Status**: `docs/bmm-workflow-status.yaml`
- **Validation Registry**: `docs/validation/validation-registry.yaml`
- **Skills Directory**: `.opencode/skills/`
- **Commands Directory**: `.opencode/command/`
- **Post-Mortems**: `docs/postmortems/`

## Skill-First Context Compression (Required)

- Keep `AGENTS.md` focused on authority, gates, and escalation.
- Load operational detail only when needed via skills.
- Mandatory skill loading for feature domains:
  - Docker/network changes -> `chiseai-docker-governance`
  - CI diagnosis and quality gates -> `chiseai-validation`
  - Incident handling/post-mortems -> `chiseai-incident-response`
  - Branch lifecycle cleanup -> `chiseai-branch-hygiene`
  - Iterlog/Redis/Qdrant/memory promotion -> `chiseai-memory-ops` + `chiseai-metacognition-ops`
  - Worker delegation contracts -> `chiseai-worker-contracts`
- If a required skill is not loaded for the domain, stop and load it before executing.

---

## CRITICAL WORKFLOW SUMMARY

- **Data-first:** finish Phase 0 (Data Gathering) before analysis
- **Granular tasks:** small, clear validation criteria
- **Sequential:** no parallel work until data foundation complete
- **Quality gates:** each task must pass validation

---

## Git Safety Essentials

- Never work on `main` without explicit human approval
- Run `git status -sb` before/after operations
- PR creation must be push-triggered via `.woodpecker/pr-auto-flow.yaml` for normal flow
- Direct PR open/update/close actions by agents are exceptional-only (incident/manual override/recovery)
- Use `feature/<story-id>-<slug>` branches
- PR titles must contain a recognized story id token:
  - `ST-*`, `CH-*`, `FT-*`, `REWARD-*`, `REPO-*`, `SAFETY-*`, `BRANCH-*`, `PAPER-*`, `RECON-*` (must include a digit)
- Before switching branches, working tree must be clean

### Merge Authority (Explicit Roles)
- **Workers**: Push branches + handoff evidence only; workers do NOT open PRs or merge to main
- **Jarvis**: Orchestrates handoff to Merlin; coordinates worker completion
- **senior-dev**: May prepare integration fixes on feature branches; direct main merges require explicit non-autonomous delegation
- **Merlin**: Autonomous merge/reconcile authority (CI triage, merge to main, branch pruning, exceptional PR lifecycle recovery). Required merge authority after >2 failed merge attempts (see merge attempt definition below)

### Question Routing Authority (REQUIRED)
- **Only Aria may ask Craig direct questions.**
- **Jarvis and all other subagents/workers must never ask Craig/user direct questions.**
- If a subagent needs clarification, it must escalate upward to the orchestrator (Jarvis -> Aria) using a structured blocker packet with:
  - `question`
  - `recommended_default`
  - `risk_if_default_wrong`
  - `decision_deadline_utc`
- Orchestrators are responsible for answering all subagent questions, choosing defaults when safe, and only escalating to Craig under Aria's strict escalation criteria.
- In orchestrated task mode, menu-driven "wait for user input" behavior is forbidden unless the session is explicitly marked interactive by Aria.

### Merge Attempt Definition
One merge attempt = sync/rebase OR conflict resolution + required checks rerun + merge attempt

### When Merlin is Required
- After 2+ failed merge attempts by senior-dev with attempted fixes
- Emergency merges requiring override
- Complex merges with conflicts across >3 files
- Infrastructure changes (CI, Terraform, core workflow)

### Cross-Branch Verification Guardrail (REQUIRED)
Before claiming "merged to main", verify with:
```bash
git branch --contains <commit>
```
This ensures the work is actually on main and prevents false merge claims. See `docs/evidence/PARTY-MODE-TRUTH-AUDIT-BRAINEVAL-CI.md` for the incident that motivated this rule.

### Post-Branch Reconcile Loop (REQUIRED)
After each branch handoff/merge cycle, run this loop before starting the next batch:
1. Check Woodpecker PR/pipeline state and classify all non-green pipelines (`running|pending|failure|error`).
2. Route failed/error PRs for fixes before additional dependent work proceeds.
3. Confirm merged branch head is contained in `main` (`git branch --contains <head_sha>`).
4. Sync local main to origin:
```bash
git switch main
git fetch origin --prune
git pull --ff-only origin main
git status -sb
```
5. Only continue new dependent development from the refreshed local `main`.

### Pre-Critic Merge Sync Gate (REQUIRED)
Before Jarvis runs Critic review for release acceptance:
1. Confirm work is merged to `origin/main` (not only local branch/main).
2. Confirm merged head containment on `main` (`git branch --contains <head_sha>`).
3. Confirm local `main` is synced to `origin/main` (`git fetch origin --prune` + `git pull --ff-only origin main`).
4. If any check fails, Critic review is advisory only and completion is blocked.

---

## Docker & Network Governance (CRITICAL SUMMARY)

Skill-first rule:
- For any Docker/container/network action, load `chiseai-docker-governance`.
- Treat AGENTS as policy summary; treat the skill as the operational runbook.

Non-negotiable guardrails:
- Authoritative Docker network is `chiseai`.
- From agent/container context, prefer `host.docker.internal` for host services; do not use `localhost` from inside containers.
- Required container label for ChiseAI services: `project=chiseai`.
- Protected containers require explicit Captain Craig approval before modification:
  - `tradedev`
  - `intelligent_ride`
  - `aisetup-mcp-discord-1`
  - `duckduckgo-mcp-server`
- Pre-commit governance check (`scripts/validate_docker_connectivity.py`) is blocking.

Authoritative detail sources (load on demand):
- `.opencode/skills/chiseai-docker-governance/SKILL.md`
- `infrastructure/terraform/` (network/container declarations)
- `scripts/validate_docker_connectivity.py` (enforced checks)

---

## Recent Skill Additions

- `chiseai-skill-validation` - Validate skill structure and compliance
- `chiseai-metrics-dashboard` - Grafana dashboard interaction guide
- `chiseai-testing-patterns` - Testing patterns and best practices
- `chiseai-metacognition-ops` - Metacognitive prediction/outcome/calibration workflow
- `chiseai-skill-autonomy` - Autonomous skill KPI loop with non-blocking missing-skill fallback
- `chiseai-autocog-orchestration` - Aria autonomous cognition oversight with backend review and severity-based action routing

---

## Swarm Policy Hardening Addendum (Required)

This addendum hardens orchestration behavior for Aria/Jarvis and all executor agents.
These rules are additive and must be enforced consistently across `AGENTS.md` and `.opencode/agent/*.md`.

### A) Canonical Routing and Escalation State Machine (Required)

- Task sizing policy:
  - `quickdev`: all 1SP tasks
  - `dev`: all tasks >1SP up to 3SP
  - `senior-dev`: tasks >3SP, cross-cutting refactors, complex/systemic failures
- Escalation pass limits (strict):
  - `quickdev`: max 2 passes on the same blocker, then escalate to `dev`
  - `dev`: max 2 passes on the same blocker, then escalate to `senior-dev`
  - `senior-dev`: max 2 passes on the same blocker, then escalate to `merlin`
  - `merlin`: max 3 passes on the same blocker, then return blocker packet to Aria and wait for direction
- Legacy five-attempt escalation references are superseded by this policy.

### B) Planning and Replanning Gates (Required)

- Rule: plan first, execute second.
- No executor delegation until Aria marks `PLAN_APPROVED=true`.
- If any of the following happen, stop that execution path and replan before continuing:
  - failed validation gate
  - scope drift or hidden dependency discovery
  - escalation threshold reached
  - new medium/high/critical risk signal invalidating assumptions
- Never "push through" failed validation with hopeful retries.

### C) Subagent Offload and Context Hygiene (Required)

- Aria/Jarvis must offload complex analysis and execution to subagents to keep orchestrator context clean.
- Use bounded escalation and tiering, not unbounded "more compute".
- Parallelization is allowed only with disjoint scope + explicit locks + no ordering dependency.

### D) Proof-of-Work Completion Gate (Required)

- No task may be marked complete without evidence.
- Required completion evidence:
  - commands run
  - tests run and results
  - log checks performed and findings
  - acceptance criteria mapping to evidence
  - residual risk notes
- **File existence verification**: For every file claimed as changed, worker must provide:
  - `git show <commit> --name-only` output OR `ls -la <file_path>` with timestamp proof
  - `git diff --stat HEAD~N` showing file changes with +/- counts
- **Cross-branch verification**: Before claiming 'merged to main', worker must provide:
  - `git branch --contains <commit>` output showing 'main'
- Exceptions (for no-test tasks such as docs-only changes) require explicit no-test justification.

#### File Existence Verification Requirements

Every completion claim MUST include:

1. **File Change Evidence**: `git diff --stat HEAD~N` showing all modified files
2. **Commit Content Proof**: `git show <commit-sha> --name-only` proving files exist in commit
3. **Branch Containment Proof**: `git branch --contains <commit-sha>` showing commit is on claimed branch
4. **Cross-Branch Verification**: For merged work, `git branch --contains <commit-sha>` must show 'main'

**No file-existence proof = No completion approval**

### E) Autonomous Bug-Fix Policy (Required)

- Bug tasks default to autonomous root-cause-first execution:
  - reproduce -> isolate root cause -> patch -> verify -> regression check
- No user hand-holding for routine bug fixes.
- Escalate to Aria when:
  - requirements are ambiguous and risky
  - security/compliance impact exists
  - production-impacting decision needs authority

### F) Critic and Remediation Loop (Required)

- After implementation, Jarvis must run read-only critic review per completed task (parallel where safe).
- If issues are found:
  - `low|medium`: Jarvis creates remediation plan, executes round 1 -> re-review -> round 2 if needed.
  - `high|critical`: Jarvis must report status + issues + recommended plan to Aria and pause that scope.
  - If Aria critiques the plan, Jarvis revises and resubmits until approved.
- If unresolved after two remediation rounds (or Aria rejects plan path), return blockers to Aria with full evidence.

### G) Lessons Loop (Required)

- Every session must capture lessons in `docs/tempmemories/lessons.md` in addition to existing memory flows.
- At session start, Aria/Jarvis must read relevant lesson entries and apply them.
- Single-writer rule:
  - workers emit `LESSON_CANDIDATE`
  - Jarvis normalizes/deduplicates and appends final entries at session close

### H) Machine-Checkable Governance (Required)

- CI must include policy consistency checks that fail on:
  - contradictory escalation thresholds across files
  - contradictory routing rules across files
  - missing required completion/evidence fields
- Add explicit handoff metadata schema:
  - `attempt_count`
  - `escalation_from`
  - `escalation_reason`
  - `evidence_ref`
- Add task budget caps:
  - `max_total_attempts`
  - `max_wall_clock_minutes`
  - `max_token_budget`

### I) Fast-Agent Soft Deprecation (Policy)

- `quickdev-fast` (and optionally `juniordev`) are soft-deprecated for default routing.
- Default 1SP route is `quickdev`; fast agents remain fallback-only during transition.
- Remove fast agents from default routing tables first, then fully retire after verified non-use.

### J) Jarvis Session Rotation (Required)

- Aria must start a fresh Jarvis session when scope changes materially:
  - new batch with different AC,
  - new task family/workstream,
  - high/critical incident replanning.
- Jarvis session handoff must include current plan state, open blockers, active risks, and pending evidence.

### K) Aria Fallback Control (Required)

- If Jarvis cannot produce an approvable high/critical remediation plan after 2 revisions, Aria takes direct orchestration control for that scope.
- Aria reassigns execution to `senior-dev` or `merlin` and preserves evidence trail and containment notes.

### L) Repeated-Error Circuit Breaker (Required)

- Define `error_signature` as:
  - `tool + normalized_error_message + primary file:line|test + task_scope`
- If the same `error_signature` appears 2 times in the same scope without a material strategy change, stop retries and switch to RCA mode.
- RCA mode must include:
  - failing evidence reference
  - root-cause hypothesis
  - at least 2 materially different fix options
  - selected option and rationale
- A retry is allowed only when `strategy_delta` is explicit (different code path, dependency strategy, validation method, or execution order).
- Re-running the same command/patch pattern without `strategy_delta` is non-compliant.
- On 3rd recurrence of the same `error_signature` across escalation tiers, log an incident and escalate blocker packet to Aria.
- Completion evidence must include:
  - `error_signature`
  - `attempt_count`
  - `strategy_delta`
  - `evidence_ref`


## YAML Rules
- Treat YAML as validation-sensitive, not prose.
- For `.yaml`, `.yml`, and markdown frontmatter, make the smallest possible change.
- Preserve indentation, quoting style, comments, and key order unless explicitly told otherwise.
- Trigger to load skill: if task touches `.yaml`, `.yml`, or markdown frontmatter, load `yaml-editor` before editing.
- Prefer `@yaml-config-editor` for YAML-heavy edits (multiple YAML files, schema-sensitive config, or frontmatter batches).
- After editing `.yaml` or `.yml`, run this exact sequence:
  1. `npx --prefix . prettier --write <file>`
  2. `yamllint <file>`
  3. if lint fails, fix and rerun both commands until clean
- After editing markdown frontmatter:
  1. preserve opening and closing `---` boundaries
  2. run `python3 scripts/validate_frontmatter.py`
  3. if validation fails, fix frontmatter and rerun until clean
- If a schema modeline exists, respect it and keep the file schema-valid.
- Do not finish with known YAML parse or lint errors.
- Preferred repair command for one target file: `.opencode/commands/yaml-fix.md`.
