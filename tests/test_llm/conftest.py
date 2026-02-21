"""
Pytest configuration for test_llm module.
"""


def pytest_addoption(parser):
    """Add custom pytest option for integration tests."""
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Run integration tests against live API",
    )
