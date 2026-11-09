import client, { generateIdempotencyKey } from './client'

export const listUsers = (params = {}) =>
  client.get('/admin/users', { params }).then((r) => r.data)

export const listWardenStudents = (params = {}) =>
  client.get('/warden/users', { params }).then((r) => r.data)

export const importUsers = (fileOrFormData) => {
  const formData = fileOrFormData instanceof FormData ? fileOrFormData : new FormData()
  if (!(fileOrFormData instanceof FormData)) {
    formData.append('file', fileOrFormData)
  }
  return client.post('/admin/users/import', formData).then((r) => r.data)
}

export const enableUser = (userId) =>
  client.put(`/admin/users/${userId}/enable`).then((r) => r.data)

export const disableUser = (userId) =>
  client.put(`/admin/users/${userId}/disable`).then((r) => r.data)

export const unlockUser = (userId) =>
  client.put(`/admin/users/${userId}/unlock`).then((r) => r.data)

export const updateUserHostels = (userId, data) =>
  client.put(`/admin/users/${userId}/hostels`, data).then((r) => r.data)

export const grantRole = (data) =>
  client.post('/admin/role-grants', data, {
    headers: { 'Idempotency-Key': generateIdempotencyKey() },
  }).then((r) => r.data)

export const listRoleGrants = (params = {}) =>
  client.get('/admin/role-grants', { params }).then((r) => r.data)

export const revokeRoleGrant = (grantId) =>
  client.delete(`/admin/role-grants/${grantId}`, {
    headers: { 'Idempotency-Key': generateIdempotencyKey() },
  }).then((r) => r.data)

export const listAuditLogs = (params = {}) =>
  client.get('/admin/audit-logs', { params }).then((r) => r.data)

export const getOccupancyReport = (params = {}) =>
  client.get('/reports/occupancy', { params }).then((r) => r.data)

export const getFairnessReport = (params = {}) =>
  client.get('/reports/fairness', { params }).then((r) => r.data)

export const getRejectionReport = (params = {}) =>
  client.get('/reports/rejections', { params }).then((r) => r.data)

export const createHostel = (data) =>
  client.post('/admin/hostels', data, {
    headers: { 'Idempotency-Key': generateIdempotencyKey() },
  }).then((r) => r.data)

export const createFloor = (hostelId, data) =>
  client.post(`/admin/hostels/${hostelId}/floors`, data, {
    headers: { 'Idempotency-Key': generateIdempotencyKey() },
  }).then((r) => r.data)

export const createRoomsFromList = (
  floorId,
  roomNumbers,
  { capacity = 2, skipExisting = false, dryRun = false } = {}
) =>
  client.post(
    `/admin/floors/${floorId}/rooms/from-list`,
    {
      room_numbers: roomNumbers,
      capacity,
      skip_existing: skipExisting,
      dry_run: dryRun,
    },
    { params: { dry_run: dryRun } }
  ).then((r) => r.data)

export const bulkCreateRooms = (floorId, data) =>
  client.post(`/admin/floors/${floorId}/rooms/bulk`, data, {
    headers: { 'Idempotency-Key': generateIdempotencyKey() },
  }).then((r) => r.data)

export const updateRoom = (roomId, data) =>
  client.patch(`/admin/rooms/${roomId}`, data).then((r) => r.data)

export const verifyAccessibility = (userId, data) =>
  client.put(`/warden/users/${userId}/accessibility`, data).then((r) => r.data)

export const listAllotments = (params = {}) =>
  client.get('/admin/allotments', { params }).then((r) => r.data)
