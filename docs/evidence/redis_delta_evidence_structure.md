# Redis Delta Evidence Structure

This document shows example evidence structures collected by the Redis Delta Collector
for G1-G4 validation.

## Example Evidence (Successful Validation)

### Validation Report

```json
{
  "execution_id": "abc12345",
  "timestamp_utc": "2024-02-28T14:00:00.000000+00:00",
  "gate_results": [
    {
      "name": "G1",
      "status": "pass",
      "message": "Scheduler heartbeat present - scheduler running",
      "evidence": {
        "index_name": "bmad:chiseai:scheduler:heartbeat",
        "start_count": 1,
        "end_count": 1,
        "delta": 0,
        "sample_ids": [],
        "timestamp_start_utc": "2024-02-28T13:59:00+00:00",
        "timestamp_end_utc": "2024-02-28T14:00:00+00:00"
      },
      "timestamp_utc": "2024-02-28T14:00:00+00:00"
    },
    {
      "name": "G2",
      "status": "pass",
      "message": "Signal generation active: 3 new signals",
      "evidence": {
        "index_name": "paper:index:signals",
        "start_count": 42,
        "end_count": 45,
        "delta": 3,
        "sample_ids": [
          "paper:signal:20240228135900:SOL:sig-001",
          "paper:signal:20240228135930:BTC:sig-002",
          "paper:signal:20240228135945:ETH:sig-003"
        ],
        "timestamp_start_utc": "2024-02-28T13:59:00+00:00",
        "timestamp_end_utc": "2024-02-28T14:00:00+00:00"
      },
      "timestamp_utc": "2024-02-28T14:00:00+00:00"
    },
    {
      "name": "G3",
      "status": "pass",
      "message": "Outcome flow active: 2 new outcomes",
      "evidence": {
        "index_name": "paper:index:outcomes",
        "start_count": 38,
        "end_count": 40,
        "delta": 2,
        "sample_ids": [
          "paper:outcome:20240228135915:SOL:out-001",
          "paper:outcome:20240228135945:BTC:out-002"
        ],
        "timestamp_start_utc": "2024-02-28T13:59:00+00:00",
        "timestamp_end_utc": "2024-02-28T14:00:00+00:00"
      },
      "timestamp_utc": "2024-02-28T14:00:00+00:00"
    },
    {
      "name": "G4",
      "status": "pass",
      "message": "Kill switch enabled and not triggered - safety active",
      "evidence": {
        "enabled": "true",
        "triggered": "false",
        "last_check": "2024-02-28T14:00:00+00:00"
      },
      "timestamp_utc": "2024-02-28T14:00:00+00:00"
    }
  ],
  "delta_evidence": [
    {
      "index_name": "paper:index:signals",
      "start_count": 42,
      "end_count": 45,
      "delta": 3,
      "sample_ids": ["paper:signal:20240228135900:SOL:sig-001"],
      "timestamp_start_utc": "2024-02-28T13:59:00+00:00",
      "timestamp_end_utc": "2024-02-28T14:00:00+00:00"
    },
    {
      "index_name": "paper:index:orders",
      "start_count": 40,
      "end_count": 43,
      "delta": 3,
      "sample_ids": ["paper:order:20240228135905:SOL:ord-001"],
      "timestamp_start_utc": "2024-02-28T13:59:00+00:00",
      "timestamp_end_utc": "2024-02-28T14:00:00+00:00"
    },
    {
      "index_name": "paper:index:fills",
      "start_count": 38,
      "end_count": 40,
      "delta": 2,
      "sample_ids": ["paper:fill:20240228135910:SOL:ord-001"],
      "timestamp_start_utc": "2024-02-28T13:59:00+00:00",
      "timestamp_end_utc": "2024-02-28T14:00:00+00:00"
    },
    {
      "index_name": "paper:index:outcomes",
      "start_count": 38,
      "end_count": 40,
      "delta": 2,
      "sample_ids": ["paper:outcome:20240228135915:SOL:out-001"],
      "timestamp_start_utc": "2024-02-28T13:59:00+00:00",
      "timestamp_end_utc": "2024-02-28T14:00:00+00:00"
    }
  ],
  "correlation_evidence": [
    {
      "signal_id": "sig-001",
      "order_id": "ord-001",
      "fill_id": "ord-001",
      "outcome_id": "out-001",
      "correlation_chain": ["signal", "order", "fill", "outcome"],
      "data": {
        "signal": {
          "signal_id": "sig-001",
          "token": "SOL",
          "direction": "long",
          "confidence": 0.75,
          "timestamp": "2024-02-28T13:59:00+00:00"
        },
        "order": {
          "order_id": "ord-001",
          "symbol": "SOL",
          "side": "buy",
          "quantity": 1.5,
          "signal_id": "sig-001"
        },
        "fill": {
          "order_id": "ord-001",
          "filled_quantity": 1.5,
          "avg_fill_price": 125.50
        },
        "outcome": {
          "outcome_id": "out-001",
          "signal_id": "sig-001",
          "pnl": 12.50,
          "win": true
        }
      }
    }
  ],
  "overall_passed": true,
  "errors": []
}
```

## Canonical Index Keys

The collector monitors these Redis keys:

| Key | Type | Purpose |
|-----|------|---------|
| `paper:index:signals` | Sorted Set | Index of all trading signals |
| `paper:index:orders` | Sorted Set | Index of all orders |
| `paper:index:fills` | Sorted Set | Index of all fills |
| `paper:index:outcomes` | Sorted Set | Index of all outcomes |
| `bmad:chiseai:scheduler:heartbeat` | String | Scheduler heartbeat |
| `bmad:chiseai:kill_switch` | Hash | Kill switch state |

## Gate Definitions

| Gate | Index | Pass Condition | Fail Condition |
|------|-------|----------------|----------------|
| G1 | `bmad:chiseai:scheduler:heartbeat` | Heartbeat present | Heartbeat missing |
| G2 | `paper:index:signals` | delta > 0 | delta = 0 |
| G3 | `paper:index:outcomes` | delta > 0 | delta = 0 |
| G4 | `bmad:chiseai:kill_switch` | enabled=true, triggered=false | triggered=true or enabled=false |

## Correlation Chain

The collector builds correlation proofs following this chain:

```
signal_id -> order_id -> fill_id -> outcome_id
```

Each step is stored in the `data` field of `CorrelationEvidence`.

## Usage

```bash
# Run with defaults (60 second window)
python3 scripts/validation/redis_deltas.py

# Custom validation window
VALIDATION_WINDOW_SECONDS=120 python3 scripts/validation/redis_deltas.py

# Custom Redis connection
REDIS_HOST=chiseai-redis REDIS_PORT=6380 python3 scripts/validation/redis_deltas.py
```

## Output

Reports are written to `docs/evidence/redis_delta_report_{execution_id}.json`
