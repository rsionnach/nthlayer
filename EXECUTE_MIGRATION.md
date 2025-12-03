# Execute Roadmap Migration - Quick Guide

**Status:** ✅ Ready to Execute  
**Script:** `./migrate_roadmap_to_beads_v2.sh`  
**Time:** ~3 minutes  
**Risk:** Low (git-tracked, reversible)

---

## What This Does

Migrates complete NthLayer roadmap to beads with:
- ✅ 1 historical epic (Foundation) - closed
- ✅ 5 foundation features - closed
- ✅ 10 future work epics - open
- ✅ 60 features/tasks - open
- ✅ Links 4 existing demo issues
- ✅ No duplicates (skips PostgreSQL/Redis/Kubernetes templates)

**Result:** 77 total issues (6 closed + 71 open) showing 40% platform completion

---

## Pre-Execution Checklist

✅ Beads installed (`~/go/bin/bd`)  
✅ Beads initialized (`.beads/` exists)  
✅ Prefix updated (`nthlayer` in config.yaml)  
✅ Scripts ready:
   - `migrate_roadmap_to_beads_v2.sh` (executable)
   - `FOUNDATION_COMPLETE.md` (created)

---

## Execute

```bash
cd /Users/robfox/trellis

# Run migration
./migrate_roadmap_to_beads_v2.sh

# Expected output:
# - Creates Epic 0 (Foundation) and closes it
# - Creates 5 foundation features and closes them
# - Links existing demo issues (trellis-948, etc.)
# - Creates 10 epics (Observability, Error Budget, Alerts, etc.)
# - Creates 60 features under those epics
# - Shows summary
```

**Time:** ~3 minutes (beads creates issues quickly)

---

## Post-Migration Validation

### 1. Check Epic Count
```bash
bd list --type epic

# Expected: 11 epics
# - 1 closed (Foundation)
# - 1 open (Live Demo - existing trellis-rpv)
# - 10 open (new: Observability, Error Budget, etc.)
```

### 2. Check Closed Issues
```bash
bd list --status closed

# Expected: 6 closed
# - 1 epic (nthlayer-foundation or similar)
# - 5 features (core platform, templates, dashboards, unified, demo)
# - 1 existing (trellis-02u - Fly.io deployment)
```

### 3. Check Stats
```bash
bd stats

# Expected:
# Total: ~77 issues
# Open: ~71
# Closed: 6
# In Progress: 1 (trellis-948)
# Blocked: 3 (demo completion)
```

### 4. Check Ready Work
```bash
bd ready

# Should NOT show:
# - "Add PostgreSQL template" (already done)
# - "Add Redis template" (already done)
# - "Unified apply" (already done)

# SHOULD show:
# - "Add Kafka template"
# - "Implement SLO/SLI generation"
# - Other unblocked features
```

### 5. Check No Duplicates
```bash
bd list --title "PostgreSQL template"
# Expected: 0 results (template exists in code, not as open issue)

bd list --title "Kafka template"
# Expected: 1 result (not implemented yet, open issue)
```

### 6. Check Dependencies
```bash
# Check foundation epic is closed
bd show $(bd list --title "Foundation" --json | jq -r '.[0].id')
# Status should be: closed

# Check existing issues linked to Epic 10
bd show trellis-948 | grep "Strategic"
# Should show dependency on Epic 10
```

---

## Expected Issue Breakdown

### Closed (6 total)
- nthlayer-foundation [epic] - Foundation & MVP Development
- nthlayer-xxx [task] - Core platform infrastructure
- nthlayer-xxx [feature] - Technology templates (PostgreSQL/Redis/Kubernetes)
- nthlayer-xxx [feature] - Dashboard generation & recording rules
- nthlayer-xxx [feature] - Unified workflow (plan/apply)
- nthlayer-xxx [feature] - Live demo infrastructure

### Open Epics (11 total)
1. trellis-rpv [epic] - Live Demo Infrastructure (existing)
2. nthlayer-xxx [epic] - Observability Suite Expansion
3. nthlayer-xxx [epic] - Error Budget Foundation
4. nthlayer-xxx [epic] - Intelligent Alerts & Scorecard
5. nthlayer-xxx [epic] - Deployment Policies & Gates
6. nthlayer-xxx [epic] - Incident Management Expansion
7. nthlayer-xxx [epic] - Access Control & Security
8. nthlayer-xxx [epic] - Cost Management
9. nthlayer-xxx [epic] - Documentation & Knowledge
10. nthlayer-xxx [epic] - Compliance & Governance
11. nthlayer-xxx [epic] - Strategic Positioning & Launch

### Open Features (~60 total)
- Epic 1: 10 features (Kafka, Elasticsearch, MongoDB, SLO tracking, APM, etc.)
- Epic 2: 8 features (OpenSLO parser, error budget calculator, etc.)
- Epic 3: 6 features (Alert engine, Slack notifications, scorecard, etc.)
- Epic 4: 7 features (Policy DSL, ArgoCD blocking, CI/CD generation, etc.)
- Epic 5: 5 features (On-call schedules, war rooms, runbooks, etc.)
- Epic 6: 7 features (IAM roles, RBAC, secrets management, etc.)
- Epic 7: 4 features (Cost tagging, budgets, auto-scaling, etc.)
- Epic 8: 5 features (Runbook generation, docs templates, etc.)
- Epic 9: 5 features (SOC2, GDPR, backup policies, etc.)
- Epic 10: 10 features (6 new + 4 existing linked)

---

## After Migration

### Commit to Git
```bash
# Add updated beads files
git add .beads/issues.jsonl .beads/metadata.json

# Commit
git commit -m "Execute roadmap migration to beads

Migrated complete roadmap to dependency-aware tracking:
- 1 historical epic (Foundation) closed
- 10 future work epics created
- 60 features tracked (no duplicates)
- 4 existing demo issues linked
- Total: 77 issues, 40% complete

Removed duplicates:
- PostgreSQL/Redis/Kubernetes templates (exist)
- Dashboard generation (exists)
- Recording rules (exist)
- Unified apply (exists)
- Live demo (exists)

Result: Accurate tracking, ready work detection, no confusion.

Co-authored-by: factory-droid[bot] <138933559+factory-droid[bot]@users.noreply.github.com>"
```

### Daily Workflow
```bash
# Morning: What should I work on?
bd ready --priority P0,P1

# During work: Update status
bd update <id> --status in_progress

# When done: Close issue
bd close <id> --reason "Completed X, tested Y"
```

---

## Rollback (If Needed)

If something goes wrong:

```bash
# Check git diff
git diff .beads/issues.jsonl

# Rollback
git checkout .beads/issues.jsonl .beads/metadata.json

# Or revert commit
git revert HEAD
```

---

## Troubleshooting

### Issue: "bd: command not found"
```bash
# Use full path
~/go/bin/bd --version

# Or add to PATH
export PATH="$PATH:~/go/bin"
```

### Issue: Wrong prefix (shows trellis-xxx instead of nthlayer-xxx)
```bash
# Check config
cat .beads/config.yaml | grep issue-prefix

# Should show: issue-prefix: "nthlayer"
# If not, edit and re-run
```

### Issue: Duplicates created
```bash
# List all issues with "PostgreSQL"
bd list --title "PostgreSQL"

# If duplicates exist, delete them
bd delete <id>
```

### Issue: Migration fails mid-way
```bash
# Check what was created
bd list --type epic

# Check last created issue
bd list --json | jq -r '.[-1]'

# Continue from where it failed
# (script is idempotent-ish, safe to re-run)
```

---

## Next Steps After Migration

### Immediate
1. ✅ Validate migration (run checks above)
2. ✅ Commit to git
3. ✅ Update current work (bd update trellis-948)
4. ✅ Archive old roadmap .md files (optional)

### This Week
1. ✅ Use `bd ready` to drive daily work
2. ✅ Complete Grafana Cloud setup (trellis-948)
3. ✅ Start next unblocked feature
4. ✅ Practice beads workflow

### Next Month
1. ✅ Update README to point to beads for roadmap
2. ✅ Start Epic 2 (Error Budget Foundation)
3. ✅ Begin pilot program (Epic 10)
4. ✅ Weekly roadmap reviews with `bd stats`

---

## Summary

**What:** Migrate complete roadmap to beads  
**Why:** Dependency-aware tracking, ready work detection, accurate progress  
**How:** Run `./migrate_roadmap_to_beads_v2.sh`  
**Time:** 3 minutes execution + 5 minutes validation  
**Risk:** Low (git-tracked, reversible)  
**Benefit:** Always know what to work on, never start blocked work

**Ready?** Run: `./migrate_roadmap_to_beads_v2.sh`

---

**Status:** ✅ ALL PREP COMPLETE - READY TO EXECUTE
