# Model Registry API Documentation

REST API for ChiseAI Model Registry - versioning, storage, and retrieval of ML models.

## Overview

The Model Registry API provides HTTP endpoints for managing ML model versions with semantic versioning, metadata tracking, and rollback support.

## Base URL

```
/api/v1/models
```

## Authentication

Authentication is not implemented in this version. Future versions may include API key or token-based authentication.

## Endpoints

### Health Check

Check the health status of the model registry.

```http
GET /health
```

**Response:**

```json
{
  "status": "healthy",
  "registry_initialized": true,
  "timestamp": "2024-01-15T10:30:00"
}
```

### Register Model

Register a new model version.

```http
POST /api/v1/models
Content-Type: multipart/form-data
```

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `model_file` | file | Yes | Model file (pickle/joblib format) |
| `model_name` | string | Yes | Name of the model |
| `version` | string | Yes | Semantic version (e.g., "1.0.0") |
| `training_data` | string | Yes | Reference to training dataset |
| `hyperparameters` | string | No | JSON string of hyperparameters |
| `metrics` | string | No | JSON string of performance metrics |
| `tags` | string | No | JSON array of tags |

**Example Request:**

```bash
curl -X POST http://localhost:8000/api/v1/models \
  -F "model_file=@model.pkl" \
  -F "model_name=price_predictor" \
  -F "version=1.0.0" \
  -F "training_data=dataset_v1" \
  -F 'hyperparameters={"lr": 0.001, "epochs": 100}' \
  -F 'metrics={"accuracy": 0.95}' \
  -F 'tags=["production", "v1"]'
```

**Response (201 Created):**

```json
{
  "success": true,
  "message": "Model price_predictor@1.0.0 registered successfully",
  "model": {
    "version": "1.0.0",
    "created_at": "2024-01-15T10:30:00",
    "model_name": "price_predictor",
    "checksum": "abc123def456..."
  }
}
```

**Error Responses:**

- `400 Bad Request` - Invalid request (validation failed, invalid JSON)
- `409 Conflict` - Version already exists
- `500 Internal Server Error` - Server error
- `503 Service Unavailable` - Registry not initialized

### List Versions

List all versions of a model.

```http
GET /api/v1/models/{name}
```

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `name` | path | Yes | Model name |
| `limit` | query | No | Maximum versions to return (default: 100, max: 1000) |
| `offset` | query | No | Number of versions to skip (default: 0) |

**Example Request:**

```bash
curl http://localhost:8000/api/v1/models/price_predictor?limit=10
```

**Response (200 OK):**

```json
{
  "success": true,
  "model_name": "price_predictor",
  "versions": [
    {
      "version": "1.1.0",
      "created_at": "2024-01-15T12:00:00",
      "checksum": "abc123..."
    },
    {
      "version": "1.0.0",
      "created_at": "2024-01-15T10:30:00",
      "checksum": "def456..."
    }
  ],
  "count": 2
}
```

### Get Model

Get a specific version of a model.

```http
GET /api/v1/models/{name}/{version}
```

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `name` | path | Yes | Model name |
| `version` | path | Yes | Version string (e.g., "1.0.0") |

**Example Request:**

```bash
curl http://localhost:8000/api/v1/models/price_predictor/1.0.0
```

**Response (200 OK):**

```json
{
  "success": true,
  "model_name": "price_predictor",
  "version": "1.0.0",
  "metadata": {
    "model_name": "price_predictor",
    "version": "1.0.0",
    "created_at": "2024-01-15T10:30:00",
    "training_data": "dataset_v1",
    "hyperparameters": {"lr": 0.001, "epochs": 100},
    "metrics": {"accuracy": 0.95, "f1": 0.93},
    "tags": ["production", "v1"],
    "checksum": "abc123def456..."
  }
}
```

**Error Responses:**

- `404 Not Found` - Model or version not found
- `400 Bad Request` - Invalid version format

### Get Latest Model

Get the latest version of a model.

```http
GET /api/v1/models/{name}/latest
```

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `name` | path | Yes | Model name |

**Example Request:**

```bash
curl http://localhost:8000/api/v1/models/price_predictor/latest
```

**Response (200 OK):**

Same format as Get Model response.

**Error Responses:**

- `404 Not Found` - No versions exist for the model

### Rollback Model

Rollback to a previous model version.

```http
POST /api/v1/models/{name}/rollback?version={version}
```

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `name` | path | Yes | Model name |
| `version` | query | Yes | Version to rollback to |

**Example Request:**

```bash
curl -X POST "http://localhost:8000/api/v1/models/price_predictor/rollback?version=1.0.0"
```

**Response (200 OK):**

```json
{
  "success": true,
  "message": "Successfully rolled back price_predictor to version 1.0.0",
  "model_name": "price_predictor",
  "rolled_back_to": "1.0.0"
}
```

**Error Responses:**

- `404 Not Found` - Model or version not found
- `400 Bad Request` - Invalid version format
- `500 Internal Server Error` - Rollback operation failed

### Get Version History

Get detailed version history for a model.

```http
GET /api/v1/models/{name}/history
```

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `name` | path | Yes | Model name |

**Example Request:**

```bash
curl http://localhost:8000/api/v1/models/price_predictor/history
```

**Response (200 OK):**

```json
{
  "success": true,
  "model_name": "price_predictor",
  "history": [
    {
      "version": "1.1.0",
      "created_at": "2024-01-15T12:00:00",
      "model_name": "price_predictor",
      "metrics": {"accuracy": 0.96},
      "tags": ["production"],
      "training_data": "dataset_v2",
      "checksum": "abc123..."
    },
    {
      "version": "1.0.0",
      "created_at": "2024-01-15T10:30:00",
      "model_name": "price_predictor",
      "metrics": {"accuracy": 0.95},
      "tags": ["production"],
      "training_data": "dataset_v1",
      "checksum": "def456..."
    }
  ]
}
```

### Compare Versions

Compare two model versions.

```http
GET /api/v1/models/{name}/compare?version1={v1}&version2={v2}
```

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `name` | path | Yes | Model name |
| `version1` | query | Yes | First version to compare |
| `version2` | query | Yes | Second version to compare |

**Example Request:**

```bash
curl "http://localhost:8000/api/v1/models/price_predictor/compare?version1=1.0.0&version2=1.1.0"
```

**Response (200 OK):**

```json
{
  "success": true,
  "model_name": "price_predictor",
  "version1": {
    "version": "1.0.0",
    "created_at": "2024-01-15T10:30:00",
    "metrics": {"accuracy": 0.95, "f1": 0.93}
  },
  "version2": {
    "version": "1.1.0",
    "created_at": "2024-01-15T12:00:00",
    "metrics": {"accuracy": 0.96, "f1": 0.94}
  },
  "metric_diffs": {
    "accuracy": 0.01,
    "f1": 0.01
  }
}
```

**Error Responses:**

- `404 Not Found` - Model or version not found

### Delete Version

Delete a specific model version.

```http
DELETE /api/v1/models/{name}/{version}
```

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `name` | path | Yes | Model name |
| `version` | path | Yes | Version to delete |

**Warning:** This permanently deletes the model files. Cannot delete the current "latest" version.

**Example Request:**

```bash
curl -X DELETE http://localhost:8000/api/v1/models/price_predictor/1.0.0
```

**Response:**

- `204 No Content` - Successfully deleted

**Error Responses:**

- `404 Not Found` - Model or version not found
- `400 Bad Request` - Cannot delete the current "latest" version

## Error Responses

All error responses follow this format:

```json
{
  "success": false,
  "error": "Error summary",
  "detail": "Detailed error message"
}
```

### HTTP Status Codes

| Code | Description |
|------|-------------|
| 200 | Success |
| 201 | Created |
| 204 | No Content |
| 400 | Bad Request |
| 404 | Not Found |
| 409 | Conflict |
| 422 | Validation Error |
| 500 | Internal Server Error |
| 503 | Service Unavailable |

## Rate Limiting

Rate limiting is not implemented in this version.

## OpenAPI/Swagger

When the API is running, you can access the interactive API documentation at:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Python Client Example

```python
import requests

# Register a model
with open("model.pkl", "rb") as f:
    response = requests.post(
        "http://localhost:8000/api/v1/models",
        files={"model_file": f},
        data={
            "model_name": "price_predictor",
            "version": "1.0.0",
            "training_data": "dataset_v1",
            "hyperparameters": '{"lr": 0.001}',
            "metrics": '{"accuracy": 0.95}',
        }
    )
print(response.json())

# Get latest model
response = requests.get("http://localhost:8000/api/v1/models/price_predictor/latest")
print(response.json())

# List versions
response = requests.get("http://localhost:8000/api/v1/models/price_predictor")
print(response.json())

# Rollback
response = requests.post(
    "http://localhost:8000/api/v1/models/price_predictor/rollback?version=1.0.0"
)
print(response.json())
```

## CLI Tool

A command-line interface is also available:

```bash
# Register a model
chise-model register price_predictor ./model.pkl --version 1.0.0 --training-data dataset_v1

# List versions
chise-model list price_predictor

# Get model info
chise-model get price_predictor --version 1.0.0

# Rollback
chise-model rollback price_predictor 1.0.0

# Check health
chise-model health
```

See the CLI documentation for more details.
