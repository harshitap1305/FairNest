import client from './client'
import { saveBlob, filenameFromDisposition } from '../utils/download'

async function download(url, params, fallbackName) {
  const res = await client.get(url, { params, responseType: 'blob' })
  saveBlob(res.data, filenameFromDisposition(res.headers['content-disposition'], fallbackName))
}

export const downloadAllotmentRoster = (cycleId, status) =>
  download(`/admin/cycles/${cycleId}/allotments.csv`, status ? { status } : {}, 'allotments.csv')

export const downloadAuditLogs = (params = {}) =>
  download('/admin/audit-logs.csv', params, 'audit_logs.csv')

export const getOperationsOverview = () =>
  client.get('/reports/overview').then((r) => r.data)
