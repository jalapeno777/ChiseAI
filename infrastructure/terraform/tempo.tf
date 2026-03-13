# Grafana Tempo Distributed Tracing Backend
# Story: TEMPO-2026-001

resource "docker_volume" "tempo" {
  name = "chiseai-tempo-data"
}

resource "docker_container" "tempo" {
  name  = "chiseai-tempo"
  image = "grafana/tempo:${var.tempo_version}"

  # Network configuration
  networks_advanced {
    name    = docker_network.chiseai.name
    aliases = ["tempo", "chiseai-tempo"]
  }

  # Port mappings
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

  # Volume mounts
  volumes {
    volume_name    = docker_volume.tempo.name
    container_path = "/tmp/tempo"
  }

  volumes {
    host_path      = abspath("${path.module}/config/tempo.yaml")
    container_path = "/etc/tempo.yaml"
    read_only      = true
  }

  # Environment variables
  env = [
    "TEMPO_ENVIRONMENT=${var.environment}",
  ]

  # Container configuration
  command = ["-config.file=/etc/tempo.yaml"]

  # Health check
  healthcheck {
    test     = ["CMD", "wget", "-q", "--spider", "http://localhost:3200/ready"]
    interval = "30s"
    timeout  = "10s"
    retries  = 3
  }

  # Resource limits
  memory = var.tempo_memory_mb

  # Labels for governance
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
    value = "tempo"
  }

  labels {
    label = "service"
    value = "tempo"
  }

  labels {
    label = "story"
    value = "TEMPO-2026-001"
  }

  # Restart policy
  restart = "unless-stopped"

  depends_on = [
    docker_network.chiseai,
  ]
}

# Tempo configuration file
resource "local_file" "tempo_config" {
  content = templatefile("${path.module}/config/tempo.yaml.tpl", {
    environment     = var.environment
    log_level       = var.tempo_log_level
    retention_hours = var.tempo_retention_hours
  })
  filename = "${path.module}/config/tempo.yaml"
}
