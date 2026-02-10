import React from 'react';
import { makeStyles, Theme, createStyles } from '@material-ui/core/styles';
import { Box, Typography, LinearProgress, Tooltip } from '@material-ui/core';
import type { ErrorBudgetSummary } from '../types';

const useStyles = makeStyles((theme: Theme) =>
  createStyles({
    root: {
      width: '100%',
    },
    header: {
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      marginBottom: theme.spacing(0.5),
    },
    percentText: {
      fontWeight: 'bold',
      fontSize: '1.1rem',
    },
    progressBar: {
      height: 10,
      borderRadius: 5,
    },
    progressHealthy: {
      backgroundColor: '#e8f5e9',
      '& .MuiLinearProgress-bar': {
        backgroundColor: '#4caf50',
      },
    },
    progressWarning: {
      backgroundColor: '#fff3e0',
      '& .MuiLinearProgress-bar': {
        backgroundColor: '#ff9800',
      },
    },
    progressCritical: {
      backgroundColor: '#ffebee',
      '& .MuiLinearProgress-bar': {
        backgroundColor: '#f44336',
      },
    },
    progressExhausted: {
      backgroundColor: '#f3e5f5',
      '& .MuiLinearProgress-bar': {
        backgroundColor: '#9c27b0',
      },
    },
    progressUnknown: {
      backgroundColor: theme.palette.grey[200],
      '& .MuiLinearProgress-bar': {
        backgroundColor: theme.palette.grey[400],
      },
    },
    details: {
      display: 'flex',
      justifyContent: 'space-between',
      marginTop: theme.spacing(0.5),
    },
    statusChip: {
      display: 'inline-flex',
      alignItems: 'center',
      padding: theme.spacing(0.25, 1),
      borderRadius: 12,
      fontSize: '0.75rem',
      fontWeight: 500,
    },
    statusHealthy: {
      backgroundColor: '#e8f5e9',
      color: '#2e7d32',
    },
    statusWarning: {
      backgroundColor: '#fff3e0',
      color: '#e65100',
    },
    statusCritical: {
      backgroundColor: '#ffebee',
      color: '#c62828',
    },
    statusExhausted: {
      backgroundColor: '#f3e5f5',
      color: '#6a1b9a',
    },
    noData: {
      color: theme.palette.text.secondary,
      fontStyle: 'italic',
    },
  }),
);

interface BudgetGaugeProps {
  budget: ErrorBudgetSummary | undefined;
}

const getProgressClass = (
  status: string | null | undefined,
  classes: ReturnType<typeof useStyles>,
): string => {
  switch (status) {
    case 'healthy':
      return classes.progressHealthy;
    case 'warning':
      return classes.progressWarning;
    case 'critical':
      return classes.progressCritical;
    case 'exhausted':
      return classes.progressExhausted;
    default:
      return classes.progressUnknown;
  }
};

const getStatusClass = (
  status: string | null | undefined,
  classes: ReturnType<typeof useStyles>,
): string => {
  switch (status) {
    case 'healthy':
      return classes.statusHealthy;
    case 'warning':
      return classes.statusWarning;
    case 'critical':
      return classes.statusCritical;
    case 'exhausted':
      return classes.statusExhausted;
    default:
      return '';
  }
};

const formatMinutes = (minutes: number | null | undefined): string => {
  if (minutes === null || minutes === undefined) return 'N/A';
  if (minutes < 60) return `${Math.round(minutes)}m`;
  const hours = minutes / 60;
  if (hours < 24) return `${hours.toFixed(1)}h`;
  const days = hours / 24;
  return `${days.toFixed(1)}d`;
};

export const BudgetGauge: React.FC<BudgetGaugeProps> = ({ budget }) => {
  const classes = useStyles();

  const remainingPercent = budget?.remainingPercent ?? null;
  const status = budget?.status ?? null;

  if (remainingPercent === null) {
    return (
      <Box className={classes.root}>
        <Typography variant="subtitle2" gutterBottom>
          Error Budget
        </Typography>
        <Typography className={classes.noData}>
          No budget data available
        </Typography>
      </Box>
    );
  }

  const progressClass = getProgressClass(status, classes);
  const statusClass = getStatusClass(status, classes);

  const tooltipText = [
    `Remaining: ${formatMinutes(budget?.remainingMinutes)}`,
    `Consumed: ${formatMinutes(budget?.consumedMinutes)}`,
    `Total: ${formatMinutes(budget?.totalMinutes)}`,
    budget?.burnRate ? `Burn rate: ${budget.burnRate.toFixed(2)}x` : null,
  ]
    .filter(Boolean)
    .join(' | ');

  return (
    <Tooltip title={tooltipText}>
      <Box className={classes.root}>
        <Box className={classes.header}>
          <Typography variant="subtitle2">Error Budget</Typography>
          <Typography className={classes.percentText}>
            {remainingPercent.toFixed(1)}% remaining
          </Typography>
        </Box>
        <LinearProgress
          variant="determinate"
          value={remainingPercent}
          className={`${classes.progressBar} ${progressClass}`}
        />
        <Box className={classes.details}>
          <Typography variant="caption" color="textSecondary">
            {formatMinutes(budget?.remainingMinutes)} of{' '}
            {formatMinutes(budget?.totalMinutes)}
          </Typography>
          {status && (
            <Box className={`${classes.statusChip} ${statusClass}`}>
              {status.toUpperCase()}
            </Box>
          )}
        </Box>
      </Box>
    </Tooltip>
  );
};
