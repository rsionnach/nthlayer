import React from 'react';
import { makeStyles, Theme, createStyles } from '@material-ui/core/styles';
import { Box, Divider, Link, Typography } from '@material-ui/core';
import { InfoCard, Progress, WarningPanel } from '@backstage/core-components';
import { useEntity } from '@backstage/plugin-catalog-react';
import { useAsync } from 'react-use';
import { useApi, configApiRef } from '@backstage/core-plugin-api';

import { ScoreBadge } from '../ScoreBadge';
import { SloList } from '../SloList';
import { BudgetGauge } from '../BudgetGauge';
import { GateStatus } from '../GateStatus';
import type { NthlayerEntity } from '../../types';
import { NTHLAYER_ENTITY_ANNOTATION } from '../../types';

const useStyles = makeStyles((theme: Theme) =>
  createStyles({
    root: {
      display: 'flex',
      flexDirection: 'column',
      gap: theme.spacing(2),
    },
    header: {
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'flex-start',
    },
    serviceInfo: {
      display: 'flex',
      flexDirection: 'column',
    },
    tierChip: {
      display: 'inline-flex',
      alignItems: 'center',
      padding: theme.spacing(0.25, 1),
      borderRadius: 4,
      fontSize: '0.75rem',
      fontWeight: 500,
      textTransform: 'uppercase',
    },
    tierCritical: {
      backgroundColor: '#ffebee',
      color: '#c62828',
    },
    tierHigh: {
      backgroundColor: '#fff3e0',
      color: '#e65100',
    },
    tierStandard: {
      backgroundColor: '#e3f2fd',
      color: '#1565c0',
    },
    tierLow: {
      backgroundColor: '#f5f5f5',
      color: '#616161',
    },
    section: {
      marginTop: theme.spacing(1),
    },
    links: {
      display: 'flex',
      gap: theme.spacing(2),
      flexWrap: 'wrap',
    },
    timestamp: {
      marginTop: theme.spacing(1),
    },
  }),
);

/**
 * Check if the entity has the nthlayer annotation.
 */
export const isNthlayerAvailable = (entity: { metadata: { annotations?: Record<string, string> } }): boolean => {
  return Boolean(entity.metadata.annotations?.[NTHLAYER_ENTITY_ANNOTATION]);
};

/**
 * Hook to fetch NthLayer entity data from the annotation path.
 */
const useNthlayerData = () => {
  const { entity } = useEntity();
  const config = useApi(configApiRef);

  const annotationPath = entity.metadata.annotations?.[NTHLAYER_ENTITY_ANNOTATION];

  return useAsync(async (): Promise<NthlayerEntity | null> => {
    if (!annotationPath) {
      return null;
    }

    // Try to resolve the path - could be relative or absolute URL
    let url: string;
    if (annotationPath.startsWith('http://') || annotationPath.startsWith('https://')) {
      url = annotationPath;
    } else {
      // For relative paths, try to fetch from the app's public assets
      // In a real implementation, this would use a backend plugin or catalog processor
      const baseUrl = config.getOptionalString('app.baseUrl') ?? '';
      url = `${baseUrl}/${annotationPath.replace(/^\.\//, '')}`;
    }

    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Failed to fetch NthLayer data: ${response.statusText}`);
    }

    return response.json();
  }, [annotationPath]);
};

const TierBadge: React.FC<{ tier: string }> = ({ tier }) => {
  const classes = useStyles();

  const tierClass = {
    critical: classes.tierCritical,
    high: classes.tierHigh,
    standard: classes.tierStandard,
    low: classes.tierLow,
  }[tier] || classes.tierStandard;

  return <Box className={`${classes.tierChip} ${tierClass}`}>{tier}</Box>;
};

/**
 * Content component for NthLayer card - used when data is available.
 */
export const NthlayerCardContent: React.FC = () => {
  const classes = useStyles();
  const { value: data, loading, error } = useNthlayerData();
  const { entity } = useEntity();

  if (!isNthlayerAvailable(entity)) {
    return (
      <WarningPanel
        title="NthLayer not configured"
        message={`Add the ${NTHLAYER_ENTITY_ANNOTATION} annotation to enable reliability data.`}
      />
    );
  }

  if (loading) {
    return <Progress />;
  }

  if (error) {
    return (
      <WarningPanel
        title="Failed to load reliability data"
        message={error.message}
      />
    );
  }

  if (!data) {
    return (
      <WarningPanel
        title="No data available"
        message="NthLayer entity data could not be loaded."
      />
    );
  }

  const { service, slos, errorBudget, score, deploymentGate, links, generatedAt } = data;

  return (
    <Box className={classes.root}>
      {/* Header with score and service info */}
      <Box className={classes.header}>
        <Box className={classes.serviceInfo}>
          <Box display="flex" alignItems="center" gap={1}>
            <Typography variant="subtitle1">{service.name}</Typography>
            <TierBadge tier={service.tier} />
          </Box>
          <Typography variant="caption" color="textSecondary">
            {service.team} • {service.type}
          </Typography>
        </Box>
        <ScoreBadge score={score} />
      </Box>

      <Divider />

      {/* SLOs */}
      <Box className={classes.section}>
        <Typography variant="subtitle2" gutterBottom>
          Service Level Objectives
        </Typography>
        <SloList slos={slos} />
      </Box>

      <Divider />

      {/* Error Budget */}
      <Box className={classes.section}>
        <BudgetGauge budget={errorBudget} />
      </Box>

      <Divider />

      {/* Deployment Gate */}
      <Box className={classes.section}>
        <GateStatus gate={deploymentGate} />
      </Box>

      {/* Links */}
      {links && (
        <>
          <Divider />
          <Box className={classes.section}>
            <Typography variant="subtitle2" gutterBottom>
              Links
            </Typography>
            <Box className={classes.links}>
              {links.grafanaDashboard && (
                <Link href={links.grafanaDashboard} target="_blank" rel="noopener">
                  Dashboard
                </Link>
              )}
              {links.runbook && (
                <Link href={links.runbook} target="_blank" rel="noopener">
                  Runbook
                </Link>
              )}
              {links.alertsYaml && (
                <Link href={links.alertsYaml} target="_blank" rel="noopener">
                  Alerts
                </Link>
              )}
            </Box>
          </Box>
        </>
      )}

      {/* Timestamp */}
      {generatedAt && (
        <Typography variant="caption" color="textSecondary" className={classes.timestamp}>
          Last updated: {new Date(generatedAt).toLocaleString()}
        </Typography>
      )}
    </Box>
  );
};

/**
 * Main NthLayer card component for Backstage entity pages.
 *
 * Displays reliability data including SLOs, error budget, and deployment gate status.
 */
export const NthlayerCard: React.FC = () => {
  return (
    <InfoCard title="Reliability" subheader="NthLayer">
      <NthlayerCardContent />
    </InfoCard>
  );
};
