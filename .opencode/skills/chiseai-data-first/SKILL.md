---
name: chiseai-data-first
description: Enforce Phase 0 data gathering completion before analysis, modeling, or strategy recommendations.
metadata:
  version: "2.0"
  opencode_min_version: "1.1.60"
  author: "ChiseAI Team"
  last_updated: "2026-02-23"
---

# chiseai-data-first

## Goal

Avoid building analysis on incomplete or low-quality data foundations. Ensure every decision is grounded in verified, high-quality data before proceeding to modeling, strategy, or implementation.

## When To Use

### Primary Use Cases

- **Starting any new story or epic** - Before any analysis or implementation work
- **Strategy generation** - Before recommending any trading strategy
- **Backtesting work** - Before running any historical simulations
- **Model development** - Before training or fine-tuning any model
- **Performance analysis** - Before analyzing system or strategy performance
- **Risk assessment** - Before evaluating or adjusting risk parameters
- **Data pipeline work** - When modifying data ingestion or transformation

### Specific Scenarios

| Scenario | Required Data | Phase 0 Duration |
|----------|---------------|------------------|
| New strategy backtest | OHLCV, fills, order book snapshots | 1-2 hours |
| Model training | Labeled dataset, feature catalog | 2-4 hours |
| Performance analysis | Execution logs, PnL data, metrics | 30 min - 1 hour |
| Risk parameter tuning | Historical drawdowns, volatility data | 1-2 hours |
| System optimization | Profiling data, bottleneck metrics | 30 min - 1 hour |

### The "Data-First" Mindset

Before asking "What should we build?" ask:
1. What data do we have?
2. What data do we need?
3. Is the data quality sufficient?
4. What assumptions are we making about the data?

## When Not To Use

### Exceptions (Proceed Without Full Phase 0)

1. **Emergency hotfixes** - Production issue requiring immediate fix
   - Document: "Skipping Phase 0 due to P0 production issue"
   - Follow-up: Schedule Phase 0 review post-fix

2. **Pure refactoring** - No data dependencies
   - Condition: Changes only affect code structure, not behavior
   - Verify: No data queries, transformations, or outputs modified

3. **Documentation updates** - No code execution
   - Condition: Only markdown/yaml changes
   - Verify: No code blocks executed or data referenced

4. **Configuration changes** - If data sources unchanged
   - Condition: Only parameter tuning with existing validated data
   - Verify: Data pipeline proven stable for 7+ days

### Why These Are Exceptions

Each exception carries risk:
- **Hotfixes**: May introduce bugs that data analysis would have prevented
- **Refactoring**: May break implicit data contracts
- **Docs**: May document outdated data behavior
- **Config changes**: May violate constraints visible only in data

Always document why Phase 0 was skipped and what risks were accepted.

## Rules (Non-Negotiable)

1. **Finish Phase 0 data gathering before deeper analysis**
2. **If data is incomplete, mark the story blocked and specify exactly what data is missing**
3. **Record data sources and data-quality assumptions in Redis iterlog**
4. **Never proceed to modeling/strategy with known data gaps**
5. **Always validate data freshness before analysis**

## Phase 0 Data Gathering Checklist

### Step 1: Identify Required Data

- [ ] List all data sources needed for the task
- [ ] Identify data format requirements (schema, granularity)
- [ ] Determine time range needed
- [ ] Note any data transformations required

### Step 2: Verify Data Availability

- [ ] Check Redis for cached data
- [ ] Check PostgreSQL for historical data
- [ ] Check Qdrant for relevant prior findings
- [ ] Verify API endpoints are accessible
- [ ] Confirm data pipeline is operational

### Step 3: Assess Data Quality

- [ ] Check for missing values
- [ ] Verify data completeness (expected rows vs actual)
- [ ] Check for outliers or anomalies
- [ ] Validate data types and formats
- [ ] Cross-reference with known-good samples

### Step 4: Document Findings

- [ ] Record data sources in Redis iterlog
- [ ] Note any quality issues discovered
- [ ] List assumptions made about data
- [ ] Flag any gaps that need resolution

### Step 5: Gate Decision

- [ ] All required data available? → Proceed to Phase 1
- [ ] Data incomplete but workable? → Document gaps, proceed with caution
- [ ] Critical data missing? → Block story, specify exactly what's needed

## Data Quality Gates

### Level 1: Availability Gate

**Question**: Is the data physically present?

| Check | Pass Criteria | Action on Fail |
|-------|---------------|----------------|
| Data exists | Required tables/files present | Block story |
| Time range sufficient | Covers analysis period | Extend data collection |
| API accessible | Returns valid responses | Fix infrastructure |

### Level 2: Completeness Gate

**Question**: Is the data sufficiently complete?

| Check | Pass Criteria | Action on Fail |
|-------|---------------|----------------|
| Missing values | < 5% missing | Impute or document |
| Row count | Within 10% of expected | Investigate gaps |
| Column coverage | All required fields present | Add to pipeline |

### Level 3: Accuracy Gate

**Question**: Is the data correct?

| Check | Pass Criteria | Action on Fail |
|-------|---------------|----------------|
| Schema validation | Matches expected schema | Fix ingestion |
| Value ranges | Within expected bounds | Investigate outliers |
| Cross-validation | Matches external sources | Audit pipeline |

### Level 4: Freshness Gate

**Question**: Is the data current enough?

| Check | Pass Criteria | Action on Fail |
|-------|---------------|----------------|
| Last update | Within acceptable lag | Trigger refresh |
| Timestamp continuity | No unexpected gaps | Fix pipeline |
| Version consistency | Using correct version | Update references |

## Templates

### Template 1: Data Requirements Document

```markdown
# Data Requirements for [STORY_ID]

## Overview
- **Story**: [Story title]
- **Date**: [Date]
- **Owner**: [Agent name]

## Required Data Sources

| Source | Type | Location | Status |
|--------|------|----------|--------|
| [Source 1] | [Redis/Postgres/API] | [Path/Table/Endpoint] | [Available/Missing/Partial] |

## Data Specifications

### Dataset 1: [Name]
- **Source**: [Where it comes from]
- **Format**: [Schema description]
- **Granularity**: [Time resolution]
- **Time Range**: [Start] to [End]
- **Expected Volume**: [Rows/Size]
- **Quality Notes**: [Known issues]

## Transformations Required
1. [Transformation 1]
2. [Transformation 2]

## Assumptions
1. [Assumption 1]
2. [Assumption 2]

## Gaps & Blockers
- [Gap 1]: [Impact and resolution needed]
```

### Template 2: Data Quality Report

```markdown
# Data Quality Report - [DATASET_NAME]

## Summary
- **Report Date**: [Date]
- **Dataset**: [Name]
- **Source**: [Location]
- **Overall Quality**: [High/Medium/Low/Unusable]

## Availability Check
- [x] Data exists at expected location
- [x] All required columns present
- [ ] Time range complete (gap: [description])

## Completeness Metrics
| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| Total Rows | [N] | [Expected] | [Pass/Fail] |
| Missing Values | [N%] | <5% | [Pass/Fail] |
| Duplicate Rows | [N] | 0 | [Pass/Fail] |

## Accuracy Checks
| Check | Result | Expected | Status |
|-------|--------|----------|--------|
| [Check 1] | [Value] | [Expected] | [Pass/Fail] |

## Anomalies Detected
1. [Anomaly description and impact]

## Recommendations
1. [Recommendation 1]
2. [Recommendation 2]

## Gate Decision
- [ ] PASS - Proceed to analysis
- [ ] CONDITIONAL - Proceed with documented caveats
- [ ] FAIL - Block until issues resolved
```

### Template 3: Phase 0 Completion Checklist

```markdown
# Phase 0 Completion - [STORY_ID]

## Story Information
- **Story ID**: [ID]
- **Title**: [Title]
- **Phase 0 Started**: [Timestamp]
- **Phase 0 Completed**: [Timestamp]
- **Duration**: [Time]

## Data Sources Confirmed

| Source | Location | Quality | Notes |
|--------|----------|---------|-------|
| [1] | [Path] | [H/M/L] | [Notes] |

## Quality Gates Passed
- [x] Level 1: Availability
- [x] Level 2: Completeness
- [x] Level 3: Accuracy
- [x] Level 4: Freshness

## Assumptions Documented
1. [Assumption 1]
2. [Assumption 2]

## Gaps Acknowledged
1. [Gap 1] - Risk: [Low/Medium/High] - Mitigation: [Strategy]

## Redis Iterlog Updated
- [ ] Data sources recorded
- [ ] Quality notes logged
- [ ] Assumptions documented

## Decision
- [x] **PROCEED** to Phase 1 (Analysis)
- [ ] **CONDITIONAL** proceed with caveats
- [ ] **BLOCKED** - Missing: [Description]

## Next Steps
1. [Next step 1]
2. [Next step 2]
```

## Examples

### Example 1: Strategy Backtest Data Gathering

**Scenario**: Developing a mean-reversion strategy for BTC/USDT

**Phase 0 Execution**:

1. **Identify Required Data**:
   - OHLCV data (1-minute granularity)
   - Order book snapshots (top 10 levels)
   - Funding rates (8-hour resolution)
   - Trade fills (if backtesting with execution model)

2. **Verify Availability**:
   ```bash
   # Check Redis for cached OHLCV
   redis-cli HGET "bmad:chiseai:data:cache:btcusdt:ohlcv" "1m"
   
   # Check PostgreSQL for historical data
   psql -c "SELECT COUNT(*) FROM ohlcv_1m WHERE symbol='BTCUSDT' AND time > '2025-01-01'"
   ```

3. **Assess Quality**:
   - Missing candles: 0.2% (acceptable)
   - Order book gaps: 5% during low-volume periods (document)
   - Funding rate lag: 4 hours max (acceptable for this strategy)

4. **Document Findings**:
   ```python
   redis_state_hset(
       name="bmad:chiseai:iterlog:story:ST-STRAT-001",
       key="data_sources",
       value=json.dumps({
           "ohlcv": {"source": "postgres", "quality": "high", "gaps": "0.2%"},
           "orderbook": {"source": "redis_cache", "quality": "medium", "gaps": "5%"},
           "funding": {"source": "api", "quality": "high", "lag": "4h"}
       })
   )
   ```

5. **Gate Decision**: PROCEED with documented gaps

**Outcome**: Strategy backtest completed successfully with documented data quality caveats.

### Example 2: Model Training Data Preparation

**Scenario**: Training a price prediction model

**Phase 0 Execution**:

1. **Data Requirements**:
   - Feature dataset: 50+ technical indicators
   - Labels: Next-period returns
   - Time range: 2 years minimum
   - Train/validation/test split: 60/20/20

2. **Quality Issues Found**:
   - 15% of labels missing in 2024 Q1 (exchange outage)
   - Feature correlation matrix shows multicollinearity
   - Class imbalance: 70% negative returns

3. **Resolution**:
   - Fill missing labels with forward-fill (document assumption)
   - Apply PCA to reduce multicollinearity
   - Use stratified sampling for train/test split

4. **Blocker Encountered**:
   - Critical: Volume profile data missing for 3 months
   - Resolution: Pause Phase 0, request data pipeline fix
   - Story marked BLOCKED with specific data requirement

**Outcome**: Story blocked until data pipeline fixed. Pipeline team notified.

### Example 3: Performance Analysis Data Validation

**Scenario**: Analyzing strategy performance over last quarter

**Phase 0 Execution**:

1. **Quick Data Check**:
   ```python
   # Verify execution logs exist
   logs = redis_state_lrange("bmad:chiseai:execution:logs", 0, -1)
   assert len(logs) > 0, "No execution logs found"
   
   # Check PnL data freshness
   last_update = redis_state_hget("bmad:chiseai:metrics:pnl", "last_update")
   assert (now - last_update) < timedelta(hours=1), "PnL data stale"
   ```

2. **Quality Verification**:
   - All trades have corresponding fills
   - PnL sums match account balance changes
   - No duplicate trade IDs

3. **Document and Proceed**:
   - Data quality: HIGH
   - Freshness: Current (5-minute lag)
   - Completeness: 100%

**Outcome**: Performance analysis completed with high confidence in data quality.

### Example 4: Risk Parameter Tuning

**Scenario**: Adjusting position sizing based on historical volatility

**Phase 0 Execution**:

1. **Identify Required Data**:
   - Historical volatility series (daily, 30-day rolling)
   - Position sizes and outcomes
   - Drawdown events with timestamps
   - Correlation matrix across assets

2. **Verify Data Sources**:
   ```python
   # Check volatility data availability
   vol_data = query_postgres(
       "SELECT date, volatility_30d FROM volatility_daily "
       "WHERE symbol IN ('BTC', 'ETH', 'SOL') AND date > '2024-01-01'"
   )
   
   # Verify drawdown data
   drawdowns = query_postgres(
       "SELECT * FROM drawdown_events WHERE severity > 0.05"
   )
   ```

3. **Quality Assessment**:
   - Volatility data: Complete, daily updates
   - Drawdown events: Manually verified, high accuracy
   - Correlation matrix: Recalculated daily, consistent

4. **Gate Decision**: PROCEED - All data quality gates passed

**Outcome**: Risk parameters adjusted with full confidence in underlying data.

### Example 5: Data Pipeline Debugging

**Scenario**: Investigating data quality issues in ingestion pipeline

**Phase 0 Execution**:

1. **Problem Identification**:
   - Monitoring shows increased data gaps
   - Some timestamps are out of order
   - Duplicate entries detected

2. **Data Investigation**:
   ```python
   # Check for gaps
   gaps = find_time_gaps("ohlcv_1m", "BTCUSDT", start="2025-01-01")
   print(f"Found {len(gaps)} gaps exceeding 1 minute")
   
   # Check for duplicates
   dups = query_postgres(
       "SELECT time, COUNT(*) FROM ohlcv_1m "
       "GROUP BY time HAVING COUNT(*) > 1"
   )
   
   # Check timestamp ordering
   out_of_order = check_timestamp_order("ohlcv_1m", "BTCUSDT")
   ```

3. **Root Cause**:
   - Multiple ingestion sources writing simultaneously
   - No deduplication in pipeline
   - Network latency causing out-of-order delivery

4. **Resolution Plan**:
   - Add deduplication step to pipeline
   - Implement timestamp ordering check
   - Add monitoring for data quality

**Outcome**: Pipeline issues documented, fix planned as separate story.

## Anti-Patterns to Avoid

### Anti-Pattern 1: Assumption Without Verification

❌ **Wrong**:
```markdown
# Analysis Plan
We'll use the OHLCV data to backtest the strategy.
[Proceeds directly to analysis]
```

✅ **Right**:
```markdown
# Phase 0: Data Gathering
- Verify OHLCV data exists for target period
- Check for gaps and quality issues
- Document data sources before analysis
```

### Anti-Pattern 2: Skipping Quality Gates

❌ **Wrong**:
- "The data looks fine, let's proceed"
- No quality checks performed
- No documentation of data assumptions

✅ **Right**:
- Run all 4 quality gates
- Document findings in Redis
- Get explicit gate decision (PROCEED/BLOCKED)

### Anti-Pattern 3: Silent Data Gaps

❌ **Wrong**:
- Notice missing data but don't document
- Assume missing data won't affect analysis
- Don't communicate gaps to stakeholders

✅ **Right**:
- Document every gap discovered
- Assess impact on analysis
- Communicate gaps and their implications

### Anti-Pattern 4: Stale Data Usage

❌ **Wrong**:
- Use cached data without checking freshness
- Assume yesterday's data is still valid
- Don't verify timestamps

✅ **Right**:
- Always check data timestamps
- Verify data is within acceptable lag
- Trigger refresh if stale

## Decision Framework

### When to Block vs Proceed with Caveats

**Block the story when**:
- Critical data is completely missing
- Data quality is too low to be useful (>20% gaps)
- Data is stale beyond acceptable threshold
- Schema mismatch prevents processing

**Proceed with caveats when**:
- Minor gaps exist (<5%) with documented impact
- Data quality is acceptable but not ideal
- Some assumptions required but low risk
- Workaround available for gaps

### Data Quality Decision Matrix

| Quality Level | Gaps | Freshness | Action |
|---------------|------|-----------|--------|
| High | <1% | Current | PROCEED |
| Medium | 1-5% | <4h old | PROCEED with caveats |
| Low | 5-20% | <24h old | CAUTION, document risks |
| Unusable | >20% | >24h old | BLOCK, fix pipeline |

## Integration with Other Skills

### With chiseai-validation

Phase 0 data quality checks should be validated:
- Use `chise-precommit-gates.md` to verify data checks were run
- Include data validation in CI for data-dependent stories

### With chiseai-memory-ops

Store Phase 0 findings for reuse:
- Log data sources to Redis iterlog
- Store data quality patterns in Qdrant for future reference
- Cache verified data schemas for consistency

### With chiseai-incident-response

If data issues cause incidents:
- Log as P2 incident if data gap blocked delivery
- Post-mortem should include data pipeline review
- Prevention: Add data quality monitoring

### With chiseai-worker-contracts

When delegating data-dependent work:
- Include data requirements in SCOPE_GLOBS
- Specify required data quality level
- Document data assumptions in MEMORY_CONTEXT

## Quick Reference

### Phase 0 Checklist (Copy-Paste)

```markdown
## Phase 0: Data Gathering
- [ ] Identify required data sources
- [ ] Verify data availability
- [ ] Assess data quality (4 gates)
- [ ] Document findings in Redis
- [ ] Make gate decision (PROCEED/BLOCKED)
```

### Data Quality Thresholds

| Metric | Green | Yellow | Red |
|--------|-------|--------|-----|
| Missing values | <1% | 1-5% | >5% |
| Data freshness | <1h | 1-4h | >4h |
| Schema match | 100% | 95-99% | <95% |
| Cross-validation | <1% diff | 1-5% diff | >5% diff |

### Common Data Issues & Resolutions

| Issue | Detection | Resolution |
|-------|-----------|------------|
| Missing data | Row count check | Impute or extend collection |
| Stale data | Timestamp check | Trigger refresh |
| Schema drift | Validation check | Update pipeline |
| Outliers | Statistical check | Investigate or filter |
| Duplicate rows | Unique key check | Deduplicate |

### Redis Keys for Data Operations

```
bmad:chiseai:data:cache:*         # Cached datasets
bmad:chiseai:data:quality:*       # Quality reports
bmad:chiseai:iterlog:story:ID:data_sources  # Story data log
```

### Time Budgets

| Task Type | Phase 0 Budget |
|-----------|----------------|
| Quick analysis | 15-30 min |
| Strategy backtest | 1-2 hours |
| Model training | 2-4 hours |
| System optimization | 30-60 min |

## Exit Conditions

- Data sources identified and documented.
- Data quality assumptions recorded in Redis iterlog.
- Phase 0 checklist completed OR story blocked with missing data specified.
- All required data is accessible and valid.

## Troubleshooting/Safety

- **Data unavailable**: Mark story as blocked, specify exact data needed, do not proceed with assumptions.
- **Stale data**: Check timestamps, verify data is current for the analysis timeframe.
- **Quality concerns**: Document issues in iterlog, escalate to Jarvis if data quality blocks progress.
- **Never skip Phase 0**: Building on bad data creates cascading failures.

## Related Skills

- `chiseai-risk-audit` - Validates risk assumptions that depend on data quality
- `chiseai-memory-ops` - Records data sources in Redis iterlog

## Related Commands

- `.opencode/command/chise-iterloop-start.md` - Initialize iteration with data check
- `.opencode/command/chise-precommit-gates.md` - Validate data requirements met
- `.opencode/command/chise-check-ownership.md` - Verify data access permissions
