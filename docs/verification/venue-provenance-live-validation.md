# Venue Provenance Live Validation Guide

**Document ID:** ST-VENUE-001-LIVE-VALIDATION  
**Story:** ST-VENUE-001 - Venue Provenance Fields  
**Generated:** 2026-03-01  
**Status:** ACTIVE  
**Scope:** Live validation of venue provenance in signal outcomes

---

## 1. OVERVIEW

This document describes the live validation procedure for venue provenance fields in signal outcomes. The validation ensures that:

1. Venue fields are present in outcomes
2. Bybit demo mode is correctly detected and recorded
3. Venue provenance information is complete
4. All provenance fields meet validation criteria

### 1.1 What is Venue Provenance?

Venue provenance tracks the origin and execution context of trading signals:

- **Venue**: The exchange or execution venue (e.g., "bybit_demo")
- **Executor Type**: The class/component that executed the trade (e.g., "BybitDemoConnector")
- **Provenance Endpoint**: The API endpoint used for execution
- **Demo Flag**: Boolean indicating if demo mode was active
- **Timestamp**: When the provenance was recorded

### 1.2 Why This Matters

Venue provenance is critical for:

- **Audit Trail**: Proving where and how trades were executed
- **Compliance**: Demonstrating demo-only operation
- **Debugging**: Tracking execution path issues
- **Reporting**: Accurate trade attribution

---

## 2. VALIDATION PROCEDURE

### 2.1 Prerequisites

Before running validation, ensure:

1. **PostgreSQL is accessible**:
   ```bash
   # From container context
   pg_isready -h host.docker.internal -p 5434
   ```

2. **Required environment variables** (optional but recommended):
   ```bash
   export POSTGRES_HOST=host.docker.internal
   export POSTGRES_PORT=5434
   export POSTGRES_DB=chiseai
   export POSTGRES_USER=chiseai
   export POSTGRES_PASSWORD=change-me
   ```

3. **Python dependencies**:
   ```bash
   pip install psycopg2-binary
   ```

### 2.2 Running the Validation

Execute the validation script:

```bash
python3 scripts/validation/verify_venue_provenance_live.py
```

### 2.3 Validation Steps

The script performs the following checks:

#### Step 1: Venue Field Presence
- Checks if `signal_outcomes` table exists
- Identifies venue-related columns (venue, executor_type, is_demo, etc.)
- Reports fields found vs. expected

#### Step 2: Bybit Demo Mode Configuration
- Verifies `BybitDemoConnector` is importable
- Validates `DemoProvenance` structure
- Checks demo credentials availability
- Confirms `BybitConfig` enforces demo mode
- Validates endpoint patterns block production

#### Step 3: Provenance Completeness
- Counts total outcomes in database
- Calculates percentage of outcomes with venue info
- Checks executor type distribution
- Identifies gaps in provenance data

#### Step 4: Integrity Verification
- Correlates results from all checks
- Assesses overall health status
- Provides recommendations for improvements

---

## 3. EXPECTED RESULTS

### 3.1 Healthy System

When the system is properly configured, you should see:

```
VENUE PROVENANCE VALIDATION SUMMARY
============================================================
Execution ID: a1b2c3d4
Timestamp: 2026-03-01T12:00:00+00:00
Overall Status: HEALTHY

Checks Performed:
  ✓ venue_fields_exist: pass
  ✓ bybit_demo_mode: pass
  ✓ provenance_completeness: pass
  ✓ venue_provenance_integrity: pass

Venue Fields:
  Found 3 venue-related field(s):
    - venue (character varying)
    - executor_type (character varying)
    - is_demo (boolean)

Bybit Demo Mode:
  Demo credentials available: True
  ✓ BybitDemoConnector module is importable
  ✓ DemoProvenance structure is valid
  ✓ BybitConfig demo mode enforced (endpoint: https://api-demo.bybit.com)
  ✓ Production mode correctly blocked by SecurityException
  ✓ Endpoint validation patterns are configured

Provenance Completeness:
  Total outcomes: 150
  - outcomes_with_venue: 150/150 (100.0%)
  - outcomes_with_executor_type: 150/150 (100.0%)
  - outcomes_with_demo_flag: 150/150 (100.0%)

Executor Type Distribution:
  - BybitDemoConnector: 145
  - OrderSimulator: 5

Integrity Status: healthy
Report saved to: _bmad-output/venue-provenance-report-a1b2c3d4.json
============================================================
```

### 3.2 Degraded System (Warnings)

If some checks pass but with warnings:

```
Overall Status: DEGRADED

Warnings:
  ⚠ No dedicated venue fields found in signal_outcomes table
  ⚠ Bybit demo credentials not available in environment
  ⚠ outcomes_with_venue: Only 60% complete (90/150)

Recommendations:
  → Consider adding venue, executor_type, and is_demo columns
  → Set BYBIT_DEMO_API_KEY and BYBIT_DEMO_API_SECRET environment variables
```

### 3.3 Failed Validation

If critical checks fail:

```
Overall Status: DEGRADED

Checks Performed:
  ✗ venue_fields_exist: fail
  ✓ bybit_demo_mode: pass
  ✗ provenance_completeness: fail
  ✗ venue_provenance_integrity: fail

Errors:
  ✗ signal_outcomes table does not exist
  ✗ BybitDemoConnector not importable: No module named 'execution.connectors'
```

---

## 4. TROUBLESHOOTING GUIDE

### 4.1 Database Connection Issues

**Symptom**: `psycopg2 not installed` or connection errors

**Solution**:
```bash
# Install psycopg2
pip install psycopg2-binary

# Verify PostgreSQL is running
docker ps | grep postgres

# Test connection
psql -h host.docker.internal -p 5434 -U chiseai -d chiseai -c "SELECT 1;"
```

### 4.2 Missing Venue Fields

**Symptom**: `No dedicated venue fields found`

**Cause**: The `signal_outcomes` table may not have venue-specific columns yet.

**Solution**:

Option 1: Add venue columns to the table:
```sql
ALTER TABLE signal_outcomes
ADD COLUMN IF NOT EXISTS venue VARCHAR(50),
ADD COLUMN IF NOT EXISTS executor_type VARCHAR(100),
ADD COLUMN IF NOT EXISTS is_demo BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS provenance_endpoint VARCHAR(255),
ADD COLUMN IF NOT EXISTS provenance_timestamp TIMESTAMP;
```

Option 2: Store venue info in the `note` field as JSON:
```sql
UPDATE signal_outcomes
SET note = jsonb_set(
    COALESCE(note::jsonb, '{}'),
    '{venue}',
    '"bybit_demo"'
)
WHERE note IS NULL OR note = '';
```

### 4.3 BybitDemoConnector Import Errors

**Symptom**: `BybitDemoConnector not importable`

**Solution**:
```bash
# Ensure you're in the correct directory
cd /path/to/ChiseAI

# Verify the file exists
ls -la src/execution/connectors/bybit_demo_connector.py

# Check Python path
python3 -c "import sys; print(sys.path)"

# Try importing with full path
python3 -c "from src.execution.connectors.bybit_demo_connector import BybitDemoConnector"
```

### 4.4 Demo Credentials Not Available

**Symptom**: `Demo credentials not available`

**Solution**:
```bash
# Check if credentials are set
echo $BYBIT_DEMO_API_KEY
echo $BYBIT_DEMO_API_SECRET

# Set credentials
export BYBIT_DEMO_API_KEY="your_demo_key"
export BYBIT_DEMO_API_SECRET="your_demo_secret"

# Or add to .env file
echo "BYBIT_DEMO_API_KEY=your_demo_key" >> .env
echo "BYBIT_DEMO_API_SECRET=your_demo_secret" >> .env
```

### 4.5 Low Provenance Coverage

**Symptom**: `outcomes_with_venue: Only X% complete`

**Cause**: Older outcomes may not have venue information, or the outcome capture service isn't recording venue data.

**Solution**:

1. Check the outcome capture service configuration
2. Verify `BybitDemoConnector` is being used (not `OrderSimulator`)
3. Review `trading_mode_loader.py` to ensure proper executor selection

### 4.6 Production Mode Not Blocked

**Symptom**: `Production mode not blocked - SecurityException should have been raised`

**Cause**: `BybitConfig` may not be enforcing demo mode correctly.

**Solution**:
```python
# Verify BybitConfig raises SecurityException for production
from data.exchange.bybit_connector import BybitConfig
from data.exchange.bybit_safety import SecurityException

try:
    config = BybitConfig(api_key="test", api_secret="test", demo=False, testnet=False)
    print("ERROR: Should have raised SecurityException")
except SecurityException as e:
    print("OK: Production mode is blocked")
```

---

## 5. VALIDATION CHECKLIST

Use this checklist when running validation:

| # | Check | Expected Result | Status |
|---|-------|-----------------|--------|
| 1 | PostgreSQL connection | Successful connection | ⬜ |
| 2 | signal_outcomes table exists | Table found | ⬜ |
| 3 | Venue fields present | venue, executor_type, is_demo columns | ⬜ |
| 4 | BybitDemoConnector importable | Module loads successfully | ⬜ |
| 5 | DemoProvenance structure valid | Dataclass works correctly | ⬜ |
| 6 | Demo credentials available | Environment variables set | ⬜ |
| 7 | BybitConfig enforces demo | demo=True required | ⬜ |
| 8 | Production mode blocked | SecurityException raised | ⬜ |
| 9 | Endpoint validation working | Demo allowed, prod blocked | ⬜ |
| 10 | Outcomes have venue info | >90% coverage | ⬜ |
| 11 | BybitDemoConnector outcomes | >0 outcomes | ⬜ |
| 12 | Report generated | JSON file created | ⬜ |

---

## 6. REPORT OUTPUT

### 6.1 Report Location

Reports are saved to:
```
_bmad-output/venue-provenance-report-{execution_id}.json
```

### 6.2 Report Structure

```json
{
  "timestamp": "2026-03-01T12:00:00+00:00",
  "execution_id": "a1b2c3d4",
  "overall_status": "healthy",
  "checks": [
    {
      "name": "venue_fields_exist",
      "status": "pass",
      "timestamp": "2026-03-01T12:00:01+00:00",
      "details": {...}
    }
  ],
  "venue_field_checks": {
    "fields_found": [...],
    "fields_missing": [...],
    "all_columns": {...}
  },
  "bybit_demo_checks": {
    "demo_credentials_available": true,
    "checks_performed": [...]
  },
  "provenance_completeness": {
    "total_outcomes": 150,
    "completeness_checks": [...]
  }
}
```

---

## 7. INTEGRATION WITH CI/CD

### 7.1 Pre-commit Hook

Add to `.pre-commit-config.yaml`:

```yaml
- repo: local
  hooks:
    - id: venue-provenance-validation
      name: Venue Provenance Validation
      entry: python3 scripts/validation/verify_venue_provenance_live.py
      language: system
      pass_filenames: false
      always_run: true
```

### 7.2 CI Pipeline

Add to CI workflow:

```yaml
- name: Validate Venue Provenance
  run: |
    python3 scripts/validation/verify_venue_provenance_live.py
    if [ $? -ne 0 ]; then
      echo "Venue provenance validation failed"
      exit 1
    fi
```

---

## 8. REFERENCES

- **BybitDemoConnector**: `src/execution/connectors/bybit_demo_connector.py`
- **BybitConfig**: `src/data/exchange/bybit_connector.py`
- **SecurityException**: `src/data/exchange/bybit_safety.py`
- **Signal Outcomes**: `src/market_analysis/signal_storage/postgres_storage.py`
- **Demo Trading Proof**: `docs/verification/bybit-demo-trading-proof.md`
- **Validation Script**: `scripts/validation/verify_venue_provenance_live.py`

---

## 9. EXIT CODES

| Code | Meaning | Action |
|------|---------|--------|
| 0 | All validations passed | System is healthy |
| 1 | One or more validations failed | Review errors and warnings |

---

*Document version: 1.0*  
*Last updated: 2026-03-01*  
*Story: ST-VENUE-001*
