import React from 'react';
import { makeStyles, Theme, createStyles } from '@material-ui/core/styles';
import { Box, Typography, Chip, Tooltip, List, ListItem, ListItemIcon, ListItemText } from '@material-ui/core';
import CheckCircleIcon from '@material-ui/icons/CheckCircle';
import WarningIcon from '@material-ui/icons/Warning';
import BlockIcon from '@material-ui/icons/Block';
import ArrowRightIcon from '@material-ui/icons/ArrowRight';
import type { DeploymentGate } from '../types';

const useStyles = makeStyles((theme: Theme) =>
  createStyles({
    root: {
      width: '100%',
    },
    header: {
      display: 'flex',
      alignItems: 'center',
      gap: theme.spacing(1),
      marginBottom: theme.spacing(1),
    },
    chipApproved: {
      backgroundColor: '#e8f5e9',
      color: '#2e7d32',
      fontWeight: 'bold',
      '& .MuiChip-icon': {
        color: '#2e7d32',
      },
    },
    chipWarning: {
      backgroundColor: '#fff3e0',
      color: '#e65100',
      fontWeight: 'bold',
      '& .MuiChip-icon': {
        color: '#e65100',
      },
    },
    chipBlocked: {
      backgroundColor: '#ffebee',
      color: '#c62828',
      fontWeight: 'bold',
      '& .MuiChip-icon': {
        color: '#c62828',
      },
    },
    message: {
      marginBottom: theme.spacing(1),
    },
    thresholds: {
      display: 'flex',
      gap: theme.spacing(2),
      marginBottom: theme.spacing(1),
    },
    threshold: {
      display: 'flex',
      alignItems: 'center',
      gap: theme.spacing(0.5),
    },
    thresholdLabel: {
      color: theme.palette.text.secondary,
    },
    recommendations: {
      padding: 0,
    },
    recommendationItem: {
      paddingTop: theme.spacing(0.25),
      paddingBottom: theme.spacing(0.25),
    },
    recommendationIcon: {
      minWidth: 24,
      color: theme.palette.text.secondary,
    },
  }),
);

interface GateStatusProps {
  gate: DeploymentGate | undefined;
}

const StatusChip: React.FC<{ status: string }> = ({ status }) => {
  const classes = useStyles();

  switch (status) {
    case 'APPROVED':
      return (
        <Chip
          icon={<CheckCircleIcon />}
          label="APPROVED"
          className={classes.chipApproved}
          size="small"
        />
      );
    case 'WARNING':
      return (
        <Chip
          icon={<WarningIcon />}
          label="WARNING"
          className={classes.chipWarning}
          size="small"
        />
      );
    case 'BLOCKED':
      return (
        <Chip
          icon={<BlockIcon />}
          label="BLOCKED"
          className={classes.chipBlocked}
          size="small"
        />
      );
    default:
      return <Chip label={status} size="small" />;
  }
};

export const GateStatus: React.FC<GateStatusProps> = ({ gate }) => {
  const classes = useStyles();

  if (!gate) {
    return (
      <Box className={classes.root}>
        <Typography variant="subtitle2" gutterBottom>
          Deployment Gate
        </Typography>
        <Typography color="textSecondary" variant="body2">
          No gate data available
        </Typography>
      </Box>
    );
  }

  const { status, message, warningThreshold, blockingThreshold, recommendations, budgetRemainingPercent } = gate;

  const tooltipText = budgetRemainingPercent !== null && budgetRemainingPercent !== undefined
    ? `Budget remaining: ${budgetRemainingPercent.toFixed(1)}%`
    : 'Budget data not available';

  return (
    <Box className={classes.root}>
      <Box className={classes.header}>
        <Typography variant="subtitle2">Deployment Gate</Typography>
        <Tooltip title={tooltipText}>
          <span>
            <StatusChip status={status} />
          </span>
        </Tooltip>
      </Box>

      {message && (
        <Typography variant="body2" className={classes.message}>
          {message}
        </Typography>
      )}

      <Box className={classes.thresholds}>
        {warningThreshold !== null && warningThreshold !== undefined && (
          <Box className={classes.threshold}>
            <Typography variant="caption" className={classes.thresholdLabel}>
              Warning:
            </Typography>
            <Typography variant="caption">&lt;{warningThreshold}%</Typography>
          </Box>
        )}
        {blockingThreshold !== null && blockingThreshold !== undefined && (
          <Box className={classes.threshold}>
            <Typography variant="caption" className={classes.thresholdLabel}>
              Blocking:
            </Typography>
            <Typography variant="caption">&lt;{blockingThreshold}%</Typography>
          </Box>
        )}
      </Box>

      {recommendations && recommendations.length > 0 && (
        <List dense className={classes.recommendations}>
          {recommendations.map((rec, index) => (
            <ListItem key={index} className={classes.recommendationItem}>
              <ListItemIcon className={classes.recommendationIcon}>
                <ArrowRightIcon fontSize="small" />
              </ListItemIcon>
              <ListItemText
                primary={rec}
                primaryTypographyProps={{ variant: 'caption' }}
              />
            </ListItem>
          ))}
        </List>
      )}
    </Box>
  );
};
