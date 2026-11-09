import React, { useState, useRef } from 'react'
import {
  Box, Typography, Button, Paper, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, TextField, Chip, Dialog,
  DialogTitle, DialogContent, DialogActions, Alert, Stack,
} from '@mui/material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listUsers, importUsers, enableUser, disableUser, unlockUser } from '../../api/admin'
import { useAuth } from '../../auth/AuthContext'
import LoadingSpinner from '../../components/common/LoadingSpinner'
import ErrorAlert from '../../components/common/ErrorAlert'
import { formatDatetime } from '../../utils/dates'
import { getErrorMessage } from '../../utils/errors'

const ROLE_COLORS = {
  STUDENT: 'default', WARDEN: 'primary', ADMIN: 'secondary',
  AUDITOR: 'info', SUPER_ADMIN: 'error',
}
const STATUS_COLORS = {
  ACTIVE: 'success', INVITED: 'warning', LOCKED: 'error', DISABLED: 'default',
}

export default function UsersPage() {
  const { user: currentUser } = useAuth()
  const qc = useQueryClient()
  const [search, setSearch] = useState('')
  const [importOpen, setImportOpen] = useState(false)
  const [importResult, setImportResult] = useState(null)
  const [importError, setImportError] = useState(null)
  const [mutError, setMutError] = useState(null)
  const fileRef = useRef()

  const { data: users, isLoading, error } = useQuery({
    queryKey: ['admin-users', search],
    queryFn: () => listUsers({ search: search || undefined, limit: 100 }),
    staleTime: 15000,
  })

  const importMut = useMutation({
    mutationFn: (file) => importUsers(file),
    onSuccess: (res) => {
      setImportResult(res)
      setImportError(null)
      qc.invalidateQueries({ queryKey: ['admin-users'] })
    },
    onError: (e) => setImportError(getErrorMessage(e)),
  })

  const statusMut = useMutation({
    mutationFn: async ({ userId, action }) => {
      if (action === 'enable') return enableUser(userId)
      if (action === 'disable') return disableUser(userId)
      if (action === 'unlock') return unlockUser(userId)
      return null
    },
    onSuccess: () => {
      setMutError(null)
      qc.invalidateQueries({ queryKey: ['admin-users'] })
    },
    onError: (e) => setMutError(getErrorMessage(e)),
  })

  const handleFileUpload = (e) => {
    const file = e.target.files?.[0]
    if (file) importMut.mutate(file)
  }

  return (
    <Box sx={{ p: 3 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h4" fontWeight={700}>Users</Typography>
        {currentUser?.role === 'SUPER_ADMIN' && (
          <Button variant="contained" onClick={() => setImportOpen(true)}>
            Import Students CSV
          </Button>
        )}
      </Box>

      {mutError && <Alert severity="error" sx={{ mb: 2 }}>{mutError}</Alert>}
      {error && <ErrorAlert error={error} />}

      <TextField
        label="Search by name, roll number, or email"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        size="small"
        sx={{ mb: 2, maxWidth: 380 }}
        fullWidth
      />

      {isLoading ? (
        <LoadingSpinner />
      ) : (
        <TableContainer component={Paper} elevation={2}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell><strong>Name</strong></TableCell>
                <TableCell><strong>Roll No</strong></TableCell>
                <TableCell><strong>Email</strong></TableCell>
                <TableCell><strong>Role</strong></TableCell>
                <TableCell><strong>Status</strong></TableCell>
                <TableCell><strong>Joined</strong></TableCell>
                <TableCell><strong>Actions</strong></TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(users || []).map((u) => (
                <TableRow key={u._id} hover>
                  <TableCell>{u.name || '—'}</TableCell>
                  <TableCell>{u.roll_no || '—'}</TableCell>
                  <TableCell>{u.email}</TableCell>
                  <TableCell>
                    <Chip label={u.role} color={ROLE_COLORS[u.role] || 'default'} size="small" />
                  </TableCell>
                  <TableCell>
                    <Chip label={u.status} color={STATUS_COLORS[u.status] || 'default'} size="small" variant="outlined" />
                  </TableCell>
                  <TableCell>{formatDatetime(u.created_at)}</TableCell>
                  <TableCell>
                    <Stack direction="row" spacing={1}>
                      {u.status === 'DISABLED' && (
                        <Button
                          size="small"
                          onClick={() => statusMut.mutate({ userId: u._id, action: 'enable' })}
                        >
                          Enable
                        </Button>
                      )}
                      {u.status === 'ACTIVE' && String(u._id) !== String(currentUser?.id) && (
                        <Button
                          size="small"
                          color="error"
                          onClick={() => statusMut.mutate({ userId: u._id, action: 'disable' })}
                        >
                          Disable
                        </Button>
                      )}
                      {u.status === 'LOCKED' && (
                        <Button
                          size="small"
                          color="warning"
                          onClick={() => statusMut.mutate({ userId: u._id, action: 'unlock' })}
                        >
                          Unlock
                        </Button>
                      )}
                    </Stack>
                  </TableCell>
                </TableRow>
              ))}
              {users?.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} align="center" sx={{ color: 'text.secondary' }}>
                    No users found
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      <Dialog
        open={importOpen}
        onClose={() => { setImportOpen(false); setImportResult(null); setImportError(null) }}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Import Students from CSV</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" mb={2}>
            CSV columns: <code>roll_no, name, email, gender, year, program, hostel_code</code>
          </Typography>
          {importError && <Alert severity="error" sx={{ mb: 2 }}>{importError}</Alert>}
          {importResult && (
            <Alert severity={importResult.errors > 0 ? 'warning' : 'success'} sx={{ mb: 2 }}>
              Created: {importResult.created} · Updated: {importResult.updated} · Errors: {importResult.errors}
              {importResult.details?.length > 0 && (
                <Box component="ul" sx={{ m: 0, mt: 1, pl: 2 }}>
                  {importResult.details.map((d, i) => <li key={i}>{d}</li>)}
                </Box>
              )}
            </Alert>
          )}
          <input ref={fileRef} type="file" accept=".csv" onChange={handleFileUpload} style={{ display: 'none' }} />
          <Button variant="outlined" onClick={() => fileRef.current?.click()} disabled={importMut.isPending}>
            {importMut.isPending ? 'Importing…' : 'Choose CSV File'}
          </Button>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setImportOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
