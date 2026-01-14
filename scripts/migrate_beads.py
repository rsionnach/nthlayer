#!/usr/bin/env python3
"""
Migrate beads from issues.jsonl to individual JSON files.

This script converts the legacy jsonl format to individual JSON files
organized into features/ and issues/ directories.
"""

import json
import re
from pathlib import Path
from datetime import datetime


def slugify(title: str) -> str:
    """Convert title to a valid filename slug."""
    # Remove special characters and convert to lowercase
    slug = title.lower()
    # Replace spaces and special chars with hyphens
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    # Remove leading/trailing hyphens
    slug = slug.strip("-")
    # Limit length
    if len(slug) > 60:
        slug = slug[:60].rsplit("-", 1)[0]
    return slug


def determine_directory(entry: dict) -> str:
    """Determine if entry should go in features/ or issues/."""
    issue_type = entry.get("issue_type", "task")
    title = entry.get("title", "").lower()

    # Features
    if issue_type == "feature":
        return "features"
    if issue_type == "epic":
        return "features"
    if "implement" in title or "build" in title or "create" in title:
        if entry.get("priority", 3) <= 2:
            return "features"

    # Default to issues
    return "issues"


def convert_priority(priority: int | str) -> str:
    """Convert numeric priority to P-format."""
    if isinstance(priority, str):
        return priority
    return f"P{priority}"


def migrate_entry(entry: dict, output_dir: Path, existing_files: set) -> tuple[Path | None, bool]:
    """
    Migrate a single jsonl entry to an individual JSON file.

    Returns: (output_path, was_skipped)
    """
    title = entry.get("title", entry.get("id", "unknown"))
    slug = slugify(title)

    # Skip if already exists as individual file
    if slug in existing_files:
        return None, True

    # Determine directory
    subdir = determine_directory(entry)
    target_dir = output_dir / subdir
    target_dir.mkdir(parents=True, exist_ok=True)

    # Handle duplicate slugs
    base_slug = slug
    counter = 1
    while (target_dir / f"{slug}.json").exists():
        slug = f"{base_slug}-{counter}"
        counter += 1

    output_path = target_dir / f"{slug}.json"

    # Convert to new format
    new_entry = {
        "id": slug,
        "type": entry.get("issue_type", "task"),
        "title": title,
        "description": entry.get("description", ""),
        "status": entry.get("status", "open"),
        "priority": convert_priority(entry.get("priority", 3)),
        "tags": entry.get("tags", []),
        "created_at": entry.get("created_at", datetime.now().isoformat()),
        "updated_at": entry.get("updated_at"),
        "legacy_id": entry.get("id"),  # Preserve original ID
    }

    # Add optional fields if present
    if entry.get("closed_at"):
        new_entry["closed_at"] = entry["closed_at"]
    if entry.get("dependencies"):
        new_entry["dependencies"] = [d.get("depends_on_id") for d in entry["dependencies"]]
    if entry.get("comments"):
        new_entry["comments"] = [
            {"author": c.get("author"), "text": c.get("text"), "date": c.get("created_at")}
            for c in entry["comments"]
        ]

    # Remove None values
    new_entry = {k: v for k, v in new_entry.items() if v is not None}

    # Write file
    with open(output_path, "w") as f:
        json.dump(new_entry, f, indent=2)

    return output_path, False


def main():
    """Run the migration."""
    beads_dir = Path(__file__).parent.parent / ".beads"
    jsonl_path = beads_dir / "issues.jsonl"

    if not jsonl_path.exists():
        print(f"Error: {jsonl_path} not found")
        return 1

    # Get existing individual files to avoid duplicates
    existing_files = set()
    for subdir in ["features", "issues"]:
        dir_path = beads_dir / subdir
        if dir_path.exists():
            for f in dir_path.glob("*.json"):
                existing_files.add(f.stem)

    print(f"Found {len(existing_files)} existing individual files")

    # Read jsonl
    entries = []
    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError as e:
                    print(f"Warning: Could not parse line: {e}")

    print(f"Found {len(entries)} entries in issues.jsonl")

    # Migrate
    created = 0
    skipped = 0
    errors = 0

    for entry in entries:
        try:
            path, was_skipped = migrate_entry(entry, beads_dir, existing_files)
            if was_skipped:
                skipped += 1
            elif path:
                created += 1
                print(f"  Created: {path.relative_to(beads_dir)}")
        except Exception as e:
            errors += 1
            print(f"  Error migrating {entry.get('title', 'unknown')}: {e}")

    print("\nMigration complete:")
    print(f"  Created: {created}")
    print(f"  Skipped (already exists): {skipped}")
    print(f"  Errors: {errors}")

    return 0


if __name__ == "__main__":
    exit(main())
