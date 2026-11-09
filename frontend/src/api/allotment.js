import client, { generateIdempotencyKey } from './client'

// NO payment APIs — flow is HELD -> all members accept -> CONFIRMED

export const getMyAllotment = (cycleId) =>
  (cycleId
    ? client.get(`/cycles/${cycleId}/allotments/mine`)
    : client.get('/allotments/mine')
  ).then((r) => r.data)

export const acceptAllotment = (allotmentId) =>
  client.post(`/allotments/${allotmentId}/accept`, {}, {
    headers: { 'Idempotency-Key': generateIdempotencyKey() },
  }).then((r) => r.data)

export const declineAllotment = (allotmentId) =>
  client.post(`/allotments/${allotmentId}/decline`, {}, {
    headers: { 'Idempotency-Key': generateIdempotencyKey() },
  }).then((r) => r.data)

export const cancelAllotment = (allotmentId) =>
  client.post(`/allotments/${allotmentId}/cancel`, {}, {
    headers: { 'Idempotency-Key': generateIdempotencyKey() },
  }).then((r) => r.data)

// Admin / Warden actions
export const listAllotments = (params = {}) =>
  client.get('/admin/allotments', { params }).then((r) => r.data)

export const revokeAllotment = (allotmentId, reason) =>
  client.post(`/admin/allotments/${allotmentId}/revoke`, { reason }, {
    headers: { 'Idempotency-Key': generateIdempotencyKey() },
  }).then((r) => r.data)

export const extendHold = (allotmentId, reason, extraHours = 24) =>
  client.post(`/admin/allotments/${allotmentId}/extend`, { reason, extra_hours: extraHours }, {
    headers: { 'Idempotency-Key': generateIdempotencyKey() },
  }).then((r) => r.data)

export const assignRoom = (cycleId, applicationId, roomId) =>
  client.post(`/admin/applications/${applicationId}/assign`, { cycle_id: cycleId, room_id: roomId }, {
    headers: { 'Idempotency-Key': generateIdempotencyKey() },
  }).then((r) => r.data)
