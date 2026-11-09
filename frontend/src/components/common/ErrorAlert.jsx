import React from 'react'
import { Alert } from '@mui/material'
import { getErrorMessage } from '../../utils/errors'

/**
 * Displays an error in a MUI Alert.
 * @param {object} props
 * @param {string|Error|object} props.error - Error to display (string, Error, or axios error)
 * @param {string} [props.sx] - Additional sx styles
 */
export default function ErrorAlert({ error, sx = {} }) {
  if (!error) return null
  const message = getErrorMessage(error)
  return (
    <Alert severity="error" sx={{ mb: 2, ...sx }}>
      {message}
    </Alert>
  )
}
