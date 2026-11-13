import React from 'react'
import {
  Box, Paper, Typography, Chip, LinearProgress, Stack, Tooltip, Alert, Divider,
} from '@mui/material'
import InsightsIcon from '@mui/icons-material/Insights'
import { DEMAND_STYLES } from './RoomGrid'

function competitionLabel(ratio) {
  if (ratio == null) return { text: 'No matching rooms', color: 'error' }
  if (ratio <= 0.75) return { text: 'Low competition', color: 'success' }
  if (ratio <= 1.25) return { text: 'Moderate competition', color: 'info' }
  if (ratio <= 2) return { text: 'High competition', color: 'warning' }
  return { text: 'Very high competition', color: 'error' }
}

/**
 * Summary of how contested the cycle is: groups vs. rooms for the student's group size
 * and the most-wanted rooms. Uses only anonymous aggregate counts.
 */
export default function DemandInsightsPanel({ demand, rooms = [], groupSize = 1 }) {
  if (!demand) return null
  const mine = demand.by_size?.find((s) => s.group_size === Number(groupSize))
  const comp = mine ? competitionLabel(mine.groups_per_room) : null
  const roomNo = Object.fromEntries(rooms.map((r) => [r.room_id, r.room_no]))
  const topRooms = Object.entries(demand.rooms || {})
    .filter(([, d]) => d.mentions > 0)
    .sort((a, b) => b[1].score - a[1].score)
    .slice(0, 5)
  const maxScore = topRooms[0]?.[1].score || 1

  return (
    <Paper elevation={2} sx={{ p: 2, mb: 3 }}>
      <Box display="flex" alignItems="center" gap={1} mb={1}>
        <InsightsIcon color="primary" />
        <Typography variant="h6">Demand insights</Typography>
        <Chip size="small" label={`${demand.applications_counted} application${demand.applications_counted === 1 ? '' : 's'} so far`} />
      </Box>
      <Typography variant="body2" color="text.secondary" mb={2}>
        The draw is strategy-proof, so always rank the rooms you truly prefer first. Use this to
        pick sensible backup choices further down your list.
      </Typography>

      <Stack direction={{ xs: 'column', md: 'row' }} spacing={3} divider={<Divider orientation="vertical" flexItem />}>
        <Box flex={1}>
          <Typography variant="subtitle2" gutterBottom>Groups of your size ({groupSize})</Typography>
          {mine ? (
            <>
              <Typography variant="h5" fontWeight={700}>
                {mine.groups} <Typography component="span" color="text.secondary">groups for</Typography>{' '}
                {mine.matching_rooms} <Typography component="span" color="text.secondary">rooms</Typography>
              </Typography>
              <Chip size="small" color={comp.color} label={comp.text} sx={{ mt: 1 }} />
            </>
          ) : (
            <Typography variant="body2" color="text.secondary">No group of your size has applied yet.</Typography>
          )}
        </Box>

        <Box flex={2}>
          <Typography variant="subtitle2" gutterBottom>Most wanted rooms</Typography>
          {demand.insufficient_data ? (
            <Alert severity="info" sx={{ py: 0 }}>
              Room-level demand appears once at least {demand.min_applications} applications are submitted,
              so nobody's choices can be singled out.
            </Alert>
          ) : topRooms.length === 0 ? (
            <Typography variant="body2" color="text.secondary">No room has been ranked yet.</Typography>
          ) : (
            <Stack spacing={0.75}>
              {topRooms.map(([rid, d]) => (
                <Tooltip key={rid} title={`1st choice of ${d.first_choice}, top-3 of ${d.top3}, ranked by ${d.mentions}`} arrow>
                  <Box display="flex" alignItems="center" gap={1.5}>
                    <Typography variant="body2" fontWeight={600} minWidth={84}>
                      Room {roomNo[rid] || '—'}
                    </Typography>
                    <LinearProgress
                      variant="determinate"
                      value={(d.score / maxScore) * 100}
                      color={DEMAND_STYLES[d.level].color}
                      sx={{ flexGrow: 1, height: 8, borderRadius: 4 }}
                    />
                    <Chip size="small" variant="outlined" color={DEMAND_STYLES[d.level].color} label={DEMAND_STYLES[d.level].label} />
                  </Box>
                </Tooltip>
              ))}
            </Stack>
          )}
        </Box>
      </Stack>
    </Paper>
  )
}
