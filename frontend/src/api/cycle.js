import client, { generateIdempotencyKey } from './client'

export const listCycles = (params = {}) =>
  client.get('/cycles', { params }).then((r) => r.data)

export const getCycle = (cycleId) =>
  client.get(`/cycles/${cycleId}`).then((r) => r.data)

export const createCycle = (data) =>
  client.post('/admin/cycles', data, {
    headers: { 'Idempotency-Key': generateIdempotencyKey() },
  }).then((r) => r.data)

export const updateCycle = (cycleId, data) =>
  client.put(`/admin/cycles/${cycleId}`, data).then((r) => r.data)

export const openCycle = (cycleId) =>
  client.post(`/admin/cycles/${cycleId}/open`, {}, {
    headers: { 'Idempotency-Key': generateIdempotencyKey() },
  }).then((r) => r.data)

export const scheduleCycle = (cycleId, data) =>
  client.post(`/admin/cycles/${cycleId}/schedule`, data, {
    headers: { 'Idempotency-Key': generateIdempotencyKey() },
  }).then((r) => r.data)

export const extendCycle = (cycleId, data) =>
  client.post(`/admin/cycles/${cycleId}/extend`, data, {
    headers: { 'Idempotency-Key': generateIdempotencyKey() },
  }).then((r) => r.data)

export const closeCycleEarly = (cycleId) =>
  client.post(`/admin/cycles/${cycleId}/close-window`, {}, {
    headers: { 'Idempotency-Key': generateIdempotencyKey() },
  }).then((r) => r.data)

export const reopenCycle = (cycleId, data) =>
  client.post(`/admin/cycles/${cycleId}/reopen`, data, {
    headers: { 'Idempotency-Key': generateIdempotencyKey() },
  }).then((r) => r.data)

export const cancelCycle = (cycleId, reason = '') =>
  client.post(`/admin/cycles/${cycleId}/cancel`, { reason }, {
    headers: { 'Idempotency-Key': generateIdempotencyKey() },
  }).then((r) => r.data)

export const previewAllocation = (cycleId) =>
  client.post(`/admin/cycles/${cycleId}/preview-allocation`, {}, {
    headers: { 'Idempotency-Key': generateIdempotencyKey() },
  }).then((r) => r.data)

export const runAllocation = (cycleId) =>
  client.post(`/admin/cycles/${cycleId}/allocate`, {}, {
    headers: { 'Idempotency-Key': generateIdempotencyKey() },
  }).then((r) => r.data)

export const settleCycle = (cycleId) =>
  client.post(`/admin/cycles/${cycleId}/settle`, {}, {
    headers: { 'Idempotency-Key': generateIdempotencyKey() },
  }).then((r) => r.data)

export const runCascade = (cycleId) =>
  client.post(`/admin/cycles/${cycleId}/cascade`, {}, {
    headers: { 'Idempotency-Key': generateIdempotencyKey() },
  }).then((r) => r.data)

export const cascade = runCascade

export const getAuditData = (cycleId) =>
  client.get(`/cycles/${cycleId}/audit`).then((r) => r.data)

export const verifyCycle = getAuditData
