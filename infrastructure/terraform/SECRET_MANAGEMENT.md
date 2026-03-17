# Terraform Secret Management Guide

## Overview

This document outlines the secret management approach for ChiseAI Terraform infrastructure to ensure sensitive values are not exposed in version control or state files.

## Current State

### ✅ What's Already Implemented

1. **Variable Sensitivity Marking**: All sensitive variables are marked with `sensitive = true` in `variables.tf`
2. **Git Ignore**: `.gitignore` excludes `**/*.tfvars`, `**/*.tfstate`, and `**/*.tfstate.*` files
3. **Template File**: `terraform.tfvars.template` provides a sanitized example with placeholder values

### ⚠️ Security Issues Identified

1. **Local State File**: Terraform state file (`terraform.tfstate`) is stored locally and contains sensitive values
2. **No Remote Backend**: No remote backend configured for state storage and encryption
3. **Plain Text Secrets**: Secrets are visible in local state file (3 occurrences found)

## Recommended Secret Management Approaches

### Option 1: Environment Variables (Quick Start)

Set secrets as environment variables before running Terraform commands:

```bash
# Set all required secrets as environment variables
export TF_VAR_chise_postgres_password="your-secure-password"
export TF_VAR_influxdb_admin_password="your-secure-password"
export TF_VAR_influxdb_token="your-influxdb-token"
export TF_VAR_grafana_admin_password="your-grafana-password"
export TF_VAR_woodpecker_agent_secret="your-woodpecker-secret"
export TF_VAR_woodpecker_gitea_secret="your-gitea-secret"
export TF_VAR_woodpecker_db_password="your-db-password"
export TF_VAR_taiga_secret_key="your-taiga-secret"
export TF_VAR_taiga_db_password="your-taiga-db-password"
export TF_VAR_taiga_rabbitmq_password="your-rabbitmq-password"
export TF_VAR_kimi_api_key="your-kimi-key"
export TF_VAR_zhipu_api_key="your-zhipu-key"
export TF_VAR_z_ai_api_key="your-z-ai-key"
export TF_VAR_minimax_api_key="your-minimax-key"
export TF_VAR_bybit_demo_api_key="your-bybit-demo-key"
export TF_VAR_bybit_demo_api_secret="your-bybit-demo-secret"
export TF_VAR_bybit_api_key="your-bybit-key"
export TF_VAR_bybit_api_secret="your-bybit-secret"
export TF_VAR_discord_bot_token="your-discord-token"

# Run Terraform commands
terraform plan
terraform apply
```

### Option 2: Terraform Cloud (Recommended)

1. **Sign up for Terraform Cloud**: https://app.terraform.io
2. **Create a workspace** for ChiseAI infrastructure
3. **Configure remote backend** in `versions.tf`:

```hcl
terraform {
  required_version = ">= 1.5.0"
  
  backend "remote" {
    hostname     = "app.terraform.io"
    organization = "your-organization"
    
    workspaces {
      name = "chiseai-infrastructure"
    }
  }
  
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
```

4. **Store secrets in Terraform Cloud**: Use the workspace variables UI to set sensitive values

### Option 3: AWS Secrets Manager / Azure Key Vault

For cloud-based deployments, integrate with cloud provider secret management:

```hcl
# Example using AWS Secrets Manager
data "aws_secretsmanager_secret_version" "db_password" {
  secret_id = "arn:aws:secretsmanager:region:account:secret:chiseai/db_password"
}

# Use in your configuration
resource "docker_container" "postgres" {
  env = [
    "POSTGRES_PASSWORD=${data.aws_secretsmanager_secret_version.db_password.secret_string}",
  ]
}
```

### Option 4: HashiCorp Vault

For self-hosted secret management:

```hcl
# Example using Vault provider
data "vault_kv_secret_v2" "db_password" {
  mount = "secret"
  name  = "chiseai/db_password"
}

# Use in your configuration
resource "docker_container" "postgres" {
  env = [
    "POSTGRES_PASSWORD=${data.vault_kv_secret_v2.db_password.data["password"]}",
  ]
}
```

## State File Encryption

### Current Issue
The local state file (`terraform.tfstate`) stores sensitive values in plain text.

### Solution: Remote Backend with Encryption

Configure a remote backend that supports encryption:

```hcl
# Example: AWS S3 backend with encryption
terraform {
  backend "s3" {
    bucket         = "chiseai-terraform-state"
    key            = "infrastructure/terraform.tfstate"
    region         = "us-west-2"
    encrypt        = true              # Enable server-side encryption
    dynamodb_table = "terraform-locks" # Enable state locking
  }
}
```

## Best Practices

### ✅ DO

1. **Use Environment Variables**: Set secrets via `TF_VAR_*` environment variables
2. **Use Remote State**: Store state files remotely with encryption enabled
3. **Mark Variables as Sensitive**: Always use `sensitive = true` for secret variables
4. **Use .gitignore**: Ensure `.tfvars`, `.tfstate`, and `.tfstate.*` files are ignored
5. **Create Template Files**: Provide `terraform.tfvars.template` with placeholder values
6. **Rotate Secrets Regularly**: Implement secret rotation policies
7. **Use Secret Management Tools**: Integrate with Vault, AWS Secrets Manager, or similar
8. **Enable State Encryption**: Use remote backends with encryption at rest

### ❌ DON'T

1. **Never Commit Secrets**: Don't commit actual secrets to version control
2. **Don't Use Plain Text State**: Avoid local state files for sensitive infrastructure
3. **Don't Share State Files**: Never share or copy state files containing secrets
4. **Don't Log Secrets**: Ensure secrets aren't logged in CI/CD pipelines
5. **Don't Use Default Passwords**: Change all default passwords before deployment

## Migration Steps

### Step 1: Set Up Secret Storage

Choose one of the options above and configure your secret storage solution.

### Step 2: Export Current Secrets

If you have existing secrets in `terraform.tfvars`, export them to your chosen secret store:

```bash
# Example: Export to environment variables
source terraform.tfvars  # If it's sourced as env vars
# Or manually copy values to your secret store
```

### Step 3: Remove Local Secrets

```bash
# Remove the terraform.tfvars file
rm terraform.tfvars

# Keep only the template
git add terraform.tfvars.template
git commit -m "docs(terraform): add secret management template"
```

### Step 4: Configure Remote Backend

Update `versions.tf` to use a remote backend with encryption (see examples above).

### Step 5: Initialize New Backend

```bash
# Reinitialize Terraform with new backend
terraform init -migrate-state

# Verify state is working
terraform plan
```

## CI/CD Integration

### GitHub Actions / GitLab CI

Use repository secrets to provide Terraform variables:

```yaml
# .github/workflows/terraform.yml
name: Terraform

on: [push]

jobs:
  terraform:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v2
      
      - name: Terraform Plan
        env:
          TF_VAR_chise_postgres_password: ${{ secrets.CHISE_POSTGRES_PASSWORD }}
          TF_VAR_influxdb_admin_password: ${{ secrets.INFLUXDB_ADMIN_PASSWORD }}
          # ... other secrets
        run: |
          terraform init
          terraform plan
```

## Verification Checklist

- [ ] No secrets committed to version control
- [ ] `.gitignore` excludes `.tfvars`, `.tfstate`, `.tfstate.*`
- [ ] All sensitive variables marked with `sensitive = true`
- [ ] State file stored remotely with encryption
- [ ] Template file (`terraform.tfvars.template`) exists with placeholders
- [ ] Documentation updated with secret management approach
- [ ] CI/CD pipelines use secure secret injection
- [ ] Team members understand secret management procedures

## Emergency Procedures

### If Secrets Are Exposed

1. **Immediately rotate all exposed secrets**
2. **Remove secrets from version control history** (if committed)
3. **Update `.gitignore` if needed**
4. **Notify security team**
5. **Review access logs for unauthorized access**

### If State File Is Compromised

1. **Immediately migrate to remote backend**
2. **Rotate all secrets in state file**
3. **Enable state file encryption**
4. **Review Terraform logs for unauthorized changes**

## References

- [Terraform Sensitive Variables](https://developer.hashicorp.com/terraform/language/values/variables#suppressing-values-in-cli-output)
- [Terraform Backends](https://developer.hashicorp.com/terraform/language/settings/backends)
- [Terraform Cloud](https://www.terraform.io/cloud)
- [AWS Secrets Manager](https://aws.amazon.com/secrets-manager/)
- [HashiCorp Vault](https://www.vaultproject.io/)
