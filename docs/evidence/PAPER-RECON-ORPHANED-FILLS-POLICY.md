# Paper Mode Orphaned Fills Policy

**Policy ID:** PAPER-RECON-ORPHANED-POLICY  
**Epic:** PAPER-RECON  
**Created:** 2026-04-11  
**Status:** ACTIVE

---

## 1. Policy Statement

Orphaned fills (fills with `signal_id IS NULL`) are **valid paper trades** that represent real exchange activity. They are **not errors** and should not block reconciliation. However, they must be clearly reported and distinguished from actual data anomalies.

---

## 2. Definitions

### Orphaned Fill

A fill record in `signal_outcomes` where `signal_id IS NULL`.

**Root Causes (Accepted):**

- Manual exchange repositioning
- Internal fills from exchange operations
- Exchange-sourced fills without signal linkage
- Paper mode testing fills

**Characteristics:**

- `signal_id = NULL` in `signal_outcomes` table
- `outcome_type = 'fill'`
- Represents legitimate exchange activity

### Missing Signal Fill (Anomaly)

A fill record where `signal_id IS NOT NULL` but no corresponding signal exists in the `signals` table.

**This is a data anomaly** indicating:

- Signal was deleted after fill was recorded
- Signal ID mismatch between systems
- Data corruption

---

## 3. Acceptable Handling Rules

### Orphaned Fills (signal_id IS NULL)

| Property             | Value                                                               |
| -------------------- | ------------------------------------------------------------------- |
| Validity             | **VALID** paper trade                                               |
| P&L Participation    | Yes - included in pnl, fees calculations                            |
| Signal-based Metrics | **Excluded** from confidence, signal quality metrics                |
| Reconciliation       | **NON-BLOCKING** - reported but does not cause divergence exit code |
| Visibility           | Must appear in reconcile output with clear "expected" labeling      |
| Idempotency          | Uses `order_id` as `outcome_id` for proper upsert behavior          |

### Missing Signal Fills (signal_id without signal)

| Property             | Value                                                |
| -------------------- | ---------------------------------------------------- |
| Validity             | **ANOMALY** - requires investigation                 |
| P&L Participation    | Included (data is recorded)                          |
| Signal-based Metrics | N/A - signal doesn't exist                           |
| Reconciliation       | **BLOCKING** - causes divergence exit code           |
| Visibility           | Must appear as CRITICAL severity in reconcile output |

---

## 4. Visibility & Reporting Requirements

### reconcile.py Output Requirements

The `paper_reconcile.py` script MUST report:

1. **Postgres Orphaned Fills Count** (`pg_orphaned_fills`)
   - Fills with `signal_id IS NULL`
   - Labeled as "expected in paper mode"

2. **Postgres Missing Signal Fills Count** (`pg_missing_signal_fills`)
   - Fills with `signal_id` but no corresponding signal
   - Labeled as "data anomaly"

3. **Redis Orphaned Fills** (`orphaned_fills`)
   - Fills in Redis without matching orders
   - Separate from Postgres-level tracking
   - Labeled as "WARNING" severity (Redis data integrity issue)

### Alert Key Requirements

When writing to Redis alert key (`paper:reconcile:alert`), include:

```json
{
  "pg_orphaned_fills": <count>,
  "pg_missing_signal_fills": <count>,
  "orphaned_fills_count": <count>
}
```

---

## 5. Reconciliation Divergence Classification

| Condition                                | Severity | Blocking | Notes                  |
| ---------------------------------------- | -------- | -------- | ---------------------- |
| Postgres orphaned fills > 0              | INFO     | No       | Expected in paper mode |
| Postgres missing signal fills > 0        | CRITICAL | Yes      | Data anomaly           |
| Redis orphaned fills > 0                 | WARNING  | No       | Redis data integrity   |
| Redis vs Postgres outcome count mismatch | varies   | Yes      | Data sync issue        |

---

## 6. Implementation Details

### ReconcileResult Dataclass Fields

```python
@dataclass
class ReconcileResult:
    # ... existing fields ...
    pg_orphaned_fills: int = 0  # fills with NULL signal_id (expected in paper mode)
    pg_missing_signal_fills: int = 0  # fills that SHOULD have signals but don't (anomaly)
```

### Postgres Query for Orphaned Fills

```sql
SELECT
    COUNT(*) FILTER (WHERE signal_id IS NULL) as orphaned_fills,
    COUNT(*) FILTER (WHERE signal_id IS NOT NULL AND signal_id NOT IN (
        SELECT signal_id FROM signals WHERE signal_id IS NOT NULL
    )) as missing_signal_fills
FROM signal_outcomes
WHERE outcome_type = 'fill' AND created_at >= $1
```

---

## 7. Test Plan

### Unit Tests

1. `test_reconcile_result_orphaned_fills_field` - Verify new fields exist on ReconcileResult
2. `test_reconcile_orphaned_non_blocking` - Verify orphaned fills don't cause exit_code = 1
3. `test_reconcile_missing_signal_blocking` - Verify missing signal fills DO cause exit_code = 1

### Integration Tests

1. Query Postgres with known orphaned fills returns correct counts
2. Reconcile output clearly distinguishes orphaned vs missing signal fills

### Manual Verification

```bash
# Check current orphaned fill count
psql -h host.docker.internal -p 5434 -U chiseai -d chiseai \
  -c "SELECT COUNT(*) FROM signal_outcomes WHERE outcome_type = 'fill' AND signal_id IS NULL;"

# Run reconcile and verify output
python3 scripts/paper_reconcile.py --since 2026-04-01T00:00:00Z
```

---

## 8. Revision History

| Date       | Version | Changes                 |
| ---------- | ------- | ----------------------- |
| 2026-04-11 | 1.0     | Initial policy creation |
