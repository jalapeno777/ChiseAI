# Import Path Hygiene Standards

This document defines the import path conventions and hygiene standards for the ChiseAI codebase to prevent circular imports, test leakage, and coverage issues.

## Package Structure Principles

### Root Package Isolation

Root packages should **never** import from `tests.*`. This ensures:
- Production code is deployable without test dependencies
- Test infrastructure can evolve without breaking production
- Clear separation of concerns

### Test Isolation

The `tests/` directory should be isolated and only test **public APIs**:
- Tests should import from production packages, not internal test utilities
- Test fixtures should be self-contained within `tests/` or shared via `conftest.py`
- Avoid cross-test imports that create hidden dependencies

### Circular Import Prevention

Avoid circular imports between `src/` and `tests/`:
- `src/` should never import from `tests/`
- If a test utility is needed in production, move it to `src/`
- Use lazy imports or dependency injection to break cycles

## Coverage Package Pattern

### Compatibility Shim

The `coverage/` package at the repository root is a **compatibility shim** designed to:
- Provide a stable import path for coverage tooling
- Re-export from its own submodules for backward compatibility

### Correct Pattern

```python
# coverage/__init__.py - CORRECT
from coverage.collector import CoverageCollector
from coverage.reporter import CoverageReporter
```

### Incorrect Pattern

```python
# coverage/__init__.py - WRONG
from tests.coverage import *  # Never import from tests!
```

### Why This Matters

- The `tests/coverage/` directory contains the **actual test infrastructure**
- Production `coverage/` should be independent of test code
- Mixing these causes import errors in production environments

## Config Package Pattern

### Compatibility Shim

The `config/` package is a compatibility shim for `src.config`:
- Provides backward compatibility for legacy import paths
- Should re-export from `src.config` using absolute imports

### Absolute Import Rule

Always use **absolute imports** within config packages:

```python
# config/__init__.py - CORRECT
from src.config import Settings, get_settings

# config/__init__.py - WRONG (relative import)
from ..src.config import Settings  # Fragile and breaks tools
```

### Module Structure

```
config/
  __init__.py     # Re-exports from src.config
  settings.py     # Compatibility module (optional)
```

## Validation Checklist

Before committing changes to package structure, verify:

### 1. Basic Import Test
```bash
python3 -c "from package import Module"
```
This should work without errors for all production packages.

### 2. Pytest Collection Test
```bash
pytest --collect-only
```
Should complete without import errors. Any import errors here indicate:
- Missing `__init__.py` files
- Circular imports
- Incorrect `sys.path` assumptions

### 3. Circular Import Detection
```bash
python3 -c "import package; import tests.package"
```
If this fails with circular import errors, check for:
- Production code importing from tests
- Mutual imports between modules

### 4. Coverage Tool Compatibility
```bash
python3 -m coverage run -m pytest tests/
```
Coverage should be able to trace all imports without errors.

## Common Anti-Patterns to Avoid

| Anti-Pattern | Problem | Solution |
|-------------|---------|----------|
| `from tests.xxx import yyy` in src/ | Production depends on tests | Move utility to src/ |
| Relative imports in shims | Fragile path assumptions | Use absolute imports |
| `sys.path` manipulation | Hidden dependencies | Fix package structure |
| Importing `conftest.py` directly | Test coupling | Use pytest fixtures |

## Related Documentation

- [Testing Patterns](../skills/chiseai-testing-patterns/) - Test structure and coverage requirements
- [Python Quality](../.opencode/skills/python-quality/) - Code quality standards
- [Validation Registry](../validation/validation-registry.yaml) - CI validation gates
