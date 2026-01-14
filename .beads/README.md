# Beads Setup for NthLayer

This directory contains beads issue tracking for the NthLayer project.

## Quick Start

Since `bd` command isn't in your PATH yet, use the full path:

```bash
# Add to ~/.zshrc or ~/.bashrc for convenience:
alias bd="~/go/bin/bd"
```

Then reload your shell or run: `source ~/.zshrc`

## Common Commands

```bash
# See what's ready to work on
bd ready

# See all issues
bd list

# Show issue details
bd show trellis-948

# Update issue status
bd update trellis-948 --status in_progress

# Close issue
bd close trellis-948 --reason "Grafana Cloud configured"

# See project stats
bd stats

# See blocked issues
bd blocked

# Show dependency tree
bd dep tree trellis-rpv
```

## Completed Milestones

**Epic: Metric Discovery Integration (metric-discovery-epic)** ✅ Completed Jan 2026

- ✅ Prometheus metric discovery prototype
- ✅ Metric classification by technology
- ✅ Dashboard validation infrastructure (Week 1)
- ✅ Grafana Foundation SDK integration (Week 2)
- ✅ SDK adapter for type-safe dashboard generation

**Current Release: v0.1.0a12** (Phase 2 - Dependency Intelligence)

## Files

- `issues.jsonl` - All issues (tracked in git)
- `metadata.json` - Repository metadata (tracked in git)
- `config.yaml` - Configuration (tracked in git)
- `beads.db` - SQLite database (gitignored, auto-generated from JSONL)

## Integration with Development

Beads is now the single source of truth for task tracking. When completing work:

1. Update issue status: `bd update <id> --status in_progress`
2. Do the work
3. Close issue: `bd close <id> --reason "Description of what was done"`
4. Check what's ready next: `bd ready`

## References

- [Beads GitHub](https://github.com/steveyegge/beads)
- [Adoption Proposal](../BEADS_ADOPTION_PROPOSAL.md)
