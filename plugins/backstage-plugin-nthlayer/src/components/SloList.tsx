import React from 'react';
import { makeStyles, Theme, createStyles } from '@material-ui/core/styles';
import {
  Box,
  Typography,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Chip,
  Tooltip,
} from '@material-ui/core';
import CheckCircleIcon from '@material-ui/icons/CheckCircle';
import WarningIcon from '@material-ui/icons/Warning';
import ErrorIcon from '@material-ui/icons/Error';
import HelpOutlineIcon from '@material-ui/icons/HelpOutline';
import type { SloEntry } from '../types';

const useStyles = makeStyles((theme: Theme) =>
  createStyles({
    root: {
      width: '100%',
    },
    listItem: {
      paddingTop: theme.spacing(0.5),
      paddingBottom: theme.spacing(0.5),
    },
    statusHealthy: {
      color: '#4caf50',
    },
    statusWarning: {
      color: '#ff9800',
    },
    statusCritical: {
      color: '#f44336',
    },
    statusExhausted: {
      color: '#9c27b0',
    },
    statusUnknown: {
      color: theme.palette.grey[400],
    },
    targetChip: {
      marginLeft: theme.spacing(1),
      height: 20,
      fontSize: '0.75rem',
    },
    sloName: {
      fontWeight: 500,
    },
    sloDetails: {
      display: 'flex',
      alignItems: 'center',
      gap: theme.spacing(1),
    },
    currentValue: {
      fontWeight: 'bold',
    },
    emptyState: {
      color: theme.palette.text.secondary,
      fontStyle: 'italic',
      padding: theme.spacing(2),
      textAlign: 'center',
    },
  }),
);

interface SloListProps {
  slos: SloEntry[] | undefined;
}

const StatusIcon: React.FC<{ status: string | null | undefined }> = ({ status }) => {
  const classes = useStyles();

  switch (status) {
    case 'healthy':
      return <CheckCircleIcon className={classes.statusHealthy} />;
    case 'warning':
      return <WarningIcon className={classes.statusWarning} />;
    case 'critical':
      return <ErrorIcon className={classes.statusCritical} />;
    case 'exhausted':
      return <ErrorIcon className={classes.statusExhausted} />;
    default:
      return <HelpOutlineIcon className={classes.statusUnknown} />;
  }
};

const formatSloType = (sloType: string | null | undefined): string => {
  if (!sloType) return '';
  return sloType.replace(/_/g, ' ');
};

export const SloList: React.FC<SloListProps> = ({ slos }) => {
  const classes = useStyles();

  if (!slos || slos.length === 0) {
    return (
      <Typography className={classes.emptyState}>
        No SLOs defined
      </Typography>
    );
  }

  return (
    <List className={classes.root} dense>
      {slos.map((slo, index) => (
        <ListItem key={slo.name || index} className={classes.listItem}>
          <ListItemIcon style={{ minWidth: 36 }}>
            <Tooltip title={slo.status ? `Status: ${slo.status}` : 'Status unknown'}>
              <span>
                <StatusIcon status={slo.status} />
              </span>
            </Tooltip>
          </ListItemIcon>
          <ListItemText
            primary={
              <Box className={classes.sloDetails}>
                <Typography variant="body2" className={classes.sloName}>
                  {slo.name}
                </Typography>
                {slo.sloType && (
                  <Chip
                    label={formatSloType(slo.sloType)}
                    size="small"
                    variant="outlined"
                    className={classes.targetChip}
                  />
                )}
              </Box>
            }
            secondary={
              <Box component="span" className={classes.sloDetails}>
                <Typography variant="caption" component="span">
                  Target: {slo.target}%
                </Typography>
                {slo.currentValue !== null && slo.currentValue !== undefined && (
                  <Typography
                    variant="caption"
                    component="span"
                    className={classes.currentValue}
                  >
                    Current: {slo.currentValue.toFixed(2)}%
                  </Typography>
                )}
                <Typography variant="caption" component="span" color="textSecondary">
                  ({slo.window})
                </Typography>
              </Box>
            }
          />
        </ListItem>
      ))}
    </List>
  );
};
