# AGENT DISCOVERABILITY AND UX GUIDANCE

> **Purpose**: Help agents quickly find information in the workflow status archival system with minimal friction.
> 
> **Version**: 1.0
> **Last Updated**: 2026-03-09
> **Applies To**: All agents (Aria, Jarvis, Senior Dev, Junior Dev, Merlin, Quick Dev)

---

## 1. INFORMATION ARCHITECTURE: WHERE TO LOOK

### Primary Lookup Order (for agents)

```
┌─────────────────────────────────────────────────────────────┐
│  AGENT INFORMATION LOOKUP HIERARCHY                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. WORKFLOW STATUS (docs/bmm-workflow-status.yaml)        │
│     └── Use for: Quick status checks, current state        │
│     └── Speed: <100ms                                      │
│     └── Contains: ID, status, title, owner, dates, PR#     │
│                                                             │
│  2. ARCHIVE INDEX (docs/archives/workflow-status/archive-index.yaml)
│     └── Use for: Finding archived story details            │
│     └── Speed: <200ms                                      │
│     └── Contains: Story list, archive locations            │
│                                                             │
│  3. ARCHIVE DOCUMENTS (docs/archives/story-details/)       │
│     └── Use for: Deep evidence, test results, AC           │
│     └── Speed: <500ms                                      │
│     └── Contains: Full story details                       │
│                                                             │
│  4. QDRANT SEARCH (vector search)                          │
│     └── Use for: Pattern matching, semantic search         │
│     └── Speed: <200ms                                      │
│     └── Contains: Decisions, patterns, lessons             │
│                                                             │
│  5. GIT HISTORY (git log/show)                             │
│     └── Use for: Historical versions, blame                │
│     └── Speed: 1-5s                                         │
│     └── Contains: All historical states                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Decision Tree for Information Lookup

```
What do you need?
│
├─→ Current status of a story?
│   └─→ Look in: WORKFLOW STATUS (field: status)
│
├─→ Who owns this story?
│   └─→ Look in: WORKFLOW STATUS (field: owner)
│
├─→ When was this completed?
│   └─→ Look in: WORKFLOW STATUS (field: completed_date or merged_date)
│
├─→ What was the merge commit?
│   └─→ Look in: WORKFLOW STATUS (field: merge_commit)
│
├─→ What were the acceptance criteria?
│   └─→ Look in: WORKFLOW STATUS (field: acceptance_criteria) if story is active
│   └─→ OR: ARCHIVE DOCUMENT (section: acceptance_criteria) if archived
│   └─→ Path: docs/archives/story-details/{story-id}-details.yaml
│
├─→ What evidence files were created?
│   └─→ Look in: WORKFLOW STATUS (field: evidence_files) if active
│   └─→ OR: ARCHIVE DOCUMENT (section: evidence_manifest) if archived
│
├─→ What were the test results?
│   └─→ Look in: WORKFLOW STATUS (field: test_results) if active
│   └─→ OR: ARCHIVE DOCUMENT (section: test_results) if archived
│
├─→ What lessons were learned?
│   └─→ Look in: QDRANT (search: story_id + "lessons")
│   └─→ OR: ARCHIVE DOCUMENT (section: notes_and_decisions.lessons_learned)
│
├─→ Similar patterns from past stories?
│   └─→ Look in: QDRANT (semantic search)
│   └─→ OR: Search archive documents for pattern keywords
│
├─→ What was the Redis iterlog key?
│   └─→ Look in: WORKFLOW STATUS (field: redis_iterlog_key)
│   └─→ Pattern: bmad:chiseai:iterlog:story:{story_id}
│
└─→ What did the workflow look like last week?
    └─→ Look in: GIT HISTORY (git show HEAD~7:docs/bmm-workflow-status.yaml)
    └─→ OR: ARCHIVE (docs/archives/workflow-status/archive-YYYY-MM.yaml)
```

---

## 2. QUICK REFERENCE CARD

### Fast Commands for Daily Use

```bash
# Quick status check (find story in workflow)
grep -A 5 "id: ST-XXX" docs/bmm-workflow-status.yaml

# Find story in archive index
grep "ST-XXX" docs/archives/workflow-status/archive-index.yaml

# Check if story has archived details
ls docs/archives/story-details/ | grep ST-XXX

# Read archived acceptance criteria
yq '.acceptance_criteria' docs/archives/story-details/ST-XXX-details.yaml

# Search Qdrant for patterns
python3 scripts/memory/search_qdrant.py --query "circuit breaker implementation"

# Find stories by epic
grep -B 2 -A 5 "epic_id: EP-XXX" docs/bmm-workflow-status.yaml

# Find stories by owner
grep -B 2 -A 3 "owner: jarvis" docs/bmm-workflow-status.yaml | grep "id:"

# Check Redis iterlog for story
redis-cli -h host.docker.internal -p 6380 HGETALL "bmad:chiseai:iterlog:story:ST-XXX"

# Find stories by status (e.g., completed)
yq '.completed[] | select(.status == "completed") | .id' docs/bmm-workflow-status.yaml

# Get story title quickly
grep -A 1 "id: ST-XXX" docs/bmm-workflow-status.yaml | grep "title:"
```

### Field Mapping: Workflow Status → Archive

| Information Need | Workflow Status Location | Archive Location | When to Use Archive |
|-----------------|--------------------------|------------------|---------------------|
| **id** | `id` field | `story_summary.id` | Never - always in workflow |
| **status** | `status` field | `story_summary.status` | If story >7 days old |
| **title** | `title` field | `story_summary.title` | If story >7 days old |
| **owner** | `owner` field | `story_summary.owner` | If story >7 days old |
| **priority** | `priority` field | `story_summary.priority` | If story >7 days old |
| **story_points** | `story_points` field | `story_summary.story_points` | If story >7 days old |
| **pr_number** | `pr_number` field | `story_summary.pr_number` | If story >7 days old |
| **merge_commit** | `merge_commit` field | `story_summary.merge_commit` | If story >7 days old |
| **acceptance_criteria** | `acceptance_criteria` field (if present) | `acceptance_criteria` section | Always for detailed AC |
| **evidence_files** | `evidence_files` field (if present) | `evidence_manifest.files` | Always for full manifest |
| **test_results** | `test_results` field (if present) | `test_results` section | Always for detailed results |
| **validation_summary** | `validation_summary` field (if present) | `validation_summary` section | Always for full summary |
| **notes** | `notes` field | `notes_and_decisions` section | Always for detailed notes |
| **key_decisions** | `notes` field (embedded) | `notes_and_decisions.key_decisions` | Always for structured decisions |
| **lessons_learned** | `notes` field (embedded) | `notes_and_decisions.lessons_learned` | Always for structured lessons |
| **redis_iterlog_key** | `redis_iterlog_key` field | `iterlog_references` | If accessing iterlog |

### Quick Decision Matrix

| If you need... | Start Here | Then Try | Last Resort |
|----------------|------------|----------|-------------|
| Current story status | Workflow status | Archive index | Git history |
| Story owner | Workflow status | Archive document | Git blame |
| Acceptance criteria | Workflow status | Archive document | Git history |
| Evidence files | Workflow status | Archive document | Git log --name-only |
| Test results | Workflow status | Archive document | CI logs |
| Key decisions | Qdrant search | Archive document | Git history |
| Lessons learned | Qdrant search | Archive document | Git history |
| Similar patterns | Qdrant semantic | Archive grep | Git grep |
| Historical versions | Archive documents | Archive index | Git show |

---

## 3. DEEP DIVE WORKFLOW

### How to Access Archived Details

#### Python Helper Function

```python
"""
Story Details Retrieval Helper
Place in: scripts/utils/story_lookup.py
"""

import yaml
from pathlib import Path
from typing import Optional, Dict, Any

def get_story_details(story_id: str) -> Dict[str, Any]:
    """
    Retrieve complete story details from workflow + archive.
    
    Lookup order:
    1. Get summary from workflow status
    2. Check if archived
    3. Load archive if available
    4. Search Qdrant for patterns
    
    Args:
        story_id: The story ID (e.g., "ST-GOV-001")
        
    Returns:
        Dict containing story summary and archived details if available
        
    Raises:
        ValueError: If story not found in workflow status
    """
    # Step 1: Get from workflow status
    workflow_path = Path("docs/bmm-workflow-status.yaml")
    if not workflow_path.exists():
        raise FileNotFoundError("Workflow status file not found")
    
    workflow = yaml.safe_load(workflow_path.read_text())
    
    story = None
    sections_to_check = ["completed", "backlog", "current_phase", "epics", "launch_stories"]
    
    for section in sections_to_check:
        if section in workflow:
            section_data = workflow[section]
            if isinstance(section_data, list):
                for item in section_data:
                    if isinstance(item, dict) and item.get("id") == story_id:
                        story = item
                        break
            elif isinstance(section_data, dict) and section_data.get("id") == story_id:
                story = section_data
                break
    
    if not story:
        raise ValueError(f"Story {story_id} not found in workflow status")
    
    result = {
        "story_summary": story,
        "source": "workflow_status",
        "archived_details": None,
        "archive_path": None
    }
    
    # Step 2: Check if archived
    archive_path = Path(f"docs/archives/story-details/{story_id}-details.yaml")
    if archive_path.exists():
        # Step 3: Load archived details
        archive = yaml.safe_load(archive_path.read_text())
        result["archived_details"] = archive
        result["archive_path"] = str(archive_path)
        result["source"] = "archived"
    
    return result


def get_acceptance_criteria(story_id: str) -> Optional[list]:
    """Get acceptance criteria for a story."""
    try:
        details = get_story_details(story_id)
        
        # Try archived details first
        if details.get("archived_details"):
            return details["archived_details"].get("acceptance_criteria")
        
        # Fall back to workflow status
        return details["story_summary"].get("acceptance_criteria")
    except ValueError:
        return None


def get_evidence_files(story_id: str) -> Optional[list]:
    """Get evidence files for a story."""
    try:
        details = get_story_details(story_id)
        
        # Try archived details first
        if details.get("archived_details"):
            manifest = details["archived_details"].get("evidence_manifest", {})
            return manifest.get("files", [])
        
        # Fall back to workflow status
        return details["story_summary"].get("evidence_files", [])
    except ValueError:
        return None


def get_test_results(story_id: str) -> Optional[Dict]:
    """Get test results for a story."""
    try:
        details = get_story_details(story_id)
        
        # Try archived details first
        if details.get("archived_details"):
            return details["archived_details"].get("test_results")
        
        # Fall back to workflow status
        return details["story_summary"].get("test_results")
    except ValueError:
        return None


def get_lessons_learned(story_id: str) -> Optional[list]:
    """Get lessons learned for a story."""
    try:
        details = get_story_details(story_id)
        
        # Try archived details first
        if details.get("archived_details"):
            notes = details["archived_details"].get("notes_and_decisions", {})
            return notes.get("lessons_learned", [])
        
        # Fall back to workflow status notes
        return details["story_summary"].get("notes", [])
    except ValueError:
        return None


# Example usage
if __name__ == "__main__":
    story_id = "ST-EXAMPLE-001"
    
    # Get full details
    story = get_story_details(story_id)
    print(f"Status: {story['story_summary'].get('status')}")
    print(f"Owner: {story['story_summary'].get('owner')}")
    
    if story.get('archived_details'):
        print(f"Archive location: {story['archive_path']}")
        ac = get_acceptance_criteria(story_id)
        if ac:
            print(f"Acceptance Criteria: {len(ac)} items")
    
    # Quick lookups
    print(f"\nAC: {get_acceptance_criteria(story_id)}")
    print(f"Evidence: {get_evidence_files(story_id)}")
    print(f"Lessons: {get_lessons_learned(story_id)}")
```

#### Bash Helper Aliases

Add to your `.bashrc` or `.zshrc`:

```bash
# Story lookup aliases
alias story-status='grep -A 5 "id: $1" docs/bmm-workflow-status.yaml'
alias story-archive='ls docs/archives/story-details/ | grep $1'
alias story-ac='yq ".acceptance_criteria" docs/archives/story-details/$1-details.yaml 2>/dev/null || echo "Not archived"'
alias story-evidence='yq ".evidence_manifest.files" docs/archives/story-details/$1-details.yaml 2>/dev/null || echo "Not archived"'
alias story-tests='yq ".test_results" docs/archives/story-details/$1-details.yaml 2>/dev/null || echo "Not archived"'
alias story-lessons='yq ".notes_and_decisions.lessons_learned" docs/archives/story-details/$1-details.yaml 2>/dev/null || echo "Not archived"'

# Usage:
# story-status ST-GOV-001
# story-archive ST-GOV-001
# story-ac ST-GOV-001
```

---

## 4. SEARCH PATTERNS

### Finding Information Efficiently

#### Pattern 1: "What stories are in epic EP-XXX?"

```bash
# Fast grep approach (finds all mentions)
grep -B 2 "epic_id: EP-XXX" docs/bmm-workflow-status.yaml | grep "id:"

# Using yq for structured output (more precise)
yq '.completed[] | select(.epic_id == "EP-XXX") | {id: .id, title: .title, status: .status}' docs/bmm-workflow-status.yaml

# Search across all sections
yq '[.completed[], .backlog[], .launch_stories[]] | select(.epic_id == "EP-XXX") | .id' docs/bmm-workflow-status.yaml
```

#### Pattern 2: "Find stories about circuit breakers"

```bash
# Search workflow titles
grep -i -B 2 -A 2 "circuit" docs/bmm-workflow-status.yaml

# Search archived details
find docs/archives/story-details/ -name "*.yaml" -exec grep -l -i "circuit" {} \;

# Semantic search in Qdrant
python3 scripts/memory/search_qdrant.py --query "circuit breaker implementation pattern"

# Combined search (workflow + archives)
echo "=== Workflow Status ===" && grep -i "circuit" docs/bmm-workflow-status.yaml -B 1 -A 3 && echo "=== Archives ===" && find docs/archives/story-details/ -name "*.yaml" -exec grep -l -i "circuit" {} \;
```

#### Pattern 3: "What was completed last week?"

```bash
# Using yq to filter by date (stories completed after 2026-03-01)
yq '.completed[] | select(.completed_date >= "2026-03-01" or .merged_date >= "2026-03-01") | {id: .id, title: .title, date: (.completed_date // .merged_date)}' docs/bmm-workflow-status.yaml

# Find by specific date range
yq '.completed[] | select(.merged_date >= "2026-03-01" and .merged_date <= "2026-03-07") | .id' docs/bmm-workflow-status.yaml
```

#### Pattern 4: "Find stories by owner"

```bash
# Find all stories owned by jarvis
grep -B 2 -A 3 'owner: jarvis' docs/bmm-workflow-status.yaml | grep -E "(id:|title:|status:)"

# Using yq for cleaner output
yq '.completed[] | select(.owner == "jarvis") | {id: .id, title: .title, status: .status}' docs/bmm-workflow-status.yaml
```

#### Pattern 5: "Find stories with specific status"

```bash
# Find all merged stories
yq '.completed[] | select(.status == "merged") | {id: .id, title: .title, merge_commit: .merge_commit}' docs/bmm-workflow-status.yaml

# Find all completed stories
yq '.completed[] | select(.status == "completed") | .id' docs/bmm-workflow-status.yaml
```

#### Pattern 6: "Search for patterns across all sources"

```bash
# Comprehensive search script
#!/bin/bash
# scripts/utils/comprehensive_search.sh

QUERY="$1"
echo "=== Searching for: $QUERY ==="
echo ""

echo "1. Workflow Status (titles):"
grep -i "$QUERY" docs/bmm-workflow-status.yaml -B 1 -A 1 | head -20
echo ""

echo "2. Archive Documents:"
find docs/archives/story-details/ -name "*.yaml" -exec grep -l -i "$QUERY" {} \; 2>/dev/null | head -10
echo ""

echo "3. Archive Index:"
grep -i "$QUERY" docs/archives/workflow-status/archive-index.yaml | head -10
echo ""

echo "4. Qdrant (if available):"
python3 scripts/memory/search_qdrant.py --query "$QUERY" --limit 5 2>/dev/null || echo "Qdrant search not available"
```

---

## 5. ERROR HANDLING

### Common Scenarios and Solutions

#### Scenario 1: "I can't find the acceptance criteria"

```
SYMPTOM: Story exists in workflow but acceptance_criteria field is missing or empty

DIAGNOSIS: 
- Story may have been archived (completed >7 days ago)
- AC may be in notes field instead
- AC may not have been documented

SOLUTION:
1. Check if story is archived:
   ls docs/archives/story-details/ST-XXX-details.yaml

2. If archived, read from archive:
   yq '.acceptance_criteria' docs/archives/story-details/ST-XXX-details.yaml

3. If not archived, check notes field:
   grep -A 20 "id: ST-XXX" docs/bmm-workflow-status.yaml | grep "notes:"

4. Check archive index for historical versions:
   grep "ST-XXX" docs/archives/workflow-status/archive-index.yaml

FALLBACK:
- Check git history: git log -p -- docs/bmm-workflow-status.yaml | grep -A 30 "ST-XXX" | head -50
- Search Qdrant: python3 scripts/memory/search_qdrant.py --query "ST-XXX acceptance criteria"
- Ask story owner (check workflow status owner field)
```

#### Scenario 2: "Archive file is missing"

```
SYMPTOM: Story marked as completed/merged but archive file doesn't exist

DIAGNOSIS: 
- Archive file was deleted
- Archival failed
- Story is still within 7-day retention window (not yet archived)

SOLUTION:
1. Check if story is within retention window:
   grep -A 3 "id: ST-XXX" docs/bmm-workflow-status.yaml | grep -E "(completed_date|merged_date)"

2. Check git history for archive file:
   git log -- docs/archives/story-details/ST-XXX-details.yaml

3. Restore from git if exists:
   git checkout HEAD -- docs/archives/story-details/ST-XXX-details.yaml

4. If not in git, check if archival script needs to be run:
   python3 scripts/workflow/archive_old_stories.py --dry-run

ESCALATION:
- Log incident: python3 scripts/workflow/report_archival_incident.py --story-id ST-XXX
- Notify: jarvis or senior-dev
```

#### Scenario 3: "Qdrant search returns no results"

```
SYMPTOM: Semantic search finds nothing for a known story or pattern

DIAGNOSIS:
- Story not promoted to Qdrant (check promotion criteria)
- Qdrant unavailable
- Search query too specific

SOLUTION:
1. Check if story should be in Qdrant:
   - Priority >= P1: Should be promoted
   - Has lessons_learned or key_decisions: Should be promoted
   - Check archive document: yq '.qdrant_promotion.promoted' docs/archives/story-details/ST-XXX-details.yaml

2. Check Qdrant health:
   curl http://host.docker.internal:6334/healthz

3. Manual promotion if needed:
   python3 scripts/memory/promote_to_qdrant.py --story-id ST-XXX

4. Try broader search terms:
   - Instead of "circuit breaker registry implementation"
   - Try: "circuit breaker" or "registry pattern"

FALLBACK:
- Use archive document instead
- Use grep on workflow status
- Search tempmemories: grep -r "ST-XXX" docs/tempmemories/
```

#### Scenario 4: "Workflow status file is large/slow"

```
SYMPTOM: Reading workflow status takes too long or returns too much data

DIAGNOSIS:
- File has grown large with many completed stories
- Need to use more targeted queries

SOLUTION:
1. Use yq for targeted extraction:
   yq '.completed[] | select(.id == "ST-XXX")' docs/bmm-workflow-status.yaml

2. Use grep with context control:
   grep -A 10 "id: ST-XXX" docs/bmm-workflow-status.yaml

3. Check archive for old stories:
   grep "ST-XXX" docs/archives/workflow-status/archive-index.yaml

OPTIMIZATION:
- For batch operations, use archive index instead of full workflow
- Archive old stories regularly: python3 scripts/workflow/archive_old_stories.py
```

#### Scenario 5: "Redis iterlog key not found"

```
SYMPTOM: Cannot find iterlog in Redis for a story

DIAGNOSIS:
- TTL expired (default 5 days)
- Wrong key format
- Redis unavailable

SOLUTION:
1. Verify key format:
   bmad:chiseai:iterlog:story:ST-XXX

2. Check if key exists:
   redis-cli -h host.docker.internal -p 6380 EXISTS "bmad:chiseai:iterlog:story:ST-XXX"

3. Check for tempmemory fallback:
   ls docs/tempmemories/iterlog-ST-XXX.md

4. Search for any iterlog files:
   find docs/tempmemories/ -name "*ST-XXX*"

FALLBACK:
- Use archive document notes_and_decisions section
- Check git commit messages: git log --grep="ST-XXX"
- Check PR history: gh pr list --search "ST-XXX"
```

---

## 6. AGENT ONBOARDING CHECKLIST

New agents should complete this checklist before working with the workflow system:

### Tier 1: Basic Navigation (Day 1)
- [ ] Understand the 5-tier information architecture
- [ ] Can locate docs/bmm-workflow-status.yaml
- [ ] Can locate docs/archives/workflow-status/archive-index.yaml
- [ ] Can locate docs/archives/story-details/ directory
- [ ] Can find a story by ID in workflow status
- [ ] Can determine story status, owner, and priority

### Tier 2: Archive Access (Day 2-3)
- [ ] Can check if a story is archived
- [ ] Can read archived acceptance criteria
- [ ] Can read archived evidence manifest
- [ ] Can read archived test results
- [ ] Can read archived notes and decisions
- [ ] Understand when to use archive vs workflow status

### Tier 3: Advanced Search (Week 1)
- [ ] Can search for stories by epic
- [ ] Can search for stories by owner
- [ ] Can search for stories by status
- [ ] Can use Qdrant semantic search
- [ ] Can use git history for historical versions
- [ ] Can perform comprehensive searches across all sources

### Tier 4: Troubleshooting (Week 2)
- [ ] Can handle missing acceptance criteria
- [ ] Can handle missing archive files
- [ ] Can handle Qdrant search failures
- [ ] Can use fallback methods effectively
- [ ] Knows when to escalate to jarvis/senior-dev

### Tier 5: Expert Usage (Ongoing)
- [ ] Can write helper scripts for common lookups
- [ ] Can optimize search patterns for performance
- [ ] Can mentor other agents on navigation
- [ ] Contributes improvements to this guide

---

## 7. DECISION FLOWCHART

```
┌──────────────────────────────────────────────────────────────┐
│ START: Need information about a story                        │
└──────────────────┬───────────────────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────────────────┐
│ Is it current status, owner, or basic metadata?              │
└────────┬─────────────────────────────┬───────────────────────┘
         │ YES                         │ NO
         ▼                             ▼
┌────────────────────┐      ┌──────────────────────────────────┐
│ Read from WORKFLOW │      │ Is it acceptance criteria,       │
│ STATUS             │      │ evidence, or test results?       │
└────────┬───────────┘      └────────┬─────────────────────────┘
         │                           │ YES
         │                           ▼
         │              ┌──────────────────────────────────┐
         │              │ Check ARCHIVE INDEX for story_id │
         │              └────────┬─────────────────────────┘
         │                       │
         │         ┌─────────────┴─────────────┐
         │         │ Found                     │ Not Found
         │         ▼                           ▼
         │  ┌──────────────┐        ┌──────────────────────┐
         │  │ Read ARCHIVE │        │ Story not archived   │
         │  │ DOCUMENT     │        │ yet - check workflow │
         │  └──────────────┘        │ notes or ask human   │
         │                          └──────────────────────┘
         │
         │                           │ NO
         │                           ▼
         │              ┌──────────────────────────────────┐
         │              │ Is it patterns, lessons, or      │
         │              │ similar past decisions?          │
         │              └────────┬─────────────────────────┘
         │                       │ YES
         │                       ▼
         │              ┌──────────────────────────────────┐
         │              │ Search QDRANT with semantic query│
         │              └────────┬─────────────────────────┘
         │                       │
         │         ┌─────────────┴─────────────┐
         │         │ Found                     │ Not Found
         │         ▼                           ▼
         │  ┌──────────────┐        ┌──────────────────────┐
         │  │ Use QDRANT   │        │ Fall back to grep    │
         │  │ RESULTS      │        │ on archives          │
         │  └──────────────┘        └──────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────────┐
│ END: Information retrieved                                   │
└──────────────────────────────────────────────────────────────┘
```

---

## 8. PERFORMANCE EXPECTATIONS

| Operation | Expected Time | Max Acceptable | Optimization Tip |
|-----------|---------------|----------------|------------------|
| Workflow status read | 50ms | 100ms | Use yq for targeted queries |
| Archive index lookup | 100ms | 200ms | Use grep for simple lookups |
| Archive document read | 200ms | 500ms | Cache frequently accessed |
| Qdrant semantic search | 150ms | 300ms | Use specific queries |
| Git history query | 2s | 5s | Limit with --since |
| Full story details (all sources) | 500ms | 1s | Use helper functions |
| Comprehensive search | 2s | 5s | Parallelize where possible |

### Performance Best Practices

1. **Prefer targeted queries over full file reads**
   - Use `yq` with selectors instead of loading entire YAML
   - Use `grep -A N` for context instead of reading full file

2. **Cache frequently accessed archives**
   - If reading same archive multiple times, cache in memory
   - Use Redis for cross-session caching

3. **Parallelize independent lookups**
   - Workflow status and Qdrant search can happen in parallel
   - Use background processes for git history queries

4. **Fall back gracefully**
   - If Qdrant is slow (>300ms), use archive grep
   - If archive is slow, use workflow status

---

## 9. INTEGRATION WITH WORKFLOW COMMANDS

### Iteration Start (chise-iterloop-start)

When starting work, agents should:

1. **Check workflow status** for story context:
   ```bash
   grep -A 10 "id: ST-XXX" docs/bmm-workflow-status.yaml
   ```

2. **Check related stories** in same epic:
   ```bash
   yq '.completed[] | select(.epic_id == "EP-XXX") | .id' docs/bmm-workflow-status.yaml
   ```

3. **Search Qdrant** for relevant patterns:
   ```bash
   python3 scripts/memory/search_qdrant.py --query "<story topic>"
   ```

### Iteration Close (chise-iterloop-close)

When closing work, agents should:

1. **Update workflow status** with completion evidence
2. **Ensure archive document** is created if story is being archived
3. **Promote to Qdrant** if story meets criteria (P0/P1, has lessons)
4. **Update archive index** if applicable

---

## 10. REFERENCE MATERIALS

### Key Files

| File | Purpose | When to Read |
|------|---------|--------------|
| `docs/bmm-workflow-status.yaml` | Current workflow state | Every iteration start |
| `docs/archives/workflow-status/archive-index.yaml` | Archive locations | Looking for old stories |
| `docs/archives/story-details/*.yaml` | Detailed story archives | Deep evidence needed |
| `docs/archives/examples/ST-EXAMPLE-001-details.yaml` | Archive format example | Creating new archives |
| `.opencode/command/chise-iterloop-start.md` | Iteration start procedure | Starting work |
| `.opencode/command/chise-iterloop-close.md` | Iteration close procedure | Completing work |

### Tools and Scripts

| Script | Purpose | Location |
|--------|---------|----------|
| `archive_old_stories.py` | Archive completed stories | `scripts/workflow/` |
| `search_qdrant.py` | Semantic search | `scripts/memory/` |
| `promote_to_qdrant.py` | Manual Qdrant promotion | `scripts/memory/` |
| `story_lookup.py` | Helper functions | `scripts/utils/` (create this) |

### Redis Key Patterns

```
bmad:chiseai:iterlog:story:{story_id}     # Story iteration log
bmad:chiseai:metacog:prediction:story:{story_id}  # Prediction card
bmad:chiseai:metacog:outcome:story:{story_id}     # Outcome card
bmad:chiseai:ownership:{path_slug}       # Scope ownership
```

---

## 11. QUICK START EXAMPLES

### Example 1: Starting Work on a Story

```bash
# 1. Find the story
STORY_ID="ST-GOV-001"
grep -A 10 "id: $STORY_ID" docs/bmm-workflow-status.yaml

# 2. Check if archived
if [ -f "docs/archives/story-details/${STORY_ID}-details.yaml" ]; then
    echo "Story has archived details"
    yq '.acceptance_criteria' "docs/archives/story-details/${STORY_ID}-details.yaml"
fi

# 3. Search for related patterns
python3 scripts/memory/search_qdrant.py --query "governance pattern"

# 4. Start iteration
# (follow chise-iterloop-start.md)
```

### Example 2: Finding Similar Past Work

```bash
# Search for similar stories
QUERY="circuit breaker"

# 1. Search workflow
grep -i "$QUERY" docs/bmm-workflow-status.yaml -B 1 -A 2

# 2. Search archives
find docs/archives/story-details/ -name "*.yaml" -exec grep -l -i "$QUERY" {} \;

# 3. Search Qdrant
python3 scripts/memory/search_qdrant.py --query "$QUERY" --limit 5
```

### Example 3: Completing a Story

```bash
# 1. Update workflow status with completion evidence
# (edit docs/bmm-workflow-status.yaml)

# 2. Create archive document if story is old
python3 scripts/workflow/archive_old_stories.py --story-id ST-XXX

# 3. Promote to Qdrant if meets criteria
python3 scripts/memory/promote_to_qdrant.py --story-id ST-XXX

# 4. Close iteration
# (follow chise-iterloop-close.md)
```

---

## 12. TROUBLESHOOTING QUICK REFERENCE

| Problem | Quick Fix | Full Solution |
|---------|-----------|---------------|
| Can't find story | Use `grep -r "ST-XXX" docs/` | See Scenario 1 in Error Handling |
| AC missing | Check archive document | See Section 5, Scenario 1 |
| Archive missing | Check git history | See Section 5, Scenario 2 |
| Qdrant empty | Try broader search | See Section 5, Scenario 3 |
| File too slow | Use yq selectors | See Section 8, Performance |
| Redis key missing | Check tempmemories | See Section 5, Scenario 5 |

---

## APPENDIX A: YQ QUERY CHEAT SHEET

```bash
# Get specific field
yq '.completed[0].id' docs/bmm-workflow-status.yaml

# Filter by condition
yq '.completed[] | select(.status == "merged") | .id' docs/bmm-workflow-status.yaml

# Get multiple fields
yq '.completed[] | select(.id == "ST-XXX") | {id: .id, title: .title, status: .status}' docs/bmm-workflow-status.yaml

# Count items
yq '.completed | length' docs/bmm-workflow-status.yaml

# Get array of IDs
yq '[.completed[].id]' docs/bmm-workflow-status.yaml

# Complex filter
yq '.completed[] | select(.priority == "P0" and .status == "completed") | .id' docs/bmm-workflow-status.yaml
```

---

## APPENDIX B: GIT HISTORY QUERIES

```bash
# Show workflow status from 7 days ago
git show HEAD~7:docs/bmm-workflow-status.yaml | head -50

# Find when a story was added
git log -p -- docs/bmm-workflow-status.yaml | grep -B 5 -A 5 "ST-XXX" | head -30

# Show all changes to workflow status
git log --oneline -- docs/bmm-workflow-status.yaml | head -10

# Find commits mentioning a story
git log --all --grep="ST-XXX" --oneline

# Show archive file history
git log --oneline -- docs/archives/story-details/ST-XXX-details.yaml
```

---

**Document Owner**: Jarvis  
**Review Cycle**: Monthly or after major workflow changes  
**Feedback**: Submit improvements via PR with tag `docs-discoverability`
