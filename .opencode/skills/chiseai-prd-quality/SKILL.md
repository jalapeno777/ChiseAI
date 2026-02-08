---
name: chiseai-prd-quality
description: Raise PRD quality to be measurable and traceable (explicit FR/NFR, success criteria, scope, traceability).
metadata:
  version: "1.0"
  opencode_min_version: "1.1.48"
---

# chiseai-prd-quality

## Goal

Convert narrative PRD content into a verifiable, traceable spec that can drive implementation safely.

## When To Use

- Creating or editing `docs/prd.md` or any PRD shard.
- When validation reports flag missing FR/NFR, missing success criteria, or weak traceability.

## Minimum PRD Bar (Do Not Skip)

- Success criteria section:
  - Specific, measurable, and tied to verification steps.
- Scope:
  - In-scope and out-of-scope lists.
- Functional requirements (FR):
  - Numbered FRs with unambiguous pass/fail acceptance tests.
- Non-functional requirements (NFR):
  - Numbered NFRs with metrics, method, and context.
- Traceability:
  - Map success criteria to journeys to FR/NFR.

## Preferred Workflow Command

Use `.opencode/command/bmad-bmm-validate-prd.md` after any non-trivial PRD change.

