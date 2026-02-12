# ST-OPS-007: Dashboard Validation

## Story Metadata

| Field | Value |
|-------|-------|
| **Story ID** | ST-OPS-007 |
| **Title** | Dashboard Validation |
| **Story Points** | 5 |
| **Epic ID** | EP-OPS-001 |
| **Sprint ID** | p0-7 |
| **Status** | Planned |

## Description

Implement comprehensive dashboard validation framework to ensure all dashboards meet quality standards before deployment. This includes schema validation, query validation, datasource verification, and performance checks to prevent broken or inefficient dashboards in production.

## Features Delivered

1. **Schema Validation**
   - JSON schema validation for dashboard structure
   - Required field checks (title, UID, panels)
   - Version compatibility verification

2. **Query Validation**
   - Validate InfluxDB Flux queries syntax
   - Check for common query anti-patterns
   - Verify query result format compatibility

3. **Datasource Verification**
   - Confirm referenced datasources exist
   - Validate datasource UIDs match configuration
   - Test datasource connectivity

4. **Performance Checks**
   - Detect expensive queries without time filters
   - Flag dashboards with excessive panel counts
   - Validate refresh intervals are reasonable

## Dependencies

- ST-OPS-005: Grafana Provisioning Fix (should complete first - validates provisioned dashboards)
- ST-OPS-001: Grafana Dashboards (completed - existing dashboards to validate)

## Acceptance Criteria

- [ ] AC1: Validation script exists at `scripts/validate_dashboards.py`
- [ ] AC2: Schema validation covers Grafana schema version 39+
- [ ] AC3: Query validation catches syntax errors in Flux queries
- [ ] AC4: CI gate fails if dashboard validation fails
- [ ] AC5: Validation report generated with pass/fail status per dashboard
- [ ] AC6: Pre-commit hook runs validation on dashboard changes
- [ ] AC7: All existing dashboards pass validation

## Scope Globs

```yaml
implementation:
  - scripts/validate_dashboards.py
  - src/operations/dashboard_validation/**
  - .woodpecker.yml  # Add validation step
documentation:
  - docs/operations/dashboard-validation.md
tests:
  - tests/operations/test_dashboard_validation.py
  - tests/fixtures/invalid_dashboards/*.json
```

## Verification Steps

1. Run validation script: `python scripts/validate_dashboards.py`
2. Verify all existing dashboards pass: should see 0 failures
3. Introduce a syntax error in a Flux query and re-run
4. Confirm validation catches the error with specific message
5. Test pre-commit hook: modify a dashboard and attempt commit
6. Verify CI pipeline fails on invalid dashboard
7. Review validation report output format

## Notes

- Use `jsonschema` library for schema validation
- Flux query validation can use InfluxDB's `/query` endpoint
- Consider implementing severity levels (error vs warning)
- Validation should be fast (< 10 seconds for all dashboards)
