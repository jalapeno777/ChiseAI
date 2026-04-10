# Memory Systems Evaluation: MemPalace v3.0.14 & Mastra Observational Memory

> **Story**: REPO-001 (Memory Systems Research)
> **Date**: 2026-04-09
> **Status**: Decision Complete — Hybrid Architecture Selected

---

## 1. Executive Summary

### What We Evaluated

| System                          | Version | Architecture                         | Claimed Performance                             |
| ------------------------------- | ------- | ------------------------------------ | ----------------------------------------------- |
| **MemPalace**                   | v3.0.14 | ChromaDB + SQLite KG, vector-RAG     | 96.6% LongMemEval (raw mode), 84.2% AAAK        |
| **Mastra Observational Memory** | current | Text-log compression, NOT vector-RAG | 94.87% LongMemEval (GPT-5-mini, self-published) |

### Decision

**Cherry-pick best concepts, implement hybrid architecture.**

Do NOT adopt full MemPalace or Mastra. Instead:

- From **MemPalace**: L0-L3 tiered recall, domain scoping concept, temporal validity windows
- From **Mastra**: Observer/Reflector two-agent pattern (Python reimplementation)
- From **neither**: Skip ChromaDB, SQLite KG, AAAK, MCP tools, Mastra framework, palace metaphor

### Implementation Roadmap

| Phase     | Description                                                | SP Estimate |
| --------- | ---------------------------------------------------------- | ----------- |
| Phase 1   | Observer Agent — compress raw iterlog→observation          | 3 SP        |
| Phase 2   | Reflector Agent — consolidate observations→promoted memory | 2 SP        |
| Phase 3   | Tiered Recall L0-L3 — read path efficient context assembly | 3 SP        |
| Phase 4   | Context Assembly Pipeline — session-start context builder  | 2 SP        |
| Phase 5   | Integration + Metrics — observability, rollback path       | 2 SP        |
| **Total** |                                                            | **12 SP**   |

---

## 2. MemPalace v3.0.14 Analysis

### Architecture

- **Storage**: ChromaDB (vector store) + SQLite (knowledge graph)
- **Palace metaphor**: Wings→Rooms→Closets→Drawers (hierarchical memory organization)
- **Retrieval**: Standard cosine similarity over embeddings; "tunnels" are computed at query time
- **Tool set**: 19 MCP tools for CRUD operations on palace elements
- **Dialect**: AAAK (alternative to natural language for precision)

### Performance Claims

| Benchmark       | Score        | Mode                            |
| --------------- | ------------ | ------------------------------- |
| LongMemEval     | **96.6%**    | Raw mode (no AAAK)              |
| AAAK Dialect    | **84.2%**    | With AAAK (regression from raw) |
| AAAK vs Raw Gap | -12.4 points | AAAK underperforms raw          |

### Independent Audit Findings

**Architecture is flat metadata, NOT a real hierarchy:**

```
Wing     →  string metadata field (e.g., "chiseai")
Room     →  string metadata field (e.g., "memory-research")
Closet   →  string metadata field (display-only, not stored)
Drawer   →  string metadata field (display-only, not stored)
Tunnels  →  computed at query time (standard cosine similarity)
```

Closets and Drawers exist only in the display/UI layer. The actual stored data has NO hierarchical containment. Tunnels are NOT stored edges — they are ad-hoc similarity computations at query time.

**ChromaDB issues (known, unresolved):**

- Issue #100: ChromaDB instability in production environments
- Issue #110: Shell injection vulnerability in MCP tools
- No Redis or Qdrant backend support

**What to ADOPT from MemPalace:**

1. **L0-L3 tiered recall** — hot/warm/cold/archival tiering for efficient retrieval
2. **Domain scoping concept** — memories scoped to domains (wing/room/hall metaphor)
3. **Temporal validity windows** — memories expire or promote based on time

**What to SKIP from MemPalace:**

- ChromaDB (use Qdrant instead — already integrated)
- SQLite KG (no evidence it adds value over flat metadata)
- AAAK dialect (84.2% < 96.6% raw — regression)
- Full 19 MCP tools (shell injection #110, excessive complexity)
- Shell hooks (#110 injection vulnerability)
- Palace metaphor (only 3 flat string fields under the branding)

---

## 3. Mastra Observational Memory Analysis

### Architecture

Mastra Observational Memory is a **text-log compression system**. It is NOT vector-RAG.

```
Write Path:
  Raw conversation logs
    → Observer Agent (30K token threshold, temp=0.3)
    → Extracted facts + emoji priority tags
    → Text-log storage (NOT vector)

Read Path:
  → Reflector Agent (40K threshold, temp=0)
  → Consolidated memory representations
  → Supersedes prior state (three-date model: created/updated/superseded)
```

**Two LLM Agents:**

- **Observer**: Runs at 30K token input threshold. Extracts factual statements, assigns emoji priority. Async buffering. Temp=0.3 for slight randomness.
- **Reflector**: Runs at 40K threshold. Consolidates observations into coherent memory. Supersedes prior state. Temp=0 (deterministic).

**Compression**: 5-40x ratio observed.

**Three-Date Model:**

```
created_at    → when observation first recorded
updated_at   → when observation last modified
superseded_at → when observation was replaced by newer version
```

### Performance

| Benchmark         | Score      | Notes                              |
| ----------------- | ---------- | ---------------------------------- |
| LongMemEval       | **94.87%** | GPT-5-mini (Mastra self-published) |
| Compression ratio | 5-40x      | Varies by log complexity           |

**Important caveat**: 94.87% is self-published by Mastra team. No independent replication confirmed. Treat as promising but unverified.

### Integration Barriers (why Mastra itself is not adoptable)

| Barrier                  | Severity | Notes                                              |
| ------------------------ | -------- | -------------------------------------------------- |
| TypeScript-only          | Critical | ChiseAI is Python                                  |
| Mastra framework lock-in | Critical | 3400+ lines of Mastra-specific code                |
| Storage backends         | High     | PostgreSQL, LibSQL, MongoDB only — no Redis/Qdrant |
| MCP tools                | High     | Different architecture than ChiseAI governance     |
| No independent eval      | Medium   | Self-published benchmark                           |

### What to ADOPT from Mastra

1. **Observer/Reflector pattern** — two-stage LLM compression (Python reimplementation)
2. **Token-threshold triggering** — process when input exceeds ~30K tokens
3. **Emoji priority system** — actionability/importance tagging for observations
4. **Async buffering** — collect observations before processing
5. **Three-date model** — created_at / updated_at / superseded_at temporal tracking
6. **State supersession** — newer observations replace older ones
7. **Prompt-cacheable design** — structured prompts that enable cache reuse

### What to SKIP from Mastra

- Mastra framework (TypeScript, framework lock-in)
- PostgreSQL/LibSQL/MongoDB backends (ChiseAI uses Redis/Qdrant)
- TypeScript MCP tool architecture

---

## 4. Palace Hierarchy Deep Analysis

### What It Actually Is vs. The Marketing

| Marketing Claim           | Reality                                    |
| ------------------------- | ------------------------------------------ |
| "Hierarchical memory"     | 3 flat string metadata fields in ChromaDB  |
| "Closets and Drawers"     | Display-only, NOT stored                   |
| "Tunnels connect palaces" | Computed cosine similarity at query time   |
| "Deep containment"        | No actual parent/child relationship stored |

The palace hierarchy is a **presentation metaphor**, not a data structure. Under the branding, you have:

```python
# What "palace hierarchy" actually is:
{
    "wing": "chiseai",        # string field
    "room": "memory-research", # string field
    "hall": "facts",           # string field
    # That's it. No closets, no drawers, no containment.
}
```

### Independent Audit: Flat Metadata Confirmed

- ChromaDB has no native hierarchical containment model
- Closets/Drawers exist only in the MemPalace UI, not in storage
- Tunnels are ad-hoc similarity queries, not stored graph edges
- The "hierarchy" is a rendering choice, not a storage decision

### Why It's NOT Incompatible with ChiseAI

The palace hierarchy (wing/room/hall) is **orthogonal** to ChiseAI's MemoryType 7-type taxonomy:

```
Palace wing/room/hall  =  Domain scoping (WHERE the memory lives)
ChiseAI MemoryType    =  Semantic type (WHAT the memory IS)
```

These can coexist. The palace concept can be adopted as a **DomainContext** overlay on ChiseAI's existing MemoryType enum without any conflict.

### ChiseAI Alternative: DomainContext

Instead of importing the palace metaphor, implement a clean DomainContext dataclass:

```python
from dataclasses import dataclass, field
from typing import List

@dataclass
class DomainContext:
    wing: str  # "chiseai" | "craig" | "trading" | "infra"
    room: str  # "risk-mgmt" | "strategy-dev" | "preferences" | "iterations"
    hall: str  # "facts" | "events" | "discoveries" | "preferences" | "advice"
    tunnels: List[str] = field(default_factory=list)  # related domains for cross-domain links
```

Store in Qdrant as nested payload:

```json
{
  "domain": {
    "wing": "chiseai",
    "room": "memory-research",
    "hall": "facts",
    "tunnels": ["chiseai:strategy-dev", "craig:preferences"]
  }
}
```

Qdrant supports dot-notation nested payload queries. Tunnels are string references (not computed similarity), enabling explicit cross-domain links that are auditably stored.

---

## 5. Hybrid Architecture Proposal

### Design Principles

1. **Zero new deps** — use existing Qdrant + Redis only
2. **Feature-flagged** — all new components opt-in
3. **Observable** — every phase has measurable success criteria
4. **Reversible** — rollback path at every phase

### Component Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  WRITE PATH                                                 │
│                                                             │
│  Raw iterlog messages                                       │
│       ↓                                                     │
│  Observer Agent (Phase 1)                                   │
│  - LLM extracts factual observations                       │
│  - Assigns emoji priority (🔥/✅/💡/❄️)                        │
│  - Writes to Redis observation stream                       │
│       ↓                                                     │
│  Reflector Agent (Phase 2)                                  │
│  - Runs at 40K threshold or on-demand                       │
│  - Consolidates + supersedes prior observations             │
│  - Promotes to Qdrant promoted memory                      │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  READ PATH                                                  │
│                                                             │
│  Session start → Context Assembly (Phase 4)                  │
│       ↓                                                     │
│  L0: Immediate context (last iteration, hot)                │
│       ↓ or fallback                                         │
│  L1: Recent context (last 7 days, warm)                     │
│       ↓ or fallback                                         │
│  L2: Historical context (last 30 days, cold)                │
│       ↓ or fallback                                         │
│  L3: Archived context (30+ days, via Qdrant full-text)      │
└─────────────────────────────────────────────────────────────┘
```

### Redis Key Schema for Observations

```
bmad:chiseai:memory:observations:{story_id}
  └── List of observation JSON objects (FIFO, no dedup yet)

bmad:chiseai:memory:observation_buffer:{story_id}
  └── Buffered observations pending Reflector processing

bmad:chiseai:memory:superseded:{story_id}
  └── Set of superseded observation IDs
```

### Qdrant Payload Schema with DomainContext

```json
{
  "id": "<uuid>",
  "vector": <embedding>,
  "payload": {
    "story_id": "ST-XXX",
    "memory_type": "fact|event|discovery|preference|advice|plan|context",
    "domain": {
      "wing": "chiseai",
      "room": "memory-research",
      "hall": "facts",
      "tunnels": []
    },
    "content": "...",
    "created_at": "2026-04-09T00:00:00Z",
    "updated_at": "2026-04-09T00:00:00Z",
    "superseded_at": null,
    "observer_priority": "🔥",
    "source_iterlog_range": {"start": 1, "end": 47}
  }
}
```

### Implementation Roadmap

| Phase     | Name                  | SP        | Key Deliverables                                                                            |
| --------- | --------------------- | --------- | ------------------------------------------------------------------------------------------- |
| 1         | Observer Agent        | 3 SP      | `src/governance/memory/observer_agent.py`, Redis observation stream, emoji priority tagging |
| 2         | Reflector Agent       | 2 SP      | `src/governance/memory/reflector_agent.py`, consolidation logic, state supersession         |
| 3         | Tiered Recall L0-L3   | 3 SP      | Read path tiering, temporal validity windows, Qdrant nested payload queries                 |
| 4         | Context Assembly      | 2 SP      | Session-start context builder, DomainContext injection, feature flag wiring                 |
| 5         | Integration + Metrics | 2 SP      | Full pipeline integration, Grafana panels, rollback procedures                              |
| **Total** |                       | **12 SP** |                                                                                             |

---

## 6. Risk Register

| #   | Risk                                                                                       | Severity | Probability | Mitigation                                                                    |
| --- | ------------------------------------------------------------------------------------------ | -------- | ----------- | ----------------------------------------------------------------------------- |
| R1  | Observer compression quality — LLM extracts incorrect or incomplete facts                  | HIGH     | MEDIUM      | Human-scored sample in Phase 1 PoC; <5% false positive gate                   |
| R2  | Benchmark overfitting — LongMemEval not representative of ChiseAI workloads                | MEDIUM   | MEDIUM      | A/B test against real iterlog data before Phase 2                             |
| R3  | Domain taxonomy drift — wing/room/hall taxonomy becomes inconsistent over time             | MEDIUM   | LOW         | Taxonomy governance rules; annual review cadence                              |
| R4  | Observer threshold miscalibration — 30K token threshold too aggressive or too conservative | MEDIUM   | MEDIUM      | Measure actual compression ratios in Phase 1; tune threshold                  |
| R5  | Reflector consolidation loops — observations oscillate rather than converge                | LOW      | LOW         | Temp=0 on Reflector; human review of first 10 consolidations                  |
| R6  | Qdrant payload schema changes — DomainContext migration breaks existing memories           | MEDIUM   | LOW         | Feature-flag new field; backward-compatible payload reader                    |
| R7  | Redis observation stream growth — unbounded list causes memory pressure                    | LOW      | MEDIUM      | TTL + size cap; auto-flush to Qdrant at 1000 items                            |
| R8  | ChromaDB instability — if any MemPalace concepts carried over incorrectly                  | LOW      | LOW         | Not adopting ChromaDB; zero new deps policy prevents this                     |
| R9  | Mastra self-publishing bias — 94.87% LongMemEval not independently verified                | MEDIUM   | HIGH        | Run independent eval in Phase 1 PoC before Phase 2 approval                   |
| R10 | Feature flag complexity — too many flags makes system hard to reason about                 | LOW      | MEDIUM      | Consolidate to single `MEMORY_HYBRID_ENABLED` flag; remove flag after Phase 5 |

### Top 3 Risks Summary

| Risk                   | Why Critical                                       | Watch Signal                                |
| ---------------------- | -------------------------------------------------- | ------------------------------------------- |
| R1: Observer quality   | Wrong facts propagated to all downstream decisions | False positive rate >5% in PoC sample       |
| R9: Benchmark validity | May be building for wrong target                   | Independent eval differs by >15 points      |
| R3: Taxonomy drift     | Core structural assumption; costly to fix late     | >20% of new memories lack consistent domain |

---

## 7. Redis Research Keys Reference

All research artifacts stored in Redis for audit trail:

| Key                                                        | TTL     | Content                              |
| ---------------------------------------------------------- | ------- | ------------------------------------ |
| `bmad:chiseai:research:mempalace-eval-20260408`            | 90 days | MemPalace v3.0.14 full evaluation    |
| `bmad:chiseai:research:mastra-om-eval-20260409`            | 90 days | Mastra Observational Memory analysis |
| `bmad:chiseai:research:palace-hierarchy-analysis-20260409` | 90 days | Palace hierarchy deep audit          |
| `bmad:chiseai:research:hybrid-memory-arch-20260409`        | 90 days | Hybrid architecture proposal         |

All keys: 90-day TTL from 2026-04-09 (expires 2026-07-08).

---

_Document created by Jarvis (BMAD Orchestrator) — 2026-04-09_
_Permanent reference document — do not discard_
