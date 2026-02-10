/**
 * TypeScript types matching the NthLayer Backstage entity JSON schema.
 */

export interface NthlayerEntity {
  schemaVersion: 'v1';
  generatedAt: string;
  service: ServiceContext;
  slos?: SloEntry[];
  errorBudget?: ErrorBudgetSummary;
  score?: ServiceScore;
  deploymentGate?: DeploymentGate;
  links?: Links;
}

export interface ServiceContext {
  name: string;
  team: string;
  tier: 'critical' | 'high' | 'standard' | 'low';
  type: 'api' | 'worker' | 'stream' | 'ai-gate' | 'batch' | 'database' | 'web';
  description?: string | null;
  supportModel?: 'self' | 'shared' | 'sre' | 'business_hours';
}

export interface SloEntry {
  name: string;
  target: number;
  window: string;
  sloType?: 'availability' | 'latency' | 'error_rate' | 'throughput' | 'judgment' | null;
  description?: string | null;
  currentValue?: number | null;
  status?: 'healthy' | 'warning' | 'critical' | 'exhausted' | null;
}

export interface ErrorBudgetSummary {
  totalMinutes?: number | null;
  consumedMinutes?: number | null;
  remainingMinutes?: number | null;
  remainingPercent?: number | null;
  burnRate?: number | null;
  status?: 'healthy' | 'warning' | 'critical' | 'exhausted' | null;
}

export interface ServiceScore {
  score?: number | null;
  grade?: 'A' | 'B' | 'C' | 'D' | 'F' | null;
  band?: 'excellent' | 'good' | 'fair' | 'poor' | 'critical' | null;
  trend?: 'improving' | 'stable' | 'degrading' | null;
  components?: ScoreComponents;
}

export interface ScoreComponents {
  sloCompliance?: number | null;
  incidentScore?: number | null;
  deploySuccessRate?: number | null;
  errorBudgetRemaining?: number | null;
}

export interface DeploymentGate {
  status: 'APPROVED' | 'WARNING' | 'BLOCKED';
  message?: string | null;
  budgetRemainingPercent?: number | null;
  warningThreshold?: number | null;
  blockingThreshold?: number | null;
  recommendations?: string[];
}

export interface Links {
  grafanaDashboard?: string | null;
  runbook?: string | null;
  serviceManifest?: string | null;
  slothSpec?: string | null;
  alertsYaml?: string | null;
}

/** Annotation key for the NthLayer entity JSON path */
export const NTHLAYER_ENTITY_ANNOTATION = 'nthlayer.dev/entity';
