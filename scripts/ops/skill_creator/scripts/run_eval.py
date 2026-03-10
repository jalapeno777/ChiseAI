#!/usr/bin/env python3
"""Run trigger evaluation for a skill description.

Tests whether a skill's description causes Claude or Opencode to trigger (read the skill)
for a set of queries. Outputs results as JSON.
"""

import argparse
import json
import os
import select
import subprocess
import sys
import tempfile
import time
import uuid
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from utils import parse_skill_md


def find_project_root() -> Path:
    """Find the project root by walking up from cwd looking for .claude/.

    Mimics how Claude Code discovers its project root, so the command file
    we create ends up where claude -p will look for it.
    """
    current = Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / ".claude").is_dir():
            return parent
    return current


def run_single_query_claude(
    query: str,
    skill_name: str,
    skill_description: str,
    timeout: int,
    project_root: str,
    model: str | None = None,
) -> bool:
    """Run a single query using Claude CLI and return whether the skill was triggered.

    Creates a command file in .claude/commands/ so it appears in Claude's
    available_skills list, then runs `claude -p` with the raw query.
    Uses --include-partial-messages to detect triggering early from
    stream events (content_block_start) rather than waiting for the
    full assistant message, which only arrives after tool execution.
    """
    unique_id = uuid.uuid4().hex[:8]
    clean_name = f"{skill_name}-skill-{unique_id}"
    project_commands_dir = Path(project_root) / ".claude" / "commands"
    command_file = project_commands_dir / f"{clean_name}.md"

    try:
        project_commands_dir.mkdir(parents=True, exist_ok=True)
        # Use YAML block scalar to avoid breaking on quotes in description
        indented_desc = "\n  ".join(skill_description.split("\n"))
        command_content = (
            f"---\n"
            f"description: |\n"
            f"  {indented_desc}\n"
            f"---\n\n"
            f"# {skill_name}\n\n"
            f"This skill handles: {skill_description}\n"
        )
        command_file.write_text(command_content)

        cmd = [
            "claude",
            "-p",
            query,
            "--output-format",
            "stream-json",
            "--verbose",
            "--include-partial-messages",
        ]
        if model:
            cmd.extend(["--model", model])

        # Remove CLAUDECODE env var to allow nesting claude -p inside a
        # Claude Code session. The guard is for interactive terminal conflicts;
        # programmatic subprocess usage is safe.
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd=project_root,
            env=env,
        )

        triggered = False
        start_time = time.time()
        buffer = ""
        # Track state for stream event detection
        pending_tool_name = None
        accumulated_json = ""

        try:
            while time.time() - start_time < timeout:
                if process.poll() is not None:
                    remaining = process.stdout.read()
                    if remaining:
                        buffer += remaining.decode("utf-8", errors="replace")
                    break

                ready, _, _ = select.select([process.stdout], [], [], 1.0)
                if not ready:
                    continue

                chunk = os.read(process.stdout.fileno(), 8192)
                if not chunk:
                    break
                buffer += chunk.decode("utf-8", errors="replace")

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    # Early detection via stream events
                    if event.get("type") == "stream_event":
                        se = event.get("event", {})
                        se_type = se.get("type", "")

                        if se_type == "content_block_start":
                            cb = se.get("content_block", {})
                            if cb.get("type") == "tool_use":
                                tool_name = cb.get("name", "")
                                if tool_name in ("Skill", "Read"):
                                    pending_tool_name = tool_name
                                    accumulated_json = ""
                                else:
                                    return False

                        elif se_type == "content_block_delta" and pending_tool_name:
                            delta = se.get("delta", {})
                            if delta.get("type") == "input_json_delta":
                                accumulated_json += delta.get("partial_json", "")
                                if clean_name in accumulated_json:
                                    return True

                        elif se_type in ("content_block_stop", "message_stop"):
                            if pending_tool_name:
                                return clean_name in accumulated_json
                            if se_type == "message_stop":
                                return False

                    # Fallback: full assistant message
                    elif event.get("type") == "assistant":
                        message = event.get("message", {})
                        for content_item in message.get("content", []):
                            if content_item.get("type") != "tool_use":
                                continue
                            tool_name = content_item.get("name", "")
                            tool_input = content_item.get("input", {})
                            if tool_name == "Skill" and clean_name in tool_input.get(
                                "skill", ""
                            ):
                                triggered = True
                            elif tool_name == "Read" and clean_name in tool_input.get(
                                "file_path", ""
                            ):
                                triggered = True
                            return triggered

                    elif event.get("type") == "result":
                        return triggered
        finally:
            # Clean up process on any exit path (return, exception, timeout)
            if process.poll() is None:
                process.kill()
                process.wait()

        return triggered
    finally:
        if command_file.exists():
            command_file.unlink()


def _extract_json_from_text(text: str) -> dict | None:
    """Extract and parse JSON from text, handling various formats.

    Tries multiple strategies:
    1. Direct json.loads
    2. Extract JSON from markdown code blocks
    3. Find JSON between outermost braces

    Args:
        text: The text to parse

    Returns:
        Parsed JSON dict or None if parsing fails
    """
    text = text.strip()
    if not text:
        return None

    # Strategy 1: Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 2: Extract from markdown code blocks
    if "```" in text:
        # Try to extract JSON from ```json ... ``` blocks
        import re

        json_block_pattern = r"```(?:json)?\s*\n?(.*?)\n?```"
        matches = re.findall(json_block_pattern, text, re.DOTALL)
        for match in matches:
            try:
                return json.loads(match.strip())
            except json.JSONDecodeError:
                continue

    # Strategy 3: Find JSON between outermost braces
    try:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            json_str = text[start : end + 1]
            return json.loads(json_str)
    except json.JSONDecodeError:
        pass

    return None


def _parse_opencode_ndjson(stdout: str, debug: bool = False) -> dict | None:
    """Parse opencode NDJSON output to extract the classifier response.

    Opencode with --format json outputs NDJSON events like:
    {"type":"step_start",...}
    {"type":"text","part":{"text":"{\\"triggered\\": true}"}}
    {"type":"step_finish",...}

    This function parses each line, finds text events, and extracts the JSON response.
    Non-JSON lines (like warning messages) are skipped.

    Args:
        stdout: The raw stdout from opencode
        debug: If True, print debug information to stderr

    Returns:
        Parsed JSON dict with the classifier response, or None if parsing fails
    """
    lines = stdout.strip().split("\n")
    json_parse_errors = []
    text_events_found = []

    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue

        # Skip lines that don't look like JSON (don't start with { or [)
        if not line.startswith(("{", "[")):
            if debug:
                print(
                    f"  [DEBUG] Line {line_num}: Skipping non-JSON line: {line[:100]}",
                    file=sys.stderr,
                )
            continue

        # Parse the NDJSON event
        try:
            event = json.loads(line)
        except json.JSONDecodeError as e:
            json_parse_errors.append(f"Line {line_num}: {e}")
            if debug:
                print(
                    f"  [DEBUG] Line {line_num}: JSON parse error: {e}", file=sys.stderr
                )
            continue

        # Look for text events that contain the classifier response
        if event.get("type") == "text":
            part = event.get("part", {})
            text_content = part.get("text", "")

            if text_content:
                text_events_found.append(text_content[:200])  # Truncate for debug
                # Try to extract JSON from the text content
                result = _extract_json_from_text(text_content)
                if result is not None:
                    if debug:
                        print(
                            f"  [DEBUG] Successfully parsed JSON from text event on line {line_num}",
                            file=sys.stderr,
                        )
                    return result
                elif debug:
                    print(
                        f"  [DEBUG] Line {line_num}: Text event found but no valid JSON extracted",
                        file=sys.stderr,
                    )

    # Debug output if parsing failed
    if debug:
        print(f"  [DEBUG] Total lines processed: {len(lines)}", file=sys.stderr)
        print(f"  [DEBUG] JSON parse errors: {len(json_parse_errors)}", file=sys.stderr)
        print(f"  [DEBUG] Text events found: {len(text_events_found)}", file=sys.stderr)
        if text_events_found:
            print(
                f"  [DEBUG] Text event samples: {text_events_found[:3]}",
                file=sys.stderr,
            )

    # If no text events found, try parsing the entire stdout as fallback
    return _extract_json_from_text(stdout)


def preflight_backend_check(
    backend: str, timeout: int = 10, project_root: str = "."
) -> bool:
    """Run a preflight check to verify the backend is working correctly.

    Args:
        backend: The backend to check ('opencode' or 'claude')
        timeout: Timeout for the check in seconds
        project_root: Project root directory

    Returns:
        True if the backend is working, False otherwise
    """
    if backend == "opencode":
        # Create a simple test prompt
        test_prompt = """Respond with ONLY a JSON object in this exact format:
{"triggered": true}

Do not include any other text."""

        try:
            cmd = [
                "opencode",
                "run",
                "--agent",
                "aria",
                test_prompt,
                "--format",
                "json",
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=project_root,
            )

            stdout = result.stdout.strip()
            stderr_output = result.stderr.strip()
            if not stdout:
                print(
                    "Error: Preflight check failed - opencode returned empty output. "
                    "Please verify:\n"
                    "  1. Opencode is installed and in your PATH\n"
                    "  2. The aria agent is configured correctly\n"
                    "  3. Opencode is not already running in another process",
                    file=sys.stderr,
                )
                if stderr_output:
                    print(f"  stderr: {stderr_output[:500]}", file=sys.stderr)
                return False

            # Try to parse the output
            response = _parse_opencode_ndjson(stdout, debug=False)
            if response is None:
                print(
                    "Error: Preflight check failed - could not parse opencode output as JSON.\n"
                    f"Raw output: {stdout[:500]}",
                    file=sys.stderr,
                )
                if stderr_output:
                    print(f"  stderr: {stderr_output[:500]}", file=sys.stderr)
                # Run with debug to get detailed diagnostics
                _parse_opencode_ndjson(stdout, debug=True)
                return False

            if not isinstance(response, dict) or "triggered" not in response:
                print(
                    "Error: Preflight check failed - response missing 'triggered' field.\n"
                    f"Response: {response}",
                    file=sys.stderr,
                )
                return False

            return True

        except subprocess.TimeoutExpired:
            print(
                f"Error: Preflight check failed - opencode timed out after {timeout}s.",
                file=sys.stderr,
            )
            return False
        except FileNotFoundError:
            print(
                "Error: Preflight check failed - opencode command not found. "
                "Please install opencode and ensure it's in your PATH.",
                file=sys.stderr,
            )
            return False
        except Exception as e:
            print(
                f"Error: Preflight check failed - {e}",
                file=sys.stderr,
            )
            return False

    elif backend == "claude":
        # For claude backend, just check if the command exists
        try:
            result = subprocess.run(
                ["claude", "--version"],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode != 0:
                print(
                    "Error: Preflight check failed - claude command returned error.",
                    file=sys.stderr,
                )
                return False
            return True
        except FileNotFoundError:
            print(
                "Error: Preflight check failed - claude command not found. "
                "Please install Claude CLI and ensure it's in your PATH.",
                file=sys.stderr,
            )
            return False
        except Exception as e:
            print(
                f"Error: Preflight check failed - {e}",
                file=sys.stderr,
            )
            return False

    else:
        print(f"Error: Unknown backend '{backend}'", file=sys.stderr)
        return False


def run_single_query_opencode(
    query: str,
    skill_name: str,
    skill_description: str,
    timeout: int,
    project_root: str,
    model: str | None = None,
) -> bool:
    """Run a single query using Opencode CLI and return whether the skill should be triggered.

    Creates a temporary prompt file containing the classifier prompt, then runs
    `opencode run --agent aria --prompt-file <file>`. Parses the JSON response
    to determine if the skill should be triggered.

    Args:
        query: The user query to evaluate
        skill_name: Name of the skill being tested
        skill_description: Description of the skill
        timeout: Timeout in seconds
        project_root: Project root directory (unused but kept for signature compatibility)
        model: Model to use (unused for opencode backend)

    Returns:
        True if the skill should be triggered for this query, False otherwise
    """
    # Classifier prompt template that returns strict JSON
    classifier_prompt = f"""You are evaluating whether a skill should be triggered for a user query.

Skill Name: {skill_name}
Skill Description: {skill_description}

User Query: {query}

Determine if this skill should be triggered for this query based on the skill description.
Respond with ONLY a JSON object in this exact format:
{{"triggered": true}} or {{"triggered": false}}

Do not include any other text, explanation, or formatting."""

    try:
        cmd = [
            "opencode",
            "run",
            "--agent",
            "aria",
            "--format",
            "json",
            classifier_prompt,  # Pass prompt as positional argument
        ]

        # Run opencode command with timeout
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=project_root,
        )

        # Parse stdout - handle NDJSON events from opencode --format json
        stdout = result.stdout.strip()
        stderr_output = result.stderr.strip()
        if not stdout:
            print(f"Warning: opencode returned empty stdout", file=sys.stderr)
            if stderr_output:
                print(f"  stderr: {stderr_output[:500]}", file=sys.stderr)
            return False

        # Parse the response with debug enabled on failure
        response_json = _parse_opencode_ndjson(stdout, debug=False)
        if response_json is None:
            print(f"Warning: Failed to parse opencode output as JSON", file=sys.stderr)
            print(f"  stdout preview: {stdout[:500]}", file=sys.stderr)
            if stderr_output:
                print(f"  stderr: {stderr_output[:500]}", file=sys.stderr)
            # Retry with debug enabled to get detailed diagnostics
            _parse_opencode_ndjson(stdout, debug=True)
            return False

        # Extract the "triggered" field
        if not isinstance(response_json, dict):
            print(
                f"Warning: opencode response is not a dict: {response_json}",
                file=sys.stderr,
            )
            return False

        triggered = response_json.get("triggered", False)
        return bool(triggered)

    except subprocess.TimeoutExpired:
        print(f"Warning: opencode command timed out after {timeout}s", file=sys.stderr)
        return False
    except Exception as e:
        print(f"Warning: opencode command failed: {e}", file=sys.stderr)
        return False


def run_eval(
    eval_set: list[dict],
    skill_name: str,
    description: str,
    num_workers: int,
    timeout: int,
    project_root: Path,
    runs_per_query: int = 1,
    trigger_threshold: float = 0.5,
    model: str | None = None,
    backend: str = "opencode",
) -> dict:
    """Run the full eval set and return results.

    Args:
        eval_set: List of evaluation items with 'query' and 'should_trigger' keys
        skill_name: Name of the skill being evaluated
        description: Skill description to test
        num_workers: Number of parallel workers
        timeout: Timeout per query in seconds
        project_root: Project root directory
        runs_per_query: Number of runs per query for stability
        trigger_threshold: Threshold for considering a query triggered
        model: Model to use (claude backend only)
        backend: Backend to use ('opencode' or 'claude')

    Returns:
        Dictionary with evaluation results and summary
    """
    # Run preflight backend check
    if not preflight_backend_check(
        backend, timeout=timeout, project_root=str(project_root)
    ):
        raise RuntimeError(f"Preflight check failed for backend '{backend}'")

    # Select the appropriate query function based on backend
    if backend == "opencode":
        query_fn = run_single_query_opencode
    else:
        query_fn = run_single_query_claude

    results = []

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        future_to_info = {}
        for item in eval_set:
            for run_idx in range(runs_per_query):
                future = executor.submit(
                    query_fn,
                    item["query"],
                    skill_name,
                    description,
                    timeout,
                    str(project_root),
                    model,
                )
                future_to_info[future] = (item, run_idx)

        query_triggers: dict[str, list[bool]] = {}
        query_items: dict[str, dict] = {}
        for future in as_completed(future_to_info):
            item, _ = future_to_info[future]
            query = item["query"]
            query_items[query] = item
            if query not in query_triggers:
                query_triggers[query] = []
            try:
                query_triggers[query].append(future.result())
            except Exception as e:
                print(f"Warning: query failed: {e}", file=sys.stderr)
                query_triggers[query].append(False)

    for query, triggers in query_triggers.items():
        item = query_items[query]
        trigger_rate = sum(triggers) / len(triggers)
        should_trigger = item["should_trigger"]
        if should_trigger:
            did_pass = trigger_rate >= trigger_threshold
        else:
            did_pass = trigger_rate < trigger_threshold
        results.append(
            {
                "query": query,
                "should_trigger": should_trigger,
                "trigger_rate": trigger_rate,
                "triggers": sum(triggers),
                "runs": len(triggers),
                "pass": did_pass,
            }
        )

    passed = sum(1 for r in results if r["pass"])
    total = len(results)

    return {
        "skill_name": skill_name,
        "description": description,
        "results": results,
        "summary": {
            "total": total,
            "passed": passed,
            "failed": total - passed,
        },
    }


def main():
    parser = argparse.ArgumentParser(
        description="Run trigger evaluation for a skill description"
    )
    parser.add_argument("--eval-set", required=True, help="Path to eval set JSON file")
    parser.add_argument("--skill-path", required=True, help="Path to skill directory")
    parser.add_argument(
        "--description", default=None, help="Override description to test"
    )
    parser.add_argument(
        "--num-workers", type=int, default=10, help="Number of parallel workers"
    )
    parser.add_argument(
        "--timeout", type=int, default=30, help="Timeout per query in seconds"
    )
    parser.add_argument(
        "--runs-per-query", type=int, default=3, help="Number of runs per query"
    )
    parser.add_argument(
        "--trigger-threshold", type=float, default=0.5, help="Trigger rate threshold"
    )
    parser.add_argument(
        "--backend",
        choices=["opencode", "claude"],
        default="opencode",
        help="Backend to use for evaluation (default: opencode)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model to use (claude backend only; opencode uses agent configuration)",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Print progress to stderr"
    )
    args = parser.parse_args()

    eval_set = json.loads(Path(args.eval_set).read_text())
    skill_path = Path(args.skill_path)

    if not (skill_path / "SKILL.md").exists():
        print(f"Error: No SKILL.md found at {skill_path}", file=sys.stderr)
        sys.exit(1)

    name, original_description, content = parse_skill_md(skill_path)
    description = args.description or original_description
    project_root = find_project_root()

    if args.verbose:
        print(f"Evaluating: {description}", file=sys.stderr)
        print(f"Using backend: {args.backend}", file=sys.stderr)

    output = run_eval(
        eval_set=eval_set,
        skill_name=name,
        description=description,
        num_workers=args.num_workers,
        timeout=args.timeout,
        project_root=project_root,
        runs_per_query=args.runs_per_query,
        trigger_threshold=args.trigger_threshold,
        model=args.model,
        backend=args.backend,
    )

    if args.verbose:
        summary = output["summary"]
        print(
            f"Results: {summary['passed']}/{summary['total']} passed", file=sys.stderr
        )
        for r in output["results"]:
            status = "PASS" if r["pass"] else "FAIL"
            rate_str = f"{r['triggers']}/{r['runs']}"
            print(
                f"  [{status}] rate={rate_str} expected={r['should_trigger']}: {r['query'][:70]}",
                file=sys.stderr,
            )

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
