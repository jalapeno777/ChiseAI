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
  max_block_duration: 5m
  max_block_bytes: 1000000000
  trace_idle_period: 10s

compactor:
  compaction:
    block_retention: ${retention_hours}h

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
      ingestion_rate_limit_bytes: 20000000
      max_traces_per_user: 100000
      max_bytes_per_trace: 5000000
