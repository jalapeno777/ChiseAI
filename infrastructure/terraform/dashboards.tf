# Terraform configuration for Grafana dashboards
# Deploys dashboard JSON files to Grafana via provisioning

locals {
  dashboards_path = "${path.module}/../grafana/provisioning/dashboards"
}

# Grafana dashboard provisioning configuration
resource "grafana_dashboard" "data_freshness" {
  config_json = file("${local.dashboards_path}/data-freshness.json")
  folder      = grafana_folder.chiseai.id
  overwrite   = true
}

resource "grafana_dashboard" "backtest_kpis" {
  config_json = file("${local.dashboards_path}/backtest-kpis.json")
  folder      = grafana_folder.chiseai.id
  overwrite   = true
}

resource "grafana_dashboard" "paper_execution" {
  config_json = file("${local.dashboards_path}/paper-execution.json")
  folder      = grafana_folder.chiseai.id
  overwrite   = true
}

resource "grafana_dashboard" "live_execution" {
  config_json = file("${local.dashboards_path}/live-execution.json")
  folder      = grafana_folder.chiseai.id
  overwrite   = true
}

resource "grafana_dashboard" "datasource_health" {
  config_json = file("${local.dashboards_path}/datasource-health.json")
  folder      = grafana_folder.chiseai.id
  overwrite   = true
}

resource "grafana_dashboard" "autonomous_control_plane" {
  config_json = file("${local.dashboards_path}/autonomous_control_plane.json")
  folder      = grafana_folder.chiseai.id
  overwrite   = true
}

# TEMPO-2026-001: Trace Exploration Dashboard
resource "grafana_dashboard" "tempo_trace_exploration" {
  config_json = file("${path.module}/dashboards/tempo-trace-exploration.json")
  folder      = grafana_folder.chiseai.id
  overwrite   = true

  depends_on = [
    grafana_folder.chiseai,
    grafana_data_source.influxdb,
  ]
}

# ChiseAI folder for organizing dashboards
resource "grafana_folder" "chiseai" {
  title = "ChiseAI"
}

# Data source configuration for InfluxDB
resource "grafana_data_source" "influxdb" {
  type       = "influxdb"
  name       = "ChiseAI InfluxDB"
  url        = "http://chiseai-influxdb:18087"
  is_default = true

  json_data_encoded = jsonencode({
    version       = "Flux"
    organization  = var.influxdb_org
    defaultBucket = var.influxdb_bucket
    tlsSkipVerify = true
  })

  secure_json_data_encoded = jsonencode({
    token = var.influxdb_token
  })
}

# Outputs
output "dashboard_uids" {
  description = "UIDs of created dashboards"
  value = {
    data_freshness           = grafana_dashboard.data_freshness.uid
    backtest_kpis            = grafana_dashboard.backtest_kpis.uid
    paper_execution          = grafana_dashboard.paper_execution.uid
    live_execution           = grafana_dashboard.live_execution.uid
    datasource_health        = grafana_dashboard.datasource_health.uid
    autonomous_control_plane = grafana_dashboard.autonomous_control_plane.uid
    tempo_trace_exploration  = grafana_dashboard.tempo_trace_exploration.uid
  }
}

output "folder_id" {
  description = "ID of the ChiseAI folder"
  value       = grafana_folder.chiseai.id
}
