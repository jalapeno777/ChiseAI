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

## Secret Management

**IMPORTANT**: See [SECRET_MANAGEMENT.md](./SECRET_MANAGEMENT.md) for comprehensive secret management guidance.

### Quick Start

1. Copy the template file:
```bash
cp terraform.tfvars.template terraform.tfvars
```

2. Edit `terraform.tfvars` and replace all `CHANGE_ME` placeholders with actual secrets

3. Set required environment variables before running Terraform:
```bash
export TF_VAR_chise_postgres_password="your-secure-password"
export TF_VAR_influxdb_admin_password="your-secure-password"
export TF_VAR_grafana_admin_password="your-secure-password"
export TF_VAR_woodpecker_agent_secret="your-secure-secret"
export TF_VAR_woodpecker_gitea_client="your-client-id"
export TF_VAR_woodpecker_gitea_secret="your-client-secret"
export TF_VAR_woodpecker_db_password="your-db-password"
export TF_VAR_taiga_secret_key="your-taiga-secret"
export TF_VAR_taiga_db_password="your-taiga-db-password"
export TF_VAR_taiga_rabbitmq_password="your-rabbitmq-password"
export TF_VAR_influxdb_token="your-influxdb-token"
export TF_VAR_kimi_api_key="your-kimi-key"
export TF_VAR_bybit_api_key="your-bybit-key"
export TF_VAR_bybit_api_secret="your-bybit-secret"
export TF_VAR_discord_bot_token="your-discord-token"
```

### Security Notes

- **NEVER** commit `terraform.tfvars` to version control (it's already in `.gitignore`)
- **NEVER** commit `terraform.tfstate` to version control (it's already in `.gitignore`)
- Use remote state with encryption for production deployments
- Rotate secrets regularly
- See [SECRET_MANAGEMENT.md](./SECRET_MANAGEMENT.md) for detailed security best practices
