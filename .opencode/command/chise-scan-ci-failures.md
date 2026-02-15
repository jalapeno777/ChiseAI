# chise-scan-ci-failures

Purpose: compatibility command for CI failure scanning.

Default path (required for swarm triage, DB-first when available):

```bash
python3 scripts/ci/woodpecker_triage.py diagnose --pr "${PR_NUMBER}" --write-artifacts --db-dsn "${WOODPECKER_DB_DSN}" --format human
```

API-only path (when DB DSN is unavailable):

```bash
python3 scripts/ci/woodpecker_triage.py diagnose --pr "${PR_NUMBER}" --write-artifacts --format human
```

If PR number is unknown but pipeline is known:

```bash
python3 scripts/ci/woodpecker_triage.py diagnose --pipeline "${PIPELINE_NUMBER}" --write-artifacts --format human
```

Fallback when Woodpecker API/token is unavailable:

Commands:

```bash
python3 scripts/ci/woodpecker_triage.py diagnose --from-local-dir _bmad-output/ci --write-artifacts --format human
python3 scripts/ci/scan_failure_logs.py
```

If you need raw tails from local replay artifacts:

```bash
ls -la _bmad-output/ci
sed -n '1,200p' _bmad-output/ci/lint.log
sed -n '1,200p' _bmad-output/ci/security-scan.log
sed -n '1,200p' _bmad-output/ci/local-ci-full.log
```
