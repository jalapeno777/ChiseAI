variable "chise_postgres_password" {
  type        = string
  description = "Postgres password for ChiseAI core database."
  default     = "change-me"
  sensitive   = true
}

variable "influxdb_admin_user" {
  type        = string
  description = "InfluxDB admin username."
  default     = "admin"
}

variable "influxdb_admin_password" {
  type        = string
  description = "InfluxDB admin password."
  default     = "change-me"
  sensitive   = true
}

variable "influxdb_token" {
  type        = string
  description = "InfluxDB API token for Grafana datasource and writers."
  default     = ""
  sensitive   = true
}

variable "influxdb_org" {
  type        = string
  description = "InfluxDB organization."
  default     = "chiseai"
}

variable "influxdb_bucket" {
  type        = string
  description = "InfluxDB default bucket."
  default     = "chiseai"
}

variable "grafana_admin_password" {
  type        = string
  description = "Grafana admin password."
  default     = "change-me"
  sensitive   = true
}

variable "gitea_root_url" {
  type        = string
  description = "Gitea public root URL."
  default     = "http://localhost:3000/"
}

variable "woodpecker_agent_secret" {
  type        = string
  description = "Shared secret between Woodpecker server and agent."
  default     = "change-me"
  sensitive   = true
}

variable "woodpecker_gitea_client" {
  type        = string
  description = "Woodpecker OAuth client ID from Gitea."
  default     = "change-me"
  sensitive   = true
}

variable "woodpecker_gitea_secret" {
  type        = string
  description = "Woodpecker OAuth client secret from Gitea."
  default     = "change-me"
  sensitive   = true
}

variable "woodpecker_db_password" {
  type        = string
  description = "Postgres password for Woodpecker database user."
  default     = "change-me"
  sensitive   = true
}

variable "taiga_secret_key" {
  type        = string
  description = "Taiga secret key (Django)."
  default     = "change-me"
  sensitive   = true
}

variable "taiga_db_password" {
  type        = string
  description = "Taiga Postgres password."
  default     = "change-me"
  sensitive   = true
}

variable "taiga_rabbitmq_user" {
  type        = string
  description = "Taiga RabbitMQ username."
  default     = "taiga"
}

variable "taiga_rabbitmq_password" {
  type        = string
  description = "Taiga RabbitMQ password."
  default     = "change-me"
  sensitive   = true
}

variable "taiga_public_domain" {
  type        = string
  description = "Taiga public domain (host:port)."
  default     = "localhost:9001"
}

variable "taiga_back_public_domain" {
  type        = string
  description = "Taiga back-end public domain (host:port) for browser clients."
  default     = "localhost:9002"
}

variable "taiga_events_public_domain" {
  type        = string
  description = "Taiga events/websockets public domain (host:port) for browser clients."
  default     = "localhost:9003"
}

variable "kimi_api_key" {
  type        = string
  description = "Moonshot AI Kimi API key for LLM adapter."
  default     = ""
  sensitive   = true
}

variable "kimi_base_url" {
  type        = string
  description = "Moonshot AI Kimi API base URL."
  default     = "https://api.moonshot.cn/v1"
}

variable "kimi_model" {
  type        = string
  description = "Kimi model to use (e.g., kimi-k2.5, moonshot-v1-8k, moonshot-v1-32k, moonshot-v1-128k)."
  default     = "kimi-k2.5"
}
