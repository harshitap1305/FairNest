import React from 'react'
import {
  Box, Typography, List, ListItem, ListItemText,
  Chip, Divider, Button, Paper,
} from '@mui/material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getNotifications, markNotificationRead } from '../../api/auth'
import LoadingSpinner from '../../components/common/LoadingSpinner'
import { formatDatetime } from '../../utils/dates'

export default function NotificationsPage() {
  const qc = useQueryClient()
  const { data: notifs, isLoading } = useQuery({
    queryKey: ['notifications'],
    queryFn: () => getNotifications({ limit: 50 }),
  })

  const markRead = useMutation({
    mutationFn: (id) => markNotificationRead(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['notifications'] })
      qc.invalidateQueries({ queryKey: ['notifications', 'unread-count'] })
    },
  })

  if (isLoading) return <LoadingSpinner />

  const sorted = [...(notifs || [])].sort(
    (a, b) => new Date(b.created_at) - new Date(a.created_at)
  )

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" fontWeight={700} mb={3}>Notifications</Typography>

      {sorted.length === 0 ? (
        <Typography color="text.secondary">No notifications yet.</Typography>
      ) : (
        <Paper elevation={1}>
          <List disablePadding>
            {sorted.map((n, i) => (
              <React.Fragment key={n._id || i}>
                <ListItem
                  alignItems="flex-start"
                  sx={{ bgcolor: n.read ? 'transparent' : 'action.hover' }}
                  secondaryAction={
                    !n.read && (
                      <Button size="small" onClick={() => markRead.mutate(n._id)}>
                        Mark read
                      </Button>
                    )
                  }
                >
                  <ListItemText
                    primary={
                      <Box display="flex" alignItems="center" gap={1}>
                        <Typography fontWeight={n.read ? 400 : 700}>
                          {n.title || n.body}
                        </Typography>
                        {!n.read && <Chip label="New" color="primary" size="small" />}
                      </Box>
                    }
                    secondary={
                      <>
                        {n.body && (
                          <Typography variant="body2" color="text.secondary" component="span" display="block">
                            {n.body}
                          </Typography>
                        )}
                        <Typography variant="caption" color="text.secondary">
                          {formatDatetime(n.created_at)}
                        </Typography>
                      </>
                    }
                  />
                </ListItem>
                {i < sorted.length - 1 && <Divider />}
              </React.Fragment>
            ))}
          </List>
        </Paper>
      )}
    </Box>
  )
}
