# Migration Baseline Inventory

Date: 2026-05-25
Story: REPO-MIGRATION-001

## Branch List

```
+ PAPER-FIX-005b-critic-remediation
  feature/CLEANUP-CONSUMER-HEALTH
  feature/CLEANUP-SLTP-RACE-LOCK
+ feature/CLEANUP-STALE-PRICES
  feature/G-EXIT-24H-canary-pnl-instrumentation
+ feature/PAPER-THRESHOLD-FIX-consumer-threshold-fix
  feature/PT-FIX-1a-live-fill-prices
  feature/PT-FIX-1b-ohlcv-ingestion
  feature/PT-FIX-1c-confidence-threshold
+ feature/PT-FIX-2-close-at-market
+ feature/PT-FIX-3-sltp-monitoring
  feature/PT-FIX-4-documentation
+ feature/R2A-cron-restart
+ feature/R2A-symbol-cooldown-gate
  feature/ST-MVP-002-dashboard-redis-host
+ feature/ST-MVP-003-validation-bug-fix
+ feature/ST-MVP-005-heartbeat-degradation
+ feature/ST-MVP-006-zero-signal-alerts
+ feature/ST-MVP-007-llm-redundancy
  feature/ST-MVP-009-strategy-protocol-registry
  feature/ST-MVP-010-ict-confluence-strategy
  feature/ST-MVP-011-backtest-adapter
* main
  remotes/origin/HEAD -> origin/main
  remotes/origin/feature/PT-FIX-1a-live-fill-prices
  remotes/origin/feature/PT-FIX-1b-ohlcv-ingestion
  remotes/origin/feature/PT-FIX-1c-confidence-threshold
  remotes/origin/feature/PT-FIX-2-close-at-market
  remotes/origin/main
```

## Tag List

```
archive/ST-CI-001-phase0-enable-trigger
archive/ST-KPI-CRON-001-woodpecker-setup
archive/ST-KPI-FIX-002-handoff-addendum
archive/ST-MEMORY-INGEST-001-scheduler-integration
archive/feature-ST-MEMORY-INGEST-002-grafana-final-old
backup/2026-02-17/feature/PAPER-LOOP-001-e2e
backup/2026-02-17/feature/PAPER-LOOP-001-grafana
backup/2026-02-17/feature/PAPER-LOOP-001-loop
backup/2026-02-17/feature/PAPER-LOOP-001-orchestrator
backup/2026-02-17/feature/PAPER-LOOP-001-order-simulator
backup/2026-02-17/feature/PAPER-LOOP-001-position-tracker
backup/2026-02-17/feature/PAPER-LOOP-001-risk-enforcer
backup/2026-02-17/feature/PAPER-LOOP-001-workflow-update
backup/2026-02-17/feature/RECON-20260217-postmortems
backup/2026-02-17/feature/RECON-20260217-workflow-sync
backup/2026-02-17/feature/ST-NS-019-calibration-data-collector
backup/2026-02-17/feature/ST-NS-019-threshold-optimizer
backup/2026-02-17/feature/ST-NS-020-dataset-exporter
backup/2026-02-17/feature/ST-NS-020-feature-extraction
backup/2026-02-17/feature/ST-NS-020-training-data-schema
backup/2026-02-17/feature/ST-NS-025-grafana-optimization
backup/2026-02-17/feature/ST-NS-025-lazy-loading
backup/2026-02-17/feature/ST-NS-025-query-caching
backup/2026-02-17/feature/ST-NS-026-async-pipeline
backup/2026-02-17/feature/ST-NS-026-connection-pooling
backup/2026-02-17/feature/fix/security-scan-bandit-issues
backup/archive-terraform-apply-4c4543d
backup/archive-terraform-audit-3bb18e4
backup/dirty-snapshot-20260309
backup/pre-cleanup-20260309
backup/stash-20260309-0
backup/stash-20260309-1
backup/stash-20260309-2
backup/stash-20260309-3
backup/stash-20260309-4
backup/stash-20260309-5
backup/test-temp-d884a35
cleanup-pre-20260309-120951
cleanup-pre-20260309-121025
cleanup-pre-20260309-121025
cleanup-pre-20260314-112314
cleanup-preflight-2026-03-19
safety/pre-cleanup-20260307-125351/branch-backup-pre-cleanup-20260307-125351-detached
safety/pre-cleanup-20260307-125351/branch-cleanup-SESSION-CLEANUP-001-evidence
safety/pre-cleanup-20260307-125351/branch-cleanup-SESSION-CLEANUP-001-final
safety/pre-cleanup-20260307-125351/branch-feature-BRANCH-HYGIENE-001-yaml-fix
safety/pre-cleanup-20260307-125351/branch-feature-LLM-PROVIDER-FIX-001-ADAPTER-phase-a
safety/pre-cleanup-20260307-125351/branch-feature-LLM-PROVIDER-FIX-001-E2E-phase-e
safety/pre-cleanup-20260307-125351/branch-feature-LLM-PROVIDER-FIX-001-LATENCY-phase-d
safety/pre-cleanup-20260307-125351/branch-feature-LLM-PROVIDER-FIX-001-LOCKIN-phase-c
safety/pre-cleanup-20260307-125351/branch-feature-LLM-PROVIDER-FIX-002-docs
safety/pre-cleanup-20260307-125351/branch-feature-LLM-PROVIDER-FIX-002-endpoint-correction
safety/pre-cleanup-20260307-125351/branch-feature-PAPER-CANARY-COHERENT-003-llm-timeout
safety/pre-cleanup-20260307-125351/branch-feature-PAPER-LLM-DIAG-001-config-audit
safety/pre-cleanup-20260307-125351/branch-feature-PAPER-LLM-DIAG-001-signal-path
safety/pre-cleanup-20260307-125351/branch-feature-PAPER-LLM-TIMEOUT-001-e2e-validation
safety/pre-cleanup-20260307-125351/branch-feature-ST-DISCORD-NOTIFY-001-runbook
safety/pre-cleanup-20260307-125351/branch-feature-ST-KIMI-ADAPTER-002-coding-plan-endpoint
safety/pre-cleanup-20260307-125351/branch-feature-ST-REFLECT-RUNTIME-001-docker-scheduler
safety/pre-cleanup-20260307-125351/branch-fix-E2E-BYBIT-001-connector-method
safety/pre-cleanup-20260307-125351/branch-main
safety/pre-cleanup-20260307-125351/branch-pr-393-temp
safety/pre-cleanup-20260307-125351/branch-safety-SAFETY-001-timeout-fix-2026-03-05
safety/pre-cleanup-20260307-125351/head
safety/pre-cleanup-20260307-125351/orig-head
safety/pre-cleanup-20260307-125351/rebase-onto
safety/pre-cleanup-20260307-125351/rebase-orig-head
safety/pre-cleanup-20260307-125351/wt-1-home-tacopants-projects-ChiseAI
safety/pre-cleanup-20260307-125351/wt-10-tmp-worktrees-PAPER-LLM-DIAG-001-quickdev
safety/pre-cleanup-20260307-125351/wt-11-tmp-worktrees-PAPER-LLM-DIAG-001-signal-path
safety/pre-cleanup-20260307-125351/wt-12-tmp-worktrees-ST-KIMI-ADAPTER-002-ST-KIMI-ADAPTER-002-senior-dev
safety/pre-cleanup-20260307-125351/wt-13-tmp-worktrees-ST-REFLECT-RUNTIME-001-quickdev
safety/pre-cleanup-20260307-125351/wt-14-tmp-worktrees-yaml-fix-BRANCH-HYGIENE-001-quickdev
safety/pre-cleanup-20260307-125351/wt-2-tmp-worktrees-E2E-BYBIT-001-fix
safety/pre-cleanup-20260307-125351/wt-3-tmp-worktrees-LLM-PROVIDER-FIX-001-ADAPTER-senior-dev
safety/pre-cleanup-20260307-125351/wt-4-tmp-worktrees-LLM-PROVIDER-FIX-001-phase-c
safety/pre-cleanup-20260307-125351/wt-5-tmp-worktrees-LLM-PROVIDER-FIX-001-phase-d-LLM-PROVIDER-FIX-001-LATENCY-senior-dev
safety/pre-cleanup-20260307-125351/wt-6-tmp-worktrees-LLM-PROVIDER-FIX-001-phase-e-LLM-PROVIDER-FIX-001-E2E-senior-dev
safety/pre-cleanup-20260307-125351/wt-7-tmp-worktrees-LLM-PROVIDER-FIX-002-docs-LLM-PROVIDER-FIX-002-quickdev
safety/pre-cleanup-20260307-125351/wt-8-tmp-worktrees-LLM-PROVIDER-FIX-002-endpoints
safety/pre-cleanup-20260307-125351/wt-9-tmp-worktrees-PAPER-CANARY-COHERENT-003-senior-dev-PAPER-CANARY-COHERENT-003-senior-dev
safety/pre-cleanup-20260308-171202
safety/pre-remediation-2026-02-27
```

## File Count

```
6010
```

## Last 10 Commits on Main

```
c0351cdf0 fix(opencode): enforce worker dispatch in Jarvis execution phase
d87b84223 fix(opencode): stabilize Aria→Jarvis execution delegation lane
7edce5908 fix(opencode): correct task permission routing and rule order for Aria/Jarvis
3fc5e9a4a Merge branch 'feature/ST-STATUS-UPDATE-20260511': status update for MVP+canary+Redis migration
1355defa8 ST-STATUS-UPDATE-20260511: update project status for MVP+canary reset+Redis migration
f5d8033d1 docs: restart canary Day-0 to May 11 after mock price elimination (FIX-MOCK-PRICE)
432629699 fix(trading): remove hardcoded $50K BTC price fallback to prevent mock data injection (FIX-MOCK-PRICE)
6c370d5cb fix: change Redis port from 6380 to 6379 across infrastructure config (FIX-REDIS-GRAFANA-PORTS)
9075865d2 Merge pull request 'REPO-AUTO-PR-001 feature/CLEANUP-CONSUMER-HEALTH' (#1115) from feature/CLEANUP-CONSUMER-HEALTH into main
e1162910d fix(tests): remove stale symbol_throttle_seconds + apply black formatting (CLEANUP-CONSUMER-HEALTH)
```

## Tracked Secret-Adjacent Files

- infrastructure/.env tracked: **NO** (no output from git ls-files)
- terraform.tfstate tracked: **NO** (no output from grep)

## CI Config State

```yaml
when:
  event:
    - pull_request
    - manual
clone:
  git:
    image: woodpeckerci/plugin-git
    settings:
      remote:
        from_secret: gitea_clone_url
steps:
  swarm-context:
    pull: false
    image: chiseai-ci-tools:py311-20260423
    environment:
      CI_STATUS_DIR: /woodpecker/ci-status/${CI_PIPELINE_NUMBER}
    commands:
      - |
        set -euo pipefail
        mkdir -p "$${CI_STATUS_DIR}"
        set +e
        (
          set -euo pipefail
          python3 scripts/ci/validate_swarm_context.py
        ) > "$${CI_STATUS_DIR}/swarm-context.log" 2>&1
        code=$?
        cat "$${CI_STATUS_DIR}/swarm-context.log"
        echo "$code" > "$${CI_STATUS_DIR}/swarm-context.status"
        exit 0
  cross-branch-verify:
    pull: false
    image: chiseai-ci-tools:py311-20260423
    environment:
      CI_STATUS_DIR: /woodpecker/ci-status/${CI_PIPELINE_NUMBER}
    commands:
      - |
        set -euo pipefail
        mkdir -p "$${CI_STATUS_DIR}"
        set +e
        {
          set -euo pipefail
          BRANCH="$${CI_COMMIT_BRANCH:-$${WOODPECKER_COMMIT_BRANCH:-}}"
          EVENT="$${CI_BUILD_EVENT:-$${WOODPECKER_BUILD_EVENT:-$${WOODPECKER_EVENT:-$${CI_PIPELINE_EVENT:-}}}}"
          if [ "$${EVENT}" != "push" ] || [ "$${BRANCH}" != "main" ]; then
            echo "cross-branch-verify: skipping (event=$${EVENT:-unknown}, branch=$${BRANCH:-unknown})"
            exit 0
          fi
          echo "cross-branch-verify: branch=$${BRANCH}, sha=$${CI_COMMIT_SHA:-$${WOODPECKER_COMMIT_SHA:-unknown}}"
          echo "cross-branch-verify: merge-to-main event detected; verifying commit is on main"
          git fetch --quiet --unshallow origin || git fetch --quiet --depth=50000 origin main || true
```

## Unexpected Findings

- Large number of backup and safety tags (~90+ tags), many with dated snapshots
- 6010 files tracked in repository
- No secret-adjacent files (`.env`, `terraform.tfstate`) are tracked
- CI uses chiseai-ci-tools:py311-20260423 image
- CI is configured for PR and manual events, plus push-to-main cross-branch verification
