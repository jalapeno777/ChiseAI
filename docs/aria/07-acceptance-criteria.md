# Acceptance Criteria

## 1. Identity contract
Done when:
- there is one canonical identity contract file
- approval-gated fields are explicit
- session startup always loads the contract
- no hidden alternate source silently overrides the contract

## 2. Belief mutation governance
Done when:
- every belief mutation has evidence and provenance
- every belief mutation writes an audit record
- protected mutations are blocked pending approval
- strongest-evidence conflict resolution is enforced or clearly logged

## 3. Unified memory layer
Done when:
- one query path can assemble final context from current backends
- context assembly order is deterministic
- low-value items can be evicted or compressed by policy
- protected identity items are never evicted

## 4. Consolidation
Done when:
- scheduler runs on schedule
- dry-run mode was validated first
- live archival/promotion metrics are observable
- rollback path exists
- tempmemory growth is no longer unbounded without oversight

## 5. Lesson effectiveness
Done when:
- lesson application can be tracked
- lesson outcome impact can be scored
- low-value lessons can be flagged for deprecation
- useful lessons can be promoted with evidence

## 6. Persona consistency testing
Done when:
- golden scenarios exist
- weekly automated runs exist
- drift score is computed
- critical persona regressions fail the suite

## 7. Notification system
Done when:
- daily digest sends at 8:00 PM America/Toronto
- high/critical items alert immediately
- approval requests alert immediately
- failures are logged and retried
- digest content matches approved policy

## 8. Documentation quality
Done when:
- docs are checked into repo
- swarm agents can find them easily
- prompts reference the docs by path
- tech-writer or equivalent confirms consistency across files
