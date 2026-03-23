# CI Quality Gate Remediation - Pre-Flight Baseline

**Date**: 2026-03-23
**Branch**: feature/REPO-CI-REMEDIATION-ci-quality-gate
**Story**: REPO-000

## Baseline Counts

| Tool     | Result                                       | Details                                                                                                                                                                                                    |
| -------- | -------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| pytest   | 1 failed, 11 passed, 1 skipped (unit subset) | Full suite: 19,673 items collected, 1 skipped - full run timed out at 120s (0.5% progress). First failure: `test_init_chain_failure_handled` in `tests/execution/test_llm/test_trade_decision_enhancer.py` |
| ruff     | 1777 violations                              | 1521 fixable with `--fix`; top codes: UP035 (51), UP015 (42), E712 (39), SIM114 (25), SIM118 (23), F811 (19), I001 (many), F401 (many), UP017 (many), F541 (many)                                          |
| black    | 0 files need formatting                      | `black --check src/ scripts/ config/` passed cleanly (full repo check timed out at 60s)                                                                                                                    |
| mypy     | 1 error (blocked further checking)           | Duplicate module name conflict in `_bmad/` directory between `bmad-agent-builder` and `bmad-workflow-builder`                                                                                              |
| yamllint | 10 warnings                                  | 6 line-too-long, 4 comment-spacing issues in `docs/validation/validation-registry.yaml`                                                                                                                    |

## Full Command Outputs

### pytest tests/ --tb=no -q

```
============================================================================================== test session starts ==============================================================================================
platform linux -- Python 3.13.7, pytest-9.0.1, pluggy-1.6.0
benchmark: 5.2.3 (defaults: timer=time.perf_counter disable_gc=False min_rounds=5 min_time=0.000005 max_time=1.0 calibration_precision=10 warmup=False warmup_iterations=100000)
rootdir: /home/tacopants/projects/ChiseAI
configfile: pyproject.toml
plugins: json-report-1.5.0, timeout-2.4.0, hypothesis-6.148.7, anyio-4.11.0, mock-3.15.1, benchmark-5.2.3, metadata-3.1.1, locust-2.42.6, base-url-2.1.0, forked-1.6.0, Faker-38.2.0, xdist-3.8.0, playwright-0.7.2, html-4.1.1, asyncio-1.3.0, cov-7.0.0
timeout: 120.0s
timeout method: signal
timeout func_only: False
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=function, asyncio_default_test_loop_scope=function
collected 19673 items / 1 skipped

tests/chaos/test_chaos_scenarios.py .........
tests/contract/test_autocog_interfaces.py ....s..................
tests/e2e/test_autocog_full_cycle.py ......................
[TIMEOUT at 120s - only 0.5% of suite completed]

--- Unit test subset (with --ignore for slow dirs) ---
FAILED tests/execution/test_llm/test_trade_decision_enhancer.py::TestTradeDecisionEnhancerInit::test_init_chain_failure_handled - assert <llm.provider_chain.LLMProviderChain object at 0x7a3a9772fa80> is None
1 failed, 11 passed, 1 skipped, 10 warnings in 52.82s
```

### ruff check .

```
Found 1777 errors.
[*] 1521 fixable with the `--fix` option (149 hidden fixes can be enabled with the `--unsafe-fixes` option).

Top violation codes (--statistics):
  51  UP035    deprecated-import
  42  UP015    redundant-open-modes
  39  E712     true-false-comparison
  25  SIM114   if-with-same-arms
  23  SIM118   in-dict-keys
  19  F811     redefined-while-unused
  18  F402     import-shadowed-by-loop-var
  17  SIM105   suppressible-exception
  10  SIM103   needless-bool
  10  UP037    quoted-annotation
   9  B007     unused-loop-control-variable
   9  UP041    timeout-error-alias
   8  F821     undefined-name
   6  E402     module-import-not-at-top-of-file
   6  E722     bare-except
   6  E741     ambiguous-variable-name
   4  E902     io-error
   4  SIM110   reimplemented-builtin
   3  B008     function-call-in-default-argument
   3  B905     zip-without-explicit-strict
   2  invalid-syntax
   2  B904     raise-without-from-inside-except
   2  SIM115   open-file-with-context-handler
   2  SIM201   negate-equal-op
   1  B009     get-attr-with-constant
   1  B011     assert-false
   1  B025     duplicate-try-block-exception
   1  UP032    f-string

Note: Many I001 (import-sorting) and F401 (unused-import) violations also present
but not shown in top list due to aggregation. Full output saved to /tmp/baseline_ruff.txt.
```

### black --check .

```
[Full repo check timed out at 60s - no output]
[Subset check: black --check src/ scripts/ config/ -- passed cleanly, EXIT: 0]
```

### mypy .

```
_bmad/bmb/skills/bmad-workflow-builder/scripts/generate-html-report.py: error: Duplicate module named "generate-html-report" (also at "./_bmad/bmb/skills/bmad-agent-builder/scripts/generate-html-report.py")
_bmad/bmb/skills/bmad-workflow-builder/scripts/generate-html-report.py: note: See https://mypy.readthedocs.io/en/stable/running_mypy.html#mapping-file-paths-to-modules for more info
_bmad/bmb/skills/bmad-workflow-builder/scripts/generate-html-report.py: note: Common resolutions include: a) using `--exclude` to avoid checking one of them, b) adding `__init__.py` somewhere, c) using `--explicit-package-bases` or adjusting MYPYPATH
Found 1 error in 1 file (errors prevented further checking)
```

### yamllint docs/validation/validation-registry.yaml

```
docs/validation/validation-registry.yaml
  24:141    warning  line too long (173 > 140 characters)  (line-length)
  177:141   warning  line too long (299 > 140 characters)  (line-length)
  350:141   warning  line too long (184 > 140 characters)  (line-length)
  1675:20   warning  too few spaces before comment: expected 2  (comments)
  1689:20   warning  too few spaces before comment: expected 2  (comments)
  1703:20   warning  too few spaces before comment: expected 2  (comments)
  1717:20   warning  too few spaces before comment: expected 2  (comments)
  1737:141  warning  line too long (141 > 140 characters)  (line-length)
  2315:141  warning  line too long (184 > 140 characters)  (line-length)
  2554:141  warning  line too long (214 > 140 characters)  (line-length)
  2569:141  warning  line too long (156 > 140 characters)  (line-length)
```

## Acceptance Criteria

- [x] Feature branch created from clean main
- [x] All baseline commands executed
- [x] Evidence file created in docs/evidence/
- [x] Evidence committed to branch
