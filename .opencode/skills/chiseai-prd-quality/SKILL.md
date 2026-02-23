---
name: chiseai-prd-quality
description: Raise PRD quality to be measurable and traceable (explicit FR/NFR, success criteria, scope, traceability).
metadata:
  version: "1.1"
  opencode_min_version: "1.1.60"
  author: "ChiseAI Team"
  last_updated: "2026-02-23"
---

# chiseai-prd-quality

## Goal

Convert narrative PRD content into a verifiable, traceable spec that can drive implementation safely.

## When To Use

- Creating or editing `docs/prd.md` or any PRD shard.
- When validation reports flag missing FR/NFR, missing success criteria, or weak traceability.
- Before starting implementation planning.
- Reviewing existing PRDs for quality.

## When Not To Use

- Implementation documentation (use tech specs).
- API documentation (use OpenAPI/Swagger).
- User documentation (use user guides).
- Architecture decisions (use ADRs).

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

## Exit Conditions

- All FRs have acceptance tests.
- All NFRs have measurable metrics.
- Success criteria are specific and verifiable.
- Scope boundaries clearly defined.
- Traceability matrix complete.

## Troubleshooting/Safety

- **Vague requirements**: Rewrite with specific, measurable criteria.
- **Missing acceptance test**: Block FR until test defined.
- **Unmeasurable NFR**: Add concrete metric and measurement method.
- **Scope creep**: Document out-of-scope explicitly; reject additions.

## Related Skills

- `chiseai-validation` - Validates PRD quality gates
- `chiseai-workflow-commands` - PRD workflow commands

## Related Commands

- `.opencode/command/bmad-bmm-validate-prd.md` - Validate PRD after changes
