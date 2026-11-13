import React, { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Box, Typography, List, ListItemButton, ListItemText, ListItemIcon,
  Chip, Divider, Button, Paper, Tabs, Tab, Stack, Tooltip, IconButton,
} from '@mui/material'
import DoneAllIcon from '@mui/icons-material/DoneAll'
import CircleIcon from '@mui/icons-material/Circle'
import MarkEmailReadIcon from '@mui/icons-material/MarkEmailRead'
import NotificationsNoneIcon from '@mui/icons-material/NotificationsNone'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getNotifications, getNotificationSummary, markNotificationRead, markAllNotificationsRead,
} from '../../api/auth'
import { useAuth } from '../../auth/AuthContext'
import LoadingSpinner from '../../components/common/LoadingSpinner'
import ErrorAlert from '../../components/common/ErrorAlert'
import { formatDatetime, timeAgo } from '../../utils/dates'
import { notificationMeta } from '../../utils/notifications'

export default function NotificationsPage() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const { role } = useAuth()
  const [tab, setTab] = useState('all')
  const [typeFilter, setTypeFilter] = useState(null)

  const params = { limit: 100 }
  if (tab === 'unread') params.unread_only = true
  if (typeFilter) params.type = typeFilter

  const { data: notifs, isLoading, error } = useQuery({
    queryKey: ['notifications', 'list', tab, typeFilter],
    queryFn: () => getNotifications(params),
  })
  const { data: summary } = useQuery({
    queryKey: ['notifications', 'summary'],
    queryFn: getNotificationSummary,
  })

  const refresh = () => qc.invalidateQueries({ queryKey: ['notifications'] })
  const markRead = useMutation({ mutationFn: markNotificationRead, onSuccess: refresh })
  const markAll = useMutation({ mutationFn: markAllNotificationsRead, onSuccess: refresh })

  const sorted = useMemo(
    () => [...(notifs || [])].sort((a, b) => new Date(b.created_at) - new Date(a.created_at)),
    [notifs]
  )
  const unreadTotal = summary?.unread_count ?? 0
  const typeCounts = Object.entries(summary?.unread_by_type ?? {}).sort((a, b) => b[1] - a[1])

  const openNotification = (n) => {
    if (!n.read) markRead.mutate(n._id)
    const path = role === 'STUDENT' ? notificationMeta(n.type).studentPath : null
    if (path) navigate(path)
  }

  return (
    <Box sx={{ p: 3, maxWidth: 960 }}>
      <Box display="flex" alignItems="center" justifyContent="space-between" flexWrap="wrap" gap={2} mb={2}>
        <Box>
          <Typography variant="h4" fontWeight={700}>Notifications</Typography>
          <Typography variant="body2" color="text.secondary">
            {unreadTotal > 0 ? `${unreadTotal} unread` : 'You are all caught up'}
          </Typography>
        </Box>
        <Button
          variant="outlined"
          startIcon={<DoneAllIcon />}
          disabled={unreadTotal === 0 || markAll.isPending}
          onClick={() => markAll.mutate()}
        >
          Mark all as read
        </Button>
      </Box>

      <ErrorAlert error={error || markAll.error} />

      <Paper elevation={1} sx={{ mb: 2 }}>
        <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ px: 1 }}>
          <Tab value="all" label="All" />
          <Tab value="unread" label={unreadTotal ? `Unread (${unreadTotal})` : 'Unread'} />
        </Tabs>
        {typeCounts.length > 0 && (
          <>
            <Divider />
            <Stack direction="row" spacing={1} sx={{ p: 1.5, flexWrap: 'wrap', rowGap: 1 }}>
              <Chip
                label="All types"
                size="small"
                variant={typeFilter ? 'outlined' : 'filled'}
                onClick={() => setTypeFilter(null)}
              />
              {typeCounts.map(([type, n]) => (
                <Chip
                  key={type}
                  size="small"
                  color={notificationMeta(type).color}
                  variant={typeFilter === type ? 'filled' : 'outlined'}
                  label={`${notificationMeta(type).label} · ${n}`}
                  onClick={() => setTypeFilter(typeFilter === type ? null : type)}
                />
              ))}
            </Stack>
          </>
        )}
      </Paper>

      {isLoading ? (
        <LoadingSpinner />
      ) : sorted.length === 0 ? (
        <Paper elevation={0} sx={{ p: 6, textAlign: 'center', bgcolor: 'transparent' }}>
          <NotificationsNoneIcon sx={{ fontSize: 48, color: 'text.disabled' }} />
          <Typography color="text.secondary" mt={1}>
            {tab === 'unread' ? 'No unread notifications.' : 'No notifications yet.'}
          </Typography>
        </Paper>
      ) : (
        <Paper elevation={1}>
          <List disablePadding>
            {sorted.map((n, i) => {
              const meta = notificationMeta(n.type)
              return (
                <React.Fragment key={n._id || i}>
                  <ListItemButton
                    alignItems="flex-start"
                    onClick={() => openNotification(n)}
                    sx={{ bgcolor: n.read ? 'transparent' : 'action.hover', pr: 7 }}
                  >
                    <ListItemIcon sx={{ minWidth: 28, mt: 1 }}>
                      {!n.read && <CircleIcon color="primary" sx={{ fontSize: 10 }} />}
                    </ListItemIcon>
                    <ListItemText
                      primary={
                        <Box display="flex" alignItems="center" gap={1} flexWrap="wrap">
                          <Typography fontWeight={n.read ? 400 : 700}>{n.title || n.body}</Typography>
                          <Chip label={meta.label} color={meta.color} size="small" variant="outlined" />
                        </Box>
                      }
                      secondary={
                        <>
                          {n.body && n.title && (
                            <Typography variant="body2" color="text.secondary" component="span" display="block">
                              {n.body}
                            </Typography>
                          )}
                          <Tooltip title={formatDatetime(n.created_at)}>
                            <Typography variant="caption" color="text.secondary" component="span">
                              {timeAgo(n.created_at)}
                            </Typography>
                          </Tooltip>
                        </>
                      }
                    />
                    {!n.read && (
                      <Tooltip title="Mark as read">
                        <IconButton
                          size="small"
                          sx={{ position: 'absolute', right: 12, top: 12 }}
                          onClick={(e) => { e.stopPropagation(); markRead.mutate(n._id) }}
                          aria-label="Mark as read"
                        >
                          <MarkEmailReadIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    )}
                  </ListItemButton>
                  {i < sorted.length - 1 && <Divider component="li" />}
                </React.Fragment>
              )
            })}
          </List>
        </Paper>
      )}
    </Box>
  )
}
