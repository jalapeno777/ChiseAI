# BrainSpec vNext-B: Time-to-Improvement Optimization

## Version
- **ID**: vNext-B
- **Parent**: vCurrent (1.0.0-current)
- **Target**: Implement and minimize time_to_improvement tracking
- **Status**: DESIGN
- **Story ID**: BRAIN-CICD-2026-03-01
- **Batch**: 2B

## Problem Statement

Current `time_to_improvement = 0.0` (placeholder). No tracking of experiments needed to beat champion.

This prevents optimization of the R&D cycle and hides inefficiency in experimentation. Without tracking:
- We cannot measure how many experiments it takes to find improvements
- We cannot identify when experimentation is stuck in local optima
- We cannot optimize the experimentation process itself
- We waste compute on unproductive experiment series

## Changes from vCurrent

### 1. Role Modifications

#### 1.1 Jarvis - Add "ExperimentTracker" Role

**New Responsibilities:**
- Track experiment count per improvement cycle in Redis iterlog
- Require experiment documentation before approving continuation
- Monitor for experiment series exceeding 10 failed attempts without champion beat
- Log experiment hypotheses and outcomes for pattern analysis

**Enhanced Iteration Logging:**
```yaml
# New Redis iterlog structure for experiment tracking
bmad:chiseai:iterlog:story:<story_id>:experiments:
  - experiment_id: "EXP-001"
    hypothesis: "Increasing grid density improves Sharpe"
    approach: "2x grid spacing, same bounds"
    started_at: "2026-03-01T10:00:00Z"
    outcome: "pending|champion_beat|no_improvement|regression"
    champion_beat: false
    metrics:
      sharpe_before: 1.2
      sharpe_after: 1.15
      experiments_to_beat: null
```

#### 1.2 SeniorDev - Add "ChampionAnalysis" Responsibility

**New Responsibilities:**
- Run champion comparison before promotion recommendations
- Analyze why experiments failed to beat champion
- Document learnings from failed experiments
- Recommend experiment series termination when appropriate

**Required Actions:**
- Before recommending promotion: `chise-champion-compare --experiment-id=<id>`
- Document analysis in iterlog under `experiments:<id>:analysis`
- Provide go/no-go recommendation with rationale

#### 1.3 Dev - Add "ExperimentDocumentation" Responsibility

**New Responsibilities:**
- Document experiment hypothesis in branch names
- Record experiment approach in commit messages
- Log experiment outcomes in PR descriptions
- Maintain experiment journal in iterlog

**Branch Naming Convention:**
```
feature/<story-id>-EXP-<number>-<hypothesis-slug>

Examples:
- feature/ST-001-EXP-001-double-grid-density
- feature/ST-001-EXP-002-widen-stop-loss
- feature/ST-001-EXP-003-reduce-trade-frequency
```

**Commit Message Format:**
```
exp(<scope>): <hypothesis> (<story-id>-EXP-<number>)

Approach: <brief description of changes>
Expected: <expected outcome>

Refs: <story-id>-EXP-<number>
```

### 2. Policy Additions

#### 2.1 Experiment Documentation Policy (MANDATORY)

**Policy ID**: EXP-DOC-001
**Applies to**: All agents conducting experiments

**Requirements:**
1. Every experiment MUST document:
   - **Hypothesis**: What we believe will improve the champion
   - **Approach**: How we will test the hypothesis
   - **Expected Outcome**: Quantifiable prediction
   - **Actual Outcome**: Measured results
   - **Learning**: What we learned (success or failure)

2. Documentation locations:
   - Branch name: `feature/<story>-EXP-<number>-<hypothesis>`
   - Commit message: Include hypothesis and approach
   - PR description: Include experiment template
   - Redis iterlog: Structured experiment record

**Enforcement:**
- Jarvis rejects experiments without documentation
- Missing documentation = experiment does not count toward time_to_improvement

#### 2.2 Champion Comparison Policy (MANDATORY)

**Policy ID**: CHAMP-COMP-001
**Applies to**: SeniorDev, Jarvis

**Requirements:**
1. Before any promotion decision, SeniorDev MUST:
   - Run champion comparison analysis
   - Document comparison metrics
   - Provide explicit recommendation

2. Comparison must include:
   - Primary metric delta (e.g., Sharpe ratio)
   - Risk-adjusted comparison
   - Statistical significance (if applicable)
   - Compute cost of experiment

3. Jarvis must review and approve comparison before promotion

**Template:**
```markdown
## Champion Comparison: EXP-<number>

| Metric | Champion | Experiment | Delta | Significant? |
|--------|----------|------------|-------|--------------|
| Sharpe | 1.45 | 1.52 | +0.07 | Yes |
| Max DD | 12% | 11% | -1% | No |
| Trades/Day | 5.2 | 4.8 | -0.4 | Yes |

**Recommendation**: [PROMOTE | CONTINUE | ABORT]
**Rationale**: [Why]
```

#### 2.3 Experiment Count Tracking Policy (MANDATORY)

**Policy ID**: EXP-COUNT-001
**Applies to**: Jarvis

**Requirements:**
1. Jarvis MUST track:
   - Total experiments per improvement cycle
   - Experiments since last champion beat
   - Cumulative experiments to achieve each champion beat

2. Redis tracking structure:
```yaml
bmad:chiseai:brain:experiments:<story_id>:
  cycle_start: "2026-03-01T00:00:00Z"
  current_champion: "EXP-003"
  experiments_since_beat: 5
  total_experiments: 8
  history:
    - exp_id: "EXP-001"
      beat_champion: false
    - exp_id: "EXP-002"
      beat_champion: false
    - exp_id: "EXP-003"
      beat_champion: true
      experiments_to_beat: 3
```

#### 2.4 Experiment Series Abort Policy (MANDATORY)

**Policy ID**: EXP-ABORT-001
**Applies to**: Jarvis

**Requirements:**
1. Jarvis MUST abort experiment series when:
   - 10 consecutive experiments without champion beat
   - No meaningful learning from recent experiments
   - Compute cost exceeds budget without progress

2. Abort process:
   - Log abort decision with rationale
   - Document lessons learned
   - Reset experiment counter
   - Require new hypothesis before resuming

3. Exception process:
   - If strong rationale exists to continue, document exception
   - Require Aria or human approval for exception
   - Set new termination threshold (max 15 experiments)

### 3. Tool Usage Updates

#### 3.1 Jarvis Tool Usage Patterns

**Required Tool Usage:**

1. **Iteration Logging for Experiment Tracking:**
   ```python
   # Log experiment start
   redis_state_hset(
       name=f"bmad:chiseai:iterlog:story:{story_id}:experiments:{exp_id}",
       key="hypothesis",
       value=hypothesis
   )
   
   # Log experiment outcome
   redis_state_hset(
       name=f"bmad:chiseai:iterlog:story:{story_id}:experiments:{exp_id}",
       key="outcome",
       value=json.dumps({
           "beat_champion": True/False,
           "metrics": {...},
           "learning": "..."
       })
   )
   ```

2. **Experiment Count Monitoring:**
   ```python
   # Check experiment count before approving new experiment
   exp_count = redis_state_hget(
       name=f"bmad:chiseai:brain:experiments:{story_id}",
       key="experiments_since_beat"
   )
   
   if int(exp_count) >= 10:
       # Trigger abort review
       pass
   ```

3. **Qdrant for Experiment Pattern Analysis:**
   ```python
   # Search for similar past experiments
   qdrant_qdrant-find(
       query="grid density experiments that improved Sharpe"
   )
   ```

#### 3.2 SeniorDev Tool Usage Patterns

**Required Tool Usage:**

1. **Champion Comparison:**
   ```bash
   # Run before promotion recommendation
   python3 scripts/champion_compare.py --experiment-id=<id> --output=json
   ```

2. **Experiment Analysis Logging:**
   ```python
   # Log analysis in iterlog
   redis_state_rpush(
       name=f"bmad:chiseai:iterlog:story:{story_id}:experiments:{exp_id}:analysis",
       value=json.dumps({
           "analyzed_by": "senior-dev",
           "recommendation": "PROMOTE|CONTINUE|ABORT",
           "rationale": "..."
       })
   )
   ```

#### 3.3 Dev Tool Usage Patterns

**Required Tool Usage:**

1. **Branch Creation with Experiment ID:**
   ```bash
   # Follow naming convention
   git checkout -b feature/ST-001-EXP-001-double-grid-density
   ```

2. **Commit with Experiment Metadata:**
   ```bash
   # Include hypothesis in commit
   git commit -m "exp(grid): double grid density to improve Sharpe (ST-001-EXP-001)
   
   Approach: Reduce grid spacing from 1% to 0.5%
   Expected: Sharpe improvement of 0.1-0.2
   
   Refs: ST-001-EXP-001"
   ```

### 4. Evaluation Gates

#### 4.1 New BrainEval Gates

**Gate ID**: TIME-TO-IMPROVE-001
**Description**: time_to_improvement must be tracked (not placeholder)

**Criteria:**
- [ ] time_to_improvement is computed from actual experiment data
- [ ] Every experiment has documented hypothesis and outcome
- [ ] Experiment count is tracked per improvement cycle
- [ ] Champion comparison is run before promotion decisions

**Measurement:**
```python
# time_to_improvement calculation
def calculate_time_to_improvement(story_id):
    experiments = get_experiments(story_id)
    
    champion_beats = []
    count_since_last_beat = 0
    
    for exp in experiments:
        count_since_last_beat += 1
        if exp.beat_champion:
            champion_beats.append(count_since_last_beat)
            count_since_last_beat = 0
    
    if champion_beats:
        return {
            "average": sum(champion_beats) / len(champion_beats),
            "min": min(champion_beats),
            "max": max(champion_beats),
            "total_beats": len(champion_beats)
        }
    return None  # No champion beats yet
```

#### 4.2 New Metrics

**Metric 1: Average Experiments per Champion Beat**
- **ID**: AVG-EXP-PER-BEAT
- **Target**: < 10 experiments
- **Warning**: > 15 experiments
- **Critical**: > 20 experiments

**Metric 2: Experiment Success Rate**
- **ID**: EXP-SUCCESS-RATE
- **Formula**: `champion_beats / total_experiments`
- **Target**: > 15%
- **Warning**: < 10%
- **Critical**: < 5%

**Metric 3: Consecutive Failed Experiments**
- **ID**: CONSEC-FAILURES
- **Target**: < 5
- **Warning**: 8
- **Critical**: 10 (triggers abort review)

#### 4.3 Alerting Rules

**Alert 1: High Time-to-Improvement**
- **Condition**: time_to_improvement > 15 for 3 consecutive cycles
- **Severity**: WARNING
- **Action**: Review experimentation process, consider hypothesis quality

**Alert 2: Low Experiment Success Rate**
- **Condition**: EXP-SUCCESS-RATE < 10% over last 20 experiments
- **Severity**: WARNING
- **Action**: Review champion selection, consider strategy domain change

**Alert 3: Experiment Series Stuck**
- **Condition**: 10 consecutive experiments without champion beat
- **Severity**: CRITICAL
- **Action**: Abort series, require new hypothesis, document learnings

## Expected Impact

### KPI Targets

| KPI | Current (vCurrent) | Target (vNext-B) |
|-----|-------------------|------------------|
| time_to_improvement | 0.0 (placeholder) | Tracked, target < 10 |
| compute_cost | 0.0 (placeholder) | Better tracking |
| experiment_success_rate | Unknown | > 15% |
| avg_experiments_per_beat | Unknown | < 10 |

### Process Improvements

1. **Visibility**: Clear visibility into experimentation efficiency
2. **Optimization**: Ability to optimize the R&D cycle itself
3. **Abort Early**: Stop unproductive experiment series early
4. **Learning**: Better documentation of what works and what doesn't
5. **Compute Efficiency**: Reduce wasted compute on failed approaches

## Rollback Plan

If vNext-B underperforms:

1. **Immediate**: Revert to vCurrent BrainSpec
   - Disable experiment tracking requirements
   - Return to placeholder time_to_improvement
   - Maintain existing safety invariants

2. **Documentation**: 
   - Document learnings in iterlog
   - Store failure analysis in Qdrant
   - Update BrainSpec design notes

3. **Iteration**:
   - Design vNext-C addressing identified issues
   - Consider lighter-weight tracking approach
   - Focus on specific pain points from vNext-B

## Implementation Notes

### Phase 1: Infrastructure (Week 1)
- Set up Redis experiment tracking keys
- Create experiment logging utilities
- Update agent instructions (this spec)

### Phase 2: Adoption (Week 2-3)
- Jarvis begins tracking experiments
- Dev adopts branch naming convention
- SeniorDev runs champion comparisons

### Phase 3: Optimization (Week 4+)
- Analyze time_to_improvement data
- Identify patterns in successful experiments
- Optimize experimentation process based on data

## Compliance Checklist

- [ ] No risk cap modifications
- [ ] No promotion gate changes
- [ ] No live trading behavior changes
- [ ] Changes limited to roles/policies/tool usage
- [ ] No code changes to src/brain/ (design phase only)
- [ ] All safety invariants preserved

## References

- Parent BrainSpec: vCurrent (1.0.0-current)
- Related Skills: chiseai-brain-cicd, chiseai-worker-contracts
- Related Commands: chise-brain-upgrade-attempt
- Story: BRAIN-CICD-2026-03-01
- Batch: 2B
