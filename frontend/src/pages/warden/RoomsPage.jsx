import React, { useState, useEffect } from 'react'
import {
  Box, Typography, Grid, Card, CardContent, Tabs, Tab,
  Button, Table, TableBody, TableCell, TableContainer,
  TableHead, TableRow, Paper, Chip, Alert, MenuItem, TextField,
  Dialog, DialogTitle, DialogContent, DialogActions, Stack,
} from '@mui/material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '../../auth/AuthContext'
import { listHostels, listFloors, listHostelRooms } from '../../api/hostel'
import { createHostel, createFloor, getOccupancyReport, updateRoom } from '../../api/admin'
import LoadingSpinner from '../../components/common/LoadingSpinner'
import RoomListInput from '../../components/rooms/RoomListInput'
import { getErrorMessage } from '../../utils/errors'

export default function RoomsPage() {
  const { role } = useAuth()
  const qc = useQueryClient()
  const [hostelTab, setHostelTab] = useState(0)
  const [floorId, setFloorId] = useState('')
  const [mutError, setMutError] = useState(null)

  const [hostelOpen, setHostelOpen] = useState(false)
  const [newHostel, setNewHostel] = useState({ name: '', code: '', allowed_gender: 'ANY' })

  const [floorOpen, setFloorOpen] = useState(false)
  const [newFloor, setNewFloor] = useState({ floor_no: 1, label: '' })

  const { data: hostels = [], isLoading } = useQuery({
    queryKey: ['hostels'],
    queryFn: () => listHostels(),
  })
  const currentHostel = hostels[hostelTab] || null

  const { data: floors = [] } = useQuery({
    queryKey: ['hostel-floors', currentHostel?._id],
    queryFn: () => listFloors(currentHostel._id),
    enabled: Boolean(currentHostel?._id),
  })

  useEffect(() => {
    if (floors.length > 0 && !floors.some((f) => f._id === floorId)) {
      setFloorId(floors[0]._id)
    } else if (floors.length === 0) {
      setFloorId('')
    }
  }, [floors, floorId])

  const { data: rooms = [] } = useQuery({
    queryKey: ['hostel-rooms', currentHostel?._id, floorId],
    queryFn: () => listHostelRooms(currentHostel._id, floorId ? { floor_id: floorId } : {}),
    enabled: Boolean(currentHostel?._id),
  })

  const { data: occupancy } = useQuery({
    queryKey: ['occupancy'],
    queryFn: () => getOccupancyReport(),
  })

  const createHostelMut = useMutation({
    mutationFn: () => createHostel(newHostel),
    onSuccess: () => {
      setHostelOpen(false)
      setNewHostel({ name: '', code: '', allowed_gender: 'ANY' })
      setMutError(null)
      qc.invalidateQueries({ queryKey: ['hostels'] })
    },
    onError: (e) => setMutError(getErrorMessage(e)),
  })

  const createFloorMut = useMutation({
    mutationFn: () =>
      createFloor(currentHostel._id, {
        floor_no: Number(newFloor.floor_no),
        label: newFloor.label || `Floor ${newFloor.floor_no}`,
      }),
    onSuccess: () => {
      setFloorOpen(false)
      setNewFloor({ floor_no: (floors.length || 0) + 1, label: '' })
      setMutError(null)
      qc.invalidateQueries({ queryKey: ['hostel-floors', currentHostel?._id] })
    },
    onError: (e) => setMutError(getErrorMessage(e)),
  })

  const toggleStatusMut = useMutation({
    mutationFn: (room) =>
      updateRoom(room._id, { status: room.status === 'ACTIVE' ? 'MAINTENANCE' : 'ACTIVE' }),
    onSuccess: () => {
      setMutError(null)
      qc.invalidateQueries({ queryKey: ['hostel-rooms', currentHostel?._id] })
    },
    onError: (e) => setMutError(getErrorMessage(e)),
  })

  if (isLoading) return <LoadingSpinner />

  const currentStats = occupancy?.by_hostel?.find((h) => h.hostel_id === currentHostel?._id) || {}

  return (
    <Box sx={{ p: 3 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h4" fontWeight={700}>Hostels & Rooms</Typography>
        {['ADMIN', 'SUPER_ADMIN'].includes(role) && (
          <Button variant="contained" onClick={() => setHostelOpen(true)}>+ New Hostel</Button>
        )}
      </Box>

      {mutError && <Alert severity="error" sx={{ mb: 2 }}>{mutError}</Alert>}

      {!hostels.length ? (
        <Alert severity="info">No hostels configured yet.</Alert>
      ) : (
        <>
          <Tabs
            value={hostelTab}
            onChange={(_, v) => {
              setHostelTab(v)
              setFloorId('')
            }}
            sx={{ mb: 3 }}
          >
            {hostels.map((h) => <Tab key={h._id} label={`${h.name} (${h.code})`} />)}
          </Tabs>

          {currentHostel && (
            <>
              <Grid container spacing={2} mb={3}>
                {[
                  { key: 'total_beds', label: 'Total Beds' },
                  { key: 'occupied_beds', label: 'Confirmed Beds' },
                  { key: 'held_beds', label: 'Held Beds' },
                  { key: 'available_beds', label: 'Available Beds' },
                ].map(({ key, label }) => (
                  <Grid item xs={6} sm={3} key={key}>
                    <Card elevation={1}>
                      <CardContent sx={{ py: 1.5, '&:last-child': { pb: 1.5 } }}>
                        <Typography variant="overline" color="text.secondary" display="block">
                          {label}
                        </Typography>
                        <Typography variant="h5" fontWeight={700}>
                          {currentStats[key] ?? 0}
                        </Typography>
                      </CardContent>
                    </Card>
                  </Grid>
                ))}
              </Grid>

              <Card elevation={2} sx={{ mb: 3 }}>
                <CardContent>
                  <Box display="flex" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={2} mb={2}>
                    <Typography variant="h6">Add Rooms on Floor</Typography>
                    <Stack direction="row" spacing={1.5} alignItems="center">
                      <TextField
                        select
                        label="Floor"
                        size="small"
                        value={floorId}
                        onChange={(e) => setFloorId(e.target.value)}
                        sx={{ minWidth: 180 }}
                      >
                        {floors.map((f) => (
                          <MenuItem key={f._id} value={f._id}>
                            {f.label || `Floor ${f.floor_no}`}
                          </MenuItem>
                        ))}
                      </TextField>
                      <Button variant="outlined" size="small" onClick={() => setFloorOpen(true)}>
                        + Add Floor
                      </Button>
                    </Stack>
                  </Box>

                  {!floorId ? (
                    <Alert severity="info">Add a floor first to add rooms.</Alert>
                  ) : (
                    <RoomListInput
                      floorId={floorId}
                      onCreated={() => qc.invalidateQueries({ queryKey: ['hostel-rooms', currentHostel._id] })}
                    />
                  )}
                </CardContent>
              </Card>

              <TableContainer component={Paper} elevation={2}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell><strong>Room</strong></TableCell>
                      <TableCell><strong>Floor</strong></TableCell>
                      <TableCell><strong>Capacity</strong></TableCell>
                      <TableCell><strong>Status</strong></TableCell>
                      <TableCell><strong>Action</strong></TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {rooms.map((r) => (
                      <TableRow key={r._id} hover>
                        <TableCell fontWeight={600}>{r.room_no}</TableCell>
                        <TableCell>Floor {r.floor_no}</TableCell>
                        <TableCell>{r.capacity}</TableCell>
                        <TableCell>
                          <Chip
                            label={r.status}
                            size="small"
                            color={r.status === 'ACTIVE' ? 'success' : 'warning'}
                          />
                        </TableCell>
                        <TableCell>
                          <Button
                            size="small"
                            onClick={() => toggleStatusMut.mutate(r)}
                            disabled={toggleStatusMut.isPending}
                          >
                            {r.status === 'ACTIVE' ? 'Set Maintenance' : 'Set Active'}
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                    {rooms.length === 0 && (
                      <TableRow>
                        <TableCell colSpan={5} align="center" sx={{ color: 'text.secondary' }}>
                          No rooms on this floor yet.
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </TableContainer>
            </>
          )}
        </>
      )}

      <Dialog open={hostelOpen} onClose={() => setHostelOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>Create Hostel</DialogTitle>
        <DialogContent>
          <TextField
            label="Hostel Name"
            fullWidth
            margin="normal"
            value={newHostel.name}
            onChange={(e) => setNewHostel({ ...newHostel, name: e.target.value })}
          />
          <TextField
            label="Code (e.g. BH1)"
            fullWidth
            margin="normal"
            value={newHostel.code}
            onChange={(e) => setNewHostel({ ...newHostel, code: e.target.value.toUpperCase() })}
          />
          <TextField
            select
            label="Allowed Gender"
            fullWidth
            margin="normal"
            value={newHostel.allowed_gender}
            onChange={(e) => setNewHostel({ ...newHostel, allowed_gender: e.target.value })}
          >
            <MenuItem value="M">Male (M)</MenuItem>
            <MenuItem value="F">Female (F)</MenuItem>
            <MenuItem value="ANY">Any</MenuItem>
          </TextField>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setHostelOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={!newHostel.name || !newHostel.code || createHostelMut.isPending}
            onClick={() => createHostelMut.mutate()}
          >
            Create
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={floorOpen} onClose={() => setFloorOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>Add Floor to {currentHostel?.name}</DialogTitle>
        <DialogContent>
          <TextField
            label="Floor Number"
            type="number"
            fullWidth
            margin="normal"
            value={newFloor.floor_no}
            onChange={(e) => setNewFloor({ ...newFloor, floor_no: e.target.value })}
          />
          <TextField
            label="Label (optional)"
            fullWidth
            margin="normal"
            value={newFloor.label}
            onChange={(e) => setNewFloor({ ...newFloor, label: e.target.value })}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setFloorOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={createFloorMut.isPending}
            onClick={() => createFloorMut.mutate()}
          >
            Add Floor
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
