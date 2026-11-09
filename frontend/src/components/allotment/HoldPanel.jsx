import React, { useState } from 'react'
import {
  Box,
  Typography,
  Card,
  CardContent,
  Divider,
  Chip,
  List,
  ListItem,
  ListItemText,
  Button,
  Stack,
  Alert,
} from '@mui/material'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import CancelIcon from '@mui/icons-material/Cancel'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '../../auth/AuthContext'
import { acceptAllotment, declineAllotment } from '../../api/allotment'
import CountdownTimer from '../common/CountdownTimer'
import ConfirmDialog from '../common/ConfirmDialog'
import ErrorAlert from '../common/ErrorAlert'
import { formatDatetime } from '../../utils/dates'

const STATUS_COLOR = {
  PENDING: 'warning',
  ACCEPTED: 'success',
  DECLINED: 'error',
}

/**
 * Panel shown when a student has a HELD allotment.
 * No payment UI — flow is HELD -> all members accept -> CONFIRMED.
 */
export default function HoldPanel({ allotment }) {
  const { user } = useAuth()
  const qc = useQueryClient()
  const [confirmDecline, setConfirmDecline] = useState(false)
  const [mutError, setMutError] = useState(null)

  const allotmentId = allotment?._id || allotment?.id

  const acceptMut = useMutation({
    mutationFn: () => acceptAllotment(allotmentId),
    onSuccess: () => {
      setMutError(null)
      qc.invalidateQueries({ queryKey: ['my-allotment'] })
      qc.invalidateQueries({ queryKey: ['my-fairness'] })
    },
    onError: (err) => setMutError(err),
  })

  const declineMut = useMutation({
    mutationFn: () => declineAllotment(allotmentId),
    onSuccess: () => {
      setMutError(null)
      qc.invalidateQueries({ queryKey: ['my-allotment'] })
      qc.invalidateQueries({ queryKey: ['my-fairness'] })
    },
    onError: (err) => setMutError(err),
  })

  const room = allotment?.room ?? {}
  const members = allotment?.members ?? []
  const deadline = allotment?.expires_at ?? allotment?.hold_deadline
  const myMember = members.find((m) => String(m.user_id) === String(user?.id))
  const iAlreadyAccepted = myMember?.accept_status === 'ACCEPTED'

  return (
    <Box>
      <ErrorAlert error={mutError} />

      <Card variant="outlined" sx={{ mb: 2 }}>
        <CardContent>
          <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
            <Box>
              <Typography variant="h6" fontWeight={700}>
                Room {room.room_no || allotment?.room_no || allotment?.room_id}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {room.hostel_name || allotment?.hostel_name || ''}
                {(room.floor_no ?? allotment?.floor_no) != null
                  ? ` · Floor ${room.floor_no ?? allotment?.floor_no}`
                  : ''}
                {room.capacity ? ` · Capacity ${room.capacity}` : ''}
              </Typography>
              <Stack direction="row" spacing={1} mt={1}>
                {allotment?.rank_obtained && (
                  <Chip
                    label={`Preference #${allotment.rank_obtained}`}
                    size="small"
                    variant="outlined"
                    color="primary"
                  />
                )}
                {allotment?.round_no && (
                  <Chip label={`Round ${allotment.round_no}`} size="small" variant="outlined" />
                )}
              </Stack>
            </Box>
            <Chip label="HELD" color="warning" variant="filled" />
          </Stack>

          <Divider sx={{ my: 2 }} />

          <Typography variant="body2" color="text.secondary" gutterBottom>
            Hold expires: {formatDatetime(deadline)}
          </Typography>
          <CountdownTimer deadline={deadline} />
        </CardContent>
      </Card>

      {iAlreadyAccepted && (
        <Alert severity="info" sx={{ mb: 2 }}>
          You have accepted this room offer. Waiting for all remaining group members to accept to confirm.
        </Alert>
      )}

      <Typography variant="subtitle1" fontWeight={600} gutterBottom>
        Group Member Responses
      </Typography>
      <Card variant="outlined" sx={{ mb: 2 }}>
        <List disablePadding>
          {members.map((m, i) => (
            <React.Fragment key={m.user_id ?? i}>
              {i > 0 && <Divider />}
              <ListItem>
                <ListItemText
                  primary={m.name || m.roll_no || m.email || `Member ${i + 1}`}
                  secondary={[m.roll_no, m.email].filter(Boolean).join(' · ')}
                />
                <Chip
                  label={m.accept_status ?? 'PENDING'}
                  color={STATUS_COLOR[m.accept_status] ?? 'default'}
                  size="small"
                />
              </ListItem>
            </React.Fragment>
          ))}
          {members.length === 0 && (
            <ListItem>
              <ListItemText secondary="No member data available." />
            </ListItem>
          )}
        </List>
      </Card>

      {/* Action buttons — NO payment */}
      <Stack direction="row" spacing={2}>
        <Button
          variant="contained"
          color="success"
          startIcon={<CheckCircleIcon />}
          onClick={() => acceptMut.mutate()}
          disabled={iAlreadyAccepted || acceptMut.isPending || declineMut.isPending}
        >
          {iAlreadyAccepted
            ? 'Accepted'
            : acceptMut.isPending
            ? 'Accepting…'
            : 'Accept Room'}
        </Button>
        <Button
          variant="outlined"
          color="error"
          startIcon={<CancelIcon />}
          onClick={() => setConfirmDecline(true)}
          disabled={acceptMut.isPending || declineMut.isPending}
        >
          Decline Offer
        </Button>
      </Stack>

      <ConfirmDialog
        open={confirmDecline}
        title="Decline Allotment?"
        message="Declining releases the held room back for cascade allotment and counts as a forfeit for credit settlement. This cannot be undone."
        confirmLabel="Yes, Decline"
        onConfirm={() => {
          setConfirmDecline(false)
          declineMut.mutate()
        }}
        onCancel={() => setConfirmDecline(false)}
      />
    </Box>
  )
}
