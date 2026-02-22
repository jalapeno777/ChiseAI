#!/usr/bin/env python3
"""Fix the EP-NS-008 stories placement properly."""

with open("docs/bmm-workflow-status.yaml") as f:
    content = f.read()

lines = content.split("\n")

# Find where the last story entry ends (line with completion_date for PAPER-GATE-002)
last_story_end = None
for i, line in enumerate(lines):
    if 'completion_date: "2026-02-17"' in line:
        last_story_end = i
        break

# Find where EP-NS-008 stories actually start (the first - id: ST-NS-038 line)
epns038_line = None
for i, line in enumerate(lines):
    if line.strip() == "- id: ST-NS-038":
        epns038_line = i
        break

# Find where summary section starts
summary_line = None
for i, line in enumerate(lines):
    if "summary:" in line and lines[i].strip() == "summary:":
        summary_line = i
        break

print(f"Last story ends at: {last_story_end + 1 if last_story_end else 'not found'}")
print(f"ST-NS-038 at: {epns038_line + 1 if epns038_line else 'not found'}")
print(f"summary: at: {summary_line + 1 if summary_line else 'not found'}")

if last_story_end and epns038_line and summary_line:
    # Extract EP-NS-008 stories (from ST-NS-038 to just before summary)
    epns008_stories = lines[epns038_line:summary_line]

    # Build new file:
    # 1. Everything up to and including line 1924 (last story)
    # 2. Empty line
    # 3. EP-NS-008 stories (already indented properly)
    # 4. Summary section

    new_lines = lines[: last_story_end + 1]  # Up to and including completion_date line
    new_lines.append("")  # Empty line
    new_lines.extend(epns008_stories)  # EP-NS-008 stories
    new_lines.append("")  # Empty line before summary
    new_lines.extend(lines[summary_line:])  # Summary and rest

    with open("docs/bmm-workflow-status.yaml", "w") as f:
        f.write("\n".join(new_lines))

    print("Fixed placement")
else:
    print("Could not find markers")
