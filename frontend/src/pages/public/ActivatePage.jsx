import React, { useState } from 'react'
import { useSearchParams, Link, useNavigate } from 'react-router-dom'
import { Box, Typography, Paper, Button, TextField, Alert } from '@mui/material'
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline'
import { useForm } from 'react-hook-form'
import { activate } from '../../api/auth'
import { getErrorMessage } from '../../utils/errors'
import { MIN_PASSWORD_LENGTH } from '../../utils/password'
import PasswordStrengthMeter from '../../components/common/PasswordStrengthMeter'

export default function ActivatePage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const urlToken = searchParams.get('token') || ''
  const [done, setDone] = useState(false)
  const [error, setError] = useState(null)

  const { register, handleSubmit, watch, formState: { errors, isSubmitting } } = useForm({
    defaultValues: { token: urlToken, password: '', confirm: '' },
  })

  const onSubmit = async ({ token, password }) => {
    setError(null)
    try {
      await activate(token.trim(), password)
      setDone(true)
    } catch (err) {
      setError(getErrorMessage(err))
    }
  }

  return (
    <Box display="flex" justifyContent="center" alignItems="center" minHeight="100vh" bgcolor="background.default" p={2}>
      <Paper elevation={3} sx={{ p: 5, maxWidth: 440, width: '100%' }}>
        {done ? (
          <Box textAlign="center">
            <CheckCircleOutlineIcon color="success" sx={{ fontSize: 64, mb: 2 }} />
            <Typography variant="h5" fontWeight={700} gutterBottom>Account Activated!</Typography>
            <Typography color="text.secondary" mb={3}>
              Your password has been set and your account is now active.
            </Typography>
            <Button variant="contained" onClick={() => navigate('/login')} fullWidth>
              Go to Login
            </Button>
          </Box>
        ) : (
          <>
            <Typography variant="h5" fontWeight={700} mb={1}>Activate Your Account</Typography>
            <Typography color="text.secondary" variant="body2" mb={3}>
              Set a strong password (at least 12 characters) to activate your FairNest account.
            </Typography>

            {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

            <Box component="form" onSubmit={handleSubmit(onSubmit)} noValidate>
              {!urlToken && (
                <TextField
                  label="Activation Token"
                  fullWidth
                  margin="normal"
                  error={!!errors.token}
                  helperText={errors.token?.message}
                  {...register('token', { required: 'Activation token is required' })}
                />
              )}
              <TextField
                label="Create Password"
                type="password"
                fullWidth
                margin="normal"
                error={!!errors.password}
                helperText={errors.password?.message}
                {...register('password', {
                  required: 'Password is required',
                  minLength: { value: MIN_PASSWORD_LENGTH, message: `Use at least ${MIN_PASSWORD_LENGTH} characters` },
                })}
              />
              <PasswordStrengthMeter password={watch('password')} />
              <TextField
                label="Confirm Password"
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
              <Button
                type="submit"
                variant="contained"
                fullWidth
                size="large"
                sx={{ mt: 2 }}
                disabled={isSubmitting}
              >
                {isSubmitting ? 'Activating…' : 'Activate Account'}
              </Button>
            </Box>

            <Box mt={2} textAlign="center">
              <Typography variant="body2">
                <Link to="/login" style={{ textDecoration: 'none', color: 'inherit' }}>
                  ← Back to login
                </Link>
              </Typography>
            </Box>
          </>
        )}
      </Paper>
    </Box>
  )
}
