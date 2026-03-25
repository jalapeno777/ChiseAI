#!/usr/bin/env python3
"""Fix Woodpecker CI configuration: move pull policy to per-step level."""

import re


def fix_ci_yaml(input_path: str, output_path: str) -> None:
    """Fix the ci.yaml by:
    1. Removing the root-level `pull: if-not-present` line
    2. Adding `pull: if-not-exists` as first property for each step with `image:`
    """
    with open(input_path) as f:
        content = f.read()

    lines = content.split("\n")
    result_lines = []
    i = 0
    in_steps = False
    in_clone = False
    # Track indentation of the current block context
    block_indent = None

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Determine current line's indentation
        current_indent = len(line) - len(line.lstrip())

        # Track context changes based on indentation
        if stripped == "steps:":
            in_steps = True
            in_clone = False
            block_indent = None
        elif stripped == "clone:":
            in_clone = True
            in_steps = False
            block_indent = None
        elif stripped.startswith("when:") and current_indent == 0:
            # Root-level when block
            block_indent = current_indent
            in_steps = False
            in_clone = False
        elif block_indent is not None:
            # We're inside a block - check if we've exited it
            # If we see a non-empty, non-comment line at same or lower indent, we exited
            if (
                stripped
                and not stripped.startswith("#")
                and current_indent <= block_indent
            ):
                # Exited the block
                block_indent = None
                in_steps = False
                in_clone = False

        # Remove root-level pull: if-not-present (at indent 0, not inside any block)
        if (
            current_indent == 0
            and stripped == "pull: if-not-present"
            and block_indent is None
        ):
            i += 1
            continue

        # Check if this is a step name line within steps
        # Pattern: whitespace + word chars + optional dash + colon at end
        step_match = re.match(r"^(\s+)(\w[\w-]*)(\s*:\s*)$", line)
        if step_match and in_steps and not in_clone and block_indent is None:
            step_indent = step_match.group(1)
            step_match.group(2)

            # Add the step name line
            result_lines.append(line)
            i += 1

            # Look ahead to see if this step has an image property
            has_image = False
            j = i
            while j < len(lines):
                next_line = lines[j]
                next_stripped = next_line.strip()
                # Stop at next step (same or less indentation followed by name:)
                if re.match(
                    r"^\s+\w[\w-]*\s*:\s*$", next_line
                ) and not next_line.strip().startswith("#"):
                    break
                if next_stripped.startswith("image:"):
                    has_image = True
                    break
                j += 1

            # If step has image, add pull: if-not-exists as first property
            if has_image:
                pull_line = step_indent + "  pull: if-not-exists"
                result_lines.append(pull_line)

            continue

        result_lines.append(line)
        i += 1

    # Write output
    with open(output_path, "w") as f:
        f.write("\n".join(result_lines))

    print(f"Fixed {input_path} -> {output_path}")


if __name__ == "__main__":
    input_file = "/home/tacopants/projects/ChiseAI/.woodpecker/ci.yaml"
    output_file = "/home/tacopants/projects/ChiseAI/.woodpecker/ci.yaml"
    fix_ci_yaml(input_file, output_file)
