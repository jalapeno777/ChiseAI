FROM python:3.11-slim

LABEL project=chiseai
LABEL service=grafana-watchdog

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 -s /bin/bash watchdog

# Set working directory
WORKDIR /app

# Copy requirements first for better layer caching
COPY infrastructure/grafana/watchdog/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy watchdog script
COPY scripts/grafana-watchdog.py .
RUN chmod +x grafana-watchdog.py

# Copy healthcheck script
COPY infrastructure/grafana/watchdog/healthcheck.py .
RUN chmod +x healthcheck.py

# Create dashboards directory
RUN mkdir -p /etc/grafana/provisioning/dashboards && \
    chown -R watchdog:watchdog /etc/grafana/provisioning

# Switch to non-root user
USER watchdog

# Environment defaults
# Use host.docker.internal:3001 for host Grafana, override via GRAFANA_URL env var for local container
ENV GRAFANA_URL=http://host.docker.internal:3001
ENV DASHBOARDS_PATH=/etc/grafana/provisioning/dashboards
ENV WATCHDOG_LOG_LEVEL=INFO
ENV WATCHDOG_DEBOUNCE_SECONDS=5
ENV PYTHONUNBUFFERED=1

# Health check - uses dynamic healthcheck script that reads GRAFANA_URL
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 /app/healthcheck.py

# Run watchdog
CMD ["python3", "grafana-watchdog.py"]
