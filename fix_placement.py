#!/usr/bin/env python3
"""Fix the EP-NS-008 stories placement in bmm-workflow-status.yaml"""

with open("docs/bmm-workflow-status.yaml") as f:
    lines = f.readlines()

# Find the line where stories section ends (where summary comment starts)
summary_comment_line = None
for i, line in enumerate(lines):
    if "# SUMMARY COUNTS" in line:
        summary_comment_line = i
        break

# Find where EP-NS-008 section starts
epns008_start = None
for i, line in enumerate(lines):
    if "EP-NS-008 STORIES:" in line:
        epns008_start = i
        break

# Find where EP-NS-008 section ends (should be end of file or before item_3_completion)
item3_line = None
for i, line in enumerate(lines):
    if line.strip() == "item_3_completion:":
        item3_line = i
        break

print(
    f"Summary comment at line: {summary_comment_line + 1 if summary_comment_line else 'not found'}"
)
print(
    f"EP-NS-008 starts at line: {epns008_start + 1 if epns008_start else 'not found'}"
)
print(f"item_3_completion at line: {item3_line + 1 if item3_line else 'not found'}")

if summary_comment_line and epns008_start and item3_line:
    # Extract EP-NS-008 section (from header comment to just before item_3_completion)
    # Include 2 lines before EP-NS-008 header (empty line + "# ===...")
    epns008_section = lines[epns008_start - 1 : item3_line]

    # Remove EP-NS-008 section from current location
    new_lines = lines[: epns008_start - 1] + lines[item3_line:]

    # Find new position of summary comment after removal
    new_summary_line = None
    for i, line in enumerate(new_lines):
        if "# SUMMARY COUNTS" in line:
            new_summary_line = i
            break

    # Insert EP-NS-008 section BEFORE the summary comment
    final_lines = (
        new_lines[:new_summary_line] + epns008_section + new_lines[new_summary_line:]
    )

    with open("docs/bmm-workflow-status.yaml", "w") as f:
        f.writelines(final_lines)

    print(f"Moved EP-NS-008 section to before line {new_summary_line + 1}")
    print("Fixed bmm-workflow-status.yaml")
else:
    print("Could not find required markers")
