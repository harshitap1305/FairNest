/**
 * Display metadata for notification types: a human label, an MUI colour and,
 * for students, the page that lets them act on the notification.
 */
export const NOTIFICATION_META = {
  CYCLE_OPENED: { label: 'Cycle opened', color: 'info', studentPath: '/student/group' },
  GROUP_INVITE: { label: 'Group invite', color: 'primary', studentPath: '/student/group' },
  ALLOTMENT_HELD: { label: 'Room offered', color: 'success', studentPath: '/student/allotment' },
  CASCADE_OFFER: { label: 'Cascade offer', color: 'success', studentPath: '/student/allotment' },
  HOLD_EXPIRING_SOON: { label: 'Expiring soon', color: 'warning', studentPath: '/student/allotment' },
  HOLD_EXTENDED: { label: 'Hold extended', color: 'info', studentPath: '/student/allotment' },
  WAITLISTED: { label: 'Waitlisted', color: 'warning', studentPath: '/student/allotment' },
  ALLOTMENT_CONFIRMED: { label: 'Confirmed', color: 'success', studentPath: '/student/allotment' },
  ALLOTMENT_DECLINED: { label: 'Declined', color: 'default', studentPath: '/student/allotment' },
  ALLOTMENT_EXPIRED: { label: 'Expired', color: 'error', studentPath: '/student/allotment' },
  ALLOTMENT_CANCELLED: { label: 'Cancelled', color: 'default', studentPath: '/student/allotment' },
  ALLOTMENT_REVOKED: { label: 'Revoked', color: 'error', studentPath: '/student/allotment' },
}

export function notificationMeta(type) {
  return NOTIFICATION_META[type] ?? {
    label: (type || 'General').replace(/_/g, ' ').toLowerCase().replace(/^\w/, (c) => c.toUpperCase()),
    color: 'default',
    studentPath: null,
  }
}
