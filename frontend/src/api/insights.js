import client from './client'

/** Anonymous aggregate demand for every room in a cycle. */
export const getRoomDemand = (cycleId) =>
  client.get(`/cycles/${cycleId}/room-demand`).then((r) => r.data)

/** The signed-in student's position in the cascade waitlist for a cycle. */
export const getMyWaitlistPosition = (cycleId) =>
  client.get(`/cycles/${cycleId}/waitlist/me`).then((r) => r.data)
