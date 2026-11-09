import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import {
  Box,
  Card,
  CardContent,
  TextField,
  Button,
  Typography,
  Stack,
} from '@mui/material'
import { useAuth } from '../../auth/AuthContext'
import ErrorAlert from '../../components/common/ErrorAlert'

const ROLE_HOME = {
  STUDENT: '/student',
  ADMIN: '/admin',
  WARDEN: '/warden',
  AUDITOR: '/auditor',
  SUPER_ADMIN: '/superadmin',
}

export default function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm()

  const onSubmit = async ({ identifier, password }) => {
    setError(null)
    setLoading(true)
    try {
      const me = await login(identifier, password)
      navigate(ROLE_HOME[me?.role] ?? '/', { replace: true })
    } catch (err) {
      setError(err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <Box
      display="flex"
      alignItems="center"
      justifyContent="center"
      minHeight="100vh"
      bgcolor="grey.50"
      p={2}
    >
      <Card sx={{ maxWidth: 420, width: '100%' }}>
        <CardContent sx={{ p: 4 }}>
          <Typography variant="h5" fontWeight={700} gutterBottom>
            FairNest
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            Sign in with your college email or roll number
          </Typography>

          <ErrorAlert error={error} />

          <form onSubmit={handleSubmit(onSubmit)} noValidate>
            <Stack spacing={2}>
              <TextField
                label="Email or Roll Number"
                type="text"
                fullWidth
                autoFocus
                autoComplete="username"
                {...register('identifier', { required: 'Email or roll number is required' })}
                error={Boolean(errors.identifier)}
                helperText={errors.identifier?.message}
              />
              <TextField
                label="Password"
                type="password"
                fullWidth
                autoComplete="current-password"
                {...register('password', { required: 'Password is required' })}
                error={Boolean(errors.password)}
                helperText={errors.password?.message}
              />
              <Button
                type="submit"
                variant="contained"
                size="large"
                fullWidth
                disabled={loading}
              >
                {loading ? 'Signing in…' : 'Sign In'}
              </Button>
            </Stack>
          </form>

          <Box sx={{ mt: 2, display: 'flex', justifyContent: 'space-between' }}>
            <Button size="small" onClick={() => navigate('/activate')} sx={{ textTransform: 'none' }}>
              Activate account
            </Button>
            <Button size="small" onClick={() => navigate('/forgot')} sx={{ textTransform: 'none' }}>
              Forgot password?
            </Button>
          </Box>
        </CardContent>
      </Card>
    </Box>
  )
}
