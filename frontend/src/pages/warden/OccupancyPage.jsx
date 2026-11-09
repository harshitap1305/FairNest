import React, { useState } from 'react'
import {
  Box, Typography, Grid, Card, CardContent, LinearProgress, MenuItem, TextField,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Paper,
} from '@mui/material'
import { useQuery } from '@tanstack/react-query'
import { getOccupancyReport } from '../../api/admin'
import { listCycles } from '../../api/cycle'
import LoadingSpinner from '../../components/common/LoadingSpinner'
import ErrorAlert from '../../components/common/ErrorAlert'

export default function OccupancyPage() {
  const [cycleId, setCycleId] = useState('')
  const { data: cycles = [] } = useQuery({ queryKey: ['cycles'], queryFn: () => listCycles() })
  const { data: occupancy, isLoading, error } = useQuery({
    queryKey: ['occupancy', cycleId],
    queryFn: () => getOccupancyReport(cycleId ? { cycle_id: cycleId } : {}),
  })

  if (isLoading) return <LoadingSpinner />
  if (error) return <Box sx={{ p: 3 }}><ErrorAlert error={error} /></Box>

  const byHostel = occupancy?.by_hostel || []
  const byFloor = Object.values(occupancy?.by_floor || {}).sort((a, b) => a.floor_no - b.floor_no)

  return (
    <Box sx={{ p: 3 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={2} mb={3}>
        <Typography variant="h4" fontWeight={700}>Hostel Occupancy</Typography>
        <TextField
          select
          label="Cycle Filter"
          size="small"
          value={cycleId}
          onChange={(e) => setCycleId(e.target.value)}
          sx={{ minWidth: 260 }}
        >
          <MenuItem value="">All Managed Cycles</MenuItem>
          {cycles.map((c) => (
            <MenuItem key={c._id} value={c._id}>{c.name}</MenuItem>
          ))}
        </TextField>
      </Box>

      <Grid container spacing={3} mb={4}>
        {byHostel.map((h) => {
          const pct = h.total_beds > 0 ? Math.round((h.occupied_beds / h.total_beds) * 100) : 0
          return (
            <Grid item xs={12} sm={6} md={4} key={h.hostel_id}>
              <Card elevation={2}>
                <CardContent>
                  <Typography variant="h6" fontWeight={700}>
                    {h.hostel_name} {h.hostel_code ? `(${h.hostel_code})` : ''}
                  </Typography>
                  <LinearProgress
                    variant="determinate"
                    value={pct}
                    color={pct > 90 ? 'error' : pct > 70 ? 'warning' : 'success'}
                    sx={{ my: 1.5, height: 8, borderRadius: 4 }}
                  />
                  <Typography variant="body2">
                    Confirmed: {h.occupied_beds} / {h.total_beds} beds ({pct}%)
                  </Typography>
                  <Typography variant="body2" color="warning.main">
                    Held: {h.held_beds} · Available: {h.available_beds}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
          )
        })}
      </Grid>

      {byFloor.length > 0 && (
        <TableContainer component={Paper} elevation={2}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell><strong>Floor</strong></TableCell>
                <TableCell><strong>Total Beds</strong></TableCell>
                <TableCell><strong>Confirmed Beds</strong></TableCell>
                <TableCell><strong>Held Beds</strong></TableCell>
                <TableCell><strong>Available Rooms</strong></TableCell>
                <TableCell><strong>Blocked Rooms</strong></TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {byFloor.map((f) => (
                <TableRow key={f.floor_no} hover>
                  <TableCell>Floor {f.floor_no}</TableCell>
                  <TableCell>{f.total_beds}</TableCell>
                  <TableCell>{f.occupied_beds}</TableCell>
                  <TableCell>{f.held_beds}</TableCell>
                  <TableCell sx={{ color: 'success.main', fontWeight: 600 }}>{f.available ?? 0}</TableCell>
                  <TableCell>{f.blocked ?? 0}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Box>
  )
}
