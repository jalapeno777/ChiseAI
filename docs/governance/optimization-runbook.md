# Governance Optimization Runbook

## Overview

This runbook documents the optimization feedback loop process for governance metrics. It provides step-by-step instructions for conducting periodic optimization cycles.

## Optimization Cycle Process

### Phase 1: Baseline Analysis (AC1)

**Objective**: Analyze current governance metrics to identify bottlenecks and improvement opportunities.

**Steps**:
1. Retrieve Week 1 baseline data from Redis/Qdrant
2. Run analysis script: `python3 src/governance/optimization/analyze_baseline.py`
3. Review generated analysis in `docs/evidence/ST-GOV-MINI-002/week1-analysis.json`
4. Identify key bottlenecks and performance gaps

**Key Metrics to Analyze**:
- Retrieval latency (P95, mean)
- Memory hit rate
- Deduplication ratio
- Relevance scores (mean, precision@5, recall@10, MRR)
- Worker efficiency (locks per worker)
- Coverage ratio

**Output**: `docs/evidence/ST-GOV-MINI-002/week1-analysis.json`

### Phase 2: Generate Recommendations (AC2)

**Objective**: Generate 3+ actionable optimization recommendations based on analysis.

**Steps**:
1. Run recommendation engine: `python3 src/governance/optimization/generate_recommendations.py`
2. Review generated recommendations in `docs/evidence/ST-GOV-MINI-002/recommendations.json`
3. Validate each recommendation includes:
   - Problem statement
   - Root cause analysis
   - Proposed solution
   - Expected impact (quantified)
   - Implementation effort estimate

**Recommendation Categories**:
- Performance (latency, throughput)
- Accuracy (relevance, precision)
- Efficiency (deduplication, resource usage)
- Throughput (worker efficiency, parallelization)

**Output**: 
- `docs/evidence/ST-GOV-MINI-002/recommendations.json`
- Redis: `bmad:chiseai:governance:optimization:recommendations:v2`

### Phase 3: Implement Optimization (AC3)

**Objective**: Implement the highest-impact recommendation and measure improvement.

**Steps**:
1. Run implementation script: `python3 src/governance/optimization/implement_optimization.py`
2. The script automatically selects the highest-impact recommendation
3. Review implementation results in `docs/evidence/ST-GOV-MINI-002/optimization-results.json`
4. Validate before/after metrics show measurable improvement

**Selection Criteria**:
- Impact × Confidence × Risk / Effort
- Priority weighting (high > medium > low)
- Dependencies (prefer recommendations with no dependencies)

**Validation Criteria**:
- Memory hit rate >= 85%
- P95 retrieval latency < 50ms
- Cache warming completes < 30s
- No regression in MRR

**Output**: `docs/evidence/ST-GOV-MINI-002/optimization-results.json`

### Phase 4: Documentation (AC4)

**Objective**: Update governance documentation with optimization process and lessons learned.

**Steps**:
1. Update this runbook with any process improvements
2. Document lessons learned in `docs/tempmemories/lessons.md`
3. Update relevant skill documentation if new patterns discovered

**Documentation Updates**:
- Add new bottlenecks discovered
- Update threshold values based on learnings
- Document any new optimization techniques
- Record lessons learned

## Optimization Recommendations Template

Each recommendation should follow this structure:

```json
{
  "id": "REC-XXX",
  "title": "Brief description",
  "problem_statement": "What problem this addresses",
  "root_cause_analysis": "Why this problem exists",
  "proposed_solution": "How to fix it",
  "expected_impact": {
    "metric": "metric_name",
    "current_value": 0.0,
    "target_value": 0.0,
    "improvement_percent": 0.0,
    "confidence": "high|medium|low"
  },
  "implementation_effort": {
    "story_points": 0,
    "duration_days": 0,
    "complexity": "low|medium|high",
    "risk_level": "low|medium|high"
  },
  "implementation_steps": ["step1", "step2", ...],
  "validation_criteria": ["criterion1", "criterion2", ...],
  "priority": "high|medium|low",
  "category": "performance|accuracy|efficiency|throughput",
  "dependencies": []
}
```

## Key Thresholds

| Metric | Good | Needs Improvement | Critical |
|--------|------|-------------------|----------|
| Memory Hit Rate | >= 80% | 70-79% | < 70% |
| Retrieval P95 | < 50ms | 50-100ms | > 100ms |
| Relevance Mean | >= 0.8 | 0.7-0.79 | < 0.7 |
| Deduplication | >= 0.8 | 0.7-0.79 | < 0.7 |
| MRR | >= 0.9 | 0.8-0.89 | < 0.8 |
| Coverage | >= 0.95 | 0.9-0.94 | < 0.9 |

## Lessons Learned

### Week 2 Optimization (ST-GOV-MINI-002)

**Key Findings**:
1. Memory hit rate of 75% is below optimal threshold (80%+)
2. Relevance mean score of 0.784 indicates retrieval quality can be improved
3. Deduplication ratio of 0.7 has room for improvement (target 0.85)

**Successful Optimizations**:
1. **Cache Warming and TTL Optimization** (REC-001)
   - Increased memory hit rate from 75% to 88% (+17.3%)
   - Reduced retrieval mean latency from 25ms to 18ms (+28%)
   - Implementation: 2 SP, 3 days

**Recommendations for Future Cycles**:
- Implement cache warming as part of agent startup sequence
- Consider hybrid search for relevance improvement
- Add semantic deduplication for better efficiency

## Automation

The optimization cycle is partially automated through:

1. **Baseline Analysis Script**: `src/governance/optimization/analyze_baseline.py`
2. **Recommendation Engine**: `src/governance/optimization/generate_recommendations.py`
3. **Implementation Script**: `src/governance/optimization/implement_optimization.py`

## Schedule

- **Weekly**: Automated metrics collection
- **Bi-weekly**: Baseline analysis and recommendation generation
- **Monthly**: Full optimization cycle implementation

## Contact

For questions about the optimization process, contact:
- Governance Team: governance@chiseai.local
- Optimization Lead: ST-GOV-MINI-002
