# ST-PAPER-RECON-008 ORM Schema Drift Remediation

## Issue Summary

The `SignalOutcome` dataclass (`src/ml/models/signal_outcome.py`) has many fields that are NOT present in the PostgreSQL `signal_outcomes` table schema (`src/market_analysis/signal_storage/postgres_storage.py`).

The `outcome_persistence.py` INSERT at lines 199-218 attempts to INSERT 27 columns into a table that only defined 11 columns.

## Root Cause

Schema drift occurred as the `SignalOutcome` dataclass evolved with new fields (RECON-001, DISCORD-TRADING-001, ST-VENUE-001, ST-PIPELINE-Q2) without updating the PostgreSQL schema.

## SignalOutcome Fields Not in PostgreSQL Schema

| Field            | Type     | Source Story        |
| ---------------- | -------- | ------------------- |
| outcome_id       | UUID     | Core ID             |
| order_id         | str      | Core                |
| symbol           | str      | Core                |
| token            | str      | Core                |
| side             | str      | Core                |
| direction        | str      | Core                |
| fill_price       | Decimal  | Core                |
| fill_quantity    | Decimal  | Core                |
| fill_timestamp   | datetime | Core                |
| fee              | Decimal  | Core                |
| status           | str      | Core                |
| metadata         | dict     | Core                |
| entry_price      | Decimal  | RECON-001           |
| exit_price       | Decimal  | RECON-001           |
| entry_time       | datetime | RECON-001           |
| exit_time        | datetime | RECON-001           |
| leverage         | Decimal  | RECON-001           |
| entry_reason     | str      | RECON-001           |
| position_size    | Decimal  | RECON-001           |
| is_test          | bool     | DISCORD-TRADING-001 |
| execution_venue  | str      | ST-VENUE-001        |
| execution_mode   | str      | ST-VENUE-001        |
| execution_source | str      | ST-VENUE-001        |
| venue_metadata   | dict     | ST-VENUE-001        |
| confidence_score | float    | ST-PIPELINE-Q2      |
| signal_type      | str      | ST-PIPELINE-Q2      |

## Original PostgreSQL Schema (Minimal)

```sql
CREATE TABLE IF NOT EXISTS signal_outcomes (
    id SERIAL PRIMARY KEY,
    signal_id UUID NOT NULL REFERENCES signals(signal_id) ON DELETE CASCADE,
    exit_timestamp BIGINT NOT NULL,
    is_win BOOLEAN NOT NULL,
    pnl REAL NOT NULL,
    exit_price REAL NOT NULL,
    duration_hours REAL NOT NULL,
    outcome_type VARCHAR(20) NOT NULL,
    note TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(signal_id)
)
```

## Updated PostgreSQL Schema

Added all columns required by `outcome_persistence.py` INSERT and `SignalOutcome` dataclass:

```sql
CREATE TABLE IF NOT EXISTS signal_outcomes (
    id SERIAL PRIMARY KEY,
    -- Core identification
    outcome_id UUID NOT NULL,
    signal_id UUID REFERENCES signals(signal_id) ON DELETE SET NULL,
    order_id VARCHAR(100),
    symbol VARCHAR(20),
    token VARCHAR(20),
    -- Trade direction
    side VARCHAR(10),
    direction VARCHAR(10),
    -- Fill data
    fill_price REAL,
    fill_quantity REAL,
    fill_timestamp TIMESTAMP,
    -- Outcome classification
    outcome_type VARCHAR(20) NOT NULL,
    -- Financials
    pnl REAL,
    fee REAL,
    -- Status and timestamps
    status VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Metadata
    metadata JSONB,
    -- RECON-001: Canonical trade outcome fields
    entry_price REAL,
    exit_price REAL,
    entry_time TIMESTAMP,
    exit_time TIMESTAMP,
    leverage REAL DEFAULT 1.0,
    entry_reason VARCHAR(50),
    position_size REAL,
    -- DISCORD-TRADING-001: Test trade labeling
    is_test BOOLEAN DEFAULT FALSE,
    -- ST-VENUE-001: Venue provenance fields
    execution_venue VARCHAR(50),
    execution_mode VARCHAR(20),
    execution_source VARCHAR(100),
    venue_metadata JSONB,
    -- ST-PIPELINE-Q2: Signal-to-outcome correlation fields
    confidence_score REAL DEFAULT 0.0,
    signal_type VARCHAR(20),
    -- Legacy compatibility fields (deprecated but kept for migration)
    exit_timestamp BIGINT,
    is_win BOOLEAN,
    duration_hours REAL,
    note TEXT,
    UNIQUE(outcome_id)
)
```

## Changes Made

**File: `src/market_analysis/signal_storage/postgres_storage.py`**

- Updated `signal_outcomes` table schema in `initialize_schema()` method (lines 131-166)
- Added all 27 columns that `outcome_persistence.py` expects to INSERT
- Changed constraint from `UNIQUE(signal_id)` to `UNIQUE(outcome_id)` to match the actual INSERT behavior
- Changed `signal_id` from `NOT NULL` to nullable with `ON DELETE SET NULL` to allow for outcome records without signals

## Verification

```bash
# SignalOutcome import test
$ PYTHONPATH=src python3 -c "from ml.models.signal_outcome import SignalOutcome; print('OK')"
OK

# Paper trading unit tests
$ PYTHONPATH=src pytest tests/unit/paper_trading/ -v
9 passed in 0.44s

# Execution unit tests (2 pre-existing failures unrelated to schema change)
$ PYTHONPATH=src pytest tests/unit/execution/ -v
155 passed, 2 failed (risk_enforcer and signal_consumer pre-existing issues)
```

The 2 test failures are pre-existing bugs unrelated to this schema change:

1. `test_process_signal_blocked_by_risk_enforcer` - violations.rule attribute issue in orchestrator
2. `test_multiple_signals_in_one_poll` - kill switch AsyncMock comparison issue

## Completion Evidence

- **Branch**: `feature/ST-PAPER-RECON-008-orm-schema-drift`
- **Worktree**: `/tmp/worktrees/ST-PAPER-RECON-008-orm-schema-drift`
- **Files changed**: `src/market_analysis/signal_storage/postgres_storage.py`
- **Tests**: 9 paper_trading passed, 155/157 execution passed (2 pre-existing failures)
- **Import verification**: OK

## Follow-up Recommendations

1. Add database migration script for existing databases (ALTER TABLE ADD COLUMN for new columns)
2. Add schema validation in CI to detect drift between dataclass and database schema
3. Update `OutcomeRecord` model in `src/execution/outcomes/models.py` to match extended schema
