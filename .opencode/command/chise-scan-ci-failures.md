# chise-scan-ci-failures

Purpose: quickly summarize CI failures from repo-checkable artifacts, suitable for PR comments.

Commands:

```bash
python3 scripts/ci/scan_failure_logs.py
```

If you need raw tails:

```bash
ls -la _bmad-output/ci
sed -n '1,200p' _bmad-output/ci/lint.log
sed -n '1,200p' _bmad-output/ci/security-scan.log
sed -n '1,200p' _bmad-output/ci/local-ci.log
```

