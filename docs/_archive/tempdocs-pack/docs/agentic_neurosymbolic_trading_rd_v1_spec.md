# Agentic Neuro‑Symbolic Trading R&D System — V1 Specification (Backtest → Paper → Human‑Approved Live)

## 1) Summary of what you want (high‑level)
You want a trading system whose AI component can **autonomously improve** (self‑evaluate + self‑evolve) to reach an end goal of:

- **Primary objective:** maximize **net profit** (measured **after fees + modeled slippage**)
- **Secondary objective:** minimize **turnover** (defined as **trades/day**)
- **Tertiary objective:** minimize **drawdown (DD)** *within your existing hard risk caps*

And you want the AI to be allowed to:
- Evolve **parameters and structure** (new filters/modules, different entry/exit/sizing logic)  
…but only deploy changes automatically **up to Paper Trading**.

**Live Trading updates are gated**:
- Only after paper proves the change, AND
- Only after **human approval**.

---

## 2) Core design principles (the “rules of the universe”)
1) **Staged promotion:** Backtest → Paper (canary → full) → Human approval → Live  
2) **Neuro‑symbolic governance:** learned/LLM reasoning proposes; **symbolic constraints** enforce caps, invariants, and promotion rules  
3) **Constrained action space:** the AI can only modify strategies/brains via approved interfaces (DSL/config), never “free‑edit” live behavior  
4) **Auditability:** every change is versioned, reproducible, diffable, and tied to evidence (backtest + paper results)  
5) **Champion/Challenger:** always compare challengers against a champion, keep rollback ready

---

## 3) Terminology (useful labels for docs + agent prompts)
- **Agentic LLMOps / MLOps:** agents that plan tasks, run tools, evaluate results, and iterate
- **Neuro‑symbolic system:** neural/LLM components + symbolic constraints/invariants (risk + promotion gates)
- **Closed‑loop R&D loop:** Observe → Evaluate → Diagnose → Propose → Test → Select → Deploy (to paper) → Monitor
- **Strategy CI/CD:** automated pipeline for building/testing/promoting strategies
- **Champion/Challenger:** current best vs candidates
- **Brain CI/CD (meta‑evolution):** same pipeline concept applied to the *agent “brain” itself* (prompts, roles, policies, tool usage)

---

## 4) Objective + selection policy (lexicographic with a “profit‑close” band)
### 4.1 Hard constraints (non‑negotiable)
You already have these defined in the project:
- DD caps, daily loss caps, leverage/exposure caps, etc.

These must be enforced in:
- Backtests
- Paper trading
- (Eventually) live trading

### 4.2 Lexicographic selection policy (after constraints pass)
1) **Maximize net profit after costs**  
2) If profit is “close” (within **3%**) then prefer:
   1. **Lower turnover** (trades/day)
   2. **Lower operational complexity score** (if tracked; see §7.6)
   3. **Lower DD** (still within caps)

### 4.3 Profit “close” definition (ε = 3%)
Let P be net profit after costs in the evaluation window.

A candidate is “close” if:
- `P_candidate ≥ P_best * (1 - 0.03)`

Example: best = $100k, close = ≥ $97k.

**Important:** Apply the 3% tie‑break logic **on Paper first** (paper is truth), with backtest supporting.

---

## 5) Turnover metric specification (trades/day)
### 5.1 What counts as a “trade”
- Count **filled orders aggregated per unique order_id** (partial fills do not inflate count)
- A trade is any order_id with total filled quantity > 0

### 5.2 Day bucketing
- Use **UTC calendar days** (00:00–23:59 UTC)
- `days` = number of UTC days in the evaluation window with valid market data

### 5.3 Required turnover statistics
Compute all of the following per window:
- `avg_trades_per_day`
- `p95_trades_per_day`
- `max_trades_per_day`

These prevent “average looks fine” but “spike days are chaos.”

---

## 6) Turnover ceilings (starting policy)
You gave a starting ceiling of **20 trades/day**.

Recommended v1 gates:
- **Hard gate:** `avg_trades_per_day ≤ 20`
- **Ops sanity gates:**  
  - `p95_trades_per_day ≤ 30`  
  - `max_trades_per_day ≤ 45`

These are adjustable once you see paper behavior.

---

## 7) V1 “Brain” architecture (recommended)
### 7.1 The V1 brain is a hybrid cognitive architecture
**Recommended core:**
- **LLM Orchestrator (deliberative R&D brain):** proposes candidates, runs experiments, writes reports
- **Symbolic Guardrails Engine:** enforces caps/invariants and promotion gating
- **Strategy DSL + Registry:** keeps strategies constrained, versioned, and diffable

Optional (high leverage, safe neural add‑ons):
- Regime classifier (trend/range/high vol)
- Slippage/fee impact model
- Uncertainty/edge confidence gating

### 7.2 Constrained action space (must‑have)
The AI may only:
- Generate/edit **strategy configs** inside the DSL (parameter + structure mutations)
- Toggle approved modules
- Submit candidates into the pipeline
- Auto‑deploy to **paper only**
- Produce a promotion packet for humans

The AI may NOT:
- Modify live trading directly
- Modify risk caps / promotion rules
- Bypass audit logging

### 7.3 Strategy DSL (the “safe language” for evolution)
Define a schema that includes:
- Signal modules (entry)
- Filters (regime, volatility, cooldowns)
- Exit logic (stop, take profit, time‑based, trailing)
- Sizing (risk per trade, vol targeting, DD scaling)
- Risk rules (per‑trade and per‑day)
- Execution policy references (order types, retry policy)

### 7.4 Strategy Registry (versioning + reproducibility)
For every strategy version store:
- Unique version id
- Config/DSL payload
- Backtest and paper reports
- Diffs vs champion
- Dependencies (data version, code version, feature version)

### 7.5 Brain Registry (meta‑evolution support)
Treat “the brain” as versioned too:
- Role definitions (planner/critic/evaluator)
- Prompt/policy configs
- Allowed tools + action constraints
- Evaluation suite definition
- Diff logs and promotion history

### 7.6 Operational complexity score (recommended, separate from turnover)
Turnover captures cost & churn, but “ops complexity” can be worse than churn.

Track a simple score (start minimal; expand later):
- # modules enabled in the DSL
- # traded symbols
- orders/day variance (spikiness)
- frequency of parameter changes (if strategy adapts internally)

Use it as:
- a tie‑break after turnover, or
- a soft constraint (must be below threshold)

---

## 8) Strategy CI/CD pipeline (Backtest → Paper → Human‑Approved Live)
### 8.1 Stages
1) **Candidate generation:** parameter + structure mutations (in DSL)
2) **Backtest gate:** walk‑forward + stress + fee/slippage sensitivity
3) **Paper canary:** limited scope (small notional / fewer symbols)
4) **Paper full:** expanded scope, longer horizon
5) **Promotion packet:** generated for human review
6) **Live canary (optional):** tiny capital + strict kill switch
7) **Live full:** after continued confirmation

### 8.2 Backtest gate (must include)
- Walk‑forward validation
- Slippage/fee sensitivity sweeps
- Stress tests (high vol, low liquidity, crash days)
- Leakage defenses (purged CV / embargo where applicable)

### 8.3 Paper gate (must include)
- Net profit after costs vs champion
- Turnover stats: avg/p95/max trades/day
- Execution realism: rejects, slippage, fill quality
- Drift checks: input shifts + performance decay alarms

---

## 9) Trade Budgeter (enforceable turnover control)
To make the 20 trades/day ceiling real in paper (and eventually live):
- **Daily trade tokens:** 20
- **Spend rule:** 1 token per filled order_id
- If tokens are low: tighten entry thresholds (only higher‑quality setups)
- If tokens are 0: block new entries; allow exits

This stops “churn monsters” from slipping through.

---

## 10) Brain CI/CD (the system upgrading its own “brain”)
### 10.1 What brain upgrades mean in practice
New “brains” can change:
- planning/critique structure (planner‑critic, debate team, tree search)
- mutation operators (what strategy edits are proposed)
- evaluation strictness (robustness tests, sensitivity checks)
- memory/retrieval policies (what evidence to use)
- tool usage policies (compute budget, experiment scheduling)

### 10.2 Brain evaluation suite (scores the R&D loop)
Score brain versions on:
- **Paper carryover rate:** % of backtest winners that remain good in paper
- **False positives:** backtest wins that die in paper
- **Time‑to‑improvement:** experiments required to beat champion
- **Bias toward low turnover:** does it pick lower trades/day when profit is within 3%?
- **Compute cost:** resources per useful promotion
- **Safety compliance:** never violates constraints; never touches live

### 10.3 Brain promotion
- Candidate brain runs **offline BrainEval**
- Then runs in **shadow mode** (alongside current brain) generating candidates only
- If it wins: produce promotion packet for human approval
- Human approval flips active brain version

### 10.4 Root of trust (should not be self‑modifiable)
Lock down:
- Risk caps / invariants
- Promotion gate logic
- Audit log write path
- Emergency rollback

---

## 11) Brain upgrade cadence controller (your schedule)
Starting cadence:
- **Every 3 days** (Rapid Iteration)

Then transition to:
- Weekly
- Monthly

Recommended transition rules (simple and safe):
- **Rapid → Weekly** when last ~3 attempts show stable KPIs and no critical regressions
- **Weekly → Monthly** after ~6+ weeks stable
- **Snap‑back to Rapid** if drift alerts spike or paper carryover drops

---

## 12) Required artifacts (what every run must output)
### 12.1 Strategy artifacts (every candidate)
- **Strategy Card (1 page):** net profit after costs, DD (within caps), avg/p95/max trades/day, complexity score, where it works/fails
- **Diff vs champion:** what changed (params, modules, logic)
- **Robustness report:** walk‑forward distribution + stress + sensitivity to fees/slippage
- **Paper report:** paper canary/full results + execution stats

### 12.2 Brain artifacts (every candidate brain)
- **BrainSpec:** roles/policies/tool permissions
- **BrainEval report:** KPIs vs current brain
- **Shadow results summary:** candidate quality and paper carryover
- **Promotion packet:** recommended change + evidence + risks

---

## 13) Recommended implementation path (pragmatic build order)
### Phase 0 — Foundations (fast, essential)
- Define **Strategy DSL/schema**
- Implement **append‑only audit logs** for signals/trades/fills
- Implement **Strategy Registry** + versioning
- Implement **Backtest runner interface** (even if backtester already exists)

### Phase 1 — Evaluation hardening
- Walk‑forward and stress test harness
- Fee/slippage sensitivity sweeps
- Implement selection policy (profit first, 3% tie‑break to turnover)

### Phase 2 — Paper staging automation
- Paper canary deployment tooling
- Paper metrics collection (turnover, execution realism)
- Add **Trade Budgeter** enforcement

### Phase 3 — Self‑evolution (parameter + structure)
- Mutation operators (parameter and structural edits)
- Search policies (Bayes opt for params; evolutionary for structure)
- Candidate triage (reject high turnover and fragile strategies early)

### Phase 4 — Brain CI/CD (meta‑evolution)
- Brain registry + BrainEval suite
- Shadow mode brain comparisons
- Cadence controller (every 3 days → weekly → monthly)

---

## 14) What your LLM agent(s) should review, evaluate, and plan
Use this as the planning checklist for the orchestrator:

1) Confirm the Strategy DSL schema and allowed modules
2) Confirm “net profit after costs” definition and cost model (fees + slippage)
3) Implement turnover metrics (avg/p95/max trades/day) exactly as specified
4) Implement turnover gates (avg ≤ 20, p95 ≤ 30, max ≤ 45) + trade budgeter (20 tokens/day)
5) Implement lexicographic selection with ε=3% profit‑close rule
6) Ensure risk caps are enforced at every stage (backtest + paper)
7) Implement Strategy Registry (versioning, diffs, artifact storage)
8) Implement paper canary → paper full automation and monitoring
9) Implement promotion packets and human approval workflow for live
10) Implement Brain Registry + BrainEval (paper carryover, false positives, time‑to‑improvement, compute)
11) Implement cadence controller and transition rules

---

## 15) Open items (to decide later, but not blockers)
- Exact operational complexity score formula (start simple; iterate)
- Paper prove‑out horizons (days/trade count) and promotion thresholds
- Whether to include a small live canary stage before full live
- How aggressively to explore structure mutations vs parameter mutations (compute budget)

---

## 16) Policy snippets (for quick copy/paste)
### Selection policy
```yaml
selection_policy:
  primary_metric: net_profit_after_costs
  profit_epsilon_relative: 0.03

  turnover_metric:
    unit: trades_per_day
    trade_definition: filled_orders_per_unique_order_id
    day_bucket: UTC
    stats: [avg_trades_per_day, p95_trades_per_day, max_trades_per_day]

  turnover_gates:
    hard:
      avg_trades_per_day_max: 20
    ops_sanity:
      p95_trades_per_day_max: 30
      max_trades_per_day_max: 45

  tie_break_when_profit_close:
    - minimize: avg_trades_per_day (paper)
    - minimize: p95_trades_per_day (paper)
    - minimize: max_trades_per_day (paper)
    - minimize: ops_complexity_score
    - minimize: drawdown
```

### Trade budgeter
```yaml
trade_budgeter:
  enabled: true
  daily_trade_tokens: 20
  token_spend_rule: "1 token per filled order_id"
  when_low_tokens:
    tighten_entry_thresholds: true
  when_no_tokens:
    block_new_entries: true
    allow_exits: true
```

### Brain upgrade cadence
```yaml
brain_upgrade_policy:
  phase: rapid
  rapid:
    every_days: 3
    max_candidate_brains_per_attempt: 2
  weekly:
    every_weeks: 1
    max_candidate_brains_per_attempt: 1
  monthly:
    every_months: 1
    max_candidate_brains_per_attempt: 1

  promotion:
    requires_human_approval: true
    auto_deploy_allowed_to: paper_only
```
