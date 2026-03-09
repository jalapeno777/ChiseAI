# Workflow Status Information Architecture Design

## Executive Summary

The current `docs/bmm-workflow-status.yaml` has grown to **6,549 lines** with significant information architecture problems. This design proposes a **3-tier architecture** that separates:

1. **Lean workflow status** (high-signal, frequently accessed)
2. **Archive documents** (detailed evidence, historical records)
3. **Qdrant semantic memory** (searchable learnings and patterns)

---

## 1. LEAN WORKFLOW STATUS SCHEMA

### What Stays in Main File (High-Signal Fields)

```yaml
workflow_status_schema:
  # REQUIRED - Core Identity
  required_fields:
    - id                    # Story ID (e.g., ST-001, EP-001)
    - status                # planned | in_progress | completed | merged | deprecated
    - title                 # Short descriptive title
    - epic_id               # Parent epic reference
    - priority              # P0-CRITICAL | P1-HIGH | P2-MEDIUM | P3-LOW
    - owner                 # Agent/role responsible
  
  # REQUIRED - Completion Evidence (Guardrails)
  completion_evidence:
    - pr_number             # GitHub/Gitea PR number
    - merge_commit          # SHA of merge commit on main
    - merge_commits         # List for multi-PR stories
    - remediation_pr_numbers # For remediation stories
  
  # OPTIONAL - Planning Metadata
  planning_fields:
    - created_date          # ISO 8601 date
    - completed_date        # ISO 8601 date  
    - merged_date           # ISO 8601 date
    - story_points          # Numeric estimation
    - sprint_id             # Sprint identifier
    - depends_on            # List of story dependencies
  
  # OPTIONAL - Quick Reference
  quick_reference:
    - description           # Brief 1-2 sentence summary
    - validation_status     # planned | validated | partial | failed
    - current_completion    # Percentage for in-progress

# Estimated Size Reduction: 6,549 lines → ~800-1,000 lines (85% reduction)
```

### Rationale for Field Retention

| Field Category | Rationale |
|---------------|-----------|
| **Core Identity** | Required for all automation, reporting, and navigation |
| **Completion Evidence** | Critical guardrails per GOV-BATCH-003-STATUS-FALSIFICATION incident |
| **Planning Metadata** | Needed for sprint planning and velocity tracking |
| **Quick Reference** | Enables agents to understand context without deep diving |

---

## 2. ARCHIVE DOCUMENT SCHEMA

### Archive Structure

```yaml
archive_schema:
  # Location Strategy
  location: docs/archives/story-details/
  
  # Filename Pattern
  filename_pattern: "{story_id}-{slug}-details.yaml"
  example: "ST-GOV-001-memory-deduplication-details.yaml"
  
  # Archive Index (for traceability)
  index_location: docs/archives/story-details/archive-index.yaml
  index_entry:
    story_id: ST-GOV-001
    archived_at: "2026-03-08T12:00:00Z"
    archive_path: docs/archives/story-details/ST-GOV-001-memory-deduplication-details.yaml
    workflow_status_ref: docs/bmm-workflow-status.yaml#line-2150
    retention_until: "2027-03-08T12:00:00Z"  # 1 year default
  
  # Document Structure
  document_schema:
    story_id: ST-GOV-001
    title: "Memory Deduplication Engine"
    archived_at: "2026-03-08T12:00:00Z"
    original_location: "docs/bmm-workflow-status.yaml"
    
    sections:
      acceptance_criteria:
        - "Detects semantic duplicates with ≥95% accuracy using Qdrant similarity"
        - "Deduplication runs automatically before memory writes"
        - "Configurable similarity threshold (default: 0.92 cosine similarity)"
        # ... full list
      
      implementation_notes:
        created_files:
          - path: src/governance/deduplication/engine.py
            lines: 486
          - path: tests/test_governance/test_deduplication.py
            lines: 844
        key_decisions:
          - decision: "Used cosine similarity over Euclidean distance"
            rationale: "Better for high-dimensional text embeddings"
            date: "2026-03-05"
      
      evidence_files:
        - path: docs/evidence/ST-GOV-001-test-results.json
          type: test_results
          description: "Comprehensive test suite results"
        - path: docs/tempmemories/ST-GOV-001-implementation-notes.md
          type: implementation_notes
      
      test_results:
        unit_tests:
          total: 49
          passed: 49
          failed: 0
          coverage_percent: 88
        integration_tests:
          status: missing
          note: "test_similarity_accuracy.py does not exist despite being in test_strategy"
      
      validation_gates:
        - gate: coverage
          target: ">=85%"
          actual: "88%"
          status: passed
        - gate: false_positive_rate
          target: "<5%"
          actual: null
          status: pending
      
      detailed_notes:
        - "CI evidence: Woodpecker CI passed for merge commit 0ce77cf"
        - "Test suite: 844 lines in tests/test_governance/test_deduplication.py"
      
      validation_summary:
        overall: partial
        blockers:
          - "integration test: MISSING"
          - "false_positive_rate: PENDING - no evidence found"
      
      remediation_history:
        - date: "2026-03-08"
          action: "CONSOLIDATION REMEDIATION"
          description: "Verified merged to main via cross-branch verification"
          evidence: "docs/evidence/GOVERNANCE_MERGE_EVIDENCE_2026-03-08.md"
```

### Archive Organization

```
docs/archives/
├── story-details/              # Individual story archives
│   ├── ST-GOV-001-*.yaml
│   ├── ST-GOV-002-*.yaml
│   └── archive-index.yaml      # Master index
├── epic-summaries/             # Epic-level aggregations
│   └── EP-GOV-001-summary.yaml
├── sprint-reports/             # Sprint retrospectives
│   └── GOV-PHASE1-001-report.yaml
└── incidents/                  # Post-mortem archives
    └── GOV-BATCH-003-postmortem.yaml
```

### Retention Policy

```yaml
retention_policy:
  story_details: 1_year
  epic_summaries: 2_years
  sprint_reports: 1_year
  incidents: 7_years  # Compliance requirement
  
  auto_archive_trigger:
    - status in [completed, merged, deprecated]
    - last_updated > 30_days_ago
    - not in active_sprint
```

---

## 3. QDRANT METADATA SCHEMA

### Collection Design

```yaml
qdrant_metadata:
  collection: ChiseAI
  
  # Point Structure
  point_schema:
    id: "uuid-or-story-derived"
    vector: "1536-dim embedding of content"
    
    payload:
      # REQUIRED - Identity
      story_id: "ST-GOV-001"
      epic_id: "EP-GOV-001"
      type: "decision" | "pattern" | "summary" | "anti-pattern" | "lesson"
      
      # REQUIRED - Context
      phase: "implementation" | "validation" | "remediation" | "planning"
      project: "crypto-chise-bmad"
      created_at: "2026-03-08T12:00:00Z"
      
      # OPTIONAL - Relationships
      related_stories: ["ST-GOV-002", "ST-GOV-003"]
      related_incidents: ["GOV-BATCH-003"]
      
      # OPTIONAL - Searchable Content
      title: "Memory Deduplication Engine Implementation"
      key_decisions:
        - "Used cosine similarity over Euclidean distance"
        - "Threshold set to 0.92 for 95% accuracy target"
      lessons_learned:
        - "Integration tests should be created before marking validated"
        - "Cross-branch verification prevents false merge claims"
      
      # OPTIONAL - Evidence References
      evidence_refs:
        - type: "test_results"
          path: "docs/evidence/ST-GOV-001-test-results.json"
        - type: "merge_evidence"
          path: "docs/evidence/GOVERNANCE_MERGE_EVIDENCE_2026-03-08.md"
      
      # OPTIONAL - Metrics
      metrics:
        test_coverage: 88
        test_pass_rate: 100
        lines_of_code: 1330
  
  # Indexable Fields for Filtering
  filterable_fields:
    - story_id
    - epic_id
    - type
    - phase
    - project
    - created_at
    - related_stories
    - related_incidents
```

### Semantic Search Use Cases

| Use Case | Query Pattern | Example |
|----------|--------------|---------|
| **Find Similar Decisions** | Vector similarity + `type:decision` | "How did we handle deduplication before?" |
| **Learn from Failures** | `type:anti-pattern` + `related_incidents` | "What caused status falsification?" |
| **Pattern Discovery** | `type:pattern` + epic filter | "Common patterns in governance stories" |
| **Lesson Retrieval** | Vector similarity + `type:lesson` | "Lessons about cross-branch verification" |

---

## 4. MIGRATION MAPPING

### Field Migration Matrix

```yaml
migration_mapping:
  # HIGH-SIGNAL: Keep in workflow status
  - source_field: id
    target: workflow_status.required_fields.id
    condition: always
    
  - source_field: status
    target: workflow_status.required_fields.status
    condition: always
    
  - source_field: title
    target: workflow_status.required_fields.title
    condition: always
    
  - source_field: epic_id
    target: workflow_status.required_fields.epic_id
    condition: always
    
  - source_field: priority
    target: workflow_status.required_fields.priority
    condition: always
    
  - source_field: owner
    target: workflow_status.required_fields.owner
    condition: always
    
  - source_field: pr_number
    target: workflow_status.completion_evidence.pr_number
    condition: always
    
  - source_field: merge_commit
    target: workflow_status.completion_evidence.merge_commit
    condition: always
    
  - source_field: story_points
    target: workflow_status.planning_fields.story_points
    condition: always
    
  - source_field: sprint_id
    target: workflow_status.planning_fields.sprint_id
    condition: always

  # LOW-SIGNAL: Archive to story-details
  - source_field: acceptance_criteria
    target: archive.story_details.sections.acceptance_criteria
    condition: story.status in [completed, merged, deprecated]
    
  - source_field: implementation_notes
    target: archive.story_details.sections.implementation_notes
    condition: story.status in [completed, merged]
    
  - source_field: evidence_files
    target: archive.story_details.sections.evidence_files
    condition: always
    
  - source_field: test_results
    target: archive.story_details.sections.test_results
    condition: story.status in [completed, merged]
    
  - source_field: validation_gates
    target: archive.story_details.sections.validation_gates
    condition: story.status in [completed, merged, validated]
    
  - source_field: detailed_notes
    target: archive.story_details.sections.detailed_notes
    condition: story.status in [completed, merged]
    
  - source_field: notes
    target: archive.story_details.sections.detailed_notes
    condition: story.status in [completed, merged]
    
  - source_field: remediation_history
    target: archive.story_details.sections.remediation_history
    condition: exists
    
  - source_field: phases
    target: archive.story_details.sections.phases
    condition: exists
    
  - source_field: loop_results
    target: archive.story_details.sections.loop_results
    condition: exists

  # SEMANTIC: Migrate to Qdrant
  - source_field: key_decisions
    target: qdrant.metadata.payload.key_decisions
    condition: always
    transform: extract_from_notes_and_implementation
    
  - source_field: lessons_learned
    target: qdrant.metadata.payload.lessons_learned
    condition: story.status in [completed, merged]
    transform: extract_from_notes_and_remediation
    
  - source_field: description
    target: qdrant.metadata.payload.title
    condition: always
    transform: summarize_for_search
    
  - source_field: validation_summary
    target: qdrant.metadata.payload.metrics
    condition: exists
```

### Migration Script Pseudocode

```python
# migration_script.py

def migrate_story(story: dict) -> MigrationResult:
    """
    Migrate a single story from bloated workflow status to 3-tier architecture.
    """
    result = MigrationResult()
    
    # 1. Extract high-signal fields for lean workflow status
    result.workflow_entry = extract_workflow_fields(story)
    
    # 2. Create archive document with full details
    if should_archive(story):
        result.archive_document = create_archive_document(story)
        result.archive_path = write_archive(result.archive_document)
    
    # 3. Create Qdrant points for semantic search
    result.qdrant_points = []
    
    # 3a. Decision points
    if 'key_decisions' in story or 'implementation_notes' in story:
        decision_point = create_decision_point(story)
        result.qdrant_points.append(decision_point)
    
    # 3b. Lesson learned points
    if story['status'] in ['completed', 'merged']:
        lesson_point = create_lesson_point(story)
        result.qdrant_points.append(lesson_point)
    
    # 3c. Pattern/anti-pattern points
    if 'validation_summary' in story or 'test_results' in story:
        pattern_point = create_pattern_point(story)
        result.qdrant_points.append(pattern_point)
    
    return result

def should_archive(story: dict) -> bool:
    """Determine if story should be archived."""
    return (
        story['status'] in ['completed', 'merged', 'deprecated']
        and len(story.get('notes', [])) > 3  # Has substantial notes
    ) or 'acceptance_criteria' in story
```

---

## 5. ACCESS PATTERNS

### Agent Workflow

```yaml
# Quick Status Check (workflow status only)
agent_reads:
  - file: docs/bmm-workflow-status.yaml
  - pattern: "Find story by ID, get status and basic metadata"
  - latency: "<100ms"
  - lines_read: "~10 lines per story"

# Deep Dive (archive + workflow)
agent_researches:
  - file: docs/bmm-workflow-status.yaml
  - action: "Get story reference and archive_path"
  - then:
      - file: "docs/archives/story-details/{story_id}-details.yaml"
      - action: "Read full implementation details"
  - latency: "<500ms"
  - lines_read: "~100-500 lines per story"

# Pattern Discovery (Qdrant)
agent_discovers:
  - query: "qdrant.search(vector=embed('deduplication patterns'))"
  - filter: "type:pattern AND epic_id:EP-GOV-001"
  - action: "Find similar past implementations"
  - latency: "<200ms"
  - results: "Top 5 similar decisions with context"
```

### Automation Integration

```yaml
# CI/CD Pipeline
pre_commit_hook:
  - reads: workflow_status.completion_evidence
  - validates: pr_number and merge_commit present for completed stories
  - latency_requirement: "<1 second"

# Epic Status Sync
status_sync:
  - reads: workflow_status.required_fields.status
  - aggregates: child story statuses
  - writes: epic status updates
  - latency_requirement: "<5 seconds"

# Sprint Reporting
sprint_report:
  - reads: workflow_status.planning_fields
  - aggregates: story_points, completion rates
  - generates: velocity charts
  - latency_requirement: "<10 seconds"
```

---

## 6. IMPLEMENTATION ROADMAP

### Phase 1: Foundation (Week 1)

```yaml
phase_1:
  deliverables:
    - Create docs/archives/story-details/ directory structure
    - Create archive-index.yaml template
    - Create migration script skeleton
    - Update validation scripts to check new structure
  
  validation:
    - Archive directory exists and is git-tracked
    - Migration script can parse current workflow status
    - No breaking changes to existing automation
```

### Phase 2: Migration (Week 2-3)

```yaml
phase_2:
  deliverables:
    - Run migration on completed stories (status=completed/merged)
    - Create archive documents for top 20 largest stories
    - Verify archive index is accurate
    - Update workflow status with archive references
  
  validation:
    - All completed stories have archive documents
    - Archive index is queryable
    - Workflow status file size reduced by 50%+
```

### Phase 3: Qdrant Integration (Week 4)

```yaml
phase_3:
  deliverables:
    - Create Qdrant collection schema
    - Implement decision/lesson/pattern extraction
    - Populate Qdrant with historical data
    - Create semantic search CLI tool
  
  validation:
    - Qdrant contains >100 decision points
    - Semantic search returns relevant results
    - Integration tests pass
```

### Phase 4: Cleanup (Week 5)

```yaml
phase_4:
  deliverables:
    - Remove archived content from workflow status
    - Update all automation to use new paths
    - Create runbook for archive maintenance
    - Train agents on new access patterns
  
  validation:
    - Workflow status <1,000 lines
    - All CI passes
    - Agents can find information efficiently
```

---

## 7. RATIONALE SUMMARY

### Why This Architecture?

| Problem | Solution | Benefit |
|---------|----------|---------|
| **6,549 lines** in single file | 3-tier separation | 85% reduction in main file |
| **Mixed signal density** | Separate high/low signal | Faster status lookups |
| **No semantic search** | Qdrant integration | Pattern discovery across stories |
| **Historical bloat** | Archive with retention | Sustainable growth |
| **False merge claims** | Completion evidence guardrails | Audit integrity |

### Trade-offs

| Trade-off | Mitigation |
|-----------|------------|
| **More files to manage** | Automated archive index, clear naming conventions |
| **Cross-file lookups** | Archive references in workflow status, Qdrant relationships |
| **Migration complexity** | Phased approach, validation at each phase |
| **Learning curve** | Runbook documentation, agent training |

### Success Metrics

```yaml
success_metrics:
  file_size:
    before: 6549_lines
    target: <1000_lines
    measurement: wc -l docs/bmm-workflow-status.yaml
  
  lookup_latency:
    status_check: "<100ms"
    deep_dive: "<500ms"
    pattern_search: "<200ms"
  
  archive_coverage:
    completed_stories: "100% archived"
    archive_index_accuracy: "100%"
  
  qdrant_coverage:
    decision_points: ">100"
    lesson_learned: ">50"
    search_relevance: ">80% top-3 accuracy"
```

---

## Appendix A: Example Migration

### Before (Current State)

```yaml
# In docs/bmm-workflow-status.yaml (~50 lines)
- acceptance_criteria:
  - Detects semantic duplicates with ≥95% accuracy using Qdrant similarity
  - Deduplication runs automatically before memory writes
  - Configurable similarity threshold (default: 0.92 cosine similarity)
  - Conflict resolution for near-duplicates with timestamps
  - Performance: <100ms per deduplication check
  description: Detect and resolve semantic duplicate memories using Qdrant similarity
  epic_id: EP-GOV-001
  fr_coverage:
  - FR-GOV-001
  governance_feature: GF-001
  id: ST-GOV-001
  notes:
  - 'CI evidence: Woodpecker CI passed for merge commit 0ce77cf'
  - 'Test suite: 844 lines in tests/test_governance/test_deduplication.py'
  ci_evidence:
  - type: woodpecker_ci
    commit: 0ce77cf
    status: passed
  merge_commit: 0ce77cf
  pr_number: 410
  priority: P0-CRITICAL
  sprint_id: GOV-PHASE1-001
  status: completed
  story_points: 5
  test_strategy:
    integration: pytest tests/test_governance/integration/test_similarity_accuracy.py
    unit: pytest tests/test_governance/test_deduplication.py -v
  title: Memory Deduplication Engine
  validation_gates:
  - coverage: 85
  - false_positive_rate: <5%
  - latency_p99: <100ms
  validation_status: partial
  validation_notes:
  - 'coverage: 88% (PASSED)'
  - 'false_positive_rate: PENDING'
  - 'latency_p99: PENDING'
```

### After (Proposed State)

```yaml
# In docs/bmm-workflow-status.yaml (~15 lines)
- id: ST-GOV-001
  status: completed
  title: Memory Deduplication Engine
  epic_id: EP-GOV-001
  priority: P0-CRITICAL
  owner: senior-dev
  story_points: 5
  sprint_id: GOV-PHASE1-001
  pr_number: 410
  merge_commit: 0ce77cf
  description: Detect and resolve semantic duplicate memories using Qdrant similarity
  validation_status: partial
  archive_ref: docs/archives/story-details/ST-GOV-001-memory-deduplication-details.yaml
```

```yaml
# In docs/archives/story-details/ST-GOV-001-memory-deduplication-details.yaml (~100 lines)
story_id: ST-GOV-001
title: Memory Deduplication Engine
archived_at: "2026-03-08T12:00:00Z"
original_location: "docs/bmm-workflow-status.yaml"

sections:
  acceptance_criteria:
    - Detects semantic duplicates with ≥95% accuracy using Qdrant similarity
    - Deduplication runs automatically before memory writes
    - Configurable similarity threshold (default: 0.92 cosine similarity)
    - Conflict resolution for near-duplicates with timestamps
    - Performance: <100ms per deduplication check
  
  implementation_notes:
    test_suite_size: "844 lines"
    ci_status: passed
    ci_commit: 0ce77cf
  
  validation_gates:
    coverage: { target: 85, actual: 88, status: passed }
    false_positive_rate: { target: "<5%", actual: null, status: pending }
    latency_p99: { target: "<100ms", actual: null, status: pending }
  
  remediation_notes:
    - "CONSOLIDATION REMEDIATION 2026-03-08: Verified merged to main"
```

---

## Appendix B: Validation Checklist

```yaml
pre_migration:
  - [ ] Backup current workflow status
  - [ ] Document current file size and line count
  - [ ] Identify all automation that reads workflow status
  - [ ] Create rollback plan

post_migration:
  - [ ] Verify workflow status <1,000 lines
  - [ ] Verify all completed stories have archive documents
  - [ ] Verify archive index is accurate
  - [ ] Verify Qdrant contains expected decision points
  - [ ] Run full CI pipeline
  - [ ] Test agent workflows
  - [ ] Validate completion evidence guardrails still work
  - [ ] Update documentation
```

---

*Document Version: 1.0*
*Created: 2026-03-09*
*Author: Senior Architect*
*Status: Design Complete - Ready for Review*
