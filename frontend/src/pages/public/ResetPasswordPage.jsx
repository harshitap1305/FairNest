import React, { useState } from 'react'
import { useSearchParams, Link, useNavigate } from 'react-router-dom'
import { Box, Button, Paper, TextField, Typography, Alert } from '@mui/material'
import { useForm } from 'react-hook-form'
import { resetPassword } from '../../api/auth'
import { getErrorMessage } from '../../utils/errors'

export default function ResetPasswordPage() {
  const [searchParams] = useSearchParams()
  const urlToken = searchParams.get('token') || ''
  const navigate = useNavigate()
  const { register, handleSubmit, watch, formState: { errors, isSubmitting } } = useForm({
    defaultValues: { token: urlToken, password: '', confirm: '' },
  })
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(false)

  const onSubmit = async ({ token, password }) => {
    setError(null)
    if (!token?.trim()) {
      setError('Missing reset token.')
      return
    }
    try {
      await resetPassword(token.trim(), password)
      setSuccess(true)
      setTimeout(() => navigate('/login'), 2500)
    } catch (err) {
      setError(getErrorMessage(err))
    }
  }

  if (success) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="100vh" p={2}>
        <Paper elevation={3} sx={{ p: 5, maxWidth: 420, width: '100%', textAlign: 'center' }}>
          <Alert severity="success">Password reset successful! Redirecting to login…</Alert>
        </Paper>
      </Box>
    )
  }

  return (
    <Box display="flex" justifyContent="center" alignItems="center" minHeight="100vh" bgcolor="background.default" p={2}>
      <Paper elevation={3} sx={{ p: 5, maxWidth: 420, width: '100%' }}>
        <Typography variant="h5" fontWeight={700} mb={3}>Reset Password</Typography>
        <Box component="form" onSubmit={handleSubmit(onSubmit)} noValidate>
          {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
          {!urlToken && (
            <TextField
              label="Reset token"
              fullWidth
              margin="normal"
              error={!!errors.token}
              helperText={errors.token?.message}
              {...register('token', { required: 'Reset token is required' })}
            />
          )}
          <TextField
            label="New password"
            type="password"
            fullWidth
            margin="normal"
            error={!!errors.password}
            helperText={errors.password?.message}
            {...register('password', {
              required: 'Password is required',
              minLength: { value: 12, message: 'Minimum 12 characters' },
            })}
          />
          <TextField
            label="Confirm password"
            type="password"
            fullWidth
            margin="normal"
            error={!!errors.confirm}
            helperText={errors.confirm?.message}
            {...register('confirm', {
              required: 'Please confirm your password',
              validate: (val) => val === watch('password') || 'Passwords do not match',
            })}
          />
          <Button type="submit" variant="contained" fullWidth sx={{ mt: 2 }} disabled={isSubmitting}>
            {isSubmitting ? 'Resetting…' : 'Reset Password'}
          </Button>
        </Box>
        <Box mt={2} textAlign="center">
          <Link to="/login" style={{ textDecoration: 'none', color: 'inherit', fontSize: '0.875rem' }}>
            ← Back to login
          </Link>
        </Box>
      </Paper>
    </Box>
  )
}
