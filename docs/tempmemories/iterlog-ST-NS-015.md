---
story_id: ST-NS-015
story_title: Correlation Analysis Engine
epic_id: EP-NS-003
phase: implementation
status: deprecated
started_at: "2026-02-09T00:00:00Z"
completed_at: "2026-02-10T18:00:00Z"
deprecated_note: "⚠️ DEPRECATED: Superseded by ST-NS-015A (Correlation Calculation Engine) and ST-NS-015B (Correlation Risk Integration & Alerts)"
acceptance_criteria:
  - Correlation matrix calculated for all portfolio positions
  - High correlation (>0.7) pairs identified and flagged
  - Correlation-based concentration warnings issued
  - Dynamic correlation updates with market regime changes
  - Integration with position sizing for correlation-adjusted sizing
  - FR-015 is satisfied: Analyze correlations across portfolio positions
key_decisions:
  - Rolling correlation window for dynamic updates
  - Correlation-adjusted sizing to reduce concentration risk
  - Threshold-based alerting for high correlation pairs
learnings:
  - Correlations shift with market regimes - rolling windows essential
  - Correlation-adjusted sizing reduces effective concentration
  - High correlation pairs need special handling in sizing
---

## Incidents
None

## Scope Ownership
- Owner: main
- Status: Merged
