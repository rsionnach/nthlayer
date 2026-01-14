import yaml from 'js-yaml';
import { SERVICES, DEFAULT_SERVICE, ServiceData } from '../data/services';

export interface CommandContext {
  yamlContent: string;
  parsedYaml: Record<string, unknown>;
  getService: (name: string) => ServiceData;
}

export interface CommandResult {
  output: string;
  isError?: boolean;
  delay?: number;
}

export type CommandHandler = (
  args: string[],
  context: CommandContext
) => CommandResult;

// Parse YAML and extract service config
function parseContext(yamlContent: string): CommandContext {
  let parsedYaml: Record<string, unknown> = {};
  try {
    parsedYaml = (yaml.load(yamlContent) as Record<string, unknown>) || {};
  } catch {
    // Invalid YAML, use empty
  }

  const getService = (name: string): ServiceData => {
    const service = parsedYaml?.service as Record<string, unknown> | undefined;
    const yamlServiceName = service?.name as string | undefined;

    if (name === yamlServiceName || name === 'current') {
      const baseService = SERVICES[yamlServiceName || ''] || DEFAULT_SERVICE;
      return {
        ...baseService,
        name: yamlServiceName || name,
        tier: (service?.tier as ServiceData['tier']) || baseService.tier,
        owner: (service?.owner as string) || baseService.owner,
      };
    }
    return SERVICES[name] || { ...DEFAULT_SERVICE, name };
  };

  return { yamlContent, parsedYaml, getService };
}

// Command: nthlayer drift <service>
function driftCommand(args: string[], ctx: CommandContext): CommandResult {
  const service = ctx.parsedYaml?.service as Record<string, unknown> | undefined;
  const serviceName = args[0] || (service?.name as string) || 'payment-api';
  const serviceData = ctx.getService(serviceName);
  const drift = serviceData.drift;

  const slos = ctx.parsedYaml?.slos as Array<Record<string, unknown>> | undefined;
  const yamlSlo = slos?.find((s) => s.name === drift.sloName);
  const target = (yamlSlo?.target as number) || 0.999;

  const trendArrow = drift.trend < -0.005 ? '↘' : drift.trend > 0.005 ? '↗' : '→';
  const trendPercent = (drift.trend * 100).toFixed(2);
  const trendSign = drift.trend >= 0 ? '+' : '';

  const severityColor: Record<string, string> = {
    none: '\x1b[32m',
    info: '\x1b[36m',
    warn: '\x1b[33m',
    critical: '\x1b[31m',
  };
  const reset = '\x1b[0m';

  let output = `Analyzing drift for ${serviceName}...\n\n`;
  output += `SLO: ${drift.sloName} (target: ${(target * 100).toFixed(1)}%)\n`;
  output += `  Current budget: ${(drift.currentBudget * 100).toFixed(1)}%\n`;
  output += `  Trend: ${trendSign}${trendPercent}%/week ${trendArrow}\n`;
  output += `  Pattern: ${drift.pattern}\n`;
  output += `  Severity: ${severityColor[drift.severity]}${drift.severity.toUpperCase()}${reset}\n`;
  output += `\n`;
  output += `  Projection:\n`;

  if (drift.daysUntilExhaustion) {
    output += `    Days until exhaustion: ${drift.daysUntilExhaustion}\n`;
  } else {
    output += `    Days until exhaustion: N/A (stable)\n`;
  }
  output += `    Budget in 30d: ${(drift.projectedBudget30d * 100).toFixed(1)}%\n`;

  if (drift.severity === 'critical') {
    output += `\n\x1b[31m✗ CRITICAL: Immediate action required. Budget exhaustion imminent.\x1b[0m`;
  } else if (drift.severity === 'warn') {
    output += `\n\x1b[33m⚠ WARNING: Investigate gradual degradation before it becomes critical.\x1b[0m`;
  } else {
    output += `\n\x1b[32m✓ OK: No significant drift detected.\x1b[0m`;
  }

  return { output, delay: 800 };
}

// Command: nthlayer validate-slo <service>
function validateSloCommand(args: string[], ctx: CommandContext): CommandResult {
  const service = ctx.parsedYaml?.service as Record<string, unknown> | undefined;
  const serviceName = args[0] || (service?.name as string) || 'payment-api';
  const serviceData = ctx.getService(serviceName);

  let target = 0.999;
  const targetFlagIndex = args.indexOf('--target');
  if (targetFlagIndex !== -1 && args[targetFlagIndex + 1]) {
    target = parseFloat(args[targetFlagIndex + 1]);
  } else {
    const slos = ctx.parsedYaml?.slos as Array<Record<string, unknown>> | undefined;
    if (slos?.[0]?.target) {
      target = slos[0].target as number;
    }
  }

  const criticalDeps = serviceData.dependencies.filter((d) => d.critical);
  const serialAvailability = criticalDeps.reduce((acc, d) => acc * d.availability, 1);
  const feasible = target <= serialAvailability;
  const gap = target - serialAvailability;

  let output = `Validating SLO target ${(target * 100).toFixed(2)}% for ${serviceName}...\n\n`;
  output += `Dependency chain:\n`;
  output += `  ${serviceName}\n`;

  for (const dep of criticalDeps) {
    const icon =
      dep.type === 'datastore' ? '🗄' :
      dep.type === 'external' ? '🌐' :
      dep.type === 'queue' ? '📨' : '→';
    output += `  └── ${icon} ${dep.name} (${(dep.availability * 100).toFixed(2)}%)\n`;
  }

  output += `\n`;
  output += `Serial availability: ${(serialAvailability * 100).toFixed(3)}%\n`;
  output += `Target: ${(target * 100).toFixed(2)}%\n\n`;

  if (feasible) {
    output += `\x1b[32m✓ FEASIBLE: Target is achievable given dependency chain.\x1b[0m\n`;
    const headroom = serialAvailability - target;
    output += `  Headroom: ${(headroom * 100).toFixed(3)}%`;
  } else {
    output += `\x1b[31m✗ INFEASIBLE: Target exceeds dependency ceiling by ${(Math.abs(gap) * 100).toFixed(3)}%\x1b[0m\n\n`;
    output += `Recommendations:\n`;
    output += `  1. Reduce target to ${(serialAvailability * 100).toFixed(2)}% (achievable ceiling)\n`;

    const weakest = criticalDeps.reduce((min, d) =>
      d.availability < min.availability ? d : min
    );
    output += `  2. Improve ${weakest.name} reliability (currently ${(weakest.availability * 100).toFixed(2)}%)\n`;
    output += `  3. Add redundancy or circuit breaker for critical dependencies`;
  }

  return { output, delay: 600 };
}

// Command: nthlayer deps <service>
function depsCommand(args: string[], ctx: CommandContext): CommandResult {
  const service = ctx.parsedYaml?.service as Record<string, unknown> | undefined;
  const serviceName = args[0] || (service?.name as string) || 'payment-api';
  const serviceData = ctx.getService(serviceName);

  let output = `Dependencies for ${serviceName}:\n\n`;
  output += `Upstream (${serviceName} depends on):\n`;

  for (const dep of serviceData.dependencies) {
    const icon =
      dep.type === 'datastore' ? '🗄' :
      dep.type === 'external' ? '🌐' :
      dep.type === 'queue' ? '📨' : '→';
    const criticalBadge = dep.critical ? ' [critical]' : '';
    output += `  ${icon} ${dep.name} (${dep.type})${criticalBadge}\n`;
    output += `     Availability: ${(dep.availability * 100).toFixed(2)}%\n`;
  }

  const downstreamCount = Math.floor(Math.random() * 5) + 1;
  output += `\nDownstream (depends on ${serviceName}): ${downstreamCount} services\n`;

  return { output, delay: 400 };
}

// Command: nthlayer blast-radius <service>
function blastRadiusCommand(args: string[], ctx: CommandContext): CommandResult {
  const service = ctx.parsedYaml?.service as Record<string, unknown> | undefined;
  const serviceName = args[0] || (service?.name as string) || 'payment-api';
  const serviceData = ctx.getService(serviceName);

  const impactMultiplier =
    serviceData.tier === 'critical' ? 3 : serviceData.tier === 'standard' ? 2 : 1;
  const directDependents = Math.floor(Math.random() * 3 * impactMultiplier) + impactMultiplier;
  const transitiveDependents = directDependents * 2;
  const teamsAffected = Math.ceil(directDependents / 2);

  let output = `Blast radius analysis for ${serviceName}:\n\n`;
  output += `Scenario: ${serviceName} degrades to 99% availability for 1 hour\n\n`;
  output += `Direct dependents: ${directDependents} services\n`;
  output += `Transitive impact: ${transitiveDependents} services\n`;
  output += `Teams affected: ${teamsAffected}\n\n`;

  output += `Affected teams:\n`;
  const teams = ['orders-team', 'checkout-squad', 'mobile-team', 'web-team', 'analytics-eng'];
  for (let i = 0; i < teamsAffected; i++) {
    output += `  • ${teams[i % teams.length]}\n`;
  }

  output += `\n`;
  if (serviceData.tier === 'critical') {
    output += `\x1b[31m⚠ HIGH IMPACT: This is a critical-tier service.\x1b[0m\n`;
    output += `Recommend notifying all affected teams before any changes.`;
  } else {
    output += `\x1b[33mMODERATE IMPACT: Review affected services before changes.\x1b[0m`;
  }

  return { output, delay: 700 };
}

// Command: nthlayer portfolio
function portfolioCommand(): CommandResult {
  let output = `Service Portfolio Overview\n`;
  output += `${'─'.repeat(60)}\n`;
  output += `${'Service'.padEnd(18)} ${'Tier'.padEnd(10)} ${'Budget'.padEnd(10)} ${'Drift'.padEnd(10)} Owner\n`;
  output += `${'─'.repeat(60)}\n`;

  for (const [name, service] of Object.entries(SERVICES)) {
    const budgetStr = `${(service.budget * 100).toFixed(0)}%`.padEnd(10);
    const severityStr = service.drift.severity.toUpperCase().padEnd(10);
    output += `${name.padEnd(18)} ${service.tier.padEnd(10)} ${budgetStr} ${severityStr} ${service.owner}\n`;
  }

  output += `${'─'.repeat(60)}\n`;
  output += `\nSummary: ${Object.keys(SERVICES).length} services, `;

  const warnings = Object.values(SERVICES).filter(
    (s) => s.drift.severity === 'warn' || s.drift.severity === 'critical'
  );
  if (warnings.length > 0) {
    output += `\x1b[33m${warnings.length} with drift warnings\x1b[0m`;
  } else {
    output += `\x1b[32mall healthy\x1b[0m`;
  }

  return { output, delay: 500 };
}

// Command: nthlayer lint
function lintCommand(_args: string[], ctx: CommandContext): CommandResult {
  const errors: string[] = [];
  const warnings: string[] = [];

  try {
    const config = yaml.load(ctx.yamlContent) as Record<string, unknown>;
    const service = config?.service as Record<string, unknown> | undefined;
    const slos = config?.slos as Array<Record<string, unknown>> | undefined;

    if (!service?.name) {
      errors.push('service.name is required');
    }
    if (!service?.tier) {
      warnings.push('service.tier not specified, defaulting to "standard"');
    }
    if (!slos || slos.length === 0) {
      warnings.push('No SLOs defined');
    }

    for (const slo of slos || []) {
      const target = slo.target as number | undefined;
      if (target && (target > 1 || target < 0.9)) {
        errors.push(`SLO "${slo.name}": target ${target} should be between 0.9 and 1.0`);
      }
    }

    if (service?.tier === 'critical' && (!slos || slos.length === 0)) {
      errors.push('Critical-tier services must define at least one SLO');
    }
  } catch (e) {
    const err = e as Error;
    errors.push(`YAML parse error: ${err.message}`);
  }

  let output = `Linting service.yaml...\n\n`;

  if (errors.length === 0 && warnings.length === 0) {
    output += `\x1b[32m✓ No issues found. Configuration is valid.\x1b[0m`;
  } else {
    if (errors.length > 0) {
      output += `\x1b[31mErrors (${errors.length}):\x1b[0m\n`;
      for (const err of errors) {
        output += `  ✗ ${err}\n`;
      }
    }
    if (warnings.length > 0) {
      output += `\x1b[33mWarnings (${warnings.length}):\x1b[0m\n`;
      for (const warn of warnings) {
        output += `  ⚠ ${warn}\n`;
      }
    }
  }

  return { output, delay: 300 };
}

// Command: help
function helpCommand(): CommandResult {
  const output = `NthLayer Interactive Demo - Available Commands

  nthlayer drift <service>              Check error budget drift
  nthlayer validate-slo <service>       Validate SLO target feasibility
  nthlayer deps <service>               Show service dependencies
  nthlayer blast-radius <service>       Analyze impact if service degrades
  nthlayer portfolio                    Show all services overview
  nthlayer lint                         Validate the service.yaml config

  clear                                 Clear terminal
  help                                  Show this help

Tips:
  • Edit the YAML on the left to see how commands respond
  • Use "current" as service name to use the YAML's service
  • Try changing the SLO target and running validate-slo`;

  return { output, delay: 0 };
}

// Command router
const COMMANDS: Record<string, CommandHandler> = {
  drift: driftCommand,
  'validate-slo': validateSloCommand,
  deps: depsCommand,
  'blast-radius': blastRadiusCommand,
  portfolio: portfolioCommand,
  lint: lintCommand,
  help: helpCommand,
};

export function executeCommand(input: string, yamlContent: string): CommandResult {
  const trimmed = input.trim();

  if (!trimmed) {
    return { output: '', delay: 0 };
  }

  if (trimmed === 'clear') {
    return { output: '__CLEAR__', delay: 0 };
  }

  if (trimmed === 'help') {
    return helpCommand();
  }

  const parts = trimmed.split(/\s+/);

  if (parts[0] !== 'nthlayer') {
    return {
      output: `Command not found: ${parts[0]}\nType "help" for available commands.`,
      isError: true,
      delay: 0,
    };
  }

  const subcommand = parts[1];
  const args = parts.slice(2);

  const handler = COMMANDS[subcommand];
  if (!handler) {
    return {
      output: `Unknown subcommand: ${subcommand}\nType "help" for available commands.`,
      isError: true,
      delay: 0,
    };
  }

  const context = parseContext(yamlContent);
  return handler(args, context);
}
