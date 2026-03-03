# BrainEval Scheduler Configuration

## Environment Variables

### Redis Connection

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_HOST` | `chiseai-redis` | Redis server hostname |
| `REDIS_PORT` | `6380` | Redis server port |
| `REDIS_DB` | `0` | Redis database number |

### Scheduler Intervals

| Variable | Default | Description |
|----------|---------|-------------|
| `SCHEDULER_INTERVAL_6H` | `21600` | 6h cycle interval in seconds (6 hours) |
| `SCHEDULER_INTERVAL_DAILY` | `86400` | Daily cycle interval in seconds (24 hours) |
| `SCHEDULER_INTERVAL_WEEKLY` | `604800` | Weekly cycle interval in seconds (7 days) |

### Scheduler Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SCHEDULER_OUTPUT_DIR` | `/app/_bmad-output/brain-eval/scheduler` | Output directory for logs and checkpoints |
| `SCHEDULER_HEALTH_PORT` | `8080` | Port for health check HTTP endpoint |
| `SCHEDULER_CHECKPOINT_INTERVAL` | `300` | Checkpoint save interval in seconds |

### Python Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `PYTHONUNBUFFERED` | `1` | Disable Python output buffering |
| `PYTHONPATH` | `/app` | Python module search path |

## Command Line Options

### Running Specific Cycles

```bash
# Run 6h cycle once
python kpi_scheduler.py --cycle 6h

# Run daily cycle once
python kpi_scheduler.py --cycle daily

# Run weekly cycle once
python kpi_scheduler.py --cycle weekly
```

### Daemon Mode

```bash
# Run in daemon mode (continuous scheduling)
python kpi_scheduler.py --daemon

# With custom output directory
python kpi_scheduler.py --daemon --output-dir /custom/path
```

### Dry Run Mode

```bash
# Dry-run all cycles for validation
python kpi_scheduler.py --dry-run-all

# Dry-run specific cycle
python kpi_scheduler.py --cycle 6h --dry-run
```

## Docker Compose Override

Create a `docker-compose.override.yml` for local customization:

```yaml
version: '3.8'

services:
  brain-scheduler:
    environment:
      - SCHEDULER_INTERVAL_6H=3600  # Run 6h cycle every hour for testing
      - SCHEDULER_INTERVAL_DAILY=7200  # Run daily every 2 hours for testing
    volumes:
      - ./local-output:/app/_bmad-output/brain-eval/scheduler
```

## Health Check Endpoints

### GET /health

Returns basic health status:

```json
{
  "status": "healthy",
  "state": "running",
  "timestamp": "2026-03-03T12:00:00Z"
}
```

Status codes:
- `200 OK`: Scheduler is healthy
- `503 Service Unavailable`: Scheduler is in error state

### GET /status

Returns detailed status including checkpoint:

```json
{
  "status": "healthy",
  "state": "running",
  "checkpoint": {
    "state": "running",
    "last_run_6h": 1741000000.0,
    "last_run_daily": 1740900000.0,
    "last_run_weekly": 1740500000.0,
    "cycle_count": 42,
    "error_count": 0,
    "last_error": null,
    "version": "1.0",
    "timestamp": "2026-03-03T12:00:00Z"
  },
  "timestamp": "2026-03-03T12:00:00Z"
}
```

## Checkpoint File

The scheduler persists state to a checkpoint file:

**Location**: `{SCHEDULER_OUTPUT_DIR}/checkpoint.json`

**Format**:
```json
{
  "state": "running",
  "last_run_6h": 1741000000.0,
  "last_run_daily": 1740900000.0,
  "last_run_weekly": 1740500000.0,
  "cycle_count": 42,
  "error_count": 0,
  "last_error": null,
  "version": "1.0",
  "timestamp": "2026-03-03T12:00:00Z"
}
```

The checkpoint survives container restarts and allows the scheduler to resume from where it left off.

## State Machine

The scheduler uses the following states:

| State | Description |
|-------|-------------|
| `initializing` | Starting up, loading checkpoint |
| `running` | Normal operation, scheduling cycles |
| `paused` | Temporarily paused (not currently used) |
| `shutting_down` | Graceful shutdown in progress |
| `error` | Error state, check logs |

## Log Files

### Scheduler Log

**Location**: `{SCHEDULER_OUTPUT_DIR}/scheduler.log`

Contains JSON log entries:
```json
{"timestamp": "2026-03-03T12:00:00Z", "event": "cycle_start", "cycle": "6h", "dry_run": false}
{"timestamp": "2026-03-03T12:05:00Z", "event": "cycle_complete", "cycle": "6h", "success": true, "dry_run": false}
```

### Container Logs

View with Docker:
```bash
docker logs -f chiseai-brain-scheduler
```

## Resource Limits

Default resource limits in Docker Compose:

| Resource | Limit | Reservation |
|----------|-------|-------------|
| CPU | 1.0 cores | 0.25 cores |
| Memory | 512 MB | 128 MB |

Adjust in `docker-compose.scheduler.yml` if needed.

## Troubleshooting

### Scheduler not starting

Check logs:
```bash
docker logs chiseai-brain-scheduler
```

Verify Redis connection:
```bash
docker exec chiseai-brain-scheduler python3 -c "import redis; r = redis.Redis(host='chiseai-redis', port=6380); print(r.ping())"
```

### Health check failing

Check if health endpoint is responding:
```bash
docker exec chiseai-brain-scheduler curl -f http://localhost:8080/health
```

### Cycles not running

Check checkpoint state:
```bash
docker exec chiseai-brain-scheduler cat /app/_bmad-output/brain-eval/scheduler/checkpoint.json
```

Verify intervals are set correctly:
```bash
docker exec chiseai-brain-scheduler env | grep SCHEDULER
```
