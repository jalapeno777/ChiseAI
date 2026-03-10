---
name: "chise-opencode-session-hygiene"
description: "Safe session hygiene for local caches/transient artifacts without touching required project records."
disable-model-invocation: true
---

# Safe Session Hygiene

## Never prune
- `docs/tempmemories/**`
- `docs/postmortems/**`
- `reports/**` (unless explicitly approved)
- `checkpoints/**`

## Safe prune targets
These are rebuildable/transient:
- `.pytest_cache/**`
- `.mypy_cache/**`
- `.ruff_cache/**`
- `htmlcov/**`
- `coverage.xml`
- temporary swap files (`*.swp`, `*.tmp`) in repo root

## Commands
```bash
rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov
rm -f coverage.xml
find . -maxdepth 2 -type f \( -name "*.swp" -o -name "*.tmp" \) -delete
```

## Optional (older opencode temp artifacts)
Run only if path exists and only for old files:
```bash
find .opencode -type f -name "*.tmp" -mtime +7 -delete
```

## Verify
```bash
git status -sb
```
