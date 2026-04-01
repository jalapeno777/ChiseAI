# Implementation Notes

## Why this is an evolution, not a replacement
The current system already has:
- Redis-backed operational memory
- Qdrant-backed semantic memory
- file-based tempmemories
- reflection loops
- belief storage
- retrieval evaluation
- Discord notification code

The missing pieces are mostly coordination, governance, testing, and deterministic assembly.

## Primary gaps this scaffold addresses
- no single machine-readable persona contract
- no persona consistency regression suite
- no immutable belief mutation audit event model
- incomplete notification event coverage
- no final deterministic context assembly module
- consolidation scheduler not safely rolled out
- no lesson effectiveness loop

## Implementation principle
Add thin orchestration layers before rewriting low-level storage.

## Recommended placement
If equivalent files already exist in your repo, merge these concepts into the existing modules instead of creating parallel systems.
