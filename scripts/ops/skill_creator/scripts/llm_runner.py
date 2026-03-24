#!/usr/bin/env python3
"""Shared LLM runner utility for calling opencode and claude backends.

Provides a unified interface for calling LLM backends via subprocess,
with proper error handling, timeout management, and cleanup.
"""

import contextlib
import os
import subprocess
import tempfile
from typing import Literal

Backend = Literal["opencode", "claude"]


def _call_claude(prompt: str, model: str | None, timeout: int = 300) -> str:
    """Run `claude -p` with the prompt on stdin and return the text response.

    Prompt goes over stdin (not argv) because it can easily exceed comfortable
    argv length for long prompts.

    Args:
        prompt: The prompt text to send to Claude
        model: Optional model name to use
        timeout: Maximum time to wait for response in seconds

    Returns:
        The text response from Claude

    Raises:
        RuntimeError: If claude -p exits with non-zero status
        subprocess.TimeoutExpired: If the command times out
    """
    cmd = ["claude", "-p", "--output-format", "text"]
    if model:
        cmd.extend(["--model", model])

    # Remove CLAUDECODE env var to allow nesting claude -p inside a
    # Claude Code session. The guard is for interactive terminal conflicts;
    # programmatic subprocess usage is safe.
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    result = subprocess.run(
        cmd,
        input=prompt,
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"claude -p exited {result.returncode}\nstderr: {result.stderr}"
        )
    return result.stdout


def _call_opencode(prompt: str, timeout: int = 300) -> str:
    """Run `opencode run --agent Aria --prompt-file <file>` and return text response.

    Writes the prompt to a temporary file and passes it to opencode via
    --prompt-file to avoid command line length limitations.

    Args:
        prompt: The prompt text to send to Opencode
        timeout: Maximum time to wait for response in seconds

    Returns:
        The text response from Opencode

    Raises:
        RuntimeError: If opencode run exits with non-zero status
        subprocess.TimeoutExpired: If the command times out
    """
    prompt_file = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(prompt)
            prompt_file = f.name

        cmd = ["opencode", "run", "--agent", "Aria", "--prompt-file", prompt_file]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"opencode run exited {result.returncode}\nstderr: {result.stderr}"
            )
        return result.stdout
    finally:
        # Clean up temp file
        if prompt_file:
            with contextlib.suppress(OSError):
                os.unlink(prompt_file)


def call_llm(
    prompt: str,
    backend: Backend = "opencode",
    model: str | None = None,
    timeout: int = 300,
) -> str:
    """Call an LLM backend and return the text response.

    This is the main entry point for calling LLM backends. It dispatches
    to the appropriate backend implementation based on the backend parameter.

    Args:
        prompt: The prompt text to send to the LLM
        backend: Which backend to use ('opencode' or 'claude')
        model: Model name (only used by claude backend)
        timeout: Maximum time to wait for response in seconds

    Returns:
        The LLM response text

    Raises:
        ValueError: If an unknown backend is specified
        RuntimeError: If the backend command fails
        subprocess.TimeoutExpired: If the command times out

    Example:
        >>> response = call_llm("Hello, world!", backend="opencode")
        >>> response = call_llm("Hello, world!", backend="claude", model="claude-3-5-sonnet-20241022")
    """
    if backend == "opencode":
        return _call_opencode(prompt, timeout)
    elif backend == "claude":
        return _call_claude(prompt, model, timeout)
    else:
        raise ValueError(f"Unknown backend: {backend}. Must be 'opencode' or 'claude'.")
