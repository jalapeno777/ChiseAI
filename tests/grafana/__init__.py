"""Grafana Tests.

This directory contains tests for Grafana dashboard validation.
"""

# Running Tests
#
# ```bash
# # Run all Grafana tests
# pytest tests/grafana/ -v
#
# # Run specific test file
# pytest tests/grafana/test_dashboards.py -v
#
# # Run with coverage
# pytest tests/grafana/ --cov=tests/grafana --cov-report=html
# ```
#
# Test Coverage
#
# - **Dashboard Schema Validation**: Verify JSON structure and required fields
# - **Panel Configuration**: Check required panels exist with correct settings
# - **Variable Configuration**: Validate template variables
# - **Threshold Configuration**: Verify color-coded thresholds
# - **Query Validation**: Ensure InfluxDB queries reference correct measurements
# - **Terraform Configuration**: Validate IaC resources
