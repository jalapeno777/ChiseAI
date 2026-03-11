---
type: summary
story_id: ST-001
created: 2026-03-11T00:00:00
tags: [eval, chiseai-memory-ops, skill-optimization]
---

# ST-SKILL-OPT-001 Eval Results

## Benchmark Summary
- **Skill**: chiseai-memory-ops
- **Total Evals**: 10
- **Passed**: 9
- **Failed**: 1
- **Pass Rate**: 90%
- **Threshold**: 80%
- **Status**: PASS

## Eval Coverage
| Eval | Query | Result |
|------|-------|--------|
| eval-001 | How do I start a story iteration with Redis? | PASS |
| eval-002 | Log a decision to the story iterlog | PASS |
| eval-003 | Store long-term knowledge in Qdrant | PASS |
| eval-004 | Refresh TTL on Redis keys | PASS |
| eval-005 | Claim scope ownership in Redis | PASS |
| eval-006 | What to do when Redis is unavailable? | PASS |
| eval-007 | Store metacognition prediction card | PASS |
| eval-008 | Query prior decisions from Qdrant | PASS |
| eval-009 | What's the weather like today? | PASS (correctly rejected) |
| eval-010 | How to write a Python function? | FAIL (false positive) |

## Metacognition
- **Prediction**: 80%+ pass rate expected
- **Outcome**: 90% pass rate achieved
- **Calibration**: Skill triggers appropriately on memory-related queries

## Notes
- One false positive on eval-010 (coding query)
- Overall skill performance exceeds threshold
- No skill modifications required
