---
project: ChiseAI
scope: context
type: qdrant-query-fallback
story_id: CH-AGENTS-003
phase: testing
started_at: "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
needs_manual_qdrant_import: true
---

## Intended Qdrant Query

- Query: "parallel delegation scope ownership incidents GitReviewBot gitea pr review woodpecker lint"
- Goal: retrieve prior decisions/patterns about parallel-safety and autonomous review gates.

## Why Fallback

- No repo-integrated `qdrant_qdrant-find` client/tooling is available from this environment.
- Qdrant may be reachable over HTTP, but semantic search requires embedding/vector generation which is not wired into this workflow command.

## Next Manual Action

- Run the equivalent semantic find in the Qdrant MCP (collection `ChiseAI`) and paste key hits back into the iterlog or promote to Qdrant as a `summary`/`decision`.
