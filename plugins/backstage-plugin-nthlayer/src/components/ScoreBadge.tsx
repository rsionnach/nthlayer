import React from 'react';
import { makeStyles, Theme, createStyles } from '@material-ui/core/styles';
import { Box, Typography, Tooltip } from '@material-ui/core';
import TrendingUpIcon from '@material-ui/icons/TrendingUp';
import TrendingDownIcon from '@material-ui/icons/TrendingDown';
import TrendingFlatIcon from '@material-ui/icons/TrendingFlat';
import type { ServiceScore } from '../types';

const useStyles = makeStyles((theme: Theme) =>
  createStyles({
    root: {
      display: 'flex',
      alignItems: 'center',
      gap: theme.spacing(1),
    },
    gradeBadge: {
      width: 48,
      height: 48,
      borderRadius: '50%',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      fontWeight: 'bold',
      fontSize: '1.5rem',
      color: theme.palette.common.white,
    },
    gradeA: {
      backgroundColor: '#4caf50', // green
    },
    gradeB: {
      backgroundColor: '#8bc34a', // light green
    },
    gradeC: {
      backgroundColor: '#ffeb3b', // yellow
      color: theme.palette.text.primary,
    },
    gradeD: {
      backgroundColor: '#ff9800', // orange
    },
    gradeF: {
      backgroundColor: '#f44336', // red
    },
    gradeUnknown: {
      backgroundColor: theme.palette.grey[400],
    },
    scoreText: {
      display: 'flex',
      flexDirection: 'column',
    },
    scoreValue: {
      fontWeight: 'bold',
      fontSize: '1.1rem',
    },
    trendContainer: {
      display: 'flex',
      alignItems: 'center',
      gap: theme.spacing(0.5),
    },
    trendImproving: {
      color: '#4caf50',
    },
    trendDegrading: {
      color: '#f44336',
    },
    trendStable: {
      color: theme.palette.grey[500],
    },
  }),
);

interface ScoreBadgeProps {
  score: ServiceScore | undefined;
}

const gradeColors: Record<string, string> = {
  A: 'gradeA',
  B: 'gradeB',
  C: 'gradeC',
  D: 'gradeD',
  F: 'gradeF',
};

const TrendIcon: React.FC<{ trend: string | null | undefined }> = ({ trend }) => {
  const classes = useStyles();

  if (trend === 'improving') {
    return <TrendingUpIcon className={classes.trendImproving} fontSize="small" />;
  }
  if (trend === 'degrading') {
    return <TrendingDownIcon className={classes.trendDegrading} fontSize="small" />;
  }
  return <TrendingFlatIcon className={classes.trendStable} fontSize="small" />;
};

export const ScoreBadge: React.FC<ScoreBadgeProps> = ({ score }) => {
  const classes = useStyles();

  const grade = score?.grade ?? null;
  const scoreValue = score?.score ?? null;
  const trend = score?.trend ?? null;
  const band = score?.band ?? null;

  const gradeClass = grade ? gradeColors[grade] || 'gradeUnknown' : 'gradeUnknown';
  const displayGrade = grade ?? '?';

  const tooltipText = band
    ? `${band.charAt(0).toUpperCase() + band.slice(1)} reliability (${scoreValue ?? 'N/A'}/100)`
    : 'Reliability score not available';

  return (
    <Tooltip title={tooltipText}>
      <Box className={classes.root}>
        <Box className={`${classes.gradeBadge} ${classes[gradeClass as keyof typeof classes]}`}>
          {displayGrade}
        </Box>
        <Box className={classes.scoreText}>
          <Typography className={classes.scoreValue}>
            {scoreValue !== null ? `${Math.round(scoreValue)}` : 'N/A'}
          </Typography>
          {trend && (
            <Box className={classes.trendContainer}>
              <TrendIcon trend={trend} />
              <Typography variant="caption" color="textSecondary">
                {trend}
              </Typography>
            </Box>
          )}
        </Box>
      </Box>
    </Tooltip>
  );
};
