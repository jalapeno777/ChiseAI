# Grafana Tempo Distributed Tracing Backend
# Story: TEMPO-2026-001
# Phase: 1 (Infrastructure)

resource "docker_volume" "tempo-data" {
  name = "chiseai-tempo-data"
}

resource "docker_container" "chiseai-tempo" {
  name  = "chiseai-tempo"
  image = "grafana/tempo:2.3.1"

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
    volume_name    = docker_volume.tempo-data.name
    container_path = "/tmp/tempo"
  }

  volumes {
    host_path      = "${path.module}/config/tempo.yaml"
    container_path = "/etc/tempo.yaml"
    read_only      = true
  }

  env = [
    "TEMPO_ENVIRONMENT=${var.environment}",
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
    docker_volume.tempo-data,
  ]
}
