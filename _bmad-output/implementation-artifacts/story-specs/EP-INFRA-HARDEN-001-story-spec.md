# EP-INFRA-HARDEN-001: Infrastructure Hardening

## Epic Overview

| Field | Value |
|---|---|
| **Epic ID** | EP-INFRA-HARDEN-001 |
| **Priority** | P1 |
| **Status** | queued (pending 72h burn-in gate) |
| **Burn-in Gate** | 2026-05-07T11:01:12Z |
| **Estimated Story Points** | 8 |
| **Owner** | jarvis |
| **Depends On** | RECON-BURN-IN-72H (72h post-pipeline-unblock burn-in) |

## Background

R2a canary experienced multiple infrastructure failures that required manual remediation:

| Incident | Description | Date | Root Cause |
|---|---|---|---|
| BLK-001 | Signal crash-loop (Exit 255) | 2026-05-02 | Unhandled exception in signal generator |
| BLK-002 | InfluxDB zombie process | 2026-05-02 | Orphaned write process consuming resources |
| BLK-003 | Consumer idle (no processing) | 2026-05-02 | Consumer stuck waiting on dead queue |
| AUTOCOG-CRON-FIX-001 | Cron pipeline misfire | 2026-05-02 | ci.yaml trigger pattern matching cron branches |
| REPO-0428 | CI syntax error (17 consecutive failures) | 2026-05-02 | Invalid YAML in .woodpecker config |

All incidents were manually resolved on 2026-05-02. EP-PIPELINE-UNBLOCK-001 completed and merged at d3c7a286e on 2026-05-04. This epic addresses the systemic infrastructure reliability issues to prevent similar failures during R2b and beyond.

## Objective

Harden infrastructure for long-term operational stability by:

- Automating health monitoring for containers and cron jobs
- Improving alerting to catch issues before they become blockers
- Eliminating common failure modes that required manual intervention during R2a
- Building automated incident response for known failure patterns

## Stories

### ST-INFRA-001: Cron Pipeline Reliability

| Field | Value |
|---|---|
| **Size** | 2SP |
| **Priority** | P1 |
| **Incidents Addressed** | AUTOCOG-CRON-FIX-001, REPO-0428 |

**Description**: Ensure all Woodpecker cron pipelines are reliable with daily health reporting and alerting for missed executions.

**Acceptance Criteria**:

1. Audit all cron pipelines for trigger correctness:
   - Verify no ci.yaml trigger pattern is matching cron branches
   - Document each cron pipeline's expected trigger and schedule
   - Fix any misconfigured triggers found during audit
2. Add daily cron health check script:
   - `scripts/ops/cron_health_check.py`
   - Verifies all scheduled jobs ran within expected windows
   - Reads cron schedule from documentation/reference file
   - Checks Woodpecker API (or `woodpecker-cli`) for recent pipeline runs
3. Alert via Discord if any cron job misses its scheduled window by > 30 minutes:
   - Use existing Discord webhook integration
   - Alert includes: job name, expected time, last seen run, suggested action
   - Alert severity: warning (not critical — cron retries usually work)
4. Document all cron schedules in a single reference file:
   - `docs/runbooks/cron-schedules.md`
   - Format: job name, cron expression, expected duration, alert threshold
   - Reference file is the source of truth for health check configuration
5. Verify with 48h of cron execution monitoring:
   - Health check runs for 48h without false positives
   - At least one simulated missed job triggers alert correctly

**Implementation Notes**:

- Woodpecker cron API: `GET /api/repos/{owner}/{repo}/pipelines` with branch filter
- Check script should be idempotent — safe to run multiple times
- Consider adding cron health to existing daily health report
- If Woodpecker API is not accessible, fall back to `woodpecker-cli logs` parsing
- Integrate with existing `chiseai-validation` skill patterns

**Scope**: `.woodpecker/`, `scripts/ops/cron_health_check.py` (new), `docs/runbooks/`

**Verification**: `cron_health_check.py` runs and reports status, alert fires on simulated missed job

---

### ST-INFRA-002: Container Health Monitoring

| Field | Value |
|---|---|
| **Size** | 2SP |
| **Priority** | P1 |
| **Incidents Addressed** | BLK-001 (Exit 255 crash-loop) |

**Description**: Add automated container health monitoring with auto-restart on failure patterns (especially Exit 255 which caused BLK-001).

**Acceptance Criteria**:

1. Monitoring script checks all ChiseAI containers every 60 seconds:
   - `scripts/ops/container_monitor.py`
   - Discovers containers via Docker label `project=chiseai`
   - Checks container status, health, and uptime
   - Runs as a long-lived process (systemd service or Docker sidecar)
2. Auto-restart on Exit 255 (with exponential backoff):
   - First restart: immediate
   - Second restart: 30 second delay
   - Third restart: 60 second delay
   - After 3 retries: stop auto-restart, alert only
   - Restart delay configurable via environment variable
3. Alert on any container restart (not just Exit 255):
   - Discord alert with: container name, exit code, restart count, last log lines
   - Alert severity based on exit code:
     - Exit 0 (planned): info
     - Exit 1 (error): warning
     - Exit 255 (crash): critical
4. Container restart count tracked in Redis with TTL:
   - `monitor:container:<name>:restarts` — count with 30-minute TTL
   - `monitor:container:<name>:last_restart_ts` — timestamp
   - `monitor:container:<name>:last_exit_code` — exit code
5. Circuit breaker: if container restarts > 5 in 30 minutes:
   - Stop auto-restart for that container
   - Alert with critical severity
   - Include recommendation: "manual investigation required"
   - Circuit breaker auto-resets after 30 minutes of stability
6. Health check integrates with existing Docker governance:
   - Uses `project=chiseai` label for container discovery
   - Respects protected container list from `chiseai-docker-governance`
   - Does NOT auto-restart protected containers (alert only)

**Implementation Notes**:

- Use Docker SDK for Python (`docker` package) for container interaction
- Script structure: main loop with configurable check interval
- Consider using `docker events` stream for real-time detection instead of polling
- Protected containers: `tradedev`, `intelligent_ride`, `aisetup-mcp-discord-1`, `duckduckgo-mcp-server`
- Log all monitoring events to `monitor:container:log` Redis stream
- Add `--dry-run` flag for testing without actual restarts

**Scope**: `scripts/ops/container_monitor.py` (new), `scripts/ops/`

**Verification**: Simulate container failure, verify auto-restart + alert + Redis tracking

---

### ST-INFRA-003: Terraform Provider URL Stability Audit

| Field | Value |
|---|---|
| **Size** | 1SP |
| **Priority** | P1 |

**Description**: Audit all Terraform provider URLs for stability and pin versions where possible.

**Acceptance Criteria**:

1. All provider URLs verified as reachable and stable:
   - HTTP HEAD/GET returns 200 for all provider source URLs
   - Response time < 5 seconds for each provider
   - Document any providers with slow or inconsistent responses
2. Provider versions pinned (no floating `latest` tags):
   - Every provider block has explicit `version` constraint
   - Version constraints use `~>` for minor version flexibility
   - No `>= 0.0.0` or unconstrained versions
3. Terraform init/plan/apply works cleanly from scratch:
   - `terraform init` succeeds with no provider download errors
   - `terraform plan` produces expected output (no unexpected changes)
   - `terraform apply` is NOT run (plan-only verification)
4. Document provider versions and URLs:
   - `infrastructure/terraform/PROVIDERS.md` — new file
   - Format: provider name, source URL, pinned version, last verified date
   - Include instructions for updating providers
5. CI pipeline for Terraform validation exists:
   - `terraform fmt -check` passes
   - `terraform validate` passes
   - Runs on PRs that touch `infrastructure/terraform/`

**Implementation Notes**:

- Check `infrastructure/terraform/` for all `.tf` files
- Common providers: Docker, local, null, random, etc.
- If provider registry is slow, consider local mirror or caching
- Document any providers that cannot be pinned (and why)
- Add `.terraform.lock.hcl` to version control for reproducibility

**Scope**: `infrastructure/terraform/`

**Verification**: `terraform init && terraform plan` succeeds with no provider errors

---

### ST-INFRA-004: Woodpecker CI Reliability Review

| Field | Value |
|---|---|
| **Size** | 1SP |
| **Priority** | P1 |
| **Incidents Addressed** | REPO-0428 (17 consecutive CI failures from invalid syntax) |

**Description**: Review Woodpecker CI configuration for reliability issues, especially around syntax validation and error handling.

**Acceptance Criteria**:

1. CI YAML syntax validation added to lint step:
   - All `.woodpecker/*.yaml` files validated on every PR
   - Validation uses `yamllint` with project-specific config
   - Validation failure blocks PR merge
2. All Woodpecker config files pass yamllint:
   - Zero errors, zero warnings
   - Fix any existing violations found during review
   - Add `.yamllint` config if not present (or update existing)
3. No invalid or unsupported syntax in any `.woodpecker/*.yaml`:
   - Audit for deprecated Woodpecker syntax
   - Verify all `when:` conditions use current syntax
   - Verify all `commands:` use valid shell syntax
   - Document any Woodpecker version-specific syntax requirements
4. CI pipeline error rate baseline established:
   - Record current error rate (target: < 5% of runs)
   - Document common failure modes
   - Track in Redis: `ci:stats:error_rate`, `ci:stats:common_failures`
5. Document CI reliability findings and fixes:
   - `docs/runbooks/ci-reliability.md` — new file
   - Include: findings, fixes applied, prevention measures, monitoring plan

**Implementation Notes**:

- Use `yamllint` with relaxed config for CI files (some Woodpecker syntax is non-standard YAML)
- Check for common issues: trailing spaces, wrong indentation, missing quotes
- Consider adding `woodpecker-cli lint` if available
- Cross-reference with `.woodpecker/ci.yaml` for trigger patterns
- CI error rate tracking: parse Woodpecker API or CI logs

**Scope**: `.woodpecker/`, `scripts/ci/`

**Verification**: All `.woodpecker/*.yaml` files pass yamllint with no errors

---

### ST-INFRA-005: Grafana Dashboard Health Checks

| Field | Value |
|---|---|
| **Size** | 1SP |
| **Priority** | P1 |

**Description**: Add health check panels and alerts to Grafana dashboards for proactive issue detection.

**Acceptance Criteria**:

1. r2a-canary-health dashboard has pipeline health overview panel:
   - Panel shows: signal generation rate, consumer processing rate, queue depth
   - Panel updates every 60 seconds
   - Panel has visual threshold indicators (green/yellow/red)
2. Alert rules configured for key conditions:
   - **Signal generation stop**: no new signals for > 15 minutes
   - **Consumer idle**: no processed signals for > 10 minutes
   - **Container restart**: any ChiseAI container restarts
   - **Error rate spike**: error rate > 10% over 5-minute window
3. Alert notification routed to Discord via existing contact point:
   - Use existing Discord webhook contact point
   - Alert message includes: dashboard link, affected metric, current value, threshold
4. Dashboard accessible and rendering correctly:
   - Dashboard loads without errors in Grafana UI
   - All panels render with live data
   - Time range selector works correctly
5. Document dashboard layout and alert configuration:
   - `docs/runbooks/grafana-health-dashboards.md`
   - Include: panel descriptions, alert thresholds, notification routing

**Implementation Notes**:

- Use Grafana provisioning or API to create/update dashboard JSON
- Dashboard JSON model should be version-controlled
- Alert rules use Grafana unified alerting (not legacy dashboard alerts)
- Coordinate with `chiseai-metrics-dashboard` skill for patterns
- Consider adding a "Canary Status" summary panel at the top

**Scope**: Grafana configuration (via API/JSON models), `docs/runbooks/`

**Verification**: Alert fires on simulated pipeline stop, notification received

---

### ST-INFRA-006: Incident Response Automation

| Field | Value |
|---|---|
| **Size** | 1SP |
| **Priority** | P1 |
| **Incidents Addressed** | BLK-001, BLK-002, BLK-003 (all required manual intervention) |

**Description**: Automate initial incident response steps for common failure patterns identified during R2a.

**Acceptance Criteria**:

1. Automated incident creation for container crash-loop:
   - Trigger: > 3 container restarts in 10 minutes
   - Creates incident with template: affected service, likely root cause (Exit 255), remediation steps
   - Incident severity: P1
   - Integration with `chiseai-incident-response` skill
2. Automated incident creation for cron job failure:
   - Trigger: > 2 consecutive missed cron executions
   - Creates incident with template: affected cron job, last successful run, remediation steps
   - Incident severity: P2
3. Incident template includes:
   - Affected service/component
   - Likely root cause (based on failure pattern)
   - Remediation steps (specific, actionable)
   - Evidence links (logs, metrics, Redis keys)
4. Integration with existing `chiseai-incident-response` skill:
   - Uses same incident format and logging
   - Incident logged to Redis iterlog
   - Follows same severity/P0-P3 classification
5. Incident response runbook for top 5 failure patterns from R2a:
   - `docs/runbooks/incident-response.md` — new or extended
   - Patterns: Exit 255 crash-loop, zombie process, consumer idle, cron misfire, CI syntax error
   - Each pattern: symptoms, diagnosis steps, remediation, prevention

**Implementation Notes**:

- New script: `scripts/ops/incident_responder.py`
- Script is event-driven: triggered by container monitor (ST-INFRA-002) or cron health check (ST-INFRA-001)
- Incident templates stored as JSON in `scripts/ops/incident_templates/`
- Use Redis pub/sub for event passing between monitors and responder
- Consider integration with Grafana incident management if available
- Each incident should auto-populate as much data as possible (reduce manual toil)

**Scope**: `scripts/ops/incident_responder.py` (new), `docs/runbooks/incident-response.md`

**Verification**: Simulate failure pattern, verify incident created with correct template

## Dependencies

| Dependency | Type | Gate Date |
|---|---|---|
| RECON-BURN-IN-72H | Hard gate | 2026-05-07T11:01:12Z |

All stories are blocked until burn-in gate passes. Burn-in verification checks:

- Pipeline components stable (no crash-loops, no consumer idle, no zombie processes)
- Signal generation consistent (no gaps > 2h)
- CI pipelines green for 72h

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Infrastructure changes during burn-in window | Low | High | All changes gated on burn-in completion |
| Auto-restart masking deeper issues | Medium | High | Circuit breaker on restart count, alerting on every restart |
| Terraform state drift | Low | Medium | Pin provider versions, validate in CI |
| Cron health check false positives | Medium | Low | 30-minute grace window, configurable thresholds |
| Incident responder creating noise | Medium | Medium | Strict trigger thresholds, deduplication, rate limiting |

## Success Criteria

1. All 6 stories completed and merged
2. Container monitoring active with < 5 minute detection time for failures
3. Cron health check running daily with Discord alerting for missed jobs
4. Terraform validated from clean state with pinned providers
5. CI YAML syntax validation in place preventing REPO-0428 class failures
6. Grafana health dashboard with alerting for key pipeline conditions
7. Incident response automated for top 5 R2a failure patterns
8. No P0/P1 incidents caused by infrastructure changes during implementation

## Execution Order

```
ST-INFRA-004 (CI reliability review) — no dependencies, can start immediately
ST-INFRA-003 (Terraform audit) — no dependencies, can start immediately
├── ST-INFRA-001 (cron reliability) — can parallel with ST-INFRA-002
│   └── ST-INFRA-006 (incident response) — depends on monitor + cron check
├── ST-INFRA-002 (container monitoring) — can parallel with ST-INFRA-001
│   └── ST-INFRA-006 (incident response) — depends on monitor + cron check
└── ST-INFRA-005 (Grafana dashboards) — can parallel with others
```

ST-INFRA-003, ST-INFRA-004, and ST-INFRA-005 have no interdependencies and can run in parallel.
ST-INFRA-001 and ST-INFRA-002 can also run in parallel.
ST-INFRA-006 depends on both ST-INFRA-001 and ST-INFRA-002 for event sources.

## Cross-Epic Coordination

This epic should coordinate with EP-CANARY-R2B-001:

- ST-INFRA-002 (container monitoring) should cover all canary containers
- ST-INFRA-005 (Grafana dashboards) should integrate with canary health dashboard
- ST-INFRA-006 (incident response) should cover canary-specific failure patterns
- Both epics share the same burn-in gate and should start execution simultaneously after gate passes
