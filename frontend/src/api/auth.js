import client from './client'

export const login = (identifier, password) =>
  client.post('/auth/login', { identifier, password }).then((r) => r.data)

export const refreshSession = () =>
  client.post('/auth/refresh').then((r) => r.data)

export const activate = (token, password) =>
  client.post('/auth/activate', { token, password }).then((r) => r.data)

export const forgotPassword = (email) =>
  client.post('/auth/forgot', { email }).then((r) => r.data)

export const resetPassword = (token, newPassword) =>
  client.post('/auth/reset', { token, new_password: newPassword }).then((r) => r.data)

export const changePassword = (oldPassword, newPassword) =>
  client.post('/auth/change-password', {
    old_password: oldPassword,
    new_password: newPassword,
  }).then((r) => r.data)

export const logout = () =>
  client.post('/auth/logout').then((r) => r.data)

export const logoutAll = () =>
  client.post('/auth/logout-all').then((r) => r.data)

export const listSessions = () =>
  client.get('/auth/sessions').then((r) => r.data)

export const revokeSession = (familyId) =>
  client.delete(`/auth/sessions/${familyId}`).then((r) => r.data)

export const getMe = () =>
  client.get('/me').then((r) => r.data)

export const getCredits = (params = {}) =>
  client.get('/me/credits', { params }).then((r) => r.data)

export const getFairnessExplanation = (cycleId) =>
  client.get('/me/fairness', { params: cycleId ? { cycle_id: cycleId } : {} }).then((r) => r.data)

export const getNotifications = (params = {}) =>
  client.get('/me/notifications', { params }).then((r) => r.data)

export const getUnreadNotificationCount = () =>
  client.get('/me/notifications/unread-count').then((r) => r.data)

export const markNotificationRead = (notificationId) =>
  client.post(`/me/notifications/${notificationId}/read`).then((r) => r.data)

export const markAllNotificationsRead = () =>
  client.post('/me/notifications/read-all').then((r) => r.data)

export const getNotificationSummary = () =>
  client.get('/me/notifications/summary').then((r) => r.data)

export const getSecurityActivity = (limit = 20) =>
  client.get('/me/security-activity', { params: { limit } }).then((r) => r.data)
