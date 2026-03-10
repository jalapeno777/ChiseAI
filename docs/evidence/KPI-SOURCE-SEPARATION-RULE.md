# KPI Source Separation Rule

## Canonical Rule

> **Bybit truth is canonical for live trading GO gates.**  
> **Paper journal is simulation telemetry only.**  
> **Never mix sources for GO decisions.**

## When to Use Each Source

### bybit_truth (Canonical for Live)

**Use for:**
- Live trading GO gate decisions
- Production performance metrics
- Fee calculations and reconciliation
- Real PnL reporting
- Regulatory/compliance reporting

**Data characteristics:**
- Source: Bybit API (executions endpoint)
- Contains: Actual executed orders, real fees, real fills
- Latency: Historical (batch queries)
- Accuracy: Ground truth from exchange

**Label in reports:**
```json
{
  "source": "bybit_truth",
  "source_label": "CANONICAL FOR GO GATES",
  "canonical": true,
  "trading_mode": "live"
}
```

### paper_journal_sim (Simulation Only)

**Use for:**
- Paper trading validation
- Strategy backtesting
- Algorithm behavior verification
- Risk model calibration
- Pre-live testing

**Data characteristics:**
- Source: Redis journal (paper trades)
- Contains: Simulated trades, calculated PnL, no real fees
- Latency: Real-time (as trades occur)
- Accuracy: Simulation based on price feeds

**Label in reports:**
```json
{
  "source": "paper_journal_sim",
  "source_label": "SIMULATION - NOT CANONICAL FOR GO",
  "canonical": false,
  "trading_mode": "paper",
  "warning": "Simulation data - not for live GO decisions"
}
```

## How to Identify Canonical vs Non-Canonical Reports

### Canonical (bybit_truth)

| Check | Canonical Report |
|-------|------------------|
| Source field | `"source": "bybit_truth"` |
| Label | "CANONICAL FOR GO GATES" |
| Data origin | Bybit API executions |
| Fee basis | Real fees paid |
| Use case | Live trading promotion |

### Non-Canonical (paper_journal_sim)

| Check | Non-Canonical Report |
|-------|----------------------|
| Source field | `"source": "paper_journal_sim"` |
| Label | "SIMULATION - NOT CANONICAL FOR GO" |
| Data origin | Redis journal (simulated) |
| Fee basis | Calculated/estimated |
| Use case | Paper testing only |

## Migration Guide for Existing Workflows

### Step 1: Identify Current Source

Check existing KPI reports for source labels:
```bash
# Check for source metadata
grep -l '"source"' docs/validation/evidence/*KPI*.json

# Reports WITHOUT source labels are LEGACY
```

### Step 2: Categorize Legacy Reports

| If report contains... | Likely source | Action |
|-----------------------|---------------|--------|
| Simulated PnL, no fees | paper_journal_sim | Label as simulation |
| Real fees, Bybit order IDs | bybit_truth | Label as canonical |
| Mixed/matching unclear | UNKNOWN | Mark as LEGACY, do not use for GO |

### Step 3: Update GO Gates

Add source validation to GO gate logic:

```python
def validate_kpi_source(kpi_report: dict) -> bool:
    """Validate KPI source for GO gate."""
    source = kpi_report.get('source')
    
    if source == 'bybit_truth':
        return True  # Canonical for live
    
    if source == 'paper_journal_sim':
        if kpi_report.get('mode') == 'live':
            raise ValueError("Cannot use paper data for live GO!")
        return True  # OK for paper mode GO
    
    # Legacy or unknown source
    raise ValueError(f"Unknown KPI source: {source}")
```

### Step 4: Update KPI Calculators

Modify KPI calculation scripts to include source labels:

```python
# For Bybit KPI calculator
report = {
    "source": "bybit_truth",
    "source_label": "CANONICAL FOR GO GATES",
    "canonical": True,
    # ... rest of report
}

# For Paper KPI calculator
report = {
    "source": "paper_journal_sim",
    "source_label": "SIMULATION - NOT CANONICAL FOR GO",
    "canonical": False,
    # ... rest of report
}
```

## Enforcement

### Pre-Commit Checks

Add to validation:
```bash
# Check all new KPI reports have source labels
scripts/validate/kpi_source_check.py docs/validation/evidence/
```

### GO Gate Validation

GO gates MUST fail if:
- KPI report lacks source label
- Source is `paper_journal_sim` but mode is `live`
- Mixed sources detected within calculation

### CI/CD Pipeline

Add gate:
```yaml
- name: Validate KPI Source Labels
  run: |
    python scripts/validate/kpi_source_check.py \
      --require-label \
      --canonical-only-for-live \
      docs/validation/evidence/
```

## Source of Truth Verification

### Cross-Reference with Live Reconciliation

The canonical status of `bybit_truth` is verified by:
- `docs/validation/evidence/LIVE-RECONCILIATION-20260310.json`
- Direct API comparison with Bybit executions
- Zero-match journal comparison confirming separation

### Regular Audits

Monthly reconciliation:
1. Query Bybit API for execution history
2. Compare with stored KPI reports
3. Verify source labels match data origin
4. Flag mismatches for investigation

## Examples

### Example 1: Validating a Live GO Report

```python
kpi_report = load_report("BYBIT-TRUTH-KPI-20260310.json")

assert kpi_report['source'] == 'bybit_truth'
assert kpi_report['source_label'] == 'CANONICAL FOR GO GATES'
assert kpi_report['canonical'] == True

# Safe to use for live GO gate
go_decision = evaluate_go_gate(kpi_report)
```

### Example 2: Rejecting Mixed Source

```python
kpi_report = load_report("SUSPICIOUS-KPI-20260310.json")

if kpi_report.get('source') not in ['bybit_truth', 'paper_journal_sim']:
    raise ValueError("Unknown source - cannot evaluate GO gate")

if kpi_report['source'] == 'paper_journal_sim' and mode == 'live':
    raise ValueError("Cannot use paper simulation for live trading GO!")
```

### Example 3: Paper Mode Validation

```python
kpi_report = load_report("PAPER-SIM-KPI-20260310.json")

assert kpi_report['source'] == 'paper_journal_sim'
assert kpi_report['source_label'] == 'SIMULATION - NOT CANONICAL FOR GO'

# OK for paper mode GO
if mode == 'paper':
    go_decision = evaluate_go_gate(kpi_report)
```

## References

- **ADR-007**: Architecture decision record for this rule
- **LIVE-RECONCILIATION-20260310**: Evidence proving source separation
- **PARTY-MODE-KPI-FIX-001-CORRECTED**: Root cause analysis
- **EVIDENCE-INDEX**: Complete list of KPI artifacts

## Contact

For questions about source separation or canonical status:
- Review ADR-007 in `docs/architecture/`
- Check evidence index in `docs/validation/evidence/`
- Consult live reconciliation report for verification

---

*Rule Established: 2026-03-10*  
*Supersedes: All prior undocumented source mixing practices*  
*Authority: ChiseAI Architecture Review Board*
