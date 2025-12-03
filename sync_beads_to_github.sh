#!/bin/bash
# Sync P0 Epics and Features from Beads to GitHub Issues
# Can be run manually or automated via git hooks/GitHub Actions

set -e

cd "$(dirname "$0")"

REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
MAPPING_FILE=".beads/github_sync.json"
BD="$HOME/go/bin/bd"

echo "🔄 Syncing Beads → GitHub Issues"
echo "================================="
echo "Repository: $REPO"
echo ""

# Create mapping file if it doesn't exist
if [ ! -f "$MAPPING_FILE" ]; then
    echo "{}" > "$MAPPING_FILE"
    echo "📝 Created mapping file: $MAPPING_FILE"
fi

# Get P0 epics and features from beads
echo "🏷️  Ensuring labels exist..."
# Create labels if they don't exist (ignore errors if they already exist)
gh label create "beads-sync" --description "Synced from beads project tracker" --color "0E8A16" 2>/dev/null || true
gh label create "epic" --description "Epic - large feature grouping" --color "3E4B9E" 2>/dev/null || true
gh label create "feature" --description "Feature implementation" --color "1D76DB" 2>/dev/null || true

echo "🔍 Finding P0 epics and features in beads..."
echo ""

# Get all P0 epics
epics=$($BD list --priority P0 --type epic --json | jq -r '.[] | @base64')

# Get all P0 features
features=$($BD list --priority P0 --type feature --json | jq -r '.[] | @base64')

# Combine them
items=$(echo -e "$epics\n$features" | grep -v '^$')

if [ -z "$items" ]; then
    echo "✅ No P0 epics/features found to sync"
    exit 0
fi

count=0
created=0
updated=0
skipped=0

for item in $items; do
    # Decode the base64 JSON
    row=$(echo "$item" | base64 --decode)
    
    beads_id=$(echo "$row" | jq -r '.id')
    title=$(echo "$row" | jq -r '.title')
    description=$(echo "$row" | jq -r '.description // ""')
    status=$(echo "$row" | jq -r '.status')
    type=$(echo "$row" | jq -r '.type')
    
    count=$((count + 1))
    
    echo "[$count] Processing: $beads_id - $title"
    
    # Check if already synced
    github_number=$(jq -r --arg id "$beads_id" '.[$id] // empty' "$MAPPING_FILE")
    
    # Prepare labels (skip if type is null)
    if [ "$type" != "null" ] && [ -n "$type" ]; then
        labels="beads-sync $type"
    else
        labels="beads-sync"
    fi
    
    # Map beads status to GitHub state
    if [ "$status" = "closed" ]; then
        gh_state="closed"
    else
        gh_state="open"
    fi
    
    # Prepare body with beads reference
    body="**Beads ID:** \`$beads_id\`

$description

---
*This issue is automatically synced from beads. Do not edit manually.*
*Beads Status: \`$status\`*"
    
    if [ -n "$github_number" ]; then
        # Issue exists, check if it needs updating
        echo "   → Already synced as #$github_number"
        
        # Get current GitHub issue state
        current_state=$(gh issue view "$github_number" | grep -i "^state:" | awk '{print tolower($2)}')
        
        if [ "$current_state" != "$gh_state" ]; then
            echo "   → Updating state: $current_state → $gh_state"
            if [ "$gh_state" = "closed" ]; then
                gh issue close "$github_number" --comment "Closed in beads"
            else
                gh issue reopen "$github_number"
            fi
            updated=$((updated + 1))
        else
            echo "   → No changes needed"
            skipped=$((skipped + 1))
        fi
    else
        # Create new GitHub issue
        echo "   → Creating new GitHub issue..."
        
        # Create issue with labels (using multiple --label flags)
        label_args=""
        for label in $labels; do
            label_args="$label_args --label $label"
        done
        
        issue_url=$(gh issue create \
            --title "$title" \
            --body "$body" \
            $label_args)
        
        if [ -n "$issue_url" ]; then
            # Extract issue number from URL (e.g., https://github.com/user/repo/issues/123)
            new_number=$(echo "$issue_url" | grep -oE '[0-9]+$')
            
            echo "   → Created #$new_number"
            
            # If beads issue is already closed, close the GitHub issue too
            if [ "$gh_state" = "closed" ]; then
                gh issue close "$new_number" --comment "Created as closed (already completed in beads)"
            fi
            
            # Store mapping
            jq --arg id "$beads_id" --arg num "$new_number" '. + {($id): $num}' "$MAPPING_FILE" > "$MAPPING_FILE.tmp"
            mv "$MAPPING_FILE.tmp" "$MAPPING_FILE"
            
            created=$((created + 1))
        else
            echo "   ⚠️  Failed to create issue"
        fi
    fi
    
    echo ""
done

echo "================================="
echo "✅ Sync complete!"
echo ""
echo "Summary:"
echo "  Total processed: $count"
echo "  Created: $created"
echo "  Updated: $updated"
echo "  Skipped (no change): $skipped"
echo ""
echo "View issues: https://github.com/$REPO/issues?q=is%3Aissue+label%3Abeads-sync"
echo ""
echo "Mapping stored in: $MAPPING_FILE"
