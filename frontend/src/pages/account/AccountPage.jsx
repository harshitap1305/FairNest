import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import {
  Box, Typography, Grid, Card, CardContent, CardHeader, Avatar, Chip, Stack, Divider,
  TextField, Button, Alert, Table, TableHead, TableRow, TableCell, TableBody,
  IconButton, InputAdornment, Tooltip, List, ListItem, ListItemIcon, ListItemText,
} from '@mui/material'
import Visibility from '@mui/icons-material/Visibility'
import VisibilityOff from '@mui/icons-material/VisibilityOff'
import LaptopIcon from '@mui/icons-material/Laptop'
import PhoneIphoneIcon from '@mui/icons-material/PhoneIphone'
import LoginIcon from '@mui/icons-material/Login'
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline'
import LockResetIcon from '@mui/icons-material/LockReset'
import LogoutIcon from '@mui/icons-material/Logout'
import ShieldIcon from '@mui/icons-material/Shield'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  changePassword, listSessions, revokeSession, logoutAll, getSecurityActivity,
} from '../../api/auth'
import { useAuth } from '../../auth/AuthContext'
import ErrorAlert from '../../components/common/ErrorAlert'
import ConfirmDialog from '../../components/common/ConfirmDialog'
import LoadingSpinner from '../../components/common/LoadingSpinner'
import PasswordStrengthMeter from '../../components/common/PasswordStrengthMeter'
import { formatDatetime, timeAgo } from '../../utils/dates'
import { describeUserAgent } from '../../utils/device'
import { MIN_PASSWORD_LENGTH } from '../../utils/password'

const ACTIVITY_LABELS = {
  LOGIN_SUCCESS: { label: 'Signed in', icon: <LoginIcon color="success" /> },
  LOGIN_FAILED: { label: 'Failed sign-in attempt', icon: <ErrorOutlineIcon color="error" /> },
  ACCOUNT_LOCKED: { label: 'Account temporarily locked', icon: <ErrorOutlineIcon color="error" /> },
  ACTIVATE_ACCOUNT: { label: 'Account activated', icon: <ShieldIcon color="primary" /> },
  PASSWORD_CHANGE: { label: 'Password changed', icon: <LockResetIcon color="primary" /> },
  PASSWORD_RESET: { label: 'Password reset via email link', icon: <LockResetIcon color="warning" /> },
  LOGOUT_ALL: { label: 'Signed out of all devices', icon: <LogoutIcon /> },
  REVOKE_SESSION: { label: 'Signed out a device', icon: <LogoutIcon /> },
  TOKEN_REUSE_DETECTED: { label: 'Suspicious token reuse blocked', icon: <ErrorOutlineIcon color="error" /> },
}

function initials(name = '') {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join('') || '?'
}

function ProfileCard({ user }) {
  const rows = [
    ['Email', user?.email],
    ['Roll number', user?.roll_no],
    ['Program', user?.program && `${user.program}${user?.year ? ` · Year ${user.year}` : ''}`],
    ['Last sign-in', user?.last_login_at && formatDatetime(user.last_login_at)],
  ].filter(([, v]) => v)
  return (
    <Card>
      <CardContent>
        <Box display="flex" alignItems="center" gap={2} mb={2}>
          <Avatar sx={{ width: 56, height: 56, bgcolor: 'primary.main', fontSize: 22 }}>
            {initials(user?.name)}
          </Avatar>
          <Box>
            <Typography variant="h6">{user?.name ?? 'User'}</Typography>
            <Stack direction="row" spacing={1} mt={0.5}>
              <Chip size="small" label={user?.role?.replace('_', ' ')} color="primary" />
              {user?.accessibility_verified && <Chip size="small" label="Accessibility verified" color="success" />}
            </Stack>
          </Box>
        </Box>
        <Divider sx={{ mb: 1.5 }} />
        {rows.map(([k, v]) => (
          <Box key={k} display="flex" justifyContent="space-between" py={0.5} gap={2}>
            <Typography variant="body2" color="text.secondary">{k}</Typography>
            <Typography variant="body2" fontWeight={500} textAlign="right">{v}</Typography>
          </Box>
        ))}
        {user?.role === 'STUDENT' && (
          <Box display="flex" justifyContent="space-between" py={0.5}>
            <Typography variant="body2" color="text.secondary">Fairness credits</Typography>
            <Typography variant="body2" fontWeight={700}>{user?.credits ?? '—'} / 10</Typography>
          </Box>
        )}
      </CardContent>
    </Card>
  )
}

function ChangePasswordCard({ onChanged }) {
  const [show, setShow] = useState(false)
  const { register, handleSubmit, watch, reset, formState: { errors } } = useForm()
  const newPw = watch('new_password', '')
  const mutation = useMutation({
    mutationFn: ({ old_password, new_password }) => changePassword(old_password, new_password),
    onSuccess: () => { reset(); onChanged() },
  })
  const adornment = (
    <InputAdornment position="end">
      <IconButton onClick={() => setShow((s) => !s)} edge="end" aria-label="Toggle password visibility">
        {show ? <VisibilityOff /> : <Visibility />}
      </IconButton>
    </InputAdornment>
  )
  return (
    <Card>
      <CardHeader title="Change password" subheader="You will be signed out everywhere afterwards." />
      <CardContent sx={{ pt: 0 }}>
        <ErrorAlert error={mutation.error} />
        <form onSubmit={handleSubmit((v) => mutation.mutate(v))} noValidate>
          <Stack spacing={2}>
            <TextField
              label="Current password"
              type={show ? 'text' : 'password'}
              autoComplete="current-password"
              InputProps={{ endAdornment: adornment }}
              {...register('old_password', { required: 'Enter your current password' })}
              error={Boolean(errors.old_password)}
              helperText={errors.old_password?.message}
            />
            <TextField
              label="New password"
              type={show ? 'text' : 'password'}
              autoComplete="new-password"
              {...register('new_password', {
                required: 'Choose a new password',
                minLength: { value: MIN_PASSWORD_LENGTH, message: `Use at least ${MIN_PASSWORD_LENGTH} characters` },
                validate: (v, all) => v !== all.old_password || 'New password must differ from the current one',
              })}
              error={Boolean(errors.new_password)}
              helperText={errors.new_password?.message}
            />
            <PasswordStrengthMeter password={newPw} />
            <TextField
              label="Confirm new password"
              type={show ? 'text' : 'password'}
              autoComplete="new-password"
              {...register('confirm', { validate: (v) => v === newPw || 'Passwords do not match' })}
              error={Boolean(errors.confirm)}
              helperText={errors.confirm?.message}
            />
            <Box>
              <Button type="submit" variant="contained" disabled={mutation.isPending}>
                {mutation.isPending ? 'Updating…' : 'Update password'}
              </Button>
            </Box>
          </Stack>
        </form>
      </CardContent>
    </Card>
  )
}

function SessionsCard({ onSignedOutEverywhere }) {
  const qc = useQueryClient()
  const [confirmAll, setConfirmAll] = useState(false)
  const { data: sessions, isLoading, error } = useQuery({ queryKey: ['sessions'], queryFn: listSessions })
  const revoke = useMutation({
    mutationFn: revokeSession,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sessions'] }),
  })
  const others = (sessions || []).filter((s) => !s.current)
  const revokeOthers = useMutation({
    mutationFn: async () => { for (const s of others) await revokeSession(s.family_id) },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sessions'] }),
  })
  const signOutAll = useMutation({ mutationFn: logoutAll, onSuccess: onSignedOutEverywhere })

  return (
    <Card>
      <CardHeader
        title="Where you're signed in"
        subheader="Sign out any device you don't recognise."
        action={
          <Stack direction="row" spacing={1} sx={{ mt: 1, mr: 1 }}>
            <Button size="small" disabled={!others.length || revokeOthers.isPending} onClick={() => revokeOthers.mutate()}>
              Sign out other devices
            </Button>
            <Button size="small" color="error" onClick={() => setConfirmAll(true)}>
              Sign out everywhere
            </Button>
          </Stack>
        }
      />
      <CardContent sx={{ pt: 0 }}>
        <ErrorAlert error={error || revoke.error || revokeOthers.error || signOutAll.error} />
        {isLoading ? <LoadingSpinner minHeight="80px" /> : (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Device</TableCell>
                <TableCell>IP address</TableCell>
                <TableCell>Signed in</TableCell>
                <TableCell>Expires</TableCell>
                <TableCell align="right" />
              </TableRow>
            </TableHead>
            <TableBody>
              {(sessions || []).map((s) => {
                const dev = describeUserAgent(s.user_agent)
                return (
                  <TableRow key={s.family_id} hover>
                    <TableCell>
                      <Box display="flex" alignItems="center" gap={1}>
                        {dev.mobile ? <PhoneIphoneIcon fontSize="small" /> : <LaptopIcon fontSize="small" />}
                        <Tooltip title={s.user_agent || ''}><span>{dev.label}</span></Tooltip>
                        {s.current && <Chip size="small" color="success" label="This device" />}
                      </Box>
                    </TableCell>
                    <TableCell>{s.ip || '—'}</TableCell>
                    <TableCell><Tooltip title={formatDatetime(s.created_at)}><span>{timeAgo(s.created_at)}</span></Tooltip></TableCell>
                    <TableCell>{formatDatetime(s.expires_at)}</TableCell>
                    <TableCell align="right">
                      {!s.current && (
                        <Button size="small" color="error" disabled={revoke.isPending} onClick={() => revoke.mutate(s.family_id)}>
                          Sign out
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                )
              })}
              {!sessions?.length && (
                <TableRow><TableCell colSpan={5}><Typography color="text.secondary">No active sessions.</Typography></TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        )}
      </CardContent>
      <ConfirmDialog
        open={confirmAll}
        title="Sign out everywhere?"
        message="All devices, including this one, will be signed out. You will need to sign in again."
        confirmLabel="Sign out everywhere"
        onConfirm={() => { setConfirmAll(false); signOutAll.mutate() }}
        onCancel={() => setConfirmAll(false)}
      />
    </Card>
  )
}

function ActivityCard() {
  const { data, isLoading, error } = useQuery({ queryKey: ['security-activity'], queryFn: () => getSecurityActivity(15) })
  const failed = (data || []).filter((e) => e.action === 'LOGIN_FAILED').length
  return (
    <Card>
      <CardHeader title="Recent security activity" />
      <CardContent sx={{ pt: 0 }}>
        <ErrorAlert error={error} />
        {failed >= 3 && (
          <Alert severity="warning" sx={{ mb: 1 }}>
            {failed} failed sign-in attempts recently. If these weren't you, change your password.
          </Alert>
        )}
        {isLoading ? <LoadingSpinner minHeight="80px" /> : (
          <List dense disablePadding>
            {(data || []).map((e, i) => {
              const meta = ACTIVITY_LABELS[e.action] ?? { label: e.action, icon: <ShieldIcon /> }
              return (
                <ListItem key={`${e.ts}-${i}`} disableGutters>
                  <ListItemIcon sx={{ minWidth: 36 }}>{meta.icon}</ListItemIcon>
                  <ListItemText
                    primary={meta.label}
                    secondary={`${timeAgo(e.ts)}${e.ip ? ` · ${e.ip}` : ''}`}
                  />
                </ListItem>
              )
            })}
            {!data?.length && <Typography color="text.secondary">No activity recorded yet.</Typography>}
          </List>
        )}
      </CardContent>
    </Card>
  )
}

export default function AccountPage() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const goToLogin = async (notice) => {
    await logout()
    navigate('/login', { replace: true, state: { notice } })
  }

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" fontWeight={700} mb={0.5}>Account & security</Typography>
      <Typography color="text.secondary" mb={3}>Manage your profile, password and signed-in devices.</Typography>
      <Grid container spacing={3}>
        <Grid item xs={12} md={5}>
          <Stack spacing={3}>
            <ProfileCard user={user} />
            <ActivityCard />
          </Stack>
        </Grid>
        <Grid item xs={12} md={7}>
          <Stack spacing={3}>
            <ChangePasswordCard onChanged={() => goToLogin('Password changed. Please sign in with your new password.')} />
            <SessionsCard onSignedOutEverywhere={() => goToLogin('You have been signed out of all devices.')} />
          </Stack>
        </Grid>
      </Grid>
    </Box>
  )
}
