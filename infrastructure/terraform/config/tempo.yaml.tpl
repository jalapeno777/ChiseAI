# Grafana Tempo Configuration
# Story: TEMPO-2026-001 - Distributed Tracing Backend
# Generated from tempo.yaml.tpl - DO NOT EDIT DIRECTLY

server:
  http_listen_port: 3200
  log_level: ${log_level}

distributor:
  receivers:
    otlp:
      protocols:
        grpc:
          endpoint: 0.0.0.0:4317
        http:
          endpoint: 0.0.0.0:4318

ingester:
  # Block configuration for trace ingestion
  # max_block_duration: How long to wait before cutting a block (5 minutes)
  # max_block_bytes: Maximum size of a block before cutting (1GB)
  # trace_idle_period: How long to wait before flushing an idle trace (10 seconds)
  max_block_duration: 5m
  max_block_bytes: 1000000000
  trace_idle_period: 10s

compactor:
  compaction:
    # block_retention: How long to retain trace blocks before deletion
    # Set to ${retention_hours}h (${retention_hours} hours = ${retention_hours/24} days)
    # This ensures trace data is automatically purged after the retention period
    block_retention: ${retention_hours}h
    # Compaction window controls how often compaction runs
    compaction_window: 1h
    # Maximum compaction level - higher levels mean more compacted data
    max_compaction_level: 3

storage:
  trace:
    backend: local
    local:
      path: /tmp/tempo/traces
    wal:
      path: /tmp/tempo/wal

overrides:
  defaults:
    global:
      # Rate limiting configuration
      # ingestion_rate_limit_bytes: Maximum bytes per second per tenant (20MB/s)
      ingestion_rate_limit_bytes: 20000000
      # max_traces_per_user: Maximum number of active traces per user (100K)
      max_traces_per_user: 100000
      # max_bytes_per_trace: Maximum size of a single trace (5MB)
      # Prevents abuse from excessively large traces
      max_bytes_per_trace: 5000000
      # max_search_bytes_per_trace: Maximum bytes for search results per trace
      # Set to 0 to disable search limits (search all traces)
      max_search_bytes_per_trace: 0
      # max_bytes_per_tag_values_query: Maximum response size for tag values queries
      # Prevents memory exhaustion from large tag value queries (100MB)
      max_bytes_per_tag_values_query: 104857600
