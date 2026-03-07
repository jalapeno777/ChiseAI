# ChiseAI Metacognition Integration Blueprint

Status: proposed-for-implementation  
Owner: Craig / Aria / Jarvis / Merlin  
Date: 2026-03-07

## 1) Executive Summary

This blueprint integrates metacognition into the existing OpenCode + BMAD network so Aria/Jarvis improve decision quality over time using measurable prediction-to-outcome loops.

Core objective:
- reduce repeated mistakes and avoidable regressions
- improve confidence calibration
- increase safe autonomy while preserving capital-safety constraints

This is aligned with product goals in:
- `docs/product-brief.md` (autonomous-by-default, risk invariants, zero kill-switch target)
- `docs/prd.md` (FR-017/018/019 learning+calibration, FR-DEV-001..005 autonomous engineering discipline)

## 2) Why This Is Needed

Current state already has strong primitives:
- `INSIGHT_PACKET` + `ARIA_DECISION`
- iterlogs + structured issues
- incident/postmortem flow
- reflection scripts and weekly rollups

Gap:
- no mandatory, standardized prediction artifact at story start
- no mandatory predicted-vs-actual calibration artifact at story close
- no first-class metacog compliance validator in precommit workflow
- story-id regex in reflection policy excluded non-`ST-*` IDs

Risk if not addressed:
- confidence drift and repeated failure signatures
- hidden process regressions across stories
- weaker autonomy expansion decisions (insufficient evidence)

## 3) Design Principles

1. Data-first and measurable:
- every prediction must define measurable expected metrics.

2. Lightweight at story level:
- short cards, not long essays.

3. Enforcement through commands and gates:
- workflow should fail fast if artifacts are missing.

4. Dual memory model:
- Redis for operational/ephemeral state.
- Qdrant for durable semantic learning.

5. Risk-tier strictness:
- all stories require artifacts; stricter review for P0/P1/high-risk/global-lock.

## 4) Integrated Workflow (OpenCode/BMAD)

## 4.1 Start-of-story

Required command sequence:
1. `chise-iterloop-start`
2. `chise-metacog-start`

`chise-metacog-start` creates `## Metacognitive Predictions` with:
- predicted_outcome
- predicted_risks
- confidence
- verification_plan
- expected_metrics

## 4.2 During execution (Aria/Jarvis)

Aria/Jarvis continue standard protocol (`INSIGHT_PACKET`, `ARIA_DECISION`), but must anchor recommendations against:
- start prediction assumptions
- known prevention rules from memory
- measurable expected outcome deltas

## 4.3 Close-of-story

Required command sequence:
1. `chise-metacog-close`
2. `chise-iterloop-close`

`chise-metacog-close` creates:
- `## Metacognitive Outcomes`
- `## Metacognitive Calibration`

Then validate:
- `python3 scripts/validation/validate_metacog_compliance.py --story-id=<id> --strict`

## 4.4 Weekly loop

Command:
- `chise-metacog-weekly`

Purpose:
- trend calibration quality
- tune autonomy thresholds using evidence
- detect consistent degradation early

## 5) Memory Integration

## 5.1 Redis keys

- `bmad:chiseai:metacog:prediction:story:<story_id>`
- `bmad:chiseai:metacog:outcome:story:<story_id>`
- `bmad:chiseai:metacog:calibration:agent:<agent>:weekly:<yyyy-Www>`
- `bmad:chiseai:metacog:prevention_rules`

TTL policy:
- prediction/outcome: 30 days
- weekly calibration: 90 days
- prevention rules: 90 days

Canonical note:
- This blueprint is the source-of-truth TTL policy for metacognition artifacts; skills/commands must match these values.

## 5.2 Qdrant collection

Collection:
- `ChiseAI_metacognition`

Required payload fields:
- project, story_id, agent, decision_type
- predicted_risk, actual_outcome, confidence
- calibration_delta, prevention_rule, scope_context

Fallback:
- `docs/tempmemories/*` with `needs_manual_qdrant_import: true`

## 6) Skills and Commands Added

New skill:
- `.opencode/skills/chiseai-metacognition-ops/SKILL.md`

New commands:
- `.opencode/command/chise-metacog-start.md`
- `.opencode/command/chise-metacog-close.md`
- `.opencode/command/chise-metacog-weekly.md`

Updated commands:
- `.opencode/command/chise-iterloop-start.md`
- `.opencode/command/chise-iterloop-close.md`
- `.opencode/command/chise-precommit-gates.md`

New validator:
- `scripts/validation/validate_metacog_compliance.py`

Policy fix:
- `docs/policy/reflection_policy.yaml` story-id pattern now accepts `ST|CH|FT|REWARD|REPO|SAFETY|BRANCH|PAPER|RECON`

## 7) Additional Components (Plugin/Adjustment Recommendations)

Not required for initial rollout:
- no plugin is mandatory to start; commands + validator + memory schema are sufficient.

Recommended next components:
1. Metacog score plugin:
- computes rolling calibration error and decision-quality index automatically.

2. Metacog retrieval plugin:
- injects top 3 relevant prevention rules and past misses into planning prompts.

3. Metacog guard plugin:
- blocks close/merge if prediction/outcome/calibration artifacts are missing for required stories.

4. Grafana panel additions:
- calibration trend by agent
- prevention-rule hit rate
- repeat-fingerprint rate

## 8) Quantification Framework (How We Prove This Helps)

Use a 4-week baseline, then weekly trend comparison.

Primary KPIs:
1. Repeat issue fingerprint rate (down is good)
2. Reopen/regression rate (down is good)
3. Median cycle time (down is good, without quality loss)
4. Confidence calibration error (down is good)
5. Prevention-rule hit rate (up is good)
6. P0/P1 incident frequency (down is good)

Formula and threshold table:

| KPI | Formula | Warn Threshold | Expansion Threshold | Owner |
|---|---|---|---|---|
| Calibration error (ECE) | `sum_i((n_i/N) * abs(acc_i - conf_i))` | `>0.10` | `<=0.08` for 2 weeks | Aria |
| Repeat fingerprint rate | `repeat_fingerprints / total_fingerprints` | no weekly drop vs baseline | `>=15%` reduction vs 4-week baseline | Jarvis |
| Reopen/regression rate | `reopened_or_regressed / shipped_items` | `>8%` | `<=5%` for 2 weeks | Merlin |
| Median cycle time guardrail | `median(close_ts - start_ts)` | `>10%` degradation vs baseline | must not degrade while quality is flat/worse | Aria |
| Prevention-rule hit rate | `incidents_prevented_by_rule / total_incidents` | `<20%` after initial rollout | `>=35%` sustained trend | Jarvis |
| P0/P1 incident frequency | `p0_p1_count / week` | any upward 2-week trend | non-increasing for 4 weeks | Craig |

Secondary product-aligned KPIs:
- kill-switch event count
- drawdown breach incidents
- paper/live stability days
- Sharpe/Sortino stability trend

Decision policy:
- If incident rate decreases and calibration improves for 2 consecutive weeks: expand autonomy envelope cautiously.
- If calibration worsens and repeat incidents rise for 2 consecutive weeks: tighten thresholds and escalate to Aria/Craig.

Review cadence:
- Weekly operational review: Aria + Jarvis.
- Monthly policy retune: Aria + Merlin with Craig sign-off.
- Quarterly threshold recalibration: Craig authority.

Weekly command output schema (`chise-metacog-weekly`):
```yaml
week_id: "YYYY-Www"
generated_at_utc: "ISO8601"
decision: "NO_CHANGE|TIGHTEN_AUTONOMY_THRESHOLDS|EXPAND_AUTONOMY_ENVELOPE"
kpis:
  ece: 0.0
  repeat_fingerprint_rate: 0.0
  reopen_regression_rate: 0.0
  median_cycle_time_hours: 0.0
  prevention_rule_hit_rate: 0.0
  p0_p1_incident_count: 0
baseline_comparison:
  ece_delta: 0.0
  repeat_rate_delta_pct: 0.0
  reopen_rate_delta_pct: 0.0
  cycle_time_delta_pct: 0.0
evidence_links:
  - "<path-or-url>"
recommended_actions:
  - "<action>"
owner: "aria|jarvis|merlin"
```

## 9) Rollout Plan

Phase A (now):
- deploy skill + commands + validator + policy fix + docs.

Phase B (1-2 weeks):
- enforce strict metacog compliance for active stories in precommit/CI paths.

Phase C (2-4 weeks):
- add dashboards and retrieval automation.
- evaluate plugin need based on manual burden.

## 10) Risks and Mitigations

Risk: process overhead slows throughput.  
Mitigation: keep cards compact and template-driven.

Risk: low-quality artifacts (box-checking).  
Mitigation: strict field validation + critic audit + weekly trend checks.

Risk: drift between docs and implementation.  
Mitigation: keep command definitions canonical and validate in precommit.

Risk: over-tightening autonomy due to short-term noise.  
Mitigation: use 2-week sustained trend criteria before policy shifts.

## 11) Definition of Done for This Integration

1. Metacog skill and commands exist and are discoverable.
2. Iterloop start/close reference metacog commands.
3. Precommit supports metacog compliance validation.
4. Reflection policy accepts all valid Chise story-id formats.
5. Weekly reporting path exists (`chise-metacog-weekly`).
6. Aria receives formal review prompt and implementation recommendations.
