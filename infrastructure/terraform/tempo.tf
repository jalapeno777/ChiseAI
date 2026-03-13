# Grafana Tempo Distributed Tracing Backend
# Story: TEMPO-2026-001
# Phase: 1 (Infrastructure)

# Template rendering for Tempo config
data "template_file" "tempo_config" {
  template = file("${path.module}/config/tempo.yaml.tpl")

  vars = {
    log_level       = var.tempo_log_level
    retention_hours = var.tempo_retention_hours
  }
}

resource "local_file" "tempo_config" {
  content  = data.template_file.tempo_config.rendered
  filename = "${path.module}/config/tempo.yaml"
}

# Tempo data volume
resource "docker_volume" "tempo_data" {
  name = "chiseai-tempo-data"
}

# Tempo container
resource "docker_container" "chiseai_tempo" {
  name  = "chiseai-tempo"
  image = "grafana/tempo:${var.tempo_version}"

  networks_advanced {
    name    = "chiseai"
    aliases = ["tempo", "chiseai-tempo"]
  }

  ports {
    internal = 3200
    external = 3200
    protocol = "tcp"
  }

  ports {
    internal = 4317
    external = 4317
    protocol = "tcp"
  }

  ports {
    internal = 4318
    external = 4318
    protocol = "tcp"
  }

  volumes {
    volume_name    = docker_volume.tempo_data.name
    container_path = "/tmp/tempo"
  }

  volumes {
    host_path      = abspath(local_file.tempo_config.filename)
    container_path = "/etc/tempo.yaml"
    read_only      = true
  }

  env = [
    "TEMPO_LOG_LEVEL=${var.tempo_log_level}",
  ]

  command = ["-config.file=/etc/tempo.yaml"]

  healthcheck {
    test     = ["CMD", "wget", "-q", "--spider", "http://localhost:3200/ready"]
    interval = "30s"
    timeout  = "10s"
    retries  = 3
  }

  memory = 2048

  labels {
    label = "project"
    value = "chiseai"
  }

  labels {
    label = "service"
    value = "tempo"
  }

  labels {
    label = "story"
    value = "TEMPO-2026-001"
  }

  restart = "unless-stopped"

  depends_on = [
    docker_volume.tempo_data,
    local_file.tempo_config,
  ]
}
