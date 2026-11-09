import React, { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Box, Typography, Card, CardContent, TextField, Button,
  Chip, Alert, Stack, Grid,
} from '@mui/material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getCycle, openCycle, closeCycleEarly, cancelCycle,
  extendCycle, reopenCycle, settleCycle,
} from '../../api/cycle'
import { listHostels } from '../../api/hostel'
import LoadingSpinner from '../../components/common/LoadingSpinner'
import ConfirmDialog from '../../components/common/ConfirmDialog'
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

export default function CycleEditorPage() {
  const { cycleId } = useParams()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [confirmAction, setConfirmAction] = useState(null)
  const [mutError, setMutError] = useState(null)
  const [infoMsg, setInfoMsg] = useState(null)
  const [newCloseAt, setNewCloseAt] = useState('')
  const [actionReason, setActionReason] = useState('')

  const { data: cycle, isLoading } = useQuery({
    queryKey: ['cycle', cycleId],
    queryFn: () => getCycle(cycleId),
    enabled: Boolean(cycleId),
  })
  const { data: hostels = [] } = useQuery({ queryKey: ['hostels'], queryFn: () => listHostels() })

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['cycle', cycleId] })
    qc.invalidateQueries({ queryKey: ['cycles'] })
  }

  const openMut = useMutation({
    mutationFn: () => openCycle(cycleId),
    onSuccess: () => { setMutError(null); setInfoMsg('Cycle opened & inventory snapshotted.'); refresh() },
    onError: (e) => setMutError(getErrorMessage(e)),
  })

  const closeMut = useMutation({
    mutationFn: () => closeCycleEarly(cycleId),
    onSuccess: () => { setMutError(null); setInfoMsg('Application window closed & groups locked.'); refresh() },
    onError: (e) => setMutError(getErrorMessage(e)),
  })

  const extendMut = useMutation({
    mutationFn: () => extendCycle(cycleId, {
      new_close_at: new Date(newCloseAt).toISOString(),
      reason: actionReason,
    }),
    onSuccess: () => { setMutError(null); setInfoMsg('Window extended.'); setNewCloseAt(''); setActionReason(''); refresh() },
    onError: (e) => setMutError(getErrorMessage(e)),
  })

  const reopenMut = useMutation({
    mutationFn: () => reopenCycle(cycleId, {
      apply_close_at: new Date(newCloseAt).toISOString(),
      reason: actionReason,
    }),
    onSuccess: () => { setMutError(null); setInfoMsg('Cycle reopened for applications.'); setNewCloseAt(''); setActionReason(''); refresh() },
    onError: (e) => setMutError(getErrorMessage(e)),
  })

  const cancelMut = useMutation({
    mutationFn: () => cancelCycle(cycleId, 'Cancelled from Cycle Details'),
    onSuccess: () => navigate('/admin/cycles'),
    onError: (e) => setMutError(getErrorMessage(e)),
  })

  const settleMut = useMutation({
    mutationFn: () => settleCycle(cycleId),
    onSuccess: (res) => {
      setMutError(null)
      setInfoMsg(`Cycle settled (${res?.settled_users ?? 0} students updated).`)
      refresh()
    },
    onError: (e) => setMutError(getErrorMessage(e)),
  })

  if (!cycleId) return <Box sx={{ p: 3 }}><Alert severity="info">Select a cycle from the list to manage.</Alert></Box>
  if (isLoading) return <LoadingSpinner />
  if (!cycle) return <Box sx={{ p: 3 }}><Alert severity="error">Cycle not found.</Alert></Box>

  const hostel = hostels.find((h) => h._id === cycle.hostel_id)
  const roomCounts = cycle.room_counts || {}
  const stats = cycle.stats || {}

  return (
    <Box sx={{ p: 3 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3} flexWrap="wrap" gap={1}>
        <Box>
          <Typography variant="h4" fontWeight={700}>{cycle.name}</Typography>
          <Typography color="text.secondary">
            {hostel ? `${hostel.name} (${hostel.code})` : cycle.hostel_id} · {cycle.academic_year}
          </Typography>
        </Box>
        <Chip label={cycle.status.replace(/_/g, ' ')} color={STATUS_COLORS[cycle.status] || 'default'} />
      </Box>

      {mutError && <Alert severity="error" sx={{ mb: 2 }}>{mutError}</Alert>}
      {infoMsg && <Alert severity="success" sx={{ mb: 2 }}>{infoMsg}</Alert>}

      <Card elevation={2} sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" mb={2}>Cycle Summary</Typography>
          <Grid container spacing={2}>
            <Grid item xs={6} sm={3}>
              <Typography variant="overline" color="text.secondary">Window Opens</Typography>
              <Typography>{formatDatetime(cycle.apply_open_at)}</Typography>
            </Grid>
            <Grid item xs={6} sm={3}>
              <Typography variant="overline" color="text.secondary">Window Closes</Typography>
              <Typography>{formatDatetime(cycle.apply_close_at)}</Typography>
            </Grid>
            <Grid item xs={6} sm={3}>
              <Typography variant="overline" color="text.secondary">Freeze Duration</Typography>
              <Typography>{cycle.freeze_hours ?? 48}h</Typography>
            </Grid>
            <Grid item xs={6} sm={3}>
              <Typography variant="overline" color="text.secondary">Rooms / Applications</Typography>
              <Typography>
                Avail {roomCounts.AVAILABLE ?? 0} · Held {roomCounts.HELD ?? 0} · Conf {roomCounts.CONFIRMED ?? 0} · Apps {stats.n_applications ?? stats.applications_submitted ?? 0}
              </Typography>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      <Card elevation={2} sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" mb={2}>Lifecycle Actions</Typography>
          <Stack direction="row" spacing={2} flexWrap="wrap">
            {['DRAFT', 'SCHEDULED'].includes(cycle.status) && (
              <Button variant="contained" onClick={() => openMut.mutate()} disabled={openMut.isPending}>
                Open Cycle
              </Button>
            )}
            {cycle.status === 'APPLICATIONS_OPEN' && (
              <Button variant="outlined" color="warning" onClick={() => setConfirmAction('close')}>
                Close Window Early
              </Button>
            )}
            {cycle.status === 'APPLICATIONS_CLOSED' && (
              <Button variant="contained" onClick={() => navigate('/admin/allocation')}>
                Go to Allocation Console →
              </Button>
            )}
            {['ALLOTMENT_ACTIVE', 'CLOSED'].includes(cycle.status) && (
              <Button variant="contained" color="secondary" onClick={() => setConfirmAction('settle')}>
                Settle Cycle & Update Credits
              </Button>
            )}
            {!['ALLOCATING', 'ALLOTMENT_ACTIVE', 'CLOSED', 'SETTLED', 'CANCELLED'].includes(cycle.status) && (
              <Button color="error" variant="outlined" onClick={() => setConfirmAction('cancel')}>
                Cancel Cycle
              </Button>
            )}
          </Stack>
        </CardContent>
      </Card>

      {['APPLICATIONS_OPEN', 'APPLICATIONS_CLOSED'].includes(cycle.status) && (
        <Card elevation={2}>
          <CardContent>
            <Typography variant="h6" mb={2}>
              {cycle.status === 'APPLICATIONS_OPEN' ? 'Extend Close Time' : 'Reopen Application Window'}
            </Typography>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems="center">
              <TextField
                label="New close time"
                type="datetime-local"
                size="small"
                InputLabelProps={{ shrink: true }}
                value={newCloseAt}
                onChange={(e) => setNewCloseAt(e.target.value)}
              />
              <TextField
                label="Reason"
                size="small"
                value={actionReason}
                onChange={(e) => setActionReason(e.target.value)}
                sx={{ flex: 1 }}
              />
              {cycle.status === 'APPLICATIONS_OPEN' ? (
                <Button
                  variant="contained"
                  disabled={!newCloseAt || extendMut.isPending}
                  onClick={() => extendMut.mutate()}
                >
                  Extend Window
                </Button>
              ) : (
                <Button
                  variant="contained"
                  disabled={!newCloseAt || reopenMut.isPending}
                  onClick={() => reopenMut.mutate()}
                >
                  Reopen Window
                </Button>
              )}
            </Stack>
          </CardContent>
        </Card>
      )}

      <ConfirmDialog
        open={confirmAction === 'cancel'}
        title="Cancel Cycle"
        message="Cancel this cycle? This cannot be undone."
        onConfirm={() => { cancelMut.mutate(); setConfirmAction(null) }}
        onCancel={() => setConfirmAction(null)}
      />
      <ConfirmDialog
        open={confirmAction === 'close'}
        title="Close Application Window"
        message="Close applications now and freeze group credit snapshots?"
        onConfirm={() => { closeMut.mutate(); setConfirmAction(null) }}
        onCancel={() => setConfirmAction(null)}
      />
      <ConfirmDialog
        open={confirmAction === 'settle'}
        title="Settle Cycle"
        message="Settle all finalized outcomes and credit ledgers for this cycle? Active holds must be resolved first."
        onConfirm={() => { settleMut.mutate(); setConfirmAction(null) }}
        onCancel={() => setConfirmAction(null)}
      />
    </Box>
  )
}
