"""Shared fixtures for CI tests."""

import pytest
from scripts.ci.pipeline import (
    CIPipeline,
    LintStage,
    PipelineConfig,
    SecurityStage,
    TestStage,
)


@pytest.fixture
def pipeline_config():
    """Basic pipeline configuration."""
    return PipelineConfig(
        project_name="test-project",
        python_version="3.13",
        min_coverage=80.0,
        timeout_minutes=30,
    )


@pytest.fixture
def ci_pipeline(pipeline_config):
    """Basic CI pipeline instance."""
    return CIPipeline(pipeline_config)


@pytest.fixture
def lint_stage(pipeline_config):
    """Lint stage instance."""
    return LintStage(pipeline_config)


@pytest.fixture
def test_stage(pipeline_config):
    """Test stage instance."""
    return TestStage(pipeline_config)


@pytest.fixture
def security_stage(pipeline_config):
    """Security stage instance."""
    return SecurityStage(pipeline_config)


@pytest.fixture
def sample_woodpecker_config():
    """Sample Woodpecker CI configuration."""
    return """
when:
  - event: push
    branch: [main]

steps:
  lint:
    image: python:3.13
    commands:
      - pip install black ruff
      - black --check src/
"""
