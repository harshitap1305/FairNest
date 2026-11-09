import React, { useState, useEffect } from 'react'
import { Typography } from '@mui/material'

/**
 * Countdown timer that counts down to a deadline ISO string.
 * Shows "Xh Ym Zs remaining" and turns red under 1 hour.
 * @param {object} props
 * @param {string} props.deadline - ISO date string
 * @param {object} [props.sx] - Extra sx props for the Typography
 */
export default function CountdownTimer({ deadline, sx = {} }) {
  const [timeLeft, setTimeLeft] = useState(null)
  const [isUnderOneHour, setIsUnderOneHour] = useState(false)

  useEffect(() => {
    if (!deadline) return

    function computeTimeLeft() {
      const target = new Date(deadline)
      const now = new Date()
      const diff = target - now

      if (diff <= 0) {
        setTimeLeft('Expired')
        setIsUnderOneHour(true)
        return
      }

      const totalSeconds = Math.floor(diff / 1000)
      const hours = Math.floor(totalSeconds / 3600)
      const minutes = Math.floor((totalSeconds % 3600) / 60)
      const seconds = totalSeconds % 60

      setIsUnderOneHour(hours < 1)
      setTimeLeft(`${hours}h ${minutes}m ${seconds}s remaining`)
    }

    computeTimeLeft()
    const interval = setInterval(computeTimeLeft, 1000)
    return () => clearInterval(interval)
  }, [deadline])

  if (!deadline) return null

  return (
    <Typography
      variant="body2"
      fontWeight="medium"
      sx={{
        color: isUnderOneHour ? 'error.main' : 'text.secondary',
        ...sx,
      }}
    >
      {timeLeft ?? '…'}
    </Typography>
  )
}
