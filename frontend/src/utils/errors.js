// Map of backend error codes to user-friendly messages
export const API_ERRORS = {
  // Auth
  INVALID_CREDENTIALS: 'Invalid email, roll number, or password.',
  ACCOUNT_INACTIVE: 'Your account is inactive or disabled. Contact support.',
  ACCOUNT_LOCKED: 'Account temporarily locked due to failed logins. Please wait.',
  TOKEN_EXPIRED: 'Your session has expired. Please log in again.',
  TOKEN_INVALID: 'Invalid or expired token.',
  TOKEN_REUSE_DETECTED: 'Security alert: session token reuse detected. Please log in again.',
  CSRF_ORIGIN_MISMATCH: 'Untrusted request origin.',
  RATE_LIMITED: 'Too many attempts. Please wait before trying again.',
  ROLE_HIERARCHY_VIOLATION: 'You do not have sufficient privileges to grant this role.',
  SELF_GRANT_FORBIDDEN: 'You cannot grant a role to yourself.',
  LAST_SUPER_ADMIN: 'Cannot revoke or disable the last active Super Admin.',
  HOSTEL_SCOPE_DENIED: 'You do not have access to this hostel.',

  // Group / Application
  GROUP_ALREADY_EXISTS: 'You already belong to a group in this cycle.',
  NOT_LEADER: 'Only the group leader can perform this action.',
  INVITE_ALREADY_EXISTS: 'This student already has an invite to the group.',
  ALREADY_IN_GROUP: 'Student is already an accepted member of a group in this cycle.',
  GROUP_FULL: 'Group has reached the maximum allowed size.',
  GENDER_MISMATCH: 'All group members must match hostel eligibility.',
  WINDOW_NOT_OPEN: 'Applications for this cycle have not opened yet.',
  WINDOW_CLOSED: 'The application window for this cycle is closed.',
  ROOM_NOT_ELIGIBLE: 'One or more selected choices are unavailable or cannot accommodate your group size.',
  VERSION_CONFLICT: 'Application was modified concurrently. Please refresh and try again.',
  IDEMPOTENCY_CONFLICT: 'Duplicate request with conflicting payload.',

  // Allotment (NO payment flow — hold acceptance only)
  ALLOTMENT_NOT_FOUND: 'Allotment not found.',
  HOLD_EXPIRED: 'The hold deadline has expired.',
  ALREADY_CONFIRMED: 'Allotment is already confirmed.',
  CANCEL_NOT_CONFIRMED: 'Only confirmed allotments can be cancelled.',

  // Cycle / Rooms
  ROOM_IN_LIVE_RELEASE: 'Cannot open cycle: one or more rooms are currently live in another active cycle.',
  WINDOW_EXTEND_INVALID: 'Cannot extend close time earlier than the current close time or schedule.',
  ALLOCATION_ALREADY_RUN: 'Allocation has already run or cycle is not closed for applications.',
  SEED_NOT_REVEALED: 'Allocation seed is only revealed after allocation runs.',
  ROOM_BUSY: 'Room has an active HELD or CONFIRMED allotment; revoke it before setting maintenance.',
  ROOMS_ALREADY_EXIST: 'Some rooms already exist in this hostel.',

  // Generic
  UNAUTHORIZED: 'Authentication required.',
  FORBIDDEN: 'You do not have permission to perform this action.',
  NOT_FOUND: 'The requested resource was not found.',
  VALIDATION_ERROR: 'Invalid input.',
  SERVER_ERROR: 'A server error occurred. Please try again later.',
  NETWORK_ERROR: 'Network error. Please check your connection.',
  UNKNOWN: 'An unexpected error occurred.',
}

/**
 * Extract a user-friendly error message from backend error envelopes:
 *   { error: { code, message, request_id } }
 */
export function getErrorMessage(err) {
  if (!err) return API_ERRORS.UNKNOWN
  if (typeof err === 'string') return err

  if (err.response) {
    const data = err.response.data
    const apiErr = data?.error

    if (apiErr) {
      if (apiErr.message) return String(apiErr.message)
      if (apiErr.code && API_ERRORS[apiErr.code]) return API_ERRORS[apiErr.code]
    }

    if (data?.error_code && API_ERRORS[data.error_code]) {
      return API_ERRORS[data.error_code]
    }
    if (data?.detail) {
      return typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
    }
    if (data?.message) return String(data.message)

    if (err.response.status === 401) return API_ERRORS.UNAUTHORIZED
    if (err.response.status === 403) return API_ERRORS.FORBIDDEN
    if (err.response.status === 404) return API_ERRORS.NOT_FOUND
    if (err.response.status >= 500) return API_ERRORS.SERVER_ERROR
  }

  if (err.request && !err.response) return API_ERRORS.NETWORK_ERROR
  if (err.message) return err.message

  return API_ERRORS.UNKNOWN
}
