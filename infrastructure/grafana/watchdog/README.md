# Grafana Dashboard Watchdog

Auto-discovery framework for Grafana dashboards. Monitors the dashboard provisioning directory and automatically reloads Grafana when changes are detected.

## Overview

The watchdog solves the problem of Grafana requiring a restart to pick up new dashboard JSON files. It monitors the `infrastructure/grafana/provisioning/dashboards/` directory and triggers Grafana's provisioning reload API when files are added, modified, or deleted.

## Features

- **Real-time monitoring**: Detects file changes within 5 seconds
- **Multiple deployment options**: Systemd service or Docker sidecar
- **Debounced reloads**: Prevents excessive API calls with configurable debounce
- **Comprehensive logging**: Detailed logs for troubleshooting
- **Health checks**: Validates Grafana connectivity before operations
- **Authentication support**: Works with basic auth or API keys

## Quick Start

### Option 1: Docker Sidecar (Recommended)

```bash
cd infrastructure/grafana/watchdog
docker-compose up -d
```

### Option 2: Systemd Service

```bash
# Copy service file
sudo cp infrastructure/grafana/watchdog/chiseai-grafana-watchdog.service /etc/systemd/system/

# Create environment file
sudo mkdir -p /etc/chiseai
sudo tee /etc/chiseai/grafana-watchdog.env << EOF
GRAFANA_URL=http://localhost:3001
GRAFANA_USER=admin
GRAFANA_PASSWORD=your-password
EOF

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable chiseai-grafana-watchdog
sudo systemctl start chiseai-grafana-watchdog
```

### Option 3: Manual Script

```bash
# Using the management script
./infrastructure/grafana/watchdog/watchdog.sh start

# Or directly with Python
python3 scripts/grafana-watchdog.py
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GRAFANA_URL` | `http://host.docker.internal:3001` | Grafana base URL |
| `GRAFANA_USER` | `admin` | Grafana admin username |
| `GRAFANA_PASSWORD` | `admin` | Grafana admin password |
| `GRAFANA_API_KEY` | - | Optional API key (overrides basic auth) |
| `DASHBOARDS_PATH` | `infrastructure/grafana/provisioning/dashboards` | Path to monitor |
| `WATCHDOG_LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `WATCHDOG_DEBOUNCE_SECONDS` | `5` | Seconds to wait before reloading |

### JSON Config File

Create a config file and pass it with `--config`:

```json
{
  "grafana_url": "http://grafana:3001",
  "grafana_user": "admin",
  "grafana_password": "admin",
  "dashboards_path": "/etc/grafana/provisioning/dashboards",
  "debounce_seconds": 5.0,
  "log_level": "INFO"
}
```

Usage:
```bash
python3 scripts/grafana-watchdog.py --config /path/to/config.json
```

## Management Commands

### Using watchdog.sh

```bash
./infrastructure/grafana/watchdog/watchdog.sh [command]

Commands:
  start   - Start the watchdog daemon
  stop    - Stop the watchdog daemon
  restart - Restart the watchdog daemon
  status  - Check watchdog status and view recent logs
  logs    - Watch the log file in real-time
  test    - Run tests and environment checks
```

### Using Systemd

```bash
# Check status
sudo systemctl status chiseai-grafana-watchdog

# View logs
sudo journalctl -u chiseai-grafana-watchdog -f

# Restart
sudo systemctl restart chiseai-grafana-watchdog
```

### Using Docker Compose

```bash
cd infrastructure/grafana/watchdog

# Start
docker-compose up -d

# View logs
docker-compose logs -f grafana-watchdog

# Restart
docker-compose restart grafana-watchdog

# Stop
docker-compose down
```

## Testing

Run the test suite:

```bash
pytest tests/test_ops/test_grafana_watchdog.py -v
```

Manual test:

```bash
# 1. Start the watchdog
./infrastructure/grafana/watchdog/watchdog.sh start

# 2. Create a new dashboard
cp infrastructure/grafana/provisioning/dashboards/data-freshness.json \
   infrastructure/grafana/provisioning/dashboards/test-new-dashboard.json

# 3. Check that it appears in Grafana (within 30 seconds)
curl http://host.docker.internal:3001/api/search | jq '.[].title'

# 4. Delete the test dashboard
rm infrastructure/grafana/provisioning/dashboards/test-new-dashboard.json

# 5. Verify it disappears from Grafana
```

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Dashboard JSON │────▶│  Watchdog        │────▶│  Grafana API    │
│  Files          │     │  (File Watcher)  │     │  /api/admin/    │
└─────────────────┘     └──────────────────┘     │  provisioning/  │
                                                  │  dashboards/    │
                                                  │  reload         │
                                                  └─────────────────┘
```

## Troubleshooting

### Watchdog can't connect to Grafana

1. Verify Grafana is running:
   ```bash
   curl http://host.docker.internal:3001/api/health
   ```

2. Check credentials:
   ```bash
   curl -u admin:admin http://host.docker.internal:3001/api/org
   ```

3. For Docker sidecar, ensure both containers are on the same network:
   ```bash
   docker network inspect chiseai
   ```

### Changes not being detected

1. Check the watchdog is running:
   ```bash
   ./infrastructure/grafana/watchdog/watchdog.sh status
   ```

2. Verify the dashboards path:
   ```bash
   ls -la infrastructure/grafana/provisioning/dashboards/
   ```

3. Check logs for errors:
   ```bash
   tail -f /tmp/grafana-watchdog.log
   ```

### Reload API returns 404

The provisioning reload API may not be available in older Grafana versions. The watchdog will log a warning and continue monitoring. Grafana will still pick up changes on the next restart.

## Files

- `scripts/grafana-watchdog.py` - Main watchdog script
- `infrastructure/grafana/watchdog/Dockerfile` - Docker image definition
- `infrastructure/grafana/watchdog/docker-compose.yml` - Docker Compose setup
- `infrastructure/grafana/watchdog/chiseai-grafana-watchdog.service` - Systemd service file
- `infrastructure/grafana/watchdog/watchdog.sh` - Management script
- `infrastructure/grafana/watchdog/requirements.txt` - Python dependencies
- `tests/test_ops/test_grafana_watchdog.py` - Test suite

## Related Stories

- ST-OPS-005: Grafana Dashboard Provisioning Infrastructure
- ST-OPS-001: Grafana Dashboard Implementation
