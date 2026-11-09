import React from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Box, Grid, Card, CardContent, Typography, Chip, List,
  ListItem, ListItemText, Divider, Button, Stack,
} from '@mui/material'
import { useQuery } from '@tanstack/react-query'
import { useAuth } from '../../auth/AuthContext'
import { getMe, getNotifications } from '../../api/auth'
import { listCycles } from '../../api/cycle'
import { getMyAllotment } from '../../api/allotment'
import { getMyGroup, getMyInvites } from '../../api/group'
import { formatDatetime, timeUntil } from '../../utils/dates'

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

const ALLOTMENT_COLORS = {
  HELD: 'warning',
  CONFIRMED: 'success',
  CANCELLED: 'error',
  DECLINED: 'error',
  EXPIRED: 'default',
  REVOKED: 'error',
}

export default function Dashboard() {
  const { user } = useAuth()
  const navigate = useNavigate()

  const { data: cycles } = useQuery({
    queryKey: ['cycles'],
    queryFn: () => listCycles(),
    staleTime: 30000,
  })

  const activeCycle =
    cycles?.find((c) =>
      ['APPLICATIONS_OPEN', 'ALLOTMENT_ACTIVE', 'APPLICATIONS_CLOSED', 'ALLOCATING', 'SCHEDULED'].includes(
        c.status
      )
    ) || cycles?.[0]

  const { data: group } = useQuery({
    queryKey: ['my-group', activeCycle?._id],
    queryFn: () => getMyGroup(activeCycle._id),
    enabled: Boolean(activeCycle?._id),
    retry: false,
  })

  const { data: invites } = useQuery({
    queryKey: ['my-invites', activeCycle?._id],
    queryFn: () => getMyInvites(activeCycle._id),
    enabled: Boolean(activeCycle?._id),
    retry: false,
  })

  const { data: allotment } = useQuery({
    queryKey: ['my-allotment'],
    queryFn: () => getMyAllotment(),
    retry: false,
  })

  const { data: notifs } = useQuery({
    queryKey: ['notifications'],
    queryFn: () => getNotifications({ limit: 10 }),
    staleTime: 15000,
  })

  const { data: me } = useQuery({ queryKey: ['me'], queryFn: getMe })

  const credits = me?.credits ?? user?.credits ?? '—'
  const unreadNotifs = (notifs || []).filter((n) => !n.read).slice(0, 5)
  const holdDeadline = allotment?.expires_at ?? allotment?.hold_deadline

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" fontWeight={700} mb={3}>
        Welcome back, {(user?.name || 'Student').split(' ')[0]}
      </Typography>

      <Grid container spacing={3}>
        <Grid item xs={12} md={6} lg={3}>
          <Card elevation={2} sx={{ height: '100%' }}>
            <CardContent>
              <Typography variant="overline" color="text.secondary">Current Cycle</Typography>
              {activeCycle ? (
                <>
                  <Typography variant="h6" fontWeight={700} mt={1}>{activeCycle.name}</Typography>
                  <Chip
                    label={activeCycle.status.replace(/_/g, ' ')}
                    color={STATUS_COLORS[activeCycle.status] || 'default'}
                    size="small"
                    sx={{ mt: 1 }}
                  />
                  {activeCycle.apply_close_at && (
                    <Typography variant="body2" color="text.secondary" mt={1}>
                      Window closes: {formatDatetime(activeCycle.apply_close_at)}
                    </Typography>
                  )}
                </>
              ) : (
                <Typography mt={1} color="text.secondary">No active cycle</Typography>
              )}
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={6} lg={3}>
          <Card elevation={2} sx={{ height: '100%' }}>
            <CardContent>
              <Typography variant="overline" color="text.secondary">My Group</Typography>
              {group ? (
                <>
                  <Typography variant="h6" fontWeight={700} mt={1}>{group.name || 'My Group'}</Typography>
                  <Typography variant="body2" color="text.secondary">
                    {group.size ?? group.members?.length ?? 0} member{(group.size ?? group.members?.length) !== 1 ? 's' : ''} · {group.status}
                  </Typography>
                  <Button size="small" sx={{ mt: 1, px: 0 }} onClick={() => navigate('/student/preferences')}>
                    {group.application?.status === 'SUBMITTED' ? 'View Preferences →' : 'Rank Preferences →'}
                  </Button>
                </>
              ) : (
                <>
                  <Typography mt={1} color="text.secondary">
                    {invites?.length > 0 ? `${invites.length} pending invite(s)` : 'Not in a group yet'}
                  </Typography>
                  <Button size="small" sx={{ mt: 1, px: 0 }} onClick={() => navigate('/student/group')}>
                    Form Group / Apply Solo →
                  </Button>
                </>
              )}
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={6} lg={3}>
          <Card elevation={2} sx={{ height: '100%' }}>
            <CardContent>
              <Typography variant="overline" color="text.secondary">My Allotment</Typography>
              {allotment ? (
                <>
                  <Box mt={1} mb={1}>
                    <Chip
                      label={allotment.status}
                      color={ALLOTMENT_COLORS[allotment.status] || 'default'}
                      size="small"
                    />
                  </Box>
                  <Typography variant="body1" fontWeight={600}>
                    Room {allotment.room?.room_no || allotment.room_no || allotment.room_id}
                  </Typography>
                  {allotment.status === 'HELD' && holdDeadline && (
                    <Typography variant="body2" color="warning.main">
                      Accept within {timeUntil(holdDeadline)}
                    </Typography>
                  )}
                  <Button size="small" sx={{ mt: 0.5, px: 0 }} onClick={() => navigate('/student/allotment')}>
                    Open Allotment →
                  </Button>
                </>
              ) : (
                <Typography mt={1} color="text.secondary">No allotment yet</Typography>
              )}
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={6} lg={3}>
          <Card elevation={2} sx={{ height: '100%' }}>
            <CardContent>
              <Typography variant="overline" color="text.secondary">Fairness Credits</Typography>
              <Typography variant="h4" fontWeight={700} mt={1} color="primary.main">
                {credits}
              </Typography>
              <Stack direction="row" spacing={1} mt={1}>
                <Button size="small" sx={{ px: 0 }} onClick={() => navigate('/student/credits')}>
                  Ledger →
                </Button>
                <Button size="small" sx={{ px: 0 }} onClick={() => navigate('/student/fairness')}>
                  How it works →
                </Button>
              </Stack>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={6}>
          <Card elevation={2}>
            <CardContent>
              <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                <Typography variant="h6" fontWeight={600}>Unread Notifications</Typography>
                <Button size="small" onClick={() => navigate('/notifications')}>View All</Button>
              </Box>
              {unreadNotifs.length === 0 ? (
                <Typography color="text.secondary">No unread notifications</Typography>
              ) : (
                <List dense disablePadding>
                  {unreadNotifs.map((n, i) => (
                    <React.Fragment key={n._id || i}>
                      <ListItem disableGutters>
                        <ListItemText
                          primary={n.title || n.body}
                          secondary={`${n.body ? `${n.body} · ` : ''}${formatDatetime(n.created_at)}`}
                          primaryTypographyProps={{ fontWeight: 600 }}
                        />
                      </ListItem>
                      {i < unreadNotifs.length - 1 && <Divider />}
                    </React.Fragment>
                  ))}
                </List>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  )
}
