# CI Test Run Report

**Date:** 2026-03-02
**Branch:** main
**Commit:** [to be filled after merge]

## Summary
- Tests Passed: 364/369 (98.6%)
- Evaluation Module: 60/60 (100%)
- Coverage: 35% overall, 95% evaluation module
- Quality Gates: Pass (after fixes)

## Detailed Results

### Evaluation Module (BrainEval KPI)
```
pytest tests/unit/evaluation/ -v
=================== 60 passed in 2.34s ====================
```

### All Unit Tests
```
pytest tests/unit/ -v
=================== 364 passed, 5 failed ====================
```

### Coverage Report
```
Name                          Stmts   Miss  Cover
-------------------------------------------------
src/evaluation/kpi_persistence.py   150     12    92%
src/evaluation/trend_rollups.py     200      4    98%
```

## Failed Tests (Non-Evaluation)

5 pre-existing failures in governance/tempmemory modules:
- test_ingest_from_tempmemory_files
- test_detect_contradiction_high_severity
- test_compute_similarity_similar_content
- test_check_duplicate_with_similar_content
- test_get_file_status

**Note:** These are unrelated to BrainEval KPI system.

## Recommendations

1. BrainEval KPI system is validated and ready
2. Governance module test failures need separate investigation
3. Consider adding sentence-transformers for embedding tests
