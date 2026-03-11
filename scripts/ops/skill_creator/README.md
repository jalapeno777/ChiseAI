# Skill Creator Ops Bundle

This directory provides a tracked, repo-local copy of the skill creation and evaluation tooling used by ChiseAI commands:

- `chise-skill-create`
- `chise-skill-trigger-optimize`
- `chise-skill-benchmark`
- `chise-skill-benchmark-run`
- `chise-skill-lifecycle`

Run module-based commands from this directory:

```bash
cd scripts/ops/skill_creator
python3 -m scripts.run_loop --help
python3 -m scripts.run_eval --help
python3 -m scripts.aggregate_benchmark --help
python3 scripts/run_benchmark_suite.py --help
python3 scripts/skill_lifecycle_orchestrator.py --help
```

Reference schema:
- `references/schemas.md`

## Backend Selection

Both `run_eval.py` and `improve_description.py` support a `--backend` flag to choose the LLM backend:

- `--backend opencode` (default): Uses the Opencode CLI
- `--backend claude`: Uses the Claude API directly

### Opencode Backend

When using the default `opencode` backend, commands are executed via:

```bash
opencode run --agent Aria --prompt-file <file>
```

**Requirements:**
- Opencode CLI must be installed and authenticated
- The `Aria` agent must be available in your Opencode configuration

## Example Commands

### Default Usage (Opencode)

```bash
# Run evaluation with default opencode backend
python3 -m scripts.run_eval --eval-set eval.json --skill-path ./my-skill

# Improve skill description with default backend
python3 -m scripts.improve_description --skill-path ./my-skill
```

### Explicit Backend Selection

```bash
# Explicitly use opencode backend
python3 -m scripts.run_eval --backend opencode --eval-set eval.json --skill-path ./my-skill

# Use Claude as fallback
python3 -m scripts.run_eval --backend claude --eval-set eval.json --skill-path ./my-skill

# Improve description with Claude
python3 -m scripts.improve_description --backend claude --skill-path ./my-skill
```

## Migration Notes

### Default Backend Change

The default backend has changed from `claude` to `opencode`. If you previously ran commands without specifying a backend, they will now use Opencode instead of Claude.

### Continuing with Claude

To continue using the Claude backend, add `--backend claude` to your commands:

```bash
# Before (implicit Claude)
python3 -m scripts.run_eval --eval-set eval.json --skill-path ./my-skill

# After (explicit Claude)
python3 -m scripts.run_eval --backend claude --eval-set eval.json --skill-path ./my-skill
```

### Prerequisites

Ensure the Opencode CLI is installed and authenticated before using the default backend:

```bash
# Verify Opencode installation
opencode --version

# Authenticate if needed
opencode auth login
```
