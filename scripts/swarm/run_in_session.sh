#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash scripts/swarm/run_in_session.sh \
    --story-id <story_id> \
    --branch <branch> \
    --worktree-path <abs-path> \
    -- <command> [args...]
EOF
}

story_id=""
branch=""
worktree_path=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --story-id)
      story_id="${2:-}"
      shift 2
      ;;
    --branch)
      branch="${2:-}"
      shift 2
      ;;
    --worktree-path)
      worktree_path="${2:-}"
      shift 2
      ;;
    --)
      shift
      break
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ -z "${story_id}" || -z "${branch}" || -z "${worktree_path}" ]]; then
  echo "ERROR: missing required arguments." >&2
  usage
  exit 2
fi

if [[ $# -eq 0 ]]; then
  echo "ERROR: missing command after --" >&2
  usage
  exit 2
fi

python3 scripts/swarm/assert_session_context.py \
  --story-id "${story_id}" \
  --branch "${branch}" \
  --worktree-path "${worktree_path}" \
  --cwd "${worktree_path}"

(
  cd "${worktree_path}"
  exec "$@"
)
