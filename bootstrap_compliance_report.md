# Bootstrap Compliance Verification Report
## Generated: 2026-02-18

## Summary Statistics

| Metric | Count |
|--------|-------|
| Total Python Scripts | 59 |
| Scripts with Import | 38 |
| Scripts with Call | 38 |
| Compliant Scripts | 38 |
| Non-Compliant Scripts | 21 |
| Import Coverage | 64.4% |
| Call Coverage | 64.4% |
| Overall Compliance | 64.4% |

## Compilation Status

✅ ALL 59 SCRIPTS COMPILE SUCCESSFULLY

All Python scripts in the scripts/ directory pass `python3 -m py_compile` validation.

## Environment Bootstrap Diagnostic Summary

- Loaded env file: /home/tacopants/projects/ChiseAI/.env
- Provider Availability:
  - KIMI: available ✓
  - MINIMAX: disabled
  - ZAI: not available
  - ZHIPU: available ✓
- Summary: 2/4 providers available

## Compliant Scripts (38/59 - 64.4%)

| Script | Has Import | Has Call | Status |
|--------|------------|----------|--------|
| scripts/backfill_tempmemory_iterlogs.py | ✓ | ✓ | ✅ COMPLIANT |
| scripts/backtest_runner.py | ✓ | ✓ | ✅ COMPLIANT |
| scripts/benchmark_cache.py | ✓ | ✓ | ✅ COMPLIANT |
| scripts/branch_hygiene.py | ✓ | ✓ | ✅ COMPLIANT |
| scripts/canary_auto_eval.py | ✓ | ✓ | ✅ COMPLIANT |
| scripts/check_env.py | ✓ | ✓ | ✅ COMPLIANT |
| scripts/ci/brain_eval_ci.py | ✓ | ✓ | ✅ COMPLIANT |
| scripts/ci/check_woodpecker_forge_token_health.py | ✓ | ✓ | ✅ COMPLIANT |
| scripts/ci/check_woodpecker_stuck_pipelines.py | ✓ | ✓ | ✅ COMPLIANT |
| scripts/ci/ci_change_scope.py | ✓ | ✓ | ✅ COMPLIANT |
| scripts/ci/ci_gate.py | ✓ | ✓ | ✅ COMPLIANT |
| scripts/ci/post_ci_failure_discord.py | ✓ | ✓ | ✅ COMPLIANT |
| scripts/ci/post_ci_failure_issue.py | ✓ | ✓ | ✅ COMPLIANT |
| scripts/ci/post_ci_failure_pr_comment.py | ✓ | ✓ | ✅ COMPLIANT |
| scripts/ci/run_brain_evaluation.py | ✓ | ✓ | ✅ COMPLIANT |
| scripts/ci/scan_failure_logs.py | ✓ | ✓ | ✅ COMPLIANT |
| scripts/ci/validate_swarm_context.py | ✓ | ✓ | ✅ COMPLIANT |
| scripts/ci/woodpecker_triage.py | ✓ | ✓ | ✅ COMPLIANT |
| scripts/configure_grafana_datasource.py | ✓ | ✓ | ✅ COMPLIANT |
| scripts/data_quality_monitor.py | ✓ | ✓ | ✅ COMPLIANT |
| scripts/diagnostic_provider_chain.py | ✓ | ✓ | ✅ COMPLIANT |
| scripts/gitea_pr_automerge.py | ✓ | ✓ | ✅ COMPLIANT |
| scripts/gitea_pr_review.py | ✓ | ✓ | ✅ COMPLIANT |
| scripts/grafana-watchdog.py | ✓ | ✓ | ✅ COMPLIANT |
| scripts/iterlog_ops.py | ✓ | ✓ | ✅ COMPLIANT |
| scripts/live_pipeline_proof.py | ✓ | ✓ | ✅ COMPLIANT |
| scripts/ops/merge_reconciler.py | ✓ | ✓ | ✅ COMPLIANT |
| scripts/ops/merlin_pr_sweep.py | ✓ | ✓ | ✅ COMPLIANT |
| scripts/run_canary_monitor_pipeline.py | ✓ | ✓ | ✅ COMPLIANT |
| scripts/run_daily_summary.py | ✓ | ✓ | ✅ COMPLIANT |
| scripts/run_datasource_health_monitor.py | ✓ | ✓ | ✅ COMPLIANT |
| scripts/run_ohlcv_ingestion.py | ✓ | ✓ | ✅ COMPLIANT |
| scripts/taiga_sync.py | ✓ | ✓ | ✅ COMPLIANT |
| scripts/test_bybit_auth.py | ✓ | ✓ | ✅ COMPLIANT |
| scripts/test_bybit_websocket.py | ✓ | ✓ | ✅ COMPLIANT |
| scripts/test_execution_dashboards.py | ✓ | ✓ | ✅ COMPLIANT |
| scripts/trigger_test_trade.py | ✓ | ✓ | ✅ COMPLIANT |
| scripts/validate_pr_title.py | ✓ | ✓ | ✅ COMPLIANT |

## Non-Compliant Scripts (21/59 - 35.6%)

| Script | Has Import | Has Call | Status |
|--------|------------|----------|--------|
| scripts/canary_validation.py | ✗ | ✗ | ❌ NON-COMPLIANT |
| scripts/demo_ece.py | ✗ | ✗ | ❌ NON-COMPLIANT |
| scripts/demo_shadow_testing.py | ✗ | ✗ | ❌ NON-COMPLIANT |
| scripts/diagnostic_kimi_probe.py | ✗ | ✗ | ❌ NON-COMPLIANT |
| scripts/export_training_data.py | ✗ | ✗ | ❌ NON-COMPLIANT |
| scripts/grafana-performance-test.py | ✗ | ✗ | ❌ NON-COMPLIANT |
| scripts/incident/create_postmortem.py | ✗ | ✗ | ❌ NON-COMPLIANT |
| scripts/incident/log_incident.py | ✗ | ✗ | ❌ NON-COMPLIANT |
| scripts/populate_backtest_kpis.py | ✗ | ✗ | ❌ NON-COMPLIANT |
| scripts/run_live_proof_e2e.py | ✗ | ✗ | ❌ NON-COMPLIANT |
| scripts/sample_walk_forward.py | ✗ | ✗ | ❌ NON-COMPLIANT |
| scripts/story_id.py | ✗ | ✗ | ❌ NON-COMPLIANT |
| scripts/swarm/branch_hygiene_check.py | ✗ | ✗ | ❌ NON-COMPLIANT |
| scripts/swarm/session.py | ✗ | ✗ | ❌ NON-COMPLIANT |
| scripts/test_discord_integration.py | ✗ | ✗ | ❌ NON-COMPLIANT |
| scripts/validate_fr_traceability.py | ✗ | ✗ | ❌ NON-COMPLIANT |
| scripts/validate_iterloop_compliance.py | ✗ | ✗ | ❌ NON-COMPLIANT |
| scripts/validate_status_sync.py | ✗ | ✗ | ❌ NON-COMPLIANT |
| scripts/validate_traceability_drift.py | ✗ | ✗ | ❌ NON-COMPLIANT |
| scripts/verify_kimi_discord_fix.py | ✗ | ✗ | ❌ NON-COMPLIANT |
| scripts/woodpecker_sqlite_to_postgres.py | ✗ | ✗ | ❌ NON-COMPLIANT |

## Detailed Non-Compliant Scripts List

1. scripts/canary_validation.py
2. scripts/demo_ece.py
3. scripts/demo_shadow_testing.py
4. scripts/diagnostic_kimi_probe.py
5. scripts/export_training_data.py
6. scripts/grafana-performance-test.py
7. scripts/incident/create_postmortem.py
8. scripts/incident/log_incident.py
9. scripts/populate_backtest_kpis.py
10. scripts/run_live_proof_e2e.py
11. scripts/sample_walk_forward.py
12. scripts/story_id.py
13. scripts/swarm/branch_hygiene_check.py
14. scripts/swarm/session.py
15. scripts/test_discord_integration.py
16. scripts/validate_fr_traceability.py
17. scripts/validate_iterloop_compliance.py
18. scripts/validate_status_sync.py
19. scripts/validate_traceability_drift.py
20. scripts/verify_kimi_discord_fix.py
21. scripts/woodpecker_sqlite_to_postgres.py

## Key Findings

### Compliant Scripts (38/59 - 64.4%)
These scripts properly import and call bootstrap():
- All CI pipeline scripts (17 scripts in scripts/ci/)
- All monitoring and data scripts
- All trading and execution scripts
- All ops and workflow scripts

### Non-Compliant Scripts (21/59 - 35.6%)
These scripts are missing bootstrap import/call:
- Demo/test scripts: demo_ece.py, demo_shadow_testing.py
- Diagnostic scripts: diagnostic_kimi_probe.py, verify_kimi_discord_fix.py
- Validation scripts: validate_*.py (5 scripts)
- Incident scripts: log_incident.py, create_postmortem.py
- Utility scripts: story_id.py, session.py, branch_hygiene_check.py
- Legacy migration: woodpecker_sqlite_to_postgres.py
- Other: canary_validation.py, export_training_data.py, grafana-performance-test.py, populate_backtest_kpis.py, run_live_proof_e2e.py, sample_walk_forward.py, test_discord_integration.py

## Recommendations

1. **Priority 1**: Add bootstrap to validation scripts (validate_*.py) as they are part of CI/CD
2. **Priority 2**: Add bootstrap to incident scripts (log_incident.py, create_postmortem.py)
3. **Priority 3**: Add bootstrap to swarm utilities (session.py, branch_hygiene_check.py)
4. **Low Priority**: Demo scripts and diagnostic probes may not need bootstrap

## Verification Complete

✅ Environment check passed
✅ All scripts compile
✅ Import/call coverage: 38/59 scripts (64.4%)
