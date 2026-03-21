#!/usr/bin/env python3
"""
Workflow status deduplication script.
Identifies duplicate story entries and keeps the most recent version.
"""

import yaml
import sys
from collections import defaultdict
from datetime import datetime
from copy import deepcopy


def parse_yaml_file(filepath):
    """Parse YAML file and return data."""
    with open(filepath, "r") as f:
        return yaml.safe_load(f)


def get_timestamp_from_entry(entry):
    """Extract the most recent timestamp from an entry."""
    timestamps = []

    # Check various date fields
    if "created_date" in entry:
        try:
            timestamps.append(
                datetime.fromisoformat(entry["created_date"].replace("Z", "+00:00"))
            )
        except:
            pass

    if "completion_date" in entry:
        try:
            timestamps.append(
                datetime.fromisoformat(entry["completion_date"].replace("Z", "+00:00"))
            )
        except:
            pass

    if "merged_date" in entry:
        try:
            timestamps.append(
                datetime.fromisoformat(entry["merged_date"].replace("Z", "+00:00"))
            )
        except:
            pass

    # Check recent_changes for timestamps
    if "recent_changes" in entry:
        for change in entry["recent_changes"]:
            if isinstance(change, dict) and "timestamp" in change:
                try:
                    timestamps.append(
                        datetime.fromisoformat(
                            change["timestamp"].replace("Z", "+00:00")
                        )
                    )
                except:
                    pass

    # Check notes for timestamps
    if "notes" in entry:
        for note in entry["notes"]:
            if isinstance(note, str):
                # Try to extract date from note strings like "2026-03-05: ..."
                if note.startswith("20") and len(note) >= 10:
                    try:
                        date_str = note[:10]
                        timestamps.append(datetime.strptime(date_str, "%Y-%m-%d"))
                    except:
                        pass

    if timestamps:
        return max(timestamps)
    return datetime.min


def merge_notes(keep_entry, remove_entry):
    """Merge unique notes from remove_entry into keep_entry."""
    if "notes" not in keep_entry:
        keep_entry["notes"] = []
    if "notes" not in remove_entry:
        return

    existing_notes = set(str(n) for n in keep_entry["notes"])
    for note in remove_entry["notes"]:
        if str(note) not in existing_notes:
            keep_entry["notes"].append(note)
            existing_notes.add(str(note))


def find_duplicates(data):
    """Find duplicate entries by ID within each section."""
    duplicates = defaultdict(lambda: defaultdict(list))

    for section in ["completed", "backlog", "in_progress", "blocked"]:
        if section not in data:
            continue

        seen_ids = defaultdict(list)
        for idx, entry in enumerate(data[section]):
            if entry is None:
                continue
            entry_id = entry.get("id", f"NO_ID_{idx}")
            seen_ids[entry_id].append((idx, entry))

        for entry_id, entries in seen_ids.items():
            if len(entries) > 1:
                duplicates[section][entry_id] = entries

    return duplicates


def deduplicate_section(section_data, duplicates_info):
    """Deduplicate a section, keeping the most recent entry."""
    if not duplicates_info:
        return section_data, 0

    # Track which indices to remove
    indices_to_remove = set()

    for entry_id, entries in duplicates_info.items():
        print(f"  Processing duplicate: {entry_id} ({len(entries)} occurrences)")

        # Sort by timestamp (most recent first)
        entries_with_ts = [
            (idx, entry, get_timestamp_from_entry(entry)) for idx, entry in entries
        ]
        entries_with_ts.sort(key=lambda x: x[2], reverse=True)

        # Keep the most recent, mark others for removal
        keep_idx, keep_entry, keep_ts = entries_with_ts[0]
        print(f"    Keeping index {keep_idx} (timestamp: {keep_ts})")

        for idx, entry, ts in entries_with_ts[1:]:
            indices_to_remove.add(idx)
            print(f"    Removing index {idx} (timestamp: {ts})")
            # Merge unique notes
            merge_notes(keep_entry, entry)

    # Create new list without duplicates
    new_section = [
        entry for idx, entry in enumerate(section_data) if idx not in indices_to_remove
    ]

    return new_section, len(indices_to_remove)


def main():
    input_file = "docs/bmm-workflow-status.yaml"
    output_file = "docs/bmm-workflow-status.yaml.deduped"

    print(f"Parsing {input_file}...")
    data = parse_yaml_file(input_file)

    print("\nAnalyzing for duplicates...")
    duplicates = find_duplicates(data)

    total_duplicates = 0
    total_removed = 0

    for section, section_duplicates in duplicates.items():
        if section_duplicates:
            count = sum(len(entries) - 1 for entries in section_duplicates.values())
            total_duplicates += count
            print(
                f"\n{section.upper()}: {len(section_duplicates)} duplicate IDs, {count} total duplicates"
            )

    if total_duplicates == 0:
        print("\nNo duplicates found!")
        return

    print(f"\n\nTotal duplicates to remove: {total_duplicates}")
    print("\nDeduplicating...")

    # Process each section
    for section in ["completed", "backlog", "in_progress", "blocked"]:
        if section in data and section in duplicates and duplicates[section]:
            print(f"\nProcessing section: {section}")
            data[section], removed = deduplicate_section(
                data[section], duplicates[section]
            )
            total_removed += removed

    print(f"\n\nTotal entries removed: {total_removed}")

    # Write deduplicated file
    print(f"\nWriting deduplicated file to {output_file}...")
    with open(output_file, "w") as f:
        yaml.dump(
            data, f, default_flow_style=False, allow_unicode=True, sort_keys=False
        )

    print("Done!")
    print(f"\nSummary:")
    print(f"  - Duplicates found: {total_duplicates}")
    print(f"  - Duplicates removed: {total_removed}")
    print(f"  - Output file: {output_file}")


if __name__ == "__main__":
    main()
