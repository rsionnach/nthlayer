// Mock service data for the interactive demo

export interface DependencyData {
  name: string;
  type: 'service' | 'datastore' | 'external' | 'queue';
  availability: number;
  critical: boolean;
}

export interface DriftData {
  sloName: string;
  currentBudget: number;
  trend: number; // percent per week, negative = declining
  pattern: 'stable' | 'gradual_decline' | 'sudden_drop' | 'recovery' | 'volatile';
  severity: 'none' | 'info' | 'warn' | 'critical';
  daysUntilExhaustion: number | null;
  projectedBudget30d: number;
}

export interface ServiceData {
  name: string;
  tier: 'critical' | 'standard' | 'low';
  owner: string;
  dependencies: DependencyData[];
  drift: DriftData;
  budget: number;
}

export const SERVICES: Record<string, ServiceData> = {
  'payment-api': {
    name: 'payment-api',
    tier: 'critical',
    owner: 'payments-team',
    dependencies: [
      { name: 'user-service', type: 'service', availability: 0.999, critical: true },
      { name: 'postgresql', type: 'datastore', availability: 0.9999, critical: true },
      { name: 'stripe-api', type: 'external', availability: 0.9995, critical: true },
      { name: 'redis', type: 'datastore', availability: 0.9999, critical: false },
    ],
    drift: {
      sloName: 'availability',
      currentBudget: 0.723,
      trend: -0.0052,
      pattern: 'gradual_decline',
      severity: 'warn',
      daysUntilExhaustion: 47,
      projectedBudget30d: 0.567,
    },
    budget: 0.723,
  },

  'user-service': {
    name: 'user-service',
    tier: 'critical',
    owner: 'identity-squad',
    dependencies: [
      { name: 'postgresql', type: 'datastore', availability: 0.9999, critical: true },
      { name: 'redis', type: 'datastore', availability: 0.9999, critical: true },
      { name: 'auth0', type: 'external', availability: 0.9995, critical: true },
    ],
    drift: {
      sloName: 'availability',
      currentBudget: 0.91,
      trend: 0.001,
      pattern: 'stable',
      severity: 'none',
      daysUntilExhaustion: null,
      projectedBudget30d: 0.94,
    },
    budget: 0.91,
  },

  'order-service': {
    name: 'order-service',
    tier: 'critical',
    owner: 'orders-team',
    dependencies: [
      { name: 'payment-api', type: 'service', availability: 0.999, critical: true },
      { name: 'user-service', type: 'service', availability: 0.999, critical: true },
      { name: 'inventory-api', type: 'service', availability: 0.995, critical: true },
      { name: 'postgresql', type: 'datastore', availability: 0.9999, critical: true },
      { name: 'kafka', type: 'queue', availability: 0.9999, critical: false },
    ],
    drift: {
      sloName: 'availability',
      currentBudget: 0.45,
      trend: -0.02,
      pattern: 'sudden_drop',
      severity: 'critical',
      daysUntilExhaustion: 12,
      projectedBudget30d: 0.0,
    },
    budget: 0.45,
  },

  'analytics-api': {
    name: 'analytics-api',
    tier: 'low',
    owner: 'data-eng',
    dependencies: [
      { name: 'clickhouse', type: 'datastore', availability: 0.995, critical: true },
      { name: 'kafka', type: 'queue', availability: 0.9999, critical: true },
    ],
    drift: {
      sloName: 'availability',
      currentBudget: 0.23,
      trend: -0.001,
      pattern: 'stable',
      severity: 'info',
      daysUntilExhaustion: 180,
      projectedBudget30d: 0.20,
    },
    budget: 0.23,
  },
};

// Default/fallback for unknown services
export const DEFAULT_SERVICE: ServiceData = {
  name: 'unknown-service',
  tier: 'standard',
  owner: 'platform-team',
  dependencies: [
    { name: 'postgresql', type: 'datastore', availability: 0.9999, critical: true },
  ],
  drift: {
    sloName: 'availability',
    currentBudget: 0.85,
    trend: 0,
    pattern: 'stable',
    severity: 'none',
    daysUntilExhaustion: null,
    projectedBudget30d: 0.85,
  },
  budget: 0.85,
};
