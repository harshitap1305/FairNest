import React, { useState } from 'react'
import {
  Box, Typography, Button, Paper, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, Chip, MenuItem, TextField,
  Dialog, DialogTitle, DialogContent, DialogActions, Alert,
} from '@mui/material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listRoleGrants, grantRole, revokeRoleGrant } from '../../api/admin'
import { listHostels } from '../../api/hostel'
import { useForm, Controller } from 'react-hook-form'
import ConfirmDialog from '../../components/common/ConfirmDialog'
import LoadingSpinner from '../../components/common/LoadingSpinner'
import { formatDatetime } from '../../utils/dates'
import { getErrorMessage } from '../../utils/errors'

const ROLES = ['WARDEN', 'ADMIN', 'AUDITOR', 'SUPER_ADMIN', 'STUDENT']
const ROLE_COLORS = {
  STUDENT: 'default', WARDEN: 'primary', ADMIN: 'secondary', AUDITOR: 'info', SUPER_ADMIN: 'error',
}
const STATUS_COLORS = { PENDING: 'warning', ACTIVE: 'success', REVOKED: 'default' }

export default function RolesAndAccessPage() {
  const qc = useQueryClient()
  const [grantOpen, setGrantOpen] = useState(false)
  const [revokeTarget, setRevokeTarget] = useState(null)
  const [mutError, setMutError] = useState(null)

  const { data: grants, isLoading } = useQuery({
    queryKey: ['role-grants'],
    queryFn: () => listRoleGrants(),
  })
  const { data: hostels = [] } = useQuery({
    queryKey: ['hostels'],
    queryFn: () => listHostels(),
  })

  const { register, handleSubmit, reset, control, watch, formState: { errors } } = useForm({
    defaultValues: { email: '', role: 'WARDEN', hostel_ids: [] },
  })
  const selectedRole = watch('role')

  const grantMut = useMutation({
    mutationFn: (d) => grantRole(d),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['role-grants'] })
      setGrantOpen(false)
      setMutError(null)
      reset()
    },
    onError: (e) => setMutError(getErrorMessage(e)),
  })

  const revokeMut = useMutation({
    mutationFn: (id) => revokeRoleGrant(id),
    onSuccess: () => {
      setMutError(null)
      qc.invalidateQueries({ queryKey: ['role-grants'] })
      setRevokeTarget(null)
    },
    onError: (e) => {
      setRevokeTarget(null)
      setMutError(getErrorMessage(e))
    },
  })

  if (isLoading) return <LoadingSpinner />

  const hostelMap = Object.fromEntries(hostels.map((h) => [h._id, `${h.name} (${h.code})`]))

  return (
    <Box sx={{ p: 3 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h4" fontWeight={700}>Roles & Access Grants</Typography>
        <Button variant="contained" onClick={() => setGrantOpen(true)}>Grant Role</Button>
      </Box>

      {mutError && <Alert severity="error" sx={{ mb: 2 }}>{mutError}</Alert>}

      <TableContainer component={Paper} elevation={2}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell><strong>Email</strong></TableCell>
              <TableCell><strong>Role</strong></TableCell>
              <TableCell><strong>Status</strong></TableCell>
              <TableCell><strong>Scoped Hostels</strong></TableCell>
              <TableCell><strong>Granted At</strong></TableCell>
              <TableCell><strong>Actions</strong></TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {(grants || []).map((g) => (
              <TableRow key={g._id} hover>
                <TableCell>{g.email || '—'}</TableCell>
                <TableCell>
                  <Chip label={g.role} color={ROLE_COLORS[g.role] || 'default'} size="small" />
                </TableCell>
                <TableCell>
                  <Chip
                    label={g.status || 'PENDING'}
                    color={STATUS_COLORS[g.status] || 'default'}
                    size="small"
                    variant="outlined"
                  />
                </TableCell>
                <TableCell>
                  {(g.hostel_ids || []).length > 0
                    ? g.hostel_ids.map((id) => hostelMap[id] || id).join(', ')
                    : 'All / Global'}
                </TableCell>
                <TableCell>{formatDatetime(g.granted_at || g.created_at)}</TableCell>
                <TableCell>
                  {g.status !== 'REVOKED' && (
                    <Button size="small" color="error" onClick={() => setRevokeTarget(g._id)}>
                      Revoke
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {grants?.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} align="center" sx={{ color: 'text.secondary' }}>
                  No role grants found
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>

      <Dialog open={grantOpen} onClose={() => setGrantOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Grant Role by Email</DialogTitle>
        <Box component="form" onSubmit={handleSubmit((d) => grantMut.mutate(d))}>
          <DialogContent>
            {mutError && <Alert severity="error" sx={{ mb: 2 }}>{mutError}</Alert>}
            <TextField
              label="User email"
              type="email"
              fullWidth
              margin="normal"
              error={!!errors.email}
              helperText={errors.email?.message}
              {...register('email', { required: 'Email is required' })}
            />
            <Controller
              name="role"
              control={control}
              rules={{ required: 'Role is required' }}
              render={({ field }) => (
                <TextField {...field} select label="Role" fullWidth margin="normal">
                  {ROLES.map((r) => <MenuItem key={r} value={r}>{r}</MenuItem>)}
                </TextField>
              )}
            />
            {['WARDEN', 'ADMIN'].includes(selectedRole) && (
              <Controller
                name="hostel_ids"
                control={control}
                render={({ field }) => (
                  <TextField
                    {...field}
                    select
                    label="Managed Hostels (required for Warden/Admin scope)"
                    fullWidth
                    margin="normal"
                    SelectProps={{ multiple: true }}
                  >
                    {hostels.map((h) => (
                      <MenuItem key={h._id} value={h._id}>{h.name} ({h.code})</MenuItem>
                    ))}
                  </TextField>
                )}
              />
            )}
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setGrantOpen(false)}>Cancel</Button>
            <Button type="submit" variant="contained" disabled={grantMut.isPending}>
              {grantMut.isPending ? 'Granting…' : 'Grant Role'}
            </Button>
          </DialogActions>
        </Box>
      </Dialog>

      <ConfirmDialog
        open={!!revokeTarget}
        title="Revoke Role Grant"
        message="Revoke this role grant? Active staff accounts will revert to STUDENT and sessions invalidated."
        onConfirm={() => revokeMut.mutate(revokeTarget)}
        onCancel={() => setRevokeTarget(null)}
      />
    </Box>
  )
}
