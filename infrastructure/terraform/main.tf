locals {
  project_label = "chiseai"
  effective_bybit_demo_api_key = (
    trimspace(var.bybit_demo_api_key) != ""
    ? var.bybit_demo_api_key
    : var.bybit_api_key
  )
  effective_bybit_demo_api_secret = (
    trimspace(var.bybit_demo_api_secret) != ""
    ? var.bybit_demo_api_secret
    : var.bybit_api_secret
  )
}

# ChiseAI Application Containers
# These containers run the core ChiseAI API and Dashboard services

resource "docker_network" "chiseai" {
  name   = "chiseai"
  driver = "bridge"

  ipam_config {
    subnet  = "172.27.0.0/16"
    gateway = "172.27.0.1"
  }
}

resource "docker_volume" "redis" { name = "chiseai-redis-data" }
resource "docker_volume" "postgres" { name = "chiseai-postgres-data" }
resource "docker_volume" "influxdb" { name = "chiseai-influxdb-data" }
resource "docker_volume" "qdrant" { name = "chiseai-qdrant-data" }
resource "docker_volume" "grafana" { name = "chiseai-grafana-data" }
resource "docker_volume" "grafana_datasources" { name = "chiseai-grafana-datasources" }
resource "docker_volume" "gitea" { name = "chiseai-gitea-data" }
resource "docker_volume" "woodpecker" { name = "chiseai-woodpecker-data" }
resource "docker_volume" "woodpecker_tmp" { name = "chiseai-woodpecker-tmp" }
resource "docker_volume" "daily_summary_logs" { name = "chiseai-daily-summary-logs" }

resource "docker_container" "redis" {
  name  = "chiseai-redis"
  image = "redis:7"

  command = ["redis-server", "--port", "6380", "--appendonly", "yes"]

  ports {
    internal = 6380
    external = 6380
  }

  labels {
    label = "project"
    value = local.project_label
  }

  # Docker Desktop groups "apps" primarily by Compose project; we add these labels
  # so Terraform-managed containers are less cluttered in the UI.
  labels {
    label = "com.docker.compose.project"
    value = local.project_label
  }

  labels {
    label = "com.docker.compose.service"
    value = "redis"
  }

  networks_advanced {
    name = docker_network.chiseai.name
  }

  volumes {
    volume_name    = docker_volume.redis.name
    container_path = "/data"
  }
}

resource "docker_container" "postgres" {
  name  = "chiseai-postgres"
  image = "postgres:15"

  env = [
    "POSTGRES_DB=chiseai",
    "POSTGRES_USER=chiseai",
    "POSTGRES_PASSWORD=${var.chise_postgres_password}",
  ]

  command = ["postgres", "-p", "5434"]

  ports {
    internal = 5434
    external = 5434
  }

  labels {
    label = "project"
    value = local.project_label
  }

  labels {
    label = "com.docker.compose.project"
    value = local.project_label
  }

  labels {
    label = "com.docker.compose.service"
    value = "postgres"
  }

  networks_advanced {
    name = docker_network.chiseai.name
  }

  volumes {
    volume_name    = docker_volume.postgres.name
    container_path = "/var/lib/postgresql/data"
  }
}

resource "docker_container" "influxdb" {
  name  = "chiseai-influxdb"
  image = "influxdb:2"

  env = [
    "DOCKER_INFLUXDB_INIT_MODE=setup",
    "DOCKER_INFLUXDB_INIT_ADMIN_TOKEN=${var.influxdb_token}",
    "DOCKER_INFLUXDB_INIT_USERNAME=${var.influxdb_admin_user}",
    "DOCKER_INFLUXDB_INIT_PASSWORD=${var.influxdb_admin_password}",
    "DOCKER_INFLUXDB_INIT_ORG=${var.influxdb_org}",
    "DOCKER_INFLUXDB_INIT_BUCKET=${var.influxdb_bucket}",
    "INFLUXD_HTTP_BIND_ADDRESS=:18087",
  ]

  ports {
    internal = 18087
    external = 18087
  }

  labels {
    label = "project"
    value = local.project_label
  }

  labels {
    label = "com.docker.compose.project"
    value = local.project_label
  }

  labels {
    label = "com.docker.compose.service"
    value = "influxdb"
  }

  networks_advanced {
    name = docker_network.chiseai.name
  }

  volumes {
    volume_name    = docker_volume.influxdb.name
    container_path = "/var/lib/influxdb2"
  }
}

resource "docker_container" "qdrant" {
  name  = "chiseai-qdrant"
  image = "qdrant/qdrant:v1.16.3"

  env = [
    "QDRANT__SERVICE__HTTP_PORT=6334",
  ]

  ports {
    internal = 6334
    external = 6334
  }

  labels {
    label = "project"
    value = local.project_label
  }

  labels {
    label = "com.docker.compose.project"
    value = local.project_label
  }

  labels {
    label = "com.docker.compose.service"
    value = "qdrant"
  }

  networks_advanced {
    name = docker_network.chiseai.name
  }

  volumes {
    volume_name    = docker_volume.qdrant.name
    container_path = "/qdrant/storage"
  }
}

resource "docker_container" "grafana" {
  name  = "chiseai-grafana"
  image = "grafana/grafana:10.4.2"

  env = [
    "GF_SECURITY_ADMIN_PASSWORD=${var.grafana_admin_password}",
    "GF_SERVER_HTTP_PORT=3001",
    "INFLUXDB_TOKEN=${var.influxdb_token}",
    "INFLUXDB_ORG=${var.influxdb_org}",
    "INFLUXDB_BUCKET=${var.influxdb_bucket}",
    # Bootstrap configuration for craig-admin user
    "ADMIN_USER=craig-admin",
    "ADMIN_PASSWORD=${var.grafana_admin_password}",
    "ADMIN_EMAIL=craig@chiseai.local",
    "ADMIN_NAME=Craig Admin",
  ]

  ports {
    internal = 3001
    external = 3001
  }

  labels {
    label = "project"
    value = local.project_label
  }

  labels {
    label = "com.docker.compose.project"
    value = local.project_label
  }

  labels {
    label = "com.docker.compose.service"
    value = "grafana"
  }

  networks_advanced {
    name = docker_network.chiseai.name
  }

  # Persist Grafana data (users, dashboards, etc.) across container recreations
  volumes {
    volume_name    = docker_volume.grafana.name
    container_path = "/var/lib/grafana"
  }

  # TEMPO-2026-001: Mount Tempo datasource provisioning configuration
  volumes {
    volume_name    = docker_volume.grafana_datasources.name
    container_path = "/etc/grafana/provisioning/datasources"
    read_only      = true
  }

}

resource "docker_container" "gitea" {
  name  = "gitea"
  image = "gitea/gitea:1.22.0"

  env = [
    "GITEA__server__ROOT_URL=${var.gitea_root_url}",
    "GITEA__server__HTTP_ADDR=0.0.0.0",
    "GITEA__server__SSH_DOMAIN=localhost",
    "GITEA__server__SSH_PORT=2222",
    "GITEA__server__DISABLE_SSH=false",
    "GITEA__database__DB_TYPE=sqlite3",
    "GITEA__webhook__ALLOWED_HOST_LIST=woodpecker-server",
  ]

  ports {
    internal = 3000
    external = 3000
  }

  ports {
    internal = 22
    external = 2222
  }

  labels {
    label = "project"
    value = local.project_label
  }

  labels {
    label = "com.docker.compose.project"
    value = local.project_label
  }

  labels {
    label = "com.docker.compose.service"
    value = "gitea"
  }

  networks_advanced {
    name = docker_network.chiseai.name
  }

  volumes {
    volume_name    = docker_volume.gitea.name
    container_path = "/data"
  }
}

resource "docker_container" "woodpecker_server" {
  name  = "woodpecker-server"
  image = "woodpeckerci/woodpecker-server:v3.12.0"

  env = [
    "WOODPECKER_OPEN=false",
    "WOODPECKER_HOST=http://localhost:8012",
    "WOODPECKER_GITEA=true",
    "WOODPECKER_GITEA_URL=http://gitea:3000",
    "WOODPECKER_GITEA_CLIENT=${var.woodpecker_gitea_client}",
    "WOODPECKER_GITEA_SECRET=${var.woodpecker_gitea_secret}",
    "WOODPECKER_AGENT_SECRET=${var.woodpecker_agent_secret}",
    "WOODPECKER_PLUGINS_TRUSTED_CLONE=docker.io/woodpeckerci/plugin-git:2.5.1,docker.io/woodpeckerci/plugin-git",
    # Increase forge config fetch resilience for push/PR webhook events.
    "WOODPECKER_FORGE_TIMEOUT=15s",
    "WOODPECKER_FORGE_RETRY=5",
    "WOODPECKER_GRPC_ADDR=:9000",
    # Use Postgres to avoid sqlite locking under concurrency.
    "WOODPECKER_DATABASE_DRIVER=postgres",
    "WOODPECKER_DATABASE_DATASOURCE=postgres://woodpecker:${var.woodpecker_db_password}@chiseai-postgres:5434/woodpecker?sslmode=disable",
  ]

  ports {
    internal = 8000
    external = 8012
  }

  labels {
    label = "project"
    value = local.project_label
  }

  labels {
    label = "com.docker.compose.project"
    value = local.project_label
  }

  labels {
    label = "com.docker.compose.service"
    value = "woodpecker-server"
  }

  networks_advanced {
    name = docker_network.chiseai.name
  }

  volumes {
    volume_name    = docker_volume.woodpecker.name
    container_path = "/var/lib/woodpecker"
  }

  volumes {
    volume_name    = docker_volume.woodpecker_tmp.name
    container_path = "/tmp"
  }
}

resource "docker_container" "woodpecker_agent" {
  name  = "woodpecker-agent"
  image = "woodpeckerci/woodpecker-agent:v3.12.0"

  env = [
    "WOODPECKER_SERVER=woodpecker-server:9000",
    "WOODPECKER_AGENT_SECRET=${var.woodpecker_agent_secret}",
    "WOODPECKER_MAX_WORKFLOWS=1",
    "WOODPECKER_BACKEND=docker",
    "WOODPECKER_BACKEND_DOCKER_HOST=unix:///run/docker.sock",
    "WOODPECKER_BACKEND_DOCKER_API_VERSION=1.44",
    "WOODPECKER_BACKEND_DOCKER_TLS_VERIFY=false",
    "WOODPECKER_BACKEND_DOCKER_NETWORK=chiseai",
    "WOODPECKER_AGENT_CONFIG_FILE=/tmp/agent.conf",
    "WOODPECKER_LOG_LEVEL=debug",
  ]

  labels {
    label = "project"
    value = local.project_label
  }

  labels {
    label = "com.docker.compose.project"
    value = local.project_label
  }

  labels {
    label = "com.docker.compose.service"
    value = "woodpecker-agent"
  }

  networks_advanced {
    name = docker_network.chiseai.name
  }

  privileged = true

  mounts {
    target = "/run/docker.sock"
    source = "/run/docker.sock"
    type   = "bind"
  }

  volumes {
    volume_name    = docker_volume.woodpecker_tmp.name
    container_path = "/tmp"
  }
}

# ChiseAI API Service
resource "docker_container" "chiseai_api" {
  name  = "chiseai-api-final"
  image = "chiseai-api:latest"

  env = [
    "DATABASE_URL=postgresql://chiseai:${var.chise_postgres_password}@chiseai-postgres:5434/chiseai",
    "INFLUXDB_URL=http://chiseai-influxdb:18087",
    "INFLUXDB_ORG=${var.influxdb_org}",
    "INFLUXDB_TOKEN=${var.influxdb_token}",
    "REDIS_HOST=chiseai-redis",
    "REDIS_PORT=6380",
    "REDIS_DB=0",
    "QDRANT_URL=http://chiseai-qdrant:6334",
    "CHISEAI_ENV=production",
    "PYTHONPATH=/app:/app/src:/app/scripts",
    "KIMI_API_KEY=${var.kimi_api_key}",
    "KIMI_BASE_URL=${var.kimi_base_url}",
    "KIMI_MODEL=${var.kimi_model}",
    "ZHIPU_API_KEY=${var.zhipu_api_key}",
    "Z_AI_API_KEY=${var.z_ai_api_key}",
    "MINIMAX_API_KEY=${var.minimax_api_key}",
    "MINIMAX_ENABLED=${var.minimax_enabled}",
  ]

  ports {
    internal = 8000
    external = 8001
  }

  # ACP Dashboard Sync WebSocket (EP-NS-008)
  ports {
    internal = 8765
    external = 8765
  }

  labels {
    label = "project"
    value = local.project_label
  }

  labels {
    label = "com.docker.compose.project"
    value = local.project_label
  }

  labels {
    label = "com.docker.compose.service"
    value = "chiseai-api"
  }

  networks_advanced {
    name = docker_network.chiseai.name
  }
}

# ChiseAI Dashboard Service
resource "docker_container" "chise_dashboard" {
  name  = "chise-dashboard"
  image = "chiseai-dashboard:latest"

  env = [
    "REDIS_HOST=chiseai-redis",
    "REDIS_PORT=6380",
    "REDIS_DB=0",
    "CHISEAI_API_URL=http://chiseai-api-final:8001",
    "STREAMLIT_SERVER_PORT=8502",
    "STREAMLIT_SERVER_HEADLESS=true",
    "PYTHONPATH=/app",
  ]

  ports {
    internal = 8501
    external = 8502
  }

  labels {
    label = "project"
    value = local.project_label
  }

  labels {
    label = "com.docker.compose.project"
    value = local.project_label
  }

  labels {
    label = "com.docker.compose.service"
    value = "chise-dashboard"
  }

  networks_advanced {
    name = docker_network.chiseai.name
  }
}

# Data Quality Monitor - Always-on service for continuous data quality checks
# Uses custom image that includes scripts/ and src/ directories
# Fix for ST-OPS-011 AC-3: Script path resolution via embedded image
resource "docker_container" "chiseai_data_quality_monitor" {
  name  = "chiseai-data-quality-monitor"
  image = "chiseai-data-quality-monitor:latest"

  command = ["sh", "-c", "while true; do python3 /app/scripts/data_quality_monitor.py --check --export-influx; sleep 60; done"]

  env = [
    "DQ_INFLUX_URL=http://chiseai-influxdb:18087",
    "DQ_INFLUX_TOKEN=${var.influxdb_token}",
    "DQ_INFLUX_ORG=${var.influxdb_org}",
    "DQ_INFLUX_BUCKET=chiseai",
    "REDIS_HOST=chiseai-redis",
    "REDIS_PORT=6380",
    "REDIS_DB=0",
  ]

  restart = "always"

  networks_advanced {
    name = docker_network.chiseai.name
  }

  labels {
    label = "project"
    value = local.project_label
  }

  labels {
    label = "com.docker.compose.project"
    value = local.project_label
  }

  labels {
    label = "com.docker.compose.service"
    value = "data-quality-monitor"
  }

  healthcheck {
    test     = ["CMD-SHELL", "pgrep -f '/app/scripts/data_quality_monitor.py' || exit 1"]
    interval = "60s"
    timeout  = "10s"
    retries  = 3
  }
}

# Datasource Health Monitor - writes datasource_health and datasource_alerts for Grafana
resource "docker_container" "chiseai_datasource_health_monitor" {
  name  = "chiseai-datasource-health-monitor"
  image = "chiseai-data-quality-monitor:latest"

  command = [
    "python3",
    "/app/scripts/run_datasource_health_monitor.py",
    "--interval",
    "30",
  ]

  env = [
    "INFLUXDB_TOKEN=${var.influxdb_token}",
    "DQ_INFLUX_URL=http://chiseai-influxdb:18087",
    "DQ_INFLUX_ORG=${var.influxdb_org}",
    "DQ_INFLUX_BUCKET=${var.influxdb_bucket}",
    "POSTGRES_USER=chiseai",
    "POSTGRES_PASSWORD=${var.chise_postgres_password}",
  ]

  restart = "always"

  networks_advanced {
    name = docker_network.chiseai.name
  }

  labels {
    label = "project"
    value = local.project_label
  }

  labels {
    label = "com.docker.compose.project"
    value = local.project_label
  }

  labels {
    label = "com.docker.compose.service"
    value = "datasource-health-monitor"
  }

  healthcheck {
    test     = ["CMD-SHELL", "pgrep -f '/app/scripts/run_datasource_health_monitor.py' || exit 1"]
    interval = "60s"
    timeout  = "10s"
    retries  = 3
  }
}

# OHLCV Ingestion Daemon - Continuous market data ingestion for Grafana
# Story: INFRA-002
# Fetches OHLCV data from exchanges and stores in InfluxDB for dashboard visualization
resource "docker_container" "chiseai_ohlcv_ingestion" {
  name  = "chiseai-ohlcv-ingestion"
  image = "chiseai-ohlcv-ingestion:latest"

  env = [
    "INFLUXDB_HOST=chiseai-influxdb",
    "INFLUXDB_PORT=18087",
    "INFLUXDB_TOKEN=${var.influxdb_token}",
    "INFLUXDB_ORG=${var.influxdb_org}",
    "INFLUXDB_BUCKET=${var.influxdb_bucket}",
    "SYMBOLS=BTC/USDT,ETH/USDT,SOL/USDT",
    "TIMEFRAMES=1m,5m,15m,1h",
    "INGEST_INTERVAL_SECONDS=60",
    "EXCHANGE_ID=binance",
    "FETCH_LIMIT=100",
    "PYTHONUNBUFFERED=1",
    "PYTHONPATH=/app:/app/scripts",
  ]

  restart = "always"

  networks_advanced {
    name = docker_network.chiseai.name
  }

  labels {
    label = "project"
    value = local.project_label
  }

  labels {
    label = "com.docker.compose.project"
    value = local.project_label
  }

  labels {
    label = "com.docker.compose.service"
    value = "ohlcv-ingestion"
  }

  healthcheck {
    test     = ["CMD-SHELL", "python3 -c \"import os; exit(0) if any('run_ohlcv_ingestion' in open(f'/proc/{p}/cmdline', 'r').read() for p in os.listdir('/proc') if p.isdigit()) else exit(1)\" || exit 1"]
    interval = "60s"
    timeout  = "10s"
    retries  = 3
  }
}

# Live paper trading executor daemon (Bybit demo + mandatory LLM decision path)
resource "docker_container" "chiseai_paper_trading_executor" {
  name  = "chiseai-paper-trading-executor"
  image = "chiseai-api:latest"

  command = [
    "python3",
    "scripts/run_trading_activity.py",
    "--mode",
    "paper",
    "--duration",
    "0",
    "--confidence-threshold",
    "0.75",
    "--portfolio-value",
    "10000",
  ]

  env = [
    "REDIS_HOST=chiseai-redis",
    "REDIS_PORT=6380",
    "BYBIT_API_MODE=demo",
    "BYBIT_DEMO_API_KEY=${local.effective_bybit_demo_api_key}",
    "BYBIT_DEMO_API_SECRET=${local.effective_bybit_demo_api_secret}",
    "PAPER_ORDER_EXECUTOR=bybit_demo",
    "ALLOW_SIMULATOR_FALLBACK=false",
    "USE_LLM_TRADE_DECISIONS=true",
    "REQUIRE_LLM_TRADE_DECISION=true",
    "SIGNAL_EXCHANGE_ID=bybit",
    "TRADING_SYMBOLS=${var.trading_symbols}",
    "TRADING_TIMEFRAME=${var.trading_timeframe}",
    "SYMBOL_EVAL_INTERVAL_SECONDS=${var.trading_symbol_eval_interval_seconds}",
    "TRADING_INCIDENT_STREAM=bmad:chiseai:incidents:stream",
    "DISCORD_TRADING_WEBHOOK_URL=${var.discord_trading_webhook_url}",
    "KIMI_API_KEY=${var.kimi_api_key}",
    "KIMI_BASE_URL=${var.kimi_base_url}",
    "KIMI_MODEL=${var.kimi_model}",
    "ZHIPU_API_KEY=${var.zhipu_api_key}",
    "Z_AI_API_KEY=${var.z_ai_api_key}",
    "MINIMAX_API_KEY=${var.minimax_api_key}",
    "MINIMAX_ENABLED=${var.minimax_enabled}",
    "BYBIT_FILL_PERSISTENCE_ENABLED=true",
    "PYTHONUNBUFFERED=1",
    "PYTHONPATH=/app:/app/src",
  ]

  restart = "always"

  networks_advanced {
    name = docker_network.chiseai.name
  }

  labels {
    label = "project"
    value = local.project_label
  }

  labels {
    label = "com.docker.compose.project"
    value = local.project_label
  }

  labels {
    label = "com.docker.compose.service"
    value = "paper-trading-executor"
  }

  healthcheck {
    test         = ["CMD-SHELL", "python3 -c \"import os; exit(0) if any('run_trading_activity.py' in open(f'/proc/{p}/cmdline','r').read() for p in os.listdir('/proc') if p.isdigit()) else exit(1)\" || exit 1"]
    interval     = "60s"
    timeout      = "10s"
    retries      = 3
    start_period = "30s"
  }
}

# Daily Summary Cron Job - Paper trading daily reports
# Story: ST-CONTAINER-001
# Migrated from docker-compose.daily-summary.yml to Terraform
# Runs daily summary scheduler at midnight UTC
resource "docker_container" "chiseai_daily_summary" {
  name  = "chiseai-daily-summary"
  image = "chiseai-daily-summary:latest"

  env = [
    "REDIS_HOST=chiseai-redis",
    "REDIS_PORT=6380",
    "REDIS_DB=0",
    "POSTGRES_HOST=chiseai-postgres",
    "POSTGRES_PORT=5434",
    "POSTGRES_USER=chiseai",
    "POSTGRES_PASSWORD=${var.chise_postgres_password}",
    "POSTGRES_DB=chiseai",
    "INFLUXDB_URL=http://chiseai-influxdb:18087",
    "INFLUXDB_TOKEN=${var.influxdb_token}",
    "INFLUXDB_ORG=${var.influxdb_org}",
    "INFLUXDB_BUCKET=${var.influxdb_bucket}",
    "PYTHONUNBUFFERED=1",
    "PYTHONPATH=/app:/app/src",
    "LOG_FILE=/app/logs/daily_summary.log",
    "LOCK_FILE=/tmp/chiseai_daily_summary.lock",
  ]

  restart = "always"

  networks_advanced {
    name = docker_network.chiseai.name
  }

  labels {
    label = "project"
    value = local.project_label
  }

  labels {
    label = "com.docker.compose.project"
    value = local.project_label
  }

  labels {
    label = "com.docker.compose.service"
    value = "daily-summary"
  }

  volumes {
    volume_name    = docker_volume.daily_summary_logs.name
    container_path = "/app/logs"
  }

  healthcheck {
    test     = ["CMD-SHELL", "pgrep -x cron > /dev/null || exit 1"]
    interval = "60s"
    timeout  = "10s"
    retries  = 3
  }
}

resource "docker_container" "kimi_adapter" {
  name  = "chiseai-kimi-adapter"
  image = "chiseai-kimi-adapter:latest"

  env = [
    "KIMI_API_KEY=${var.kimi_api_key}",
    "KIMI_BASE_URL=${var.kimi_base_url}",
    "KIMI_MODEL=${var.kimi_model}",
  ]

  ports {
    internal = 8002
    external = 8002
  }

  restart = "always"

  networks_advanced {
    name = docker_network.chiseai.name
  }

  labels {
    label = "project"
    value = local.project_label
  }

  labels {
    label = "com.docker.compose.project"
    value = local.project_label
  }

  labels {
    label = "com.docker.compose.service"
    value = "kimi-adapter"
  }

  healthcheck {
    test     = ["CMD", "curl", "-f", "http://localhost:8002/health"]
    interval = "30s"
    timeout  = "10s"
    retries  = 3
  }
}

# Signal Supervisor Container - EP-PAPER-RUN-001
# Polls Redis for actionable signals and submits them to the paper trading orchestrator
# Uses live InfluxDB data only (ALLOW_SIMULATOR_FALLBACK=false)
resource "docker_container" "chiseai_signal_supervisor" {
  name  = "chiseai-signal-supervisor"
  image = "chiseai-signals:latest"

  command = [
    "python3",
    "scripts/run_signal_consumer.py",
    "--poll-interval",
    "30.0",
  ]

  env = [
    "REDIS_HOST=chiseai-redis",
    "REDIS_PORT=6380",
    "INFLUXDB_URL=http://chiseai-influxdb:18087",
    "INFLUXDB_ORG=${var.influxdb_org}",
    "INFLUXDB_TOKEN=${var.influxdb_token}",
    "INFLUXDB_BUCKET=chiseai",
    "ALLOW_SIMULATOR_FALLBACK=false",
    "TRADING_SYMBOLS=BTC/USDT,ETH/USDT",
    "PYTHONUNBUFFERED=1",
    "PYTHONPATH=/app:/app/src:/app/local_packages",
  ]

  restart = "always"

  networks_advanced {
    name = docker_network.chiseai.name
  }

  labels {
    label = "project"
    value = local.project_label
  }

  labels {
    label = "com.docker.compose.project"
    value = local.project_label
  }

  labels {
    label = "com.docker.compose.service"
    value = "signal-supervisor"
  }

  healthcheck {
    test         = ["CMD-SHELL", "python3 -c \"import os; exit(0) if any('run_signal_consumer.py' in open(f'/proc/{p}/cmdline','r').read() for p in os.listdir('/proc') if p.isdigit()) else exit(1)\" || exit 1"]
    interval     = "60s"
    timeout      = "10s"
    retries      = 3
    start_period = "30s"
  }
}
