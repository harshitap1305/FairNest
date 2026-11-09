import { format, formatDistanceToNow } from 'date-fns'

/**
 * Format an ISO datetime string to a human-readable local datetime.
 * e.g. "Nov 7, 2026, 5:30 PM"
 */
export function formatDatetime(iso) {
  if (!iso) return '—'
  try {
    return format(new Date(iso), 'MMM d, yyyy, h:mm a')
  } catch {
    return iso
  }
}

/**
 * Returns a string like "2h 15m" showing time until the ISO deadline.
 * Returns "Expired" if the date is in the past.
 */
export function timeUntil(iso) {
  if (!iso) return '—'
  try {
    const target = new Date(iso)
    const now = new Date()
    if (target <= now) return 'Expired'

    const diff = target - now
    const totalSeconds = Math.floor(diff / 1000)
    const hours = Math.floor(totalSeconds / 3600)
    const minutes = Math.floor((totalSeconds % 3600) / 60)
    const seconds = totalSeconds % 60

    if (hours > 0) {
      return `${hours}h ${minutes}m`
    }
    if (minutes > 0) {
      return `${minutes}m ${seconds}s`
    }
    return `${seconds}s`
  } catch {
    return '—'
  }
}

/**
 * Format a duration in seconds to "Xh Ym Zs".
 * e.g. formatDuration(3665) → "1h 1m 5s"
 */
export function formatDuration(seconds) {
  if (seconds == null || isNaN(seconds)) return '—'
  const s = Math.floor(seconds)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60

  const parts = []
  if (h > 0) parts.push(`${h}h`)
  if (m > 0) parts.push(`${m}m`)
  if (sec > 0 || parts.length === 0) parts.push(`${sec}s`)
  return parts.join(' ')
}

/**
 * Returns a relative time string like "3 hours ago" or "in 2 days".
 */
export function timeAgo(iso) {
  if (!iso) return '—'
  try {
    return formatDistanceToNow(new Date(iso), { addSuffix: true })
  } catch {
    return iso
  }
}
