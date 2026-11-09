import React, { useState } from 'react'
import { Box, Typography, Card, CardContent, MenuItem, TextField, Button, Alert } from '@mui/material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listCycles, runCascade } from '../../api/cycle'
import ConfirmDialog from '../../components/common/ConfirmDialog'
import { getErrorMessage } from '../../utils/errors'

export default function CascadePage() {
  const qc = useQueryClient()
  const { data: cycles } = useQuery({ queryKey: ['cycles'], queryFn: () => listCycles() })
  const [cycleId, setCycleId] = useState('')
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [result, setResult] = useState(null)
  const [mutError, setMutError] = useState(null)

  const cascadeMut = useMutation({
    mutationFn: () => runCascade(cycleId),
    onSuccess: (res) => {
      setResult(res)
      setMutError(null)
      qc.invalidateQueries({ queryKey: ['cycles'] })
    },
    onError: (e) => setMutError(getErrorMessage(e)),
  })

  const activeCycles = (cycles || []).filter((c) => c.status === 'ALLOTMENT_ACTIVE')

  return (
    <Box sx={{ p: 3, maxWidth: 620 }}>
      <Typography variant="h4" fontWeight={700} mb={1}>Run Cascade</Typography>
      <Typography color="text.secondary" mb={3}>
        Offer freed rooms (declined, expired, cancelled, or revoked) strictly in the original Round-1 weighted random order.
      </Typography>

      <Card elevation={2}>
        <CardContent>
          {mutError && <Alert severity="error" sx={{ mb: 2 }}>{mutError}</Alert>}
          {result && (
            <Alert severity="success" sx={{ mb: 2 }}>
              Cascade Round #{result.round_no ?? '—'} complete: allotted {result.allotted ?? 0} group(s),{' '}
              {result.remaining_waitlisted ?? 0} remaining waitlisted.
            </Alert>
          )}

          <TextField
            select
            label="Active Cycle"
            value={cycleId}
            onChange={(e) => { setCycleId(e.target.value); setResult(null) }}
            fullWidth
            margin="normal"
          >
            {activeCycles.map((c) => <MenuItem key={c._id} value={c._id}>{c.name}</MenuItem>)}
          </TextField>

          <Button
            variant="contained"
            sx={{ mt: 2 }}
            disabled={!cycleId || cascadeMut.isPending}
            onClick={() => setConfirmOpen(true)}
          >
            {cascadeMut.isPending ? 'Running…' : 'Run Cascade'}
          </Button>
        </CardContent>
      </Card>

      <ConfirmDialog
        open={confirmOpen}
        title="Run Cascade"
        message="This will offer available rooms to waitlisted groups in their original Round-1 order. Continue?"
        onConfirm={() => { setConfirmOpen(false); cascadeMut.mutate() }}
        onCancel={() => setConfirmOpen(false)}
      />
    </Box>
  )
}
