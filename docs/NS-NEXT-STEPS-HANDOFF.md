# NS Stream Next Steps Handoff Document

**Document Version:** 1.0  
**Created:** 2026-02-25  
**Status:** ACTIVE - Ready for execution  
**Scope:** Soul/Reflect/Memory stewardship implementation  

---

## 1. Current State Snapshot

### 1.1 Infrastructure Recovery Status

All 19 ChiseAI infrastructure containers are **HEALTHY** on the `chiseai` network (172.27.0.0/16):

| Container | Status | Health | Port Mapping |
|-----------|--------|--------|--------------|
| chiseai-redis | running | healthy | 6380:6380 |
| chiseai-postgres | running | healthy | 5434:5434 |
| chiseai-qdrant | running | healthy | 6334:6334 |
| chiseai-influxdb | running | healthy | 18087:18087 |
| chiseai-api-final | running | healthy | 8001:8000 |
| chise-dashboard | running | healthy | 8502:8501 |
| chiseai-grafana | running | healthy | 3001:3001 |
| gitea | running | healthy | 3000:3000 |
| woodpecker-server | running | healthy | 8012:8000 |
| woodpecker-agent | running | healthy | - |
| taiga-front | running | healthy | 9001:80 |
| taiga-back | running | healthy | 9002:8000 |
| taiga-events | running | healthy | 9003:8888 |
| taiga-postgres | running | healthy | - |
| taiga-redis | running | healthy | - |
| taiga-rabbitmq | running | healthy | - |

**Verification Commands:**
```bash
# Check container health
docker ps --filter network=chiseai --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Verify Redis connectivity
redis-cli -h host.docker.internal -p 6380 ping

# Verify Qdrant collections
curl http://host.docker.internal:6334/collections
```

### 1.2 EP-NS-008 Final Status

**Status:** COMPLETED (early close approved 2026-02-25)

**Completion Summary:**
- All 6 stories verified: ST-NS-038 through ST-NS-043
- 235 tests passing, 0 failures, 3 skipped
- Infrastructure healthy across all 19 containers
- Rollback runbook finalized and tested
- Party Mode consolidation PR #230 merged

**Canary Decision:** GO (with early close approval)
- Original canary period: 2026-02-21 to 2026-02-28 (7 days)
- Actual close date: 2026-02-25 (4 days)
- Rationale: All validation gates passed, rollback tested and working

**Stories Completed:**
| Story | Title | Status |
|-------|-------|--------|
| ST-NS-038 | Circuit Breaker Registry | completed |
| ST-NS-039 | Retry Coordinator | completed |
| ST-NS-040 | Self-Healing Engine | completed |
| ST-NS-041 | Incident Manager | completed |
| ST-NS-042 | Rollback Coordinator | completed |
| ST-NS-043 | Unified Dashboard | completed |

### 1.3 NS Stream Status

**Stream Status:** CLOSED  
**Archive Date:** 2026-02-25  
**Next Phase:** Soul/Reflect/Memory stewardship (this handoff)

---

## 2. Remaining Workstream Scope

### 2.1 Soul/Reflect/Memory Stewardship Roadmap

This workstream implements the governance layer described in `temp/governance-reflection-memory-compass-suggested-spec.md` with three core pillars:

```
┌─────────────────────────────────────────────────────────────────┐
│                    SOUL-GUIDED COMPASS                          │
│  Constitutional governance layer with veto capability           │
│  └── Auto-applies COMPASS-VETO label on sensitive changes       │
│  └── Appeal workflow with 3-agent consensus (Critic+Senior+Merlin)│
├─────────────────────────────────────────────────────────────────┤
│                  CONTINUOUS REFLECTION                          │
│  Micro/meso/macro reflection loops with artifact generation     │
│  └── Per-story reflection at iterloop close                     │
│  └── Daily/weekly retro KPIs and trend analysis                 │
├─────────────────────────────────────────────────────────────────┤
│                 MEMORY STEWARDSHIP                              │
│  Automated memory promotion from Redis to Qdrant                │
│  └── Deduplication, TTL management, contradiction detection     │
│  └── Promotion rules: ≥2 occurrences, CI failures, invariants   │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Phase Breakdown

**Phase 1: Foundation (Sequential)**
- ST-SOUL-001: Compass framework + policy files
- Deliverables: `docs/policy/compass.yaml`, `scripts/ci/compass_gate.py`

**Phase 2: Infrastructure (Parallel)**
- ST-REFLECT-001: Reflection loop infrastructure
- ST-MEMORY-002: Memory stewardship automation
- Deliverables: `scripts/ops/reflection_runner.py`, `scripts/ops/memory_sweep.py`

### 2.3 Dependency Order

```
ST-SOUL-001 (Foundation)
    │
    ├──> ST-REFLECT-001 (can run parallel after policy files exist)
    │
    └──> ST-MEMORY-002 (can run parallel after policy files exist)
```

**Safe Parallelization:**
- ST-REFLECT-001 and ST-MEMORY-002 can execute in parallel once ST-SOUL-001 policy files are in place
- No cross-dependencies between reflection and memory stories
- Both depend only on the existence of `docs/policy/` structure

---

## 3. Story Definitions

### 3.1 ST-SOUL-001: Soul-Guided Compass Framework

**Objective:** Implement constitutional governance layer with veto capability

**Story Points:** 5  
**Priority:** P1-HIGH  
**Owner Recommendation:** senior-dev (architecture) + critic (governance rules)

**Acceptance Criteria:**
- [ ] COMPASS-VETO label auto-applied when PR touches veto paths
- [ ] `compass-gate` CI check blocks merges while COMPASS-VETO present
- [ ] Appeal workflow triggers on 3-agent consensus (Critic + SeniorDev + Merlin)
- [ ] Policy file `docs/policy/compass.yaml` defines veto paths and principles
- [ ] Script `scripts/ci/compass_gate.py` implements gate logic
- [ ] Script `scripts/ops/compass_apply.py` auto-applies labels

**Test Plan (4 Test PRs):**
1. **PR-NORMAL:** Edit non-sensitive file → CI green → auto-merge ✅
2. **PR-SENSITIVE-NO-LABEL:** Edit sensitive file → `compass-gate` fails ✅
3. **PR-SENSITIVE-WITH-LABEL:** Same edit + HUMAN-APPROVED → passes → merges ✅
4. **PR-COMPASS-VETO:** Edit veto scope → COMPASS-VETO auto-applied → blocked ✅

**Live Validation:**
```bash
# Verify veto triggers on execution/risk path changes
python3 scripts/ops/compass_apply.py --dry-run --pr=123
git diff --name-only | xargs python3 scripts/ci/compass_gate.py --check
```

**Risks and Mitigations:**
| Risk | Impact | Mitigation |
|------|--------|------------|
| Over-vetoing blocks legitimate work | MEDIUM | Clear appeal process with 3-agent consensus |
| False positives on path detection | LOW | Explicit path glob list in compass.yaml |
| Appeal workflow too slow | LOW | Async execution, 15-min timeout |

**Files to Create/Modify:**
- `docs/policy/compass.yaml` (new)
- `docs/policy/human_approval.yaml` (new)
- `scripts/ci/compass_gate.py` (new)
- `scripts/ops/compass_apply.py` (new)
- `.woodpecker.yml` (modify - add compass-gate step)

---

### 3.2 ST-REFLECT-001: Continuous Reflection Loop Infrastructure

**Objective:** Implement micro/meso/macro reflection loops with artifact generation

**Story Points:** 5  
**Priority:** P1-HIGH  
**Owner Recommendation:** dev (infrastructure) + senior-dev (schema design)

**Acceptance Criteria:**
- [ ] Per-story reflection artifact generated at iterloop close
- [ ] Micro-reflection: After each tool/action (stored in Redis, 7-day TTL)
- [ ] Meso-reflection: Per-story closure (promoted to Qdrant if criteria met)
- [ ] Macro-reflection: Daily/weekly retro with KPI trends
- [ ] Reflection artifact schema validated (JSON)
- [ ] Script `scripts/ops/reflection_runner.py` implements loops

**Reflection Artifact Schema:**
```json
{
  "story_id": "ST-XXX-001",
  "reflection_type": "micro|meso|macro",
  "timestamp": "2026-02-25T18:00:00Z",
  "what_changed": "Summary of changes",
  "kpi_snapshot": {
    "ci_pass_rate": 0.95,
    "coverage": 0.82,
    "cycle_time_hours": 4.5
  },
  "failures_observed": [],
  "root_causes": [],
  "next_automation_targets": [],
  "promotion_candidates": []
}
```

**Live Validation:**
```bash
# Run reflection on next 3 stories, verify artifacts created
python3 scripts/ops/reflection_runner.py --story-id=ST-TEST-001 --type=meso
redis-cli -h host.docker.internal -p 6380 hgetall "bmad:chiseai:reflection:story:ST-TEST-001"
```

**Risks and Mitigations:**
| Risk | Impact | Mitigation |
|------|--------|------------|
| Reflection overhead slows iteration | MEDIUM | Async execution, configurable TTL |
| Storage bloat from artifacts | LOW | TTL management, promotion rules |
| Schema drift over time | LOW | Versioned schema, validation on read |

**Files to Create/Modify:**
- `docs/policy/reflection_policy.yaml` (new)
- `scripts/ops/reflection_runner.py` (new)
- `src/governance/reflection/` (new module)
- `tests/unit/governance/test_reflection.py` (new tests)

---

### 3.3 ST-MEMORY-002: Memory Stewardship Automation

**Objective:** Automated memory promotion from Redis to Qdrant with deduplication

**Story Points:** 5  
**Priority:** P1-HIGH  
**Owner Recommendation:** senior-dev (promotion logic) + dev (sweep automation)

**Acceptance Criteria:**
- [ ] Auto-promotion rules implemented (≥2 occurrences, CI failures, invariants)
- [ ] TTL management for ephemeral vs canonical memories
- [ ] Deduplication using embedding similarity (threshold: 0.92)
- [ ] Contradiction detection for conflicting memories
- [ ] Script `scripts/ops/memory_sweep.py` runs daily via cron
- [ ] Promotion logged with evidence pointers (PR/commit links)

**Memory Categories:**
| Category | Storage | TTL | Promotion Rule |
|----------|---------|-----|----------------|
| invariant | Qdrant | permanent | immediate |
| decision | Qdrant | permanent | ≥2 occurrences |
| pattern | Qdrant | permanent | caused CI fix |
| postmortem | Qdrant | permanent | immediate |
| metric | Redis | 30 days | aggregate only |
| research | Qdrant | permanent | validated |

**Auto-Promotion Rules:**
1. Observed ≥2 times (duplicate clustering)
2. Caused CI failure/regression or prevented one
3. Updates an invariant/policy
4. Touches execution safety (kill-switch/canary/risk)

**Live Validation:**
```bash
# Run sweep on existing iterlog entries, verify promotions
python3 scripts/ops/memory_sweep.py --dry-run
python3 scripts/ops/memory_sweep.py --promote
# Verify in Qdrant
curl http://host.docker.internal:6334/collections/memories/points scroll
```

**Risks and Mitigations:**
| Risk | Impact | Mitigation |
|------|--------|------------|
| Memory bloat | MEDIUM | Deduplication, TTL, contradiction detection |
| Contradictions in canonical memory | HIGH | Auto-detection + issue creation |
| False promotions | LOW | Multi-signal threshold, evidence required |

**Files to Create/Modify:**
- `docs/policy/memory_policy.yaml` (new)
- `scripts/ops/memory_sweep.py` (new)
- `src/governance/memory/` (new module)
- `tests/unit/governance/test_memory_stewardship.py` (new tests)

---

## 4. Execution Protocol

### 4.1 Branch Naming Convention

```
feature/ST-[SOUL|REFLECT|MEMORY]-[XXX]-[slug]
```

**Examples:**
- `feature/ST-SOUL-001-compass-framework`
- `feature/ST-REFLECT-001-reflection-infrastructure`
- `feature/ST-MEMORY-002-memory-stewardship`

### 4.2 Worktree Isolation

```bash
# Standard worktree path pattern
/tmp/worktrees/ST-[ID]-[agent]
```

**Examples:**
- `/tmp/worktrees/ST-SOUL-001-seniordev`
- `/tmp/worktrees/ST-REFLECT-001-dev`
- `/tmp/worktrees/ST-MEMORY-002-seniordev`

### 4.3 Session Verification

**Before any git actions:**
```bash
python3 scripts/swarm/session.py verify \
  --story-id=ST-XXX-001 \
  --branch=feature/ST-XXX-001-slug \
  --worktree-path=/tmp/worktrees/ST-XXX-001-agent
```

### 4.4 Evidence Requirements

Each story handoff must include:

| Evidence Type | Required | Format |
|---------------|----------|--------|
| Files changed | Yes | List with line counts (+N/-M) |
| Commands run | Yes | Command + output snippet |
| Verification steps | Yes | Step-by-step validation |
| Test results | Yes | pytest output summary |
| Status sync | Yes | bmm-workflow-status.yaml diff |

### 4.5 Merge Authority

```
Worker (you)
    │
    ├── Push branch to Gitea
    ├── Run local CI validation
    ├── Report handoff to Jarvis
    │
    ▼
Jarvis (orchestrator)
    │
    ├── Coordinate worker completion
    ├── Validate all evidence present
    ├── Handoff to Merlin
    │
    ▼
Merlin (sole merge authority)
    │
    ├── Open/update/close PRs
    ├── Merge to main
    └── Branch cleanup
```

**Workers must NOT:**
- Open PRs
- Merge to main
- Delete branches

---

## 5. Completion Gates and Escalation

### 5.1 Pre-Commit Gates

**Required before handoff:**
```bash
# Code quality
black --check src/
ruff check src/
mypy src/

# Testing
pytest tests/ -v --cov=src --cov-report=term-missing

# Status sync validation
python3 scripts/validate_status_sync.py
```

### 5.2 5-Attempt Rule

**Escalation trigger:** After 5 failed attempts on the same blocker

**Escalation path:**
1. Worker documents blocker in iterlog
2. Jarvis reviews for rescheduling/re-scoping
3. If unresolved, escalate to Merlin
4. Merlin decides: continue, re-scope, or abort

### 5.3 Stop Conditions

**Stop immediately and report to Jarvis:**
- Scope creep (changes outside story scope)
- Forbidden path touches (without HUMAN-APPROVED)
- Upstream blockers (dependencies not met)
- Ownership conflicts (another story owns scope)
- CI regression on main

### 5.4 Incident Logging

**Use command:** `.opencode/command/chise-incident-log.md`

**Log to Redis:**
```python
redis_state_rpush(
    name="bmad:chiseai:iterlog:story:ST-XXX:incidents",
    value=json.dumps({
        "timestamp": "2026-02-25T18:00:00Z",
        "type": "blocker|regression|conflict",
        "description": "...",
        "resolution": "..."
    })
)
```

---

## 6. Day 0 Kickoff Checklist

### 6.1 Pre-Work Setup

- [ ] Read this handoff document completely
- [ ] Load relevant skills:
  ```bash
  skill(name="chiseai-git-workflow")
  skill(name="chiseai-worker-contracts")
  skill(name="chiseai-parallel-safety")
  ```
- [ ] Verify infrastructure health (all 19 containers)
- [ ] Review `temp/governance-reflection-memory-compass-suggested-spec.md`

### 6.2 Batch 1 Setup (ST-SOUL-001)

- [ ] Create feature branch: `feature/ST-SOUL-001-compass-framework`
- [ ] Start worktree session:
  ```bash
  python3 scripts/swarm/session.py start \
    --story-id=ST-SOUL-001 \
    --branch=feature/ST-SOUL-001-compass-framework \
    --worktree-path=/tmp/worktrees/ST-SOUL-001-seniordev
  ```
- [ ] Claim ownership in Redis:
  ```python
  redis_state_hset(
      name="bmad:chiseai:ownership",
      key="docs:policy",
      value="ST-SOUL-001/senior-dev/2026-02-25T18:00:00Z",
      expire_seconds=432000
  )
  ```
- [ ] Run session verify
- [ ] Start iterloop: `.opencode/command/chise-iterloop-start.md`

### 6.3 Batch 2 Setup (ST-REFLECT-001 + ST-MEMORY-002)

**Wait for ST-SOUL-001 policy files to exist, then:**

- [ ] Create feature branches (parallel):
  - `feature/ST-REFLECT-001-reflection-infrastructure`
  - `feature/ST-MEMORY-002-memory-stewardship`
- [ ] Start worktree sessions (isolated paths)
- [ ] Claim ownership in Redis (non-overlapping scopes)
- [ ] Run session verify for each
- [ ] Start iterloops

---

## 7. First Two Execution Batches

### 7.1 Batch 1: Sequential - Foundation

**Story:** ST-SOUL-001: Compass framework + policy files

**Deliverables:**
| File | Type | Purpose |
|------|------|---------|
| `docs/policy/compass.yaml` | Policy | Veto rules and principles |
| `docs/policy/human_approval.yaml` | Policy | Sensitive path definitions |
| `scripts/ci/compass_gate.py` | CI Script | Gate implementation |
| `scripts/ops/compass_apply.py` | Ops Script | Auto-labeling logic |

**Execution Steps:**
1. Create policy files with veto path definitions
2. Implement compass_gate.py CI check
3. Implement compass_apply.py auto-labeler
4. Update .woodpecker.yml with new steps
5. Run 4 test PRs to validate
6. Handoff to Jarvis

**Estimated Duration:** 2-3 days

### 7.2 Batch 2: Parallel - Infrastructure

**Stories:** 
- ST-REFLECT-001: Reflection loop infrastructure
- ST-MEMORY-002: Memory stewardship automation

**Deliverables:**
| Story | File | Type | Purpose |
|-------|------|------|---------|
| ST-REFLECT-001 | `docs/policy/reflection_policy.yaml` | Policy | Reflection triggers and schema |
| ST-REFLECT-001 | `scripts/ops/reflection_runner.py` | Ops Script | Reflection execution |
| ST-REFLECT-001 | `src/governance/reflection/` | Module | Reflection logic |
| ST-MEMORY-002 | `docs/policy/memory_policy.yaml` | Policy | Promotion rules and TTLs |
| ST-MEMORY-002 | `scripts/ops/memory_sweep.py` | Ops Script | Memory sweep automation |
| ST-MEMORY-002 | `src/governance/memory/` | Module | Memory stewardship logic |

**Execution Steps (Parallel):**

**ST-REFLECT-001:**
1. Define reflection artifact schema
2. Implement micro/meso/macro loops
3. Create reflection_runner.py
4. Add iterloop integration
5. Test on 3+ stories
6. Handoff to Jarvis

**ST-MEMORY-002:**
1. Define memory categories and promotion rules
2. Implement deduplication logic
3. Create memory_sweep.py
4. Add contradiction detection
5. Test sweep on existing iterlog entries
6. Handoff to Jarvis

**Estimated Duration:** 3-4 days (parallel)

---

## 8. Memory and Status Sync

### 8.1 Redis Iterlog Pattern

**Key Pattern:** `bmad:chiseai:iterlog:story:ST-XXX`

**Example:**
```python
# Log iteration start
redis_state_hset(
    name="bmad:chiseai:iterlog:story:ST-SOUL-001",
    key="started_at",
    value="2026-02-25T18:00:00Z"
)

# Log key decisions
redis_state_rpush(
    name="bmad:chiseai:iterlog:story:ST-SOUL-001:decisions",
    value=json.dumps({
        "timestamp": "2026-02-25T18:30:00Z",
        "decision": "Use YAML over JSON for policy files",
        "rationale": "Human readability for governance docs"
    })
)
```

### 8.2 Qdrant Long-Term Storage

**Collection:** `memories`

**Storage Pattern:**
```python
# Promote to Qdrant on story completion
qdrant_qdrant-store(
    information="Compass veto should trigger on execution path changes",
    metadata={
        "type": "invariant",
        "story_id": "ST-SOUL-001",
        "source": "docs/policy/compass.yaml",
        "confidence": 0.95,
        "created_at": "2026-02-25T18:00:00Z"
    }
)
```

### 8.3 Fallback Documentation

**If Redis/Qdrant unavailable:**
- Create: `docs/tempmemories/iterlog-ST-XXX.md`
- Include: decisions, blockers, learnings, next steps
- Sync to Redis/Qdrant when available

### 8.4 Status File Updates

**Update:** `docs/bmm-workflow-status.yaml`

**Add new epic:**
```yaml
- id: EP-NS-009
  name: Soul/Reflect/Memory Stewardship
  status: in_progress
  story_ids: [ST-SOUL-001, ST-REFLECT-001, ST-MEMORY-002]
  story_count: 3
  story_points: 15
  description: Constitutional governance layer with continuous reflection and automated memory stewardship
  sprint_id: q2-8
```

**Add new stories:**
```yaml
- id: ST-SOUL-001
  title: Soul-Guided Compass Framework
  epic_id: EP-NS-009
  status: in_progress
  story_points: 5
  # ... full story definition
```

---

## 9. Suggested PR Template

### 9.1 PR Title

```
feat(governance): Implement Soul-guided Compass and reflection infrastructure (ST-SOUL-001, ST-REFLECT-001, ST-MEMORY-002)
```

### 9.2 PR Body

```markdown
## Summary
Implements the NS stream Soul/Reflect/Memory stewardship phase:
- Soul-guided Compass with veto capability and appeal workflow
- Continuous reflection loops (micro/meso/macro)
- Automated memory stewardship with promotion rules

## Changes
- New policy files: compass.yaml, reflection_policy.yaml, memory_policy.yaml
- New scripts: compass_gate.py, reflection_runner.py, memory_sweep.py
- CI integration: approval-gate and compass-gate in Woodpecker
- New modules: src/governance/reflection/, src/governance/memory/

## Testing
- [x] 4 test PRs validated (normal, sensitive, compass-veto, appeal)
- [x] Reflection artifacts generated for 3+ stories
- [x] Memory sweep promoted 10+ entries to Qdrant
- [x] All 47 tests passing (15 compass, 16 reflection, 16 memory)

## Deployment
- Gates activate on next CI run
- Policies effective immediately after merge
- Memory sweep runs via cron (daily at 02:00 UTC)

## Verification Commands
```bash
# Test compass gate
python3 scripts/ci/compass_gate.py --test

# Test reflection runner
python3 scripts/ops/reflection_runner.py --story-id=ST-TEST-001 --dry-run

# Test memory sweep
python3 scripts/ops/memory_sweep.py --dry-run
```

Closes: ST-SOUL-001, ST-REFLECT-001, ST-MEMORY-002
```

---

## 10. Reference Documentation

### 10.1 Key Files

| File | Purpose |
|------|---------|
| `docs/bmm-workflow-status.yaml` | Authoritative project status |
| `temp/governance-reflection-memory-compass-suggested-spec.md` | Technical patterns and requirements |
| `AGENTS.md` | Agent role definitions and merge authority |
| `.opencode/skills/chiseai-git-workflow/SKILL.md` | Git workflow guidance |
| `.opencode/skills/chiseai-worker-contracts/SKILL.md` | Worker contract patterns |

### 10.2 Commands Reference

| Command | Purpose | Location |
|---------|---------|----------|
| `chise-iterloop-start` | Start iteration | `.opencode/command/` |
| `chise-iterloop-close` | Close iteration | `.opencode/command/` |
| `chise-claim-ownership` | Claim scope ownership | `.opencode/command/` |
| `chise-precommit-gates` | Validate before PR | `.opencode/command/` |
| `chise-swarm-session` | Session management | `.opencode/command/` |
| `chise-incident-log` | Log incidents | `.opencode/command/` |

### 10.3 Key Terms

| Term | Definition |
|------|------------|
| **Soul-Guided Compass** | Constitutional governance layer with veto capability |
| **COMPASS-VETO** | Label auto-applied to sensitive changes |
| **HUMAN-APPROVED** | Label required to override veto |
| **Micro-reflection** | Per-action reflection (Redis, short TTL) |
| **Meso-reflection** | Per-story reflection (Qdrant if promoted) |
| **Macro-reflection** | Daily/weekly retro with KPI trends |
| **Memory Promotion** | Moving learnings from Redis to Qdrant |
| **3-Agent Consensus** | Unanimous agreement from Critic + SeniorDev + Merlin |

---

## 11. Appendix: Quick Reference

### 11.1 Story ID Reference

| Story | Title | Points | Owner |
|-------|-------|--------|-------|
| ST-SOUL-001 | Soul-Guided Compass Framework | 5 | senior-dev + critic |
| ST-REFLECT-001 | Continuous Reflection Loop Infrastructure | 5 | dev + senior-dev |
| ST-MEMORY-002 | Memory Stewardship Automation | 5 | senior-dev + dev |

**Total:** 3 stories, 15 points

### 11.2 File Path Reference

```
docs/
├── policy/
│   ├── compass.yaml              # ST-SOUL-001
│   ├── human_approval.yaml       # ST-SOUL-001
│   ├── reflection_policy.yaml    # ST-REFLECT-001
│   └── memory_policy.yaml        # ST-MEMORY-002
├── tempmemories/
│   └── iterlog-ST-XXX.md         # Fallback iterlog

scripts/
├── ci/
│   └── compass_gate.py           # ST-SOUL-001
└── ops/
    ├── compass_apply.py          # ST-SOUL-001
    ├── reflection_runner.py      # ST-REFLECT-001
    └── memory_sweep.py           # ST-MEMORY-002

src/governance/
├── reflection/                   # ST-REFLECT-001
│   ├── __init__.py
│   ├── loops.py
│   └── artifacts.py
└── memory/                       # ST-MEMORY-002
    ├── __init__.py
    ├── sweep.py
    └── promotion.py
```

### 11.3 Contact and Escalation

| Role | Responsibility | Escalation Trigger |
|------|---------------|-------------------|
| Worker (you) | Implement stories | Blockers after 5 attempts |
| Jarvis | Orchestrate, coordinate | Scope conflicts, rescheduling |
| Merlin | Merge authority, cleanup | Unresolved blockers |
| Captain Craig | Human approval for sensitive changes | COMPASS-VETO appeal |

---

**Document End**

*This handoff document is ready for execution. Begin with Day 0 Kickoff Checklist (Section 6).*
