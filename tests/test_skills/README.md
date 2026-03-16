# Skill Evaluation Test Suite

This directory contains tests for skill evaluation suites created under ST-SKILL-EVAL-002-P0.

## Purpose

Validate that P0 skills have high-quality evaluation suites with:
- Minimum 10 eval items per skill
- 80%+ pass rate
- Negative examples (should_trigger: false)
- Complete metadata (skill_component, expected_behavior)

## Running Tests

```bash
# Run all skill evaluation tests
pytest tests/test_skills/test_evaluations.py -v

# Run specific skill validation
pytest tests/test_skills/test_evaluations.py::TestSkillEvaluationSuites::test_evals_json_exists -v
```

## Skills Evaluated

1. **chiseai-memory-ops** - Redis and Qdrant memory operations
2. **chiseai-parallel-safety** - Parallel execution safety patterns
3. **chiseai-incident-response** - Incident logging and post-mortems
4. **chiseai-workflow-commands** - BMAD workflow command routing
5. **python-quality** - Python code quality verification

## Benchmark Results

Run benchmarks with:
```bash
python3 scripts/skill_evaluation/run_benchmarks.py
```

Results are saved to `docs/evidence/ST-SKILL-EVAL-002-P0-results-<timestamp>.json`
