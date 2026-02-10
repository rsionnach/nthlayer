import React from 'react';
import { createDevApp } from '@backstage/dev-utils';
import { EntityProvider } from '@backstage/plugin-catalog-react';
import { nthlayerPlugin, EntityNthlayerCard } from '../src';

// Mock entity with NthLayer annotation
const mockEntity = {
  apiVersion: 'backstage.io/v1alpha1',
  kind: 'Component',
  metadata: {
    name: 'payment-api',
    description: 'Payment processing API',
    annotations: {
      'nthlayer.dev/entity': '/mock-nthlayer-data.json',
    },
  },
  spec: {
    type: 'service',
    lifecycle: 'production',
    owner: 'payments-team',
  },
};

// Mock NthLayer data for development
const mockNthlayerData = {
  schemaVersion: 'v1',
  generatedAt: new Date().toISOString(),
  service: {
    name: 'payment-api',
    team: 'payments-team',
    tier: 'critical',
    type: 'api',
    description: 'Payment processing API',
    supportModel: 'self',
  },
  slos: [
    {
      name: 'availability',
      target: 99.9,
      window: '30d',
      sloType: 'availability',
      currentValue: 99.95,
      status: 'healthy',
    },
    {
      name: 'latency-p99',
      target: 99.0,
      window: '30d',
      sloType: 'latency',
      currentValue: 99.2,
      status: 'healthy',
    },
  ],
  errorBudget: {
    totalMinutes: 43.2,
    consumedMinutes: 12.5,
    remainingMinutes: 30.7,
    remainingPercent: 71.1,
    burnRate: 0.8,
    status: 'healthy',
  },
  score: {
    score: 92,
    grade: 'A',
    band: 'excellent',
    trend: 'improving',
    components: {
      sloCompliance: 95,
      incidentScore: 90,
      deploySuccessRate: 88,
      errorBudgetRemaining: 95,
    },
  },
  deploymentGate: {
    status: 'APPROVED',
    message: 'Error budget healthy (71.1% remaining)',
    budgetRemainingPercent: 71.1,
    warningThreshold: 20,
    blockingThreshold: 10,
    recommendations: [
      'Budget: 30.7/43.2 minutes remaining',
      'Continue monitoring post-deployment',
    ],
  },
  links: {
    grafanaDashboard: 'https://grafana.example.com/d/payment-api',
    runbook: 'https://docs.example.com/runbooks/payment-api',
    serviceManifest: './services/payment-api.yaml',
    slothSpec: './generated/payment-api/sloth/payment-api.yaml',
    alertsYaml: './generated/payment-api/alerts.yaml',
  },
};

// Create a mock fetch for the dev environment
const originalFetch = window.fetch;
window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
  const url = typeof input === 'string' ? input : input.toString();
  if (url.includes('mock-nthlayer-data.json')) {
    return new Response(JSON.stringify(mockNthlayerData), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  }
  return originalFetch(input, init);
};

createDevApp()
  .registerPlugin(nthlayerPlugin)
  .addPage({
    element: (
      <EntityProvider entity={mockEntity}>
        <EntityNthlayerCard />
      </EntityProvider>
    ),
    title: 'NthLayer Card',
    path: '/nthlayer',
  })
  .render();
