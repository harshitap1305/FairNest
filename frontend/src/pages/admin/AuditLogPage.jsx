import React, { useState } from 'react'
import {
  Box, Typography, Paper, Table, TableBody, TableCell, TableContainer,
  TableHead, TableRow, TextField, Collapse, IconButton, Chip, Button,
} from '@mui/material'
import FileDownloadIcon from '@mui/icons-material/FileDownload'
import { downloadAuditLogs } from '../../api/exports'
import KeyboardArrowDownIcon from '@mui/icons-material/KeyboardArrowDown'
import KeyboardArrowUpIcon from '@mui/icons-material/KeyboardArrowUp'
import { useQuery } from '@tanstack/react-query'
import { listAuditLogs } from '../../api/admin'
import LoadingSpinner from '../../components/common/LoadingSpinner'
import ErrorAlert from '../../components/common/ErrorAlert'
import { formatDatetime } from '../../utils/dates'

function AuditRow({ entry }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <TableRow hover>
        <TableCell>
          <IconButton size="small" onClick={() => setOpen(!open)}>
            {open ? <KeyboardArrowUpIcon /> : <KeyboardArrowDownIcon />}
          </IconButton>
        </TableCell>
        <TableCell>{formatDatetime(entry.ts || entry.created_at)}</TableCell>
        <TableCell>{entry.actor_email || entry.actor_id || '—'}</TableCell>
        <TableCell>
          <Chip label={entry.action} color="primary" variant="outlined" size="small" />
        </TableCell>
        <TableCell>{entry.target_type || entry.entity_type || '—'}</TableCell>
        <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.75rem' }}>
          {String(entry.target_id || entry.entity_id || '').slice(-8)}
        </TableCell>
      </TableRow>
      <TableRow>
        <TableCell colSpan={6} sx={{ p: 0, border: 0 }}>
          <Collapse in={open}>
            <Box sx={{ p: 2, bgcolor: 'action.hover' }}>
              <pre style={{ margin: 0, fontSize: '0.75rem', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                {JSON.stringify(
                  { role: entry.role, before: entry.before, after: entry.after, ip: entry.ip },
                  null,
                  2
                )}
              </pre>
            </Box>
          </Collapse>
        </TableCell>
      </TableRow>
    </>
  )
}

export default function AuditLogPage() {
  const [action, setAction] = useState('')
  const [targetType, setTargetType] = useState('')
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState(null)

  const exportCsv = async () => {
    setExporting(true)
    setExportError(null)
    try {
      await downloadAuditLogs({
        action: action.trim() || undefined,
        target_type: targetType.trim() || undefined,
      })
    } catch (e) {
      setExportError(e)
    } finally {
      setExporting(false)
    }
  }

  const { data: logs, isLoading, error } = useQuery({
    queryKey: ['audit-logs', action, targetType],
    queryFn: () =>
      listAuditLogs({
        action: action.trim() || undefined,
        target_type: targetType.trim() || undefined,
        limit: 100,
      }),
    staleTime: 10000,
  })

  return (
    <Box sx={{ p: 3 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={2} mb={3}>
        <Typography variant="h4" fontWeight={700}>Audit Log</Typography>
        <Button variant="outlined" startIcon={<FileDownloadIcon />} onClick={exportCsv} disabled={exporting}>
          {exporting ? 'Exporting…' : 'Export CSV'}
        </Button>
      </Box>

      {error && <ErrorAlert error={error} />}
      <ErrorAlert error={exportError} />

      <Box display="flex" gap={2} mb={3} flexWrap="wrap">
        <TextField
          label="Filter by Action (e.g. RUN_ALLOCATION)"
          value={action}
          onChange={(e) => setAction(e.target.value)}
          size="small"
          sx={{ minWidth: 240 }}
        />
        <TextField
          label="Filter by Target Type (e.g. cycle, allotment)"
          value={targetType}
          onChange={(e) => setTargetType(e.target.value)}
          size="small"
          sx={{ minWidth: 240 }}
        />
      </Box>

      {isLoading ? (
        <LoadingSpinner />
      ) : (
        <TableContainer component={Paper} elevation={2}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell width={48} />
                <TableCell><strong>Time</strong></TableCell>
                <TableCell><strong>Actor</strong></TableCell>
                <TableCell><strong>Action</strong></TableCell>
                <TableCell><strong>Target Type</strong></TableCell>
                <TableCell><strong>Target ID</strong></TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(logs || []).map((entry, i) => <AuditRow key={entry._id || i} entry={entry} />)}
              {logs?.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} align="center" sx={{ color: 'text.secondary' }}>
                    No audit logs
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Box>
  )
}
