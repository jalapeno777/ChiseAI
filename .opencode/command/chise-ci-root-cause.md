---
name: "chise-ci-root-cause"
description: "ChiseAI: root-cause-first Woodpecker CI diagnosis (exact rule/file/test failures)."
disable-model-invocation: true
---

Use this command as the default CI failure diagnosis path for swarm agents.

Prereqs:
- Preferred: `WOODPECKER_TOKEN` + repo owner/repo env vars
- Preferred for hard failures: `WOODPECKER_DB_DSN` (DB-backed log extraction first)
- Optional fallback: local CI artifacts under `_bmad-output/ci`

PR-based diagnosis (DB-first preferred):

```bash
python3 scripts/ci/woodpecker_triage.py diagnose --pr "${PR_NUMBER}" --write-artifacts --db-dsn "${WOODPECKER_DB_DSN}" --format human
```

API-only diagnosis (when DB DSN is unavailable):

```bash
python3 scripts/ci/woodpecker_triage.py diagnose --pr "${PR_NUMBER}" --write-artifacts --format human
```

Specific pipeline diagnosis:

```bash
python3 scripts/ci/woodpecker_triage.py diagnose --pipeline "${PIPELINE_NUMBER}" --write-artifacts --format human
```

Fallback when API/token unavailable:

```bash
python3 scripts/ci/woodpecker_triage.py diagnose --from-local-dir _bmad-output/ci --write-artifacts --format human
```

Notes:
- Writes bundle to `_bmad-output/ci/woodpecker/<pipeline_number>/`
- Includes `root-cause.json`, `root-cause.md`, raw logs, and `repro.sh`
