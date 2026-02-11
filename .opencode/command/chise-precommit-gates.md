---
name: "chise-precommit-gates"
description: "ChiseAI: run local pre-commit gates (CI checks, status sync, iterloop compliance). Uses best-available commands in this repo."
disable-model-invocation: true
---

Run these gates before PR/merge. If a referenced script is missing, explicitly note it and run the closest available equivalent.

1. Repo sanity
   - `git status -sb`
   - `git branch --show-current`
   - If this is agent-run story work, verify session:
     - `python3 scripts/swarm/session.py verify --story-id=<story_id> --branch=<branch> --check-canonical`

2. Local CI checks (best available)
   - If `scripts/local-ci-checks.sh` exists, run it.
   - Otherwise, run the repo's test/lint entry points that exist (for example `pytest`, `ruff`, `black`) and report what you ran.

3. Status sync (if present)
   - If `scripts/validate_status_sync.py` exists, run: `python3 scripts/validate_status_sync.py`

4. Iterloop compliance (if present)
   - If `scripts/validate_iterloop_compliance.py` exists, run:
     - `python3 scripts/validate_iterloop_compliance.py --story-id=<story_id>`
