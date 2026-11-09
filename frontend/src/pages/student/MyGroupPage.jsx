import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Box, Typography, Button, Card, CardContent, List, ListItem,
  ListItemText, Chip, Dialog, DialogTitle, DialogContent, DialogActions,
  TextField, IconButton, Alert, Divider, MenuItem, Stack,
} from '@mui/material'
import PersonRemoveIcon from '@mui/icons-material/PersonRemove'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '../../auth/AuthContext'
import { listCycles } from '../../api/cycle'
import {
  getMyGroup, getMyInvites, createGroup, inviteMember, acceptInvite,
  declineInvite, removeMember, disbandGroup,
} from '../../api/group'
import LoadingSpinner from '../../components/common/LoadingSpinner'
import ConfirmDialog from '../../components/common/ConfirmDialog'
import { getErrorMessage } from '../../utils/errors'

const MEMBER_COLOR = { ACCEPTED: 'success', INVITED: 'warning', DECLINED: 'error' }

export default function MyGroupPage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const qc = useQueryClient()

  const { data: cycles, isLoading: cyclesLoading } = useQuery({
    queryKey: ['cycles'],
    queryFn: () => listCycles(),
  })

  const [cycleId, setCycleId] = useState('')

  useEffect(() => {
    if (!cycleId && cycles?.length) {
      const preferred =
        cycles.find((c) => c.status === 'APPLICATIONS_OPEN') ||
        cycles.find((c) => c.status === 'SCHEDULED') ||
        cycles[0]
      setCycleId(preferred._id)
    }
  }, [cycles, cycleId])

  const { data: group, isLoading: groupLoading } = useQuery({
    queryKey: ['my-group', cycleId],
    queryFn: () => getMyGroup(cycleId),
    enabled: Boolean(cycleId),
    retry: false,
  })

  const { data: pendingInvites = [] } = useQuery({
    queryKey: ['my-invites', cycleId],
    queryFn: () => getMyInvites(cycleId),
    enabled: Boolean(cycleId) && !group,
    retry: false,
  })

  const [createOpen, setCreateOpen] = useState(false)
  const [groupName, setGroupName] = useState('')
  const [inviteIdentifier, setInviteIdentifier] = useState('')
  const [inviteError, setInviteError] = useState(null)
  const [disbandOpen, setDisbandOpen] = useState(false)
  const [mutError, setMutError] = useState(null)

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['my-group'] })
    qc.invalidateQueries({ queryKey: ['my-invites'] })
  }

  const createMut = useMutation({
    mutationFn: ({ solo }) => createGroup(cycleId, { name: groupName, solo }),
    onSuccess: () => {
      setCreateOpen(false)
      setGroupName('')
      setMutError(null)
      invalidate()
    },
    onError: (e) => setMutError(getErrorMessage(e)),
  })

  const inviteMut = useMutation({
    mutationFn: () => inviteMember(group._id, inviteIdentifier),
    onSuccess: () => {
      setInviteIdentifier('')
      setInviteError(null)
      invalidate()
    },
    onError: (e) => setInviteError(getErrorMessage(e)),
  })

  const acceptMut = useMutation({
    mutationFn: (membershipId) => acceptInvite(membershipId),
    onSuccess: () => { setMutError(null); invalidate() },
    onError: (e) => setMutError(getErrorMessage(e)),
  })

  const declineMut = useMutation({
    mutationFn: (membershipId) => declineInvite(membershipId),
    onSuccess: () => { setMutError(null); invalidate() },
    onError: (e) => setMutError(getErrorMessage(e)),
  })

  const removeMut = useMutation({
    mutationFn: ({ groupId, userId }) => removeMember(groupId, userId),
    onSuccess: () => { setMutError(null); invalidate() },
    onError: (e) => setMutError(getErrorMessage(e)),
  })

  const disbandMut = useMutation({
    mutationFn: () => disbandGroup(group._id),
    onSuccess: () => { setMutError(null); invalidate() },
    onError: (e) => setMutError(getErrorMessage(e)),
  })

  if (cyclesLoading || (cycleId && groupLoading)) return <LoadingSpinner />

  if (!cycles?.length) {
    return (
      <Box sx={{ p: 3 }}>
        <Typography variant="h4" fontWeight={700} mb={2}>My Group</Typography>
        <Alert severity="info">No allotment cycles are available for your hostel yet.</Alert>
      </Box>
    )
  }

  const selectedCycle = cycles.find((c) => c._id === cycleId)
  const isCycleOpen = selectedCycle?.status === 'APPLICATIONS_OPEN'
  const isLeader = group && String(group.leader_id) === String(user?.id)
  const canModify = Boolean(isCycleOpen && group && !['LOCKED', 'DISBANDED'].includes(group.status))

  return (
    <Box sx={{ p: 3 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={2} mb={3}>
        <Typography variant="h4" fontWeight={700}>My Group</Typography>
        <TextField
          select
          label="Cycle"
          size="small"
          value={cycleId}
          onChange={(e) => setCycleId(e.target.value)}
          sx={{ minWidth: 260 }}
        >
          {cycles.map((c) => (
            <MenuItem key={c._id} value={c._id}>
              {c.name} ({c.status.replace(/_/g, ' ')})
            </MenuItem>
          ))}
        </TextField>
      </Box>

      {mutError && <Alert severity="error" sx={{ mb: 2 }}>{mutError}</Alert>}
      {!isCycleOpen && selectedCycle && (
        <Alert severity="info" sx={{ mb: 2 }}>
          This cycle is currently <strong>{selectedCycle.status.replace(/_/g, ' ')}</strong>. Group edits are only allowed while applications are open.
        </Alert>
      )}

      {!group ? (
        <Box>
          <Card elevation={2} sx={{ mb: 3 }}>
            <CardContent>
              <Typography color="text.secondary" mb={2}>
                You are not currently in a group for <strong>{selectedCycle?.name}</strong>.
              </Typography>
              <Stack direction="row" spacing={2} flexWrap="wrap">
                <Button
                  variant="contained"
                  disabled={!isCycleOpen || createMut.isPending}
                  onClick={() => setCreateOpen(true)}
                >
                  Create a Group
                </Button>
                <Button
                  variant="outlined"
                  disabled={!isCycleOpen || createMut.isPending}
                  onClick={() => createMut.mutate({ solo: true })}
                >
                  Apply Solo
                </Button>
              </Stack>
            </CardContent>
          </Card>

          {pendingInvites.length > 0 && (
            <Card elevation={2}>
              <CardContent>
                <Typography variant="h6" mb={1}>Pending Invitations</Typography>
                <List disablePadding>
                  {pendingInvites.map((inv, idx) => (
                    <React.Fragment key={inv._id}>
                      {idx > 0 && <Divider />}
                      <ListItem
                        secondaryAction={
                          <Stack direction="row" spacing={1}>
                            <Button
                              size="small"
                              variant="contained"
                              disabled={!isCycleOpen || acceptMut.isPending}
                              onClick={() => acceptMut.mutate(inv._id)}
                            >
                              Accept
                            </Button>
                            <Button
                              size="small"
                              color="error"
                              disabled={declineMut.isPending}
                              onClick={() => declineMut.mutate(inv._id)}
                            >
                              Decline
                            </Button>
                          </Stack>
                        }
                      >
                        <ListItemText
                          primary={inv.group_name || 'Room Group'}
                          secondary={`Invited by ${inv.leader_name || 'Leader'} (${inv.leader_roll_no || ''}) · Current size ${inv.group_size ?? 1}`}
                        />
                      </ListItem>
                    </React.Fragment>
                  ))}
                </List>
              </CardContent>
            </Card>
          )}

          <Dialog open={createOpen} onClose={() => setCreateOpen(false)} maxWidth="xs" fullWidth>
            <DialogTitle>Create Group</DialogTitle>
            <DialogContent>
              <TextField
                label="Group name (optional)"
                fullWidth
                value={groupName}
                onChange={(e) => setGroupName(e.target.value)}
                sx={{ mt: 1 }}
              />
            </DialogContent>
            <DialogActions>
              <Button onClick={() => setCreateOpen(false)}>Cancel</Button>
              <Button
                variant="contained"
                onClick={() => createMut.mutate({ solo: false })}
                disabled={createMut.isPending}
              >
                Create
              </Button>
            </DialogActions>
          </Dialog>
        </Box>
      ) : (
        <Box>
          <Box display="flex" justifyContent="space-between" alignItems="center" mb={2} flexWrap="wrap" gap={1}>
            <Stack direction="row" spacing={1} alignItems="center">
              <Typography variant="h6" fontWeight={700}>{group.name}</Typography>
              <Chip label={group.status} size="small" color="primary" variant="outlined" />
              {group.solo && <Chip label="SOLO" size="small" />}
            </Stack>
            <Stack direction="row" spacing={1}>
              <Button variant="contained" size="small" onClick={() => navigate('/student/preferences')}>
                Room Preferences →
              </Button>
              {isLeader && canModify && (
                <Button color="error" size="small" variant="outlined" onClick={() => setDisbandOpen(true)}>
                  Disband Group
                </Button>
              )}
              {!isLeader && canModify && (
                <Button
                  color="error"
                  size="small"
                  variant="outlined"
                  onClick={() => removeMut.mutate({ groupId: group._id, userId: user.id })}
                >
                  Leave Group
                </Button>
              )}
            </Stack>
          </Box>

          <Card elevation={2} sx={{ mb: 3 }}>
            <CardContent>
              <Typography variant="h6" mb={2}>
                Members ({group.members?.filter((m) => m.status === 'ACCEPTED').length ?? 0} accepted)
              </Typography>
              <List disablePadding>
                {(group.members || []).map((m, i) => (
                  <React.Fragment key={m.user_id || i}>
                    <ListItem
                      disableGutters
                      secondaryAction={
                        isLeader && canModify && m.role !== 'LEADER' ? (
                          <IconButton
                            size="small"
                            color="error"
                            onClick={() => removeMut.mutate({ groupId: group._id, userId: m.user_id })}
                            aria-label="Remove member"
                          >
                            <PersonRemoveIcon fontSize="small" />
                          </IconButton>
                        ) : null
                      }
                    >
                      <ListItemText
                        primary={`${m.name || m.email || m.user_id} ${m.roll_no ? `(${m.roll_no})` : ''}`}
                        secondary={`${m.email || ''} · Credits: ${m.credits ?? 3}${m.accessibility_verified ? ' · Accessibility Verified' : ''}`}
                      />
                      <Stack direction="row" spacing={1} mr={isLeader && m.role !== 'LEADER' ? 5 : 0}>
                        <Chip
                          label={m.status}
                          color={MEMBER_COLOR[m.status] || 'default'}
                          size="small"
                          variant="outlined"
                        />
                        <Chip label={m.role === 'LEADER' ? 'Leader' : 'Member'} size="small" />
                      </Stack>
                    </ListItem>
                    {i < group.members.length - 1 && <Divider />}
                  </React.Fragment>
                ))}
              </List>
            </CardContent>
          </Card>

          {isLeader && canModify && !group.solo && (
            <Card elevation={2}>
              <CardContent>
                <Typography variant="h6" mb={2}>Invite a Roommate (max group size 4)</Typography>
                {inviteError && <Alert severity="error" sx={{ mb: 2 }}>{inviteError}</Alert>}
                <Box display="flex" gap={2}>
                  <TextField
                    label="Student roll number or email"
                    size="small"
                    value={inviteIdentifier}
                    onChange={(e) => setInviteIdentifier(e.target.value)}
                    sx={{ flex: 1 }}
                  />
                  <Button
                    variant="contained"
                    onClick={() => inviteMut.mutate()}
                    disabled={inviteMut.isPending || !inviteIdentifier.trim()}
                  >
                    {inviteMut.isPending ? 'Sending…' : 'Send Invite'}
                  </Button>
                </Box>
              </CardContent>
            </Card>
          )}

          <ConfirmDialog
            open={disbandOpen}
            title="Disband Group"
            message="This will disband the group and withdraw any draft/submitted application. Continue?"
            onConfirm={() => {
              disbandMut.mutate()
              setDisbandOpen(false)
            }}
            onCancel={() => setDisbandOpen(false)}
          />
        </Box>
      )}
    </Box>
  )
}
