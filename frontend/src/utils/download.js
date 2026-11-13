/**
 * Save a Blob as a file. Needed because the API uses an in-memory bearer token,
 * so exports can't be plain <a href> links: we fetch with axios, then save.
 */
export function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

/** Pull the filename out of a Content-Disposition header, with a fallback. */
export function filenameFromDisposition(header, fallback) {
  const match = /filename="?([^";]+)"?/i.exec(header || '')
  return match ? match[1] : fallback
}
