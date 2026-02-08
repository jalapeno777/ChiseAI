locals {
  project_label = "chiseai"
}

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
resource "docker_volume" "gitea" { name = "chiseai-gitea-data" }
resource "docker_volume" "woodpecker" { name = "chiseai-woodpecker-data" }
resource "docker_volume" "woodpecker_tmp" { name = "chiseai-woodpecker-tmp" }
resource "docker_volume" "taiga_postgres" { name = "taiga-postgres-data" }
resource "docker_volume" "taiga_redis" { name = "taiga-redis-data" }
resource "docker_volume" "taiga_static" { name = "taiga-static-data" }
resource "docker_volume" "taiga_media" { name = "taiga-media-data" }

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
  ]

  ports {
    internal = 3001
    external = 3001
  }

  labels {
    label = "project"
    value = local.project_label
  }

  networks_advanced {
    name = docker_network.chiseai.name
  }

  volumes {
    volume_name    = docker_volume.grafana.name
    container_path = "/var/lib/grafana"
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
  image = "woodpeckerci/woodpecker-server:latest"

  env = [
    "WOODPECKER_OPEN=false",
    "WOODPECKER_HOST=http://localhost:8012",
    "WOODPECKER_GITEA=true",
    "WOODPECKER_GITEA_URL=http://gitea:3000",
    "WOODPECKER_GITEA_CLIENT=${var.woodpecker_gitea_client}",
    "WOODPECKER_GITEA_SECRET=${var.woodpecker_gitea_secret}",
    "WOODPECKER_AGENT_SECRET=${var.woodpecker_agent_secret}",
    "WOODPECKER_PLUGINS_TRUSTED_CLONE=docker.io/woodpeckerci/plugin-git:2.5.1,docker.io/woodpeckerci/plugin-git",
    "WOODPECKER_GRPC_ADDR=:9000",
  ]

  ports {
    internal = 8000
    external = 8012
  }

  labels {
    label = "project"
    value = local.project_label
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
  image = "woodpeckerci/woodpecker-agent:latest"

  env = [
    "WOODPECKER_SERVER=woodpecker-server:9000",
    "WOODPECKER_AGENT_SECRET=${var.woodpecker_agent_secret}",
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

resource "docker_container" "taiga_postgres" {
  name  = "taiga-postgres"
  image = "postgres:15"

  env = [
    "POSTGRES_DB=taiga",
    "POSTGRES_USER=taiga",
    "POSTGRES_PASSWORD=${var.taiga_db_password}",
  ]

  labels {
    label = "project"
    value = local.project_label
  }

  networks_advanced {
    name = docker_network.chiseai.name
  }

  volumes {
    volume_name    = docker_volume.taiga_postgres.name
    container_path = "/var/lib/postgresql/data"
  }
}

resource "docker_container" "taiga_redis" {
  name  = "taiga-redis"
  image = "redis:7"

  labels {
    label = "project"
    value = local.project_label
  }

  networks_advanced {
    name = docker_network.chiseai.name
  }

  volumes {
    volume_name    = docker_volume.taiga_redis.name
    container_path = "/data"
  }
}

resource "docker_container" "taiga_rabbitmq" {
  name  = "taiga-rabbitmq"
  image = "rabbitmq:3-management"

  env = [
    "RABBITMQ_DEFAULT_USER=${var.taiga_rabbitmq_user}",
    "RABBITMQ_DEFAULT_PASS=${var.taiga_rabbitmq_password}",
    "RABBITMQ_DEFAULT_VHOST=taiga",
  ]

  labels {
    label = "project"
    value = local.project_label
  }

  networks_advanced {
    name = docker_network.chiseai.name
  }
}

resource "docker_container" "taiga_back" {
  name  = "taiga-back"
  image = "taigaio/taiga-back:latest"

  env = [
    "TAIGA_SECRET_KEY=${var.taiga_secret_key}",
    "TAIGA_SITES_SCHEME=http",
    "TAIGA_SITES_DOMAIN=${var.taiga_public_domain}",
    "TAIGA_PUBLIC_REGISTER_ENABLED=true",
    "POSTGRES_DB=taiga",
    "POSTGRES_USER=taiga",
    "POSTGRES_PASSWORD=${var.taiga_db_password}",
    "POSTGRES_HOST=taiga-postgres",
    "POSTGRES_PORT=5432",
    "RABBITMQ_USER=${var.taiga_rabbitmq_user}",
    "RABBITMQ_PASS=${var.taiga_rabbitmq_password}",
    "TAIGA_EVENTS_RABBITMQ_HOST=taiga-rabbitmq",
    "TAIGA_ASYNC_RABBITMQ_HOST=taiga-rabbitmq",
    "EVENTS_PUSH_BACKEND_URL=amqp://${var.taiga_rabbitmq_user}:${var.taiga_rabbitmq_password}@taiga-rabbitmq:5672/taiga",
    "CELERY_BROKER_URL=amqp://${var.taiga_rabbitmq_user}:${var.taiga_rabbitmq_password}@taiga-rabbitmq:5672/taiga",
  ]

  ports {
    internal = 8000
    external = 9002
  }

  labels {
    label = "project"
    value = local.project_label
  }

  networks_advanced {
    name = docker_network.chiseai.name
  }

  volumes {
    volume_name    = docker_volume.taiga_static.name
    container_path = "/taiga/static"
  }

  volumes {
    volume_name    = docker_volume.taiga_media.name
    container_path = "/taiga/media"
  }
}

resource "docker_container" "taiga_front" {
  name  = "taiga-front"
  image = "taigaio/taiga-front:latest"

  env = [
    # Browser-facing URLs. Frontend must point at back-end (:9002) and events (:9003),
    # not at the frontend itself (:9001), otherwise login/API calls fail.
    "TAIGA_URL=http://${var.taiga_back_public_domain}",
    "TAIGA_WEBSOCKETS_URL=ws://${var.taiga_events_public_domain}",
  ]

  ports {
    internal = 80
    external = 9001
  }

  labels {
    label = "project"
    value = local.project_label
  }

  networks_advanced {
    name = docker_network.chiseai.name
  }
}

resource "docker_container" "taiga_events" {
  name  = "taiga-events"
  image = "taigaio/taiga-events:latest"

  env = [
    "RABBITMQ_URL=amqp://${var.taiga_rabbitmq_user}:${var.taiga_rabbitmq_password}@taiga-rabbitmq:5672/taiga",
    "WEB_SOCKET_SERVER_PORT=8888",
    "APP_PORT=3023",
    "SECRET=${var.taiga_secret_key}",
    "ALGORITHM=HS256",
  ]

  ports {
    internal = 8888
    external = 9003
  }

  labels {
    label = "project"
    value = local.project_label
  }

  networks_advanced {
    name = docker_network.chiseai.name
  }
}
