# ST-OPS-005: Grafana Provisioning Fix

## Story Metadata

| Field | Value |
|-------|-------|
| **Story ID** | ST-OPS-005 |
| **Title** | Grafana Provisioning Fix |
| **Story Points** | 8 |
| **Epic ID** | EP-OPS-001 |
| **Sprint ID** | p0-7 |
| **Status** | Planned |

## Description

Implement automated Grafana dashboard provisioning infrastructure to enable version-controlled, reproducible dashboard deployments. The current manual dashboard creation process is error-prone and lacks version control. This story establishes the foundation for infrastructure-as-code dashboard management.

## Features Delivered

1. **Dashboard Provisioning Configuration**
   - YAML-based provisioning config for dashboards
   - Support for multiple dashboard providers
   - Folder-based organization structure

2. **Version-Controlled Dashboards**
   - Dashboard JSON files stored in repository
   - Git-tracked dashboard definitions
   - Change history and rollback capability

3. **Automated Deployment**
   - Terraform integration for provisioning setup
   - Docker volume mounts for dashboard files
   - Automatic dashboard reload on container start

4. **Multi-Environment Support**
   - Separate provisioning configs per environment
   - Environment-specific dashboard variants
   - Configurable datasource mapping

## Dependencies

- ST-OPS-001: Grafana Dashboards (completed - base dashboards exist)
- ST-INFRA-BOOT-001: Infrastructure Bootstrap (completed - Terraform stack exists)

## Acceptance Criteria

- [ ] AC1: Provisioning configuration files exist in `infrastructure/terraform/grafana/provisioning/`
- [ ] AC2: Dashboard JSON files are stored in `infrastructure/terraform/grafana/dashboards/`
- [ ] AC3: Terraform applies provisioning configuration on `terraform apply`
- [ ] AC4: Dashboards automatically appear in Grafana after container restart
- [ ] AC5: Changes to dashboard JSON files trigger dashboard updates on redeploy
- [ ] AC6: Documentation exists for adding new dashboards via provisioning
- [ ] AC7: At least 3 dashboards are provisioned via this mechanism (data-freshness, backtest-kpis, and one new)

## Scope Globs

```yaml
implementation:
  - infrastructure/terraform/grafana/provisioning/**
  - infrastructure/terraform/grafana/dashboards/**
  - infrastructure/terraform/grafana/*.tf
documentation:
  - docs/operations/grafana-provisioning.md
tests:
  - tests/infrastructure/test_grafana_provisioning.py
```

## Verification Steps

1. Run `terraform apply` in `infrastructure/terraform/`
2. Verify provisioning config files are mounted in Grafana container
3. Restart Grafana container: `docker restart chiseai-grafana`
4. Navigate to Grafana UI at `http://localhost:3001`
5. Confirm all provisioned dashboards appear in "ChiseAI" folder
6. Verify dashboards are marked as "Provisioned" in UI
7. Make a change to a dashboard JSON file and redeploy
8. Confirm change is reflected in Grafana after restart

## Notes

- Grafana provisioning docs: https://grafana.com/docs/grafana/latest/administration/provisioning/
- Dashboards provisioned via files are read-only in UI (intentional)
- Use environment variables for sensitive datasource configuration
