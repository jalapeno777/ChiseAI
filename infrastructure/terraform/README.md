# ChiseAI Local Infra (Terraform + Docker)

This Terraform stack provisions the local ChiseAI infra on the `chiseai` Docker network.

## Services
- Core: Redis, Postgres, InfluxDB, Qdrant, Grafana
- Dev tooling: Gitea, Woodpecker (server + agent)
- Agile: Taiga (front/back/events + internal DB/Redis/RabbitMQ)

## Ports (host)
- Redis: 6380
- Postgres: 5434
- InfluxDB: 18087
- Qdrant: 6334
- Grafana: 3001
- Gitea: 3000 (SSH 2222)
- Woodpecker: 8012
- Taiga: front 9001, back 9002, events 9003

## Apply
```bash
cd infrastructure/terraform
terraform init
terraform apply
```

## Required Variables
Set these before apply:
- `TF_VAR_chise_postgres_password`
- `TF_VAR_influxdb_admin_password`
- `TF_VAR_grafana_admin_password`
- `TF_VAR_woodpecker_agent_secret`
- `TF_VAR_woodpecker_gitea_client`
- `TF_VAR_woodpecker_gitea_secret`
- `TF_VAR_woodpecker_db_password`
- `TF_VAR_taiga_secret_key`
- `TF_VAR_taiga_db_password`

Defaults are `change-me` and are not safe for real usage.
