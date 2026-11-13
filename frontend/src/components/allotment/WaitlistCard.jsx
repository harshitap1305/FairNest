import React from 'react'
import {
  Card, CardContent, Typography, Box, Chip, LinearProgress, Grid, Alert,
} from '@mui/material'
import HourglassTopIcon from '@mui/icons-material/HourglassTop'
import { useQuery } from '@tanstack/react-query'
import { listCycles } from '../../api/cycle'
import { getMyWaitlistPosition } from '../../api/insights'

const WAITLIST_CYCLE_STATES = ['ALLOTMENT_ACTIVE', 'ALLOCATING']

function Stat({ label, value, hint }) {
  return (
    <Grid item xs={6} sm={3}>
      <Typography variant="overline" color="text.secondary">{label}</Typography>
      <Typography variant="h5" fontWeight={700}>{value}</Typography>
      {hint && <Typography variant="caption" color="text.secondary">{hint}</Typography>}
    </Grid>
  )
}

/**
 * Shows the student's cascade-queue position for the cycle that is currently
 * offering rooms. Renders nothing when the student is not waitlisted.
 */
export default function WaitlistCard() {
  const { data: cycles } = useQuery({ queryKey: ['cycles'], queryFn: () => listCycles() })
  const active = (cycles || []).find((c) => WAITLIST_CYCLE_STATES.includes(c.status))

  const { data: wl } = useQuery({
    queryKey: ['waitlist-me', active?._id],
    queryFn: () => getMyWaitlistPosition(active._id),
    enabled: Boolean(active?._id),
    retry: false,
    refetchInterval: 30_000,
  })

  if (!wl?.on_waitlist) return null
  const progress = wl.total_waitlisted > 1
    ? ((wl.total_waitlisted - wl.position) / (wl.total_waitlisted - 1)) * 100
    : 100

  return (
    <Card elevation={2} sx={{ mb: 3, borderLeft: '4px solid', borderColor: 'warning.main' }}>
      <CardContent>
        <Box display="flex" alignItems="center" gap={1.5} mb={2} flexWrap="wrap">
          <HourglassTopIcon color="warning" />
          <Typography variant="h6" fontWeight={700}>You're on the waitlist</Typography>
          <Chip size="small" label={active.name} />
          {wl.reinserted && <Chip size="small" color="info" label="Priority re-insert" />}
        </Box>

        <Grid container spacing={2} mb={2}>
          <Stat label="Queue position" value={`#${wl.position}`} hint={`of ${wl.total_waitlisted} waiting`} />
          <Stat label="Same-size groups ahead" value={wl.ahead_same_size} hint={`groups of ${wl.group_size}`} />
          <Stat label="Free rooms that fit" value={wl.fitting_rooms_available} />
          <Stat label="Cycle" value={active.status.replace(/_/g, ' ').toLowerCase()} />
        </Grid>

        <LinearProgress variant="determinate" value={progress} color="warning" sx={{ height: 8, borderRadius: 4, mb: 2 }} />

        <Alert severity="info">
          When a held room is declined, expires or is cancelled, it is offered down this queue in the
          original draw order (no re-shuffle). A room is only offered if it fits your group size and one of
          your preferences, so groups behind you can sometimes be served first. You'll get a notification
          the moment a room is offered.
        </Alert>
      </CardContent>
    </Card>
  )
}
