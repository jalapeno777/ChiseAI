# Model Registry Architecture

## Overview

The ChiseAI Model Registry provides a production-hardened system for versioning, storing, and retrieving ML models with comprehensive metadata tracking and rollback support.

## Architecture Components

```
┌─────────────────────────────────────────────────────────────────┐
│                      ModelRegistry                              │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Validation Layer (SchemaValidator, MetricsValidator)   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                         │                                       │
│                         ▼                                       │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              StorageBackend (Abstract)                  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                         │                                       │
│           ┌─────────────┴─────────────┐                       │
│           ▼                           ▼                       │
│  ┌─────────────────┐      ┌─────────────────┐               │
│  │ FilesystemBackend│      │   S3Backend     │               │
│  │  (Production)   │      │  (Interface)    │               │
│  └─────────────────┘      └─────────────────┘               │
└─────────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. ModelRegistry

The main entry point for model management operations.

**Key Features:**
- Semantic versioning (MAJOR.MINOR.PATCH)
- Model validation on registration
- Rollback support (< 5 seconds)
- Version comparison and history

**Usage:**
```python
from ml.models import ModelRegistry, ModelRegistryFactory

# Create production registry with validation
registry = ModelRegistryFactory.create_production_registry(
    base_path="models",
    min_accuracy=0.8,
    required_attributes=["predict", "evaluate"]
)

# Register a new model version
version = registry.create_new_version(
    model=my_model,
    model_name="price_predictor",
    training_data="dataset_v1",
    hyperparameters={"lr": 0.001},
    metrics={"accuracy": 0.95},
    bump="minor"
)
```

### 2. FilesystemBackend

Production-ready filesystem storage with atomic operations and integrity checking.

**Storage Structure:**
```
{base_path}/
├── {model_name}/
│   ├── {version}/
│   │   ├── model.pkl          # Serialized model artifact
│   │   ├── metadata.json      # Model metadata with checksum
│   │   └── checksum.sha256    # Separate checksum file
│   └── latest.json            # Pointer to latest version
```

**Production Features:**
- **Atomic Writes**: Uses temp files and rename for atomicity
- **Integrity Checking**: SHA256 checksums for all model artifacts
- **Model Caching**: LRU cache for frequently accessed models
- **Thread Safety**: File-level locking for concurrent access
- **Metrics Collection**: Hooks for observability

### 3. Model Validation

Pluggable validation system for model registration.

**Validators:**
- `SchemaValidator`: Checks required model attributes
- `MetricsValidator`: Validates performance thresholds
- `CompositeValidator`: Combines multiple validators

**Example:**
```python
from ml.models import SchemaValidator, MetricsValidator, CompositeValidator

validator = CompositeValidator([
    SchemaValidator(required_attributes=["predict", "evaluate"]),
    MetricsValidator(min_accuracy=0.85, min_f1=0.80)
])

registry = ModelRegistry(validator=validator)
```

### 4. Exception Hierarchy

```
ModelRegistryError (base)
├── ModelNotFoundError
├── ModelVersionExistsError
├── ModelValidationError
├── ModelIntegrityError
└── StorageBackendError
```

## Data Models

### ModelMetadata

```python
@dataclass(frozen=True)
class ModelMetadata:
    model_name: str              # Model identifier
    version: str                 # Semantic version (MAJOR.MINOR.PATCH)
    created_at: datetime         # UTC timestamp
    training_data: str           # Reference to training dataset
    hyperparameters: dict        # Training hyperparameters
    metrics: dict                # Performance metrics
    tags: list                   # Categorization tags
    checksum: str | None         # SHA256 checksum (auto-generated)
```

### ModelVersion

```python
@dataclass(frozen=True)
class ModelVersion:
    model_name: str
    version: str
    created_at: datetime
    metadata_path: str
    model_path: str
    checksum: str | None
```

## Versioning Strategy

### Semantic Versioning

- **MAJOR**: Breaking changes (architecture, feature set)
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes (backward compatible)

### Version Bumping

```python
# Auto-increment version
registry.create_new_version(
    model=model,
    model_name="predictor",
    training_data="dataset_v2",
    hyperparameters={"lr": 0.001},
    metrics={"accuracy": 0.95},
    bump="minor"  # or "major", "patch"
)
```

## Rollback Mechanism

Rollback updates the "latest" pointer without modifying model files:

```python
# Rollback to previous version (< 5 seconds)
registry.rollback("predictor", "1.0.0")

# Verify rollback
model, metadata = registry.get_latest("predictor")
assert metadata.version == "1.0.0"
```

## Integrity Verification

All models include SHA256 checksums for integrity verification:

```python
# Verify model integrity
is_valid = registry.verify_integrity("predictor", "1.0.0")
assert is_valid is True

# Corrupted models raise ModelIntegrityError
try:
    registry.load_model("predictor", "corrupted_version")
except ModelIntegrityError:
    print("Model integrity check failed!")
```

## Caching Strategy

The FilesystemBackend includes an LRU cache for frequently accessed models:

```python
backend = FilesystemBackend(
    base_path="models",
    enable_cache=True,
    cache_size=10,              # Max 10 models in cache
    cache_ttl_seconds=3600      # 1 hour TTL
)

# Check cache stats
stats = backend.get_cache_stats()
print(f"Cache size: {stats['size']}/{stats['max_size']}")
```

## Metrics Collection

Implement the `MetricsCollector` protocol for observability:

```python
from ml.models.model_storage import MetricsCollector

class PrometheusMetricsCollector(MetricsCollector):
    def record_save(self, model_name: str, version: str, duration_ms: float):
        # Record to Prometheus
        pass

    def record_load(self, model_name: str, version: str, duration_ms: float):
        # Record to Prometheus
        pass

    def record_cache_hit(self, model_name: str, version: str):
        # Record cache hit
        pass

    def record_cache_miss(self, model_name: str, version: str):
        # Record cache miss
        pass

backend = FilesystemBackend(
    metrics_collector=PrometheusMetricsCollector()
)
```

## S3 Backend (Future)

The S3Backend interface is defined for future cloud storage support:

```python
from ml.models import ModelRegistryFactory

registry = ModelRegistryFactory.create_s3_registry(
    bucket="chiseai-models",
    prefix="production",
    region="us-east-1"
)
```

Note: S3Backend is currently an interface placeholder. Use FilesystemBackend for production.

## Security Considerations

1. **Immutable Versions**: Once registered, model versions cannot be modified
2. **Integrity Checking**: SHA256 checksums prevent tampering
3. **Atomic Operations**: Prevents partial writes during concurrent access
4. **Access Control**: Filesystem permissions control access to model artifacts

## Performance Characteristics

| Operation | Time Complexity | Notes |
|-----------|----------------|-------|
| Register | O(1) | Atomic write with checksum |
| Load | O(1) | Cached after first access |
| List Versions | O(n) | n = number of versions |
| Rollback | O(1) | Pointer update only |
| Integrity Check | O(m) | m = model size |

## Error Handling

All operations raise specific exceptions:

```python
from ml.models import (
    ModelNotFoundError,
    ModelVersionExistsError,
    ModelValidationError,
    ModelIntegrityError,
    StorageBackendError,
)

try:
    model, metadata = registry.get_model("predictor", "1.0.0")
except ModelNotFoundError:
    print("Model not found")
except ModelIntegrityError:
    print("Model corrupted")
except StorageBackendError:
    print("Storage operation failed")
```

## Best Practices

1. **Always use semantic versioning** for model releases
2. **Validate models** before registration using validators
3. **Verify integrity** periodically for production models
4. **Use caching** for high-throughput scenarios
5. **Monitor metrics** for performance and cache hit rates
6. **Never delete** the latest version without rollback
7. **Tag models** for easy categorization and filtering

## Related Documentation

- [Model Registry Operations Runbook](../runbooks/model-registry-operations.md)
- [API Reference](../api/model-registry.md)
