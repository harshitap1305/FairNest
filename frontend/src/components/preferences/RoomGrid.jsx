import React from 'react'
import { Box, Grid, Paper, Typography, Tooltip, Chip } from '@mui/material'
import LocalFireDepartmentIcon from '@mui/icons-material/LocalFireDepartment'

const STATUS_COLORS = {
  AVAILABLE: { bg: '#e8f5e9', border: '#66bb6a', label: 'Available' },
  HELD: { bg: '#fff8e1', border: '#ffa726', label: 'Held' },
  CONFIRMED: { bg: '#e3f2fd', border: '#42a5f5', label: 'Confirmed' },
  BLOCKED: { bg: '#f5f5f5', border: '#bdbdbd', label: 'Blocked' },
}

export const DEMAND_STYLES = {
  HIGH: { label: 'High demand', color: 'error' },
  MEDIUM: { label: 'Popular', color: 'warning' },
  LOW: { label: 'Some interest', color: 'info' },
  NONE: { label: 'Not yet ranked', color: 'success' },
}

function demandTooltip(d) {
  if (!d) return ''
  if (!d.mentions) return 'No submitted application ranks this room yet.'
  return `1st choice of ${d.first_choice} · top-3 of ${d.top3} · ranked by ${d.mentions} group${d.mentions === 1 ? '' : 's'}`
}

/**
 * Grid of room tiles for preference selection.
 * Optional `demand` maps room_id -> { level, first_choice, top3, mentions } from the
 * room-demand endpoint; when present each tile shows a popularity badge.
 */
export default function RoomGrid({
  rooms = [],
  selected = [],
  groupSize = 1,
  fillRule = 'EXACT',
  onToggle,
  demand = null,
}) {
  if (rooms.length === 0) {
    return (
      <Box sx={{ p: 3, textAlign: 'center' }}>
        <Typography variant="body2" color="text.secondary">
          No rooms match your filter.
        </Typography>
      </Box>
    )
  }

  return (
    <Grid container spacing={1.5}>
      {rooms.map((room) => {
        const rid = room.room_id || room._id || room.id
        const statusKey = STATUS_COLORS[room.status] ? room.status : 'BLOCKED'
        const colors = STATUS_COLORS[statusKey]
        const cap = Number(room.capacity ?? 1)
        const sizeFits = fillRule === 'EXACT' ? cap === Number(groupSize) : cap >= Number(groupSize)
        const isSelected = selected.includes(rid)
        const isClickable = statusKey === 'AVAILABLE' && sizeFits

        let tip = colors.label
        if (statusKey === 'AVAILABLE' && !sizeFits) {
          tip =
            fillRule === 'EXACT'
              ? `Requires exact group size ${cap} (your group has ${groupSize})`
              : `Room capacity (${cap}) is smaller than your group (${groupSize})`
        }

        return (
          <Grid item xs={6} sm={4} md={3} key={rid}>
            <Tooltip title={tip} arrow>
              <Paper
                variant="outlined"
                onClick={() => isClickable && onToggle?.(room)}
                sx={{
                  p: 1.5,
                  cursor: isClickable ? 'pointer' : 'not-allowed',
                  opacity: isClickable || isSelected ? 1 : 0.6,
                  bgcolor: isSelected ? '#bbdefb' : colors.bg,
                  borderColor: isSelected ? 'primary.main' : colors.border,
                  borderWidth: isSelected ? 2 : 1,
                  transition: 'all 0.15s',
                  '&:hover': isClickable
                    ? { boxShadow: 2, transform: 'translateY(-1px)' }
                    : {},
                }}
              >
                <Typography variant="subtitle2" fontWeight={700}>
                  Room {room.room_no || rid}
                </Typography>
                <Typography variant="caption" display="block" color="text.secondary">
                  Capacity: {cap} · Floor {room.floor_no ?? '—'}
                </Typography>
                <Box sx={{ mt: 0.5, display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
                  <Chip
                    label={colors.label}
                    size="small"
                    sx={{
                      bgcolor: colors.bg,
                      borderColor: colors.border,
                      fontSize: '0.65rem',
                      height: 18,
                    }}
                    variant="outlined"
                  />
                  {demand?.[rid] && demand[rid].level !== 'NONE' && (
                    <Tooltip title={demandTooltip(demand[rid])} arrow>
                      <Chip
                        icon={demand[rid].level === 'HIGH' ? <LocalFireDepartmentIcon sx={{ fontSize: 12 }} /> : undefined}
                        label={DEMAND_STYLES[demand[rid].level].label}
                        size="small"
                        color={DEMAND_STYLES[demand[rid].level].color}
                        variant={demand[rid].level === 'HIGH' ? 'filled' : 'outlined'}
                        sx={{ fontSize: '0.65rem', height: 18 }}
                      />
                    </Tooltip>
                  )}
                  {!sizeFits && statusKey === 'AVAILABLE' && (
                    <Chip
                      label={`Size ${cap}`}
                      size="small"
                      color="default"
                      sx={{ fontSize: '0.65rem', height: 18 }}
                    />
                  )}
                </Box>
              </Paper>
            </Tooltip>
          </Grid>
        )
      })}
    </Grid>
  )
}
