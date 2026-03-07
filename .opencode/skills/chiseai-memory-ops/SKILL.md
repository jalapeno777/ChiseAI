---
name: chiseai-memory-ops
description: Redis and Qdrant memory operations for ChiseAI iteration loops and knowledge retention.
metadata:
  version: "1.1"
  opencode_min_version: "1.1.60"
  author: "ChiseAI Team"
  last_updated: "2026-02-23"
---

# chiseai-memory-ops

## Goal

Standardize short-term (Redis) and long-term (Qdrant) memory operations for agent swarm coordination.

## When To Use

- Starting/ending story iterations
- Recording decisions and learnings
- Querying prior context
- Managing parallel work ownership

## When Not To Use

- Persistent data storage (use PostgreSQL)
- File-based caching (use filesystem)
- External service state (use service-native storage)
- Large binary data (use object storage)

## Redis (Short-Term Ops State)

### Key Patterns
| Pattern | Purpose | TTL |
|---------|---------|-----|
| `bmad:chiseai:iterlog:story:<id>` | Story iteration log | 5 days |
| `bmad:chiseai:ownership` | Scope ownership | 5 days |
| `bmad:chiseai:current-story` | Active story tracking | Session |
| `bmad:chiseai:metacog:prediction:story:<id>` | Story-level prediction card | 5 days |
| `bmad:chiseai:metacog:outcome:story:<id>` | Story-level outcome card | 5 days |
| `bmad:chiseai:metacog:calibration:agent:<agent>:weekly:<week>` | Weekly calibration trend | 30 days |
| `bmad:chiseai:metacog:prevention_rules` | Durable anti-pattern prevention hints | 90 days |

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

## Exit Conditions

- Iteration started with Redis entry created.
- Decisions logged with rationale and timestamp.
- TTL refreshed on active stories.
- Long-term learnings stored in Qdrant (or fallback file).

## Troubleshooting/Safety

- **Redis unavailable**: Use file fallback in `docs/tempmemories/`; mark for manual import.
- **Qdrant timeout**: Retry with exponential backoff; fall back to file if persistent.
- **Key collision**: Use unique story IDs; verify key before writing.
- **TTL expired**: Re-create entry if story still active; document gap.

## Related Skills

- `chiseai-parallel-safety` - Uses Redis for ownership tracking
- `chiseai-worker-contracts` - Defines memory context requirements
- `chiseai-incident-response` - Logs incidents to Redis

## Templates

### Template 1: Iteration Start Log

```python
# Story iteration initialization
story_id = "ST-DSL-042"
story_title = "Add trailing stop syntax to DSL"

# Initialize iterlog hash
redis_state_hset(
    name=f"bmad:chiseai:iterlog:story:{story_id}",
    key="story_title",
    value=story_title
)
redis_state_hset(
    name=f"bmad:chiseai:iterlog:story:{story_id}",
    key="started_at",
    value=datetime.now().isoformat()
)
redis_state_hset(
    name=f"bmad:chiseai:iterlog:story:{story_id}",
    key="agent",
    value="senior-dev"
)
redis_state_hset(
    name=f"bmad:chiseai:iterlog:story:{story_id}",
    key="branch",
    value="feature/ST-DSL-042-grammar-extensions"
)

# Set TTL (5 days)
redis_state_expire(
    name=f"bmad:chiseai:iterlog:story:{story_id}",
    expire_seconds=432000
)

# Initialize sub-lists
redis_state_rpush(
    name=f"bmad:chiseai:iterlog:story:{story_id}:decisions",
    value=json.dumps({"event": "iteration_started", "timestamp": datetime.now().isoformat()})
)
```

### Template 2: Decision Log Entry

```python
# Log a significant decision
decision = {
    "decision": "Use ANTLR4 for DSL grammar parsing",
    "rationale": "ANTLR4 has better Python support than PLY, and our team has prior experience",
    "alternatives_considered": ["PLY", "Lark", "hand-written parser"],
    "impact": "Medium - affects DSL architecture",
    "reversible": False,
    "timestamp": datetime.now().isoformat(),
    "story_id": "ST-DSL-042",
    "agent": "senior-dev"
}

redis_state_rpush(
    name=f"bmad:chiseai:iterlog:story:{story_id}:decisions",
    value=json.dumps(decision)
)

# Refresh TTL
redis_state_expire(
    name=f"bmad:chiseai:iterlog:story:{story_id}",
    expire_seconds=432000
)
```

### Template 3: Qdrant Knowledge Storage

```python
# Store long-term knowledge in Qdrant
knowledge = """
---
project: ChiseAI
scope: dsl
type: pattern
epic_id: EP-DSL-001
story_id: ST-DSL-042
tags: [antlr, parsing, grammar, dsl]
timeframe: 1m
---

# Pattern: ANTLR4 Grammar Organization

## Problem
Complex DSL grammars can become unmaintainable if not properly organized.

## Solution
Organize grammar files by domain:
- grammar/Common.g4 - Shared tokens and rules
- grammar/Expressions.g4 - Mathematical expressions
- grammar/Orders.g4 - Order-related syntax
- grammar/Strategy.g4 - Strategy definition syntax

## Example
```antlr
// Common.g4
fragment DIGIT: [0-9];
fragment LETTER: [a-zA-Z];
NUMBER: DIGIT+ ('.' DIGIT+)?;
IDENTIFIER: LETTER (LETTER | DIGIT | '_')*;
WS: [ \t\r\n]+ -> skip;
```

## When to Apply
When DSL grammar exceeds 100 lines or has multiple distinct domains.

## Trade-offs
- More files to manage
- Clearer separation of concerns
- Easier to test individual components
"""

qdrant_qdrant-store(
    information=knowledge,
    metadata={
        "project": "ChiseAI",
        "scope": "dsl",
        "type": "pattern",
        "story_id": "ST-DSL-042",
        "tags": ["antlr", "parsing", "grammar", "dsl"]
    }
)
```

### Template 4: Iteration Close Summary

```python
# Generate iteration summary before closing
story_id = "ST-DSL-042"

# Get all decisions
decisions = redis_state_lrange(
    name=f"bmad:chiseai:iterlog:story:{story_id}:decisions",
    start=0,
    stop=-1
)

# Get incidents (if any)
incidents = redis_state_lrange(
    name=f"bmad:chiseai:iterlog:story:{story_id}:incidents",
    start=0,
    stop=-1
)

# Build summary
summary = {
    "story_id": story_id,
    "completed_at": datetime.now().isoformat(),
    "decisions_count": len(decisions),
    "incidents_count": len(incidents),
    "key_decisions": [json.loads(d) for d in decisions[-3:]],  # Last 3 decisions
    "lessons_learned": []
}

# Store summary
redis_state_hset(
    name=f"bmad:chiseai:iterlog:story:{story_id}",
    key="summary",
    value=json.dumps(summary)
)

# Mark as complete
redis_state_hset(
    name=f"bmad:chiseai:iterlog:story:{story_id}",
    key="status",
    value="complete"
)
```

## Examples

### Example 1: Full Iteration Memory Flow

**Context**: Starting story ST-DSL-042

```python
# 1. Initialize iteration
redis_state_hset(
    name="bmad:chiseai:iterlog:story:ST-DSL-042",
    key="story_title",
    value="Add trailing stop syntax to DSL"
)
redis_state_hset(
    name="bmad:chiseai:iterlog:story:ST-DSL-042",
    key="started_at",
    value="2026-02-23T10:00:00Z"
)

# 2. Query prior knowledge
prior_decisions = qdrant_qdrant-find(query="DSL grammar patterns ANTLR")
# Found: Decision to use ANTLR4 from ST-DSL-031

# 3. Log decisions during work
redis_state_rpush(
    name="bmad:chiseai:iterlog:story:ST-DSL-042:decisions",
    value=json.dumps({
        "decision": "Use trailing_stop keyword instead of trail_stop",
        "rationale": "Consistent with snake_case convention in DSL",
        "timestamp": "2026-02-23T11:30:00Z"
    })
)

# 4. Store new pattern in Qdrant
qdrant_qdrant-store(
    information="Trailing stop syntax: trailing_stop(percent, reference='high'|'close'|'low')",
    metadata={"type": "pattern", "scope": "dsl", "story_id": "ST-DSL-042"}
)

# 5. Close iteration with summary
redis_state_hset(
    name="bmad:chiseai:iterlog:story:ST-DSL-042",
    key="status",
    value="complete"
)
redis_state_hset(
    name="bmad:chiseai:iterlog:story:ST-DSL-042",
    key="completed_at",
    value="2026-02-23T16:00:00Z"
)
```

### Example 2: Ownership Management

**Context**: Claiming and releasing ownership

```python
# Claim ownership
redis_state_hset(
    name="bmad:chiseai:ownership",
    key="src:strategy:dsl",
    value="ST-DSL-042/senior-dev/2026-02-23T10:00:00Z",
    expire_seconds=432000  # 5 days
)

# Check ownership before another worker starts
current_owner = redis_state_hget(
    name="bmad:chiseai:ownership",
    key="src:strategy:dsl"
)
# Returns: "ST-DSL-042/senior-dev/2026-02-23T10:00:00Z"
# Another worker would see this and STOP

# Release ownership when complete
redis_state_hdel(
    name="bmad:chiseai:ownership",
    key="src:strategy:dsl"
)
```

### Example 3: Fallback When Redis Unavailable

**Context**: Redis connection failed, using file fallback

```python
# Try Redis first
try:
    redis_state_hset(
        name=f"bmad:chiseai:iterlog:story:{story_id}",
        key="decision",
        value=json.dumps(decision_data)
    )
except Exception as e:
    # Fallback to file
    fallback_path = f"docs/tempmemories/iterlog-{story_id}.md"
    
    # Read existing content or create new
    existing = ""
    if os.path.exists(fallback_path):
        with open(fallback_path, 'r') as f:
            existing = f.read()
    
    # Append decision
    new_entry = f"""
## Decision - {datetime.now().isoformat()}
```json
{json.dumps(decision_data, indent=2)}
```
needs_manual_import: true
"""
    
    with open(fallback_path, 'w') as f:
        f.write(existing + new_entry)
    
    # Log incident
    log_incident(
        severity="P2",
        symptom="Redis unavailable, using file fallback",
        resolution="Data stored in tempmemories, needs manual import"
    )
```

## Quick Reference

### Redis Key Patterns

| Pattern | Type | Purpose | TTL |
|---------|------|---------|-----|
| `bmad:chiseai:iterlog:story:<id>` | Hash | Story metadata | 5d |
| `bmad:chiseai:iterlog:story:<id>:decisions` | List | Decision log | 5d |
| `bmad:chiseai:iterlog:story:<id>:incidents` | List | Incident log | 5d |
| `bmad:chiseai:ownership` | Hash | Scope ownership | 5d |
| `bmad:chiseai:current-story` | String | Active story | Session |

### Qdrant Collection Config

```yaml
collection: ChiseAI
vectors:
  size: 384
  distance: Cosine
index:
  type: HNSW
  m: 16
  ef_construct: 100
```

### Common Operations

```python
# Set with TTL
redis_state_hset(name, key, value, expire_seconds=432000)

# Get value
value = redis_state_hget(name, key)

# Append to list
redis_state_rpush(name, value, expire=432000)

# Get list range
items = redis_state_lrange(name, 0, -1)

# Delete key
redis_state_hdel(name, key)

# Store in Qdrant
qdrant_qdrant-store(information, metadata)

# Search Qdrant
results = qdrant_qdrant-find(query)
```

## Related Commands

- `.opencode/command/chise-iterloop-start.md` - Start iteration with memory setup
- `.opencode/command/chise-iterloop-close.md` - Close iteration and promote learnings
- `.opencode/command/chise-claim-ownership.md` - Scope ownership management
