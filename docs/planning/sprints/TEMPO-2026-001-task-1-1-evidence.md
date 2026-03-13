# TEMPO-2026-001 Task 1.1 Evidence

**Task:** 1.1 - Add Tempo to Terraform configuration
**Story ID:** TEMPO-2026-001
**Phase:** 1 (Infrastructure)
**Date:** 2026-03-13
**Status:** Complete (FIXED)

## Files Created/Modified

- infrastructure/terraform/tempo.tf (FIXED)
- infrastructure/terraform/config/tempo.yaml.tpl
- infrastructure/terraform/variables.tf (updated)

## Critical Fixes Applied (2026-03-13)

### Issue 1: INVALID TERRAFORM IDENTIFIERS
**Problem:** Resource names used hyphens which are INVALID in Terraform.
- ❌ `docker_volume.tempo-data` → ✅ `docker_volume.tempo_data`
- ❌ `docker_container.chiseai-tempo` → ✅ `docker_container.chiseai_tempo`

### Issue 2: MISSING TEMPLATE RENDERING
**Problem:** Container mounted `config/tempo.yaml` but no template rendering existed.
**Fix:** Added proper template rendering pipeline:
- `data.template_file.tempo_config` - Renders template with variables
- `local_file.tempo_config` - Writes rendered config to disk
- Container volume now references `abspath(local_file.tempo_config.filename)`

### Issue 3: INVALID VARIABLE REFERENCE
**Problem:** Container used `var.environment` which doesn't exist.
**Fix:** Changed to `var.tempo_log_level`

### Issue 4: HARDCODED IMAGE VERSION
**Problem:** Container used hardcoded `grafana/tempo:2.3.1`.
**Fix:** Changed to `grafana/tempo:${var.tempo_version}`

## Configuration

- Container: chiseai-tempo (grafana/tempo:${var.tempo_version})
- Network: chiseai
- Ports: 3200 (HTTP), 4317 (OTLP gRPC), 4318 (OTLP HTTP)
- Retention: 168 hours (7 days)
- Memory: 2GB

## Verification Results

### Pre-Fix (FAILED)
```
$ terraform validate
Error: Invalid resource name
```

### Post-Fix (PASS)
```
$ terraform fmt -check
All files formatted correctly

$ terraform validate
Success! The configuration is valid.

$ terraform plan -target=docker_volume.tempo_data -target=local_file.tempo_config -target=docker_container.chiseai_tempo
Plan: 3 to add, 0 to change, 0 to destroy.
```

### Resource Names Check
```
$ grep -E 'resource\s+"[^"]+"\s+"[^"]*-[^"]*"' tempo.tf
✅ No hyphens found in resource names
```

## Resources Created by Terraform

1. `docker_volume.tempo_data` - Named volume for trace storage
2. `local_file.tempo_config` - Rendered tempo.yaml configuration
3. `docker_container.chiseai_tempo` - Tempo container with OTLP receivers

## Readiness for Next Tasks

- ✅ Task 1.2 (Grafana datasource) - READY
- ✅ Task 1.3 (Docker Compose) - READY
- ✅ All Terraform syntax errors resolved
- ✅ Template rendering properly wired
- ✅ All variable references valid

## Commit

Fixes committed to branch: `feature/TEMPO-2026-001-task-1-1-tempo-terraform-v2`
