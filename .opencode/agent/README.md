# ChiseAI Agent Definitions

This directory contains role definitions for the ChiseAI Agent Swarm.

## Overview

The ChiseAI Agent Swarm is a multi-agent system where different AI agents collaborate to build and maintain the ChiseAI trading platform. Each agent has a specific role, responsibilities, and authority level.

## Agent Roles

### Core Swarm Agents

| Agent             | Role                      | Authority      | Primary Responsibilities                                              |
| ----------------- | ------------------------- | -------------- | --------------------------------------------------------------------- |
| **Aria**          | Product Manager           | Planning       | Story definition, PRD creation, roadmap planning                      |
| **AriaRuntime**   | Product Manager (Runtime) | Planning       | Throughput-optimized orchestration with canonical guardrail parity    |
| **Jarvis**        | Orchestrator              | Coordination   | Story delegation, parallel work coordination, incident management     |
| **JarvisRuntime** | Orchestrator (Runtime)    | Coordination   | Autonomous fast/normal/deep effort routing with strict evidence gates |
| **Merlin**        | Integration Authority     | Merge          | CI diagnosis, merge to main, branch cleanup, exceptional PR recovery  |
| **SeniorDev**     | Senior Developer          | Implementation | Complex feature implementation, architecture decisions                |
| **Dev**           | Developer                 | Implementation | Feature implementation, bug fixes                                     |
| **Quickdev**      | Fast Developer            | Implementation | Quick fixes, documentation, simple features                           |
| **QuickdevFast**  | Ultra-Fast Developer      | Implementation | Trivial mechanical 1SP tasks with maximum throughput                  |
| **Juniordev**     | Junior Developer          | Implementation | Learning, simple tasks, test writing                                  |
| **Critic**        | Quality Assurance         | Review         | Code review, quality gates, validation                                |
| **GitReviewBot**  | Automated Review          | Review         | Automated PR review for STANDARD path                                 |

## Model Policy

- `Aria` stays on Codex.
- All non-Aria agents should prefer MiniMax coding-plan models first, then Z.AI coding-plan models when the role benefits from faster reasoning or review throughput.
- Do not use MIMO models.
- Only the cheapest research/triage lanes may use free OpenCode fallback models.
- The currently documented MiniMax coding-plan models are `MiniMax-M2.7`, `MiniMax-M2.7-highspeed`, `MiniMax-M2.5`, `MiniMax-M2.5-highspeed`, `MiniMax-M2.1`, and `MiniMax-M2`.

### BMAD Framework Agents

| Agent                       | Role             | Purpose                        |
| --------------------------- | ---------------- | ------------------------------ |
| **bmm-pm**                  | Product Manager  | BMAD planning and requirements |
| **bmm-architect**           | Architect        | BMAD architecture design       |
| **bmm-dev**                 | Developer        | BMAD implementation            |
| **bmm-qa**                  | QA Engineer      | BMAD testing and validation    |
| **bmm-analyst**             | Analyst          | BMAD analysis and metrics      |
| **bmm-sm**                  | Scrum Master     | BMAD process facilitation      |
| **bmm-tech-writer**         | Technical Writer | BMAD documentation             |
| **bmm-ux-designer**         | UX Designer      | BMAD user experience           |
| **bmm-quick-flow-solo-dev** | Solo Developer   | Quick BMAD flows               |

### CIS (Creative Intelligence System) Agents

| Agent                           | Role                  | Purpose                         |
| ------------------------------- | --------------------- | ------------------------------- |
| **cis-brainstorming-coach**     | Brainstorming Coach   | Facilitate ideation             |
| **cis-creative-problem-solver** | Problem Solver        | Creative solutions              |
| **cis-design-thinking-coach**   | Design Coach          | Design thinking facilitation    |
| **cis-innovation-strategist**   | Innovation Strategist | Strategic innovation            |
| **cis-presentation-master**     | Presentation Master   | Communication and presentations |
| **cis-storyteller**             | Storyteller           | Narrative and storytelling      |

### Specialized Agents

| Agent                               | Role             | Purpose                 |
| ----------------------------------- | ---------------- | ----------------------- | ---------------------------------------- |
| **bmad-agent-bmad-master**          | BMAD Master      | Expert BMAD guidance    |
| **bmad-agent-bmb-agent-builder**    | Agent Builder    | Build new agents        |
| **bmad-agent-bmb-module-builder**   | Module Builder   | Build system modules    |
| **bmad-agent-bmb-workflow-builder** | Workflow Builder | Build workflows         |
| **bmad-agent-tea-tea**              | TEA Agent        | Trading Execution Agent |
| **Research**                        | Researcher       | Research and analysis   |
| **ResearchFast**                    | Research Triage  | Research                | High-throughput first-pass source triage |
| **WebResearch**                     | Web Researcher   | Web-based research      |

## Agent Selection Matrix

Use this matrix when `jarvis` routes work to fixed-model agents.

| Work Pattern                                                  | Preferred Agent  | Model                                        |
| ------------------------------------------------------------- | ---------------- | -------------------------------------------- |
| Top-level strategy/orchestration                              | `aria`           | `openai/gpt-5.3-codex`                       |
| Top-level strategy/orchestration (runtime profile)            | `aria-runtime`   | `openai/gpt-5.3-codex`                       |
| Critical blockers, CI deep debug, escalation terminal tier    | `merlin`         | `openai/gpt-5.3-codex`                       |
| Orchestration planning (non-Codex default)                    | `jarvis`         | `zai-coding-plan/glm-5.1-thinking`           |
| Orchestration planning (runtime profile)                      | `jarvis-runtime` | `minimax-coding-plan/MiniMax-M2.7`           |
| 4-5SP implementation, complex refactors                       | `senior-dev`     | `zai-coding-plan/glm-5.1-thinking`           |
| 2-3SP implementation                                          | `dev`            | `minimax-coding-plan/MiniMax-M2.7`           |
| 1SP implementation (quality-first)                            | `quickdev`       | `minimax-coding-plan/MiniMax-M2.7-highspeed` |
| Trivial 1SP mechanical throughput (fallback-only, deprecated) | `quickdev-fast`  | `opencode/minimax-m2.5-free`                 |
| Adversarial review / risk challenge                           | `critic`         | `zai-coding-plan/glm-5.0-thinking`           |
| Automated PR review decisions                                 | `git-review-bot` | `zai-coding-plan/glm-5.0-thinking`           |
| Deep synthesis research                                       | `research`       | `minimax-coding-plan/MiniMax-M2.7`           |
| First-pass high-volume source triage                          | `research-fast`  | `opencode/minimax-m2.5-free`                 |
| Web-citation-heavy external research                          | `web-research`   | `zai-coding-plan/glm-5.0-thinking`           |

### Codex Budget Policy

- Reserve Codex for `aria` and `merlin` by default.
- Route routine implementation/research/review to MiniMax/Z.ai agents.
- Escalate to `merlin` when blocker depth or risk justifies premium reasoning.

### Routing Rationale

- Prefer `minimax-coding-plan/MiniMax-M2.7` for implementation-oriented work:
  - `jarvis-runtime`, `dev`
  - broad refactors, multi-file implementation, and routine code execution
- Prefer `minimax-coding-plan/MiniMax-M2.7-highspeed` for small, low-risk 1SP work:
  - `quickdev`
- Prefer `zai-coding-plan/glm-5.1-thinking` for judgment-heavy work:
  - `jarvis`, `senior-dev`, `critic`, `git-review-bot`, `web-research`
  - adversarial review, reasoning-heavy synthesis, and review decisions
- Prefer `opencode/minimax-m2.5-free` only for ultra-low-budget triage:
  - `research-fast`
  - other explicitly cheap fallback lanes when cost matters more than depth

### Canonical Escalation Ladder (Required)

- `quickdev`: max 2 passes on same blocker
- `dev`: max 2 passes on same blocker
- `senior-dev`: max 2 passes on same blocker
- `merlin`: max 3 passes on same blocker
- On unresolved blocker after `merlin` pass 3, return blocker packet to Aria.

### Fast-Agent Deprecation Status

- `quickdev-fast` and `juniordev` are soft-deprecated for default routing.
- Use only as explicit fallback paths when Jarvis decides they are necessary.

## Autonomous PR Pipeline

The ChiseAI Agent Swarm uses a tiered automation pipeline for PR management:

### Three Workflow Paths

1. **SAFE Path** (Auto-Approve)
   - Documentation, comments, docstrings
   - Test-only changes
   - ≤5 files, ≤200 lines
   - Auto-merges in <5 minutes

2. **STANDARD Path** (GitReviewBot)
   - Feature additions, bug fixes
   - 6-15 files, 200-500 lines
   - GitReviewBot review in <12 minutes

3. **COMPLEX Path** (Human Escalation)
   - Infrastructure, security, CI changes
   - > 15 files or >500 lines
   - Requires human review

### Documentation

For detailed information on the autonomous workflow:

- **[Agent Onboarding](../../docs/agent-onboarding/quickstart.md)** - Getting started guide for new agents
- **[Workflow Paths](../../docs/agent-onboarding/workflow-paths.md)** - Detailed workflow path documentation
- **[Best Practices](../../docs/agent-onboarding/best-practices.md)** - Scope ownership and collaboration guidelines
- **[Troubleshooting](../../docs/agent-onboarding/troubleshooting.md)** - Common issues and solutions
- **[Operational Runbook](../../docs/runbooks/agent-autonomous-workflow.md)** - Operations and monitoring procedures

### Quick Reference

#### Claiming Scope Ownership

```python
redis_state_hset(
    name="bmad:chiseai:ownership",
    key="src:your:module",
    value="ST-XXX/agent/timestamp",
    expire_seconds=432000
)
```

#### Checking Ownership

```python
owner = redis_state_hget(name="bmad:chiseai:ownership", key="src:your:module")
if owner and "ST-XXX" not in owner:
    print("STOP - Conflict detected!")
```

#### Worker Completion Report

```yaml
WORKER_COMPLETION_REPORT:
  story_id: "ST-XXX"
  branch: "feature/ST-XXX-description"
  head_sha: "abc123"
  test_summary:
    command: "pytest tests/ -v"
    result: "passed"
    counts: "15 passed, 0 failed"
  blockers: "None"
```

## Merge Authority

### Merlin (exclusive authority):

- Open/update/close PRs
- Merge to `main` in the autonomous PR pipeline
- Handle emergency merge overrides and complex merges
- Run branch cleanup

### Jarvis Orchestrates:

- Delegation to workers
- Handoff to Merlin
- Conflict resolution
- Aria maintains one active Jarvis session at a time; parallelism is worker-level within that session
- Post-branch reconcile loop:
  - Woodpecker status sweep after each push/merge cycle
  - route failed/error PRs for remediation
  - require local `main` sync (`git fetch --prune` + `git pull --ff-only`) before dependent work

### Senior-dev (conditional authority):

- May run manual/non-autonomous merge attempts only when explicitly delegated by Jarvis/Aria

### Workers (All Other Agents):

- Push branches
- Handoff evidence to Jarvis
- **Do NOT** open PRs or merge to main

## Emergency Procedures

### Emergency Stop

Activate emergency stop to disable all automation:

```bash
redis-cli -p 6380 HSET bmad:chiseai:system emergency_stop enabled
```

### Incident Reporting

Log incidents to Redis:

```python
redis_state_rpush(
    name="bmad:chiseai:iterlog:story:ST-XXX:incidents",
    value=json.dumps({
        "type": "ownership_conflict",
        "severity": "P2",
        "description": "What went wrong"
    })
)
```

## Getting Help

- **Scope Conflicts**: Report to Jarvis immediately
- **CI Failures**: See [Troubleshooting](../../docs/agent-onboarding/troubleshooting.md)
- **Merge Conflicts**: See [Troubleshooting](../../docs/agent-onboarding/troubleshooting.md)
- **General Questions**: Ask Jarvis or consult [Quick Start](../../docs/agent-onboarding/quickstart.md)

## See Also

- [AGENTS.md](../../AGENTS.md) - Main agents documentation
- [Skills](../skills/) - Available skills for agents
- [Commands](../command/) - Workflow commands
- [BMM Workflow Status](../../docs/bmm-workflow-status.yaml) - Project status
  Task-size governance for planning:
- Prefer 1SP when safe.
- Use 2-3SP when 1SP is unsafe/infeasible.
- Use 4-5SP only when further split is unsafe.
- Any task >5SP requires explicit Craig approval via Aria before execution.
