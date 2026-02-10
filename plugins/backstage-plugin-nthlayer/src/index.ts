/**
 * NthLayer Backstage Plugin
 *
 * Displays reliability data (SLOs, error budgets, deployment gates)
 * from NthLayer-generated artifacts in the Backstage catalog.
 *
 * @packageDocumentation
 */

export {
  nthlayerPlugin,
  EntityNthlayerCard,
  EntityNthlayerContent,
} from './plugin';

export * from './types';

export { isNthlayerAvailable } from './components/NthlayerCard';
