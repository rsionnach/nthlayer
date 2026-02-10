import {
  createPlugin,
  createComponentExtension,
} from '@backstage/core-plugin-api';
import { rootRouteRef } from './routes';

/**
 * The NthLayer plugin for Backstage.
 *
 * Displays reliability data (SLOs, error budgets, deployment gates)
 * for services in the Backstage catalog.
 */
export const nthlayerPlugin = createPlugin({
  id: 'nthlayer',
  routes: {
    root: rootRouteRef,
  },
});

/**
 * Entity card component for displaying NthLayer reliability data.
 *
 * Add this to your EntityPage to show SLOs, error budget, and deployment gate status.
 *
 * @example
 * ```tsx
 * import { EntityNthlayerCard } from '@internal/plugin-nthlayer';
 *
 * // In your EntityPage.tsx:
 * <Grid item xs={12} md={6}>
 *   <EntityNthlayerCard />
 * </Grid>
 * ```
 */
export const EntityNthlayerCard = nthlayerPlugin.provide(
  createComponentExtension({
    name: 'EntityNthlayerCard',
    component: {
      lazy: () =>
        import('./components/NthlayerCard').then(m => m.NthlayerCard),
    },
  }),
);

/**
 * Conditional wrapper that only renders if the entity has the nthlayer annotation.
 */
export const EntityNthlayerContent = nthlayerPlugin.provide(
  createComponentExtension({
    name: 'EntityNthlayerContent',
    component: {
      lazy: () =>
        import('./components/NthlayerCard').then(m => m.NthlayerCardContent),
    },
  }),
);
