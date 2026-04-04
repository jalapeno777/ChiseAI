# Critic Risk Classification for PR Reviews

## Purpose

Scale critic review effort based on PR risk profile. Avoids full-repo evaluation for trivial/docs-only changes while retaining comprehensive review for risky code changes.

## Classification Basis

Classification is based **purely on file paths** in the PR diff. No content analysis. Deterministic and auditable.

## Risk Levels

### LOW Risk — Diff-Only Review

**Condition:** ALL changed files match ONLY the following patterns:

| Pattern        | Description                     |
| -------------- | ------------------------------- |
| `docs/**`      | Documentation directory         |
| `.opencode/**` | Opencode config/skills/commands |
| `**/*.md`      | Markdown files                  |
| `**/*.yaml`    | YAML configuration              |
| `**/*.yml`     | YAML configuration              |

**Additional constraint:** PR must touch fewer than 3 files total.

**Critic scope:** Changed files only (diff-only mode). No full repo scan, no import tracing.

**Rationale:** Documentation, configuration, and workflow files have minimal blast radius. A full critic cycle on these is wasteful.

---

### MEDIUM Risk — Changed Files + Direct Dependencies

**Condition:** PR touches 1–2 Python source files in `src/` that do NOT match any HIGH-risk path, AND no HIGH-risk files are present.

**Excluded from MEDIUM:** Any file matching HIGH-risk paths (see below) immediately promotes the PR to HIGH.

**Critic scope:** Changed files + their direct imports and dependents. Trace one level of imports from each changed file to identify affected surfaces.

**Rationale:** Small, isolated code changes in non-critical paths benefit from context-aware review but don't warrant full repo evaluation.

---

### HIGH Risk — Full Critic Review

**Condition:** PR matches ANY of the following:

| Trigger            | Description                    |
| ------------------ | ------------------------------ |
| 3+ changed files   | Broader surface area           |
| `src/execution/**` | Trade execution engine         |
| `src/trading/**`   | Trading logic and strategies   |
| `src/security/**`  | Security controls              |
| `src/ml/**`        | ML model code                  |
| `tests/**`         | Test directory                 |
| `**/test_*.py`     | Test files (pytest convention) |
| `**/conftest.py`   | Pytest fixtures/config         |

**Critic scope:** Full critic review — all layers (Blind Hunter, Edge Case Hunter, Acceptance Auditor) with complete repo context. This is the current default behavior.

**Rationale:** Changes to execution, trading, security, or test infrastructure can have cascading effects. Full review is warranted.

---

## Classification Algorithm

```
INPUT: list of changed file paths from PR diff

1. If any file matches a HIGH-risk trigger → return HIGH
2. If total file count >= 3 → return HIGH
3. If all files match LOW-risk patterns AND count < 3 → return LOW
4. If 1-2 Python source files in src/ (no HIGH triggers) → return MEDIUM
5. Fallback → return HIGH (safe default)
```

## Integration Notes

- This classifier is consumed by the PR review orchestrator (Merlin/Jarvis) before invoking critic review.
- The risk level determines which scope parameter is passed to the `bmad-code-review` skill.
- Classification is logged in the review evidence for auditability.
- When in doubt, classify as HIGH. It is always safe to over-review.
