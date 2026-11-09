import client, { generateIdempotencyKey } from './client'

export const createGroup = (cycleId, { name = '', solo = false } = {}) =>
  client.post(`/cycles/${cycleId}/groups`, { name, solo }, {
    headers: { 'Idempotency-Key': generateIdempotencyKey() },
  }).then((r) => r.data)

export const getMyGroup = (cycleId) =>
  client.get(`/cycles/${cycleId}/groups/mine`).then((r) => r.data)

export const getMyInvites = (cycleId) =>
  client.get(`/cycles/${cycleId}/invites/mine`).then((r) => r.data)

export const inviteMember = (groupId, identifier) =>
  client.post(`/groups/${groupId}/invites`, { identifier }, {
    headers: { 'Idempotency-Key': generateIdempotencyKey() },
  }).then((r) => r.data)

export const acceptInvite = (membershipId) =>
  client.post(`/invites/${membershipId}/accept`, {}, {
    headers: { 'Idempotency-Key': generateIdempotencyKey() },
  }).then((r) => r.data)

export const declineInvite = (membershipId) =>
  client.post(`/invites/${membershipId}/decline`, {}, {
    headers: { 'Idempotency-Key': generateIdempotencyKey() },
  }).then((r) => r.data)

export const removeMember = (groupId, userId) =>
  client.delete(`/groups/${groupId}/members/${userId}`, {
    headers: { 'Idempotency-Key': generateIdempotencyKey() },
  }).then((r) => r.data)

export const disbandGroup = (groupId) =>
  client.delete(`/groups/${groupId}`, {
    headers: { 'Idempotency-Key': generateIdempotencyKey() },
  }).then((r) => r.data)

export const saveApplication = (groupId, { cycle_id, ranked_choices, fallback = 'NONE', version }) =>
  client.put(`/groups/${groupId}/application`, { cycle_id, ranked_choices, fallback, version }).then((r) => r.data)

export const submitApplication = (groupId, { cycle_id, ranked_choices, fallback } = {}) =>
  client.post(`/groups/${groupId}/application/submit`, { cycle_id, ranked_choices, fallback }, {
    headers: { 'Idempotency-Key': generateIdempotencyKey() },
  }).then((r) => r.data)

export const withdrawApplication = (groupId, cycleId) =>
  client.post(`/groups/${groupId}/application/withdraw`, { cycle_id: cycleId }, {
    headers: { 'Idempotency-Key': generateIdempotencyKey() },
  }).then((r) => r.data)

export const getApplication = (groupId, cycleId) =>
  client.get(`/groups/${groupId}/application`, { params: cycleId ? { cycle_id: cycleId } : {} }).then((r) => r.data)
