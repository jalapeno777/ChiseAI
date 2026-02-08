---
name: chiseai-data-first
description: Enforce Phase 0 data gathering completion before analysis, modeling, or strategy recommendations.
metadata:
  version: "1.0"
  opencode_min_version: "1.1.48"
---

# chiseai-data-first

## Goal

Avoid building analysis on incomplete or low-quality data foundations.

## When To Use

- Any analysis, modeling, backtesting, or strategy generation work.
- Any time the swarm is tempted to "just infer" without verified data.

## Rules

- Finish Phase 0 data gathering before deeper analysis.
- If data is incomplete, mark the story blocked and specify exactly what data is missing.
- Record data sources and data-quality assumptions in Redis iterlog.

