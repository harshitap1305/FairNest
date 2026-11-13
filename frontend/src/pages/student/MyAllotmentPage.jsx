import React, { useState } from 'react'
import { Box, Typography, Card, CardContent, Chip, Grid, Divider, Button, Alert } from '@mui/material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getMyAllotment, cancelAllotment } from '../../api/allotment'
import HoldPanel from '../../components/allotment/HoldPanel'
import WaitlistCard from '../../components/allotment/WaitlistCard'
import LoadingSpinner from '../../components/common/LoadingSpinner'
import ConfirmDialog from '../../components/common/ConfirmDialog'
import ErrorAlert from '../../components/common/ErrorAlert'

export default function MyAllotmentPage() {
  const qc = useQueryClient()
  const [confirmCancel, setConfirmCancel] = useState(false)
  const [mutError, setMutError] = useState(null)

  const { data: allotment, isLoading, error } = useQuery({
    queryKey: ['my-allotment'],
    queryFn: () => getMyAllotment(),
    retry: false,
    refetchInterval: 30000,
  })

  const cancelMut = useMutation({
    mutationFn: () => cancelAllotment(allotment._id || allotment.id),
    onSuccess: () => {
      setMutError(null)
      qc.invalidateQueries({ queryKey: ['my-allotment'] })
      qc.invalidateQueries({ queryKey: ['my-fairness'] })
    },
    onError: (e) => setMutError(e),
  })

  if (isLoading) return <LoadingSpinner />
  if (error) return <Box sx={{ p: 3 }}><ErrorAlert error={error} /></Box>

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" fontWeight={700} mb={3}>My Allotment</Typography>
      <ErrorAlert error={mutError} />

      {(!allotment || allotment.status !== 'CONFIRMED') && <WaitlistCard />}

      {!allotment && (
        <Card elevation={2}>
          <CardContent>
            <Typography color="text.secondary">
              You have no allotment yet. Once allocation runs for your cycle, any room offered to your group will appear here for member acceptance (no payment step).
            </Typography>
          </CardContent>
        </Card>
      )}

      {allotment?.status === 'HELD' && (
        <HoldPanel allotment={allotment} />
      )}

      {allotment?.status === 'CONFIRMED' && (
        <Card elevation={2}>
          <CardContent>
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={2} flexWrap="wrap" gap={1}>
              <Box display="flex" alignItems="center" gap={2}>
                <Typography variant="h5" fontWeight={700}>Allotment Confirmed</Typography>
                <Chip label="CONFIRMED" color="success" />
              </Box>
              <Button
                variant="outlined"
                color="error"
                size="small"
                onClick={() => setConfirmCancel(true)}
                disabled={cancelMut.isPending}
              >
                Cancel Allotment
              </Button>
            </Box>
            <Divider sx={{ mb: 2 }} />
            <Grid container spacing={2}>
              <Grid item xs={6} sm={3}>
                <Typography variant="overline" color="text.secondary">Hostel</Typography>
                <Typography fontWeight={600}>{allotment.room?.hostel_name || allotment.hostel_name || '—'}</Typography>
              </Grid>
              <Grid item xs={6} sm={3}>
                <Typography variant="overline" color="text.secondary">Floor</Typography>
                <Typography fontWeight={600}>{allotment.room?.floor_no ?? allotment.floor_no ?? '—'}</Typography>
              </Grid>
              <Grid item xs={6} sm={3}>
                <Typography variant="overline" color="text.secondary">Room</Typography>
                <Typography fontWeight={600}>{allotment.room?.room_no || allotment.room_no || allotment.room_id}</Typography>
              </Grid>
              <Grid item xs={6} sm={3}>
                <Typography variant="overline" color="text.secondary">Capacity</Typography>
                <Typography fontWeight={600}>{allotment.room?.capacity ?? '—'}</Typography>
              </Grid>
            </Grid>

            {allotment.members?.length > 0 && (
              <Box mt={3}>
                <Typography variant="h6" mb={1}>Roommates</Typography>
                {allotment.members.map((m) => (
                  <Typography key={m.user_id} variant="body2">
                    {m.name || m.email || m.user_id}{m.roll_no ? ` (${m.roll_no})` : ''} — {m.accept_status}
                  </Typography>
                ))}
              </Box>
            )}
          </CardContent>
        </Card>
      )}

      {allotment && ['CANCELLED', 'DECLINED', 'EXPIRED', 'REVOKED'].includes(allotment.status) && (
        <Card elevation={2} sx={{ borderLeft: '4px solid', borderColor: 'error.main' }}>
          <CardContent>
            <Chip label={allotment.status} color="error" sx={{ mb: 1.5 }} />
            <Alert severity="info">
              {allotment.status === 'REVOKED'
                ? 'This allotment was revoked by an administrator; your group has been placed back into the cascade queue.'
                : 'This allotment was released back to the pool. Check your Fairness & Credits tabs for settlement details.'}
              {allotment.release_reason ? ` (${allotment.release_reason})` : ''}
            </Alert>
          </CardContent>
        </Card>
      )}

      <ConfirmDialog
        open={confirmCancel}
        title="Cancel Confirmed Allotment?"
        message="Cancelling a confirmed room allotment releases the room for cascade and incurs a late-cancellation credit penalty (-1 credit) at settlement."
        confirmLabel="Yes, Cancel Allotment"
        onConfirm={() => {
          setConfirmCancel(false)
          cancelMut.mutate()
        }}
        onCancel={() => setConfirmCancel(false)}
      />
    </Box>
  )
}
