# Belief Revision Audit Runbook

## Overview

This runbook documents how to audit belief revisions using the 7-day query system. Belief revisions are tracked when the autonomous cognition system detects and resolves conflicts between beliefs.

## Artifact Locations

- **Individual artifacts**: `_bmad-output/autocog/belief_revisions/{run_id}.json`
- **Index file**: `_bmad-output/autocog/belief_revisions/index.json`

## Schema Documentation

### Artifact Schema (v1.0)

Each belief revision artifact contains:

```json
{
  "run_id": "autocog-20260314-120000-abc123",
  "generated_at": "2026-03-14T12:00:00+00:00",
  "revision_count": 2,
  "revisions": [
    {
      "revision_id": "a1b2c3d4e5f67890",
      "old_belief_id": "belief-memory-health",
      "new_belief_id": "belief-memory-outdated",
      "old_belief_statement": "Memory system is healthy",
      "new_belief_statement": "Memory system needs attention",
      "old_belief_domain": "memory",
      "new_belief_domain": "memory",
      "confidence_before": 0.82,
      "confidence_after": 0.64,
      "confidence_delta": -0.18,
      "reason": "Resolved conflict conflict-001: Contradictory evidence detected",
      "evidence_refs": ["self_assessment_daily", "legacy_runtime_warning"],
      "applied_at": "2026-03-14T12:00:00+00:00"
    }
  ],
  "schema_version": "1.0",
  "artifact_type": "belief_revision_audit"
}
```

### Index Schema

The index file enables efficient 7-day queries:

```json
{
  "schema_version": "1.0",
  "last_updated": "2026-03-14T12:00:00+00:00",
  "entries": [
    {
      "run_id": "autocog-20260314-120000-abc123",
      "generated_at": "2026-03-14T12:00:00+00:00",
      "revision_count": 2,
      "artifact_path": "_bmad-output/autocog/belief_revisions/autocog-20260314-120000-abc123.json",
      "belief_ids": ["belief-memory-health", "belief-memory-outdated"],
      "domains": ["memory"],
      "severity_summary": {"high": 1, "medium": 0, "low": 1}
    }
  ]
}
```

### Severity Levels

Severity is calculated from confidence delta magnitude:

| Severity | Confidence Delta | Description |
|----------|-----------------|-------------|
| high | ≥ 0.3 | Significant belief change requiring attention |
| medium | 0.15 - 0.29 | Moderate belief adjustment |
| low | < 0.15 | Minor belief refinement |

## How to Run 7-Day Audit Query

### Default 7-Day Query

Query revisions from the last 7 days:

```bash
python scripts/audit/query_belief_revisions.py
```

### Query with Date Range

Specify custom date range:

```bash
python scripts/audit/query_belief_revisions.py \
  --start-date 2026-03-01 \
  --end-date 2026-03-14
```

### Filter by Belief ID

Query revisions for a specific belief:

```bash
python scripts/audit/query_belief_revisions.py \
  --belief-id belief-memory-health
```

### Filter by Severity

Query only high-severity revisions:

```bash
python scripts/audit/query_belief_revisions.py \
  --severity high
```

### Combined Filters

Query high-severity revisions for a specific belief in date range:

```bash
python scripts/audit/query_belief_revisions.py \
  --start-date 2026-03-01 \
  --end-date 2026-03-14 \
  --belief-id belief-memory-health \
  --severity high
```

### Output Options

Save results to file:

```bash
python scripts/audit/query_belief_revisions.py \
  --output audit_results.json
```

Get summary format instead of JSON:

```bash
python scripts/audit/query_belief_revisions.py \
  --format summary
```

Query index only (faster, no full artifact loading):

```bash
python scripts/audit/query_belief_revisions.py \
  --index-only
```

## Rollback Procedure

### Identifying Rollback Target

1. Query revisions to find the belief state to rollback to:

```bash
python scripts/audit/query_belief_revisions.py \
  --belief-id <target-belief-id> \
  --output rollback_analysis.json
```

2. Examine the artifact to identify:
   - `old_belief_id`: The belief ID before revision
   - `new_belief_id`: The belief ID after revision
   - `confidence_before`: Confidence level to restore
   - `reason`: Why the revision was made

### Manual Rollback Steps

1. **Locate the artifact** containing the revision to rollback:
   ```bash
   cat _bmad-output/autocog/belief_revisions/index.json | jq '.entries[] | select(.belief_ids | contains(["<belief-id>"]))'
   ```

2. **Review the revision details**:
   ```bash
   cat _bmad-output/autocog/belief_revisions/<run_id>.json | jq '.revisions[] | select(.old_belief_id == "<belief-id>")'
   ```

3. **Restore belief state** via Redis (if using Redis persistence):
   ```python
   from tools.redis_state import redis_state_hset, redis_state_set
   from autonomous_cognition.beliefs.models import Belief
   
   # Reconstruct original belief
   original_belief = Belief(
       belief_id="<old_belief_id>",
       statement="<old_belief_statement>",
       domain="<domain>",
       confidence=<confidence_before>,
       evidence_refs=[<evidence_refs>],
       status="active",
   )
   
   # Persist to store
   belief_store.put(original_belief)
   ```

4. **Mark superseded belief** as inactive:
   ```python
   superseded_belief.status = "superseded"
   superseded_belief.updated_at = datetime.now(UTC).isoformat()
   belief_store.put(superseded_belief)
   ```

5. **Document the rollback**:
   - Create a rollback record in `_bmad-output/autocog/rollbacks/`
   - Include original revision ID and rollback reason

### Automated Rollback (Future Enhancement)

A future enhancement will provide:

```bash
python scripts/audit/rollback_belief.py \
  --revision-id <revision-id> \
  --reason "Manual rollback due to incorrect evidence"
```

## Troubleshooting

### No revisions found

If query returns no results:

1. Check if index file exists:
   ```bash
   ls -la _bmad-output/autocog/belief_revisions/index.json
   ```

2. Verify date range covers period with activity:
   ```bash
   cat _bmad-output/autocog/belief_revisions/index.json | jq '.entries[].generated_at'
   ```

3. Check if belief ID exists in system:
   ```bash
   cat _bmad-output/autocog/belief_revisions/index.json | jq '.entries[].belief_ids | flatten | unique'
   ```

### Corrupted index

If index is corrupted:

1. Back up corrupted index:
   ```bash
   cp _bmad-output/autocog/belief_revisions/index.json \
      _bmad-output/autocog/belief_revisions/index.json.bak
   ```

2. Rebuild index from artifacts:
   ```bash
   # Future enhancement: python scripts/audit/rebuild_index.py
   # For now, manually reconstruct or delete index to regenerate on next run
   rm _bmad-output/autocog/belief_revisions/index.json
   ```

3. Next belief revision run will recreate the index

### Missing artifacts

If index references artifacts that don't exist:

1. Identify missing artifacts:
   ```bash
   python scripts/audit/query_belief_revisions.py 2>&1 | grep "Could not load artifact"
   ```

2. Clean up index entries for missing artifacts:
   ```bash
   # Future enhancement: python scripts/audit/cleanup_index.py
   ```

## Integration with Monitoring

### Grafana Dashboard

Belief revision metrics are available in Grafana:
- Revision count by severity
- Revision rate over time
- Belief stability metrics

### Discord Notifications

High-severity revisions trigger Discord notifications with:
- Revision summary
- Artifact path
- Recommended action

### Alerting

Configure alerts for:
- High-severity revision rate > threshold
- Multiple revisions of same belief within 24 hours
- Rollback operations

## Related Documentation

- [Autonomous Cognition Architecture](../../src/autonomous_cognition/README.md)
- [Belief Models](../../src/autonomous_cognition/beliefs/models.py)
- [Full Cycle Implementation](../../src/autonomous_cognition/full_cycle.py)
- [Constitution Audit](../../src/autonomous_cognition/constitution_audit.py)

## Changelog

### v1.0 (2026-03-14)
- Initial auditability pipeline implementation
- 7-day query support
- Severity-based filtering
- Index-based retrieval
- Rollback documentation
