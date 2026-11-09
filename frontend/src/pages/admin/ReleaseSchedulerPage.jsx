import React, { useState } from 'react'
import { Box, Typography, Card, CardContent, MenuItem, TextField, Button, Alert } from '@mui/material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listCycles, scheduleCycle } from '../../api/cycle'
import { useForm, Controller } from 'react-hook-form'
import LoadingSpinner from '../../components/common/LoadingSpinner'
import { getErrorMessage } from '../../utils/errors'

export default function ReleaseSchedulerPage() {
  const qc = useQueryClient()
  const { data: cycles, isLoading } = useQuery({ queryKey: ['cycles'], queryFn: () => listCycles() })
  const [mutError, setMutError] = useState(null)
  const [success, setSuccess] = useState(false)
  const { register, handleSubmit, control, formState: { errors } } = useForm({
    defaultValues: { cycle_id: '', apply_open_at: '', apply_close_at: '' },
  })

  const scheduleMut = useMutation({
    mutationFn: (d) =>
      scheduleCycle(d.cycle_id, {
        apply_open_at: new Date(d.apply_open_at).toISOString(),
        apply_close_at: new Date(d.apply_close_at).toISOString(),
      }),
    onSuccess: () => {
      setSuccess(true)
      setMutError(null)
      qc.invalidateQueries({ queryKey: ['cycles'] })
    },
    onError: (e) => {
      setSuccess(false)
      setMutError(getErrorMessage(e))
    },
  })

  const schedulableCycles = (cycles || []).filter((c) => ['DRAFT', 'SCHEDULED'].includes(c.status))
  if (isLoading) return <LoadingSpinner />

  return (
    <Box sx={{ p: 3, maxWidth: 620 }}>
      <Typography variant="h4" fontWeight={700} mb={1}>Release Scheduler</Typography>
      <Typography color="text.secondary" mb={3}>
        Schedule automatic application open and close times for a draft or scheduled cycle (minimum 60-minute window).
      </Typography>

      <Card elevation={2}>
        <CardContent>
          <Box component="form" onSubmit={handleSubmit((d) => scheduleMut.mutate(d))}>
            {mutError && <Alert severity="error" sx={{ mb: 2 }}>{mutError}</Alert>}
            {success && <Alert severity="success" sx={{ mb: 2 }}>Schedule saved! The worker will open and close this cycle automatically.</Alert>}

            <Controller
              name="cycle_id"
              control={control}
              rules={{ required: 'Select a cycle' }}
              render={({ field }) => (
                <TextField
                  {...field}
                  select
                  label="Cycle"
                  fullWidth
                  margin="normal"
                  error={!!errors.cycle_id}
                  helperText={errors.cycle_id?.message}
                >
                  {schedulableCycles.map((c) => (
                    <MenuItem key={c._id} value={c._id}>{c.name} ({c.status})</MenuItem>
                  ))}
                </TextField>
              )}
            />
            <TextField
              label="Opens at"
              type="datetime-local"
              fullWidth
              margin="normal"
              InputLabelProps={{ shrink: true }}
              error={!!errors.apply_open_at}
              helperText={errors.apply_open_at?.message}
              {...register('apply_open_at', { required: 'Open time is required' })}
            />
            <TextField
              label="Closes at"
              type="datetime-local"
              fullWidth
              margin="normal"
              InputLabelProps={{ shrink: true }}
              error={!!errors.apply_close_at}
              helperText={errors.apply_close_at?.message}
              {...register('apply_close_at', { required: 'Close time is required' })}
            />
            <Button type="submit" variant="contained" sx={{ mt: 2 }} disabled={scheduleMut.isPending}>
              {scheduleMut.isPending ? 'Saving…' : 'Save Schedule'}
            </Button>
          </Box>
        </CardContent>
      </Card>
    </Box>
  )
}
