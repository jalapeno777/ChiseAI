---
name: python-quality
description: Repo-aware Python quality workflow. Uses whatever quality tooling is actually configured in this repo and available in the current environment.
metadata:
  version: "2.0"
  opencode_min_version: "1.1.48"
  author: "ChiseAI Team"
  last_updated: "2026-02-23"
---

# python-quality (repo-aware)

## Goal

Ship Python changes that pass the repo's configured checks without inventing nonexistent tooling.

## When To Use

- Any edit/addition to Python files.
- Any PR review touching Python or Python tooling config.

## Ground Rules (Reality First)

- Treat `pyproject.toml` as the primary config source when present.
- Do not assume `Makefile`, `pre-commit`, `ruff`, `pytest`, or `mypy` exist unless you can find them in-repo and can run them in the current environment.
- If `python` is not available in the current execution environment, explicitly report that and provide host-run commands.

## Default Verification

After Python edits, run the best available subset:

- `python -m compileall .`
- If Black is installed: `black --check .`
- If Ruff is installed: `ruff check .`
- If pytest is installed and tests exist: `pytest -q`

## Output Format When Invoked

Provide:

1. Plan
2. Patch summary (files)
3. Commands run (and results) or commands to run on host
4. Risks and gaps

