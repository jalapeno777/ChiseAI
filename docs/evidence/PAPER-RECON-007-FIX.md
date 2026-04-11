{
"story_id": "PAPER-RECON-007-FIX",
"epic_id": "EP-PAPER-RECON-001",
"task": "schema-fix",
"captured_at": "2026-04-11T20:55:00Z",
"round": 2,
"problem": "Backfill script had CRITICAL issues: jsonb columns receiving JSON strings, UUID as string, and schema drift",
"critic_findings": {
"CRITICAL-1": {
"issue": "metadata and venue_metadata are jsonb columns but json.dumps() produces TEXT string. asyncpg auto-casts but this is fragile",
"fix": "Pass dict directly to asyncpg - asyncpg handles dict -> jsonb natively",
"code_change": "Removed json.dumps() calls for metadata_val and venue_metadata_val"
},
"HIGH-2": {
"issue": "signal_id passed as string to UUID column",
"fix": "Parse signal_id to UUID object before INSERT",
"code_change": "Added UUID parsing: UUID(signal_id_val) when signal_id is a string"
},
"HIGH-1": {
"issue": "ORM model has 3 columns not in Postgres (confidence_score, signal_type, is_test)",
"fix": "DOCUMENTED ONLY - do NOT fix in this PR (would require migration or model changes)",
"code_change": "None - documented as known issue"
}
},
"resolution": {
"description": "Fixed jsonb type mismatch and UUID parsing in paper_backfill.py",
"files_modified": [
"scripts/paper_backfill.py",
"docs/evidence/PAPER-RECON-007-FIX.md"
],
"key_changes": [
"CRITICAL-1: Removed json.dumps() for metadata and venue_metadata - pass dict directly",
"HIGH-2: Added UUID parsing for signal_id before INSERT",
"HIGH-1: Documented schema drift as known issue (ORM has columns Postgres lacks)"
]
},
"known_issues": {
"schema_drift": {
"description": "ORM model src/execution/outcomes/models.py has 3 columns not in Postgres: confidence_score, signal_type, is_test",
"impact": "Requires migration or model alignment to resolve",
"follow_up_task": "ST-PAPER-RECON-008 (schema alignment)"
}
},
"validation": {
"critic_review": "passed 2026-04-11",
"test_results": "pending"
},
"branch_head": "1a55c137fd99a9075fa1d87abc0b32bbc54a62a2",
"status": "IN_PROGRESS",
"evidence_links": {
"backfill_script": "scripts/paper_backfill.py",
"construct_outcome": "scripts/paper_backfill.py (lines 189-232)",
"upsert_outcome": "scripts/paper_backfill.py (lines 83-173)"
}
}
