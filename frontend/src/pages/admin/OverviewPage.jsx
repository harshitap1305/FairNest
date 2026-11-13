import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Box, Typography, Grid, Card, CardContent, Chip, Table, TableHead, TableRow, TableCell,
  TableBody, LinearProgress, Button, Alert, Paper, Stack, Tooltip, IconButton,
} from '@mui/material'
import RefreshIcon from '@mui/icons-material/Refresh'
import FileDownloadIcon from '@mui/icons-material/FileDownload'
import WarningAmberIcon from '@mui/icons-material/WarningAmber'
import EventBusyIcon from '@mui/icons-material/EventBusy'
import { useQuery } from '@tanstack/react-query'
import { getOperationsOverview, downloadAllotmentRoster } from '../../api/exports'
import LoadingSpinner from '../../components/common/LoadingSpinner'
import ErrorAlert from '../../components/common/ErrorAlert'
import { formatDatetime, timeAgo, timeUntil } from '../../utils/dates'

const STATUS_COLOR = {
  DRAFT: 'default',
  SCHEDULED: 'info',
  APPLICATIONS_OPEN: 'primary',
  APPLICATIONS_CLOSED: 'secondary',
  ALLOCATING: 'warning',
  ALLOTMENT_ACTIVE: 'success',
  CLOSED: 'default',
}

function Kpi({ label, value, hint, color = 'text.primary' }) {
  return (
    <Grid item xs={6} md={2}>
      <Card sx={{ height: '100%' }}>
        <CardContent>
          <Typography variant="overline" color="text.secondary">{label}</Typography>
          <Typography variant="h4" fontWeight={700} color={color}>{value}</Typography>
          {hint && <Typography variant="caption" color="text.secondary">{hint}</Typography>}
        </CardContent>
      </Card>
    </Grid>
  )
}

export default function OverviewPage() {
  const navigate = useNavigate()
  const [exportError, setExportError] = useState(null)
  const [downloading, setDownloading] = useState(null)
  const { data, isLoading, error, refetch, isFetching, dataUpdatedAt } = useQuery({
    queryKey: ['operations-overview'],
    queryFn: getOperationsOverview,
    refetchInterval: 30_000,
  })

  const exportRoster = async (cycleId) => {
    setDownloading(cycleId)
    setExportError(null)
    try {
      await downloadAllotmentRoster(cycleId)
    } catch (e) {
      setExportError(e)
    } finally {
      setDownloading(null)
    }
  }

  if (isLoading) return <LoadingSpinner />

  const t = data?.totals ?? {}
  const holds = data?.attention?.expiring_holds ?? []
  const closing = data?.attention?.closing_soon ?? []

  return (
    <Box sx={{ p: 3 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={2} mb={3}>
        <Box>
          <Typography variant="h4" fontWeight={700}>Operations overview</Typography>
          <Typography variant="body2" color="text.secondary">
            Live snapshot of every cycle you manage · updated {dataUpdatedAt ? timeAgo(new Date(dataUpdatedAt).toISOString()) : '—'}
          </Typography>
        </Box>
        <Tooltip title="Refresh now">
          <span>
            <IconButton onClick={() => refetch()} disabled={isFetching}><RefreshIcon /></IconButton>
          </span>
        </Tooltip>
      </Box>

      <ErrorAlert error={error || exportError} />

      <Grid container spacing={2} mb={3}>
        <Kpi label="Active cycles" value={data?.cycles?.length ?? 0} />
        <Kpi label="Applications" value={t.applications ?? 0} />
        <Kpi label="Rooms on hold" value={t.held ?? 0} color="warning.main" />
        <Kpi label="Confirmed" value={t.confirmed ?? 0} color="success.main" />
        <Kpi label="Waitlisted" value={t.waitlisted ?? 0} />
        <Kpi label="Free rooms" value={t.rooms_free ?? 0} hint={`of ${t.rooms ?? 0} in live cycles`} />
      </Grid>

      {(holds.length > 0 || closing.length > 0) && (
        <Paper elevation={2} sx={{ p: 2, mb: 3, borderLeft: '4px solid', borderColor: 'warning.main' }}>
          <Typography variant="h6" mb={1}>Needs attention</Typography>
          <Stack spacing={1}>
            {holds.map((h) => (
              <Alert
                key={h.allotment_id}
                severity="warning"
                icon={<WarningAmberIcon />}
                action={<Button size="small" onClick={() => navigate('/warden/allotments')}>Open monitor</Button>}
              >
                Room <strong>{h.room_no || '—'}</strong> ({h.cycle_name}) expires in{' '}
                <strong>{timeUntil(h.expires_at)}</strong> with {h.pending_members}/{h.member_count} member(s) yet to accept.
              </Alert>
            ))}
            {closing.map((c) => (
              <Alert key={c.cycle_id} severity="info" icon={<EventBusyIcon />}>
                Applications for <strong>{c.name}</strong> close {formatDatetime(c.apply_close_at)} ({timeUntil(c.apply_close_at)} left).
              </Alert>
            ))}
          </Stack>
        </Paper>
      )}

      <Paper elevation={2}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Cycle</TableCell>
              <TableCell>Hostel</TableCell>
              <TableCell>Status</TableCell>
              <TableCell align="right">Applications</TableCell>
              <TableCell align="right">Held</TableCell>
              <TableCell align="right">Waitlisted</TableCell>
              <TableCell sx={{ minWidth: 180 }}>Rooms confirmed</TableCell>
              <TableCell align="right" />
            </TableRow>
          </TableHead>
          <TableBody>
            {(data?.cycles ?? []).map((c) => (
              <TableRow key={c.cycle_id} hover>
                <TableCell>
                  <Button size="small" onClick={() => navigate(`/admin/cycles/${c.cycle_id}`)} sx={{ fontWeight: 600 }}>
                    {c.name}
                  </Button>
                </TableCell>
                <TableCell>{c.hostel_name || '—'}</TableCell>
                <TableCell>
                  <Chip size="small" label={c.status.replace(/_/g, ' ')} color={STATUS_COLOR[c.status] ?? 'default'} />
                  {c.expiring_soon > 0 && <Chip size="small" color="warning" label={`${c.expiring_soon} expiring`} sx={{ ml: 0.5 }} />}
                </TableCell>
                <TableCell align="right">{c.applications}</TableCell>
                <TableCell align="right">{c.held}</TableCell>
                <TableCell align="right">{c.waitlisted}</TableCell>
                <TableCell>
                  <Box display="flex" alignItems="center" gap={1}>
                    <LinearProgress
                      variant="determinate"
                      value={(c.fill_rate ?? 0) * 100}
                      color="success"
                      sx={{ flexGrow: 1, height: 8, borderRadius: 4 }}
                    />
                    <Typography variant="caption" minWidth={52}>{c.confirmed}/{c.rooms_total}</Typography>
                  </Box>
                </TableCell>
                <TableCell align="right">
                  <Tooltip title="Download allotment roster (CSV)">
                    <span>
                      <IconButton
                        size="small"
                        onClick={() => exportRoster(c.cycle_id)}
                        disabled={downloading === c.cycle_id || c.held + c.confirmed === 0}
                      >
                        <FileDownloadIcon fontSize="small" />
                      </IconButton>
                    </span>
                  </Tooltip>
                </TableCell>
              </TableRow>
            ))}
            {!data?.cycles?.length && (
              <TableRow>
                <TableCell colSpan={8}>
                  <Typography color="text.secondary" py={2} textAlign="center">No active cycles in your hostels.</Typography>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Paper>
    </Box>
  )
}
