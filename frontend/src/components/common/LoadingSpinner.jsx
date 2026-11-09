import React from 'react'
import { Box, CircularProgress } from '@mui/material'

/**
 * Full-area centered loading spinner.
 * @param {object} props
 * @param {string} [props.size] - Size passed to CircularProgress (default "40px")
 * @param {string} [props.minHeight] - Min height of the container (default "200px")
 */
export default function LoadingSpinner({ size = 40, minHeight = '200px' }) {
  return (
    <Box
      display="flex"
      alignItems="center"
      justifyContent="center"
      minHeight={minHeight}
      width="100%"
    >
      <CircularProgress size={size} />
    </Box>
  )
}
