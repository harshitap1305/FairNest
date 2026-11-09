import React, { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Box, Typography, Button, Grid, Paper, Alert, Divider, MenuItem,
  TextField, FormControl, FormLabel, RadioGroup, FormControlLabel, Radio,
  Stack, Checkbox, Chip,
} from '@mui/material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '../../auth/AuthContext'
import { listRoomsInCycle, listFloorsInCycle } from '../../api/hostel'
import { listCycles } from '../../api/cycle'
import {
  getMyGroup, getApplication, saveApplication, submitApplication, withdrawApplication,
} from '../../api/group'
import RoomGrid from '../../components/preferences/RoomGrid'
import RankList from '../../components/preferences/RankList'
import LoadingSpinner from '../../components/common/LoadingSpinner'
import ConfirmDialog from '../../components/common/ConfirmDialog'
import { getErrorMessage } from '../../utils/errors'

export default function PreferencesPage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const qc = useQueryClient()

  const [cycleId, setCycleId] = useState('')
  const [ranked, setRanked] = useState([])
  const [fallback, setFallback] = useState('NONE')
  const [floorFilter, setFloorFilter] = useState('')
  const [onlyFitting, setOnlyFitting] = useState(true)
  const [selectedFloorAdd, setSelectedFloorAdd] = useState('')
  const [mutError, setMutError] = useState(null)
  const [infoMsg, setInfoMsg] = useState(null)
  const [withdrawOpen, setWithdrawOpen] = useState(false)
  const [hydratedForCycle, setHydratedForCycle] = useState(null)

  const { data: cycles, isLoading: cyclesLoading } = useQuery({
    queryKey: ['cycles'],
    queryFn: () => listCycles(),
  })

  useEffect(() => {
    if (!cycleId && cycles?.length) {
      const open = cycles.find((c) => c.status === 'APPLICATIONS_OPEN') || cycles[0]
      setCycleId(open._id)
    }
  }, [cycles, cycleId])

  const activeCycle = cycles?.find((c) => c._id === cycleId)

  const { data: group, isLoading: groupLoading } = useQuery({
    queryKey: ['my-group', cycleId],
    queryFn: () => getMyGroup(cycleId),
    enabled: Boolean(cycleId),
    retry: false,
  })

  const { data: rooms = [], isLoading: roomsLoading } = useQuery({
    queryKey: ['cycle-rooms', cycleId],
    queryFn: () => listRoomsInCycle(cycleId),
    enabled: Boolean(cycleId),
  })

  const { data: floors = [] } = useQuery({
    queryKey: ['cycle-floors', cycleId, activeCycle?.hostel_id],
    queryFn: () => listFloorsInCycle(cycleId, activeCycle.hostel_id),
    enabled: Boolean(cycleId && activeCycle?.hostel_id),
  })

  const { data: application, isLoading: appLoading } = useQuery({
    queryKey: ['application', group?._id, cycleId],
    queryFn: () => getApplication(group._id, cycleId),
    enabled: Boolean(group?._id && cycleId),
    retry: false,
  })

  useEffect(() => {
    if (!cycleId || hydratedForCycle === cycleId) return
    if (!application && !group?.application) {
      setRanked([])
      setFallback('NONE')
      return
    }
    const appObj = application || group?.application
    if (appObj && (rooms.length > 0 || appObj.ranked_choices?.some((c) => c.kind === 'FLOOR'))) {
      const roomMap = Object.fromEntries(rooms.map((r) => [r.room_id, r]))
      const restored = (appObj.ranked_choices || [])
        .map((ch) => {
          if (ch.kind === 'FLOOR') {
            return {
              uid: `floor:${ch.floor_no}`,
              kind: 'FLOOR',
              hostel_id: ch.hostel_id || activeCycle?.hostel_id,
              floor_no: ch.floor_no,
            }
          }
          const rm = roomMap[ch.room_id]
          return {
            uid: `room:${ch.room_id}`,
            kind: 'ROOM',
            room_id: ch.room_id,
            room_no: rm?.room_no || ch.room_id,
            floor_no: rm?.floor_no,
            capacity: rm?.capacity,
          }
        })
        .filter(Boolean)
      setRanked(restored)
      setFallback(appObj.fallback || 'NONE')
      setHydratedForCycle(cycleId)
    }
  }, [application, group, rooms, cycleId, activeCycle, hydratedForCycle])

  const groupSize = group?.size ?? group?.members?.filter((m) => m.status === 'ACCEPTED').length ?? 1
  const fillRule = activeCycle?.policy?.fill_rule || 'EXACT'

  const filteredRooms = useMemo(() => {
    return rooms.filter((r) => {
      if (floorFilter !== '' && String(r.floor_no) !== String(floorFilter)) return false
      if (onlyFitting) {
        const cap = Number(r.capacity)
        if (fillRule === 'EXACT' ? cap !== groupSize : cap < groupSize) return false
      }
      return true
    })
  }, [rooms, floorFilter, onlyFitting, fillRule, groupSize])

  const payloadChoices = useMemo(
    () =>
      ranked.map((item) =>
        item.kind === 'FLOOR'
          ? { kind: 'FLOOR', hostel_id: item.hostel_id || activeCycle?.hostel_id, floor_no: Number(item.floor_no) }
          : { kind: 'ROOM', room_id: item.room_id }
      ),
    [ranked, activeCycle]
  )

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['application', group?._id, cycleId] })
    qc.invalidateQueries({ queryKey: ['my-group', cycleId] })
  }

  const saveMut = useMutation({
    mutationFn: () =>
      saveApplication(group._id, {
        cycle_id: cycleId,
        ranked_choices: payloadChoices,
        fallback,
        version: (application || group?.application)?.version,
      }),
    onSuccess: () => {
      setMutError(null)
      setInfoMsg('Draft saved.')
      invalidate()
    },
    onError: (e) => setMutError(getErrorMessage(e)),
  })

  const submitMut = useMutation({
    mutationFn: () =>
      submitApplication(group._id, {
        cycle_id: cycleId,
        ranked_choices: payloadChoices,
        fallback,
      }),
    onSuccess: () => {
      setMutError(null)
      setInfoMsg('Application submitted!')
      invalidate()
    },
    onError: (e) => setMutError(getErrorMessage(e)),
  })

  const withdrawMut = useMutation({
    mutationFn: () => withdrawApplication(group._id, cycleId),
    onSuccess: () => {
      setMutError(null)
      setInfoMsg('Application withdrawn.')
      invalidate()
    },
    onError: (e) => setMutError(getErrorMessage(e)),
  })

  const toggleRoom = (room) => {
    const rid = room.room_id
    const uid = `room:${rid}`
    const exists = ranked.find((item) => item.uid === uid)
    if (exists) {
      setRanked(ranked.filter((item) => item.uid !== uid))
      return
    }
    if (ranked.length >= 10) {
      setMutError('Maximum 10 ranked choices allowed.')
      return
    }
    setMutError(null)
    setRanked([
      ...ranked,
      {
        uid,
        kind: 'ROOM',
        room_id: rid,
        room_no: room.room_no,
        floor_no: room.floor_no,
        capacity: room.capacity,
      },
    ])
  }

  const addFloorChoice = () => {
    if (selectedFloorAdd === '') return
    const fno = Number(selectedFloorAdd)
    const uid = `floor:${fno}`
    if (ranked.some((r) => r.uid === uid)) {
      setMutError(`Floor ${fno} is already in your ranked preferences.`)
      return
    }
    if (ranked.length >= 10) {
      setMutError('Maximum 10 ranked choices allowed.')
      return
    }
    setMutError(null)
    setRanked([
      ...ranked,
      {
        uid,
        kind: 'FLOOR',
        hostel_id: activeCycle?.hostel_id,
        floor_no: fno,
      },
    ])
    setSelectedFloorAdd('')
  }

  if (cyclesLoading || (cycleId && (groupLoading || roomsLoading || appLoading))) {
    return <LoadingSpinner />
  }

  if (!activeCycle) {
    return (
      <Box sx={{ p: 3 }}>
        <Typography variant="h4" fontWeight={700} mb={2}>Preferences</Typography>
        <Alert severity="info">No allotment cycles found.</Alert>
      </Box>
    )
  }

  const appObj = application || group?.application
  const isSubmitted = appObj?.status === 'SUBMITTED'
  const isCycleOpen = activeCycle.status === 'APPLICATIONS_OPEN'
  const isLeader = group && String(group.leader_id) === String(user?.id)
  const canEdit = Boolean(isCycleOpen && group && isLeader && !['LOCKED', 'DISBANDED'].includes(group.status))
  const selectedRoomIds = ranked.filter((r) => r.kind === 'ROOM').map((r) => r.room_id)

  return (
    <Box sx={{ p: 3 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={2} mb={2}>
        <Box>
          <Typography variant="h4" fontWeight={700}>Room Preferences</Typography>
          <Typography color="text.secondary">
            Group size: <strong>{groupSize}</strong> · Fill rule: <strong>{fillRule}</strong> · Max 10 choices
          </Typography>
        </Box>
        <TextField
          select
          label="Cycle"
          size="small"
          value={cycleId}
          onChange={(e) => {
            setCycleId(e.target.value)
            setHydratedForCycle(null)
            setRanked([])
          }}
          sx={{ minWidth: 260 }}
        >
          {cycles.map((c) => (
            <MenuItem key={c._id} value={c._id}>
              {c.name} ({c.status.replace(/_/g, ' ')})
            </MenuItem>
          ))}
        </TextField>
      </Box>

      {!group && (
        <Alert
          severity="warning"
          sx={{ mb: 2 }}
          action={
            <Button color="inherit" size="small" onClick={() => navigate('/student/group')}>
              Go to My Group
            </Button>
          }
        >
          Create a group or apply solo before selecting room preferences.
        </Alert>
      )}

      {group && !isLeader && (
        <Alert severity="info" sx={{ mb: 2 }}>
          Only the group leader can save or submit room preferences.
        </Alert>
      )}

      {!isCycleOpen && (
        <Alert severity="info" sx={{ mb: 2 }}>
          Application window is <strong>{activeCycle.status.replace(/_/g, ' ')}</strong> (read-only).
        </Alert>
      )}

      {mutError && <Alert severity="error" sx={{ mb: 2 }}>{mutError}</Alert>}
      {infoMsg && <Alert severity="success" sx={{ mb: 2 }}>{infoMsg}</Alert>}
      {isSubmitted && (
        <Alert severity="success" sx={{ mb: 2 }}>
          Application submitted! You can adjust choices or withdraw while the window remains open.
        </Alert>
      )}

      <Grid container spacing={3}>
        <Grid item xs={12} md={7}>
          <Paper elevation={2} sx={{ p: 2 }}>
            <Box display="flex" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={1} mb={2}>
              <Typography variant="h6">Rooms in Cycle</Typography>
              <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap">
                <TextField
                  select
                  label="Floor"
                  size="small"
                  value={floorFilter}
                  onChange={(e) => setFloorFilter(e.target.value)}
                  sx={{ minWidth: 120 }}
                >
                  <MenuItem value="">All Floors</MenuItem>
                  {floors.map((f) => (
                    <MenuItem key={f._id} value={String(f.floor_no)}>
                      {f.label || `Floor ${f.floor_no}`}
                    </MenuItem>
                  ))}
                </TextField>
                <FormControlLabel
                  control={
                    <Checkbox
                      size="small"
                      checked={onlyFitting}
                      onChange={(e) => setOnlyFitting(e.target.checked)}
                    />
                  }
                  label={<Typography variant="body2">Size matches group ({groupSize})</Typography>}
                />
              </Stack>
            </Box>

            <RoomGrid
              rooms={filteredRooms}
              selected={selectedRoomIds}
              groupSize={groupSize}
              fillRule={fillRule}
              onToggle={(room) => {
                if (!canEdit) return
                toggleRoom(room)
              }}
            />
          </Paper>
        </Grid>

        <Grid item xs={12} md={5}>
          <Paper elevation={2} sx={{ p: 2, minHeight: 420 }}>
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
              <Typography variant="h6">Ranked Preferences ({ranked.length}/10)</Typography>
              {appObj?.status && <Chip label={appObj.status} size="small" color={isSubmitted ? 'success' : 'default'} />}
            </Box>

            {canEdit && floors.length > 0 && (
              <Box display="flex" gap={1} mb={2}>
                <TextField
                  select
                  label="Add floor preference"
                  size="small"
                  value={selectedFloorAdd}
                  onChange={(e) => setSelectedFloorAdd(e.target.value)}
                  sx={{ flex: 1 }}
                >
                  {floors.map((f) => (
                    <MenuItem key={f._id} value={String(f.floor_no)}>
                      {f.label || `Floor ${f.floor_no}`} ({f.available_rooms ?? 0} avail)
                    </MenuItem>
                  ))}
                </TextField>
                <Button variant="outlined" onClick={addFloorChoice} disabled={selectedFloorAdd === ''}>
                  Add Floor
                </Button>
              </Box>
            )}

            <RankList items={ranked} onChange={(next) => canEdit && setRanked(next)} />

            <Divider sx={{ my: 2 }} />

            <FormControl component="fieldset" disabled={!canEdit} sx={{ mb: 2 }}>
              <FormLabel component="legend">If none of your ranked choices are available</FormLabel>
              <RadioGroup value={fallback} onChange={(e) => setFallback(e.target.value)}>
                <FormControlLabel
                  value="NONE"
                  control={<Radio size="small" />}
                  label="Leave unallotted / waitlist (+2 credits on settlement)"
                />
                <FormControlLabel
                  value="ANY_ELIGIBLE"
                  control={<Radio size="small" />}
                  label="Auto-assign any eligible available room (fallback)"
                />
              </RadioGroup>
            </FormControl>

            {canEdit && (
              <Box display="flex" gap={1.5} flexWrap="wrap">
                <Button
                  variant="outlined"
                  onClick={() => saveMut.mutate()}
                  disabled={saveMut.isPending}
                >
                  {saveMut.isPending ? 'Saving…' : 'Save Draft'}
                </Button>
                <Button
                  variant="contained"
                  onClick={() => submitMut.mutate()}
                  disabled={submitMut.isPending || ranked.length === 0}
                >
                  {submitMut.isPending ? 'Submitting…' : isSubmitted ? 'Re-submit' : 'Submit Application'}
                </Button>
                {isSubmitted && (
                  <Button color="error" variant="text" onClick={() => setWithdrawOpen(true)}>
                    Withdraw
                  </Button>
                )}
              </Box>
            )}
          </Paper>
        </Grid>
      </Grid>

      <ConfirmDialog
        open={withdrawOpen}
        title="Withdraw Application"
        message="Are you sure you want to withdraw your application? You can re-submit while the window is open."
        onConfirm={() => {
          withdrawMut.mutate()
          setWithdrawOpen(false)
        }}
        onCancel={() => setWithdrawOpen(false)}
      />
    </Box>
  )
}
