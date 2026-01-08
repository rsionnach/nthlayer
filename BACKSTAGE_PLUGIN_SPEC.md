# NthLayer Backstage Plugin Specification

## Overview

**Feature Name:** NthLayer Backstage Plugin
**Status:** Proposed
**Target Release:** v0.6.0 (after MCP server)
**Estimated Effort:** 3-5 days

### What is Backstage?

Backstage is Spotify's open-source developer portal platform. It provides:
- **Software Catalog** — Service registry with ownership
- **TechDocs** — Documentation
- **Plugins** — Extensible UI components

Backstage Documentation: https://backstage.io/docs

### Why a Backstage Plugin?

Backstage is where developers already go to understand services. Embedding NthLayer surfaces reliability intelligence where teams naturally work:

| Without Plugin | With Plugin |
|----------------|-------------|
| Switch to terminal, run CLI | See reliability in service page |
| Manually correlate ownership | Ownership already in Backstage |
| No visibility for non-SREs | Self-serve reliability insights |
| Separate tool to learn | Integrated into existing workflow |

**Target users:**
- Developers checking service health before changes
- On-call engineers understanding dependencies
- Engineering managers reviewing team reliability
- Platform teams monitoring org-wide posture

---

## Development Approach

### Scaffolding (Recommended)

Use the Backstage CLI to scaffold the plugins from your Backstage repository root:

```bash
# Create backend plugin
yarn new --select backend-plugin
# ? Enter the ID of the plugin: nthlayer
# Creates: plugins/nthlayer-backend/

# Create frontend plugin
yarn new --select frontend-plugin
# ? Enter the ID of the plugin: nthlayer
# Creates: plugins/nthlayer/
```

This generates the correct structure with:
- Package.json with proper dependencies
- TypeScript configuration
- Basic plugin boilerplate
- Dev harness for isolated testing

### Development Workflow

```bash
# 1. Scaffold plugins
yarn new --select backend-plugin   # name: nthlayer
yarn new --select frontend-plugin  # name: nthlayer

# 2. Develop backend in isolation
yarn workspace @internal/plugin-nthlayer-backend start

# 3. Develop frontend in isolation
yarn workspace @internal/plugin-nthlayer start

# 4. Test in full app
yarn dev
```

### Key Backstage Patterns

| Pattern | Description |
|---------|-------------|
| **New Backend System** | Use `createBackendPlugin` from `@backstage/backend-plugin-api` (production-ready) |
| **Legacy Frontend System** | Use `createPlugin` from `@backstage/core-plugin-api` (new frontend system still alpha) |
| **API Factory** | Register APIs with `createApiFactory` for dependency injection |
| **Auth Policies** | Explicitly declare unauthenticated routes with `httpRouter.addAuthPolicy()` |
| **Lazy Loading** | Use dynamic imports for components to reduce bundle size |

---

## Plugin Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Backstage Frontend                                 │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    @nthlayer/backstage-plugin                        │   │
│  │                                                                      │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │   │
│  │  │ EntityCard   │  │ DependencyViz│  │ PortfolioPage│              │   │
│  │  │              │  │              │  │              │              │   │
│  │  │ • Drift      │  │ • Graph      │  │ • All svcs   │              │   │
│  │  │ • Budget     │  │ • Cytoscape  │  │ • Filters    │              │   │
│  │  │ • SLO status │  │ • Interactive│  │ • Risks      │              │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘              │   │
│  │                                                                      │   │
│  └──────────────────────────────────────┬───────────────────────────────┘   │
│                                         │                                   │
└─────────────────────────────────────────┼───────────────────────────────────┘
                                          │ REST API
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Backstage Backend                                  │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                @nthlayer/backstage-plugin-backend                    │   │
│  │                                                                      │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │   │
│  │  │ DriftRouter  │  │ DepsRouter   │  │ PortfolioRtr │              │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘              │   │
│  │                           │                                         │   │
│  │                           ▼                                         │   │
│  │                  ┌──────────────────┐                              │   │
│  │                  │  NthLayerClient  │                              │   │
│  │                  └──────────────────┘                              │   │
│  │                                                                      │   │
│  └──────────────────────────────────────┬───────────────────────────────┘   │
│                                         │                                   │
└─────────────────────────────────────────┼───────────────────────────────────┘
                                          │
                    ┌─────────────────────┼─────────────────────┐
                    │                     │                     │
                    ▼                     ▼                     ▼
            ┌─────────────┐       ┌─────────────┐       ┌─────────────┐
            │  NthLayer   │       │  Prometheus │       │  PagerDuty  │
            │    CLI      │       │             │       │             │
            └─────────────┘       └─────────────┘       └─────────────┘
```

---

## Package Structure

```
plugins/
├── nthlayer/                              # Frontend plugin
│   ├── package.json
│   ├── src/
│   │   ├── index.ts                       # Plugin exports
│   │   ├── plugin.ts                      # Plugin definition
│   │   ├── routes.ts                      # Route definitions
│   │   │
│   │   ├── components/
│   │   │   ├── EntityReliabilityCard/     # Card for entity page
│   │   │   │   ├── EntityReliabilityCard.tsx
│   │   │   │   └── index.ts
│   │   │   │
│   │   │   ├── DependencyGraph/           # Interactive graph viz
│   │   │   │   ├── DependencyGraph.tsx
│   │   │   │   ├── GraphControls.tsx
│   │   │   │   └── index.ts
│   │   │   │
│   │   │   ├── DriftIndicator/            # Drift status display
│   │   │   │   ├── DriftIndicator.tsx
│   │   │   │   ├── DriftChart.tsx
│   │   │   │   └── index.ts
│   │   │   │
│   │   │   ├── SLOStatus/                 # SLO feasibility display
│   │   │   │   ├── SLOStatus.tsx
│   │   │   │   ├── BudgetGauge.tsx
│   │   │   │   └── index.ts
│   │   │   │
│   │   │   ├── BlastRadius/               # Blast radius visualization
│   │   │   │   ├── BlastRadiusCard.tsx
│   │   │   │   └── index.ts
│   │   │   │
│   │   │   └── PortfolioPage/             # Full-page portfolio view
│   │   │       ├── PortfolioPage.tsx
│   │   │       ├── PortfolioTable.tsx
│   │   │       ├── PortfolioFilters.tsx
│   │   │       └── index.ts
│   │   │
│   │   ├── api/
│   │   │   ├── NthLayerApiClient.ts       # API client
│   │   │   └── types.ts                   # TypeScript types
│   │   │
│   │   └── hooks/
│   │       ├── useDrift.ts                # Drift data hook
│   │       ├── useDependencies.ts         # Dependencies hook
│   │       └── usePortfolio.ts            # Portfolio hook
│   │
│   └── dev/                               # Development harness
│       └── index.tsx
│
└── nthlayer-backend/                      # Backend plugin
    ├── package.json
    └── src/
        ├── index.ts                       # Plugin exports
        ├── plugin.ts                      # Plugin definition
        ├── service/
        │   ├── router.ts                  # Express routes
        │   └── NthLayerClient.ts          # Client for NthLayer
        └── types.ts                       # Shared types
```

---

## Dependencies

### Frontend Plugin

```json
// plugins/nthlayer/package.json
{
  "name": "@nthlayer/backstage-plugin",
  "version": "0.1.0",
  "main": "src/index.ts",
  "types": "src/index.ts",
  "dependencies": {
    "@backstage/core-components": "^0.14.0",
    "@backstage/core-plugin-api": "^1.9.0",
    "@backstage/plugin-catalog-react": "^1.11.0",
    "@backstage/theme": "^0.5.0",
    "@material-ui/core": "^4.12.4",
    "@material-ui/icons": "^4.11.3",
    "@material-ui/lab": "^4.0.0-alpha.61",
    "cytoscape": "^3.28.0",
    "cytoscape-dagre": "^2.5.0",
    "react-cytoscapejs": "^2.0.0",
    "recharts": "^2.10.0"
  },
  "peerDependencies": {
    "react": "^17.0.0 || ^18.0.0"
  }
}
```

### Backend Plugin

```json
// plugins/nthlayer-backend/package.json
{
  "name": "@nthlayer/backstage-plugin-backend",
  "version": "0.1.0",
  "main": "src/index.ts",
  "types": "src/index.ts",
  "dependencies": {
    "@backstage/backend-common": "^0.21.0",
    "@backstage/backend-plugin-api": "^0.6.0",
    "@backstage/config": "^1.2.0",
    "express": "^4.18.0",
    "express-promise-router": "^4.1.0",
    "node-fetch": "^2.7.0"
  }
}
```

---

## Backend Plugin Implementation

### Plugin Definition

```typescript
// plugins/nthlayer-backend/src/plugin.ts

import {
  createBackendPlugin,
  coreServices,
} from '@backstage/backend-plugin-api';
import { createRouter } from './service/router';

/**
 * NthLayer backend plugin.
 *
 * Exposes REST endpoints for reliability intelligence:
 * - /drift/:service - Drift analysis
 * - /deps/:service - Dependency discovery
 * - /ownership/:service - Ownership attribution
 * - /validate-slo/:service - SLO feasibility validation
 * - /blast-radius/:service - Impact analysis
 * - /portfolio - Org-wide reliability view
 * - /graph - Dependency graph
 *
 * @public
 */
export const nthLayerPlugin = createBackendPlugin({
  pluginId: 'nthlayer',
  register(env) {
    env.registerInit({
      deps: {
        httpRouter: coreServices.httpRouter,
        logger: coreServices.logger,
        config: coreServices.rootConfig,
      },
      async init({ httpRouter, logger, config }) {
        const router = await createRouter({ logger, config });

        httpRouter.use(router);

        // Auth policies - declare which routes allow unauthenticated access
        // By default, Backstage 1.25+ requires authentication
        httpRouter.addAuthPolicy({
          path: '/health',
          allow: 'unauthenticated',
        });

        // If you want to allow unauthenticated access to all routes
        // (e.g., for internal network deployments), uncomment:
        // httpRouter.addAuthPolicy({
        //   path: '/',
        //   allow: 'unauthenticated',
        // });

        logger.info('NthLayer backend plugin initialized');
      },
    });
  },
});
```

### Plugin Entry Point

```typescript
// plugins/nthlayer-backend/src/index.ts

/**
 * NthLayer Backstage Backend Plugin
 *
 * @packageDocumentation
 */

export { nthLayerPlugin as default } from './plugin';
```

### NthLayer Client

```typescript
// plugins/nthlayer-backend/src/service/NthLayerClient.ts

import { Config } from '@backstage/config';
import { Logger } from 'winston';
import fetch from 'node-fetch';
import { spawn } from 'child_process';

export interface DriftResult {
  service: string;
  window: string;
  analyzedAt: string;
  slos: Array<{
    name: string;
    currentBudget: string;
    trend: string;
    pattern: string;
    severity: 'none' | 'info' | 'warn' | 'critical';
    projection: {
      daysUntilExhaustion: number | null;
      budget30d: string;
    };
    recommendation: string;
  }>;
  overallSeverity: 'none' | 'info' | 'warn' | 'critical';
  summary: string;
}

export interface DependencyResult {
  service: string;
  upstream: Array<{
    service: string;
    type: string;
    confidence: string;
    providers: string[];
  }>;
  downstream: Array<{
    service: string;
    type: string;
    confidence: string;
  }>;
}

export interface OwnershipResult {
  service: string;
  owner: string | null;
  confidence: string;
  source: string | null;
  contacts: {
    slack: string | null;
    email: string | null;
    pagerduty: string | null;
  };
}

export interface SLOValidationResult {
  service: string;
  target: string;
  feasible: boolean;
  serialAvailability: string;
  ceiling: string;
  dependencyChain: Array<{
    service: string;
    availability: number;
  }>;
  recommendations: string[];
}

export interface BlastRadiusResult {
  service: string;
  directDependents: Array<{
    service: string;
    tier: string;
    owner: string | null;
  }>;
  transitiveImpact: {
    totalServices: number;
    byDepth: Record<string, number>;
  };
  teamsAffected: Record<string, {
    services: string[];
    contact: string | null;
  }>;
  estimatedOrgImpact: string;
}

export interface PortfolioResult {
  totalServices: number;
  services: Array<{
    service: string;
    tier: string;
    owner: string | null;
    drift?: string;
    budget?: string;
    dependencyCount?: number;
  }>;
  summary: {
    withDriftWarning: number;
    unowned: number;
  };
}

export class NthLayerClient {
  private readonly mode: 'cli' | 'api';
  private readonly apiUrl?: string;
  private readonly cliPath: string;
  private readonly logger: Logger;

  constructor(config: Config, logger: Logger) {
    this.logger = logger;

    // Determine mode based on config
    const nthlayerConfig = config.getOptionalConfig('nthlayer');
    this.mode = nthlayerConfig?.getOptionalString('mode') as 'cli' | 'api' || 'cli';
    this.apiUrl = nthlayerConfig?.getOptionalString('apiUrl');
    this.cliPath = nthlayerConfig?.getOptionalString('cliPath') || 'nthlayer';

    this.logger.info(`NthLayer client initialized in ${this.mode} mode`);
  }

  async getDrift(service: string, window: string = '30d'): Promise<DriftResult> {
    if (this.mode === 'api' && this.apiUrl) {
      return this.fetchApi(`/drift/${service}?window=${window}`);
    }
    return this.runCli(['drift', service, '--window', window, '--format', 'json']);
  }

  async getDependencies(service: string, depth: number = 2): Promise<DependencyResult> {
    if (this.mode === 'api' && this.apiUrl) {
      return this.fetchApi(`/deps/${service}?depth=${depth}`);
    }
    return this.runCli(['deps', service, '--depth', String(depth), '--format', 'json']);
  }

  async getOwnership(service: string): Promise<OwnershipResult> {
    if (this.mode === 'api' && this.apiUrl) {
      return this.fetchApi(`/ownership/${service}`);
    }
    return this.runCli(['ownership', service, '--format', 'json']);
  }

  async validateSLO(service: string, target?: number): Promise<SLOValidationResult> {
    if (this.mode === 'api' && this.apiUrl) {
      const params = target ? `?target=${target}` : '';
      return this.fetchApi(`/validate-slo/${service}${params}`);
    }
    const args = ['validate-slo', service, '--format', 'json'];
    if (target) {
      args.push('--target', String(target));
    }
    return this.runCli(args);
  }

  async getBlastRadius(service: string): Promise<BlastRadiusResult> {
    if (this.mode === 'api' && this.apiUrl) {
      return this.fetchApi(`/blast-radius/${service}`);
    }
    return this.runCli(['blast-radius', service, '--format', 'json']);
  }

  async getPortfolio(options?: {
    tier?: string;
    includeDrift?: boolean;
    includeDependencies?: boolean;
  }): Promise<PortfolioResult> {
    if (this.mode === 'api' && this.apiUrl) {
      const params = new URLSearchParams();
      if (options?.tier) params.set('tier', options.tier);
      if (options?.includeDrift) params.set('include_drift', 'true');
      if (options?.includeDependencies) params.set('include_deps', 'true');
      return this.fetchApi(`/portfolio?${params}`);
    }

    const args = ['portfolio', '--format', 'json'];
    if (options?.tier) {
      args.push('--tier', options.tier);
    }
    if (options?.includeDrift) {
      args.push('--with-drift');
    }
    if (options?.includeDependencies) {
      args.push('--with-deps');
    }
    return this.runCli(args);
  }

  async getDependencyGraph(): Promise<{
    nodes: Array<{ id: string; aliases: string[] }>;
    edges: Array<{ source: string; target: string; type: string; confidence: number }>;
  }> {
    if (this.mode === 'api' && this.apiUrl) {
      return this.fetchApi('/graph');
    }
    return this.runCli(['graph', 'export', '--format', 'json']);
  }

  private async fetchApi<T>(path: string): Promise<T> {
    const url = `${this.apiUrl}${path}`;
    this.logger.debug(`Fetching ${url}`);

    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`NthLayer API error: ${response.status} ${response.statusText}`);
    }
    return response.json() as Promise<T>;
  }

  private async runCli<T>(args: string[]): Promise<T> {
    return new Promise((resolve, reject) => {
      this.logger.debug(`Running: ${this.cliPath} ${args.join(' ')}`);

      const proc = spawn(this.cliPath, args, {
        env: process.env,
      });

      let stdout = '';
      let stderr = '';

      proc.stdout.on('data', (data) => {
        stdout += data.toString();
      });

      proc.stderr.on('data', (data) => {
        stderr += data.toString();
      });

      proc.on('close', (code) => {
        if (code !== 0) {
          this.logger.error(`NthLayer CLI error: ${stderr}`);
          reject(new Error(`NthLayer CLI exited with code ${code}: ${stderr}`));
          return;
        }

        try {
          resolve(JSON.parse(stdout));
        } catch (e) {
          reject(new Error(`Failed to parse NthLayer output: ${stdout}`));
        }
      });

      proc.on('error', (err) => {
        reject(new Error(`Failed to run NthLayer CLI: ${err.message}`));
      });
    });
  }
}
```

### Router

```typescript
// plugins/nthlayer-backend/src/service/router.ts

import { errorHandler } from '@backstage/backend-common';
import { Config } from '@backstage/config';
import express from 'express';
import Router from 'express-promise-router';
import { Logger } from 'winston';
import { NthLayerClient } from './NthLayerClient';

export interface RouterOptions {
  logger: Logger;
  config: Config;
}

export async function createRouter(
  options: RouterOptions,
): Promise<express.Router> {
  const { logger, config } = options;
  const client = new NthLayerClient(config, logger);

  const router = Router();
  router.use(express.json());

  // Health check
  router.get('/health', (_, response) => {
    response.json({ status: 'ok' });
  });

  // Drift endpoint
  router.get('/drift/:service', async (req, res) => {
    const { service } = req.params;
    const window = (req.query.window as string) || '30d';

    try {
      const result = await client.getDrift(service, window);
      res.json(result);
    } catch (error) {
      logger.error(`Error getting drift for ${service}:`, error);
      res.status(500).json({ error: String(error) });
    }
  });

  // Dependencies endpoint
  router.get('/deps/:service', async (req, res) => {
    const { service } = req.params;
    const depth = parseInt(req.query.depth as string) || 2;

    try {
      const result = await client.getDependencies(service, depth);
      res.json(result);
    } catch (error) {
      logger.error(`Error getting dependencies for ${service}:`, error);
      res.status(500).json({ error: String(error) });
    }
  });

  // Ownership endpoint
  router.get('/ownership/:service', async (req, res) => {
    const { service } = req.params;

    try {
      const result = await client.getOwnership(service);
      res.json(result);
    } catch (error) {
      logger.error(`Error getting ownership for ${service}:`, error);
      res.status(500).json({ error: String(error) });
    }
  });

  // Validate SLO endpoint
  router.get('/validate-slo/:service', async (req, res) => {
    const { service } = req.params;
    const target = req.query.target ? parseFloat(req.query.target as string) : undefined;

    try {
      const result = await client.validateSLO(service, target);
      res.json(result);
    } catch (error) {
      logger.error(`Error validating SLO for ${service}:`, error);
      res.status(500).json({ error: String(error) });
    }
  });

  // Blast radius endpoint
  router.get('/blast-radius/:service', async (req, res) => {
    const { service } = req.params;

    try {
      const result = await client.getBlastRadius(service);
      res.json(result);
    } catch (error) {
      logger.error(`Error getting blast radius for ${service}:`, error);
      res.status(500).json({ error: String(error) });
    }
  });

  // Portfolio endpoint
  router.get('/portfolio', async (req, res) => {
    const tier = req.query.tier as string | undefined;
    const includeDrift = req.query.include_drift === 'true';
    const includeDeps = req.query.include_deps === 'true';

    try {
      const result = await client.getPortfolio({
        tier,
        includeDrift,
        includeDependencies: includeDeps,
      });
      res.json(result);
    } catch (error) {
      logger.error('Error getting portfolio:', error);
      res.status(500).json({ error: String(error) });
    }
  });

  // Graph endpoint
  router.get('/graph', async (_, res) => {
    try {
      const result = await client.getDependencyGraph();
      res.json(result);
    } catch (error) {
      logger.error('Error getting dependency graph:', error);
      res.status(500).json({ error: String(error) });
    }
  });

  router.use(errorHandler());
  return router;
}
```

---

## Frontend Plugin Implementation

### Plugin Definition

```typescript
// plugins/nthlayer/src/plugin.ts

import {
  createPlugin,
  createApiFactory,
  createRoutableExtension,
  createComponentExtension,
  discoveryApiRef,
  fetchApiRef,
} from '@backstage/core-plugin-api';
import { rootRouteRef } from './routes';
import { nthLayerApiRef, NthLayerClient } from './api';

/**
 * NthLayer frontend plugin.
 *
 * Provides UI components for reliability intelligence:
 * - EntityReliabilityCard - Service page overview card
 * - DependencyGraph - Interactive dependency visualization
 * - BlastRadiusCard - Impact analysis card
 * - NthLayerPortfolioPage - Full portfolio view
 *
 * @public
 */
export const nthLayerPlugin = createPlugin({
  id: 'nthlayer',
  routes: {
    root: rootRouteRef,
  },
  apis: [
    // Register API factory for dependency injection
    createApiFactory({
      api: nthLayerApiRef,
      deps: {
        discoveryApi: discoveryApiRef,
        fetchApi: fetchApiRef,
      },
      factory: ({ discoveryApi, fetchApi }) =>
        new NthLayerClient({ discoveryApi, fetchApi }),
    }),
  ],
});

/**
 * Full page component - Portfolio overview
 * @public
 */
export const NthLayerPortfolioPage = nthLayerPlugin.provide(
  createRoutableExtension({
    name: 'NthLayerPortfolioPage',
    component: () =>
      import('./components/PortfolioPage').then(m => m.PortfolioPage),
    mountPoint: rootRouteRef,
  }),
);

/**
 * Entity page card - Reliability status overview
 * @public
 */
export const EntityReliabilityCard = nthLayerPlugin.provide(
  createComponentExtension({
    name: 'EntityReliabilityCard',
    component: {
      lazy: () =>
        import('./components/EntityReliabilityCard').then(
          m => m.EntityReliabilityCard,
        ),
    },
  }),
);

/**
 * Dependency graph - Interactive visualization
 * Can be used standalone or in entity page
 * @public
 */
export const DependencyGraph = nthLayerPlugin.provide(
  createComponentExtension({
    name: 'DependencyGraph',
    component: {
      lazy: () =>
        import('./components/DependencyGraph').then(m => m.DependencyGraph),
    },
  }),
);

/**
 * Blast radius card - Impact analysis
 * @public
 */
export const BlastRadiusCard = nthLayerPlugin.provide(
  createComponentExtension({
    name: 'BlastRadiusCard',
    component: {
      lazy: () =>
        import('./components/BlastRadius').then(m => m.BlastRadiusCard),
    },
  }),
);
```

### Routes

```typescript
// plugins/nthlayer/src/routes.ts

import { createRouteRef } from '@backstage/core-plugin-api';

/**
 * Route reference for the NthLayer portfolio page.
 * Used internally and for external linking.
 */
export const rootRouteRef = createRouteRef({
  id: 'nthlayer',
});
```

### Plugin Entry Point

```typescript
// plugins/nthlayer/src/index.ts

/**
 * NthLayer Backstage Frontend Plugin
 *
 * @packageDocumentation
 */

export {
  nthLayerPlugin,
  NthLayerPortfolioPage,
  EntityReliabilityCard,
  DependencyGraph,
  BlastRadiusCard,
} from './plugin';

export { nthLayerApiRef } from './api';
```

### API Client

```typescript
// plugins/nthlayer/src/api/index.ts

export { nthLayerApiRef, type NthLayerApi } from './NthLayerApi';
export { NthLayerClient } from './NthLayerClient';
```

```typescript
// plugins/nthlayer/src/api/NthLayerApi.ts

import { createApiRef } from '@backstage/core-plugin-api';
import type {
  DriftResult,
  DependencyResult,
  OwnershipResult,
  SLOValidationResult,
  BlastRadiusResult,
  PortfolioResult,
  GraphResult,
} from './types';

/**
 * API for NthLayer reliability intelligence.
 * @public
 */
export interface NthLayerApi {
  getDrift(service: string, window?: string): Promise<DriftResult>;
  getDependencies(service: string, depth?: number): Promise<DependencyResult>;
  getOwnership(service: string): Promise<OwnershipResult>;
  validateSLO(service: string, target?: number): Promise<SLOValidationResult>;
  getBlastRadius(service: string): Promise<BlastRadiusResult>;
  getPortfolio(options?: {
    tier?: string;
    includeDrift?: boolean;
    includeDependencies?: boolean;
  }): Promise<PortfolioResult>;
  getGraph(): Promise<GraphResult>;
}

/**
 * API reference for NthLayer.
 * Used with useApi() hook to access the API.
 * @public
 */
export const nthLayerApiRef = createApiRef<NthLayerApi>({
  id: 'plugin.nthlayer.api',
});
```

```typescript
// plugins/nthlayer/src/api/NthLayerClient.ts

import { DiscoveryApi, FetchApi } from '@backstage/core-plugin-api';
import { NthLayerApi } from './NthLayerApi';
import type {
  DriftResult,
  DependencyResult,
  OwnershipResult,
  SLOValidationResult,
  BlastRadiusResult,
  PortfolioResult,
  GraphResult,
} from './types';

/**
 * Client implementation for NthLayer API.
 * Communicates with the nthlayer-backend plugin.
 */
export class NthLayerClient implements NthLayerApi {
  private readonly discoveryApi: DiscoveryApi;
  private readonly fetchApi: FetchApi;

  constructor(options: { discoveryApi: DiscoveryApi; fetchApi: FetchApi }) {
    this.discoveryApi = options.discoveryApi;
    this.fetchApi = options.fetchApi;
  }

  private async getBaseUrl(): Promise<string> {
    return this.discoveryApi.getBaseUrl('nthlayer');
  }

  private async fetch<T>(path: string): Promise<T> {
    const baseUrl = await this.getBaseUrl();
    const response = await this.fetchApi.fetch(`${baseUrl}${path}`);

    if (!response.ok) {
      const text = await response.text();
      throw new Error(`NthLayer API error: ${response.status} ${response.statusText}: ${text}`);
    }

    return response.json();
  }

  async getDrift(service: string, window = '30d'): Promise<DriftResult> {
    return this.fetch(`/drift/${encodeURIComponent(service)}?window=${window}`);
  }

  async getDependencies(service: string, depth = 2): Promise<DependencyResult> {
    return this.fetch(`/deps/${encodeURIComponent(service)}?depth=${depth}`);
  }

  async getOwnership(service: string): Promise<OwnershipResult> {
    return this.fetch(`/ownership/${encodeURIComponent(service)}`);
  }

  async validateSLO(service: string, target?: number): Promise<SLOValidationResult> {
    const params = target ? `?target=${target}` : '';
    return this.fetch(`/validate-slo/${encodeURIComponent(service)}${params}`);
  }

  async getBlastRadius(service: string): Promise<BlastRadiusResult> {
    return this.fetch(`/blast-radius/${encodeURIComponent(service)}`);
  }

  async getPortfolio(options?: {
    tier?: string;
    includeDrift?: boolean;
    includeDependencies?: boolean;
  }): Promise<PortfolioResult> {
    const params = new URLSearchParams();
    if (options?.tier) params.set('tier', options.tier);
    if (options?.includeDrift) params.set('include_drift', 'true');
    if (options?.includeDependencies) params.set('include_deps', 'true');

    const query = params.toString();
    return this.fetch(`/portfolio${query ? `?${query}` : ''}`);
  }

  async getGraph(): Promise<GraphResult> {
    return this.fetch('/graph');
  }
}
```

```typescript
// plugins/nthlayer/src/api/types.ts

export interface DriftResult {
  service: string;
  window: string;
  analyzedAt: string;
  slos: Array<{
    name: string;
    currentBudget: string;
    trend: string;
    pattern: string;
    severity: 'none' | 'info' | 'warn' | 'critical';
    projection: {
      daysUntilExhaustion: number | null;
      budget30d: string;
    };
    recommendation: string;
  }>;
  overallSeverity: 'none' | 'info' | 'warn' | 'critical';
  summary: string;
}

export interface DependencyResult {
  service: string;
  upstream: Array<{
    service: string;
    type: string;
    confidence: string;
    providers: string[];
  }>;
  downstream: Array<{
    service: string;
    type: string;
    confidence: string;
  }>;
}

export interface OwnershipResult {
  service: string;
  owner: string | null;
  confidence: string;
  source: string | null;
  contacts: {
    slack: string | null;
    email: string | null;
    pagerduty: string | null;
  };
}

export interface SLOValidationResult {
  service: string;
  target: string;
  feasible: boolean;
  serialAvailability: string;
  ceiling: string;
  dependencyChain: Array<{
    service: string;
    availability: number;
  }>;
  recommendations: string[];
}

export interface BlastRadiusResult {
  service: string;
  directDependents: Array<{
    service: string;
    tier: string;
    owner: string | null;
  }>;
  transitiveImpact: {
    totalServices: number;
    byDepth: Record<string, number>;
  };
  teamsAffected: Record<string, {
    services: string[];
    contact: string | null;
  }>;
  estimatedOrgImpact: string;
}

export interface PortfolioResult {
  totalServices: number;
  services: Array<{
    service: string;
    tier: string;
    owner: string | null;
    drift?: string;
    budget?: string;
    dependencyCount?: number;
  }>;
  summary: {
    withDriftWarning: number;
    unowned: number;
  };
}

export interface GraphResult {
  nodes: Array<{ id: string; aliases: string[] }>;
  edges: Array<{ source: string; target: string; type: string; confidence: number }>;
  metadata: {
    builtAt: string;
    providersUsed: string[];
  };
}
```
```

### Entity Reliability Card

```tsx
// plugins/nthlayer/src/components/EntityReliabilityCard/EntityReliabilityCard.tsx

import React from 'react';
import {
  Card,
  CardContent,
  Divider,
  Grid,
  Typography,
  Chip,
  LinearProgress,
  Box,
  Tooltip,
} from '@material-ui/core';
import { makeStyles } from '@material-ui/core/styles';
import {
  StatusOK,
  StatusWarning,
  StatusError,
  StatusPending,
  InfoCard,
  Progress,
} from '@backstage/core-components';
import { useEntity } from '@backstage/plugin-catalog-react';
import { useApi } from '@backstage/core-plugin-api';
import useAsync from 'react-use/lib/useAsync';
import { nthLayerApiRef } from '../../api';
import { DriftIndicator } from '../DriftIndicator';

const useStyles = makeStyles((theme) => ({
  severityChip: {
    marginLeft: theme.spacing(1),
  },
  criticalChip: {
    backgroundColor: theme.palette.error.main,
    color: theme.palette.error.contrastText,
  },
  warnChip: {
    backgroundColor: theme.palette.warning.main,
    color: theme.palette.warning.contrastText,
  },
  okChip: {
    backgroundColor: theme.palette.success.main,
    color: theme.palette.success.contrastText,
  },
  budgetBar: {
    height: 10,
    borderRadius: 5,
  },
  section: {
    marginTop: theme.spacing(2),
  },
}));

/**
 * Card component showing reliability status for an entity.
 * Must be used within an EntityProvider context.
 *
 * @public
 */
export const EntityReliabilityCard = () => {
  const classes = useStyles();
  const { entity } = useEntity();
  const api = useApi(nthLayerApiRef);

  const serviceName = entity.metadata.name;

  const { value: drift, loading: driftLoading, error: driftError } = useAsync(
    () => api.getDrift(serviceName),
    [serviceName],
  );

  const { value: deps, loading: depsLoading } = useAsync(
    () => api.getDependencies(serviceName, 1),
    [serviceName],
  );

  const { value: validation } = useAsync(
    () => api.validateSLO(serviceName),
    [serviceName],
  );

  if (driftLoading || depsLoading) {
    return (
      <InfoCard title="Reliability Status">
        <Progress />
      </InfoCard>
    );
  }

  if (driftError) {
    return (
      <InfoCard title="Reliability Status">
        <Typography color="error">
          Failed to load reliability data: {driftError.message}
        </Typography>
      </InfoCard>
    );
  }

  const getSeverityStatus = (severity: string) => {
    switch (severity) {
      case 'critical':
        return <StatusError />;
      case 'warn':
        return <StatusWarning />;
      case 'none':
      case 'info':
        return <StatusOK />;
      default:
        return <StatusPending />;
    }
  };

  const getSeverityChipClass = (severity: string) => {
    switch (severity) {
      case 'critical':
        return classes.criticalChip;
      case 'warn':
        return classes.warnChip;
      default:
        return classes.okChip;
    }
  };

  // Parse budget percentage
  const budgetPercent = drift?.slos?.[0]?.currentBudget
    ? parseFloat(drift.slos[0].currentBudget.replace('%', ''))
    : 100;

  return (
    <InfoCard
      title="Reliability Status"
      subheader={
        <Box display="flex" alignItems="center">
          {getSeverityStatus(drift?.overallSeverity || 'none')}
          <Chip
            label={drift?.overallSeverity?.toUpperCase() || 'OK'}
            size="small"
            className={`${classes.severityChip} ${getSeverityChipClass(drift?.overallSeverity || 'none')}`}
          />
        </Box>
      }
    >
      <CardContent>
        {/* Error Budget */}
        <Typography variant="subtitle2" gutterBottom>
          Error Budget
        </Typography>
        <Box display="flex" alignItems="center" mb={1}>
          <Box flexGrow={1} mr={2}>
            <Tooltip title={`${budgetPercent.toFixed(1)}% remaining`}>
              <LinearProgress
                variant="determinate"
                value={budgetPercent}
                className={classes.budgetBar}
                color={budgetPercent < 20 ? 'secondary' : 'primary'}
              />
            </Tooltip>
          </Box>
          <Typography variant="body2">{budgetPercent.toFixed(1)}%</Typography>
        </Box>

        <Divider />

        {/* Drift Status */}
        <Box className={classes.section}>
          <Typography variant="subtitle2" gutterBottom>
            Drift Analysis
          </Typography>
          {drift?.slos?.map((slo) => (
            <DriftIndicator key={slo.name} slo={slo} />
          ))}
          {drift?.summary && (
            <Typography variant="body2" color="textSecondary">
              {drift.summary}
            </Typography>
          )}
        </Box>

        <Divider />

        {/* SLO Feasibility */}
        {validation && (
          <Box className={classes.section}>
            <Typography variant="subtitle2" gutterBottom>
              SLO Feasibility
            </Typography>
            <Box display="flex" alignItems="center" mb={1}>
              {validation.feasible ? <StatusOK /> : <StatusWarning />}
              <Typography variant="body2" style={{ marginLeft: 8 }}>
                Target: {validation.target} | Ceiling: {validation.ceiling}
              </Typography>
            </Box>
            {!validation.feasible && validation.recommendations?.[0] && (
              <Typography variant="body2" color="textSecondary">
                ⚠️ {validation.recommendations[0]}
              </Typography>
            )}
          </Box>
        )}

        <Divider />

        {/* Dependencies Summary */}
        <Box className={classes.section}>
          <Typography variant="subtitle2" gutterBottom>
            Dependencies
          </Typography>
          <Grid container spacing={2}>
            <Grid item xs={6}>
              <Typography variant="body2" color="textSecondary">
                Upstream
              </Typography>
              <Typography variant="h6">
                {deps?.upstream?.length || 0}
              </Typography>
            </Grid>
            <Grid item xs={6}>
              <Typography variant="body2" color="textSecondary">
                Downstream
              </Typography>
              <Typography variant="h6">
                {deps?.downstream?.length || 0}
              </Typography>
            </Grid>
          </Grid>
        </Box>
      </CardContent>
    </InfoCard>
  );
};
```

### Drift Indicator Component

```tsx
// plugins/nthlayer/src/components/DriftIndicator/DriftIndicator.tsx

import React from 'react';
import { Box, Typography, Tooltip } from '@material-ui/core';
import { makeStyles } from '@material-ui/core/styles';
import TrendingDownIcon from '@material-ui/icons/TrendingDown';
import TrendingUpIcon from '@material-ui/icons/TrendingUp';
import TrendingFlatIcon from '@material-ui/icons/TrendingFlat';

const useStyles = makeStyles((theme) => ({
  root: {
    display: 'flex',
    alignItems: 'center',
    marginBottom: theme.spacing(1),
  },
  trendDown: {
    color: theme.palette.error.main,
  },
  trendUp: {
    color: theme.palette.success.main,
  },
  trendFlat: {
    color: theme.palette.text.secondary,
  },
  sloName: {
    marginRight: theme.spacing(1),
    fontWeight: 500,
  },
  trend: {
    marginLeft: theme.spacing(1),
  },
}));

interface DriftIndicatorProps {
  slo: {
    name: string;
    currentBudget: string;
    trend: string;
    pattern: string;
    severity: string;
    projection: {
      daysUntilExhaustion: number | null;
      budget30d: string;
    };
  };
}

export const DriftIndicator: React.FC<DriftIndicatorProps> = ({ slo }) => {
  const classes = useStyles();

  // Parse trend to determine direction
  const trendValue = parseFloat(slo.trend.replace('%/week', '').replace('+', ''));
  const isNegative = trendValue < -0.1;
  const isPositive = trendValue > 0.1;

  const getTrendIcon = () => {
    if (isNegative) {
      return <TrendingDownIcon className={classes.trendDown} />;
    }
    if (isPositive) {
      return <TrendingUpIcon className={classes.trendUp} />;
    }
    return <TrendingFlatIcon className={classes.trendFlat} />;
  };

  const getTooltipContent = () => {
    const lines = [
      `Pattern: ${slo.pattern}`,
      `30-day projection: ${slo.projection.budget30d}`,
    ];
    if (slo.projection.daysUntilExhaustion) {
      lines.push(`Exhaustion in: ${slo.projection.daysUntilExhaustion} days`);
    }
    return lines.join('\n');
  };

  return (
    <Tooltip title={getTooltipContent()} arrow>
      <Box className={classes.root}>
        <Typography variant="body2" className={classes.sloName}>
          {slo.name}:
        </Typography>
        <Typography variant="body2">
          {slo.currentBudget}
        </Typography>
        {getTrendIcon()}
        <Typography
          variant="body2"
          className={`${classes.trend} ${isNegative ? classes.trendDown : isPositive ? classes.trendUp : classes.trendFlat}`}
        >
          {slo.trend}
        </Typography>
      </Box>
    </Tooltip>
  );
};
```

### Dependency Graph Component

```tsx
// plugins/nthlayer/src/components/DependencyGraph/DependencyGraph.tsx

import React, { useRef, useState } from 'react';
import CytoscapeComponent from 'react-cytoscapejs';
import cytoscape from 'cytoscape';
import dagre from 'cytoscape-dagre';
import {
  Box,
  Paper,
  Typography,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  IconButton,
  Tooltip,
} from '@material-ui/core';
import { makeStyles } from '@material-ui/core/styles';
import ZoomInIcon from '@material-ui/icons/ZoomIn';
import ZoomOutIcon from '@material-ui/icons/ZoomOut';
import CenterFocusStrongIcon from '@material-ui/icons/CenterFocusStrong';
import { Progress, WarningPanel } from '@backstage/core-components';
import { useApi } from '@backstage/core-plugin-api';
import useAsync from 'react-use/lib/useAsync';
import { nthLayerApiRef } from '../../api';

// Register dagre layout
cytoscape.use(dagre);

const useStyles = makeStyles((theme) => ({
  root: {
    height: '100%',
    display: 'flex',
    flexDirection: 'column',
  },
  controls: {
    padding: theme.spacing(2),
    display: 'flex',
    gap: theme.spacing(2),
    alignItems: 'center',
    flexWrap: 'wrap',
  },
  graphContainer: {
    flexGrow: 1,
    minHeight: 400,
    border: `1px solid ${theme.palette.divider}`,
    borderRadius: theme.shape.borderRadius,
  },
  legend: {
    padding: theme.spacing(1),
    display: 'flex',
    gap: theme.spacing(2),
    justifyContent: 'center',
  },
  legendItem: {
    display: 'flex',
    alignItems: 'center',
    gap: theme.spacing(0.5),
  },
  legendDot: {
    width: 12,
    height: 12,
    borderRadius: '50%',
  },
}));

interface DependencyGraphProps {
  /** Service to highlight in the graph */
  focusService?: string;
  /** Height of the graph container */
  height?: number;
}

/**
 * Interactive dependency graph visualization using Cytoscape.js.
 * Can be used standalone or within an entity page.
 *
 * @public
 */
export const DependencyGraph: React.FC<DependencyGraphProps> = ({
  focusService,
  height = 500,
}) => {
  const classes = useStyles();
  const api = useApi(nthLayerApiRef);
  const cyRef = useRef<cytoscape.Core | null>(null);
  const [layout, setLayout] = useState('dagre');

  const { value: graphData, loading, error } = useAsync(
    () => api.getGraph(),
    [],
  );

  // Build cytoscape elements from graph data
  const elements = React.useMemo(() => {
    if (!graphData) return [];

    const nodes = graphData.nodes.map((node) => ({
      data: {
        id: node.id,
        label: node.id,
        isFocus: node.id === focusService,
      },
    }));

    const edges = graphData.edges.map((edge, idx) => ({
      data: {
        id: `edge-${idx}`,
        source: edge.source,
        target: edge.target,
        type: edge.type,
        confidence: edge.confidence,
      },
    }));

    return [...nodes, ...edges];
  }, [graphData, focusService]);

  // Cytoscape stylesheet
  const stylesheet: cytoscape.Stylesheet[] = [
    {
      selector: 'node',
      style: {
        'background-color': '#6366f1',
        label: 'data(label)',
        color: '#fff',
        'text-valign': 'center',
        'text-halign': 'center',
        'font-size': '10px',
        width: 60,
        height: 60,
      },
    },
    {
      selector: 'node[?isFocus]',
      style: {
        'background-color': '#f59e0b',
        'border-width': 3,
        'border-color': '#d97706',
        width: 80,
        height: 80,
      },
    },
    {
      selector: 'edge',
      style: {
        width: 2,
        'line-color': '#94a3b8',
        'target-arrow-color': '#94a3b8',
        'target-arrow-shape': 'triangle',
        'curve-style': 'bezier',
      },
    },
    {
      selector: 'edge[type = "datastore"]',
      style: {
        'line-color': '#22c55e',
        'target-arrow-color': '#22c55e',
        'line-style': 'dashed',
      },
    },
    {
      selector: 'edge[type = "queue"]',
      style: {
        'line-color': '#8b5cf6',
        'target-arrow-color': '#8b5cf6',
      },
    },
    {
      selector: 'edge[type = "external"]',
      style: {
        'line-color': '#ef4444',
        'target-arrow-color': '#ef4444',
        'line-style': 'dotted',
      },
    },
  ];

  const handleZoomIn = () => {
    cyRef.current?.zoom(cyRef.current.zoom() * 1.2);
  };

  const handleZoomOut = () => {
    cyRef.current?.zoom(cyRef.current.zoom() / 1.2);
  };

  const handleFit = () => {
    cyRef.current?.fit();
  };

  if (loading) {
    return <Progress />;
  }

  if (error) {
    return (
      <WarningPanel title="Failed to load dependency graph">
        {error.message}
      </WarningPanel>
    );
  }

  return (
    <Box className={classes.root}>
      <Box className={classes.controls}>
        <FormControl variant="outlined" size="small" style={{ minWidth: 120 }}>
          <InputLabel>Layout</InputLabel>
          <Select
            value={layout}
            onChange={(e) => setLayout(e.target.value as string)}
            label="Layout"
          >
            <MenuItem value="dagre">Hierarchical</MenuItem>
            <MenuItem value="circle">Circle</MenuItem>
            <MenuItem value="grid">Grid</MenuItem>
            <MenuItem value="cose">Force-directed</MenuItem>
          </Select>
        </FormControl>

        <Box display="flex" alignItems="center" style={{ gap: 4 }}>
          <Tooltip title="Zoom In">
            <IconButton size="small" onClick={handleZoomIn}>
              <ZoomInIcon />
            </IconButton>
          </Tooltip>
          <Tooltip title="Zoom Out">
            <IconButton size="small" onClick={handleZoomOut}>
              <ZoomOutIcon />
            </IconButton>
          </Tooltip>
          <Tooltip title="Fit to View">
            <IconButton size="small" onClick={handleFit}>
              <CenterFocusStrongIcon />
            </IconButton>
          </Tooltip>
        </Box>
      </Box>

      <Paper className={classes.graphContainer} style={{ height }}>
        <CytoscapeComponent
          elements={elements}
          stylesheet={stylesheet}
          layout={{ name: layout }}
          style={{ width: '100%', height: '100%' }}
          cy={(cy) => {
            cyRef.current = cy;
          }}
        />
      </Paper>

      <Box className={classes.legend}>
        <Box className={classes.legendItem}>
          <Box className={classes.legendDot} style={{ backgroundColor: '#6366f1' }} />
          <Typography variant="caption">Service</Typography>
        </Box>
        <Box className={classes.legendItem}>
          <Box className={classes.legendDot} style={{ backgroundColor: '#f59e0b' }} />
          <Typography variant="caption">Focus</Typography>
        </Box>
        <Box className={classes.legendItem}>
          <Box className={classes.legendDot} style={{ backgroundColor: '#22c55e' }} />
          <Typography variant="caption">Datastore</Typography>
        </Box>
        <Box className={classes.legendItem}>
          <Box className={classes.legendDot} style={{ backgroundColor: '#8b5cf6' }} />
          <Typography variant="caption">Queue</Typography>
        </Box>
        <Box className={classes.legendItem}>
          <Box className={classes.legendDot} style={{ backgroundColor: '#ef4444' }} />
          <Typography variant="caption">External</Typography>
        </Box>
      </Box>
    </Box>
  );
};
```

### Portfolio Page

```tsx
// plugins/nthlayer/src/components/PortfolioPage/PortfolioPage.tsx

import React, { useState } from 'react';
import {
  Content,
  ContentHeader,
  Header,
  HeaderLabel,
  Page,
  SupportButton,
  Table,
  TableColumn,
  Progress,
  WarningPanel,
} from '@backstage/core-components';
import {
  Box,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Chip,
  Typography,
  Grid,
  Paper,
} from '@material-ui/core';
import { makeStyles } from '@material-ui/core/styles';
import { useApi } from '@backstage/core-plugin-api';
import useAsync from 'react-use/lib/useAsync';
import { nthLayerApiRef } from '../../api';
import { DependencyGraph } from '../DependencyGraph';

const useStyles = makeStyles((theme) => ({
  filters: {
    marginBottom: theme.spacing(2),
    display: 'flex',
    gap: theme.spacing(2),
  },
  summaryCard: {
    padding: theme.spacing(2),
    textAlign: 'center',
  },
  summaryValue: {
    fontSize: '2rem',
    fontWeight: 'bold',
  },
  criticalChip: {
    backgroundColor: theme.palette.error.main,
    color: theme.palette.error.contrastText,
  },
  warnChip: {
    backgroundColor: theme.palette.warning.main,
    color: theme.palette.warning.contrastText,
  },
  okChip: {
    backgroundColor: theme.palette.success.main,
    color: theme.palette.success.contrastText,
  },
}));

/**
 * Full-page portfolio view showing reliability across all services.
 *
 * @public
 */
export const PortfolioPage = () => {
  const classes = useStyles();
  const api = useApi(nthLayerApiRef);
  const [tierFilter, setTierFilter] = useState<string>('all');
  const [includeDrift, setIncludeDrift] = useState(true);

  const { value: portfolio, loading, error } = useAsync(
    () => api.getPortfolio({
      tier: tierFilter !== 'all' ? tierFilter : undefined,
      includeDrift,
      includeDependencies: true,
    }),
    [tierFilter, includeDrift],
  );

  const columns: TableColumn[] = [
    {
      title: 'Service',
      field: 'service',
      render: (row: any) => (
        <Typography variant="body2" style={{ fontWeight: 500 }}>
          {row.service}
        </Typography>
      ),
    },
    {
      title: 'Tier',
      field: 'tier',
      render: (row: any) => (
        <Chip label={row.tier} size="small" variant="outlined" />
      ),
    },
    {
      title: 'Owner',
      field: 'owner',
      render: (row: any) => row.owner || <em>Unowned</em>,
    },
    {
      title: 'Budget',
      field: 'budget',
      render: (row: any) => row.budget || '-',
    },
    {
      title: 'Drift',
      field: 'drift',
      render: (row: any) => {
        if (!row.drift) return '-';
        const chipClass =
          row.drift === 'critical' ? classes.criticalChip :
          row.drift === 'warn' ? classes.warnChip : classes.okChip;
        return (
          <Chip
            label={row.drift.toUpperCase()}
            size="small"
            className={chipClass}
          />
        );
      },
    },
    {
      title: 'Dependencies',
      field: 'dependencyCount',
      render: (row: any) => row.dependencyCount ?? '-',
    },
  ];

  if (error) {
    return (
      <Page themeId="tool">
        <Header title="Reliability Portfolio" />
        <Content>
          <WarningPanel title="Failed to load portfolio">
            {error.message}
          </WarningPanel>
        </Content>
      </Page>
    );
  }

  return (
    <Page themeId="tool">
      <Header title="Reliability Portfolio" subtitle="Service reliability posture overview">
        <HeaderLabel label="Services" value={String(portfolio?.totalServices || 0)} />
        <HeaderLabel label="At Risk" value={String(portfolio?.summary?.withDriftWarning || 0)} />
      </Header>
      <Content>
        <ContentHeader title="">
          <SupportButton>
            NthLayer reliability portfolio shows the health of all services.
          </SupportButton>
        </ContentHeader>

        {/* Summary Cards */}
        <Grid container spacing={3} style={{ marginBottom: 24 }}>
          <Grid item xs={12} md={3}>
            <Paper className={classes.summaryCard}>
              <Typography variant="subtitle2" color="textSecondary">
                Total Services
              </Typography>
              <Typography className={classes.summaryValue}>
                {portfolio?.totalServices || 0}
              </Typography>
            </Paper>
          </Grid>
          <Grid item xs={12} md={3}>
            <Paper className={classes.summaryCard}>
              <Typography variant="subtitle2" color="textSecondary">
                With Drift Warning
              </Typography>
              <Typography className={classes.summaryValue} style={{ color: '#f59e0b' }}>
                {portfolio?.summary?.withDriftWarning || 0}
              </Typography>
            </Paper>
          </Grid>
          <Grid item xs={12} md={3}>
            <Paper className={classes.summaryCard}>
              <Typography variant="subtitle2" color="textSecondary">
                Unowned
              </Typography>
              <Typography className={classes.summaryValue} style={{ color: '#ef4444' }}>
                {portfolio?.summary?.unowned || 0}
              </Typography>
            </Paper>
          </Grid>
          <Grid item xs={12} md={3}>
            <Paper className={classes.summaryCard}>
              <Typography variant="subtitle2" color="textSecondary">
                Healthy
              </Typography>
              <Typography className={classes.summaryValue} style={{ color: '#22c55e' }}>
                {(portfolio?.totalServices || 0) - (portfolio?.summary?.withDriftWarning || 0)}
              </Typography>
            </Paper>
          </Grid>
        </Grid>

        {/* Filters */}
        <Box className={classes.filters}>
          <FormControl variant="outlined" size="small" style={{ minWidth: 120 }}>
            <InputLabel>Tier</InputLabel>
            <Select
              value={tierFilter}
              onChange={(e) => setTierFilter(e.target.value as string)}
              label="Tier"
            >
              <MenuItem value="all">All Tiers</MenuItem>
              <MenuItem value="critical">Critical</MenuItem>
              <MenuItem value="standard">Standard</MenuItem>
              <MenuItem value="low">Low</MenuItem>
            </Select>
          </FormControl>
        </Box>

        {/* Services Table */}
        <Table
          title="Services"
          options={{
            search: true,
            paging: true,
            pageSize: 20,
            sorting: true,
          }}
          columns={columns}
          data={portfolio?.services || []}
          isLoading={loading}
        />

        {/* Dependency Graph */}
        <Box mt={4}>
          <Typography variant="h6" gutterBottom>
            Dependency Graph
          </Typography>
          <DependencyGraph height={600} />
        </Box>
      </Content>
    </Page>
  );
};
```

---

## Integration

### App Configuration

```yaml
# app-config.yaml

nthlayer:
  # Mode: 'cli' to invoke NthLayer CLI, 'api' to call NthLayer HTTP API
  mode: cli

  # Path to NthLayer CLI (if mode: cli)
  cliPath: /usr/local/bin/nthlayer

  # NthLayer API URL (if mode: api)
  # apiUrl: http://nthlayer-api:8080

# Proxy configuration (alternative to backend plugin for simple setups)
# proxy:
#   endpoints:
#     '/nthlayer':
#       target: 'http://nthlayer-api:8080'
#       changeOrigin: true
```

### Backend Registration (New Backend System)

```typescript
// packages/backend/src/index.ts

import { createBackend } from '@backstage/backend-defaults';

const backend = createBackend();

// Core plugins
backend.add(import('@backstage/plugin-app-backend'));
backend.add(import('@backstage/plugin-catalog-backend'));
// ... other plugins

// Add NthLayer backend plugin
backend.add(import('@internal/plugin-nthlayer-backend'));

backend.start();
```

### Frontend App Registration

```typescript
// packages/app/src/App.tsx

import { createApp } from '@backstage/app-defaults';
import { AppRouter, FlatRoutes } from '@backstage/core-app-api';

// Import NthLayer plugin
import { NthLayerPortfolioPage } from '@internal/plugin-nthlayer';

const app = createApp({
  // ... other config
});

const routes = (
  <FlatRoutes>
    {/* ... other routes */}

    {/* NthLayer portfolio page */}
    <Route path="/nthlayer" element={<NthLayerPortfolioPage />} />
  </FlatRoutes>
);

export default app.createRoot(
  <>
    <AlertDisplay />
    <OAuthRequestDialog />
    <AppRouter>
      <Root>{routes}</Root>
    </AppRouter>
  </>,
);
```

### Entity Page Integration

```typescript
// packages/app/src/components/catalog/EntityPage.tsx

import React from 'react';
import { Grid } from '@material-ui/core';
import {
  EntityAboutCard,
  EntityLinksCard,
  EntityLayout,
} from '@backstage/plugin-catalog';
import { EntityCatalogGraphCard } from '@backstage/plugin-catalog-graph';

// Import NthLayer components
import {
  EntityReliabilityCard,
  DependencyGraph,
  BlastRadiusCard,
} from '@internal/plugin-nthlayer';

// Overview content with reliability card
const overviewContent = (
  <Grid container spacing={3} alignItems="stretch">
    <Grid item md={6}>
      <EntityAboutCard variant="gridItem" />
    </Grid>
    <Grid item md={6}>
      {/* NthLayer reliability status card */}
      <EntityReliabilityCard />
    </Grid>
    <Grid item md={6}>
      <EntityLinksCard />
    </Grid>
    <Grid item md={6}>
      {/* NthLayer blast radius card */}
      <BlastRadiusCard />
    </Grid>
  </Grid>
);

// Service entity page with reliability tab
const serviceEntityPage = (
  <EntityLayout>
    <EntityLayout.Route path="/" title="Overview">
      {overviewContent}
    </EntityLayout.Route>

    {/* Add dependencies tab */}
    <EntityLayout.Route path="/dependencies" title="Dependencies">
      <DependencyGraph />
    </EntityLayout.Route>

    <EntityLayout.Route path="/diagram" title="Diagram">
      <EntityCatalogGraphCard variant="gridItem" height={400} />
    </EntityLayout.Route>

    {/* ... other routes */}
  </EntityLayout>
);

// Apply to component entity page as well
const componentEntityPage = serviceEntityPage;

// Export entity pages
export const entityPage = (
  <EntitySwitch>
    <EntitySwitch.Case if={isKind('component')} children={componentEntityPage} />
    <EntitySwitch.Case if={isKind('api')} children={apiEntityPage} />
    <EntitySwitch.Case>{defaultEntityPage}</EntitySwitch.Case>
  </EntitySwitch>
);
```

### Sidebar Navigation

```typescript
// packages/app/src/components/Root/Root.tsx

import React, { PropsWithChildren } from 'react';
import { Sidebar, SidebarItem, SidebarPage } from '@backstage/core-components';
import LayersIcon from '@material-ui/icons/Layers';
import HomeIcon from '@material-ui/icons/Home';
import CategoryIcon from '@material-ui/icons/Category';

export const Root = ({ children }: PropsWithChildren<{}>) => (
  <SidebarPage>
    <Sidebar>
      <SidebarItem icon={HomeIcon} to="/" text="Home" />
      <SidebarItem icon={CategoryIcon} to="catalog" text="Catalog" />

      {/* Add NthLayer to sidebar */}
      <SidebarItem icon={LayersIcon} to="nthlayer" text="Reliability" />
    </Sidebar>
    {children}
  </SidebarPage>
);
```

---

## Screenshots (Wireframes)

### Entity Reliability Card

```
┌─────────────────────────────────────────┐
│ Reliability Status            ● WARN    │
├─────────────────────────────────────────┤
│                                         │
│ Error Budget                            │
│ ████████████████░░░░░░░░░░░░░░░  72.3% │
│                                         │
│ ─────────────────────────────────────── │
│                                         │
│ Drift Analysis                          │
│ availability: 72.3%  ↘ -0.52%/week     │
│ latency_p99:  89.1%  → stable          │
│                                         │
│ Budget declining at 0.52%/week.        │
│                                         │
│ ─────────────────────────────────────── │
│                                         │
│ SLO Feasibility                         │
│ ● Target: 99.95% | Ceiling: 99.89%     │
│ ⚠️ Consider reducing target to 99.9%   │
│                                         │
│ ─────────────────────────────────────── │
│                                         │
│ Dependencies                            │
│   Upstream      Downstream              │
│      4              7                   │
│                                         │
└─────────────────────────────────────────┘
```

### Portfolio Page

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Reliability Portfolio                                                      │
│  Service reliability posture overview                     Services: 47     │
│                                                           At Risk: 3       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐           │
│  │ Total      │  │ At Risk    │  │ Unowned    │  │ Healthy    │           │
│  │    47      │  │     3      │  │     2      │  │    44      │           │
│  └────────────┘  └────────────┘  └────────────┘  └────────────┘           │
│                                                                             │
│  Tier: [All Tiers ▼]                                        🔍 Search      │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │ Service        │ Tier     │ Owner          │ Budget │ Drift  │ Deps  │ │
│  ├───────────────────────────────────────────────────────────────────────┤ │
│  │ payment-api    │ critical │ payments-team  │ 72%    │ WARN   │ 4     │ │
│  │ user-service   │ critical │ identity-squad │ 91%    │ OK     │ 3     │ │
│  │ order-service  │ critical │ orders-team    │ 45%    │ CRITICAL│ 5    │ │
│  │ analytics-api  │ low      │ data-eng       │ 23%    │ OK     │ 2     │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│  Dependency Graph                                                           │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │                        [Interactive Cytoscape Graph]                   │ │
│  │                                                                        │ │
│  │            ┌─────────┐                                                │ │
│  │            │ user-   │                                                │ │
│  │            │ service │                                                │ │
│  │            └────┬────┘                                                │ │
│  │           ┌─────┴─────┐                                               │ │
│  │     ┌─────┴───┐   ┌───┴─────┐                                        │ │
│  │     │payment- │   │ order-  │                                        │ │
│  │     │  api    │   │ service │                                        │ │
│  │     └────┬────┘   └────┬────┘                                        │ │
│  │          │             │                                              │ │
│  │     ┌────┴────┐   ┌────┴────┐                                        │ │
│  │     │postgresql│  │  kafka  │                                        │ │
│  │     └─────────┘   └─────────┘                                        │ │
│  │                                                                        │ │
│  │  ● Service  ● Datastore  ● Queue  ● External                         │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Hooks

React hooks for accessing NthLayer data in components.

```typescript
// plugins/nthlayer/src/hooks/useDrift.ts

import { useApi } from '@backstage/core-plugin-api';
import { useEntity } from '@backstage/plugin-catalog-react';
import useAsync from 'react-use/lib/useAsync';
import { nthLayerApiRef } from '../api';

/**
 * Hook to fetch drift data for the current entity.
 */
export function useDrift(window = '30d') {
  const { entity } = useEntity();
  const api = useApi(nthLayerApiRef);
  const serviceName = entity.metadata.name;

  return useAsync(
    () => api.getDrift(serviceName, window),
    [serviceName, window],
  );
}
```

```typescript
// plugins/nthlayer/src/hooks/useDependencies.ts

import { useApi } from '@backstage/core-plugin-api';
import { useEntity } from '@backstage/plugin-catalog-react';
import useAsync from 'react-use/lib/useAsync';
import { nthLayerApiRef } from '../api';

/**
 * Hook to fetch dependencies for the current entity.
 */
export function useDependencies(depth = 2) {
  const { entity } = useEntity();
  const api = useApi(nthLayerApiRef);
  const serviceName = entity.metadata.name;

  return useAsync(
    () => api.getDependencies(serviceName, depth),
    [serviceName, depth],
  );
}
```

```typescript
// plugins/nthlayer/src/hooks/useOwnership.ts

import { useApi } from '@backstage/core-plugin-api';
import { useEntity } from '@backstage/plugin-catalog-react';
import useAsync from 'react-use/lib/useAsync';
import { nthLayerApiRef } from '../api';

/**
 * Hook to fetch ownership for the current entity.
 */
export function useOwnership() {
  const { entity } = useEntity();
  const api = useApi(nthLayerApiRef);
  const serviceName = entity.metadata.name;

  return useAsync(
    () => api.getOwnership(serviceName),
    [serviceName],
  );
}
```

```typescript
// plugins/nthlayer/src/hooks/usePortfolio.ts

import { useApi } from '@backstage/core-plugin-api';
import useAsync from 'react-use/lib/useAsync';
import { nthLayerApiRef } from '../api';

/**
 * Hook to fetch portfolio data (not tied to entity).
 */
export function usePortfolio(options?: {
  tier?: string;
  includeDrift?: boolean;
  includeDependencies?: boolean;
}) {
  const api = useApi(nthLayerApiRef);

  return useAsync(
    () => api.getPortfolio(options),
    [options?.tier, options?.includeDrift, options?.includeDependencies],
  );
}
```

---

## Summary

This Backstage plugin spec provides:

**Backend Plugin (`@internal/plugin-nthlayer-backend`):**
- Uses new backend system with `createBackendPlugin`
- Express router with REST endpoints
- `NthLayerClient` supporting CLI and API modes
- Auth policies for endpoint security
- Endpoints: `/drift`, `/deps`, `/ownership`, `/validate-slo`, `/blast-radius`, `/portfolio`, `/graph`, `/health`

**Frontend Plugin (`@internal/plugin-nthlayer`):**
- Uses `createPlugin` with `createApiFactory` for API injection
- Lazy-loaded components for performance
- `EntityReliabilityCard` — Service page overview card
- `DependencyGraph` — Interactive Cytoscape.js visualization
- `DriftIndicator` — Trend indicators with tooltips
- `BlastRadiusCard` — Impact analysis card
- `PortfolioPage` — Full-page portfolio view with table and graph

**Integration Points:**
- Entity page cards via `EntityReliabilityCard`
- Dedicated `/nthlayer` route
- Sidebar navigation
- Entity page `/dependencies` tab

**Visualization:**
- Cytoscape.js for dependency graphs (with dagre layout)
- Recharts for trend charts
- Material-UI for consistent Backstage styling

**Development Approach:**
- Scaffold with `yarn new --select backend-plugin` and `yarn new --select frontend-plugin`
- Develop in isolation with `yarn workspace @internal/plugin-nthlayer start`
- Test with full app via `yarn dev`

**Estimated Implementation:** 3-5 days (assumes backend APIs already exist)
