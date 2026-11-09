import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { Box, Button, Paper, TextField, Typography, Alert } from '@mui/material'
import { useForm } from 'react-hook-form'
import { forgotPassword } from '../../api/auth'
import { getErrorMessage } from '../../utils/errors'

export default function ForgotPasswordPage() {
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm()
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState(null)

  const onSubmit = async ({ email }) => {
    setError(null)
    try {
      await forgotPassword(email)
      setSubmitted(true)
    } catch (err) {
      setError(getErrorMessage(err))
    }
  }

  return (
    <Box display="flex" justifyContent="center" alignItems="center" minHeight="100vh" bgcolor="background.default" p={2}>
      <Paper elevation={3} sx={{ p: 5, maxWidth: 420, width: '100%' }}>
        <Typography variant="h5" fontWeight={700} mb={1}>Forgot Password</Typography>
        <Typography color="text.secondary" mb={3}>
          Enter your email and we'll send you a reset link.
        </Typography>

        {submitted ? (
          <Alert severity="success">
            If that email is registered, a password reset link has been queued.
          </Alert>
        ) : (
          <Box component="form" onSubmit={handleSubmit(onSubmit)} noValidate>
            {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
            <TextField
              label="Email address"
              type="email"
              fullWidth
              margin="normal"
              error={!!errors.email}
              helperText={errors.email?.message}
              {...register('email', {
                required: 'Email is required',
                pattern: { value: /\S+@\S+\.\S+/, message: 'Invalid email' },
              })}
            />
            <Button type="submit" variant="contained" fullWidth sx={{ mt: 2 }} disabled={isSubmitting}>
              {isSubmitting ? 'Sending…' : 'Send Reset Link'}
            </Button>
          </Box>
        )}

        <Box mt={2} textAlign="center">
          <Typography variant="body2">
            <Link to="/login" style={{ textDecoration: 'none', color: 'inherit' }}>← Back to login</Link>
          </Typography>
        </Box>
      </Paper>
    </Box>
  )
}
