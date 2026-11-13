import React from 'react'
import { Box, LinearProgress, Typography, Stack } from '@mui/material'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import RadioButtonUncheckedIcon from '@mui/icons-material/RadioButtonUnchecked'
import { passwordChecks, passwordStrength } from '../../utils/password'

/** Live strength bar plus a checklist of the password rules. */
export default function PasswordStrengthMeter({ password }) {
  if (!password) return null
  const { score, label, color } = passwordStrength(password)
  return (
    <Box>
      <Box display="flex" alignItems="center" gap={1}>
        <LinearProgress
          variant="determinate"
          value={(score / 5) * 100}
          color={color === 'inherit' ? 'primary' : color}
          sx={{ flexGrow: 1, height: 6, borderRadius: 3 }}
        />
        <Typography variant="caption" color={`${color}.main`} fontWeight={600} minWidth={72}>
          {label}
        </Typography>
      </Box>
      <Stack spacing={0.25} mt={1}>
        {passwordChecks(password).map((c) => (
          <Box key={c.label} display="flex" alignItems="center" gap={0.75}>
            {c.ok
              ? <CheckCircleIcon color="success" sx={{ fontSize: 16 }} />
              : <RadioButtonUncheckedIcon color="disabled" sx={{ fontSize: 16 }} />}
            <Typography variant="caption" color={c.ok ? 'text.primary' : 'text.secondary'}>
              {c.label}
            </Typography>
          </Box>
        ))}
      </Stack>
    </Box>
  )
}
