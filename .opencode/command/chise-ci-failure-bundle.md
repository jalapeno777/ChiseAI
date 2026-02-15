---
name: "chise-ci-failure-bundle"
description: "ChiseAI: generate complete Woodpecker CI failure bundle for handoff/escalation."
disable-model-invocation: true
---

Use this command when handing off CI failures to another agent or escalating to `merlin`.

Run DB-backed root-cause first (required when `WOODPECKER_DB_DSN` is available):

```bash
python3 scripts/ci/woodpecker_triage.py diagnose --pipeline "${PIPELINE_NUMBER}" --write-artifacts --db-dsn "${WOODPECKER_DB_DSN}" --format human
```

Preferred (pipeline known):

```bash
python3 scripts/ci/woodpecker_triage.py bundle --pipeline "${PIPELINE_NUMBER}" --format human
```

PR-targeted bundle:

```bash
python3 scripts/ci/woodpecker_triage.py bundle --pr "${PR_NUMBER}" --format human
```

Local fallback bundle:

```bash
python3 scripts/ci/woodpecker_triage.py bundle --from-local-dir _bmad-output/ci --format human
```

Bundle location:
- `_bmad-output/ci/woodpecker/<pipeline_number>/`
