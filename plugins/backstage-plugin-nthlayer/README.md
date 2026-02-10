# NthLayer Backstage Plugin

Display NthLayer reliability data (SLOs, error budgets, deployment gates) in your Backstage service catalog.

## Features

- **Reliability Score**: Letter grade (A-F) with trend indicator
- **SLO List**: Visual status of all defined SLOs with targets and current values
- **Error Budget Gauge**: Progress bar showing budget consumption
- **Deployment Gate Status**: APPROVED/WARNING/BLOCKED status with recommendations

## Installation

### 1. Install the plugin

```bash
# From your Backstage root directory
yarn add --cwd packages/app @internal/plugin-nthlayer
```

### 2. Add to Entity Page

In `packages/app/src/components/catalog/EntityPage.tsx`:

```tsx
import { EntityNthlayerCard, isNthlayerAvailable } from '@internal/plugin-nthlayer';

// Add to your service entity page
const serviceEntityPage = (
  <EntityLayout>
    <EntityLayout.Route path="/" title="Overview">
      <Grid container spacing={3}>
        {/* Other cards... */}

        <EntitySwitch>
          <EntitySwitch.Case if={isNthlayerAvailable}>
            <Grid item xs={12} md={6}>
              <EntityNthlayerCard />
            </Grid>
          </EntitySwitch.Case>
        </EntitySwitch>
      </Grid>
    </EntityLayout.Route>

    {/* Or as a dedicated tab */}
    <EntityLayout.Route path="/reliability" title="Reliability">
      <EntityNthlayerCard />
    </EntityLayout.Route>
  </EntityLayout>
);
```

### 3. Annotate your entities

Add the `nthlayer.dev/entity` annotation to your `catalog-info.yaml`:

```yaml
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: payment-api
  annotations:
    nthlayer.dev/entity: ./generated/payment-api/backstage.json
spec:
  type: service
  owner: payments-team
```

### 4. Generate the JSON artifact

Run NthLayer to generate the `backstage.json` file. Both OpenSRM and legacy formats are supported:

```bash
# OpenSRM format (recommended)
nthlayer apply payment-api.reliability.yaml

# Legacy format (still supported)
nthlayer apply services/payment-api.yaml

# Or generate only the Backstage artifact
nthlayer generate-backstage payment-api.reliability.yaml
```

This creates `generated/payment-api/backstage.json` which the plugin reads.

**Format auto-detection**: The generator automatically detects whether your file uses OpenSRM (`apiVersion: srm/v1`) or legacy (`service:` + `resources:`) format.

## Configuration

The plugin reads the JSON path from the `nthlayer.dev/entity` annotation. The path can be:

- **Relative path**: `./generated/payment-api/backstage.json` (resolved from catalog location)
- **Absolute URL**: `https://artifacts.example.com/payment-api/backstage.json`

## Data Flow

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ nthlayer apply  │ --> │ backstage.json   │ --> │ Backstage UI    │
│ (CI/CD)         │     │ (static file)    │     │ (this plugin)   │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

1. **Generate**: `nthlayer apply` creates `backstage.json` alongside other artifacts
2. **Store**: Commit to repo, upload to S3, or serve via artifact server
3. **Display**: Plugin fetches JSON and renders the reliability card

## Development

```bash
# Start isolated dev server
cd plugins/backstage-plugin-nthlayer
yarn start

# Run tests
yarn test

# Build
yarn build
```

## Components

| Component | Description |
|-----------|-------------|
| `EntityNthlayerCard` | Main card component for entity pages |
| `EntityNthlayerContent` | Content without InfoCard wrapper |
| `isNthlayerAvailable` | Helper to check if annotation exists |
| `ScoreBadge` | Letter grade with trend arrow |
| `SloList` | List of SLOs with status indicators |
| `BudgetGauge` | Error budget progress bar |
| `GateStatus` | Deployment gate status chip |

## JSON Schema

The plugin expects JSON conforming to the NthLayer Backstage entity schema:

```json
{
  "schemaVersion": "v1",
  "generatedAt": "2024-01-15T10:30:00Z",
  "service": {
    "name": "payment-api",
    "team": "payments",
    "tier": "critical",
    "type": "api"
  },
  "slos": [...],
  "errorBudget": {...},
  "score": {...},
  "deploymentGate": {...},
  "links": {...}
}
```

See `src/nthlayer/schemas/backstage-entity.schema.json` for the full schema.

## Full Documentation

See the complete integration guide at [docs/backstage-integration.md](../../docs/backstage-integration.md) for:

- CI/CD pipeline examples (GitHub Actions, GitLab CI, Jenkins)
- Artifact storage options (repo, S3, GCS)
- Troubleshooting guide
- Architecture decisions

## License

Apache-2.0
