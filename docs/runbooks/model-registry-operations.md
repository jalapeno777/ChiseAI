# Model Registry Operations Runbook

## Overview

This runbook provides operational procedures for the ChiseAI Model Registry.

## Table of Contents

1. [Common Operations](#common-operations)
2. [Troubleshooting](#troubleshooting)
3. [Monitoring](#monitoring)
4. [Emergency Procedures](#emergency-procedures)
5. [Maintenance](#maintenance)

## Common Operations

### Register a New Model

```python
from ml.models import ModelRegistryFactory
from datetime import datetime, timezone

# Create registry
registry = ModelRegistryFactory.create_filesystem_registry("models")

# Register with explicit version
from ml.models import ModelMetadata

metadata = ModelMetadata(
    model_name="price_predictor",
    version="1.0.0",
    created_at=datetime.now(timezone.utc),
    training_data="s3://datasets/training/v1/",
    hyperparameters={"lr": 0.001, "epochs": 100},
    metrics={"accuracy": 0.95, "f1": 0.93},
    tags=["production", "v1"],
)

version = registry.register_model(model, metadata)
print(f"Registered: {version.model_name}@{version.version}")
```

### Register with Auto-Versioning

```python
# Auto-increment version based on bump type
version = registry.create_new_version(
    model=model,
    model_name="price_predictor",
    training_data="dataset_v2",
    hyperparameters={"lr": 0.001},
    metrics={"accuracy": 0.96},
    tags=["production"],
    bump="minor",  # or "major", "patch"
)
```

### Retrieve a Model

```python
# Get latest version
model, metadata = registry.get_latest("price_predictor")

# Get specific version
model, metadata = registry.get_model("price_predictor", "1.0.0")

# Get by "latest" tag
model, metadata = registry.get_model("price_predictor", "latest")
```

**Expected Output:**
```
Model loaded: price_predictor@1.0.0
Created: 2026-02-20T10:30:00Z
Metrics: {'accuracy': 0.95, 'f1': 0.93}
```

### Rollback to Previous Version

```python
import time

# Time the rollback (should be < 5 seconds)
start = time.time()
registry.rollback("price_predictor", "1.0.0")
elapsed = time.time() - start

print(f"Rollback completed in {elapsed:.2f} seconds")

# Verify rollback
model, metadata = registry.get_latest("price_predictor")
assert metadata.version == "1.0.0"
```

### List Model Versions

```python
# List all versions
versions = registry.list_versions("price_predictor")
for v in versions:
    print(f"{v.version}: {v.created_at}")

# Get version history with metadata
history = registry.get_version_history("price_predictor")
for h in history:
    print(f"{h['version']}: accuracy={h['metrics']['accuracy']}")
```

### Compare Versions

```python
comparison = registry.compare_versions(
    "price_predictor",
    version1="1.0.0",
    version2="1.1.0"
)

print(f"Accuracy diff: {comparison['metric_diffs']['accuracy']}")
```

### Delete a Version

⚠️ **Warning**: Deletion is permanent. Prefer rollback for reverting.

```python
# First rollback to a different version
registry.rollback("price_predictor", "1.0.0")

# Then delete the old version
registry.delete_version("price_predictor", "1.1.0")
```

### Verify Model Integrity

```python
# Check model integrity
is_valid = registry.verify_integrity("price_predictor", "1.0.0")

if is_valid:
    print("Model integrity verified")
else:
    print("Model may be corrupted!")
```

## Troubleshooting

### ModelNotFoundError

**Symptom**: `ModelNotFoundError: Model version not found: model@version`

**Resolution**:
1. Check model name spelling
2. List available versions: `registry.list_versions("model_name")`
3. Check if model was deleted

```python
# Debug: List all versions
versions = registry.list_versions("model_name")
print(f"Available versions: {[v.version for v in versions]}")
```

### ModelVersionExistsError

**Symptom**: `ModelVersionExistsError: Version X.Y.Z already exists`

**Resolution**:
1. Use auto-versioning with `create_new_version()`
2. Choose a different version number
3. Delete the existing version first (if appropriate)

```python
# Use auto-versioning to avoid conflicts
version = registry.create_new_version(
    model=model,
    model_name="model_name",
    training_data="...",
    hyperparameters={...},
    metrics={...},
    bump="patch",  # Auto-increments version
)
```

### ModelIntegrityError

**Symptom**: `ModelIntegrityError: Checksum verification failed`

**Resolution**:
1. Do not use the corrupted model
2. Restore from backup if available
3. Re-train and register a new version

```python
# Check which versions are affected
for version in registry.list_versions("model_name"):
    try:
        registry.verify_integrity("model_name", version.version)
        print(f"{version.version}: OK")
    except ModelIntegrityError:
        print(f"{version.version}: CORRUPTED")
```

### ModelValidationError

**Symptom**: `ModelValidationError: Metric 'accuracy' below threshold`

**Resolution**:
1. Check model performance metrics
2. Adjust validation thresholds if needed
3. Re-train model to meet requirements

```python
# Create registry without strict validation
registry = ModelRegistryFactory.create_filesystem_registry(
    base_path="models",
    # Don't set min_accuracy to bypass validation
)
```

### StorageBackendError

**Symptom**: `StorageBackendError: Failed to save/load model`

**Resolution**:
1. Check disk space: `df -h`
2. Check permissions: `ls -la models/`
3. Verify filesystem is not read-only
4. Check for network issues (if using remote storage)

```bash
# Check disk space
df -h

# Check permissions
ls -la models/

# Check filesystem
mount | grep models
```

## Monitoring

### Cache Statistics

```python
# Get cache stats
stats = backend.get_cache_stats()

if stats:
    print(f"Cache size: {stats['size']}/{stats['max_size']}")
    print(f"Entries: {len(stats['entries'])}")
    for entry in stats['entries']:
        print(f"  {entry['key']}: {entry['access_count']} accesses")
```

### Metrics Collection

```python
from ml.models.model_storage import MetricsCollector

class LoggingMetricsCollector(MetricsCollector):
    def record_save(self, model_name: str, version: str, duration_ms: float):
        print(f"SAVE: {model_name}@{version} in {duration_ms:.2f}ms")

    def record_load(self, model_name: str, version: str, duration_ms: float):
        print(f"LOAD: {model_name}@{version} in {duration_ms:.2f}ms")

    def record_cache_hit(self, model_name: str, version: str):
        print(f"CACHE HIT: {model_name}@{version}")

    def record_cache_miss(self, model_name: str, version: str):
        print(f"CACHE MISS: {model_name}@{version}")

backend = FilesystemBackend(
    metrics_collector=LoggingMetricsCollector()
)
```

### Health Check

```python
def model_registry_health_check(registry, model_name: str) -> dict:
    """Perform health check on model registry."""
    results = {
        "model_name": model_name,
        "status": "healthy",
        "issues": [],
    }

    # Check if model exists
    versions = registry.list_versions(model_name)
    if not versions:
        results["status"] = "warning"
        results["issues"].append("No versions found")
        return results

    results["version_count"] = len(versions)

    # Check latest version
    try:
        latest = registry.backend.get_latest_version(model_name)
        results["latest_version"] = latest.version if latest else None
    except Exception as e:
        results["status"] = "error"
        results["issues"].append(f"Failed to get latest: {e}")

    # Verify integrity of all versions
    corrupted = []
    for version in versions:
        try:
            registry.verify_integrity(model_name, version.version)
        except Exception:
            corrupted.append(version.version)

    if corrupted:
        results["status"] = "critical"
        results["issues"].append(f"Corrupted versions: {corrupted}")

    return results

# Run health check
health = model_registry_health_check(registry, "price_predictor")
print(f"Status: {health['status']}")
for issue in health['issues']:
    print(f"  Issue: {issue}")
```

## Emergency Procedures

### Emergency Rollback

When a deployed model is causing issues:

```python
import time

def emergency_rollback(model_name: str, target_version: str):
    """Emergency rollback procedure."""
    print(f"EMERGENCY ROLLBACK: {model_name} -> {target_version}")

    # Verify target version exists and is valid
    try:
        model, metadata = registry.get_model(model_name, target_version)
        print(f"✓ Target version {target_version} is valid")
    except Exception as e:
        print(f"✗ Target version invalid: {e}")
        return False

    # Perform rollback
    start = time.time()
    try:
        registry.rollback(model_name, target_version)
        elapsed = time.time() - start
        print(f"✓ Rollback completed in {elapsed:.2f}s")
    except Exception as e:
        print(f"✗ Rollback failed: {e}")
        return False

    # Verify rollback
    model, metadata = registry.get_latest(model_name)
    if metadata.version == target_version:
        print(f"✓ Verified: latest is now {target_version}")
        return True
    else:
        print(f"✗ Verification failed: latest is {metadata.version}")
        return False

# Execute emergency rollback
success = emergency_rollback("price_predictor", "1.0.0")
```

### Recover from Corruption

If model files are corrupted:

```python
def recover_from_corruption(model_name: str):
    """Recovery procedure for corrupted models."""
    versions = registry.list_versions(model_name)

    # Find last known good version
    good_version = None
    for version in versions:
        try:
            registry.verify_integrity(model_name, version.version)
            good_version = version.version
            print(f"✓ Version {version.version} is valid")
            break
        except Exception:
            print(f"✗ Version {version.version} is corrupted")

    if good_version:
        print(f"Rolling back to last good version: {good_version}")
        registry.rollback(model_name, good_version)
    else:
        print("No valid versions found! Manual intervention required.")

recover_from_corruption("price_predictor")
```

### Clear Cache

If cache is causing issues:

```python
# Clear the cache
backend.clear_cache()
print("Cache cleared")

# Verify
stats = backend.get_cache_stats()
assert stats["size"] == 0
```

## Maintenance

### Cleanup Old Versions

```python
def cleanup_old_versions(
    registry,
    model_name: str,
    keep_latest: int = 5
):
    """Remove old versions, keeping only the latest N."""
    versions = registry.list_versions(model_name)

    if len(versions) <= keep_latest:
        print(f"Nothing to cleanup ({len(versions)} versions)")
        return

    # Get current latest
    latest = registry.backend.get_latest_version(model_name)
    latest_version = latest.version if latest else None

    # Delete old versions (except latest)
    to_delete = versions[keep_latest:]
    for version in to_delete:
        if version.version == latest_version:
            continue  # Never delete latest

        try:
            registry.delete_version(model_name, version.version)
            print(f"Deleted {version.version}")
        except Exception as e:
            print(f"Failed to delete {version.version}: {e}")

cleanup_old_versions(registry, "price_predictor", keep_latest=5)
```

### Backup Models

```python
import shutil
from pathlib import Path

def backup_models(source_dir: str, backup_dir: str):
    """Backup all models to another location."""
    source = Path(source_dir)
    backup = Path(backup_dir)

    # Create backup directory
    backup.mkdir(parents=True, exist_ok=True)

    # Copy all models
    for model_dir in source.iterdir():
        if model_dir.is_dir():
            dest = backup / model_dir.name
            shutil.copytree(model_dir, dest, dirs_exist_ok=True)
            print(f"Backed up: {model_dir.name}")

    print(f"Backup completed: {backup_dir}")

backup_models("models", "models_backup")
```

### Verify All Models

```python
def verify_all_models(registry):
    """Verify integrity of all models in registry."""
    base_path = Path(registry.backend.base_path)

    results = {
        "total": 0,
        "valid": 0,
        "corrupted": 0,
        "errors": [],
    }

    for model_dir in base_path.iterdir():
        if not model_dir.is_dir():
            continue

        model_name = model_dir.name
        versions = registry.list_versions(model_name)

        for version in versions:
            results["total"] += 1
            try:
                registry.verify_integrity(model_name, version.version)
                results["valid"] += 1
            except Exception as e:
                results["corrupted"] += 1
                results["errors"].append({
                    "model": model_name,
                    "version": version.version,
                    "error": str(e),
                })

    print(f"Verification complete:")
    print(f"  Total: {results['total']}")
    print(f"  Valid: {results['valid']}")
    print(f"  Corrupted: {results['corrupted']}")

    if results['errors']:
        print("\nErrors:")
        for err in results['errors']:
            print(f"  {err['model']}@{err['version']}: {err['error']}")

    return results

verify_all_models(registry)
```

## Best Practices

1. **Always validate models** before registration
2. **Use semantic versioning** consistently
3. **Tag models** for easy categorization
4. **Monitor cache hit rates** and adjust size if needed
5. **Regular integrity checks** for production models
6. **Keep backups** of critical models
7. **Never delete** the latest version without rollback
8. **Document model metadata** thoroughly

## Support

For issues not covered in this runbook:

1. Check the [Architecture Documentation](../architecture/model-registry.md)
2. Review test cases: `tests/test_ml/test_model_registry.py`
3. Contact the ML Platform team
