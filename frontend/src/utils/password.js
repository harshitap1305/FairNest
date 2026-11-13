/**
 * Client-side password strength estimate. The backend still enforces the real rules
 * (min 10 chars, not common, not equal to the identifier); this only guides the user.
 */
export const MIN_PASSWORD_LENGTH = 10

export function passwordChecks(pw = '') {
  return [
    { ok: pw.length >= MIN_PASSWORD_LENGTH, label: `At least ${MIN_PASSWORD_LENGTH} characters` },
    { ok: /[a-z]/.test(pw) && /[A-Z]/.test(pw), label: 'Upper and lower case letters' },
    { ok: /\d/.test(pw), label: 'A number' },
    { ok: /[^A-Za-z0-9]/.test(pw), label: 'A symbol' },
  ]
}

export function passwordStrength(pw = '') {
  if (!pw) return { score: 0, label: '', color: 'inherit' }
  let score = passwordChecks(pw).filter((c) => c.ok).length
  if (pw.length >= 14) score += 1
  if (/^(.)\1+$/.test(pw) || /^(password|qwerty|123456)/i.test(pw)) score = 0
  const levels = [
    { label: 'Very weak', color: 'error' },
    { label: 'Weak', color: 'error' },
    { label: 'Fair', color: 'warning' },
    { label: 'Good', color: 'info' },
    { label: 'Strong', color: 'success' },
    { label: 'Very strong', color: 'success' },
  ]
  return { score, ...levels[Math.min(score, levels.length - 1)] }
}
