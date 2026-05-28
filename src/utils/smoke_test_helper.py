"""Smoke test helper - validates CI pipeline end-to-end."""


def ci_pipeline_greeting(name: str) -> str:
    """Return a greeting string for CI pipeline validation.

    Args:
        name: The name to greet.

    Returns:
        A greeting string.

    Raises:
        ValueError: If name is empty.
    """
    if not name:
        raise ValueError("Name cannot be empty")
    return f"Hello, {name}! CI pipeline is working."
