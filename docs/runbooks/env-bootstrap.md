---
title: Environment Bootstrap Runbook
category: development
severity: informational
estimated_time_to_read: 10 minutes
last_updated: 2026-02-18
maintainers: dev-team
story_id: ST-ENV-001
executable: false
---

# Environment Bootstrap Runbook

## Overview

The environment bootstrap system provides **consistent environment loading** for standalone scripts and LLM modules across the ChiseAI codebase.

### Purpose

- Ensure environment variables are loaded before any LLM provider imports
- Provide a standardized way to load `.env` files across different contexts (scripts, Docker, cron)
- Enable diagnostic checks for provider availability
- Support multiple LLM providers with fallback chains

### Precedence Rules

Environment variables are resolved in the following order (highest to lowest):

1. **Process Environment Variables** - Already set in the shell/process
2. **Explicit Env File** - Specified via `--env-file` or `env_file` parameter
3. **Default .env File** - Auto-discovered in standard locations:
   - `./.env` (current directory)
   - `../.env` (parent directory)
   - `REPO_ROOT/.env` (repository root)
   - `~/.chiseai/.env` (user config directory)

> **Important**: Variables already set in the process environment are **never overwritten** by `.env` files. This allows command-line overrides like `KIMI_API_KEY=xxx python script.py`.

---

## Quick Start

### For Python Scripts

Import and call `bootstrap()` at the very top of your script, **before any other imports**:

```python
#!/usr/bin/env python3
"""My standalone script."""

import sys
import os

# Add src to path (adjust based on script location)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Bootstrap environment FIRST
from config.bootstrap import bootstrap
bootstrap()

# NOW safe to import LLM providers
from config import get_available_providers
providers = get_available_providers()
```

### For CLI Diagnostics

Use `check_env.py` to verify your environment:

```bash
# Basic check
python scripts/check_env.py

# Verbose output
python scripts/check_env.py --verbose

# Check specific env file
python scripts/check_env.py --env-file /path/to/.env
```

**Exit codes:**
- `0` - At least one provider available
- `1` - No providers available
- `2` - Error occurred

### For Docker

Mount your `.env` file and/or pass environment variables:

```bash
# Mount .env file
docker run -v $(pwd)/.env:/app/.env myimage

# Pass environment variables
docker run -e KIMI_API_KEY=$KIMI_API_KEY myimage

# Both
docker run -v $(pwd)/.env:/app/.env -e KIMI_API_KEY=$KIMI_API_KEY myimage
```

Verify with:
```bash
docker run --rm myimage python scripts/check_env.py
```

---

## Script Usage

### Basic Bootstrap Pattern

```python
#!/usr/bin/env python3
"""Example script showing proper bootstrap usage."""

import sys
import os
from pathlib import Path

# Add src to Python path
script_dir = Path(__file__).parent
src_dir = script_dir.parent / "src"
sys.path.insert(0, str(src_dir))

# Bootstrap environment BEFORE any LLM imports
from config.bootstrap import bootstrap
bootstrap()

# Now safe to import LLM providers
from config import get_available_providers

# Check available providers
providers = get_available_providers()
print(f"Available providers: {providers}")
```

### With Verbose Logging

```python
from config.bootstrap import bootstrap

# Enable verbose output to see loaded files
state = bootstrap(verbose=True)

# Access bootstrap state
print(f"Loaded files: {state['loaded_files']}")
print(f"Provider status: {state['providers']}")
```

### With Explicit Env File

```python
from pathlib import Path
from config.bootstrap import bootstrap

# Load specific env file
env_file = Path("/path/to/custom.env")
state = bootstrap(env_file=env_file)
```

### Skip Env File Loading

```python
from config.bootstrap import bootstrap

# Don't load any .env files (use only process env)
state = bootstrap(load_env=False)
```

### Accessing Bootstrap State

```python
from config.bootstrap import get_bootstrap_state, format_provider_status

# Get current state
state = get_bootstrap_state()

# Format provider status for display
for name, status in state['providers'].items():
    print(f"{name}: {format_provider_status(status)}")
```

---

## Docker Usage

### Docker Run

```bash
# Basic: Mount .env file
docker run \
  -v $(pwd)/.env:/app/.env \
  myimage \
  python scripts/my_script.py

# With environment variables
docker run \
  -v $(pwd)/.env:/app/.env \
  -e KIMI_API_KEY=$KIMI_API_KEY \
  -e KIMI_MODEL=k2p5 \
  myimage \
  python scripts/my_script.py

# Verify environment before running
docker run --rm \
  -v $(pwd)/.env:/app/.env \
  myimage \
  python scripts/check_env.py
```

### Docker Compose

```yaml
version: '3.8'

services:
  myapp:
    image: myimage
    env_file:
      - .env
    environment:
      # Override specific variables
      KIMI_MODEL: k2p5
      KIMI_ENABLED: "true"
    volumes:
      # Alternative: mount .env explicitly
      - ./.env:/app/.env:ro
    command: python scripts/my_script.py
```

### Dockerfile Best Practices

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Copy application code
COPY src/ ./src/
COPY scripts/ ./scripts/

# Don't copy .env - mount at runtime
# COPY .env .env  # ❌ WRONG - never commit .env

# Set Python path
ENV PYTHONPATH=/app/src:$PYTHONPATH

# Default command runs check first
CMD ["python", "scripts/check_env.py"]
```

### Docker Verification

```bash
# Check if environment is properly loaded
docker run --rm myimage python scripts/check_env.py

# Expected output:
# Environment Bootstrap Diagnostic
# ========================================
# 
# Env files loaded:
#   - /app/.env
# 
# Provider Availability:
#   KIMI: available (via KIMI_API_KEY)
#   MINIMAX: disabled (MINIMAX_ENABLED != true)
#   ZAI: not available (ZAI_API_KEY, ZAI_API_KEY_PRIMARY not set)
#   ZHIPU: not available (ZHIPU_API_KEY not set)
# 
# Summary: 1/4 providers available
```

---

## Cron Usage

### The Problem

Cron jobs run with a **minimal environment** - often missing:
- `PATH` variables
- Home directory context
- Environment variables from your shell

### Solution 1: Source .env in Crontab

```bash
# Edit crontab
crontab -e

# Source .env before running script
0 9 * * * cd /path/to/repo && . .env && python scripts/my_script.py

# Or use full paths
0 9 * * * cd /path/to/repo && . .env && /usr/bin/python3 scripts/my_script.py
```

### Solution 2: Use check_env.py as Preflight

```bash
# Check environment before running (fails fast if misconfigured)
0 9 * * * cd /path/to/repo && python scripts/check_env.py && python scripts/my_script.py

# With logging
0 9 * * * cd /path/to/repo && python scripts/check_env.py >> /var/log/myapp/env.log 2>&1 && python scripts/my_script.py
```

### Solution 3: Wrapper Script

Create a wrapper script that handles environment setup:

```bash
#!/bin/bash
# scripts/cron_wrapper.sh

set -e

# Change to repo directory
cd "$(dirname "$0")/.."

# Source .env if it exists
if [ -f .env ]; then
    set -a  # Automatically export all variables
    source .env
    set +a
fi

# Verify environment
python scripts/check_env.py

# Run the actual script
python "$@"
```

Make it executable and use in crontab:
```bash
chmod +x scripts/cron_wrapper.sh
```

```bash
# Crontab entry
0 9 * * * /path/to/repo/scripts/cron_wrapper.sh scripts/my_script.py
```

### Solution 4: Full Environment in Crontab

```bash
# Set full environment in crontab
SHELL=/bin/bash
PATH=/usr/local/bin:/usr/bin:/bin
HOME=/home/username

# Environment variables
KIMI_API_KEY=your_key_here
KIMI_MODEL=k2p5
KIMI_ENABLED=true

# Job
0 9 * * * cd /path/to/repo && python scripts/my_script.py
```

### Cron Troubleshooting

```bash
# Test cron environment
* * * * * env > /tmp/cron_env.txt 2>&1

# Compare with your shell
env > /tmp/shell_env.txt
diff /tmp/shell_env.txt /tmp/cron_env.txt

# Check script output
tail -f /var/log/syslog | grep CRON
# or
tail -f /var/log/cron.log
```

---

## Environment Variable Reference

### KIMI (Primary Provider)

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `KIMI_API_KEY` | API key for KIMI | - | Yes (unless using alternative) |
| `KIMI_API_KEY_PRIMARY` | Alternative key name | - | No |
| `KIMI_ENABLED` | Enable/disable KIMI | `true` | No |
| `KIMI_MODEL` | Model to use | `k2p5` | No |
| `KIMI_BASE_URL` | API endpoint | `https://api.kimi.com/coding/v1` | No |
| `KIMI_TIMEOUT` | Request timeout (seconds) | `30.0` | No |
| `KIMI_MAX_RETRIES` | Retry attempts | `3` | No |
| `KIMI_RETRY_DELAY` | Delay between retries | `1.0` | No |

### Z.ai / Zhipu (Secondary Provider)

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `ZAI_API_KEY` | API key for Z.ai | - | Yes (if using ZAI) |
| `ZAI_API_KEY_PRIMARY` | Alternative key name | - | No |
| `ZHIPU_API_KEY` | API key for Zhipu | - | Yes (if using Zhipu) |
| `ZAI_ENABLED` | Enable/disable ZAI | `true` | No |
| `ZHIPU_ENABLED` | Enable/disable Zhipu | `true` | No |

> **Note**: `ZAI_API_KEY` can be used as a proxy for `ZHIPU_API_KEY` (fallback chain).

### MiniMax (Fallback Provider)

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `MINIMAX_API_KEY` | API key for MiniMax | - | Yes (if enabled) |
| `MINIMAX_ENABLED` | Enable/disable MiniMax | `false` | No |

> **Note**: MiniMax is **disabled by default**. Set `MINIMAX_ENABLED=true` to enable.

### Gitea (Repository Operations)

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `GITEA_BASE_URL` | Gitea instance URL | `http://host.docker.internal:3000` | Yes |
| `GITEA_OWNER` | Repository owner | `craig` | Yes |
| `GITEA_REPO` | Repository name | `ChiseAI` | Yes |
| `GITEA_TOKEN` | PAT for PR operations | - | Yes |
| `GITEA_REVIEW_TOKEN` | PAT for PR reviews | - | Yes |

### Discord (Notifications)

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `DISCORD_BOT_TOKEN` | Bot authentication | - | Yes (if using bot) |
| `DISCORD_WEBHOOK_URL` | Webhook URL | - | Yes (if using webhook) |
| `DISCORD_DEFAULT_CHANNEL` | Default channel | `trading-signals` | No |
| `DISCORD_GUILD_ID` | Restrict to guild | - | No |

### Infrastructure

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `REDIS_HOST` | Redis server host | `chiseai-redis` | No |
| `REDIS_PORT` | Redis server port | `6380` | No |
| `POSTGRES_HOST` | PostgreSQL host | `chiseai-postgres` | No |
| `POSTGRES_PORT` | PostgreSQL port | `5434` | No |

---

## Troubleshooting

### Provider Not Found

**Symptom:**
```
Provider Availability:
  KIMI: not available (KIMI_API_KEY not set)
```

**Solutions:**
1. Check environment variable name (case-sensitive)
2. Verify `.env` file is being loaded: `bootstrap(verbose=True)`
3. Check if variable is set in process: `echo $KIMI_API_KEY`
4. Ensure no typos in variable name

### Wrong Precedence

**Symptom:** Script uses wrong API key despite `.env` having correct value.

**Cause:** Process environment variables take precedence over `.env` files.

**Solution:**
```bash
# Check if already set in environment
echo $KIMI_API_KEY

# Unset if needed
unset KIMI_API_KEY

# Or override for single command
KIMI_API_KEY=new_value python script.py
```

### Docker Issues

**Symptom:** Environment variables not available in container.

**Solutions:**

1. **Verify mount path:**
   ```bash
   docker run --rm -v $(pwd)/.env:/app/.env myimage cat /app/.env
   ```

2. **Check file permissions:**
   ```bash
   ls -la .env
   # Should be readable by container user
   ```

3. **Use absolute paths:**
   ```bash
   docker run -v /absolute/path/to/.env:/app/.env myimage
   ```

4. **Verify with check_env.py:**
   ```bash
   docker run --rm -v $(pwd)/.env:/app/.env myimage python scripts/check_env.py
   ```

### Cron Issues

**Symptom:** Script works manually but fails in cron.

**Solutions:**

1. **Check working directory:**
   ```bash
   # Always use absolute paths or cd first
   0 9 * * * cd /path/to/repo && python scripts/my_script.py
   ```

2. **Source .env explicitly:**
   ```bash
   0 9 * * * cd /path/to/repo && . .env && python scripts/my_script.py
   ```

3. **Use full Python path:**
   ```bash
   0 9 * * * cd /path/to/repo && /usr/bin/python3 scripts/my_script.py
   ```

4. **Check cron environment:**
   ```bash
   * * * * * env > /tmp/cron_env.txt
   ```

### Bootstrap Called Too Late

**Symptom:** Import error when loading LLM providers.

**Cause:** Bootstrap must be called **before** importing LLM modules.

**Wrong:**
```python
from config import get_available_providers  # ❌ Too early
from config.bootstrap import bootstrap
bootstrap()
```

**Correct:**
```python
from config.bootstrap import bootstrap
bootstrap()  # ✅ Bootstrap first
from config import get_available_providers  # ✅ Now safe
```

### Multiple Bootstrap Calls

**Symptom:** Warnings about multiple bootstrap calls.

**Solution:** Bootstrap is idempotent but logs warnings. Call once at script entrypoint:

```python
def main():
    bootstrap()  # Call here
    # ... rest of script

if __name__ == "__main__":
    main()
```

---

## Security Notes

### Never Commit .env Files

`.env` files are listed in `.gitignore`:
```
# .gitignore
.env
.env.local
.env.*.local
```

**If you accidentally commit an .env file:**
```bash
# 1. Remove from git history
git rm --cached .env
git commit -m "Remove .env from repository"

# 2. Rotate any exposed secrets immediately

# 3. Force push (if not on main branch)
git push --force-with-lease
```

### Use Process Environment Variables in Production

**Development:**
```bash
# Use .env file
python scripts/my_script.py
```

**Production:**
```bash
# Use process environment (more secure)
export KIMI_API_KEY=$(cat /run/secrets/kimi_key)
python scripts/my_script.py
```

**Docker Secrets (Swarm/Kubernetes):**
```yaml
# docker-compose.yml
secrets:
  kimi_api_key:
    external: true

services:
  myapp:
    secrets:
      - kimi_api_key
    environment:
      KIMI_API_KEY_FILE: /run/secrets/kimi_api_key
```

### check_env.py Never Reveals Key Values

The diagnostic script only shows:
- Which environment variables are **set** (not their values)
- File paths of loaded `.env` files
- Provider availability status

**Safe to run in:**
- CI/CD logs
- Shared terminals
- Debug output

### Bootstrap Logs File Paths, Not Values

When `verbose=True`, bootstrap logs:
```
INFO: Loaded env file: /path/to/.env  # ✅ Safe
```

Not:
```
INFO: KIMI_API_KEY=sk-xxx...  # ❌ Never happens
```

### Example .env.example

Use `.env.example` as a template (no real secrets):

```bash
# Copy to .env and fill with real values
cp .env.example .env

# Edit .env with your secrets
nano .env
```

See `.env.example` for the current template.

---

## Related Documentation

- [LLM Configuration](../llm-configuration.md) - Provider-specific setup
- [CI/CD Gitea Woodpecker](../ci-cd-gitea-woodpecker.md) - CI environment setup
- `.env.example` - Environment variable template

## API Reference

### `bootstrap()`

```python
def bootstrap(
    load_env: bool = True,
    env_file: Path | None = None,
    verbose: bool = False,
) -> dict[str, Any]
```

**Parameters:**
- `load_env` - Whether to load `.env` files (default: True)
- `env_file` - Specific env file to load (default: auto-discover)
- `verbose` - Enable verbose logging (default: False)

**Returns:**
Dictionary with:
- `loaded_files`: List of loaded env file paths
- `providers`: Dictionary of provider availability status

### `get_bootstrap_state()`

```python
def get_bootstrap_state() -> dict[str, Any]
```

Returns the current bootstrap state (same format as `bootstrap()` return value).

### `format_provider_status()`

```python
def format_provider_status(status: dict[str, Any]) -> str
```

Formats provider status for display without revealing secrets.

---

## Quick Reference

### One-Liners

```bash
# Check environment
python scripts/check_env.py

# Bootstrap in Python
python -c "from config.bootstrap import bootstrap; bootstrap(verbose=True)"

# Test with specific env file
python scripts/check_env.py --env-file /path/to/.env

# Docker check
docker run --rm -v $(pwd)/.env:/app/.env myimage python scripts/check_env.py
```

### Common Patterns

| Context | Pattern |
|---------|---------|
| Script | `bootstrap()` at top, before imports |
| Docker | Mount `.env`, verify with `check_env.py` |
| Cron | `cd /path && . .env && python script.py` |
| CI/CD | Use environment variables, not `.env` |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | At least one provider available |
| 1 | No providers available |
| 2 | Error occurred |

---

*Last updated: 2026-02-18 | Story: ST-ENV-001*
