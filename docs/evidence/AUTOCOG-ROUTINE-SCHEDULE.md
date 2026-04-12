# Autocog Routine Schedule Documentation

## Overview

The Autocog system operates on a 3-tier routine cadence for continuous autonomous evaluation and improvement. This document describes the schedule, manual trigger procedures, disable mechanism, and alert routing.

---

## 3-Tier Cadence Schedule

| Tier | Name              | Frequency     | Trigger                             | Scripts                                                                                 | Output                              |
| ---- | ----------------- | ------------- | ----------------------------------- | --------------------------------------------------------------------------------------- | ----------------------------------- |
| 1    | **Heartbeat**     | Every 6 hours | Cron: `0 */6 * * *`                 | `scripts/evaluation/run_6h_eval.sh`                                                     | Short health ping to `#autocog-log` |
| 2    | **Weekly Review** | Weekly        | Cron: `0 0 * * 0` (Sunday midnight) | `scripts/evaluation/run_weekly_eval.sh` + `scripts/autocog_weekly_summary.py`           | Summary posted to `#autocog-log`    |
| 3    | **Monthly Audit** | Monthly       | Cron: `0 0 1 * *` (1st of month)    | `scripts/evaluation/run_mini_eval.py` + `scripts/evaluation/repeated_issue_analyzer.py` | Full audit report to `#alerts`      |

### Cron Configuration (`.woodpecker/cron-eval.yaml`)

```yaml
- name: autocog-heartbeat
  cron: "0 */6 * * *"
  script: scripts/evaluation/run_6h_eval.sh

- name: autocog-weekly
  cron: "0 0 * * 0"
  script: scripts/evaluation/run_weekly_eval.sh

- name: autocog-monthly
  cron: "0 0 1 * *"
  script: scripts/evaluation/run_mini_eval.py
```

---

## Drift Score Thresholds

| Threshold    | Value  | Meaning                               | Action                              |
| ------------ | ------ | ------------------------------------- | ----------------------------------- |
| **Warning**  | `0.5`  | Drift detected but not critical       | Log warning; post to `#autocog-log` |
| **Critical** | `0.85` | Significant drift requiring attention | Immediate alert to `#alerts`        |

The drift score is computed by `src/autonomous_cognition/drift/concept_drift.py` and `src/persona/evaluator.py`.

**Code reference:**

- `src/persona/evaluator.py` → `compute_drift_score()` returns `overall_drift_score`
- Threshold check in `scripts/eval/run_persona_harness.py`: exit 0 if `drift_score >= threshold`, exit 1 otherwise

---

## How to Trigger Manually

### Heartbeat (6h Eval) Manually

```bash
# Run the 6-hour evaluation script directly
python3 scripts/evaluation/run_6h_eval.sh

# Or via the autonomy cadence controller
python3 scripts/evaluation/autonomy_cadence_controller.py --cadence heartbeat
```

### Weekly Review Manually

```bash
# Run weekly evaluation
bash scripts/evaluation/run_weekly_eval.sh

# Generate weekly summary report (reads last 7 days of cycles)
python3 scripts/autocog_weekly_summary.py --days 7 --output-dir _bmad-output/autocog/summaries

# Run weekly reflection
python3 scripts/evaluation/run_weekly_reflection.py
```

### Monthly Audit Manually

```bash
# Run monthly evaluation
python3 scripts/evaluation/run_mini_eval.py

# Run repeated issue analyzer for monthly audit
python3 scripts/evaluation/repeated_issue_analyzer.py --period monthly

# Canary health check (full audit)
python3 scripts/autocog_canary_health_check.py --verbose
```

### Run All Cadences Sequentially

```bash
# Via the autonomy cadence tick wrapper
bash scripts/cron/autonomy_cadence_tick.sh
```

---

## How to Disable

### Feature Flag

The entire autocog routine system is controlled by the feature flag `autocog:routine:enabled`.

**To disable:**

```bash
# Via Redis CLI
redis-cli -h host.docker.internal -p 6380 SET autocog:routine:enabled false

# Via Python
import redis
r = redis.Redis.from_url("redis://host.docker.internal:6380/1")
r.set("autocog:routine:enabled", "false")
```

**To re-enable:**

```bash
redis-cli -h host.docker.internal -p 6380 SET autocog:routine:enabled true
```

**Check current status:**

```bash
redis-cli -h host.docker.internal -p 6380 GET autocog:routine:enabled
```

### Cron Disabling

To disable a specific cron job, either:

1. Remove or comment out the entry in `.woodpecker/cron-eval.yaml`
2. Or rename the script so cron cannot find it

---

## Alert Channels

| Channel            | Use Case                                                                  | Cadence           |
| ------------------ | ------------------------------------------------------------------------- | ----------------- |
| **`#alerts`**      | Critical drift (score ≥ 0.85), constitution violations, critical failures | All tiers         |
| **`#autocog-log`** | Weekly summaries, heartbeat health pings, routine status updates          | Heartbeat, Weekly |

### Alert Routing Logic

Alerts are routed based on severity:

- **HIGH / CRITICAL** → `#alerts` (immediate)
- **MEDIUM / LOW** → `#autocog-log` (digest)

See `src/governance/notifications/event_router.py` and `src/governance/notifications/severity_mapper.py`.

---

## File Locations

### Scripts Directory

| Script                                              | Purpose                               |
| --------------------------------------------------- | ------------------------------------- |
| `scripts/evaluation/run_6h_eval.sh`                 | Heartbeat evaluation trigger          |
| `scripts/evaluation/run_weekly_eval.sh`             | Weekly evaluation trigger             |
| `scripts/evaluation/run_mini_eval.py`               | Monthly audit evaluation              |
| `scripts/evaluation/autonomy_cadence_controller.py` | Unified cadence controller            |
| `scripts/evaluation/repeated_issue_analyzer.py`     | Issue pattern analysis                |
| `scripts/autocog_weekly_summary.py`                 | Weekly summary report generator       |
| `scripts/autocog_canary_health_check.py`            | Canary mode health check (exit 0/1/2) |
| `scripts/autocog_canary_report.py`                  | Canary report generator               |
| `scripts/cron/autonomy_cadence_tick.sh`             | Cron wrapper for cadence tick         |

### Source Files

| File                                              | Purpose                                         |
| ------------------------------------------------- | ----------------------------------------------- |
| `src/evaluation/mini_brain_eval.py`               | MiniBrainEval engine (6h/daily/weekly cadences) |
| `src/autonomous_cognition/drift/concept_drift.py` | Drift score computation                         |
| `src/persona/evaluator.py`                        | Persona drift evaluation                        |
| `src/governance/notifications/event_router.py`    | Alert routing                                   |
| `src/governance/notifications/severity_mapper.py` | Severity mapping                                |

### Output Directories

| Directory                           | Content                            |
| ----------------------------------- | ---------------------------------- |
| `_bmad-output/autocog/cycles/`      | Cycle artifacts (`autocog-*.json`) |
| `_bmad-output/autocog/summaries/`   | Weekly summary reports             |
| `docs/governance/self_assessments/` | Self-assessment JSON files         |
| `docs/evidence/`                    | Evidence documents                 |

### Configuration

| File                                 | Purpose                                             |
| ------------------------------------ | --------------------------------------------------- |
| `.woodpecker/cron-eval.yaml`         | Cron job definitions for all 3 tiers                |
| `config/aria/governance-policy.yaml` | Governance policy with `drift_score_required: true` |

---

## Related Documentation

- [Autocog Weekly Summary Script](./autocog_weekly_summary.py)
- [Canary Health Check Script](./autocog_canary_health_check.py)
- [Governance Policy](../config/aria/governance-policy.yaml)
- [Autocog Registry](../scripts/evaluation/autocog_registry.yaml)
