import React, { useState } from 'react'
import {
  Box, Typography, Paper, Table, TableBody, TableCell, TableContainer,
  TableHead, TableRow, Chip, Button, Alert, Dialog, DialogTitle,
  DialogContent, DialogActions, TextField, MenuItem, Stack,
} from '@mui/material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listAllotments, extendHold, revokeAllotment } from '../../api/allotment'
import LoadingSpinner from '../../components/common/LoadingSpinner'
import { formatDatetime, timeUntil } from '../../utils/dates'
import { getErrorMessage } from '../../utils/errors'

const STATUS_COLORS = {
  HELD: 'warning',
  CONFIRMED: 'success',
  CANCELLED: 'error',
  DECLINED: 'error',
  EXPIRED: 'default',
  REVOKED: 'error',
}

export default function AllotmentMonitorPage() {
  const qc = useQueryClient()
  const [statusFilter, setStatusFilter] = useState('HELD')
  const [modalAction, setModalAction] = useState(null) // { type: 'extend' | 'revoke', allotmentId }
  const [reason, setReason] = useState('')
  const [extraHours, setExtraHours] = useState(24)
  const [mutError, setMutError] = useState(null)

  const { data: allotments, isLoading, error } = useQuery({
    queryKey: ['allotments-warden', statusFilter],
    queryFn: () => listAllotments(statusFilter ? { status: statusFilter } : {}),
    refetchInterval: 30000,
  })

  const extendMut = useMutation({
    mutationFn: () => extendHold(modalAction.allotmentId, reason, Number(extraHours) || 24),
    onSuccess: () => {
      setModalAction(null)
      setReason('')
      setMutError(null)
      qc.invalidateQueries({ queryKey: ['allotments-warden'] })
    },
    onError: (e) => setMutError(getErrorMessage(e)),
  })

  const revokeMut = useMutation({
    mutationFn: () => revokeAllotment(modalAction.allotmentId, reason),
    onSuccess: () => {
      setModalAction(null)
      setReason('')
      setMutError(null)
      qc.invalidateQueries({ queryKey: ['allotments-warden'] })
    },
    onError: (e) => setMutError(getErrorMessage(e)),
  })

  if (isLoading) return <LoadingSpinner />

  const reasonTooShort = reason.trim().length < 10

  return (
    <Box sx={{ p: 3 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3} flexWrap="wrap" gap={2}>
        <Typography variant="h4" fontWeight={700}>Allotment Monitor</Typography>
        <TextField
          select
          label="Status"
          size="small"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          sx={{ minWidth: 180 }}
        >
          <MenuItem value="">All</MenuItem>
          {['HELD', 'CONFIRMED', 'DECLINED', 'EXPIRED', 'CANCELLED', 'REVOKED'].map((s) => (
            <MenuItem key={s} value={s}>{s}</MenuItem>
          ))}
        </TextField>
      </Box>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{getErrorMessage(error)}</Alert>}
      {mutError && <Alert severity="error" sx={{ mb: 2 }}>{mutError}</Alert>}

      {(!allotments || allotments.length === 0) ? (
        <Alert severity="info">No allotments matching this status.</Alert>
      ) : (
        <TableContainer component={Paper} elevation={2}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell><strong>Room</strong></TableCell>
                <TableCell><strong>Hostel</strong></TableCell>
                <TableCell><strong>Status</strong></TableCell>
                <TableCell><strong>Members</strong></TableCell>
                <TableCell><strong>Deadline</strong></TableCell>
                <TableCell><strong>Time Left</strong></TableCell>
                <TableCell><strong>Actions</strong></TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {allotments.map((a) => {
                const pending = a.members?.filter((m) => m.accept_status === 'PENDING').length ?? 0
                const accepted = a.members?.filter((m) => m.accept_status === 'ACCEPTED').length ?? 0
                const deadline = a.expires_at ?? a.hold_deadline
                return (
                  <TableRow key={a._id} hover>
                    <TableCell>{a.room?.room_no || a.room_no || a.room_id}</TableCell>
                    <TableCell>{a.hostel_name || a.room?.hostel_name || '—'}</TableCell>
                    <TableCell>
                      <Chip label={a.status} color={STATUS_COLORS[a.status] || 'default'} size="small" />
                    </TableCell>
                    <TableCell>
                      <Chip label={`${accepted} accepted`} size="small" color="success" sx={{ mr: 0.5 }} />
                      {pending > 0 && <Chip label={`${pending} pending`} size="small" color="warning" />}
                    </TableCell>
                    <TableCell>{a.status === 'HELD' ? formatDatetime(deadline) : '—'}</TableCell>
                    <TableCell sx={{ color: 'warning.main', fontWeight: 600 }}>
                      {a.status === 'HELD' ? timeUntil(deadline) : '—'}
                    </TableCell>
                    <TableCell>
                      <Stack direction="row" spacing={1}>
                        {a.status === 'HELD' && !a.grace_used && (
                          <Button
                            size="small"
                            onClick={() => { setReason(''); setModalAction({ type: 'extend', allotmentId: a._id }) }}
                          >
                            Extend Hold
                          </Button>
                        )}
                        {['HELD', 'CONFIRMED'].includes(a.status) && (
                          <Button
                            size="small"
                            color="error"
                            onClick={() => { setReason(''); setModalAction({ type: 'revoke', allotmentId: a._id }) }}
                          >
                            Revoke
                          </Button>
                        )}
                      </Stack>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      <Dialog open={Boolean(modalAction)} onClose={() => setModalAction(null)} maxWidth="sm" fullWidth>
        <DialogTitle>
          {modalAction?.type === 'extend' ? 'Extend Hold Deadline' : 'Revoke Allotment'}
        </DialogTitle>
        <DialogContent>
          {mutError && <Alert severity="error" sx={{ mb: 2 }}>{mutError}</Alert>}
          <Typography variant="body2" color="text.secondary" mb={2}>
            {modalAction?.type === 'extend'
              ? 'One-time grace extension before hold expiry.'
              : 'Revoking frees the room for cascade and places the group back into the waitlist without credit penalty.'}
          </Typography>
          {modalAction?.type === 'extend' && (
            <TextField
              label="Extra hours"
              type="number"
              fullWidth
              margin="normal"
              inputProps={{ min: 1, max: 72 }}
              value={extraHours}
              onChange={(e) => setExtraHours(e.target.value)}
            />
          )}
          <TextField
            label="Audit Reason (minimum 10 characters)"
            fullWidth
            multiline
            minRows={2}
            margin="normal"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            error={reason.length > 0 && reasonTooShort}
            helperText={reason.length > 0 && reasonTooShort ? 'At least 10 characters required' : ''}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setModalAction(null)}>Cancel</Button>
          <Button
            variant="contained"
            color={modalAction?.type === 'revoke' ? 'error' : 'primary'}
            disabled={reasonTooShort || extendMut.isPending || revokeMut.isPending}
            onClick={() => (modalAction?.type === 'extend' ? extendMut.mutate() : revokeMut.mutate())}
          >
            {modalAction?.type === 'extend' ? 'Extend Hold' : 'Revoke Allotment'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
