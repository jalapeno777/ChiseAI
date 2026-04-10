# Memory Audit Framework — Hybrid Memory Architecture

> **Story**: REPO-001 (Memory Systems Research)
> **Date**: 2026-04-09
> **Status**: Audit Plan Defined — Phase 1 PoC Pending Approval

---

## 1. Audit Philosophy

### Core Principles

1. **Evidence-first, no guessing** — every claim requires measurable evidence
2. **Before/after comparison** — all improvements measured against baseline
3. **Quantitative metrics** — human judgment is last resort, not first tool
4. **Human-in-the-loop scoring** — quality assessment uses trained evaluators
5. **Statistical significance required** — no declare victory without p < 0.05

### Audit Workflow

```
Phase 1 PoC
  └─ Run Observer on last 10 completed iterlogs
       ↓
  Score sample (human)
       ↓
  Measure 5 metrics vs baseline
       ↓
  Phase Gate Decision → proceed / rework / kill

Phase 2-5
  └─ Continuous monitoring
       ↓
  Grafana dashboard
       ↓
  Quarterly review
       ↓
  Rollback if kill criteria hit
```

---

## 2. Baseline Metrics (Before — Measurable Now)

Capture baseline BEFORE any implementation begins. These establish the starting point against which all improvements are measured.

### a) Recall Accuracy

**What to measure**: Retrieval hit rate on 20-30 questions formulated from existing Qdrant memories.

**How to measure**:

```bash
# 1. Collect 20-30 questions from existing Qdrant memories
# 2. Run each question against current Qdrant retrieval
# 3. Score hit/miss (hit = answerable from retrieved context)

# Example Redis key for tracking:
bmad:chiseai:memory:baseline:recall_questions
# Stored as JSON: [{"q": "...", "expected_answer": "...", "story_id": "..."}]
```

**Expected range**: 40-70% (current state, before hybrid)

**Data source**: `bmad:chiseai:memory:baseline:recall_accuracy`

---

### b) Context Loading Cost

**What to measure**: Tokens loaded at session start for typical iteration (git session, PR review, incident response).

**How to measure**:

```python
# At session start, instrument memory loading:
token_count = count_tokens(loaded_context)
redis_state_hset(
    name="bmad:chiseai:memory:baseline:context_cost",
    key=f"session_{timestamp}",
    value=token_count
)
```

**Expected range**: 8K-25K tokens (typical ChiseAI iteration)

**Data source**: `bmad:chiseai:memory:baseline:context_cost`

---

### c) Dedup Effectiveness

**What to measure**: Near-duplicate count in Qdrant (cosine similarity > 0.95).

**How to measure**:

```python
# Sample 100 random Qdrant memories
# For each pair, compute cosine similarity
# Count pairs with similarity > 0.95

dedup_ratio = near_duplicate_count / total_memory_count
```

**Expected range**: 5-20% near-duplicate rate (current state)

**Data source**: `bmad:chiseai:memory:baseline:dedup_effectiveness`

---

### d) Memory Staleness

**What to measure**: Percentage of memories with no access in 30+ days.

**How to measure**:

```sql
-- Qdrant SQL (if available) or Python script:
-- SELECT COUNT(*) FROM memories WHERE last_accessed_at < NOW() - INTERVAL '30 days';
staleness_rate = stale_memory_count / total_memory_count
```

**Expected range**: 20-50% stale (estimated based on iterlog archival patterns)

**Data source**: `bmad:chiseai:memory:baseline:staleness`

---

### e) Compression Ratio

**What to measure**: Raw iterlog tokens vs stored memory tokens.

**How to measure**:

```python
# For each completed iterlog:
raw_tokens = count_tokens(iterlog_messages)
stored_tokens = count_tokens(qdrant_memory_content)
compression_ratio = raw_tokens / stored_tokens
```

**Baseline**: 1:1 (no compression — current state)

**Note**: Compression ratio metric only becomes meaningful AFTER Phase 1 is implemented. Baseline is 1:1.

**Data source**: `bmad:chiseai:memory:baseline:compression_ratio`

---

### f) Memory Coverage

**What to measure**: Percentage of iteration logs that produce lasting memories (in Qdrant after 7+ days).

**How to measure**:

```python
# Track:
# - total iteration logs completed (Redis counter)
# - iteration logs with at least one Qdrant memory after 7 days
coverage_rate = covered_logs / total_logs
```

**Expected range**: 30-60% (estimated — many small iterations don't produce lasting memories)

**Data source**: `bmad:chiseai:memory:baseline:coverage`

---

## 3. Phase 1 PoC Audit Plan (After Observer Agent)

Phase 1 implements the Observer Agent only. Audit plan below measures whether PoC passes the gate for Phase 2.

### a) Observation Quality (Human-Scored Sample)

**What to measure**: 20 random observations from Observer output, human-scored on 4 dimensions.

**How to measure**:

```python
# Scoring rubric (1-5 each dimension):
observations = load_from_redis("bmad:chiseai:memory:observations:*")
sample = random.sample(observations, 20)

for obs in sample:
    accuracy      = human_score(1-5)  # factually correct?
    completeness  = human_score(1-5)  # captures all key facts?
    actionability = human_score(1-5)  # usable for future decisions?
    non_redundancy = human_score(1-5)  # not repeating prior observations?
```

**Success criteria**: Mean score ≥ 3.5 on all 4 dimensions. No single dimension below 2.5.

**Data source**: `bmad:chiseai:memory:poc:observation_quality`

---

### b) Compression Ratio

**What to measure**: Raw tokens → observation tokens ratio.

**How to measure**:

```python
for iterlog in dry_run_iterlogs:
    raw_tokens = count_tokens(iterlog.messages)
    obs_tokens = count_tokens(Observer.extract(iterlog))
    ratio = raw_tokens / obs_tokens

# Report: median ratio, p25/p95 range
```

**Target**: ≥ 5x compression (minimum to justify LLM call cost)

**Success criteria**: Median compression ≥ 5x. If <5x, Observer prompt may need tuning or threshold adjustment.

**Data source**: `bmad:chiseai:memory:poc:compression_ratio`

---

### c) Information Retention

**What to measure**: % of facts from raw messages surviving in observations.

**How to measure**:

```python
# For each dry-run iterlog:
raw_facts = extract_facts_human(iterlog.messages)  # ground truth via human
obs_facts = Observer.extract(iterlog)

# Compute overlap:
retention_rate = len(raw_facts ∩ obs_facts) / len(raw_facts)
```

**Target**: > 80% retention (allow for compression but not for information loss)

**Success criteria**: Median retention ≥ 80%. If <80%, Observer prompt needs revision.

**Data source**: `bmad:chiseai:memory:poc:information_retention`

---

### d) False Positive Rate

**What to measure**: Fabricated or incorrect observations (verified against raw iterlog).

**How to measure**:

```python
# Human review of 20 observations:
# Mark each as: correct / incorrect / fabricated

false_positive_rate = incorrect_count / total_count
```

**Target**: < 5% false positive rate

**Success criteria**: FP rate < 5%. If >5%, Observer prompt requires immediate revision before Phase 2.

**Data source**: `bmad:chiseai:memory:poc:false_positive_rate`

---

### e) Processing Latency

**What to measure**: Time per observation batch (from raw messages → observations stored).

**How to measure**:

```python
import time
start = time.time()
observations = Observer.process_batch(raw_messages, threshold=30000)
latency = time.time() - start

# Store:
redis_state_hset(
    name="bmad:chiseai:memory:poc:processing_latency",
    key=f"batch_{timestamp}",
    value={"latency_s": latency, "tokens": len(raw_messages)}
)
```

**Target**: < 30 seconds for 10K tokens (LLM call + parsing + Redis write)

**Success criteria**: Median latency < 30s per batch. If >30s, investigate LLM API latency or batch size.

**Data source**: `bmad:chiseai:memory:poc:processing_latency`

---

## 4. A/B Test Protocol

### Purpose

Compare current stored memories (status quo) vs Observer-generated observations on the same iterlog set. Establishes whether Observer adds measurable value.

### Protocol

**Step 1**: Dry-run Observer on last 10 completed iteration logs (already completed, stored in Redis).

**Step 2**: Collect 10 Observer observation sets + 10 corresponding current-memory sets.

**Step 3**: For each of 10 iterlogs:

```python
# Run same 3-5 questions against:
question_set = generate_questions_from_iterlog(iterlog)

# A: retrieve from current memories (status quo)
answers_a = current_retrieval(question_set)

# B: retrieve from Observer observations
answers_b = observer_retrieval(question_set)

# Human score both answer sets (blind to source)
score_a = human_score(answers_a)
score_b = human_score(answers_b)
```

**Step 4**: Scoring rubric:

| Dimension      | Score 1              | Score 3              | Score 5               |
| -------------- | -------------------- | -------------------- | --------------------- |
| Accuracy       | Factually wrong      | Mostly correct       | Fully correct         |
| Completeness   | Missing key facts    | Some facts missing   | All key facts present |
| Actionability  | Not usable           | Conditionally usable | Directly actionable   |
| Non-redundancy | Repeats prior memory | Some overlap         | No redundant content  |

**Step 5**: Statistical significance test:

```python
# Paired t-test (if normal distribution) or Wilcoxon signed-rank test
from scipy import stats

t_stat, p_value = stats.wilcoxon(scores_a, scores_b)

# Declare significance only if p < 0.05
significant = p_value < 0.05
```

**Success threshold**: Observer must score higher on ≥ 7/10 iterlogs AND p < 0.05.

### Data Source

```
bmad:chiseai:memory:ab_test:iterlog_set        # 10 iterlog IDs
bmad:chiseai:memory:ab_test:scores_a           # status quo scores
bmad:chiseai:memory:ab_test:scores_b           # Observer scores
bmad:chiseai:memory:ab_test:statistical_result # t-stat, p-value
```

---

## 5. Phase Gate Decision Criteria

### Minimum Requirements to Proceed Phase 1 → Phase 2

ALL of the following must pass:

| Metric                              | Threshold                      | Measured By                    |
| ----------------------------------- | ------------------------------ | ------------------------------ |
| Observation quality (accuracy)      | Mean ≥ 3.5/5                   | Human scoring (n=20)           |
| Observation quality (completeness)  | Mean ≥ 3.5/5                   | Human scoring (n=20)           |
| Observation quality (actionability) | Mean ≥ 3.5/5                   | Human scoring (n=20)           |
| Compression ratio                   | Median ≥ 5x                    | Automated token count          |
| Information retention               | Median ≥ 80%                   | Human-verified fact extraction |
| False positive rate                 | < 5%                           | Human verification             |
| Processing latency                  | Median < 30s/batch             | Automated timing               |
| A/B test                            | Observer wins ≥ 7/10, p < 0.05 | Statistical test               |

### Kill Criteria

If ANY of the following occur, stop the program and do not proceed to Phase 2:

| Kill Criterion                                                    | Why It Stops the Program                                                   |
| ----------------------------------------------------------------- | -------------------------------------------------------------------------- |
| False positive rate > 15%                                         | Observer fabricates too frequently — trust in memory system is compromised |
| Compression ratio < 2x after 2 rounds of prompt tuning            | Observer not compressing enough to justify cost                            |
| Information retention < 60%                                       | Too much information loss — system degrades memory quality                 |
| A/B test: Observer loses 8/10 or more                             | Observer provides no measurable improvement over status quo                |
| Observer prompt engineering reaches round 3 without passing gates | Diminishing returns; re-evaluate approach                                  |

### Continue Conditions

If all Phase Gate metrics pass AND no kill criteria triggered:
→ Proceed to Phase 2 (Reflector Agent)

---

## 6. Ongoing Audit (Post-Implementation)

After full hybrid architecture is implemented (Phases 1-5 complete), the following metrics are tracked continuously.

### Continuous Metrics

| Metric               | Measurement                      | Cadence | Alert Threshold               |
| -------------------- | -------------------------------- | ------- | ----------------------------- |
| Recall accuracy      | Hit rate on 30-question eval set | Weekly  | Drop >10 points from baseline |
| Context loading cost | Avg tokens/session               | Daily   | > 30K tokens/session          |
| Dedup effectiveness  | Near-duplicate %                 | Weekly  | > 25% near-duplicate          |
| Memory staleness     | % 30+ day inactive               | Weekly  | > 60% stale                   |
| Compression ratio    | Daily median                     | Daily   | < 4x (3 consecutive days)     |
| Memory coverage      | % iterlogs → Qdrant              | Weekly  | < 50% coverage                |
| False positive rate  | Rolling 50-observation sample    | Weekly  | > 5%                          |
| Processing latency   | p95 batch time                   | Daily   | > 60s p95                     |

### Grafana Dashboard Panels

```
memory-hybrid-overview (dashboard)
├── Recall Accuracy (gauge, 0-100%)
├── Context Loading Cost (time series, tokens/session)
├── Compression Ratio (time series, 1x-50x scale)
├── Memory Coverage (gauge, 0-100%)
├── Staleness Rate (gauge, 0-100%)
├── Processing Latency p50/p95 (time series)
├── False Positive Rate (gauge, 0-10%)
└── Near-Duplicate Rate (gauge, 0-30%)
```

### Review Cadence

| Review              | Frequency | Owner         | Scope                                    |
| ------------------- | --------- | ------------- | ---------------------------------------- |
| Metric standup      | Daily     | Jarvis        | Latency, compression ratio alerts        |
| Weekly health       | Weekly    | Jarvis + Aria | All metrics vs thresholds                |
| Quarterly deep-dive | Quarterly | Aria → Craig  | Architecture fitness, taxonomy review    |
| Annual audit        | Annual    | External      | Independent evaluation of memory quality |

### Rollback Procedure

If ongoing metrics breach alert thresholds for 3+ consecutive weeks without remediation plan approved by Craig:

1. Set `MEMORY_HYBRID_ENABLED=false` (feature flag off)
2. Revert to pre-hybrid read path (Qdrant direct retrieval)
3. Retain observation data in Redis (do not delete — enables post-mortem analysis)
4. Schedule post-mortem within 5 business days
5. Submit BLOCKER_PACKET to Craig via Aria with evidence and remediation options

---

_Audit framework created by Jarvis (BMAD Orchestrator) — 2026-04-09_
_Permanent reference document — do not discard_
_Companion to: docs/research/memory-systems-evaluation-20260409.md_
