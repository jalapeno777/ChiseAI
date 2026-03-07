# Operator Quick Reference

**How to Use:** Match your task intent to trigger phrases below → Load the corresponding skill → Execute suggested command.

---

## Skill Reference Table

### Core Workflow Skills

| Skill | Purpose | Top 3 Trigger Phrases | Next Command/Action |
|-------|---------|----------------------|---------------------|
| `chiseai-git-workflow` | Git operations, branching, PR workflow | "I need to create a branch", "Preparing a PR", "Switching branches for a story" | `chise-swarm-session` (verify) or `chise-precommit-gates` |
| `chiseai-memory-ops` | Redis/Qdrant operations for iteration tracking | "Store iteration state", "Log to iterlog", "Query memory from Redis" | `chise-iterloop-start` or `chise-iterloop-close` |
| `chiseai-validation` | Validation patterns and quality gates | "CI failed", "Run quality gates", "Pre-commit validation" | `chise-precommit-gates` or `chise-ci-root-cause` |
| `chiseai-worker-contracts` | Standardized task contracts for Jarvis delegation | "Delegating to worker agents", "Need a worker contract", "Parallel task assignment" | Draft contract → include in delegation prompt |
| `chiseai-parallel-safety` | Safety patterns for parallel agent execution | "Multiple agents working", "Avoiding scope conflicts", "Claiming file ownership" | `chise-claim-ownership` then `chise-check-ownership` |
| `chiseai-incident-response` | Structured incident logging and post-mortems | "Something broke", "Need to log an incident", "Post-mortem required" | `chise-incident-log` or `chise-postmortem-create` |
| `chiseai-branch-hygiene` | Branch lifecycle management and cleanup | "Too many stale branches", "Cleanup old feature branches", "Branch inventory" | `chise-branch-hygiene-check` |
| `chiseai-workflow-commands` | BMAD workflow command routing | "Which BMAD command for...", "Planning a sprint", "Creating a PRD" | `bmad-help` or specific `bmad-*` command |
| `chiseai-sprint-cleanup` | Repository hygiene before sprint work | "Starting new sprint", "Clean up repo before work", "Reset for sprint" | `chise-sprint-cleanup` |
| `chiseai-metacognition-ops` | Prediction/outcome/calibration loops for decision quality | "Improve Aria/Jarvis learning", "Track confidence accuracy", "Reduce repeated mistakes" | `chise-metacog-start` then `chise-metacog-close` |

### Strategy/Trading Skills

| Skill | Purpose | Top 3 Trigger Phrases | Next Command/Action |
|-------|---------|----------------------|---------------------|
| `chiseai-data-first` | Phase 0 data gathering enforcement | "Need market data first", "Before strategy analysis", "Data requirements for backtest" | Complete Phase 0 checklist in skill |
| `chiseai-risk-audit` | POC-mode risk constraint enforcement | "Check risk limits", "Audit strategy parameters", "Is this degen?" | `chise-risk-audit` |
| `chiseai-strategy-dsl-design` | Strategy DSL schema design | "Design strategy schema", "Add strategy parameter", "Evolve DSL structure" | Follow schema evolution patterns in skill |
| `chiseai-strategy-cicd-gates` | Strategy evaluation and promotion gates | "Promote strategy to paper", "Backtest passed, what next?", "Strategy CI/CD pipeline" | Follow gate sequence: backtest → paper → live |
| `chiseai-paper-trading-canary` | Paper trading validation with trade budget | "Run paper canary", "Validate paper strategy", "Trade budget enforcement" | `chise-paper-canary` |
| `chiseai-turnover-metrics` | Trades/day calculation (avg/p95/max) | "Calculate turnover", "How many trades per day?", "Turnover statistics" | `chise-turnover-report` |
| `chiseai-promotion-packet` | Human-approval promotion packet generation | "Create promotion packet", "Need human approval", "Evidence for promotion" | `chise-promotion-packet` |
| `chiseai-brain-cicd` | Brain versioning, evaluation, shadow testing | "Upgrade agent brain", "Shadow test new brain", "Brain version promotion" | `chise-brain-upgrade-attempt` |

### Infrastructure/Quality Skills

| Skill | Purpose | Top 3 Trigger Phrases | Next Command/Action |
|-------|---------|----------------------|---------------------|
| `chiseai-docker-governance` | Docker networking and container governance | "Create Docker container", "Which network to use?", "Container connectivity" | Use `chiseai` network, add `project=chiseai` label |
| `chiseai-metrics-dashboard` | Grafana dashboard interaction | "Check Grafana metrics", "Dashboard not loading", "View system metrics" | `chise-dashboard-smoke` |
| `chiseai-testing-patterns` | Testing patterns with pytest and coverage | "Write tests for...", "Increase test coverage", "Pytest best practices" | Follow pytest patterns in skill |
| `chiseai-skill-validation` | Skill markdown structure validation | "Validate skill structure", "Check skill compliance", "Skill format check" | Run validation checklist in skill |
| `chiseai-prd-quality` | PRD quality to measurable/traceable spec | "Review PRD quality", "Make requirements measurable", "FR/NFR definition" | Apply PRD quality checklist |
| `python-quality` | Python code quality (black, ruff, pytest) | "Format Python code", "Run Python linter", "Check code quality" | Run repo-configured quality tools |

---

## Overlap/Conflict Handling

When multiple skills could apply:

1. **Load the most specific skill first** — e.g., `chiseai-paper-trading-canary` over `chiseai-validation` for paper trading validation
2. **Complementary skills can be loaded together** — e.g., `chiseai-git-workflow` + `chiseai-memory-ops` for iteration-tracked PR work
3. **Delegation requires contracts** — Always load `chiseai-worker-contracts` when Jarvis delegates to workers
4. **Parallel work requires safety** — Always load `chiseai-parallel-safety` before `chise-claim-ownership`
5. **Incidents take precedence** — If something broke mid-task, switch to `chiseai-incident-response` immediately

---

## High-Frequency Trigger Map

| Agent Intent | Primary Skill to Load |
|--------------|----------------------|
| Starting a new story/task | `chiseai-git-workflow` |
| Editing files | `chiseai-git-workflow` → `chise-swarm-session` |
| Creating a PR | `chiseai-validation` → `chise-precommit-gates` |
| CI failure | `chiseai-validation` → `chise-ci-root-cause` |
| Delegating to workers (Jarvis) | `chiseai-worker-contracts` + `chiseai-parallel-safety` |
| Claiming file ownership | `chiseai-parallel-safety` → `chise-claim-ownership` |
| Something broke | `chiseai-incident-response` → `chise-incident-log` |
| Storing iteration state | `chiseai-memory-ops` → `chise-iterloop-start` |
| Running metacognitive loop | `chiseai-metacognition-ops` → `chise-metacog-start`/`chise-metacog-close` |
| Cleaning up branches | `chiseai-branch-hygiene` → `chise-branch-hygiene-check` |
| Strategy risk check | `chiseai-risk-audit` → `chise-risk-audit` |
| Paper trading validation | `chiseai-paper-trading-canary` → `chise-paper-canary` |
| Creating Docker container | `chiseai-docker-governance` |
| Writing Python tests | `chiseai-testing-patterns` |
| Python code quality | `python-quality` |
| Planning/reviewing PRD | `chiseai-prd-quality` |
| BMAD workflow tasks | `chiseai-workflow-commands` → `bmad-help` |
| Grafana/metrics | `chiseai-metrics-dashboard` → `chise-dashboard-smoke` |

---

## Quick Command Reference

| Category | Commands |
|----------|----------|
| **Iteration** | `chise-iterloop-start`, `chise-iterloop-close` |
| **Metacognition** | `chise-metacog-start`, `chise-metacog-close`, `chise-metacog-weekly` |
| **Ownership** | `chise-claim-ownership`, `chise-check-ownership` |
| **Validation** | `chise-precommit-gates`, `chise-ci-root-cause`, `chise-ci-failure-bundle` |
| **Incidents** | `chise-incident-log`, `chise-postmortem-create` |
| **Branches** | `chise-branch-hygiene-check`, `chise-sprint-cleanup` |
| **Strategy** | `chise-risk-audit`, `chise-paper-canary`, `chise-turnover-report`, `chise-promotion-packet` |
| **Brain** | `chise-brain-upgrade-attempt` |
| **Session** | `chise-swarm-session` |
| **Dashboard** | `chise-dashboard-smoke` |
| **BMAD** | `bmad-help`, `bmad-bmm-*`, `bmad-tea-*`, etc. |

---

*Last updated: 2026-03-07*
