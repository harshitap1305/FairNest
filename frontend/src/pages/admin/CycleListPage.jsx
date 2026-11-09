import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Box, Typography, Button, Paper, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, Chip, Dialog, DialogTitle,
  DialogContent, DialogActions, TextField, MenuItem, Alert, Stack,
} from '@mui/material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listCycles, createCycle, openCycle, closeCycleEarly, cancelCycle } from '../../api/cycle'
import { listHostels } from '../../api/hostel'
import LoadingSpinner from '../../components/common/LoadingSpinner'
import ErrorAlert from '../../components/common/ErrorAlert'
import ConfirmDialog from '../../components/common/ConfirmDialog'
import { useForm, Controller } from 'react-hook-form'
import { formatDatetime } from '../../utils/dates'
import { getErrorMessage } from '../../utils/errors'

const STATUS_COLORS = {
  DRAFT: 'default',
  SCHEDULED: 'info',
  APPLICATIONS_OPEN: 'success',
  APPLICATIONS_CLOSED: 'warning',
  ALLOCATING: 'info',
  ALLOTMENT_ACTIVE: 'primary',
  CLOSED: 'default',
  SETTLED: 'secondary',
  CANCELLED: 'error',
}

export default function CycleListPage() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [createOpen, setCreateOpen] = useState(false)
  const [cancelTarget, setCancelTarget] = useState(null)
  const [mutError, setMutError] = useState(null)

  const { data: cycles, isLoading, error } = useQuery({
    queryKey: ['cycles'],
    queryFn: () => listCycles(),
  })
  const { data: hostels = [] } = useQuery({
    queryKey: ['hostels'],
    queryFn: () => listHostels(),
  })

  const { register, handleSubmit, reset, control, formState: { errors } } = useForm({
    defaultValues: {
      name: '',
      academic_year: '2026-27',
      hostel_id: '',
      apply_open_at: '',
      apply_close_at: '',
      freeze_hours: 48,
    },
  })

  const hostelMap = Object.fromEntries(hostels.map((h) => [h._id, `${h.name} (${h.code})`]))

  const createMut = useMutation({
    mutationFn: (d) =>
      createCycle({
        name: d.name,
        academic_year: d.academic_year || '2026-27',
        hostel_id: d.hostel_id,
        apply_open_at: d.apply_open_at ? new Date(d.apply_open_at).toISOString() : null,
        apply_close_at: d.apply_close_at ? new Date(d.apply_close_at).toISOString() : null,
        freeze_hours: Number(d.freeze_hours) || 48,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['cycles'] })
      setCreateOpen(false)
      setMutError(null)
      reset()
    },
    onError: (e) => setMutError(getErrorMessage(e)),
  })

  const openMut = useMutation({
    mutationFn: (id) => openCycle(id),
    onSuccess: () => { setMutError(null); qc.invalidateQueries({ queryKey: ['cycles'] }) },
    onError: (e) => setMutError(getErrorMessage(e)),
  })

  const closeMut = useMutation({
    mutationFn: (id) => closeCycleEarly(id),
    onSuccess: () => { setMutError(null); qc.invalidateQueries({ queryKey: ['cycles'] }) },
    onError: (e) => setMutError(getErrorMessage(e)),
  })

  const cancelMut = useMutation({
    mutationFn: (id) => cancelCycle(id, 'Cancelled by administrator'),
    onSuccess: () => { setMutError(null); qc.invalidateQueries({ queryKey: ['cycles'] }); setCancelTarget(null) },
    onError: (e) => setMutError(getErrorMessage(e)),
  })

  if (isLoading) return <LoadingSpinner />
  if (error) return <Box sx={{ p: 3 }}><ErrorAlert error={error} /></Box>

  return (
    <Box sx={{ p: 3 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h4" fontWeight={700}>Allotment Cycles</Typography>
        <Button variant="contained" onClick={() => setCreateOpen(true)}>+ New Cycle</Button>
      </Box>

      {mutError && <Alert severity="error" sx={{ mb: 2 }}>{mutError}</Alert>}

      <TableContainer component={Paper} elevation={2}>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell><strong>Name</strong></TableCell>
              <TableCell><strong>Hostel</strong></TableCell>
              <TableCell><strong>Status</strong></TableCell>
              <TableCell><strong>Window Open</strong></TableCell>
              <TableCell><strong>Window Close</strong></TableCell>
              <TableCell><strong>Actions</strong></TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {(cycles || []).map((c) => (
              <TableRow key={c._id} hover>
                <TableCell>
                  <Button
                    size="small"
                    sx={{ p: 0, textAlign: 'left', fontWeight: 600 }}
                    onClick={() => navigate(`/admin/cycles/${c._id}`)}
                  >
                    {c.name}
                  </Button>
                </TableCell>
                <TableCell>{hostelMap[c.hostel_id] || c.hostel_id}</TableCell>
                <TableCell>
                  <Chip
                    label={c.status.replace(/_/g, ' ')}
                    color={STATUS_COLORS[c.status] || 'default'}
                    size="small"
                  />
                </TableCell>
                <TableCell>{formatDatetime(c.apply_open_at)}</TableCell>
                <TableCell>{formatDatetime(c.apply_close_at)}</TableCell>
                <TableCell>
                  <Stack direction="row" spacing={1}>
                    <Button size="small" onClick={() => navigate(`/admin/cycles/${c._id}`)}>
                      Manage
                    </Button>
                    {['DRAFT', 'SCHEDULED'].includes(c.status) && (
                      <Button size="small" color="success" onClick={() => openMut.mutate(c._id)}>
                        Open Now
                      </Button>
                    )}
                    {c.status === 'APPLICATIONS_OPEN' && (
                      <Button size="small" color="warning" onClick={() => closeMut.mutate(c._id)}>
                        Close Window
                      </Button>
                    )}
                    {!['ALLOCATING', 'ALLOTMENT_ACTIVE', 'CLOSED', 'SETTLED', 'CANCELLED'].includes(c.status) && (
                      <Button size="small" color="error" onClick={() => setCancelTarget(c._id)}>
                        Cancel
                      </Button>
                    )}
                  </Stack>
                </TableCell>
              </TableRow>
            ))}
            {cycles?.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} align="center" sx={{ color: 'text.secondary' }}>
                  No cycles created yet.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>

      <Dialog open={createOpen} onClose={() => setCreateOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Create New Cycle</DialogTitle>
        <Box component="form" onSubmit={handleSubmit((d) => createMut.mutate(d))}>
          <DialogContent>
            {mutError && <Alert severity="error" sx={{ mb: 2 }}>{mutError}</Alert>}
            <Controller
              name="hostel_id"
              control={control}
              rules={{ required: 'Select a hostel' }}
              render={({ field }) => (
                <TextField
                  {...field}
                  select
                  label="Hostel"
                  fullWidth
                  margin="normal"
                  error={!!errors.hostel_id}
                  helperText={errors.hostel_id?.message}
                >
                  {hostels.map((h) => (
                    <MenuItem key={h._id} value={h._id}>{h.name} ({h.code})</MenuItem>
                  ))}
                </TextField>
              )}
            />
            <TextField
              label="Cycle name"
              fullWidth
              margin="normal"
              error={!!errors.name}
              helperText={errors.name?.message}
              {...register('name', { required: 'Required' })}
            />
            <TextField
              label="Academic Year"
              fullWidth
              margin="normal"
              {...register('academic_year')}
            />
            <TextField
              label="Window opens at (optional)"
              type="datetime-local"
              fullWidth
              margin="normal"
              InputLabelProps={{ shrink: true }}
              {...register('apply_open_at')}
            />
            <TextField
              label="Window closes at (optional)"
              type="datetime-local"
              fullWidth
              margin="normal"
              InputLabelProps={{ shrink: true }}
              {...register('apply_close_at')}
            />
            <TextField
              label="Hold freeze duration (hours)"
              type="number"
              fullWidth
              margin="normal"
              {...register('freeze_hours')}
            />
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setCreateOpen(false)}>Cancel</Button>
            <Button type="submit" variant="contained" disabled={createMut.isPending}>
              {createMut.isPending ? 'Creating…' : 'Create'}
            </Button>
          </DialogActions>
        </Box>
      </Dialog>

      <ConfirmDialog
        open={!!cancelTarget}
        title="Cancel Cycle"
        message="Cancel this cycle and release live room reservations? This cannot be undone."
        onConfirm={() => cancelMut.mutate(cancelTarget)}
        onCancel={() => setCancelTarget(null)}
      />
    </Box>
  )
}
