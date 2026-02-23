---
name: chiseai-strategy-dsl-design
description: Design and maintain a constrained Strategy DSL (schema) that supports safe parameter + structure evolution and auditability.
metadata:
  version: "1.1"
  opencode_min_version: "1.1.60"
  author: "ChiseAI Team"
  last_updated: "2026-02-23"
---

# chiseai-strategy-dsl-design

## Goal

Guide the creation/maintenance of a Strategy DSL so the system can evolve strategies safely.

## When To Use

- Designing new strategy configuration schemas.
- Adding mutation operators for strategy evolution.
- Reviewing proposed DSL changes.
- Implementing strategy serialization/deserialization.

## When Not To Use

- Runtime strategy execution (use the DSL, don't modify it).
- Ad-hoc strategy experiments outside the schema.
- One-off strategy variations that won't be reused.
- Manual strategy editing (use DSL tools instead).

## DSL Goals

- Constrain changes to approved modules
- Make diffs readable (config diffs, not arbitrary code)
- Make strategies reproducible and testable
- Support parameter mutations and structural mutations (toggle modules, swap exit logic, add filters)

## Recommended DSL Sections

- metadata (name, version, tags)
- universe (symbols, sessions)
- signals (entry triggers)
- filters (regime, volatility, cooldown, news windows if used)
- exits (stop/take profit/trailing/time-based)
- sizing (risk-per-trade, vol targeting, DD-based scaling)
- execution_policy (order types, retries, min liquidity rules)
- risk_rules (caps and local limits)
- telemetry_tags (for audit logging)

## Mutation Operators (Approved "Moves")

- Parameter: thresholds, lookbacks, cooldowns, risk sizing
- Structural: add/remove a filter; swap entry family; swap exit family; add an ensemble wrapper

## Safety Rules

- Changes must remain inside the schema constraints
- Risk caps are enforced outside the DSL by guardrails
- Any new module requires:
  - unit tests
  - backtest validation harness support
  - documentation entry

## Exit Conditions

- DSL schema documented with all sections.
- Mutation operators enumerated and validated.
- Safety rules enforced at schema level.
- New modules have tests + docs + harness support.

## Troubleshooting/Safety

- **Schema violation**: Reject change, require schema update first.
- **Unknown mutation**: Only approved operators allowed; reject unlisted mutations.
- **Missing tests**: Block new module until tests pass.
- **Risk cap bypass**: Guardrails must enforce caps regardless of DSL content.

## Related Skills

- `chiseai-strategy-cicd-gates` - Uses DSL for strategy evaluation
- `chiseai-risk-audit` - Validates risk rules defined in DSL
- `chiseai-brain-cicd` - May propose DSL mutations

## Related Commands

- `.opencode/command/chise-risk-audit.md` - Validate DSL-based strategies
