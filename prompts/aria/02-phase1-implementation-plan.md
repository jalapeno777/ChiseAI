You are Aria. Using the approved governance decisions and the implementation scaffold, produce a Phase 1 file-by-file implementation plan for the current repo.

Constraints:
- respect the existing architecture
- prefer modifying existing modules over creating redundant systems
- preserve current Redis/Qdrant/tempmemory/reflection infrastructure
- add only the thinnest layers needed for governance, auditability, notifications, and deterministic context assembly

Required output:
1. exact files to create
2. exact files to modify
3. functions/classes to add or change
4. feature flags required
5. tests to add
6. migration and rollback notes
7. anything that must be deferred to Phase 2+
