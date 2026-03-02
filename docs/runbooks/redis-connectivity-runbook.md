# Redis Connectivity Runbook

## Overview

This runbook documents how to configure and verify Redis connectivity for the PAPER-RECOVERY-001 loop runner and related scripts.

## Prerequisites

- Docker environment with `chiseai` network
- Redis container running on `chiseai` network
- InfluxDB container running (for metrics)

## Environment Variables

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `INFLUXDB_TOKEN` | **REQUIRED** InfluxDB authentication token | `xBJwtATdOa7Sig8v...` |
| `REDIS_HOST` | Redis server hostname | `host.docker.internal` |
| `REDIS_PORT` | Redis server port | `6380` |

### Optional Variables (with defaults)

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_HOST` | `host.docker.internal` | PostgreSQL host |
| `DB_PORT` | `5434` | PostgreSQL port |
| `INFLUXDB_URL` | `http://host.docker.internal:18087` | InfluxDB URL |
| `INFLUXDB_ORG` | `chiseai` | InfluxDB organization |
| `INFLUXDB_BUCKET` | `chiseai` | InfluxDB bucket |

## Setting INFLUXDB_TOKEN

### Option 1: Export in shell (temporary)

```bash
export INFLUXDB_TOKEN="your-token-here"
```

### Option 2: Create .env file (recommended)

Create `scripts/.env`:

```bash
# InfluxDB Configuration
INFLUXDB_TOKEN=your-token-here

# Redis Configuration
REDIS_HOST=host.docker.internal
REDIS_PORT=6380

# Optional overrides
# DB_HOST=host.docker.internal
# DB_PORT=5434
```

Then source it:

```bash
source scripts/.env
```

### Option 3: Use with scripts/redis_env_fix.sh

The `redis_env_fix.sh` script will validate that `INFLUXDB_TOKEN` is set and fail with a clear error if missing.

## Verifying Redis Connectivity

### Test 1: Direct Redis Connection

```bash
# Using redis-cli from host
redis-cli -h host.docker.internal -p 6380 ping
# Expected: PONG
```

### Test 2: Using redis_env_fix.sh

```bash
# Without token (should fail with clear error)
unset INFLUXDB_TOKEN
./scripts/redis_env_fix.sh
# Expected: ERROR: INFLUXDB_TOKEN environment variable is not set

# With token (should succeed)
export INFLUXDB_TOKEN="your-token"
./scripts/redis_env_fix.sh
# Expected: Redis environment fixed messages
```

### Test 3: Python Script Connection

```bash
source scripts/.env
python3 -c "import redis; r = redis.Redis(host='host.docker.internal', port=6380); print(r.ping())"
# Expected: True
```

## Invocation Path for Loop Runner

### Standard Invocation

```bash
# 1. Set environment
export INFLUXDB_TOKEN="your-token"
export REDIS_HOST="host.docker.internal"
export REDIS_PORT="6380"

# 2. Run with environment fix wrapper
./scripts/redis_env_fix.sh python3 scripts/create_evidence_bundle.py
```

### Using Bootstrap Script

```bash
# 1. Source bootstrap (validates all env vars)
source scripts/bootstrap_paper_recovery.sh

# 2. Run your script
python3 scripts/create_evidence_bundle.py
```

### Docker Context Note

**CRITICAL**: When running inside a Docker container (like this agent environment):
- Use `host.docker.internal` to reach host services
- DO NOT use `localhost` - it refers to the container itself

## Troubleshooting

### "ERROR: INFLUXDB_TOKEN environment variable is not set"

**Cause**: Token not exported or .env file not sourced  
**Fix**: Export the token or source your .env file

### "Connection refused" to Redis

**Cause**: Redis container not running or not on chiseai network  
**Fix**:
```bash
# Check if Redis is running
docker ps --filter name=chiseai-redis

# Check network
docker network inspect chiseai
```

### "ValueError: INFLUXDB_TOKEN environment variable is not set"

**Cause**: Python script validation failed  
**Fix**: Export INFLUXDB_TOKEN before running Python scripts

## Security Notes

- **NEVER** commit tokens to git
- Use `.env` files (already in `.gitignore`)
- The `scripts/.env.example` file shows required variables without values
- All scripts now validate token presence before execution

## Related Files

- `scripts/redis_env_fix.sh` - Environment setup wrapper
- `scripts/bootstrap_paper_recovery.sh` - Bootstrap with validation
- `scripts/.env.example` - Template for environment variables
- `scripts/create_evidence_bundle.py` - Evidence collection script
