terraform {
  required_version = ">= 1.5.0"

  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
      version = "~> 3.0"
    }
    grafana = {
      source  = "grafana/grafana"
      version = "~> 2.0"
    }
  }
}

provider "docker" {}

provider "grafana" {
  url  = "http://172.17.0.1:3001"
  auth = "admin:${var.grafana_admin_password}"
}
