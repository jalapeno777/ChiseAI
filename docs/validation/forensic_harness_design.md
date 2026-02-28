# Forensic Validation Harness - Design Document

## Overview

The Forensic Validation Harness is a fail-safe validation system where gates can **ONLY** pass when all required runtime-generated artifacts are present and valid. This document explains the fail-safe mechanisms and design principles.

## Core Philosophy

### "Fail-Safe by Design"

The harness follows a strict fail-safe philosophy:

1. **Any missing required artifact = auto-FAIL**
2. **Zero delta for G1-G4 = FAIL**  
3. **No manual override capability exists**
4. **All timestamps must be monotonic UTC**

The system is designed to err on the side of caution. A gate cannot be manually marked as passing - it must earn its PASS status through evidence.

## Architecture

### Data Flow

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Artifact       │────▶│   Snapshot       │────▶│   Gate          │
│  Collectors     │     │   (T0, T5...)    │     │   Evaluation    │
└─────────────────┘     └──────────────────┘     └─────────────────┘
        │                        │                        │
        ▼                        ▼                        ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Redis/Discord  │     │   Artifacts      │     │   PASS/FAIL     │
│  /InfluxDB      │     │   Dictionary     │     │   Verdict       │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                                          │
                                                          ▼
                                                 ┌─────────────────┐
                                                 │  Evidence       │
                                                 │  Bundle         │
                                                 │  (SHA-256)      │
                                                 └─────────────────┘
```

### Key Components

#### 1. Artifact Collectors

Collectors are functions that gather evidence from external systems:

- **Redis Collectors**: Fetch scheduler heartbeats, signal counts, kill switch state
- **Discord Collectors**: Capture message IDs from trading channel
- **InfluxDB Collectors**: Query order and fill data

Each collector is registered by artifact name and called during snapshot capture.

#### 2. Snapshots

Snapshots capture the state at specific time intervals (T0, T5, T10, etc.):

```python
@dataclass
class Snapshot:
    timestamp_utc: str  # ISO format UTC
    label: str          # "T0", "T5", etc.
    artifacts: Dict[str, Artifact]
```

#### 3. Gate Evaluation

Gates are evaluated against required artifacts:

| Gate | Required Artifacts | Zero Delta Check |
|------|-------------------|------------------|
| G1   | scheduler_heartbeat | Yes |
| G2   | signal_count_delta | Yes |
| G3   | outcome_count_delta | Yes |
| G4   | kill_switch_state | Yes |
| G5   | discord_open_msg, discord_close_msg, discord_recap_msg | No |
| G6   | influx_orders_query, influx_fills_query | No |
| G7   | influx_canary_query | No |
| G8   | burn_in_verdict | No |

#### 4. Evidence Bundle

The final output is an immutable evidence bundle with SHA-256 integrity hash:

```python
@dataclass
class EvidenceBundle:
    proof_result: ProofResult    # Complete proof data
    bundle_hash: str             # SHA-256 of serialized data
    created_at: str              # UTC timestamp
    bundle_id: str               # UUID
```

## Fail-Safe Mechanisms

### 1. Artifact Presence Enforcement

```python
def evaluate_gate(self, gate: str, required_artifacts: List[str]) -> GateResult:
    for req_art in required_artifacts:
        if req_art not in all_artifacts:
            artifacts_missing.append(req_art)
            validation_errors.append(f"Missing required artifact: {req_art}")
    
    # Any missing artifact = FAIL
    if artifacts_missing:
        status = GateStatus.FAIL
```

**Fail-Safe Principle**: The gate cannot pass if ANY required artifact is missing. There is no "optional" artifact.

### 2. Zero Delta Detection

For G1-G4, zero values indicate no activity, which is a failure condition:

```python
if gate in ZERO_DELTA_GATES:
    if "delta" in data and data["delta"] == 0:
        return f"Gate {gate}: Zero delta detected"
```

**Fail-Safe Principle**: A healthy system should show activity. Zero activity is suspicious and fails the gate.

### 3. Content Validation

Each artifact type has specific validation rules:

**Discord Messages (G5)**:
- Must have `message_id` field
- `message_id` cannot be empty

**Influx Queries (G6-G7)**:
- Must have `results` field
- Results cannot be empty

```python
if gate == "G5":
    if "message_id" not in data:
        return f"Gate G5: Discord message missing message_id"
```

**Fail-Safe Principle**: Partial or malformed evidence is treated as missing evidence.

### 4. Monotonic Timestamp Validation

Timestamps must always increase:

```python
def _validate_monotonic_timestamps(self) -> List[str]:
    for i in range(1, len(self.snapshots)):
        prev_ts = datetime.fromisoformat(self.snapshots[i-1].timestamp_utc)
        curr_ts = datetime.fromisoformat(self.snapshots[i].timestamp_utc)
        if curr_ts <= prev_ts:
            errors.append(f"Non-monotonic timestamp at snapshot {i}")
```

**Fail-Safe Principle**: Time cannot go backwards. Non-monotonic timestamps indicate system clock issues or data corruption.

### 5. No Manual Override

The `GateResult` class has no `override()` method. The status is computed purely from evidence:

```python
@dataclass
class GateResult:
    gate: str
    status: GateStatus  # Computed, not settable
    artifacts_found: List[str]
    artifacts_missing: List[str]
    validation_errors: List[str]
```

**Fail-Safe Principle**: Humans cannot override the evidence. If the evidence says FAIL, the gate FAILs.

### 6. Immutable Evidence Bundle

The evidence bundle is cryptographically hashed:

```python
def generate_bundle(self) -> EvidenceBundle:
    bundle_data = json.dumps(
        self._proof_result.to_dict(),
        sort_keys=True,  # Deterministic
        default=str
    )
    bundle_hash = hashlib.sha256(bundle_data.encode()).hexdigest()
```

**Fail-Safe Principle**: Evidence cannot be tampered with after generation. Any modification changes the hash.

## Usage Example

```python
import asyncio
from scripts.validation.forensic_harness import (
    ForensicHarness,
    create_redis_collector,
    create_discord_collector,
    create_influx_collector
)

async def run_validation():
    # Create collectors
    collectors = {
        "scheduler_heartbeat": create_redis_collector(redis_client, "scheduler:heartbeat"),
        "signal_count_delta": create_redis_collector(redis_client, "signals:count"),
        "discord_open_msg": create_discord_collector(discord_client, CHANNEL_ID, "open"),
        "influx_orders_query": create_influx_collector(influx_client, "SELECT * FROM orders"),
        # ... more collectors
    }
    
    # Initialize harness
    harness = ForensicHarness(
        duration_minutes=30,
        snapshot_interval_minutes=5,
        artifact_collectors=collectors
    )
    
    # Run proof loop
    result = await harness.run_proof_loop()
    
    # Check results
    print(f"Overall Status: {result.overall_status.value}")
    for gate, gate_result in result.gate_results.items():
        print(f"{gate}: {gate_result.status.value}")
        if gate_result.validation_errors:
            print(f"  Errors: {gate_result.validation_errors}")
    
    # Generate evidence bundle
    bundle = harness.generate_bundle()
    print(f"Bundle Hash: {bundle.bundle_hash}")
    
    # Save bundle
    with open("evidence_bundle.json", "w") as f:
        f.write(bundle.to_json())

asyncio.run(run_validation())
```

## Testing

The test suite (`tests/test_validation/test_forensic_harness.py`) includes:

1. **Initialization Tests**: Verify harness setup
2. **Snapshot Capture Tests**: Verify artifact collection
3. **Gate Pass Tests**: Verify PASS conditions
4. **Gate Fail Tests**: Verify all FAIL conditions
5. **Timestamp Tests**: Verify monotonic validation
6. **Bundle Tests**: Verify evidence integrity
7. **Integration Tests**: End-to-end workflows

Run tests:
```bash
pytest tests/test_validation/test_forensic_harness.py -v
```

## Security Considerations

1. **No Secrets in Evidence**: Collectors must not capture API keys or credentials
2. **Hash Verification**: Bundle hashes can be verified independently
3. **Audit Trail**: All artifacts include source paths for traceability
4. **Time Integrity**: UTC timestamps prevent timezone manipulation

## Future Enhancements

1. **Digital Signatures**: Sign bundles with private keys
2. **Blockchain Anchoring**: Anchor bundle hashes to blockchain
3. **Real-time Streaming**: Stream artifacts during proof loop
4. **ML Anomaly Detection**: Detect anomalous patterns in artifacts
5. **Multi-party Validation**: Require multiple validators to sign off

## Conclusion

The Forensic Validation Harness implements a strict fail-safe design where:

- **Evidence is king**: Gates pass only with complete, valid evidence
- **Fail closed**: Any doubt results in FAIL
- **Immutable**: Evidence bundles are cryptographically secured
- **Auditable**: Full traceability from source to verdict

This design ensures that validation results can be trusted and audited, providing confidence in the trading system's integrity.
