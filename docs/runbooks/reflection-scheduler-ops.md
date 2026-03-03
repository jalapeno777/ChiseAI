# Reflection Scheduler Operations Runbook

> **Story**: ST-REFLECT-RUNTIME-001  
> **Last Updated**: 2026-03-03  
> **Owner**: ChiseAI Infrastructure Team

## Overview

This runbook documents the operations for the BrainEval reflection scheduler, which runs KPI cadence jobs on 6-hour, daily, and weekly intervals. The scheduler is deployed as a Docker container (`chiseai-brain-scheduler`) on the `chiseai` network.

## Table of Contents

1. [Docker-First Deployment](#docker-first-deployment)
2. [Health Check Commands](#health-check-commands)
3. [Feature Flag Enablement](#feature-flag-enablement)
4. [Local Cron Fallback](#local-cron-fallback)
5. [Troubleshooting](#troubleshooting)

---

## Docker-First Deployment

### Prerequisites

- Docker daemon running
- `chiseai` Docker network exists (managed by Terraform)
- Redis accessible at `chiseai-redis:6380`

### Build and Deploy

```bash
# Navigate to project root
cd /home/tacopants/projects/ChiseAI

# Build the scheduler container
docker compose -f infrastructure/docker/docker-compose.scheduler.yml build

# Start the scheduler container
docker compose -f infrastructure/docker/docker-compose.scheduler.yml up -d
```

### Verify Deployment

```bash
# Check container status
docker ps --filter name=chiseai-brain-scheduler

# View container logs
docker logs chiseai-brain-scheduler --tail 50

# Check health from inside container
docker exec chiseai-brain-scheduler curl -f http://localhost:8080/health
```

### Container Configuration

| Setting | Value | Description |
|---------|-------|-------------|
| Container Name | `chiseai-brain-scheduler` | Primary identifier |
| Image | `chiseai-brain-scheduler:latest` | Built from Dockerfile.scheduler |
| Network | `chiseai` | External network managed by Terraform |
| Health Port | `8080` | Internal health check endpoint |
| Redis Host | `chiseai-redis` | Service name on chiseai network |
| Redis Port | `6380` | Redis server port |

### Resource Limits

```yaml
deploy:
  resources:
    limits:
      cpus: '1.0'
      memory: 512M
    reservations:
      cpus: '0.25'
      memory: 128M
```

### Restart Policy

The container uses `unless-stopped` restart policy, meaning it will automatically restart unless explicitly stopped.

---

## Health Check Commands

### Container Health Status

```bash
# Check Docker health status
docker ps --filter name=chiseai-brain-scheduler --format "table {{.Names}}\t{{.Status}}\t{{.Health}}"

# Detailed health check
docker inspect --format='{{.State.Health.Status}}' chiseai-brain-scheduler
```

### HTTP Health Endpoint

The scheduler exposes a health endpoint on port 8080:

```bash
# From inside the container
docker exec chiseai-brain-scheduler curl -s http://localhost:8080/health
```

**Expected Response:**
```json
{
  "status": "healthy",
  "state": "running",
  "timestamp": "2026-03-03T21:08:58.981707+00:00"
}
```

### Health Check Configuration

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
  interval: 30s
  timeout: 10s
  start_period: 60s
  retries: 3
```

### Monitoring Health

```bash
# Watch health status in real-time
watch -n 5 'docker ps --filter name=chiseai-brain-scheduler --format "{{.Names}}: {{.Status}}"'

# Check recent health events
docker events --filter container=chiseai-brain-scheduler --filter event=health_status
```

---

## Feature Flag Enablement

### Governance Feature Flags

The scheduler uses Redis-based feature flags for governance capabilities. All flags are stored in the hash `chise:feature_flags:governance`.

### Enable All Governance Flags

```bash
# Using redis-cli from host (if Redis is on host)
redis-cli -h host.docker.internal -p 6380 HSET chise:feature_flags:governance \
  reflection_enabled true \
  memory_promotion_enabled true \
  memory_sweep_enabled true \
  memory_dedup_enabled true \
  consolidation_enabled true \
  contradiction_detection_enabled true
```

### Verify Feature Flags

```bash
# List all governance flags
redis-cli -h host.docker.internal -p 6380 HGETALL chise:feature_flags:governance

# Check specific flags
redis-cli -h host.docker.internal -p 6380 HMGET chise:feature_flags:governance \
  reflection_enabled \
  memory_promotion_enabled \
  memory_sweep_enabled
```

### Feature Flag Reference

| Flag | Description | Default |
|------|-------------|---------|
| `reflection_enabled` | Enable reflection cycle processing | `false` |
| `memory_promotion_enabled` | Enable memory promotion to long-term | `false` |
| `memory_sweep_enabled` | Enable memory sweep/cleanup | `false` |
| `memory_dedup_enabled` | Enable memory deduplication | `false` |
| `consolidation_enabled` | Enable memory consolidation | `false` |
| `contradiction_detection_enabled` | Enable contradiction detection | `false` |

### Disable Feature Flags

```bash
# Disable a specific flag
redis-cli -h host.docker.internal -p 6380 HSET chise:feature_flags:governance reflection_enabled false
```

---

## Local Cron Fallback

If Docker deployment is not available, the scheduler can run as a local cron job.

### Cron Schedule

```cron
# /etc/cron.d/chiseai-brain-scheduler
# BrainEval KPI Scheduler - Local Cron Fallback

# 6-hour cycle (runs at 00:00, 06:00, 12:00, 18:00)
0 */6 * * * root /usr/bin/python3 /home/tacopants/projects/ChiseAI/scripts/evaluation/run_mini_eval.py >> /var/log/chiseai/mini_eval.log 2>&1

# Daily cycle (runs at 00:00)
0 0 * * * root /usr/bin/python3 /home/tacopants/projects/ChiseAI/scripts/evaluation/run_daily_trends.py >> /var/log/chiseai/daily_trends.log 2>&1

# Weekly cycle (runs at 00:00 on Sundays)
0 0 * * 0 root /usr/bin/python3 /home/tacopants/projects/ChiseAI/scripts/evaluation/run_weekly_reflection.py >> /var/log/chiseai/weekly_reflection.log 2>&1
```

### Setup Local Cron

```bash
# Create log directory
sudo mkdir -p /var/log/chiseai
sudo chown $USER:$USER /var/log/chiseai

# Install cron file
sudo cp infrastructure/cron/chiseai-scheduler /etc/cron.d/
sudo chmod 644 /etc/cron.d/chiseai-scheduler

# Verify cron job
crontab -l
```

### Manual Script Execution

```bash
# Run 6-hour evaluation manually
cd /home/tacopants/projects/ChiseAI
python3 scripts/evaluation/run_mini_eval.py

# Run daily trends manually
python3 scripts/evaluation/run_daily_trends.py

# Run weekly reflection manually
python3 scripts/evaluation/run_weekly_reflection.py
```

---

## Troubleshooting

### Container Won't Start

**Symptom:** Container exits immediately after start

**Diagnosis:**
```bash
# Check container logs
docker logs chiseai-brain-scheduler

# Check if network exists
docker network ls | grep chiseai

# Check if Redis is accessible
docker exec chiseai-brain-scheduler nc -zv chiseai-redis 6380
```

**Resolution:**
1. Ensure `chiseai` network exists: `docker network create chiseai`
2. Check Redis connectivity
3. Verify volume permissions

### Health Check Failing

**Symptom:** Container shows as `unhealthy`

**Diagnosis:**
```bash
# Check health check logs
docker inspect --format='{{json .State.Health}}' chiseai-brain-scheduler | jq

# Test health endpoint manually
docker exec chiseai-brain-scheduler curl -v http://localhost:8080/health
```

**Resolution:**
1. Check if scheduler process is running: `docker exec chiseai-brain-scheduler ps aux`
2. Review application logs: `docker logs chiseai-brain-scheduler --tail 100`
3. Restart container: `docker restart chiseai-brain-scheduler`

### Redis Connection Issues

**Symptom:** Scheduler cannot connect to Redis

**Diagnosis:**
```bash
# Test Redis connectivity from container
docker exec chiseai-brain-scheduler nc -zv chiseai-redis 6380

# Check Redis from host
redis-cli -h host.docker.internal -p 6380 ping
```

**Resolution:**
1. Verify Redis container is running: `docker ps | grep redis`
2. Check network connectivity: `docker network inspect chiseai`
3. Verify Redis credentials and database

### Port Conflicts

**Symptom:** Cannot bind to port 8080

**Diagnosis:**
```bash
# Check what's using port 8080
sudo netstat -tlnp | grep 8080
sudo lsof -i :8080
```

**Resolution:**
1. The scheduler uses port 8080 internally only (not exposed to host)
2. If you need external access, modify docker-compose to add port mapping:
   ```yaml
   ports:
     - "8080:8080"
   ```

### High Memory Usage

**Symptom:** Container using more than 512MB memory

**Diagnosis:**
```bash
# Check memory usage
docker stats chiseai-brain-scheduler --no-stream

# Check for memory leaks in logs
docker logs chiseai-brain-scheduler | grep -i memory
```

**Resolution:**
1. Increase memory limit in docker-compose.yml
2. Check for runaway processes in container
3. Restart container to clear memory

### Scheduler Jobs Not Running

**Symptom:** No output files in `_bmad-output/brain-eval/scheduler`

**Diagnosis:**
```bash
# Check scheduler logs
docker logs chiseai-brain-scheduler --tail 100

# Verify output directory exists
docker exec chiseai-brain-scheduler ls -la /app/_bmad-output/brain-eval/scheduler/

# Check feature flags
redis-cli -h host.docker.internal -p 6380 HGETALL chise:feature_flags:governance
```

**Resolution:**
1. Ensure feature flags are enabled (see [Feature Flag Enablement](#feature-flag-enablement))
2. Check scheduler state in logs
3. Verify volume mounts are correct

### Container Restart Loop

**Symptom:** Container keeps restarting

**Diagnosis:**
```bash
# Check restart count
docker inspect --format='{{.RestartCount}}' chiseai-brain-scheduler

# Check last exit code
docker inspect --format='{{.State.ExitCode}}' chiseai-brain-scheduler
```

**Resolution:**
1. Check logs for error messages
2. Verify all dependencies are available
3. Temporarily disable restart policy for debugging:
   ```bash
   docker update --restart=no chiseai-brain-scheduler
   ```

### Emergency Procedures

#### Stop Scheduler

```bash
# Graceful stop
docker compose -f infrastructure/docker/docker-compose.scheduler.yml down

# Force stop
docker stop chiseai-brain-scheduler
docker rm chiseai-brain-scheduler
```

#### Reset Scheduler State

```bash
# Stop and remove container
docker compose -f infrastructure/docker/docker-compose.scheduler.yml down

# Remove volumes (WARNING: deletes all output data)
docker volume rm docker_brain-scheduler-output docker_brain-scheduler-logs

# Rebuild and restart
docker compose -f infrastructure/docker/docker-compose.scheduler.yml up -d --build
```

---

## Quick Reference

### Common Commands

```bash
# Start scheduler
docker compose -f infrastructure/docker/docker-compose.scheduler.yml up -d

# Stop scheduler
docker compose -f infrastructure/docker/docker-compose.scheduler.yml down

# View logs
docker logs -f chiseai-brain-scheduler

# Restart scheduler
docker restart chiseai-brain-scheduler

# Shell into container
docker exec -it chiseai-brain-scheduler /bin/bash

# Check scheduler status
docker ps --filter name=chiseai-brain-scheduler
```

### File Locations

| File | Path |
|------|------|
| Dockerfile | `infrastructure/docker/Dockerfile.scheduler` |
| Docker Compose | `infrastructure/docker/docker-compose.scheduler.yml` |
| Scheduler Script | `scripts/evaluation/kpi_scheduler.py` |
| Output Directory | `/app/_bmad-output/brain-eval/scheduler` (container) |
| Log Directory | `/app/logs` (container) |
| This Runbook | `docs/runbooks/reflection-scheduler-ops.md` |

### Related Documentation

- [Docker Governance](../../AGENTS.md#docker--container-connectivity-critical)
- [Terraform Infrastructure](../../infrastructure/terraform/)
- [BrainEval KPI System](../../docs/brain-eval-kpi-system.md)

---

## Live Validation Checklist

Use this checklist to verify the scheduler is operating correctly after deployment or updates.

### Pre-Validation Requirements

- [ ] Docker daemon is running
- [ ] `chiseai` network exists
- [ ] Redis is accessible at `host.docker.internal:6380`
- [ ] Scheduler container is built and running

### Validation Steps

#### 1. Verify Scheduler Container Health

```bash
# Check container is running
docker ps --filter name=chiseai-brain-scheduler --format "table {{.Names}}\t{{.Status}}"

# Check health endpoint
docker exec chiseai-brain-scheduler curl -s http://localhost:8080/health | jq .

# Check detailed status
docker exec chiseai-brain-scheduler curl -s http://localhost:8080/status | jq .
```

**Expected Results:**
- Container status: `Up` or `healthy`
- Health endpoint: `{"status": "healthy", "state": "running"}`
- Status endpoint: Shows checkpoint with cycle counts and timestamps

#### 2. Verify Feature Flags Are Active

```bash
# List all governance feature flags
redis-cli -h host.docker.internal -p 6380 KEYS 'chise:feature_flags:governance:*'

# Get all governance flags and values
redis-cli -h host.docker.internal -p 6380 HGETALL chise:feature_flags:governance
```

**Expected Results:**
- Keys exist for governance feature flags
- Critical flags are enabled:
  - `reflection_enabled`: `true`
  - `memory_promotion_enabled`: `true`
  - `memory_sweep_enabled`: `true`
  - `consolidation_enabled`: `true`
  - `contradiction_detection_enabled`: `true`

#### 3. Trigger Manual Reflection Execution

```bash
cd /home/tacopants/projects/ChiseAI

# Run weekly reflection in dry-run mode (safe test)
python3 scripts/evaluation/run_weekly_reflection.py --week $(date +%Y-W%V) --dry-run

# Run weekly reflection for real
python3 scripts/evaluation/run_weekly_reflection.py --week $(date +%Y-W%V)

# Run with LLM insights enabled (requires LLM provider config)
python3 scripts/evaluation/run_weekly_reflection.py --week $(date +%Y-W%V) --use-llm
```

**Expected Results:**
- Dry-run: Shows artifact preview without writing files
- Real run: Creates artifact file in `_bmad-output/brain-eval/reflections/weekly/`
- LLM run: Attempts LLM calls (may fallback if providers unavailable)

#### 4. Verify Artifacts Generated

```bash
# List generated artifacts
ls -la _bmad-output/brain-eval/reflections/weekly/

# View artifact content
cat _bmad-output/brain-eval/reflections/weekly/$(date +%Y-W%V).json | jq .

# Check for LLM insights (if --use-llm was used)
cat _bmad-output/brain-eval/reflections/weekly/$(date +%Y-W%V).json | jq '.llm_insights, .llm_executive_summary'
```

**Expected Results:**
- Artifact file exists: `YYYY-WXX.json`
- Valid JSON structure with required fields:
  - `story_id`
  - `reflection_type`
  - `timestamp`
  - `what_changed`
  - `kpi_snapshot`
  - `weekly_content`

#### 5. Verify Redis Reflection Entries

```bash
# Check for reflection keys in Redis
redis-cli -h host.docker.internal -p 6380 KEYS 'bmad:chiseai:reflection:*'

# Get specific weekly reflection entry
redis-cli -h host.docker.internal -p 6380 GET bmad:chiseai:reflection:macro:weekly:$(date +%Y-W%V)
```

**Note:** Redis reflection entries are created by the scheduler's storage layer, not directly by the weekly reflection script.

#### 6. Run Conformance Tests

```bash
# Run LLM conformance tests
python3 -m pytest tests/test_governance/test_reflection_llm_conformance.py -v --tb=short

# Run reflection unit tests
python3 -m pytest tests/unit/governance/test_reflection.py -v --tb=short
```

**Expected Results:**
- All tests pass (24 conformance tests + 53 unit tests)
- No failures or errors

#### 7. Verify LLM Structure Conformance

```bash
# Verify no direct provider imports
python3 -c "
import ast
import sys

with open('src/governance/reflection/llm_integration.py', 'r') as f:
    tree = ast.parse(f.read())

for node in ast.walk(tree):
    if isinstance(node, ast.ImportFrom):
        module = node.module or ''
        # Only provider_chain from src.llm is allowed
        if 'llm' in module and module not in ['src.llm', 'src.llm.provider_chain']:
            print(f'WARNING: Direct import from {module}')
            sys.exit(1)

print('✓ LLM integration uses provider_chain pattern')
"

# Verify LLM calls go through provider chain
python3 -c "
from src.governance.reflection.llm_integration import ReflectionLLMIntegration
import inspect

source = inspect.getsource(ReflectionLLMIntegration.generate_llm_insights)

if 'LLMProviderChain' in source:
    print('✓ Uses LLMProviderChain for LLM calls')
else:
    print('✗ Does not use LLMProviderChain')
"
```

---

## Troubleshooting

### Container Won't Start

**Symptom:** Container exits immediately after start

**Diagnosis:**
```bash
# Check container logs
docker logs chiseai-brain-scheduler

# Check if network exists
docker network ls | grep chiseai

# Check if Redis is accessible
docker exec chiseai-brain-scheduler nc -zv chiseai-redis 6380
```

**Resolution:**
1. Ensure `chiseai` network exists: `docker network create chiseai`
2. Check Redis connectivity
3. Verify volume permissions

### Health Check Failing

**Symptom:** Container shows as `unhealthy`

**Diagnosis:**
```bash
# Check health check logs
docker inspect --format='{{json .State.Health}}' chiseai-brain-scheduler | jq

# Test health endpoint manually
docker exec chiseai-brain-scheduler curl -v http://localhost:8080/health
```

**Resolution:**
1. Check if scheduler process is running: `docker exec chiseai-brain-scheduler ps aux`
2. Review application logs: `docker logs chiseai-brain-scheduler --tail 100`
3. Restart container: `docker restart chiseai-brain-scheduler`

### Redis Connection Issues

**Symptom:** Scheduler cannot connect to Redis

**Diagnosis:**
```bash
# Test Redis connectivity from container
docker exec chiseai-brain-scheduler nc -zv chiseai-redis 6380

# Check Redis from host
redis-cli -h host.docker.internal -p 6380 ping
```

**Resolution:**
1. Verify Redis container is running: `docker ps | grep redis`
2. Check network connectivity: `docker network inspect chiseai`
3. Verify Redis credentials and database

### Port Conflicts

**Symptom:** Cannot bind to port 8080

**Diagnosis:**
```bash
# Check what's using port 8080
sudo netstat -tlnp | grep 8080
sudo lsof -i :8080
```

**Resolution:**
1. The scheduler uses port 8080 internally only (not exposed to host)
2. If you need external access, modify docker-compose to add port mapping:
   ```yaml
   ports:
     - "8080:8080"
   ```

### High Memory Usage

**Symptom:** Container using more than 512MB memory

**Diagnosis:**
```bash
# Check memory usage
docker stats chiseai-brain-scheduler --no-stream

# Check for memory leaks in logs
docker logs chiseai-brain-scheduler | grep -i memory
```

**Resolution:**
1. Increase memory limit in docker-compose.yml
2. Check for runaway processes in container
3. Restart container to clear memory

### Scheduler Jobs Not Running

**Symptom:** No output files in `_bmad-output/brain-eval/scheduler`

**Diagnosis:**
```bash
# Check scheduler logs
docker logs chiseai-brain-scheduler --tail 100

# Verify output directory exists
docker exec chiseai-brain-scheduler ls -la /app/_bmad-output/brain-eval/scheduler/

# Check feature flags
redis-cli -h host.docker.internal -p 6380 HGETALL chise:feature_flags:governance
```

**Resolution:**
1. Ensure feature flags are enabled (see [Feature Flag Enablement](#feature-flag-enablement))
2. Check scheduler state in logs
3. Verify volume mounts are correct

### Container Restart Loop

**Symptom:** Container keeps restarting

**Diagnosis:**
```bash
# Check restart count
docker inspect --format='{{.RestartCount}}' chiseai-brain-scheduler

# Check last exit code
docker inspect --format='{{.State.ExitCode}}' chiseai-brain-scheduler
```

**Resolution:**
1. Check logs for error messages
2. Verify all dependencies are available
3. Temporarily disable restart policy for debugging:
   ```bash
   docker update --restart=no chiseai-brain-scheduler
   ```

### LLM Integration Failures

**Symptom:** LLM insights not being generated or timeouts

**Diagnosis:**
```bash
# Check if LLM integration is available
python3 -c "from src.governance.reflection.llm_integration import ReflectionLLMIntegration; print('✓ LLM integration available')"

# Run weekly reflection with verbose logging
python3 scripts/evaluation/run_weekly_reflection.py --week $(date +%Y-W%V) --use-llm 2>&1 | head -50
```

**Resolution:**
1. LLM integration has graceful fallback - it will use deterministic insights if LLM fails
2. Check LLM provider configuration in environment variables
3. Verify API keys are set for KIMI, Zhipu, or other providers
4. The system will work without LLM - insights will be generated from trend data

### Artifact Generation Failures

**Symptom:** Weekly reflection runs but no artifact file created

**Diagnosis:**
```bash
# Check output directory permissions
ls -la _bmad-output/brain-eval/reflections/weekly/

# Run with dry-run to see what would be generated
python3 scripts/evaluation/run_weekly_reflection.py --week $(date +%Y-W%V) --dry-run

# Check for errors in output
python3 scripts/evaluation/run_weekly_reflection.py --week $(date +%Y-W%V) 2>&1
```

**Resolution:**
1. Ensure output directory exists: `mkdir -p _bmad-output/brain-eval/reflections/weekly`
2. Check write permissions on output directory
3. Verify previous week rollup exists in `_bmad-output/brain-eval/trends/`

---

## Rollback Procedures

### Rollback Scheduler to Previous Version

If a deployment causes issues, roll back to the previous stable version:

```bash
# Stop current container
docker compose -f infrastructure/docker/docker-compose.scheduler.yml down

# Remove current container
docker rm chiseai-brain-scheduler

# Pull previous image (if using registry)
docker pull chiseai-brain-scheduler:previous-tag

# Or rebuild from previous commit
git checkout <previous-commit>
docker compose -f infrastructure/docker/docker-compose.scheduler.yml build

# Start with previous version
docker compose -f infrastructure/docker/docker-compose.scheduler.yml up -d
```

### Disable Feature Flags (Emergency)

If governance features are causing issues, disable them immediately:

```bash
# Disable all governance feature flags
redis-cli -h host.docker.internal -p 6380 HSET chise:feature_flags:governance \
  reflection_enabled false \
  memory_promotion_enabled false \
  memory_sweep_enabled false \
  consolidation_enabled false \
  contradiction_detection_enabled false

# Verify flags are disabled
redis-cli -h host.docker.internal -p 6380 HGETALL chise:feature_flags:governance
```

### Restore from Backup

If artifacts or data are corrupted:

```bash
# Stop scheduler
docker stop chiseai-brain-scheduler

# Restore artifacts from backup (if available)
cp -r /backup/brain-eval/reflections/weekly/* _bmad-output/brain-eval/reflections/weekly/

# Restart scheduler
docker start chiseai-brain-scheduler
```

### Complete Reset

**WARNING:** This deletes all scheduler data and state.

```bash
# Stop and remove container
docker compose -f infrastructure/docker/docker-compose.scheduler.yml down

# Remove volumes (deletes all output data)
docker volume rm docker_brain-scheduler-output docker_brain-scheduler-logs 2>/dev/null || true

# Remove local output directory
rm -rf _bmad-output/brain-eval/reflections/weekly/*

# Rebuild and restart
docker compose -f infrastructure/docker/docker-compose.scheduler.yml up -d --build
```

---

## Verification Commands Reference

### Quick Status Check

```bash
# One-liner status check
echo "=== Scheduler Status ===" && docker ps --filter name=chiseai-brain-scheduler --format "table {{.Names}}\t{{.Status}}" && echo && echo "=== Health ===" && docker exec chiseai-brain-scheduler curl -s http://localhost:8080/health | jq -r '.status' && echo && echo "=== Feature Flags ===" && redis-cli -h host.docker.internal -p 6380 HMGET chise:feature_flags:governance reflection_enabled memory_promotion_enabled consolidation_enabled
```

### Test Weekly Reflection

```bash
# Quick test with dry-run
python3 scripts/evaluation/run_weekly_reflection.py --week $(date +%Y-W%V) --dry-run 2>&1 | tail -20
```

### Check Recent Artifacts

```bash
# List last 5 artifacts
ls -lt _bmad-output/brain-eval/reflections/weekly/ | head -6
```

---

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2026-03-03 | Initial runbook creation with Docker-first deployment | ST-REFLECT-RUNTIME-001 |
| 2026-03-03 | Added live validation checklist and troubleshooting section | ST-REFLECT-RUNTIME-001 |
