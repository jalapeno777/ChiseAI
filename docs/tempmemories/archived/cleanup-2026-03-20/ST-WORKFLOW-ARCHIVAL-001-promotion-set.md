---
type: summary
story_id: ST-001
created: 2026-03-09T00:00:00
tags: [workflow-archival, memory-promotion, phase-3]
author: merlin
priority: medium
---

# ST-WORKFLOW-ARCHIVAL-001 - Memory Promotion Set

**Story ID**: ST-WORKFLOW-ARCHIVAL-001  
**Phase**: Implementation  
**Created**: 2026-03-09  
**Category**: workflow-archival  
**Project**: crypto-chise-bmad

## Memory Set for Qdrant Import

This document contains memories ready for Qdrant storage. Each memory is formatted with metadata for programmatic import.

---

### Memory 1: Pattern - Lean Status + Archive Separation

**Type**: pattern  
**Name**: Lean Status + Archive Separation

**Information**:
```
Workflow status archival uses a two-tier storage pattern:
- Lean status in workflow-status.yaml: id, status, title, priority, epic_id, completion_date, merge_commit, pr_number, archive_ref
- Full details in archive entries: description, acceptance_criteria, notes, test_results, etc.
- Benefits: Fast active reference lookup, complete historical audit trail, reduced main file size
- Reference: docs/archives/workflow-status/schema/archive-entry-schema.yaml
```

**Metadata**:
```json
{
  "project": "crypto-chise-bmad",
  "type": "pattern",
  "phase": "implementation",
  "story_id": "ST-WORKFLOW-ARCHIVAL-001",
  "category": "workflow-archival",
  "created_date": "2026-03-09",
  "name": "Lean Status + Archive Separation"
}
```

---

### Memory 2: Decision - Phase-Gated Migration Over Big-Bang

**Type**: decision  
**Name**: Phase-Gated Migration Over Big-Bang

**Information**:
```
Migration approach: Incremental phase-gated rollout instead of big-bang
- Phase 0: Foundation (schema, scripts, directory structure)
- Phase 1: Pilot (10 stories, verify integrity)
- Phase 2: Batch 1 (10 stories, test at scale)
- Phase 3: Assessment (verify no eligible stories missed)
- Phase 4: Automation (weekly scheduled archival)
- Rationale: Risk mitigation, early validation, iterative improvement
- Enables rollback at any phase if issues detected
```

**Metadata**:
```json
{
  "project": "crypto-chise-bmad",
  "type": "decision",
  "phase": "implementation",
  "story_id": "ST-WORKFLOW-ARCHIVAL-001",
  "category": "workflow-archival",
  "created_date": "2026-03-09",
  "name": "Phase-Gated Migration Over Big-Bang"
}
```

---

### Memory 3: Pattern - Completion Evidence as Archival Gate

**Type**: pattern  
**Name**: Completion Evidence as Archival Gate

**Information**:
```
Stories cannot be archived without completion evidence:
- Required fields: pr_number OR merge_commit OR remediation_pr_numbers OR merge_commits
- Validation: Pre-commit hook enforcement
- Prevents false completion claims (reference: GOV-BATCH-003-STATUS-FALSIFICATION incident)
- Enables audit trail verification
- Critical governance control for workflow integrity
```

**Metadata**:
```json
{
  "project": "crypto-chise-bmad",
  "type": "pattern",
  "phase": "implementation",
  "story_id": "ST-WORKFLOW-ARCHIVAL-001",
  "category": "workflow-archival",
  "created_date": "2026-03-09",
  "name": "Completion Evidence as Archival Gate"
}
```

---

### Memory 4: Decision - 30-Day Age Threshold for Archival

**Type**: decision  
**Name**: 30-Day Age Threshold for Archival

**Information**:
```
Archival eligibility threshold: Stories must be completed/merged >30 days
- Rationale: Active stories need quick reference, older stories are historical
- Trade-off: File size vs. accessibility
- Future consideration: May reduce to 21 days based on development velocity
- Balance between maintaining lean active workflow and preserving complete audit trail
- Enables scheduled automation without frequent manual review
```

**Metadata**:
```json
{
  "project": "crypto-chise-bmad",
  "type": "decision",
  "phase": "implementation",
  "story_id": "ST-WORKFLOW-ARCHIVAL-001",
  "category": "workflow-archival",
  "created_date": "2026-03-09",
  "name": "30-Day Age Threshold for Archival"
}
```

---

### Memory 5: Pattern - Data Integrity Verification

**Type**: pattern  
**Name**: Data Integrity Verification

**Information**:
```
Data integrity verification for archival migration:
- SHA-256 checksums for archive entries
- No-data-loss verification between original and archived
- Rollback capability testing at each phase
- Automated integrity checks in migration scripts
- Verification includes: field count, data types, required fields
- Critical for maintaining trust in archived workflow history
```

**Metadata**:
```json
{
  "project": "crypto-chise-bmad",
  "type": "pattern",
  "phase": "implementation",
  "story_id": "ST-WORKFLOW-ARCHIVAL-001",
  "category": "workflow-archival",
  "created_date": "2026-03-09",
  "name": "Data Integrity Verification"
}
```

---

## Import Script Template

```python
# Script to import these memories into Qdrant
# Location: scripts/import_workflow_archival_memories.py

import json
from qdrant_client import QdrantClient

def import_memories():
    client = QdrantClient(host="localhost", port=6333)
    
    memories = [
        {
            "information": "Workflow status archival uses a two-tier storage pattern...",
            "metadata": {
                "project": "crypto-chise-bmad",
                "type": "pattern",
                # ... full metadata
            }
        },
        # ... other memories
    ]
    
    for memory in memories:
        # Store in Qdrant
        # Implementation depends on Qdrant setup
        pass

if __name__ == "__main__":
    import_memories()
```

---

## Summary

**Total Memories**: 5  
- Patterns: 3 (Lean Status Separation, Completion Evidence Gate, Data Integrity)
- Decisions: 2 (Phase-Gated Migration, 30-Day Threshold)

**Storage Status**: Fallback document created (Qdrant validation errors encountered)  
**Fallback Location**: docs/tempmemories/ST-WORKFLOW-ARCHIVAL-001-promotion-set.md  
**Next Steps**: Resolve Qdrant metadata validation and import programmatically

---

## Related References

- Schema: `docs/archives/workflow-status/schema/archive-entry-schema.yaml`
- Incident: `GOV-BATCH-003-STATUS-FALSIFICATION`
- Story: `ST-WORKFLOW-ARCHIVAL-001`
- Workflow Status: `docs/bmm-workflow-status.yaml`
