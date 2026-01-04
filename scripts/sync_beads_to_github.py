#!/usr/bin/env python3
"""Sync beads to GitHub issues.

Creates GitHub issues for open beads that don't have an issue yet.
Updates existing issues with bead changes.
"""

import json
import subprocess
from pathlib import Path

BEADS_FILE = Path(__file__).parent.parent / ".beads" / "issues.jsonl"
SYNC_FILE = Path(__file__).parent.parent / ".beads" / "github_sync.json"

# Priority mapping
PRIORITY_LABELS = {
    0: "priority: critical",
    1: "priority: high",
    2: "priority: medium",
    3: "priority: low",
}

# Issue type mapping
TYPE_LABELS = {
    "epic": "type: epic",
    "feature": "type: feature",
    "task": "type: task",
    "bug": "type: bug",
}


def load_beads():
    """Load all beads from JSONL file."""
    beads = []
    with open(BEADS_FILE) as f:
        for line in f:
            if line.strip():
                beads.append(json.loads(line))
    return beads


def load_sync_state():
    """Load sync state (bead_id -> github_issue_number)."""
    if SYNC_FILE.exists():
        with open(SYNC_FILE) as f:
            return json.load(f)
    return {}


def save_sync_state(state):
    """Save sync state."""
    with open(SYNC_FILE, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True)


def create_github_issue(bead):
    """Create a GitHub issue for a bead."""
    labels = []

    # Add priority label
    priority = bead.get("priority", 2)
    if priority in PRIORITY_LABELS:
        labels.append(PRIORITY_LABELS[priority])

    # Add type label
    issue_type = bead.get("issue_type", "task")
    if issue_type in TYPE_LABELS:
        labels.append(TYPE_LABELS[issue_type])

    # Add status label
    if bead.get("status") == "closed":
        labels.append("status: closed")
    elif bead.get("status") == "in_progress":
        labels.append("status: in-progress")

    # Build body
    body = f"**Bead ID:** `{bead['id']}`\n\n"
    body += bead.get("description", "No description")

    if bead.get("dependencies"):
        body += "\n\n**Dependencies:**\n"
        for dep in bead["dependencies"]:
            body += f"- Blocked by: `{dep['depends_on_id']}`\n"

    if bead.get("close_reason"):
        body += f"\n\n**Close Reason:** {bead['close_reason']}"

    # Create issue
    cmd = [
        "gh",
        "issue",
        "create",
        "--title",
        bead["title"],
        "--body",
        body,
    ]

    for label in labels:
        cmd.extend(["--label", label])

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        # Extract issue number from URL
        url = result.stdout.strip()
        issue_number = url.split("/")[-1]
        print(f"Created issue #{issue_number} for {bead['id']}: {bead['title']}")
        return issue_number
    else:
        print(f"Failed to create issue for {bead['id']}: {result.stderr}")
        return None


def close_github_issue(issue_number, reason=""):
    """Close a GitHub issue."""
    cmd = ["gh", "issue", "close", str(issue_number)]
    if reason:
        cmd.extend(["--comment", f"Closed: {reason}"])

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"Closed issue #{issue_number}")
    else:
        print(f"Failed to close issue #{issue_number}: {result.stderr}")


def sync_beads(max_priority=1):
    """Sync beads to GitHub issues.

    Args:
        max_priority: Maximum priority to sync (0=P0 only, 1=P0+P1, 2=P0+P1+P2, etc.)
    """
    beads = load_beads()
    sync_state = load_sync_state()

    # Filter to open beads with priority <= max_priority
    open_beads = [
        b for b in beads if b.get("status") != "closed" and b.get("priority", 2) <= max_priority
    ]
    closed_beads = [b for b in beads if b.get("status") == "closed"]

    print(f"Syncing beads with priority <= P{max_priority}")
    print(f"Found {len(open_beads)} open beads to sync")

    created = 0
    skipped = 0
    closed = 0

    # Create issues for open beads without GitHub issues
    for bead in open_beads:
        bead_id = bead["id"]

        if bead_id in sync_state:
            skipped += 1
            continue

        issue_number = create_github_issue(bead)
        if issue_number:
            sync_state[bead_id] = issue_number
            created += 1

    # Close GitHub issues for closed beads
    for bead in closed_beads:
        bead_id = bead["id"]

        if bead_id in sync_state:
            issue_number = sync_state[bead_id]
            close_github_issue(issue_number, bead.get("close_reason", ""))
            closed += 1

    save_sync_state(sync_state)

    print("\n=== Sync Complete ===")
    print(f"Created: {created}")
    print(f"Skipped (already synced): {skipped}")
    print(f"Closed: {closed}")
    print(f"Total open beads: {len(open_beads)}")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Sync beads to GitHub issues")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be created")
    parser.add_argument(
        "--priority",
        type=int,
        default=1,
        help="Max priority to sync (0=P0, 1=P0+P1, 2=all). Default: 1",
    )
    args = parser.parse_args()

    beads = load_beads()
    sync_state = load_sync_state()

    # Filter by priority
    open_beads = [
        b for b in beads if b.get("status") != "closed" and b.get("priority", 2) <= args.priority
    ]
    new_beads = [b for b in open_beads if b["id"] not in sync_state]

    if args.dry_run:
        print(f"Would create {len(new_beads)} new issues (P0-P{args.priority}):")
        for bead in new_beads:
            p = bead.get("priority", 2)
            print(f"  P{p} - {bead['id']}: {bead['title']}")
    else:
        sync_beads(max_priority=args.priority)


if __name__ == "__main__":
    main()
