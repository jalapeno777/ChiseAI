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

> **Note**: For the specific TF-SECRETS-002 migration workflow with pre-commit validation and CI gates, see [Migration Guide: TF-SECRETS-002](#migration-guide-tf-secrets-002).

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

## Migration Guide: TF-SECRETS-002

### What Changed in TF-SECRETS-002

This migration hardens secret management by:

1. **Pre-commit Validation**: Added `scripts/terraform/validate_tfvars.py` to detect and block tfvars files with real secrets from being committed
2. **CI Gate Enforcement**: Woodpecker CI includes a `tfvars-gate` step that fails PRs containing `*.tfvars` files (except templates)
3. **Template Maintenance**: `terraform.tfvars.template` is the only tfvars file allowed in version control

### Files to Update

When migrating existing infrastructure to TF-SECRETS-002 standards, ensure the following files are properly configured:

| File | Purpose | Status |
|------|---------|--------|
| `.gitignore` | Must exclude `**/*.tfvars`, `**/*.tfstate`, `**/*.tfstate.*` | Required |
| `terraform.tfvars.template` | Sanitized template with placeholder values | Required |
| `terraform.tfvars` | Actual values (gitignored, never commit) | Local only |
| `scripts/terraform/validate_tfvars.py` | Pre-commit and CI validation script | Required |
| `.pre-commit-config.yaml` | Must include tfvars validation hook | Required |

### Workflow for New Deployments

Follow this workflow when setting up Terraform in a new environment:

```bash
# 1. Copy the template to create your local tfvars
cd infrastructure/terraform
cp terraform.tfvars.template terraform.tfvars

# 2. Fill in actual values in terraform.tfvars
# Edit the file with your real secrets
vim terraform.tfvars

# 3. Verify terraform.tfvars is ignored (should not appear in status)
git status

# 4. Run validation before any commit
python3 scripts/terraform/validate_tfvars.py

# 5. If validation passes, proceed with Terraform operations
terraform init
terraform plan
terraform apply
```

### Workflow for Existing Deployments

If you have an existing `terraform.tfvars` with real secrets:

```bash
# 1. Ensure your secrets are backed up securely
# (Copy values to a password manager or secure note)

# 2. Verify gitignore is working
git check-ignore terraform.tfvars
# Should output: terraform.tfvars

# 3. If tfvars was previously committed, remove from history
git filter-branch --force --index-filter \
  'git rm --cached --ignore-unmatch infrastructure/terraform/terraform.tfvars' \
  --prune-empty --tag-name-filter cat -- --all

# 4. Force push if needed (coordinate with team first)
# git push origin --force --all

# 5. Rotate all exposed secrets immediately
```

### Validation Commands

```bash
# Run pre-commit validation manually
python3 scripts/terraform/validate_tfvars.py

# Run with auto-fix (removes tfvars from staging)
python3 scripts/terraform/validate_tfvars.py --fix

# Check what files would be flagged
python3 scripts/terraform/validate_tfvars.py --dry-run
```

### Troubleshooting

#### CI Fails with tfvars-gate Error

**Symptom**: Woodpecker CI fails with message about tfvars files detected

**Solution**:
```bash
# Remove any tfvars files from your PR (except template)
git reset HEAD infrastructure/terraform/terraform.tfvars
git checkout -- .gitignore  # Ensure gitignore is correct
git commit --amend --no-edit
```

#### Pre-commit Hook Fails

**Symptom**: Commit blocked by pre-commit hook detecting tfvars

**Solution**:
```bash
# Option 1: Run the fix script
python3 scripts/terraform/validate_tfvars.py --fix

# Option 2: Manually unstage the file
git reset HEAD infrastructure/terraform/terraform.tfvars
```

#### Template Out of Sync

**Symptom**: `terraform.tfvars.template` missing new variables

**Solution**:
```bash
# Update template with new placeholder
echo "# New variable added in TF-SECRETS-002" >> terraform.tfvars.template
echo 'new_variable = "PLACEHOLDER_VALUE"' >> terraform.tfvars.template

# Commit the template update
git add terraform.tfvars.template
git commit -m "docs(terraform): update tfvars template for TF-SECRETS-002"
```

#### Accidentally Committed Secrets

**Symptom**: Real secrets visible in git history

**Solution**:
1. **Immediately rotate all exposed secrets**
2. Remove from git history using `git filter-branch` or BFG Repo-Cleaner
3. Force push (coordinate with team)
4. Notify security team
5. Review access logs

### Verification Checklist for TF-SECRETS-002

After completing migration, verify:

- [ ] `terraform.tfvars` exists locally but is not tracked by git
- [ ] `terraform.tfvars.template` exists and is tracked
- [ ] `.gitignore` includes `**/*.tfvars` pattern
- [ ] `scripts/terraform/validate_tfvars.py` runs without errors
- [ ] Pre-commit hook is installed and functional
- [ ] CI pipeline `tfvars-gate` step passes
- [ ] No tfvars files appear in `git status`
- [ ] All team members have local copies of secrets

### Related Documentation

- Pre-commit hook configuration: `.pre-commit-config.yaml`
- Validation script: `scripts/terraform/validate_tfvars.py`
- CI configuration: `.woodpecker/` pipeline files
