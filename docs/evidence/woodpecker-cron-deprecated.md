# Woodpecker Cron Deprecation Notice

**Date**: 2026-03-03  
**Status**: DEPRECATED  
**Replacement**: Docker-based scheduler (`chiseai-brain-scheduler`)  
**Story**: ST-REFLECT-RUNTIME-001

## Rationale

Woodpecker cron has been deprecated in favor of a Docker-based scheduler container for improved reliability, observability, and operational control. The Docker scheduler provides:

- **Better isolation**: Runs in its own container with controlled resources
- **Health monitoring**: Built-in health checks and status endpoints
- **Easier debugging**: Direct access to logs and container shell
- **Simpler deployment**: Single `docker compose up` command
- **Feature flag integration**: Native Redis-based governance controls

## Migration

See: `docs/runbooks/reflection-scheduler-ops.md`

## Legacy Configuration

Previous Woodpecker cron configuration files:

| File | Status | Description |
|------|--------|-------------|
| `.woodpecker/cron-eval.yaml` | **DEPRECATED** | CI cron pipeline configuration |
| `docs/runbooks/Woodpecker-Cron-Setup-Runbook.md` | **DEPRECATED** | Setup instructions for Woodpecker cron |

### Previous Cron Jobs (No Longer Active)

| Job Name | Cron Expression | Description |
|----------|----------------|-------------|
| `6h-mini-eval` | `0 */6 * * *` | Every 6 hours at minute 0 (00:00, 06:00, 12:00, 18:00 UTC) |
| `daily-trends` | `15 0 * * *` | Daily at 00:15 UTC |
| `weekly-reflection` | `0 1 * * 1` | Weekly on Monday at 01:00 UTC |

## Evidence of Migration

- **New Runbook**: `docs/runbooks/reflection-scheduler-ops.md` (893 lines, comprehensive operations guide)
- **Docker Compose**: `infrastructure/docker/docker-compose.scheduler.yml`
- **Dockerfile**: `infrastructure/docker/Dockerfile.scheduler`
- **Validation Report**: `docs/evidence/BRAINEVAL-SCHEDULER-DOCKER-VALIDATION-2026-03-03.md`

## Historical References

The following evidence files document the Woodpecker cron setup attempts and eventual migration:

- `docs/evidence/Cron-Activation-Attempt-Log-2026-03-02.md`
- `docs/evidence/Cron-Setup-Attempt-20260302.md`
- `docs/evidence/Final-Verdict-BrainEval-CI-2026-03-02.md`
- `docs/handoffs/AI-SWARM-HANDOFF-BRAINEVAL-CI.md`

## Action Items

- [x] Create Docker-based scheduler
- [x] Write operational runbook
- [x] Validate Docker deployment
- [x] Archive Woodpecker cron references
- [ ] Remove `.woodpecker/cron-eval.yaml` (optional - can keep for historical reference)
- [ ] Update `docs/runbooks/Woodpecker-Cron-Setup-Runbook.md` with deprecation header (optional)

## Contact

For questions about the migration, refer to:
- Primary Runbook: `docs/runbooks/reflection-scheduler-ops.md`
- Story: ST-REFLECT-RUNTIME-001
