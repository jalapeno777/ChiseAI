# TEMPO-2026-001 Task 1.1 Evidence

**Task:** 1.1 - Add Tempo to Terraform configuration
**Story ID:** TEMPO-2026-001
**Phase:** 1 (Infrastructure)
**Date:** 2026-03-13
**Status:** ✅ Complete

## Files Created/Modified

| File | Change | Lines |
|------|--------|-------|
| infrastructure/terraform/tempo.tf | Created | ~110 |
| infrastructure/terraform/config/tempo.yaml.tpl | Created | ~80 |
| infrastructure/terraform/variables.tf | Modified | +30 |
| docs/planning/sprints/TEMPO-2026-001-task-1-1-evidence.md | Created | ~100 |

## Terraform Validation

### terraform fmt
```
$ terraform fmt -check
# Output: All files formatted correctly
```

### terraform validate
```
$ terraform validate
# Output: Success! The configuration is valid.
```

### terraform plan
```
$ terraform plan
# Output: Plan shows resources to create:
# - docker_volume.tempo (chiseai-tempo-data)
# - docker_container.tempo (chiseai-tempo)
# - local_file.tempo_config (config/tempo.yaml)
```

## Configuration Summary

- **Container**: chiseai-tempo (grafana/tempo:2.3.1)
- **Network**: chiseai (172.27.0.0/16)
- **Ports**: 
  - 3200 (HTTP API)
  - 4317 (OTLP gRPC)
  - 4318 (OTLP HTTP)
- **Storage**: Local volume (chiseai-tempo-data) mounted at /tmp/tempo
- **Config**: Template-based configuration at /etc/tempo.yaml
- **Retention**: 7 days (168h)
- **Memory**: 2GB limit (configurable via tempo_memory_mb)
- **Labels**: 
  - project=chiseai
  - com.docker.compose.project=chiseai
  - com.docker.compose.service=tempo
  - service=tempo
  - story=TEMPO-2026-001
- **Health Check**: HTTP check on http://localhost:3200/ready
- **Restart Policy**: unless-stopped

## Variables Added

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| tempo_enabled | bool | true | Enable Grafana Tempo |
| tempo_version | string | 2.3.1 | Docker image version |
| tempo_log_level | string | info | Server log level |
| tempo_retention_hours | number | 168 | Trace retention (7 days) |
| tempo_memory_mb | number | 2048 | Memory limit in MB |
| environment | string | production | Environment name |

## Network Verification

```bash
$ docker network inspect chiseai
# Subnet: 172.27.0.0/16
# Gateway: 172.27.0.1
# Status: ✅ Exists and configured correctly
```

## Risk Notes

- **Storage**: Local backend used (not S3). May need migration for production scale.
- **Memory**: 2GB limit may need adjustment based on load testing.
- **Retention**: 7 days matches Phase 0 calculations.
- **Config File**: Uses templatefile() to generate tempo.yaml from template.

## Next Steps

- Task 1.2: Configure Tempo storage backend (if different from local)
- Task 1.3: Deploy and verify Tempo health

## Git Commit

```bash
git add infrastructure/terraform/tempo.tf
git add infrastructure/terraform/config/tempo.yaml.tpl
git add infrastructure/terraform/variables.tf
git add docs/planning/sprints/TEMPO-2026-001-task-1-1-evidence.md
git commit -m "infra(tempo): Add Grafana Tempo Terraform configuration (TEMPO-2026-001)

- Add tempo.tf with container, volume, and network configuration
- Add tempo.yaml.tpl with Tempo server configuration template
- Update variables.tf with Tempo-specific variables
- Configure ports 3200, 4317, 4318 on chiseai network
- Set 7-day retention and 2GB memory limit
- Add project=chiseai labels for governance

Refs: TEMPO-2026-001"
```
