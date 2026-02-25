"""
Governance module for ChiseAI.

This module provides governance capabilities including:
- Memory deduplication engine
- Audit and compliance utilities
- Retrieval baseline metrics
- Feature flag management
- Task sentinel enforcement utilities
- Swarm health monitoring and predictive alerting (ST-GOV-008)
- Parallel execution optimization (ST-GOV-010)

Note: To avoid circular imports, submodules must be imported directly.
Do not add imports here that would cause import cycles.

Example:
    # Correct - import submodule directly
    from governance.memory import MemoryDeduplicationEngine
    from governance.audit import AuditSnapshot

    # Avoid - this may cause circular imports
    import governance  # then use governance.MemoryDeduplicationEngine
"""

# This module is intentionally minimal to prevent circular imports.
# Import submodules directly as needed.

__all__ = []
