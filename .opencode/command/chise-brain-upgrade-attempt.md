---
name: "chise-brain-upgrade-attempt"
description: "ChiseAI: attempt a brain upgrade (BrainEval + shadow comparison) and generate a promotion packet if it wins."
disable-model-invocation: true
---
Attempt one Brain CI/CD cycle.

Rules:
- Follow the `chiseai-brain-cicd` skill.
- Do not modify risk caps, promotion gates, or live trading.
- Generate at most 2 candidate BrainSpecs.

Steps:
1) Diagnose current bottleneck (false positives, slow time-to-improvement, turnover bias issues).
2) Propose BrainSpec vNext changes (roles/policies/tool usage), keeping action constraints intact.
3) Run BrainEval comparing vCurrent vs vNext on recent history.
4) Run vNext in shadow mode generating candidates only; compare candidate quality and paper carryover proxy.
5) If vNext wins, generate a promotion packet for human approval; otherwise log “no change”.

If $ARGUMENTS is provided, treat it as the primary KPI to optimize first (e.g., "paper_carryover_rate").
