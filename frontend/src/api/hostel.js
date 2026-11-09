import client from './client'

export const listHostels = (params = {}) =>
  client.get('/hostels', { params }).then((r) => r.data)

export const getHostel = (hostelId) =>
  client.get(`/hostels/${hostelId}`).then((r) => r.data)

export const listFloors = (hostelId) =>
  client.get(`/hostels/${hostelId}/floors`).then((r) => r.data)

export const listHostelRooms = (hostelId, params = {}) =>
  client.get(`/hostels/${hostelId}/rooms`, { params }).then((r) => r.data)

export const listRoomsInCycle = (cycleId, params = {}) =>
  client.get(`/cycles/${cycleId}/rooms`, { params }).then((r) => r.data)

export const listFloorsInCycle = (cycleId, hostelId) =>
  (hostelId
    ? client.get(`/cycles/${cycleId}/hostels/${hostelId}/floors`)
    : client.get(`/cycles/${cycleId}/floors`)
  ).then((r) => r.data)

export const getAvailabilitySummary = (cycleId) =>
  client.get(`/cycles/${cycleId}/availability-summary`).then((r) => r.data)
