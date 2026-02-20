#!/usr/bin/env python3
"""Fix the EP-NS-008 stories placement - move them BEFORE sprints section."""

with open("docs/bmm-workflow-status.yaml", "r") as f:
    content = f.read()

lines = content.split("\n")

# Find where sprints section starts
sprints_line = None
for i, line in enumerate(lines):
    if line.strip() == "sprints:":
        sprints_line = i
        break

# Find where stories section starts
stories_line = None
for i, line in enumerate(lines):
    if line.strip() == "stories:":
        stories_line = i
        break

# Find EP-NS-038 entry
epns038_line = None
for i, line in enumerate(lines):
    if line.strip() == "- id: ST-NS-038":
        epns038_line = i
        break

# Find where sprints section ends (should be item_3_completion or summary)
item3_line = None
for i, line in enumerate(lines):
    if line.strip() == "item_3_completion:":
        item3_line = i
        break

print(f"stories: at line {stories_line + 1 if stories_line else 'not found'}")
print(f"sprints: at line {sprints_line + 1 if sprints_line else 'not found'}")
print(f"ST-NS-038 at line {epns038_line + 1 if epns038_line else 'not found'}")
print(f"item_3_completion at line {item3_line + 1 if item3_line else 'not found'}")

if stories_line and sprints_line and epns038_line and item3_line:
    # Check if ST-NS-038 is after sprints: (which is wrong)
    if epns038_line > sprints_line:
        print("ST-NS-038 is AFTER sprints: - need to move it")

        # Extract all EP-NS-008 stories (from ST-NS-038 to just before item_3_completion)
        epns008_content = lines[epns038_line:item3_line]

        # Remove them from current location
        new_lines = lines[:epns038_line] + lines[item3_line:]

        # Find new position of sprints: after removal
        new_sprints_line = None
        for i, line in enumerate(new_lines):
            if line.strip() == "sprints:":
                new_sprints_line = i
                break

        # Insert EP-NS-008 stories BEFORE sprints: section
        # Add an empty line before for separation
        final_lines = new_lines[:new_sprints_line]
        final_lines.append("")  # Empty line for separation
        final_lines.extend(epns008_content)
        final_lines.extend(new_lines[new_sprints_line:])

        with open("docs/bmm-workflow-status.yaml", "w") as f:
            f.write("\n".join(final_lines))

        print(f"Moved EP-NS-008 stories to before line {new_sprints_line + 1}")
        print("Fixed!")
    else:
        print("ST-NS-038 is already in correct position")
else:
    print("Could not find required markers")
