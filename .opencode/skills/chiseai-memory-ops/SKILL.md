---
name: chiseai-memory-ops
description: Redis and Qdrant memory operations for ChiseAI iteration loops and knowledge retention.
metadata:
  version: "1.0"
  opencode_min_version: "1.1.60"
---

# chiseai-memory-ops

## Goal

Standardize short-term (Redis) and long-term (Qdrant) memory operations for agent swarm coordination.

## When To Use

- Starting/ending story iterations
- Recording decisions and learnings
- Querying prior context
- Managing parallel work ownership

## Redis (Short-Term Ops State)

### Key Patterns
| Pattern | Purpose | TTL |
|---------|---------|-----|
| `bmad:chiseai:iterlog:story:<id>` | Story iteration log | 5 days |
| `bmad:chiseai:ownership` | Scope ownership | 5 days |
| `bmad:chiseai:current-story` | Active story tracking | Session |

### Standard Operations

#### Start Iteration
```python
redis_state_hset(
    name=f"bmad:chiseai:iterlog:story:{story_id}",
    key="story_title", 
    value=story_title
)
redis_state_expire(
    name=f"bmad:chiseai:iterlog:story:{story_id}",
    expire_seconds=432000  # 5 days
)
```

#### Log Decision
```python
redis_state_rpush(
    name=f"bmad:chiseai:iterlog:story:{story_id}:decisions",
    value=json.dumps({
        "decision": decision_text,
        "rationale": rationale,
        "timestamp": datetime.now().isoformat()
    })
)
```

#### Refresh TTL on Activity
When logging any activity, refresh the story's TTL:
```python
redis_state_expire(
    name=f"bmad:chiseai:iterlog:story:{story_id}",
    expire_seconds=432000
)
```

## Qdrant (Long-Term Semantic Memory)

### Vector Configuration
- **Collection**: `ChiseAI`
- **Dimensions**: 384 (fast-all-minilm-l6-v2)
- **Metric**: COSINE distance
- **Index**: HNSW

### Storage Format
```text
---
project: ChiseAI
scope: architecture
type: decision|pattern|anti-pattern|summary
epic_id: EP-XXX
story_id: ST-XXX
tags: [tag1, tag2]
timeframe: 1d|1w|1m
---

Content here...
```

### Fallback Strategy
When Redis/Qdrant unavailable, write to `docs/tempmemories/` with identical frontmatter. Mark with `needs_manual_import: true`.

## Related Commands
- `.opencode/command/chise-iterloop-start.md` - Start iteration with memory setup
- `.opencode/command/chise-iterloop-close.md` - Close iteration and promote learnings
- `.opencode/command/chise-claim-ownership.md` - Scope ownership management
