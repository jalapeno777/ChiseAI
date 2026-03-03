# BrainEval Scheduler Documentation

## Overview

The BrainEval Scheduler is a container-native scheduling system for BrainEval KPI cadence jobs. It provides a safer alternative to Woodpecker for running periodic evaluation cycles.

## Purpose

The scheduler manages three evaluation cadences:
- **6h Cycle**: Mini ingest/eval (every 6 hours)
- **Daily Cycle**: Trend rollups + daily reflection (every 24 hours)
- **Weekly Cycle**: Deep reflection (every 7 days)

## Architecture

The scheduler consists of:

1. **KPI Scheduler Core** (`scripts/evaluation/kpi_scheduler.py`)
   - State machine with checkpointing
   - HTTP health check endpoint
   - Graceful shutdown handling
   - Docker-safe while/sleep loop

2. **Container Image** (`infrastructure/docker/Dockerfile.scheduler`)
   - Based on python:3.11-slim
   - Includes cron and curl for health checks
   - Runs as non-root user
   - Exposes health check on port 8080

3. **Docker Compose** (`infrastructure/docker/docker-compose.scheduler.yml`)
   - Service: `brain-scheduler`
   - Network: `chiseai` (external)
   - Persistent volumes for output and logs
   - Health check and restart policies

## Quick Start

### Build the Container

```bash
docker build -f infrastructure/docker/Dockerfile.scheduler -t chiseai-brain-scheduler:latest .
```

### Run with Docker Compose

```bash
cd infrastructure/docker
docker-compose -f docker-compose.scheduler.yml up -d
```

### Check Health

```bash
# From inside the container network
curl http://chiseai-brain-scheduler:8080/health

# From host (if port is mapped)
curl http://localhost:8080/health
```

### View Logs

```bash
docker logs -f chiseai-brain-scheduler
```

## Documentation

- [Configuration](configuration.md) - Environment variables and options
- [Architecture](architecture.md) - Component diagram and data flow

## Safety Features

- **No systemd dependencies**: Pure Python with while/sleep loop
- **Idempotent operations**: All cycles check before write
- **Non-destructive**: Never deletes data, only appends
- **Graceful shutdown**: Handles SIGTERM/SIGINT properly
- **State persistence**: Checkpoint file survives restarts
- **Health monitoring**: HTTP endpoint for container orchestration

## Related Components

- `scripts/evaluation/run_mini_eval.py` - 6h cycle implementation
- `scripts/evaluation/run_daily_trends.py` - Daily cycle implementation
- `scripts/evaluation/run_weekly_reflection.py` - Weekly cycle implementation
